"""Upsert Jikan / MAL payloads into Memgraph. All writes are idempotent (MERGE) and batched via UNWIND."""
from __future__ import annotations

import re
import time
from typing import Any, Iterable

from . import db
from .jikan import JikanClient

# --------------------------------------------------------------------------- helpers

def _img(obj: dict[str, Any] | None) -> str | None:
    """Pick a jpg image url from a Jikan `images` block."""
    if not obj:
        return None
    jpg = obj.get("jpg") or {}
    return jpg.get("image_url") or jpg.get("small_image_url")


def _ref(obj: dict[str, Any] | None, name_key: str = "name") -> dict[str, Any]:
    """Minimal node payload from an embedded Jikan reference (person/character/anime)."""
    obj = obj or {}
    return {
        "mal_id": obj.get("mal_id"),
        "name": obj.get(name_key) or obj.get("name") or obj.get("title"),
        "image_url": _img(obj.get("images")),
        "url": obj.get("url"),
    }


def _now() -> int:
    return int(time.time())


def split_positions(text: str) -> list[str]:
    """'add Director (Chief Director), Series Composition (eps 1, 3)' -> ['Director', 'Series Composition'].
    Splits on commas outside parentheses and strips parenthetical notes."""
    text = text.removeprefix("add ").strip()
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    out: list[str] = []
    for part in parts:
        name = re.sub(r"\s*\(.*?\)\s*", " ", part).strip(" ,")
        if name and name not in out:
            out.append(name)
    return out


# --------------------------------------------------------------------------- anime

MEDIA_TYPE_MAP = {  # official MAL API media_type -> Jikan `type`
    "tv": "TV", "ova": "OVA", "movie": "Movie", "special": "Special",
    "ona": "ONA", "music": "Music", "tv_special": "TV Special", "cm": "CM", "pv": "PV",
}


def anime_props_from_full(d: dict[str, Any]) -> dict[str, Any]:
    aired = d.get("aired") or {}
    year = d.get("year") or ((aired.get("prop") or {}).get("from") or {}).get("year")
    return {
        "title": d.get("title"),
        "title_english": d.get("title_english"),
        "title_japanese": d.get("title_japanese"),
        "type": d.get("type"),
        "episodes": d.get("episodes"),
        "status": d.get("status"),
        "year": year,
        "season": d.get("season"),
        "score": d.get("score"),
        "scored_by": d.get("scored_by"),
        "rank": d.get("rank"),
        "popularity": d.get("popularity"),
        "members": d.get("members"),
        "rating": d.get("rating"),
        "source": d.get("source"),
        "duration": d.get("duration"),
        "aired_from": aired.get("from"),
        "synopsis": d.get("synopsis"),
        "image_url": _img(d.get("images")),
        "url": d.get("url"),
        "fetched_at": _now(),
    }


def upsert_anime_full(d: dict[str, Any]) -> None:
    mal_id = d["mal_id"]
    db.run(
        "MERGE (a:Anime {mal_id: $id}) SET a += $props",
        id=mal_id, props=anime_props_from_full(d),
    )

    studios = [{"mal_id": s["mal_id"], "name": s["name"], "url": s.get("url")} for s in d.get("studios") or []]
    if studios:
        db.run(
            """
            MATCH (a:Anime {mal_id: $id})
            UNWIND $rows AS row
            MERGE (s:Studio {mal_id: row.mal_id}) SET s.name = row.name, s.url = row.url
            MERGE (a)-[:PRODUCED_BY]->(s)
            """,
            id=mal_id, rows=studios,
        )

    genres: list[dict[str, Any]] = []
    for key, kind in (("genres", "genre"), ("explicit_genres", "explicit"), ("themes", "theme"), ("demographics", "demographic")):
        genres += [{"mal_id": g["mal_id"], "name": g["name"], "kind": kind} for g in d.get(key) or []]
    if genres:
        db.run(
            """
            MATCH (a:Anime {mal_id: $id})
            UNWIND $rows AS row
            MERGE (g:Genre {mal_id: row.mal_id}) SET g.name = row.name, g.kind = row.kind
            MERGE (a)-[:HAS_GENRE]->(g)
            """,
            id=mal_id, rows=genres,
        )

    relations: list[dict[str, Any]] = []
    for rel in d.get("relations") or []:
        for entry in rel.get("entry") or []:
            if entry.get("type") == "anime":
                relations.append({"mal_id": entry["mal_id"], "title": entry.get("name"), "url": entry.get("url"), "relation": rel["relation"]})
    if relations:
        db.run(
            """
            MATCH (a:Anime {mal_id: $id})
            UNWIND $rows AS row
            MERGE (b:Anime {mal_id: row.mal_id})
              ON CREATE SET b.title = row.title, b.url = row.url
            MERGE (a)-[r:RELATED_TO {relation: row.relation}]->(b)
            """,
            id=mal_id, rows=relations,
        )


def upsert_anime_characters(anime_id: int, rows: Iterable[dict[str, Any]]) -> None:
    chars: list[dict[str, Any]] = []
    voices: list[dict[str, Any]] = []
    for row in rows:
        c = _ref(row.get("character"))
        if c["mal_id"] is None:
            continue
        chars.append({**c, "role": row.get("role"), "favorites": row.get("favorites")})
        for va in row.get("voice_actors") or []:
            p = _ref(va.get("person"))
            if p["mal_id"] is None:
                continue
            voices.append({**p, "character_id": c["mal_id"], "language": va.get("language")})

    if chars:
        db.run(
            """
            MATCH (a:Anime {mal_id: $id})
            UNWIND $rows AS row
            MERGE (c:Character {mal_id: row.mal_id})
              SET c.name = row.name, c.image_url = coalesce(row.image_url, c.image_url), c.url = row.url,
                  c.favorites = coalesce(row.favorites, c.favorites)
            MERGE (a)-[h:HAS_CHARACTER]->(c) SET h.role = row.role
            """,
            id=anime_id, rows=chars,
        )
    if voices:
        db.run(
            """
            UNWIND $rows AS row
            MATCH (c:Character {mal_id: row.character_id})
            MERGE (p:Person {mal_id: row.mal_id})
              SET p.name = row.name, p.image_url = coalesce(row.image_url, p.image_url), p.url = row.url
            MERGE (p)-[v:VOICES]->(c)
              ON CREATE SET v.anime_ids = [$id], v.language = row.language
              ON MATCH SET v.language = coalesce(row.language, v.language),
                           v.anime_ids = CASE WHEN $id IN coalesce(v.anime_ids, []) THEN v.anime_ids
                                              ELSE coalesce(v.anime_ids, []) + [$id] END
            """,
            id=anime_id, rows=voices,
        )


def upsert_anime_staff(anime_id: int, rows: Iterable[dict[str, Any]]) -> None:
    staff = []
    for row in rows:
        p = _ref(row.get("person"))
        if p["mal_id"] is None:
            continue
        clean: list[str] = []
        for pos in row.get("positions") or []:
            for x in split_positions(pos):
                if x not in clean:
                    clean.append(x)
        staff.append({**p, "positions": clean})
    if staff:
        db.run(
            """
            MATCH (a:Anime {mal_id: $id})
            UNWIND $rows AS row
            MERGE (p:Person {mal_id: row.mal_id})
              SET p.name = row.name, p.image_url = coalesce(row.image_url, p.image_url), p.url = row.url
            MERGE (p)-[w:WORKED_ON]->(a) SET w.positions = row.positions
            """,
            id=anime_id, rows=staff,
        )


def expand_anime_light(j: JikanClient, mal_id: int) -> dict[str, int]:
    """Metadata only (/full): score, genres, studio, relations, image — no characters/staff. Marks the node light=true."""
    full = j.anime_full(mal_id)
    upsert_anime_full(full)
    db.run("MATCH (a:Anime {mal_id: $id}) SET a.light = true", id=mal_id)
    return {"relations": sum(len(r.get("entry") or []) for r in full.get("relations") or [])}


def expand_anime(j: JikanClient, mal_id: int) -> dict[str, int]:
    """Fetch /full, /characters, /staff for an anime and upsert everything."""
    full = j.anime_full(mal_id)
    upsert_anime_full(full)
    db.run("MATCH (a:Anime {mal_id: $id}) REMOVE a.light", id=mal_id)
    chars = j.anime_characters(mal_id)
    upsert_anime_characters(mal_id, chars)
    staff = j.anime_staff(mal_id)
    upsert_anime_staff(mal_id, staff)
    return {"characters": len(chars), "staff": len(staff), "relations": sum(len(r.get("entry") or []) for r in full.get("relations") or [])}


# --------------------------------------------------------------------------- person

def expand_person(j: JikanClient, mal_id: int) -> dict[str, int]:
    """/people/{id}/full: voice roles (anime + character, no language) and staff positions."""
    d = j.person_full(mal_id)
    db.run(
        "MERGE (p:Person {mal_id: $id}) SET p += $props",
        id=mal_id,
        props={
            "name": d.get("name"),
            "given_name": d.get("given_name"),
            "family_name": d.get("family_name"),
            "birthday": d.get("birthday"),
            "favorites": d.get("favorites"),
            "about": d.get("about"),
            "image_url": _img(d.get("images")),
            "url": d.get("url"),
            "fetched_at": _now(),
        },
    )
    voices = []
    for v in d.get("voices") or []:
        a, c = _ref(v.get("anime"), "title"), _ref(v.get("character"))
        if a["mal_id"] is None or c["mal_id"] is None:
            continue
        voices.append({"anime": a, "character": c, "role": v.get("role")})
    if voices:
        db.run(
            """
            MATCH (p:Person {mal_id: $id})
            UNWIND $rows AS row
            MERGE (a:Anime {mal_id: row.anime.mal_id})
              ON CREATE SET a.title = row.anime.name, a.image_url = row.anime.image_url, a.url = row.anime.url
            MERGE (c:Character {mal_id: row.character.mal_id})
              ON CREATE SET c.name = row.character.name, c.image_url = row.character.image_url, c.url = row.character.url
            MERGE (a)-[h:HAS_CHARACTER]->(c) ON CREATE SET h.role = row.role
            MERGE (p)-[v:VOICES]->(c)
              ON CREATE SET v.anime_ids = [row.anime.mal_id]
              ON MATCH SET v.anime_ids = CASE WHEN row.anime.mal_id IN coalesce(v.anime_ids, []) THEN v.anime_ids
                                              ELSE coalesce(v.anime_ids, []) + [row.anime.mal_id] END
            """,
            id=mal_id, rows=voices,
        )
    # staff positions: group by anime
    positions: dict[int, dict[str, Any]] = {}
    for w in d.get("anime") or []:
        a = _ref(w.get("anime"), "title")
        if a["mal_id"] is None:
            continue
        entry = positions.setdefault(a["mal_id"], {"anime": a, "positions": []})
        for pos in split_positions(w.get("position") or ""):
            if pos not in entry["positions"]:
                entry["positions"].append(pos)
    if positions:
        db.run(
            """
            MATCH (p:Person {mal_id: $id})
            UNWIND $rows AS row
            MERGE (a:Anime {mal_id: row.anime.mal_id})
              ON CREATE SET a.title = row.anime.name, a.image_url = row.anime.image_url, a.url = row.anime.url
            MERGE (p)-[w:WORKED_ON]->(a)
              ON CREATE SET w.positions = row.positions
              ON MATCH SET w.positions = w.positions + [x IN row.positions WHERE NOT x IN w.positions]
            """,
            id=mal_id, rows=list(positions.values()),
        )
    return {"voices": len(voices), "staff_anime": len(positions)}


# --------------------------------------------------------------------------- character

def expand_character(j: JikanClient, mal_id: int) -> dict[str, int]:
    """/characters/{id}/full: anime appearances (with role) and voice actors (with language)."""
    d = j.character_full(mal_id)
    db.run(
        "MERGE (c:Character {mal_id: $id}) SET c += $props",
        id=mal_id,
        props={
            "name": d.get("name"),
            "name_kanji": d.get("name_kanji"),
            "nicknames": d.get("nicknames") or [],
            "favorites": d.get("favorites"),
            "about": d.get("about"),
            "image_url": _img(d.get("images")),
            "url": d.get("url"),
            "fetched_at": _now(),
        },
    )
    appearances = []
    for e in d.get("anime") or []:
        a = _ref(e.get("anime"), "title")
        if a["mal_id"] is not None:
            appearances.append({"anime": a, "role": e.get("role")})
    if appearances:
        db.run(
            """
            MATCH (c:Character {mal_id: $id})
            UNWIND $rows AS row
            MERGE (a:Anime {mal_id: row.anime.mal_id})
              ON CREATE SET a.title = row.anime.name, a.image_url = row.anime.image_url, a.url = row.anime.url
            MERGE (a)-[h:HAS_CHARACTER]->(c) ON CREATE SET h.role = row.role
            """,
            id=mal_id, rows=appearances,
        )
    voices = []
    for v in d.get("voices") or []:
        p = _ref(v.get("person"))
        if p["mal_id"] is not None:
            voices.append({**p, "language": v.get("language")})
    if voices:
        db.run(
            """
            MATCH (c:Character {mal_id: $id})
            UNWIND $rows AS row
            MERGE (p:Person {mal_id: row.mal_id})
              SET p.name = row.name, p.image_url = coalesce(row.image_url, p.image_url), p.url = row.url
            MERGE (p)-[v:VOICES]->(c)
              ON CREATE SET v.language = row.language, v.anime_ids = []
              ON MATCH SET v.language = coalesce(row.language, v.language)
            """,
            id=mal_id, rows=voices,
        )
    return {"anime": len(appearances), "voices": len(voices)}


# --------------------------------------------------------------------------- user list

def upsert_user_list(username: str, entries: Iterable[dict[str, Any]]) -> int:
    rows = []
    for e in entries:
        node, ls = e.get("node") or {}, e.get("list_status") or {}
        if not node.get("id"):
            continue
        season = node.get("start_season") or {}
        rows.append({
            "mal_id": node["id"],
            "props": {
                "title": node.get("title"),
                "title_english": (node.get("alternative_titles") or {}).get("en") or None,
                "type": MEDIA_TYPE_MAP.get(node.get("media_type"), node.get("media_type")),
                "episodes": node.get("num_episodes") or None,
                "year": season.get("year"),
                "season": season.get("season"),
                "score": node.get("mean"),
                "image_url": (node.get("main_picture") or {}).get("medium"),
                "url": f"https://myanimelist.net/anime/{node['id']}",
            },
            "list": {
                "status": ls.get("status"),
                "score": ls.get("score"),
                "episodes_watched": ls.get("num_episodes_watched"),
                "is_rewatching": ls.get("is_rewatching"),
                "updated_at": ls.get("updated_at"),
            },
        })
    db.run("MERGE (u:User {username: $u})", u=username)
    # Remove entries no longer on the list, then upsert current ones.
    db.run(
        """
        MATCH (u:User {username: $u})-[l:LISTED]->(a:Anime)
        WHERE NOT a.mal_id IN $ids
        DELETE l SET a.list_status = null, a.watched = null
        """,
        u=username, ids=[r["mal_id"] for r in rows],
    )
    for i in range(0, len(rows), 500):
        db.run(
            """
            MATCH (u:User {username: $u})
            UNWIND $rows AS row
            MERGE (a:Anime {mal_id: row.mal_id})
              ON CREATE SET a += row.props
              ON MATCH SET a.title = coalesce(a.title, row.props.title),
                           a.image_url = coalesce(a.image_url, row.props.image_url),
                           a.type = coalesce(a.type, row.props.type)
            MERGE (u)-[l:LISTED]->(a) SET l += row.list
            SET a.list_status = row.list.status, a.my_score = row.list.score,
                a.watched = row.list.status <> 'plan_to_watch'
            """,
            u=username, rows=rows[i:i + 500],
        )
    mark_seen_franchise()
    return len(rows)


def mark_seen_franchise() -> int:
    """Flag every anime in the same franchise (sequel/prequel/side-story chains) as anything on the list.
    Recommendations exclude these; direct ones are shown as gaps. Cheap (Memgraph BFS), so run after any ingest."""
    db.run("MATCH (a:Anime) WHERE a.seen_franchise REMOVE a.seen_franchise")
    rows = db.run("""
        MATCH (u:User)-[:LISTED]->(x:Anime)
        MATCH (x)-[:RELATED_TO *BFS 0..6 (r, n | r.relation <> 'Character')]-(f:Anime)
        WITH DISTINCT f SET f.seen_franchise = true
        RETURN count(f) AS n
    """)
    return rows[0]["n"] if rows else 0


def listed_stub_ids(username: str | None = None, limit: int | None = None) -> list[int]:
    """Anime on the user's list that haven't been expanded via Jikan yet."""
    q = """
        MATCH (u:User)-[:LISTED]->(a:Anime)
        WHERE ($u IS NULL OR u.username = $u) AND a.fetched_at IS NULL
        RETURN a.mal_id AS id ORDER BY id
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    return [r["id"] for r in db.run(q, u=username)]


def stats() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label in db.NODE_LABELS + ["User"]:
        out[label] = db.run(f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]
    for rel in ["LISTED", "HAS_CHARACTER", "VOICES", "WORKED_ON", "RELATED_TO", "PRODUCED_BY", "HAS_GENRE"]:
        out[rel] = db.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")[0]["c"]
    out["listed_unfetched"] = len(listed_stub_ids())
    return out


# --------------------------------------------------------------------------- enrichment (beyond the list)

def top_people_ids(kind: str, top: int, lang: str = "Japanese") -> list[int]:
    """Unexpanded people ranked by presence in watched anime. kind='va' or a staff position."""
    if kind == "va":
        q = """
            MATCH (u:User)-[l:LISTED]->(a:Anime)-[:HAS_CHARACTER]->(c:Character)<-[v:VOICES]-(p:Person)
            WHERE l.status <> 'plan_to_watch' AND v.language = $lang
            WITH p, count(DISTINCT a) AS n WHERE p.fetched_at IS NULL
            RETURN p.mal_id AS id ORDER BY n DESC LIMIT $top
        """
    else:
        q = """
            MATCH (u:User)-[l:LISTED]->(a:Anime)<-[w:WORKED_ON]-(p:Person)
            WHERE l.status <> 'plan_to_watch' AND $kind IN w.positions
            WITH p, count(DISTINCT a) AS n WHERE p.fetched_at IS NULL
            RETURN p.mal_id AS id ORDER BY n DESC LIMIT $top
        """
    return [r["id"] for r in db.run(q, lang=lang, kind=kind, top=top)]


def linked_stub_ids(min_links: int, limit: int) -> list[int]:
    """Stub anime (never fetched) connected to at least `min_links` people, most-connected first."""
    return [r["id"] for r in db.run("""
        MATCH (b:Anime) WHERE b.fetched_at IS NULL
        OPTIONAL MATCH (b)-[:HAS_CHARACTER]->(:Character)<-[:VOICES]-(p1:Person)
        OPTIONAL MATCH (b)<-[:WORKED_ON]-(p2:Person)
        WITH b, count(DISTINCT p1) + count(DISTINCT p2) AS links
        WHERE links >= $min_links
        RETURN b.mal_id AS id ORDER BY links DESC LIMIT $limit
    """, min_links=min_links, limit=limit)]


def normalize_positions() -> int:
    """One-off repair: split/strip every WORKED_ON.positions entry (see split_positions)."""
    rows = db.run("MATCH ()-[w:WORKED_ON]->() UNWIND w.positions AS pos WITH DISTINCT pos RETURN pos")
    fixes = {r["pos"]: split_positions(r["pos"]) for r in rows}
    changed = [{"old": k, "new": v} for k, v in fixes.items() if v != [k]]
    for i in range(0, len(changed), 200):
        db.run("""
            UNWIND $rows AS row
            MATCH ()-[w:WORKED_ON]->() WHERE row.old IN w.positions
            WITH w, row, [x IN w.positions WHERE x <> row.old] AS rest
            SET w.positions = rest + [x IN row.new WHERE NOT x IN rest]
        """, rows=changed[i:i + 200])
    return len(changed)
