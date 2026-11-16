"""Character genders from AniList, which records them (MyAnimeList doesn't).

AniList anime carry MyAnimeList ids, so for each anime we ask AniList for its cast and match characters by name
within that one cast. MyAnimeList writes "Last, First" and AniList "First Last", so names are compared as sets of
words. A sample of 51 main characters matched 100% and 98% had a gender.

A background worker fills genders in for anime on players' lists (not the whole graph: AniList's terms forbid mass
collection), seen anime first, at a polite rate (AniList allows about 30 requests a minute). Each anime is marked
with genders_at so it is asked once, and anime added to a list later are picked up automatically.
Corrections made by players are stored with gender_source = 'user' and are never overwritten.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from typing import Any

import httpx

from . import db

log = logging.getLogger(__name__)

URL = "https://graphql.anilist.co"
PER_MINUTE = 25  # AniList's limit is currently 30; stay under it
IDLE = 600  # seconds to wait when everything is done before looking for new anime
GENDERS = ["Female", "Male", "Non-binary"]  # the choices offered for corrections

QUERY = """query ($id: Int, $page: Int) { Media(idMal: $id, type: ANIME) {
  characters(page: $page, perPage: 50, sort: ROLE) { pageInfo { hasNextPage }
    edges { node { name { full alternative } gender } } } } }"""


def _words(name: str | None) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.findall(r"[a-z0-9]+", text)))


class AniList:
    def __init__(self) -> None:
        self._http = httpx.Client(timeout=20, headers={"User-Agent": "MAL-Graph (non-commercial)"})
        self._last = 0.0

    def _post(self, variables: dict[str, Any]) -> dict[str, Any] | None:
        for _ in range(3):
            wait = 60 / PER_MINUTE - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self._http.post(URL, json={"query": QUERY, "variables": variables})
            if resp.status_code == 429:  # back off as told, then retry
                time.sleep(int(resp.headers.get("Retry-After", "60")) + 1)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()["data"]["Media"]
        return None

    def cast(self, mal_id: int) -> dict[str, str | None] | None:
        """{name words: gender} for an anime's whole cast, or None if AniList doesn't know the anime."""
        out: dict[str, str | None] = {}
        for page in range(1, 6):
            media = self._post({"id": mal_id, "page": page})
            if not media:
                return out or None
            chars = media["characters"]
            for edge in chars["edges"]:
                node = edge["node"]
                for name in [node["name"]["full"], *(node["name"].get("alternative") or [])]:
                    out.setdefault(_words(name), node["gender"])
            if not chars["pageInfo"]["hasNextPage"]:
                break
        return out


def enrich_anime(client: AniList, mal_id: int) -> tuple[int, int]:
    """Set genders for one anime's characters. Returns (characters, with a gender)."""
    chars = db.run("MATCH (:Anime {id: $id})-[:HAS_CHARACTER]->(c:Character) RETURN c.id AS id, c.name AS name, c.gender_source AS src", id=mal_id)
    cast = client.cast(mal_id) if chars else None
    updates = []
    for c in chars:
        if c["src"] == "user" or not cast:
            continue
        gender = cast.get(_words(c["name"]))
        if gender:
            updates.append({"id": c["id"], "g": gender})
    if updates:
        db.run("UNWIND $rows AS r MATCH (c:Character {id: r.id}) WHERE coalesce(c.gender_source, '') <> 'user' "
               "SET c.gender = r.g, c.gender_source = 'anilist'", rows=updates)
    db.run("MATCH (a:Anime {id: $id}) SET a.genders_at = timestamp()", id=mal_id)
    return len(chars), len(updates)


# Only anime on someone's list. AniList's terms forbid "hoarding or mass collection", so genders are fetched for
# what players actually have, not the whole graph. Seen anime first, then plan-to-watch.
NEXT = """
    MATCH (:User)-[l:LISTED]->(a:Anime) WHERE a.genders_at IS NULL AND (a)-[:HAS_CHARACTER]->()
    WITH a, sum(CASE WHEN l.status <> 'plan_to_watch' THEN 1 ELSE 0 END) AS seen
    RETURN a.id AS id ORDER BY seen DESC, coalesce(a.members, 0) DESC LIMIT 50
"""


def _run() -> None:
    client = AniList()
    while True:
        try:
            batch = [r["id"] for r in db.run(NEXT)]
            if not batch:
                time.sleep(IDLE)
                continue
            for mal_id in batch:
                try:
                    enrich_anime(client, mal_id)
                except httpx.HTTPError as e:
                    log.warning("AniList lookup for anime %s failed: %s", mal_id, e)
                    time.sleep(30)
        except Exception:  # noqa: BLE001 - keep the worker alive (e.g. Memgraph restarting)
            log.exception("gender worker error")
            time.sleep(60)


_started = False


def start() -> None:
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_run, name="genders", daemon=True).start()


def correct(character_id: int, gender: str | None) -> bool:
    """A player's correction, shared by everyone. None means unknown. Returns False if there is no such character."""
    rows = db.run(
        "MATCH (c:Character {id: $id}) SET c.gender = $g, c.gender_source = 'user', c.gender_fixed_at = timestamp() RETURN c.id AS id",
        id=character_id, g=gender,
    )
    return bool(rows)


def coverage() -> dict[str, Any]:
    r = db.run("MATCH (a:Anime)-[:HAS_CHARACTER]->() WITH DISTINCT a RETURN count(a) AS anime, count(a.genders_at) AS done")[0]
    c = db.run("MATCH (c:Character) RETURN count(c) AS characters, count(c.gender) AS with_gender")[0]
    return {**r, **c}
