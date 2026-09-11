from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from .. import db, ingest
from ..jikan import JikanClient, JikanError
from . import queries as Q
from .serialize import PayloadBuilder, node_payload

router = APIRouter(prefix="/api")
Label = Literal["Anime", "Character", "Person", "Studio", "Genre", "User"]
_jikan: JikanClient | None = None


def jikan() -> JikanClient:
    global _jikan
    if _jikan is None:
        _jikan = JikanClient()
    return _jikan


def _records(query: str, **params: Any) -> list[Any]:
    with db.get_driver().session() as session:
        return list(session.run(query, **params))


def _parse_ref(ref: str) -> tuple[str, Any]:
    """'Anime:5114' -> ('Anime', 5114)."""
    try:
        label, key = ref.split(":", 1)
    except ValueError:
        raise HTTPException(400, f"bad node ref {ref!r}; expected Label:id")
    if label not in Q.NODE_LABELS:
        raise HTTPException(400, f"unknown label {label!r}")
    return label, (key if label == "User" else int(key))


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
        summary = await run_in_threadpool(fn, jikan(), key)
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
    lang: str | None = None,
    all_paths: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    a_label, a_key = _parse_ref(from_)
    b_label, b_key = _parse_ref(to)
    if "User" in (a_label, b_label):
        raise HTTPException(400, "paths from/to User are not supported")
    template = Q.ALL_SHORTEST_PATHS if all_paths else Q.SHORTEST_PATH
    query = template % (a_label, b_label, max_hops)
    recs = _records(
        query, from_id=a_key, to_id=b_key,
        exclude=[e for e in exclude.split(",") if e], only_watched=only_watched, lang=lang or None, limit=limit,
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


@router.get("/person/{mal_id}/characters")
def person_characters(mal_id: int, only_watched: bool = True, lang: str | None = "Japanese") -> dict[str, Any]:
    recs = _records(Q.VA_ROLES, id=mal_id, only_watched=only_watched, lang=lang or None)
    if not recs:
        _node("Person", mal_id)
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
        "username": rows[0]["username"] if rows else None,
        "by_status": {r["status"]: r["n"] for r in rows},
        "total": sum(r["n"] for r in rows),
        "unfetched": sum(r["unfetched"] for r in rows),
    }


@router.get("/stats")
def stats() -> dict[str, Any]:
    return ingest.stats()
