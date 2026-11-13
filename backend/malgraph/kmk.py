"""Kiss Marry Kill: themes drawn from the player's own graph, each with a pool of characters to pick three from.

A theme is something that ties characters together in anime the player has seen (anything on their list except
plan to watch): a voice actor, a studio, a season, a director, a character designer, an original creator, a genre,
or the anime they rated highest. Apart from the voice actor theme, only main characters count, so the pool holds
characters people remember. A theme needs at least MIN_POOL characters to be offered.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from . import db, users

MIN_POOL = 4
POOL_SIZE = 40

SEEN = "MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) WHERE l.status <> 'plan_to_watch'"
MAIN = "MATCH (a)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character)"


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
        f"{SEEN} MATCH (a)-[:HAS_CHARACTER]->(c:Character)<-[:VOICES {{language: 'Japanese'}}]-(p:Person) "
        "WITH p, count(DISTINCT c) AS n WHERE n >= $min RETURN p.mal_id AS key, p.name AS label, n",
        f"{SEEN} MATCH (a)-[h:HAS_CHARACTER]->(c:Character)<-[:VOICES {{language: 'Japanese'}}]-(p:Person {{mal_id: $key}}) "
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


def _pool(kind: Kind, key: Any, rng: random.Random) -> list[dict[str, Any]]:
    from .api.serialize import node_payload  # the API's node shape, so the UI can reuse its cards

    with db.get_driver().session() as session:  # graph nodes, not plain dicts, for node_payload
        rows = list(session.run(kind.pool, **{**users.params_for(kind.pool), "key": key}))
    rng.shuffle(rows)
    return [{"character": node_payload(r["c"]), "anime": r["anime"][:3], "main": bool(r["main"])} for r in rows[:POOL_SIZE]]


def theme(avoid: str | None = None, kind_name: str | None = None, key: Any = None) -> dict[str, Any] | None:
    """A random theme from the player's graph (or the one named), with its character pool. None if there is none."""
    rng = random.Random()
    if kind_name in BY_NAME and key is not None:
        kind = BY_NAME[kind_name]
        label = next((t["label"] for t in users.run(kind.themes, min=1) if str(t["key"]) == str(key)), str(key))
        return {"kind": kind.name, "key": key, "title": kind.title.format(label=label), "pool": _pool(kind, key, rng)}
    kinds = KINDS[:]
    rng.shuffle(kinds)
    for kind in kinds:  # a random kind, then a random theme of that kind; skip kinds the player has none of
        ranked = sorted(users.run(kind.themes, min=MIN_POOL), key=lambda t: -t["n"])
        options = [t for t in ranked[: kind.top or None] if f"{kind.name}:{t['key']}" != avoid]
        if not options:
            continue
        t = rng.choice(options)
        return {"kind": kind.name, "key": t["key"], "title": kind.title.format(label=t["label"]), "pool": _pool(kind, t["key"], rng)}
    return None
