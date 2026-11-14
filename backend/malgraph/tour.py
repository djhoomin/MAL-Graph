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

Twins come from Jaccard similarity between two anime: the makers they share divided by all the makers either has.

Recommendations follow two-step paths from the anime you scored 8 or more, through a person or studio, to anime you
haven't listed. Each path counts for more when you scored the start higher and less when the maker is prolific (the
Adamic-Adar idea), so a director with ten shows says more about your taste than a studio with a hundred.

Creative teams project the anime-to-people graph onto people: two people are linked when they worked on the same
anime, and the pairs that keep working together across your series become teams.

Sequels share nearly all their staff, so results are counted by franchise ("series"), not by anime.
"""
from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict
from typing import Any

from . import db, games

TTL = 600
PENDING_TTL = 60  # how long a tour is kept while anime it needs are still being fetched
MIN_SERIES = 2  # a cluster needs this many series to be shown
MAX_CLUSTERS = 10
MAX_BRIDGES = 8
MAX_CUTS = 8
MIN_SIDE = 2  # series the second-largest side of a cut needs
SIDE_ITEMS = 4  # series shown for each side of a cut
MAX_TWINS = 10
MIN_SHARED = 3  # makers two anime need in common to count as twins, since many anime only list a few
MAX_RECS = 10
REC_MIN_MEMBERS = 20_000  # leaves out specials and shorts nobody has heard of
REC_PATHS = 3  # paths shown for each recommendation
MAX_TEAMS = 8
TEAM_RECS = 4  # other anime shown for each team
TEAM_FETCH = 40  # stubs a tour may queue for fetching at once
TIMELINE_MAKERS = 12  # people and studios offered as highlights on a cluster's timeline
SEASONS = ["winter", "spring", "summer", "fall"]

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
       coalesce(l.score, 0) AS score, collect(g.name) AS genres, a.year AS year, a.season AS season, a.aired_from AS aired_from"""

TWINS = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH (a)-[r]-(maker)
WHERE type(r) = 'PRODUCED_BY'
   OR (type(r) = 'WORKED_ON' AND any(job IN r.positions WHERE job IN
       ['Director', 'Series Composition', 'Music', 'Character Design', 'Original Creator']))
WITH a, collect(DISTINCT maker) AS makers
WITH collect({anime: a, makers: makers}) AS shows
UNWIND shows AS x
UNWIND shows AS y
WITH x, y WHERE x.anime.mal_id < y.anime.mal_id
WITH x, y, [m IN x.makers WHERE m IN y.makers] AS shared
WHERE size(shared) >= $min_shared
RETURN x.anime.mal_id AS a, y.anime.mal_id AS b,
       [m IN shared | labels(m)[0] + ':' + toString(m.mal_id)] AS shared,
       size(x.makers) + size(y.makers) - size(shared) AS either,
       toFloat(size(shared)) / (size(x.makers) + size(y.makers) - size(shared)) AS jaccard
ORDER BY jaccard DESC"""

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


JOBS = ['Director', 'Series Composition', 'Music', 'Character Design', 'Original Creator']

RECS = """MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.score >= 8
MATCH (a)-[r1]-(maker)-[r2]-(rec:Anime)
WHERE (type(r1) = 'PRODUCED_BY' OR (type(r1) = 'WORKED_ON' AND any(job IN r1.positions WHERE job IN $jobs)))
  AND (type(r2) = 'PRODUCED_BY' OR (type(r2) = 'WORKED_ON' AND any(job IN r2.positions WHERE job IN $jobs)))
  AND NOT (u)-[:LISTED]->(rec)
  AND rec.type IN ['TV', 'Movie', 'ONA'] AND rec.score >= 7 AND rec.members >= $min_members
  AND NOT (rec)-[:RELATED_TO {relation: 'Prequel'}]->() AND NOT (rec)-[:RELATED_TO {relation: 'Parent Story'}]->()
WITH rec, maker, max(l.score) AS best, collect(DISTINCT a.mal_id) AS because
MATCH (maker)-[r3]-(made:Anime)
WHERE type(r3) = 'PRODUCED_BY' OR (type(r3) = 'WORKED_ON' AND any(job IN r3.positions WHERE job IN $jobs))
WITH rec, maker, best, because, count(DISTINCT made) AS made
WITH rec, sum((best - 7) / log(made + 1)) AS score,
     collect({maker: labels(maker)[0] + ':' + toString(maker.mal_id), made: made, best: best, because: because}) AS paths
RETURN rec.mal_id AS id, rec.title AS title, rec.image_url AS image_url, rec.score AS mal_score,
       rec.members AS members, rec.type AS type, rec.year AS year, score, paths
ORDER BY score DESC LIMIT 200"""

TEAMS = """MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)
WHERE l.status <> 'plan_to_watch'
MATCH (p:Person)-[w1:WORKED_ON]->(a)<-[w2:WORKED_ON]-(q:Person)
WHERE p.mal_id < q.mal_id
  AND any(job IN w1.positions WHERE job IN $jobs) AND any(job IN w2.positions WHERE job IN $jobs)
WITH p, q, collect(DISTINCT a.mal_id) AS together
WHERE size(together) >= 2
RETURN 'Person:' + toString(p.mal_id) AS p, 'Person:' + toString(q.mal_id) AS q, together"""


# What a team made together that you haven't listed. Anime only known by title (stubs) are fetched in the background
# and show up on a later visit, once their type, score and members are known.
TEAM_MORE = """MATCH (p:Person)-[w:WORKED_ON]->(rec:Anime)
WHERE p.mal_id IN $people AND any(job IN w.positions WHERE job IN $jobs)
  AND NOT (:User {username: $user})-[:LISTED]->(rec)
  AND NOT (rec)-[:RELATED_TO {relation: 'Prequel'}]->() AND NOT (rec)-[:RELATED_TO {relation: 'Parent Story'}]->()
  AND (rec.fetched_at IS NULL OR (rec.type IN ['TV', 'Movie', 'ONA'] AND rec.members >= $min_members))
RETURN rec.mal_id AS id, rec.title AS title, rec.image_url AS image_url, rec.score AS mal_score,
       rec.type AS type, rec.year AS year, rec.fetched_at IS NOT NULL AS fetched, collect(DISTINCT p.mal_id) AS people"""


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
    # While anime the tour asked for are still being fetched, keep the result for a minute only, so they show up soon.
    from . import jobs

    pending = jobs.queue.status(f"tour:{username}")["running"]
    with _lock:
        _cache[username] = (time.time() - (TTL - PENDING_TTL if pending else 0), result)
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
            "timeline": _timeline(members, anime, made, makers, inside),
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
    cuts, threads = _cuts(show, anime, series_of, makers)
    twins, twin_show = _twins(username, anime, series_of, makers)
    recs, rec_show = _recs(username, anime, series_of, makers)
    teams, team_show = _teams(username, anime, series_of, makers)
    return {
        "_show": show,
        "_twins": twin_show,
        "_recs": rec_show,
        "_teams": team_show,
        "twins": twins,
        "recs": recs,
        "teams": teams,
        "cuts": cuts,
        "threads": threads,
        "anime": len(anime),
        "clustered": in_clusters,
        "clusters": clusters,
        "bridges": bridges,
        "makers": len(makers),
        "queries": {"clusters": CLUSTERS, "bridges": BRIDGES, "cuts": CUTS, "twins": TWINS, "recs": RECS, "teams": TEAMS, "team_more": TEAM_MORE},
    }


def _cuts(show: list[dict[str, list[int]]], anime: dict[int, Any], series_of: dict[int, int], makers: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The people, studios and anime each cluster falls apart without.

    Returns two lists. Splits are cut points with at least two sides of two or more series, so the cluster really
    breaks in two. Threads are the rest: a single series that only connects to its cluster through one person,
    studio or anime. An anime is only reported when no person or studio next to it is a cut point too, since that
    maker usually tells the same story better."""
    splits, threads = [], []
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
                    # The cut's own anime on this side, which is what the side hangs from.
                    touch = [a for a in series.values() if _ref("Anime", a["id"]) in adj[cut] or series_of[a["id"]] in {series_of[int(n.split(":", 1)[1])] for n in adj[cut] if n.startswith("Anime:")}]
                    sides.append({
                        "series": len(series),
                        "anime": len(members),
                        "items": [_card(a) for a in list(series.values())[:SIDE_ITEMS]],
                        "touch": [_card(a) for a in touch[:2]],
                    })
            sides.sort(key=lambda x: (-x["series"], -x["anime"]))
            if len(sides) < 2:
                continue
            if kind == "Anime":
                a = anime[int(cut.split(":", 1)[1])]
                who = {"id": cut, "label": "Anime", "mal_id": a["id"], "name": a["title"], "image_url": a["image_url"]}
            else:
                who = {**makers[cut], "image_url": None}
            if sides[1]["series"] >= MIN_SIDE:
                splits.append({**who, "cluster": index, "sides": [{k: v for k, v in x.items() if k != "touch"} for x in sides]})
                continue
            for side in sides[1:]:
                threads.append({
                    "cluster": index,
                    "show": side["items"][0],
                    "via": {k: who[k] for k in ("id", "label", "name")},
                    # What the cut point also made in the rest of the cluster, when it's a person or studio.
                    "also": sides[0]["touch"] if kind != "Anime" else [],
                })
    # The most even splits first: a cut point matters most when both sides are big.
    splits.sort(key=lambda c: (-c["sides"][1]["series"], -sum(x["series"] for x in c["sides"])))
    threads.sort(key=lambda t: (t["cluster"], t["show"]["title"]))
    return splits[:MAX_CUTS], threads


def _season(a: dict[str, Any]) -> tuple[int, int] | None:
    """(year, season index) an anime started airing, from its season or else its first air date."""
    aired = a.get("aired_from") or ""
    year = a.get("year") or (int(aired[:4]) if aired[:4].isdigit() else None)
    if not year:
        return None
    if a.get("season") in SEASONS:
        return year, SEASONS.index(a["season"])
    month = int(aired[5:7]) if aired[5:7].isdigit() else 1
    return year, (month - 1) // 3


def _timeline(members: list[int], anime: dict[int, Any], made: dict[str, set[int]], makers: dict[str, Any], inside: set[int]) -> dict[str, Any]:
    """A cluster's anime by the season they started, with the people and studios behind two or more of them."""
    shared = sorted((ref for ref, did in made.items() if len(did & inside) >= 2), key=lambda ref: (-len(made[ref] & inside), makers[ref]["name"]))[:TIMELINE_MAKERS]
    items = []
    for a in members:
        when = _season(anime[a])
        if when:
            items.append({**_card(anime[a]), "year": when[0], "season": when[1], "makers": [ref for ref in shared if a in made[ref]]})
    items.sort(key=lambda x: (x["year"], x["season"], x["title"]))
    return {"items": items, "makers": [{"id": ref, "name": makers[ref]["name"], "anime": len(made[ref] & inside)} for ref in shared]}


def _twins(username: str, anime: dict[int, Any], series_of: dict[int, int], makers: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, list[int]]]]:
    """The anime from different series that share the most of their makers, by Jaccard similarity.

    Pairs that share exactly the same makers and have an anime in common are merged, so three shows made by one
    team come out as one group of three instead of three pairs."""
    groups: list[dict[str, Any]] = []
    seen = set()
    for r in db.run(TWINS, user=username, min_shared=MIN_SHARED):
        a, b = r["a"], r["b"]
        if a not in anime or b not in anime:
            continue
        pair = frozenset((series_of[a], series_of[b]))
        if len(pair) < 2 or pair in seen:
            continue
        seen.add(pair)
        shared = frozenset(ref for ref in r["shared"] if ref in makers)
        group = next((g for g in groups if g["shared"] == shared and {a, b} & g["anime"]), None)
        if group:
            group["anime"] |= {a, b}
            continue
        if len(groups) >= MAX_TWINS:
            break
        groups.append({"anime": {a, b}, "shared": shared, "either": r["either"], "jaccard": r["jaccard"]})
    twins, show = [], []
    for g in groups:
        ids = sorted(g["anime"], key=lambda x: (-anime[x]["score"], x))
        # Several anime of one series can join a group through different partners, so keep one per series.
        one = {}
        for x in ids:
            one.setdefault(series_of[x], x)
        ids = list(one.values())
        shared = sorted((makers[ref] for ref in g["shared"]), key=lambda m: (m["label"] != "Person", m["name"]))
        twins.append({
            "shows": [_card(anime[x]) for x in ids],
            "shared": [{k: m[k] for k in ("id", "label", "name")} for m in shared],
            "either": g["either"],
            "jaccard": round(g["jaccard"], 2),
        })
        show.append(_ids(ids, shared))
    return twins, show


def _recs(username: str, anime: dict[int, Any], series_of: dict[int, int], makers: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, list[int]]]]:
    """Anime you haven't listed, reached in two steps from the ones you scored highest, with the paths that led there.

    Anything from a series you've already seen any of is left out, so these are new series."""
    franchise = games.recent_franchises()
    listed = {r["id"] for r in db.run("MATCH (:User {username: $user})-[:LISTED]->(a:Anime) RETURN a.mal_id AS id", user=username)}
    seen_series = {franchise.get(a, a) for a in listed}
    recs, show, taken = [], [], set()
    for r in db.run(RECS, user=username, jobs=JOBS, min_members=REC_MIN_MEMBERS):
        series = franchise.get(r["id"], r["id"])
        if series in seen_series or series in taken:
            continue
        taken.add(series)
        # The strongest paths first: a high score at the start and a maker with few shows.
        paths = sorted((p for p in r["paths"] if p["maker"] in makers), key=lambda p: -(p["best"] - 7) / math.log(p["made"] + 1))[:REC_PATHS]
        if not paths:
            continue
        def starts(p: dict[str, Any]) -> list[int]:
            """The anime a path starts from, one per series, best scored first."""
            one: dict[int, int] = {}
            for a in sorted((a for a in p["because"] if a in anime), key=lambda a: (-anime[a]["score"], a)):
                one.setdefault(series_of[a], a)
            return list(one.values())[:2]

        because = list(dict.fromkeys(a for p in paths for a in starts(p)))
        recs.append({
            "anime": {"mal_id": r["id"], "title": r["title"], "image_url": r["image_url"], "mal_score": r["mal_score"], "members": r["members"], "type": r["type"], "year": r["year"]},
            "score": round(r["score"], 2),
            "paths": [{
                "maker": {k: makers[p["maker"]][k] for k in ("id", "label", "name")},
                "made": p["made"],
                "because": [{**_card(anime[a]), "my_score": anime[a]["score"]} for a in starts(p)],
            } for p in paths],
        })
        show.append(_ids([r["id"], *because], [makers[p["maker"]] for p in paths]))
        if len(recs) >= MAX_RECS:
            break
    return recs, show


def _teams(username: str, anime: dict[int, Any], series_of: dict[int, int], makers: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, list[int]]]]:
    """People who keep working together across your series.

    Pairs come from the projection query. A team starts from the pair with the most series in common and takes in
    anyone who worked with every member on at least two of those series, so three people who always work together
    come out as one team of three."""
    together: dict[frozenset[str], set[int]] = {}
    for r in db.run(TEAMS, user=username, jobs=JOBS):
        if r["p"] in makers and r["q"] in makers:
            together[frozenset((r["p"], r["q"]))] = {a for a in r["together"] if a in anime}

    def series(ids: set[int]) -> set[int]:
        return {series_of[a] for a in ids}

    pairs = sorted((p for p in together if len(series(together[p])) >= 2), key=lambda p: (-len(series(together[p])), sorted(p)))
    people = {x for p in pairs for x in p}
    teams: list[tuple[frozenset[str], set[int]]] = []
    for pair in pairs:
        team, shared = set(pair), set(together[pair])
        grew = True
        while grew:
            grew = False
            best = None
            for x in sorted(people - team):
                links = [together.get(frozenset((x, y))) for y in team]
                if any(l is None for l in links):
                    continue
                common = shared.intersection(*links)
                if len(series(common)) >= 2 and (best is None or len(series(common)) > len(series(best[1]))):
                    best = (x, common)
            if best:
                team.add(best[0])
                shared = best[1]
                grew = True
        key = frozenset(team)
        # Skip a team already found, or one inside a bigger team with the same series.
        if any(key <= t and series(shared) <= series(s) for t, s in teams):
            continue
        teams.append((key, shared))
    teams.sort(key=lambda t: (-len(series(t[1])), -len(t[0])))
    out, show = [], []
    appears: Counter[str] = Counter()
    for team, shared in teams:
        # Someone who works with everyone would fill the list, so each person is in two teams at most.
        if len(out) >= MAX_TEAMS or any(appears[x] >= 2 for x in team):
            continue
        appears.update(team)
        one: dict[int, int] = {}
        for a in sorted(shared, key=lambda a: (-anime[a]["score"], a)):
            one.setdefault(series_of[a], a)
        members = sorted((makers[x] for x in team), key=lambda m: m["name"])
        more = _team_more(username, members, series_of)
        out.append({
            "people": [{"id": m["id"], "name": m["name"]} for m in members],
            "series": len(one),
            "shows": [_card(anime[a]) for a in one.values()],
            "more": more,
        })
        show.append(_ids(sorted(shared) + [m["mal_id"] for m in more], members))
    return out, show


def _team_more(username: str, members: list[dict[str, Any]], series_of: dict[int, int]) -> list[dict[str, Any]]:
    """Anime from series you haven't seen that the whole team, or for a bigger team at least two of them, worked on.

    Stubs among them are queued for fetching, so they can be shown on a later visit."""
    from . import jobs

    franchise = games.recent_franchises()
    seen = set(series_of.values())
    ids = [m["mal_id"] for m in members]
    need = min(len(ids), 2)
    rows = [r for r in db.run(TEAM_MORE, people=ids, jobs=JOBS, user=username, min_members=REC_MIN_MEMBERS)
            if len(r["people"]) >= need and franchise.get(r["id"], r["id"]) not in seen]
    stubs = [r["id"] for r in rows if not r["fetched"]][:TEAM_FETCH]
    if stubs:
        jobs.queue.enqueue(f"tour:{username}", stubs)
    picked, taken = [], set()
    for r in sorted((r for r in rows if r["fetched"]), key=lambda r: (-len(r["people"]), -(r["mal_score"] or 0))):
        series = franchise.get(r["id"], r["id"])
        if series in taken:
            continue
        taken.add(series)
        picked.append({k: r[k] for k in ("title", "image_url", "mal_score", "type", "year")} | {"mal_id": r["id"], "people": len(r["people"])})
        if len(picked) >= TEAM_RECS:
            break
    return picked


def _card(a: dict[str, Any]) -> dict[str, Any]:
    return {"mal_id": a["id"], "title": a["title"], "image_url": a["image_url"]}


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


def show_item(username: str, step: str, index: int) -> dict[str, list[int]] | None:
    """What to draw for one card of a step: twins and the makers they share, a recommendation and its paths, or a
    team and the anime they made together."""
    show = tour(username).get(f"_{step}")
    return show[index] if show is not None and 0 <= index < len(show) else None


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
    from . import jobs

    with _lock:
        _cache.pop(username, None)
    jobs.queue.cancel(f"tour:{username}")
