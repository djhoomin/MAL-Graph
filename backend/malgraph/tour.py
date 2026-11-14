"""Graph tour: questions about your own list that only the graph's structure can answer.

The graph for a tour is your watched anime plus the people and studios that made them. A person or studio is
linked to an anime when they directed it, wrote its series composition, wrote its music, designed its characters,
created the original work or animated it. Voice actors are left out, because one popular voice actor would tie
everything together.

Taste clusters come from community detection (Louvain) on that graph. Bridges are the people and studios with the
highest betweenness centrality: the most shortest routes between your anime pass through them. Both run inside
Memgraph, and the queries shown in the app are the ones that run.

Cut points come from biconnected components inside each cluster: a person, studio or anime that sits in more than
one component is the only thing holding those parts of the cluster together.

Sequels share nearly all their staff, so results are counted by franchise ("series"), not by anime.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from typing import Any

from . import db, games

TTL = 600
MIN_SERIES = 2  # a cluster needs this many series to be shown
MAX_CLUSTERS = 10
MAX_BRIDGES = 8
MAX_CUTS = 8
SIDE_ITEMS = 4  # series shown for each side of a cut

# The tour's graph. It is written out in full, since the app shows it.
GRAPH = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH path = (a)-[r]-(maker)
WHERE type(r) = 'PRODUCED_BY'
   OR (type(r) = 'WORKED_ON' AND any(job IN r.positions WHERE job IN
       ['Director', 'Series Composition', 'Music', 'Character Design', 'Original Creator']))"""

CLUSTERS = GRAPH + """
WITH project(path) AS graph
CALL community_detection.get(graph) YIELD node, community_id
RETURN labels(node)[0] AS kind, node.mal_id AS id, community_id"""

BRIDGES = GRAPH + """
WITH project(path) AS graph
CALL betweenness_centrality.get(graph, False, True) YIELD node, betweenness_centrality
WHERE NOT node:Anime
RETURN labels(node)[0] AS kind, node.mal_id AS id, betweenness_centrality
ORDER BY betweenness_centrality DESC LIMIT 20"""

LINKS = GRAPH + """
RETURN a.mal_id AS anime, labels(maker)[0] AS label, maker.mal_id AS id, maker.name AS name"""

ANIME = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime) WHERE l.status <> 'plan_to_watch'
OPTIONAL MATCH (a)-[:HAS_GENRE]->(g:Genre) WHERE g.kind IN ['genre', 'theme'] AND NOT g.name IN ['Hentai', 'Erotica', 'Ecchi']
RETURN a.mal_id AS id, a.title AS title, a.image_url AS image_url, coalesce(a.members, 0) AS members,
       coalesce(l.score, 0) AS score, collect(g.name) AS genres"""

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _ref(label: str, mal_id: Any) -> str:
    return f"{label}:{mal_id}"


def _name(label: str, name: str | None) -> str:
    return games.natural(name) if label == "Person" else (name or "")


def public(t: dict[str, Any]) -> dict[str, Any]:
    """The tour without the fields kept for drawing it."""
    return {k: v for k, v in t.items() if not k.startswith("_")}


def tour(username: str) -> dict[str, Any]:
    """Clusters and bridges for one user, cached for TTL seconds. Fields starting with _ stay on the server."""
    with _lock:
        hit = _cache.get(username)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    result = _build(username)
    with _lock:
        _cache[username] = (time.time(), result)
    return result


def _build(username: str) -> dict[str, Any]:
    franchise = games.recent_franchises()
    anime = {r["id"]: r for r in db.run(ANIME, user=username)}
    series_of = {a: franchise.get(a, a) for a in anime}
    links = db.run(LINKS, user=username)
    makers: dict[str, dict[str, Any]] = {}
    made: dict[str, set[int]] = defaultdict(set)  # maker -> anime on the list
    for r in links:
        ref = _ref(r["label"], r["id"])
        makers.setdefault(ref, {"id": ref, "label": r["label"], "mal_id": r["id"], "name": _name(r["label"], r["name"])})
        made[ref].add(r["anime"])

    community: dict[int, int] = {}
    for r in db.run(CLUSTERS, user=username):
        if r["kind"] == "Anime" and r["id"] in anime:
            community[r["id"]] = r["community_id"]

    # The whole list's genre mix, so each cluster can be described by what's unusual about it.
    all_genres = Counter(g for a in anime.values() for g in set(a["genres"]))
    total = max(len(anime), 1)

    groups: dict[int, list[int]] = defaultdict(list)
    for a, c in community.items():
        groups[c].append(a)
    clusters = []
    for c, members in groups.items():
        series: dict[int, dict[str, Any]] = {}
        for a in sorted(members, key=lambda x: (-anime[x]["score"], -anime[x]["members"])):
            series.setdefault(series_of[a], anime[a])
        if len(series) < MIN_SERIES:
            continue
        inside = set(members)
        # The people and studios behind most of the cluster's series.
        counts = []
        for ref, did in made.items():
            n = len({series_of[a] for a in did & inside})
            if n >= 2:
                counts.append((n, ref))
        counts.sort(key=lambda x: (-x[0], makers[x[1]]["name"]))
        genres = Counter(g for a in members for g in set(anime[a]["genres"]))
        lift = sorted(
            ((genres[g] / len(members)) / (all_genres[g] / total), g) for g in genres if genres[g] >= max(2, len(members) / 4) and all_genres[g] < total
        )
        clusters.append({
            "community": c,
            # For drawing: every anime in the cluster and everyone linking two or more of them, which keeps it in one piece.
            "_show": _ids(members, [makers[ref] for ref, did in made.items() if len(did & inside) >= 2]),
            "anime": len(members),
            "series": [{"mal_id": s["id"], "title": s["title"], "image_url": s["image_url"], "my_score": s["score"]} for s in series.values()],
            "makers": [{**makers[ref], "series": n} for n, ref in counts[:5]],
            "genres": [g for _, g in reversed(lift[-3:])],
        })
    clusters.sort(key=lambda c: (-len(c["series"]), -c["anime"]))
    clusters = clusters[:MAX_CLUSTERS]
    shown = {c["community"]: i for i, c in enumerate(clusters)}
    in_clusters = sum(c["anime"] for c in clusters)

    # How many of your series each maker is behind, to compare a bridge's importance with a simple count.
    by_count = sorted(made, key=lambda ref: -len({series_of[a] for a in made[ref]}))
    count_rank = {ref: i + 1 for i, ref in enumerate(by_count)}

    bridges = []
    for r in db.run(BRIDGES, user=username):
        ref = _ref(r["kind"], r["id"])
        if ref not in makers:
            continue
        reach: dict[int, int] = {}  # shown cluster -> one of the maker's anime in it
        for a in sorted(made[ref], key=lambda x: -anime[x]["score"]):
            c = shown.get(community.get(a, -1))
            if c is not None:
                reach.setdefault(c, a)
        if len(reach) < 2:
            continue
        bridges.append({
            **makers[ref],
            "rank": len(bridges) + 1,
            "series": len({series_of[a] for a in made[ref]}),
            "count_rank": count_rank[ref],
            "clusters": [{"cluster": c, "mal_id": a, "title": anime[a]["title"], "image_url": anime[a]["image_url"]} for c, a in sorted(reach.items())],
        })
        if len(bridges) >= MAX_BRIDGES:
            break

    show = []
    for c in clusters:
        del c["community"]
        show.append(c.pop("_show"))
    cuts = _cuts(show, anime, series_of, makers)
    return {
        "_show": show,
        "cuts": cuts,
        "anime": len(anime),
        "clustered": in_clusters,
        "clusters": clusters,
        "bridges": bridges,
        "makers": len(makers),
        "queries": {"clusters": CLUSTERS, "bridges": BRIDGES, "cuts": CUTS},
    }


def _cuts(show: list[dict[str, list[int]]], anime: dict[int, Any], series_of: dict[int, int], makers: dict[str, Any]) -> list[dict[str, Any]]:
    """The people, studios and anime each cluster falls apart without, with the sides they hold together.

    A cut point only counts when at least two of its sides have two or more series, so a show hanging off one
    person isn't reported. An anime is only reported when no person or studio next to it is a cut point too,
    since that maker usually tells the same story better."""
    found = []
    for index, ids in enumerate(show):
        in_bcc: dict[str, set[int]] = defaultdict(set)
        adj: dict[str, set[str]] = defaultdict(set)
        for r in db.run(CUTS, **ids):
            a, b = _ref(r["from_kind"], r["from_id"]), _ref(r["to_kind"], r["to_id"])
            in_bcc[a].add(r["bcc_id"])
            in_bcc[b].add(r["bcc_id"])
            adj[a].add(b)
            adj[b].add(a)
        points = {n for n, bccs in in_bcc.items() if len(bccs) > 1}
        for cut in points:
            kind = cut.split(":", 1)[0]
            if kind == "Anime" and adj[cut] & points:
                continue
            sides = []
            seen = {cut}
            for start in sorted(adj[cut]):
                if start in seen:
                    continue
                seen.add(start)
                stack, members = [start], []
                while stack:
                    x = stack.pop()
                    if x.startswith("Anime:"):
                        members.append(int(x.split(":", 1)[1]))
                    for y in adj[x]:
                        if y not in seen:
                            seen.add(y)
                            stack.append(y)
                series: dict[int, dict[str, Any]] = {}
                for a in sorted(members, key=lambda x: (-anime[x]["score"], -anime[x]["members"])):
                    series.setdefault(series_of[a], anime[a])
                if series:
                    sides.append({
                        "series": len(series),
                        "anime": len(members),
                        "items": [{"mal_id": a["id"], "title": a["title"], "image_url": a["image_url"]} for a in list(series.values())[:SIDE_ITEMS]],
                    })
            sides.sort(key=lambda x: (-x["series"], -x["anime"]))
            if len(sides) < 2 or sides[1]["series"] < 2:
                continue
            if kind == "Anime":
                a = anime[int(cut.split(":", 1)[1])]
                who = {"id": cut, "label": "Anime", "mal_id": a["id"], "name": a["title"], "image_url": a["image_url"]}
            else:
                who = {**makers[cut], "image_url": None}
            found.append({**who, "cluster": index, "sides": sides})
    # The most even splits first: a cut point matters most when both sides are big.
    found.sort(key=lambda c: (-c["sides"][1]["series"], -sum(x["series"] for x in c["sides"])))
    return found[:MAX_CUTS]


SHOW = """MATCH (a:Anime)-[r]-(maker)
WHERE a.mal_id IN $anime AND ((maker:Person AND maker.mal_id IN $people) OR (maker:Studio AND maker.mal_id IN $studios))
  AND (type(r) = 'PRODUCED_BY' OR (type(r) = 'WORKED_ON' AND any(job IN r.positions WHERE job IN
       ['Director', 'Series Composition', 'Music', 'Character Design', 'Original Creator'])))
RETURN a, r, maker"""

# Biconnected components of one cluster as drawn on the graph. Shown in the app with the cluster's ids as parameters.
CUTS = """MATCH path = (a:Anime)-[r]-(maker)
WHERE a.mal_id IN $anime AND ((maker:Person AND maker.mal_id IN $people) OR (maker:Studio AND maker.mal_id IN $studios))
  AND (type(r) = 'PRODUCED_BY' OR (type(r) = 'WORKED_ON' AND any(job IN r.positions WHERE job IN
       ['Director', 'Series Composition', 'Music', 'Character Design', 'Original Creator'])))
WITH project(path) AS graph
CALL biconnected_components.get(graph) YIELD bcc_id, node_from, node_to
RETURN bcc_id, labels(node_from)[0] AS from_kind, node_from.mal_id AS from_id,
       labels(node_to)[0] AS to_kind, node_to.mal_id AS to_id"""


def show_cluster(username: str, index: int) -> dict[str, list[int]] | None:
    """The anime and makers to draw for one cluster: all its anime and the makers behind two or more of them."""
    show = tour(username)["_show"]
    return show[index] if 0 <= index < len(show) else None


def show_bridge(username: str, ref: str) -> dict[str, list[int]] | None:
    """A bridge with one anime from each cluster it joins, and the makers behind each cluster."""
    t = tour(username)
    b = next((b for b in t["bridges"] if b["id"] == ref), None)
    if not b:
        return None
    anime = [x["mal_id"] for x in b["clusters"]]
    return _ids(anime, [b])


def _ids(anime: list[int], makers: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        "anime": anime,
        "people": [m["mal_id"] for m in makers if m["label"] == "Person"],
        "studios": [m["mal_id"] for m in makers if m["label"] == "Studio"],
    }


def forget(username: str) -> None:
    with _lock:
        _cache.pop(username, None)
