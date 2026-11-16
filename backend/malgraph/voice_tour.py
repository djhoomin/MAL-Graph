"""The voice tour: the graph tour's ideas on a graph joined only by the Japanese voice actors of main characters.

Leading voice actors work on many shows a year, so this graph clusters poorly and recommends weakly. The tour keeps
the four steps that hold up: bridges (betweenness), twins (Jaccard similarity of main casts), duos (a projection onto
voice actors) and distance (islands, the diameter and the centre), which reuses the makers' tour code.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from typing import Any

from . import db, games, tour

TTL = 600
MAX_BRIDGES = 8
MAX_TWINS = 10
MIN_SHARED = 2  # main casts are small, so two shared leads is already a lot
MAX_DUOS = 8
COVERS = 6  # lead roles shown for each bridge

VOICE = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH path = (a)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character)<-[v:VOICES]-(p:Person)
WHERE v.language = 'Japanese' AND a.id IN v.anime_ids"""

ROLES = VOICE + """
RETURN p.id AS person, p.name AS name, a.id AS anime, c.name AS character"""

BRIDGES = VOICE + """
WITH project(path) AS graph
CALL betweenness_centrality.get(graph, False, True) YIELD node, betweenness_centrality
WHERE node:Person
RETURN node.id AS id, betweenness_centrality
ORDER BY betweenness_centrality DESC LIMIT 30"""

TWINS = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH (a)-[:HAS_CHARACTER {role: 'Main'}]->(:Character)<-[v:VOICES]-(p:Person)
WHERE v.language = 'Japanese' AND a.id IN v.anime_ids
WITH a, collect(DISTINCT p) AS cast
WITH collect({anime: a, cast: cast}) AS shows
UNWIND shows AS x
UNWIND shows AS y
WITH x, y WHERE x.anime.id < y.anime.id
WITH x, y, [p IN x.cast WHERE p IN y.cast] AS shared
WHERE size(shared) >= $min_shared
RETURN x.anime.id AS a, y.anime.id AS b, [p IN shared | p.id] AS shared,
       size(x.cast) + size(y.cast) - size(shared) AS either,
       toFloat(size(shared)) / (size(x.cast) + size(y.cast) - size(shared)) AS jaccard
ORDER BY jaccard DESC"""

# Anime on the list that MyAnimeList relates in any way, such as a crossover, which shares its cast for that reason.
RELATED = """MATCH (:User {username: $user})-[:LISTED]->(a:Anime)-[:RELATED_TO]-(b:Anime)<-[:LISTED]-(:User {username: $user})
RETURN DISTINCT a.id AS a, b.id AS b"""

DUOS = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH (p:Person)-[v1:VOICES]->(:Character)<-[:HAS_CHARACTER {role: 'Main'}]-(a)
      -[:HAS_CHARACTER {role: 'Main'}]->(:Character)<-[v2:VOICES]-(q:Person)
WHERE p.id < q.id AND v1.language = 'Japanese' AND v2.language = 'Japanese'
  AND a.id IN v1.anime_ids AND a.id IN v2.anime_ids
WITH p, q, collect(DISTINCT a.id) AS together
WHERE size(together) >= 2
RETURN p.id AS p, q.id AS q, together"""

ISLANDS = VOICE + """
WITH project(path) AS graph
CALL weakly_connected_components.get(graph) YIELD node, component_id
WHERE node:Anime
RETURN node.id AS id, component_id"""

# What "Show on the graph" draws: the anime, the voice actors and the main characters between them.
SHOW = """MATCH (a:Anime)-[h:HAS_CHARACTER {role: 'Main'}]->(c:Character)<-[v:VOICES]-(p:Person)
WHERE a.id IN $anime AND p.id IN $people AND v.language = 'Japanese' AND a.id IN v.anime_ids
RETURN a, h, c, v, p"""

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def voices(username: str) -> dict[str, Any]:
    """The voice tour for one user, cached for TTL seconds. Fields starting with _ stay on the server."""
    with _lock:
        hit = _cache.get(username)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    result = _build(username)
    with _lock:
        _cache[username] = (time.time(), result)
    return result


def forget(username: str) -> None:
    with _lock:
        _cache.pop(username, None)


def show_item(username: str, step: str, index: int) -> dict[str, list[int]] | None:
    show = voices(username).get(f"_{step}")
    return show[index] if show is not None and 0 <= index < len(show) else None


def _build(username: str) -> dict[str, Any]:
    franchise = games.recent_franchises()
    anime = {r["id"]: r for r in db.run(tour.ANIME, user=username)}
    series_of = {a: franchise.get(a, a) for a in anime}
    made: dict[str, set[int]] = defaultdict(set)  # voice actor -> anime they lead on the list
    makers: dict[str, dict[str, Any]] = {}
    roles: dict[tuple[str, int], list[str]] = defaultdict(list)  # (voice actor, anime) -> their main characters
    for r in db.run(ROLES, user=username):
        if r["anime"] not in anime:
            continue
        ref = f"Person:{r['person']}"
        makers.setdefault(ref, {"id": ref, "label": "Person", "key": r["person"], "name": games.natural(r["name"])})
        made[ref].add(r["anime"])
        name = games.natural(r["character"])
        if name not in roles[(ref, r["anime"])]:
            roles[(ref, r["anime"])].append(name)

    def series(ids: set[int]) -> set[int]:
        return {series_of[a] for a in ids}

    def role(ref: str, a: int) -> str:
        return " and ".join(roles[(ref, a)][:2])

    def best(ids: set[int]) -> int:
        return max(ids, key=lambda a: (anime[a]["score"], anime[a]["members"], -a))

    # Bridges: the voice actors on the most shortest paths between your series.
    by_count = sorted(made, key=lambda ref: (-len(series(made[ref])), makers[ref]["name"]))
    count_rank = {ref: i + 1 for i, ref in enumerate(by_count)}
    bridges, bridge_show = [], []
    for r in db.run(BRIDGES, user=username):
        ref = f"Person:{r['id']}"
        if ref not in made or len(series(made[ref])) < 2:
            continue
        one: dict[int, int] = {}
        for a in sorted(made[ref], key=lambda a: (-anime[a]["score"], -anime[a]["members"], a)):
            one.setdefault(series_of[a], a)
        bridges.append({
            **{k: makers[ref][k] for k in ("id", "label", "name")},
            "series": len(one),
            "count_rank": count_rank[ref],
            "shows": [{**tour._card(anime[a]), "note": role(ref, a)} for a in list(one.values())[:COVERS]],
        })
        bridge_show.append(tour._ids(list(one.values()), [makers[ref]]))
        if len(bridges) >= MAX_BRIDGES:
            break

    # Twins: anime from different, unrelated series with the most similar main casts.
    related = {(r["a"], r["b"]) for r in db.run(RELATED, user=username)}
    linked = {(series_of[a], series_of[b]) for a, b in related if a in anime and b in anime}
    twins, twin_show, taken = [], [], set()
    rows = [r for r in db.run(TWINS, user=username, min_shared=MIN_SHARED) if r["a"] in anime and r["b"] in anime]
    rows.sort(key=lambda r: (-len(r["shared"]), -r["jaccard"], -(anime[r["a"]]["members"] + anime[r["b"]]["members"])))
    for r in rows:
        a, b = r["a"], r["b"]
        key = frozenset((series_of[a], series_of[b]))
        if series_of[a] == series_of[b] or key in taken or (series_of[a], series_of[b]) in linked:
            continue
        taken.add(key)
        shared = sorted((f"Person:{p}" for p in r["shared"]), key=lambda ref: makers[ref]["name"])
        twins.append({
            "shows": [tour._card(anime[a]), tour._card(anime[b])],
            "shared": [{"id": ref, "name": makers[ref]["name"], "roles": [role(ref, a), role(ref, b)]} for ref in shared],
            "either": r["either"],
            "jaccard": round(r["jaccard"], 2),
        })
        twin_show.append(tour._ids([a, b], [makers[ref] for ref in shared]))
        if len(twins) >= MAX_TWINS:
            break

    # Series MyAnimeList relates, such as a show and its crossover, count as one for duos.
    group = {x: x for x in set(series_of.values())}

    def find(x: int) -> int:
        while group[x] != x:
            group[x] = group[group[x]]
            x = group[x]
        return x

    for x, y in linked:
        group[find(x)] = find(y)

    def unrelated(ids: set[int]) -> set[int]:
        return {find(series_of[a]) for a in ids}

    # Duos: two voice actors who lead together in two or more of your series. Each voice actor is in two duos at most.
    pairs = []
    for r in db.run(DUOS, user=username):
        p, q = f"Person:{r['p']}", f"Person:{r['q']}"
        together = {a for a in r["together"] if a in anime}
        if p in made and q in made and len(unrelated(together)) >= 2:
            pairs.append((p, q, together))
    pairs.sort(key=lambda t: (-len(unrelated(t[2])), -len(t[2]), makers[t[0]]["name"], makers[t[1]]["name"]))
    duos, duo_show, appears = [], [], Counter()
    for p, q, together in pairs:
        if len(duos) >= MAX_DUOS:
            break
        if appears[p] >= 2 or appears[q] >= 2:
            continue
        appears.update((p, q))
        one = {}
        for a in sorted(together, key=lambda a: (-anime[a]["score"], -anime[a]["members"], a)):
            one.setdefault(find(series_of[a]), a)
        people = sorted((p, q), key=lambda ref: makers[ref]["name"])
        duos.append({
            "people": [{"id": ref, "name": makers[ref]["name"]} for ref in people],
            "series": len(one),
            "shows": [{**tour._card(anime[a]), "note": " and ".join(role(ref, a) for ref in people)} for a in one.values()],
        })
        duo_show.append(tour._ids(sorted(together), [makers[p], makers[q]]))

    component = {r["id"]: r["component_id"] for r in db.run(ISLANDS, user=username) if r["id"] in anime}
    distance, distance_show = tour._distance(component, anime, series_of, made, makers)
    return {
        "_bridges": bridge_show,
        "_twins": twin_show,
        "_duos": duo_show,
        "_distance": distance_show,
        "anime": len(anime),
        "voiced": len(component),
        "voices": len(made),
        "bridges": bridges,
        "twins": twins,
        "duos": duos,
        "distance": distance,
        "queries": {"bridges": BRIDGES, "twins": TWINS, "duos": DUOS, "islands": ISLANDS},
    }
