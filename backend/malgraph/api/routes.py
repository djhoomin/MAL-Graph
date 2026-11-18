from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from .. import anilist, db, ingest, jobs, mal_export, tour, users
from .. import jikan as jikan_client
from ..jikan import JikanClient, JikanError
from ..mal import MalError, iter_user_animelist
from ..config import settings
from . import queries as Q
from .serialize import PayloadBuilder, node_payload

router = APIRouter(prefix="/api")
Label = Literal["Anime", "Character", "Person", "Studio", "Genre", "User"]


# Server-wide caps on slow work, so a burst of requests can't tie up every worker thread. A request waits up to
# SLOT_WAIT seconds for a free slot, then gets a 503.
SLOT_WAIT = 10
_path_slots = threading.BoundedSemaphore(4)  # Memgraph path searches (each can run up to the 30 s query timeout)
_fetch_slots = threading.BoundedSemaphore(6)  # on-demand MAL fetches, which mostly wait on Jikan's rate limit


@contextmanager
def _slot(sem: threading.BoundedSemaphore, busy: str) -> Iterator[None]:
    """For sync routes, which already run on a worker thread."""
    if not sem.acquire(timeout=SLOT_WAIT):
        raise HTTPException(503, busy)
    try:
        yield
    finally:
        sem.release()


def jikan() -> JikanClient:
    return jikan_client.shared()


def _records(query: str, **params: Any) -> list[Any]:
    """Run a query; $user / $watched / $franchise are filled in for the current user."""
    with db.get_driver().session() as session:
        return list(session.run(query, **{**users.params_for(query), **params}))


def _parse_ref(ref: str) -> tuple[str, Any]:
    """'Anime:5114' -> ('Anime', 5114)."""
    try:
        label, key = ref.split(":", 1)
    except ValueError:
        raise HTTPException(400, f"bad node ref {ref!r}; expected Label:id")
    if label not in Q.NODE_LABELS:
        raise HTTPException(400, f"unknown label {label!r}")
    if label == "User":
        # Lists are private to their owner: the only user node anyone can open is their own.
        me = users.current_username()
        if not me or key.lower() != me.lower():
            raise HTTPException(404, f"User:{key} not found")
        return label, me
    try:
        return label, int(key)
    except ValueError:
        raise HTTPException(400, f"bad id {key!r}")


def _node(label: str, key: Any) -> Any:
    q = Q.NODE_USER if label == "User" else Q.NODE % label
    recs = _records(q, id=key)
    if not recs:
        raise HTTPException(404, f"{label}:{key} not found")
    return recs[0]["n"]


@router.get("/search")
def search(q: str = Query(min_length=1), kinds: str = "Anime,Character,Person,Studio", limit: int = 10) -> dict[str, Any]:
    q_lower = q.strip().lower()
    out: dict[str, list[dict[str, Any]]] = {}
    for label in kinds.split(","):
        if label in Q.SEARCH:
            out[label] = [node_payload(r["n"]) for r in _records(Q.SEARCH[label], q=q_lower, limit=limit)]
    return {"query": q, "results": out}


@router.get("/node/{ref}")
def node_detail(ref: str) -> dict[str, Any]:
    label, key = _parse_ref(ref)
    n = _node(label, key)
    degrees = [] if label == "User" else [r.data() for r in _records(Q.DEGREES % label, id=key)]
    return {"node": node_payload(n, full=True), "degrees": degrees}


@router.get("/neighbors/{ref}")
def neighbors(
    ref: str,
    rels: str = ",".join(Q.REL_TYPES),
    only_watched: bool = False,
    lang: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    label, key = _parse_ref(ref)
    limit = max(1, min(int(limit), 2000))
    if label == "User":
        recs = _records(Q.NEIGHBORS_USER, id=key, only_watched=only_watched, limit=limit)
    else:
        recs = _records(Q.NEIGHBORS % label, id=key, rels=rels.split(","), only_watched=only_watched, lang=lang or None, limit=limit)
    if not recs:
        _node(label, key)  # 404 if the node itself is missing
    return PayloadBuilder().add_records(recs).build(center=ref)


@router.post("/expand/{ref}")
async def expand(ref: str, only_watched: bool = False, lang: str | None = None) -> dict[str, Any]:
    """Fetch this node's full neighbourhood from Jikan, then return neighbours from the DB."""
    label, key = _parse_ref(ref)
    fn = {"Anime": ingest.expand_anime, "Person": ingest.expand_person, "Character": ingest.expand_character}.get(label)
    if fn is None:
        raise HTTPException(400, f"{label} nodes cannot be expanded from MAL")
    t0 = time.time()
    try:
        # Wait for a slot on a worker thread, not the event loop.
        if not await run_in_threadpool(_fetch_slots.acquire, True, SLOT_WAIT):
            raise HTTPException(503, "Many people are fetching anime right now. Try again in a moment.")
        try:
            summary = await run_in_threadpool(fn, jikan(), key)
        finally:
            _fetch_slots.release()
    except JikanError as e:
        raise HTTPException(502, str(e))
    payload = neighbors(ref, only_watched=only_watched, lang=lang)
    return {**payload, "fetched": summary, "seconds": round(time.time() - t0, 2)}


@router.get("/path")
def path(
    from_: str = Query(alias="from"),
    to: str = Query(),
    max_hops: int = Query(8, ge=1, le=15),
    only_watched: bool = False,
    exclude: str = "User,Genre",
    rels: str = ",".join(Q.REL_TYPES),
    lang: str | None = None,
    all_paths: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    a_label, a_key = _parse_ref(from_)
    b_label, b_key = _parse_ref(to)
    if "User" in (a_label, b_label):
        raise HTTPException(400, "paths from/to User are not supported")
    limit = max(1, min(int(limit), 50))
    template = Q.ALL_SHORTEST_PATHS if all_paths else Q.SHORTEST_PATH
    query = template % (a_label, b_label, max_hops)
    with _slot(_path_slots, "The server is busy finding other paths. Try again in a moment."):
        recs = _records(
            query, from_id=a_key, to_id=b_key,
            # Paths never pass through user nodes, so they can't link two people's lists.
            exclude=list({"User", *(e for e in exclude.split(",") if e)}), rels=[r for r in rels.split(",") if r and r != "LISTED"],
            only_watched=only_watched, lang=lang or None, limit=limit,
        )
    paths = [r["p"] for r in recs]
    builder = PayloadBuilder()
    for p in paths:
        builder.add(p)
    return builder.build(
        found=bool(paths),
        hops=len(paths[0].relationships) if paths else None,
        paths=[[builder_node_id(n) for n in p.nodes] for p in paths],
    )


def builder_node_id(n: Any) -> str:
    from .serialize import node_id
    return node_id(n)


node_id_of = builder_node_id


@router.get("/person/{person_id}/characters")
def person_characters(person_id: int, only_watched: bool = True, lang: str | None = "Japanese") -> dict[str, Any]:
    recs = _records(Q.VA_ROLES, id=person_id, only_watched=only_watched, lang=lang or None)
    if not recs:
        _node("Person", person_id)
    builder = PayloadBuilder().add_records(recs)
    roles = [
        {
            "character": node_payload(r["c"]),
            "anime": node_payload(r["a"]),
            "role": r["h"].get("role"),
            "language": r["v"].get("language"),
        }
        for r in recs
    ]
    return builder.build(roles=roles)


@router.get("/roster")
def roster(
    only_watched: bool = True,
    main_only: bool = False,
    lang: str | None = "Japanese",
    min_characters: int = Query(3, ge=1),
    q: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Voice actors with at least `min_characters` distinct characters (in watched anime by default)."""
    recs = _records(Q.ROSTER, only_watched=only_watched, main_only=main_only, lang=lang or None, min_characters=min_characters,
                    q=q.strip().lower() if q else None, limit=limit)
    return {"people": [{"person": node_payload(r["p"]), "characters": r["characters"], "anime": r["anime"]} for r in recs]}


@router.get("/user")
def user_summary() -> dict[str, Any]:
    rows = [r.data() for r in _records(Q.USER_SUMMARY)]
    return {
        "username": rows[0]["username"] if rows else users.current_username(),
        "by_status": {r["status"]: r["n"] for r in rows},
        "total": sum(r["n"] for r in rows),
        "unfetched": sum(r["unfetched"] for r in rows),
    }


PRIVATE_STATS = {"User", "LISTED", "listed_unfetched"}  # totals across users stay private


@router.get("/stats")
def stats() -> dict[str, Any]:
    """Size of the shared graph. The CLI's `stats` command shows the full picture, including users."""
    return {k: v for k, v in ingest.stats().items() if k not in PRIVATE_STATS}


# --------------------------------------------------------------------------- insights

ALL_STATUSES = ["completed", "watching", "on_hold", "dropped", "plan_to_watch"]
GAP_RELATIONS = ["Sequel", "Prequel", "Side Story", "Spin-Off", "Alternative Version", "Parent Story", "Alternative Setting"]


def _statuses(statuses: str | None) -> list[str]:
    return [s for s in (statuses or "").split(",") if s in ALL_STATUSES] or ALL_STATUSES


@router.get("/insights/list")
def insights_list() -> dict[str, Any]:
    """Every anime on the list with the fields the insights page charts."""
    return {"anime": [r.data() for r in _records(Q.INSIGHTS_LIST)]}


@router.get("/insights/people")
def insights_people(
    kind: str = "va",
    statuses: str | None = None,
    lang: str | None = "Japanese",
    min_anime: int = Query(2, ge=1),
    limit: int = 50,
) -> dict[str, Any]:
    """Ranked people: kind='va' (voice actors) or a staff position such as 'Director' or 'Music'."""
    if kind == "va":
        recs = _records(Q.INSIGHTS_VA, statuses=_statuses(statuses), lang=lang or None, min=min_anime, limit=limit)
    else:
        recs = _records(Q.INSIGHTS_STAFF, statuses=_statuses(statuses), position=kind, min=min_anime, limit=limit)
    return {
        "kind": kind,
        "people": [
            {"person": node_payload(r["p"]), "anime_ids": r["anime_ids"], "characters": r["characters"], "avg_my_score": r["avg_my_score"]}
            for r in recs
        ],
    }


@router.get("/insights/gaps")
def insights_gaps(statuses: str | None = "completed,watching", relations: str | None = None) -> dict[str, Any]:
    rels = [r for r in (relations or "").split(",") if r] or GAP_RELATIONS
    return {"gaps": [r.data() for r in _records(Q.INSIGHTS_GAPS, statuses=_statuses(statuses), relations=rels)]}


STAFF_POSITIONS = ["Director", "Series Composition", "Music", "Character Design", "Original Creator"]


@router.get("/insights/recommendations")
def insights_recommendations(
    via: str = "va",
    lang: str | None = "Japanese",
    min_score: float | None = 7.0,
    types: str = "TV,Movie,ONA",
    limit: int = 40,
) -> dict[str, Any]:
    """Unseen anime ranked by connections to the user's voice actors ('va'), staff ('staff') or studios ('studio')."""
    q = {"va": Q.RECS_VA, "staff": Q.RECS_STAFF, "studio": Q.RECS_STUDIO}.get(via)
    if q is None:
        raise HTTPException(400, "via must be va, staff or studio")
    recs = _records(q, lang=lang or "Japanese", positions=STAFF_POSITIONS, min_score=min_score, types=types.split(","), limit=limit)
    return {
        "via": via,
        "recommendations": [
            {"anime": node_payload(r["b"]), "score": round(r["score"], 2), "via": r["via"], "n_people": r["n_people"]}
            for r in recs
        ],
    }


# --------------------------------------------------------------------------- list sync

SYNC_COOLDOWN = 60  # seconds between list syncs for the same user (each one calls the MAL API)
_last_sync: dict[str, float] = {}


def sync_user(username: str, token: str | None = None, anilist_id: int | None = None) -> dict[str, Any]:
    """Re-read a user's list from MyAnimeList or AniList, then queue any anime not yet in the graph for background
    fetching.

    Raises HTTPException for the cooldown and for errors from the list's site. With a token (straight after sign-in)
    a private list can be read too.
    """
    # MAL usernames are case-insensitive: reuse an existing user rather than creating a second one.
    username = users.canonical(username)
    _cooldown(username)
    skipped: list[int] = []
    if settings.anilist_source and not anilist.is_anilist(username):
        raise HTTPException(400, "This site reads lists from AniList. Sign in with AniList, or upload a MyAnimeList export.")
    try:
        if anilist.is_anilist(username):
            n = ingest.upsert_user_list(username, anilist.iter_list(username, token=token, user_id=anilist_id, skipped=skipped))
        else:
            n = ingest.upsert_user_list(username, iter_user_animelist(username, token=token))
    except (MalError, anilist.AniListError) as e:
        raise HTTPException(e.status if e.status in (403, 404) else 502, str(e))
    return _after_sync(username, n, len(skipped))


def _cooldown(username: str) -> None:
    wait = SYNC_COOLDOWN - (time.time() - _last_sync.get(username.lower(), 0))
    if wait > 0:
        raise HTTPException(429, f"Your list was synced a moment ago. Try again in {int(wait) + 1} seconds.")


def _after_sync(username: str, n: int, skipped: int) -> dict[str, Any]:
    """After a list was replaced: start the cooldown, and queue anime not yet in the graph for fetching."""
    _last_sync[username.lower()] = time.time()
    tour.invalidate(username)
    stubs = ingest.listed_stub_ids(username)
    queued = jobs.queue.enqueue(username, stubs) if stubs else 0
    return {"username": username, "synced": n, "skipped": skipped, "unfetched": len(stubs),
            "expanding": queued > 0 or jobs.queue.status(username)["running"]}


@router.post("/sync")
async def sync_list() -> dict[str, Any]:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in first")
    return await run_in_threadpool(sync_user, username)


def import_export(username: str, data: bytes) -> dict[str, Any]:
    """Replace the user's list with the entries in a MyAnimeList list export."""
    username = users.canonical(username)
    _cooldown(username)
    try:
        exported_by, entries = mal_export.parse(data)
    except mal_export.ExportError as e:
        raise HTTPException(400, str(e))
    skipped = 0
    if settings.anilist_source:  # the graph uses AniList ids, so look each MyAnimeList id up
        try:
            ids = jikan().mal_to_anilist([e["node"]["id"] for e in entries])  # type: ignore[attr-defined]
        except JikanError as e:
            raise HTTPException(502, f"AniList couldn't be reached to match the export's anime: {e}")
        mapped = [{**e, "node": {**e["node"], "id": ids[e["node"]["id"]]}} for e in entries if e["node"]["id"] in ids]
        skipped, entries = len(entries) - len(mapped), mapped
    n = ingest.upsert_user_list(username, iter(entries))
    return {**_after_sync(username, n, skipped), "exported_by": exported_by}


@router.post("/sync/upload")
async def upload_list(request: Request) -> dict[str, Any]:
    """The file from MyAnimeList's Export lists, sent as the raw request body, gzipped or not."""
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in first")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > mal_export.MAX_UPLOAD:
            raise HTTPException(413, "That file is too big to be a MyAnimeList anime list export.")
    if not data:
        raise HTTPException(400, "The file was empty.")
    return await run_in_threadpool(import_export, username, bytes(data))


@router.get("/sync/status")
def sync_status() -> dict[str, Any]:
    return jobs.queue.status(users.current_username())


# --------------------------------------------------------------------------- ask the graph (agent)

from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import agent, limits


class AskBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


def _require_user() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to ask questions")
    return username


@router.get("/conversations")
def conversations() -> dict[str, Any]:
    _require_user()
    return {"conversations": agent.list_conversations()}


@router.get("/conversations/{cid}")
def conversation(cid: str) -> dict[str, Any]:
    _require_user()
    try:
        conv = agent.load_conversation(cid)
    except ValueError:
        raise HTTPException(400, "bad id")
    if conv is None:
        raise HTTPException(404, "conversation not found")
    return {k: conv[k] for k in ("id", "title", "model", "created_at", "updated_at", "turns")}


class RenameBody(BaseModel):
    title: str = Field(max_length=200)


@router.patch("/conversations/{cid}")
def rename(cid: str, body: RenameBody) -> dict[str, Any]:
    _require_user()
    try:
        conv = agent.rename_conversation(cid, body.title)
    except ValueError:
        raise HTTPException(400, "bad id")
    if conv is None:
        raise HTTPException(404, "conversation not found")
    return {"id": cid, "title": conv["title"]}


class FeedbackBody(BaseModel):
    run_id: str = Field(max_length=64)
    score: int | None = Field(default=None, ge=0, le=1)


@router.post("/conversations/{cid}/feedback")
def feedback(cid: str, body: FeedbackBody) -> dict[str, Any]:
    """Thumbs up (1) or down (0) on one answer, or no score to take it back."""
    _require_user()
    try:
        result = agent.set_feedback(cid, body.run_id, body.score)
    except ValueError:
        raise HTTPException(400, "bad id")
    if result is None:
        raise HTTPException(404, "answer not found")
    return result


class SubgraphBody(BaseModel):
    refs: list[str] = Field(max_length=150)


@router.post("/subgraph")
def subgraph(body: SubgraphBody) -> dict[str, Any]:
    """Nodes for these refs and the edges between them, to draw a step of an Ask answer again."""
    refs = [r for r in body.refs if re.fullmatch(r"(Anime|Character|Person|Studio|Genre):\d+", r)]
    return agent._subgraph(refs) if refs else {"nodes": [], "edges": []}


@router.delete("/conversations/{cid}")
def delete(cid: str) -> dict[str, Any]:
    _require_user()
    try:
        return {"deleted": agent.delete_conversation(cid)}
    except ValueError:
        raise HTTPException(400, "bad id")


@router.get("/ask/status")
def ask_status() -> dict[str, Any]:
    username = users.current_username()
    return {
        "configured": agent.configured(),
        "model": settings.openrouter_model if agent.configured() else None,
        "remaining_today": limits.remaining(username) if username else None,  # None means no cap
    }


@router.post("/ask")
async def ask(body: AskBody, request: Request) -> StreamingResponse:
    """Server-sent events: one JSON event per line ("data: {...}\n\n")."""
    username = _require_user()
    slot = limits.ask_slot(username)
    try:
        tokens = slot.__enter__()  # counts the question; released when the stream ends
    except limits.LimitReached as e:
        raise HTTPException(429, str(e))

    async def gen():
        try:
            async for ev in agent.run(body.session_id, body.message):
                if ev.get("type") == "done":
                    tokens["prompt_tokens"] += ev["usage"].get("prompt_tokens", 0)
                    tokens["completion_tokens"] += ev["usage"].get("completion_tokens", 0)
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        finally:
            slot.__exit__(None, None, None)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
