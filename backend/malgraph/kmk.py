"""Kiss Marry Kill: themes drawn from the player's own graph, each with a pool of characters to pick three from.

A theme is something that ties characters together in anime the player has seen (anything on their list except
plan to watch): a voice actor, a studio, a season, a director, a character designer, an original creator, a genre,
or the anime they rated highest. Apart from the voice actor theme, only main characters count, so the pool holds
characters people remember. A theme needs at least MIN_POOL characters to be offered.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from . import db, games, users

MIN_POOL = 4
POOL_SIZE = 40

SEEN = "MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) WHERE l.status <> 'plan_to_watch'"
GENDER = "($gender IS NULL OR c.gender = $gender)"
MAIN = f"MATCH (a)-[:HAS_CHARACTER {{role: 'Main'}}]->(c:Character) WHERE {GENDER}"


@dataclass(frozen=True)
class Kind:
    name: str
    themes: str  # returns key, label, n (pool size) for every theme of this kind
    pool: str  # returns c, anime (titles), main, for one theme ($key)
    title: str  # format string with {label}
    top: int = 0  # draw only from the `top` largest themes (0 = all), so themes are names people recognise


def _staff(position: str, title: str, name: str, top: int = 30) -> Kind:
    return Kind(
        name,
        f"{SEEN} MATCH (p:Person)-[w:WORKED_ON]->(a) WHERE '{position}' IN w.positions {MAIN} "
        "WITH p, count(DISTINCT c) AS n WHERE n >= $min RETURN p.mal_id AS key, p.name AS label, n",
        f"{SEEN} MATCH (p:Person {{mal_id: $key}})-[w:WORKED_ON]->(a) WHERE '{position}' IN w.positions {MAIN} "
        "RETURN c, collect(DISTINCT a.title) AS anime, true AS main",
        title,
        top,
    )


KINDS = [
    Kind(
        "va",
        f"{SEEN} MATCH (a)-[:HAS_CHARACTER]->(c:Character)<-[:VOICES {{language: 'Japanese'}}]-(p:Person) WHERE {GENDER} "
        "WITH p, count(DISTINCT c) AS n WHERE n >= $min RETURN p.mal_id AS key, p.name AS label, n",
        f"{SEEN} MATCH (a)-[h:HAS_CHARACTER]->(c:Character)<-[:VOICES {{language: 'Japanese'}}]-(p:Person {{mal_id: $key}}) WHERE {GENDER} "
        "RETURN c, collect(DISTINCT a.title) AS anime, 'Main' IN collect(h.role) AS main",
        "Voiced by {label}",
        60,
    ),
    Kind(
        "studio",
        f"{SEEN} MATCH (a)-[:PRODUCED_BY]->(s:Studio) {MAIN} "
        "WITH s, count(DISTINCT c) AS n WHERE n >= $min RETURN s.mal_id AS key, s.name AS label, n",
        f"{SEEN} MATCH (a)-[:PRODUCED_BY]->(s:Studio {{mal_id: $key}}) {MAIN} "
        "RETURN c, collect(DISTINCT a.title) AS anime, true AS main",
        "Main characters from {label} anime",
        25,
    ),
    Kind(
        "season",
        f"{SEEN} AND a.season IS NOT NULL AND a.year IS NOT NULL {MAIN} "
        "WITH a.year * 10 + CASE a.season WHEN 'winter' THEN 1 WHEN 'spring' THEN 2 WHEN 'summer' THEN 3 ELSE 4 END AS key, "
        "a.season AS season, a.year AS year, count(DISTINCT c) AS n WHERE n >= $min "
        "RETURN key, toUpper(substring(season, 0, 1)) + substring(season, 1) + ' ' + toString(year) AS label, n",
        f"{SEEN} AND a.year * 10 + CASE a.season WHEN 'winter' THEN 1 WHEN 'spring' THEN 2 WHEN 'summer' THEN 3 ELSE 4 END = $key {MAIN} "
        "RETURN c, collect(DISTINCT a.title) AS anime, true AS main",
        "Main characters from {label}",
    ),
    _staff("Director", "Main characters from anime directed by {label}", "director"),
    _staff("Character Design", "Characters designed by {label}", "designer"),
    _staff("Original Creator", "Characters created by {label}", "creator"),
    Kind(
        "genre",
        f"{SEEN} MATCH (a)-[:HAS_GENRE]->(g:Genre) WHERE g.kind IN ['genre', 'theme'] AND NOT g.name IN ['Hentai', 'Erotica', 'Ecchi'] {MAIN} "
        "WITH g, count(DISTINCT c) AS n WHERE n >= $min RETURN g.mal_id AS key, g.name AS label, n",
        f"{SEEN} MATCH (a)-[:HAS_GENRE]->(g:Genre {{mal_id: $key}}) {MAIN} "
        "RETURN c, collect(DISTINCT a.title) AS anime, true AS main",
        "Main characters from {label} anime",
    ),
    Kind(
        "favourites",
        f"{SEEN} AND l.score >= 9 {MAIN} WITH count(DISTINCT c) AS n WHERE n >= $min RETURN 0 AS key, 'your top-rated anime' AS label, n",
        f"{SEEN} AND l.score >= 9 {MAIN} RETURN c, collect(DISTINCT a.title) AS anime, true AS main",
        "Main characters from anime you rated 9 or 10",
    ),
]
BY_NAME = {k.name: k for k in KINDS}


def _pool(kind: Kind, key: Any, rng: random.Random, gender: str | None) -> list[dict[str, Any]]:
    from .api.serialize import node_payload  # the API's node shape, so the UI can reuse its cards

    with db.get_driver().session() as session:  # graph nodes, not plain dicts, for node_payload
        rows = list(session.run(kind.pool, **{**users.params_for(kind.pool), "key": key, "gender": gender}))
    rng.shuffle(rows)
    return [{"character": node_payload(r["c"]), "anime": r["anime"][:3], "main": bool(r["main"])} for r in rows[:POOL_SIZE]]


def theme(avoid: str | None = None, kind_name: str | None = None, key: Any = None, gender: str | None = None) -> dict[str, Any] | None:
    """A random theme from the player's graph (or the one named), with its character pool. None if there is none."""
    rng = random.Random()
    if kind_name in BY_NAME and key is not None:
        kind = BY_NAME[kind_name]
        label = next((t["label"] for t in users.run(kind.themes, min=1, gender=None) if str(t["key"]) == str(key)), str(key))
        return {"kind": kind.name, "key": key, "title": kind.title.format(label=label), "pool": _pool(kind, key, rng, gender)}
    kinds = KINDS[:]
    rng.shuffle(kinds)
    for kind in kinds:  # a random kind, then a random theme of that kind; skip kinds the player has none of
        ranked = sorted(users.run(kind.themes, min=MIN_POOL, gender=gender), key=lambda t: -t["n"])
        options = [t for t in ranked[: kind.top or None] if f"{kind.name}:{t['key']}" != avoid]
        if not options:
            continue
        t = rng.choice(options)
        return {"kind": kind.name, "key": t["key"], "title": kind.title.format(label=t["label"]), "pool": _pool(kind, t["key"], rng, gender)}
    return None


# --------------------------------------------------------------------------- Daily Kiss Marry Kill
# The same three characters for everyone each day, drawn from the shared graph rather than anyone's list: three
# well-known main roles of a popular voice actor, or three main characters from a big studio. Everyone's choices
# are tallied without names.

CHOICES = ("kiss", "marry", "kill")
_ROLES = (
    "MATCH (a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) WHERE a.fetched_at IS NOT NULL AND c.favorites IS NOT NULL "
)
DAILY_KINDS = {
    "va": (
        f"{_ROLES} MATCH (p:Person)-[:VOICES {{language: 'Japanese'}}]->(c) WITH p, count(DISTINCT c) AS n WHERE n >= 4 "
        "RETURN p.mal_id AS key, p.name AS label ORDER BY coalesce(p.favorites, 0) DESC LIMIT 40",
        f"{_ROLES} MATCH (p:Person {{mal_id: $key}})-[:VOICES {{language: 'Japanese'}}]->(c) "
        "WITH c, collect(a.mal_id) AS anime ORDER BY c.favorites DESC LIMIT 12 RETURN c.mal_id AS id, anime",
        "Voiced by {label}",
    ),
    "studio": (
        f"{_ROLES} MATCH (a)-[:PRODUCED_BY]->(s:Studio) WITH s, count(DISTINCT c) AS n WHERE n >= 6 "
        "RETURN s.mal_id AS key, s.name AS label ORDER BY n DESC LIMIT 25",
        f"{_ROLES} MATCH (a)-[:PRODUCED_BY]->(s:Studio {{mal_id: $key}}) "
        "WITH c, collect(a.mal_id) AS anime ORDER BY c.favorites DESC LIMIT 15 RETURN c.mal_id AS id, anime",
        "Main characters from {label} anime",
    ),
}


def make_daily(rng: random.Random) -> dict[str, Any]:
    """Three characters from three different franchises, sharing a voice actor or a studio."""
    franchise = games.franchises()
    kinds = list(DAILY_KINDS)
    rng.shuffle(kinds)
    for kind in kinds * 10:
        themes_q, pool_q, title = DAILY_KINDS[kind]
        themes = db.run(themes_q)
        if not themes:
            continue
        t = rng.choice(themes)
        roles = db.run(pool_q, key=t["key"])
        rng.shuffle(roles)
        picked: list[int] = []
        seen: set[int] = set()
        for r in roles:
            own = {franchise.get(a, a) for a in r["anime"]}
            if not own & seen:
                picked.append(r["id"])
                seen |= own
            if len(picked) == 3:
                label = games.natural(t["label"]) if kind == "va" else t["label"]
                return {"title": title.format(label=label), "cards": picked}
    raise ValueError("the graph is too small for a daily round yet")


def daily(day: str | None = None) -> dict[str, Any]:
    return games.daily("kmk", make_daily, day)


def tally(puzzle: dict[str, Any]) -> dict[str, Any]:
    """How everyone chose today: per character, the number of kisses, marriages and kills."""
    counts = {str(c): {ch: 0 for ch in CHOICES} for c in puzzle["cards"]}
    plays = games.plays("kmk", puzzle["date"]).values()
    for p in plays:
        for cid, ch in p["choices"].items():
            if cid in counts and ch in CHOICES:
                counts[cid][ch] += 1
    return {"players": len(plays), "counts": counts}


def play_daily(username: str, choices: dict[str, str]) -> dict[str, Any]:
    """Record a player's choices. Each card gets a different choice. Only the first play of the day counts."""
    puzzle = daily()
    if sorted(choices) != sorted(str(c) for c in puzzle["cards"]) or sorted(choices.values()) != sorted(CHOICES):
        raise ValueError("give each of today's three characters a different choice")
    return games.update_play("kmk", puzzle["date"], username, lambda old: old or {"choices": choices, "at": time.time()})
