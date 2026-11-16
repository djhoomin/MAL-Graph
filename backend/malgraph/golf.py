"""Graph Golf: get from one node to another in as few steps as you can.

A hole joins two well-known, fully fetched nodes that are 3 to 5 steps apart. A stroke is one step along a voice
role (Japanese), a character, a staff credit, a related anime or a studio. Par is the average length of a sample of
reasonable routes. Each route starts with one of up to OPENINGS moves away from the tee and then takes the shortest
way to the hole from there, so par says what a fair round looks like without enumerating every path (which would
explode on a graph this connected). Memgraph answers all the openings in one BFS query.

The daily hole is chosen from the date, saved, and stays fixed for the day even as the graph grows.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
from pathlib import Path
from typing import Any

from . import db
from .config import settings

RELS = ["VOICES", "HAS_CHARACTER", "WORKED_ON", "RELATED_TO", "PRODUCED_BY"]
LANG = "Japanese"
LABELS = {"Anime", "Character", "Person", "Studio"}
MIN_HOPS, MAX_HOPS = 3, 5
OPENINGS = 30
MAX_MOVES = 60
STEP = "(r, x | type(r) IN $rels AND (type(r) <> 'VOICES' OR r.language = $lang))"

_gen_lock = threading.Lock()  # one hole is worked out at a time, server-wide
_score_lock = threading.Lock()


class GolfError(ValueError):
    pass


def parse(ref: str) -> tuple[str, int]:
    label, _, key = ref.partition(":")
    if label not in LABELS or not key.isdigit():
        raise GolfError(f"not a golf node: {ref}")
    return label, int(key)


# --------------------------------------------------------------------------- graph questions

def shortest_path(a: str, b: str, max_hops: int = MAX_HOPS + 2) -> Any | None:
    """The shortest path between two refs over golf moves, as the driver's Path (for canvas payloads), or None."""
    (la, ia), (lb, ib) = parse(a), parse(b)
    with db.get_driver().session() as session:
        rec = session.run(
            f"MATCH (a:{la} {{id: $a}}), (b:{lb} {{id: $b}}) MATCH p = (a)-[*BFS ..{max_hops} {STEP}]-(b) RETURN p",
            a=ia, b=ib, rels=RELS, lang=LANG,
        ).single()
        return rec["p"] if rec else None


def hops(a: str, b: str, max_hops: int = MAX_HOPS + 2) -> int | None:
    (la, ia), (lb, ib) = parse(a), parse(b)
    rows = db.run(
        f"MATCH (a:{la} {{id: $a}}), (b:{lb} {{id: $b}}) MATCH p = (a)-[*BFS ..{max_hops} {STEP}]-(b) RETURN size(relationships(p)) AS n",
        a=ia, b=ib, rels=RELS, lang=LANG,
    )
    return rows[0]["n"] if rows else None


def par_for(a: str, b: str, best: int, rng: random.Random) -> tuple[int, list[int]]:
    """Average route length over a sample of opening moves, each finished by the shortest way to the hole."""
    (la, ia), (lb, ib) = parse(a), parse(b)
    opens = db.run(
        f"MATCH (a:{la} {{id: $a}})-[r]-(n) WHERE type(r) IN $rels AND (type(r) <> 'VOICES' OR r.language = $lang) "
        "RETURN DISTINCT id(n) AS id",
        a=ia, rels=RELS, lang=LANG,
    )
    ids = [o["id"] for o in opens]
    sample = rng.sample(ids, min(OPENINGS, len(ids)))
    rows = db.run(
        f"MATCH (a:{la} {{id: $a}}), (b:{lb} {{id: $b}}) "
        "UNWIND $ids AS nid MATCH (n) WHERE id(n) = nid "
        f"OPTIONAL MATCH p = (n)-[*BFS ..{best + 3} (r, x | x <> a AND type(r) IN $rels AND (type(r) <> 'VOICES' OR r.language = $lang))]-(b) "
        "RETURN nid, n = b AS at_hole, CASE WHEN p IS NULL THEN null ELSE size(relationships(p)) END AS d",
        a=ia, b=ib, ids=sample, rels=RELS, lang=LANG,
    )
    routes = sorted(1 + (0 if r["at_hole"] else r["d"]) for r in rows if r["at_hole"] or r["d"] is not None)
    if not routes:
        return best + 1, []
    return max(best, math.floor(sum(routes) / len(routes) + 0.5)), routes  # halves round up, as in golf


EASY_OPTIONS = 6


def easy_moves(here: str, hole: str) -> tuple[list[str], int | None]:
    """Easy mode: a short list of moves from `here`, one of which always gets closer to the hole, and how far the
    hole is. The list comes from a seed made of the position and the hole, so it doesn't change on a reload and every
    player at the same spot sees the same choices."""
    path = shortest_path(here, hole, MAX_HOPS + 4)
    to_hole = len(path.relationships) if path is not None else None
    closer = None
    if path is not None and len(path.nodes) > 1:
        n = path.nodes[1]
        closer = f"{next(iter(n.labels & LABELS))}:{n['id']}"
    la, ia = parse(here)
    rows = db.run(
        f"MATCH (a:{la} {{id: $a}})-[r]-(n) WHERE type(r) IN $rels AND (type(r) <> 'VOICES' OR r.language = $lang) "
        "RETURN DISTINCT labels(n)[0] AS label, n.id AS id",
        a=ia, rels=RELS, lang=LANG,
    )
    refs = sorted({f"{r['label']}:{r['id']}" for r in rows if r["label"] in LABELS} - {here, closer or ""})
    rng = random.Random(f"easy:{here}->{hole}")
    picked = rng.sample(refs, min(EASY_OPTIONS - (1 if closer else 0), len(refs)))
    if closer:
        picked.insert(rng.randrange(len(picked) + 1), closer)
    return picked, to_hole


def adjacent(a: str, b: str) -> bool:
    (la, ia), (lb, ib) = parse(a), parse(b)
    rows = db.run(
        f"MATCH (x:{la} {{id: $a}})-[r]-(y:{lb} {{id: $b}}) "
        "WHERE type(r) IN $rels AND (type(r) <> 'VOICES' OR r.language = $lang) RETURN count(r) AS n",
        a=ia, b=ib, rels=RELS, lang=LANG,
    )
    return bool(rows and rows[0]["n"])


# --------------------------------------------------------------------------- holes

def _pools() -> list[list[str]]:
    """Well-known, fully fetched tees and holes: popular anime, favourite main characters, busy voice actors."""
    anime = db.run("MATCH (a:Anime) WHERE a.fetched_at IS NOT NULL AND a.members IS NOT NULL RETURN a.id AS id ORDER BY a.members DESC LIMIT 300")
    chars = db.run(
        # Cypher sorts missing values first when descending, so leave out characters without a count.
        "MATCH (a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) WHERE a.fetched_at IS NOT NULL AND c.favorites IS NOT NULL "
        "RETURN DISTINCT c.id AS id, c.favorites AS f ORDER BY f DESC LIMIT 300"
    )
    people = db.run(
        "MATCH (p:Person)-[:VOICES {language: 'Japanese'}]->(c:Character) WITH p, count(c) AS n WHERE n >= 5 "
        "RETURN p.id AS id ORDER BY coalesce(p.favorites, 0) DESC, n DESC LIMIT 200"
    )
    pools = [[f"Anime:{r['id']}" for r in anime], [f"Character:{r['id']}" for r in chars], [f"Person:{r['id']}" for r in people]]
    return [p for p in pools if p]


def make_hole(rng: random.Random) -> dict[str, Any]:
    """Pick a tee and a hole MIN_HOPS..MAX_HOPS apart, then work out par."""
    with _gen_lock:
        pools = _pools()
        if not pools:
            raise GolfError("the graph is too small for golf yet")
        fallback: tuple[str, str, int] | None = None
        for _ in range(25):
            a, b = rng.choice(rng.choice(pools)), rng.choice(rng.choice(pools))
            if a == b:
                continue
            n = hops(a, b)
            if n is None:
                continue
            if MIN_HOPS <= n <= MAX_HOPS:
                break
            if fallback is None or abs(n - 4) < abs(fallback[2] - 4):
                fallback = (a, b, n)
        else:
            if fallback is None:
                raise GolfError("couldn't find a playable hole")
            a, b, n = fallback
        par, routes = par_for(a, b, n, rng)
        return {"start": a, "end": b, "shortest": n, "par": par, "routes": routes, "made_at": time.time()}


def _dir(*parts: str) -> Path:
    path = settings.golf_dir.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def daily_hole(day: str | None = None) -> dict[str, Any]:
    day = day or today()
    path = _dir("holes") / f"{day}.json"
    if path.exists():
        return json.loads(path.read_text())
    hole = {"date": day, **make_hole(random.Random(f"mal-graph-golf-{day}"))}
    with _gen_lock:
        if path.exists():  # another request made it while we were working
            return json.loads(path.read_text())
        path.write_text(json.dumps(hole))
    return hole


def practice_hole() -> dict[str, Any]:
    return make_hole(random.Random())


# --------------------------------------------------------------------------- rounds

def check_round(hole: dict[str, Any], moves: list[str]) -> int:
    """Validate a played round (every position from tee to hole, backtracks included). Returns the strokes."""
    if len(moves) < 2 or len(moves) > MAX_MOVES + 1:
        raise GolfError("a round needs between 1 and 60 moves")
    if moves[0] != hole["start"] or moves[-1] != hole["end"]:
        raise GolfError("a round must start at the tee and finish in the hole")
    for a, b in zip(moves, moves[1:]):
        if not adjacent(a, b):
            raise GolfError(f"{a} and {b} are not connected")
    return len(moves) - 1


def board(day: str, easy: bool = False) -> str:
    """The scoreboard a round goes on. Easy rounds have their own, so the two modes aren't ranked together."""
    return f"{day}-easy" if easy else day


def _scores_path(day: str) -> Path:
    return _dir("scores") / f"{day}.json"


def _load_scores(day: str) -> dict[str, Any]:
    try:
        return json.loads(_scores_path(day).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def record(day: str, username: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Keep a player's first round of the day. Returns the round that counts."""
    with _score_lock:
        scores = _load_scores(day)
        key = username.lower()
        if key not in scores:
            scores[key] = {**entry, "at": time.time()}
            tmp = _scores_path(day).with_suffix(".tmp")
            tmp.write_text(json.dumps(scores))
            tmp.replace(_scores_path(day))
        return scores[key]


def my_round(day: str, username: str) -> dict[str, Any] | None:
    return _load_scores(day).get(username.lower())


def summary(day: str, username: str | None, par: int) -> dict[str, Any]:
    """How the day's field did, without naming anyone: players per score relative to par, and your place."""
    scores = _load_scores(day)
    finished = [s for s in scores.values() if not s.get("gave_up")]
    counts: dict[int, int] = {}
    for s in finished:
        counts[s["strokes"] - par] = counts.get(s["strokes"] - par, 0) + 1
    mine = scores.get(username.lower()) if username else None
    rank = None
    if mine and not mine.get("gave_up"):
        rank = 1 + sum(1 for s in finished if (s["strokes"], s.get("mulligans", 0)) < (mine["strokes"], mine.get("mulligans", 0)))
    return {
        "players": len(scores),
        "finished": len(finished),
        "by_score": [{"to_par": k, "players": v} for k, v in sorted(counts.items())],
        "rank": rank,
    }


def forget(username: str) -> int:
    """Remove a user's rounds from every day's scores. Returns how many were removed."""
    key, removed = username.lower(), 0
    with _score_lock:
        for path in _dir("scores").glob("*.json"):
            try:
                scores = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if scores.pop(key, None) is not None:
                path.write_text(json.dumps(scores))
                removed += 1
    return removed
