"""Yay or Nay: swipe right or left on character cards.

Today's stack is DAILY_CARDS popular characters, the same for everyone, and once you're through it you see what share
of players said yay to each. From your list deals endless cards from anime you've watched, never one you've voted on.

Every vote also goes into the player's record (the play stored under the day "mine"), which drives the patterns: what
the characters you said yay or nay to have in common, such as a voice actor, a studio, a genre or a series, measured
against your overall yay rate so that saying yay to everyone doesn't make everything a pattern.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

from . import db, games

GAME = "yay"
RECORD = "mine"  # the day key of each player's record of every vote
DAILY_CARDS = 20
DAILY_POOL = 400
MINE_POOL = 400
BATCH = 10
MIN_VOTES = 10  # votes before patterns show
MIN_GROUP = 3  # characters a pattern needs
MIN_LIFT = 0.2  # how far a group's yay rate must be from the player's overall rate
MAX_PATTERNS = 3  # of each direction
HIDDEN_GENRES = ["Hentai", "Erotica", "Ecchi"]


def make(rng: random.Random) -> dict[str, Any]:
    """The day's stack: popular main characters, at most one per series."""
    pool = games.popular_characters(DAILY_POOL)
    if not pool:
        raise ValueError("the graph has no popular characters yet")
    series = _series_of(pool)
    picked, used = [], set()
    for cid in rng.sample(pool, len(pool)):
        s = series.get(cid, cid)
        if s in used:
            continue
        used.add(s)
        picked.append(cid)
        if len(picked) == DAILY_CARDS:
            break
    return {"cards": picked}


def daily(day: str | None = None) -> dict[str, Any]:
    return games.daily(GAME, make, day)


def _series_of(ids: list[int]) -> dict[int, int]:
    """Character -> the franchise of their best-known anime."""
    franchise = games.recent_franchises()
    rows = db.run(
        "MATCH (a:Anime)-[:HAS_CHARACTER]->(c:Character) WHERE c.id IN $ids "
        "WITH c, a ORDER BY coalesce(a.members, 0) DESC WITH c, head(collect(a.id)) AS a "
        "RETURN c.id AS c, a",
        ids=ids,
    )
    return {r["c"]: franchise.get(r["a"], r["a"]) for r in rows}


# --------------------------------------------------------------------------- votes


def record(username: str) -> dict[str, int]:
    """Every vote the player has made, character id (as text) -> 1 for yay, 0 for nay."""
    play = games.my_play(GAME, RECORD, username)
    return dict(play["votes"]) if play else {}


def vote(username: str, character: int, yay: bool, today: bool) -> dict[str, Any] | None:
    """Record a vote, in today's play too when it's one of today's cards. Returns today's play, or None for a card
    from the player's list. Raises ValueError for a card that isn't in today's stack."""
    key, value = str(character), int(yay)

    def add(play: dict[str, Any] | None) -> dict[str, Any]:
        play = play or {"votes": {}}
        play["votes"][key] = value
        return play

    out = None
    if today:
        puzzle = daily()
        if character not in puzzle["cards"]:
            raise ValueError("That character isn't in today's stack")
        out = games.update_play(GAME, puzzle["date"], username, add)
    games.update_play(GAME, RECORD, username, add)
    return out


def results(puzzle: dict[str, Any]) -> dict[str, dict[str, int]]:
    """For each of today's cards, how many players voted and how many said yay. Counts only, never names."""
    out: dict[str, dict[str, int]] = {str(c): {"players": 0, "yay": 0} for c in puzzle["cards"]}
    for play in games.plays(GAME, puzzle["date"]).values():
        for key, value in play["votes"].items():
            if key in out:
                out[key]["players"] += 1
                out[key]["yay"] += value
    return out


def mine_cards(username: str, n: int = BATCH) -> list[int]:
    """Cards from anime the player has watched that they haven't voted on, best-known first with some shuffle."""
    voted = {int(k) for k in record(username)}
    rows = db.run(
        "MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)-[h:HAS_CHARACTER]->(c:Character) "
        "WHERE l.status <> 'plan_to_watch' AND c.favorites IS NOT NULL "
        "WITH c, max(CASE WHEN h.role = 'Main' THEN 1 ELSE 0 END) AS main "
        "RETURN c.id AS id ORDER BY main DESC, c.favorites DESC LIMIT $n",
        user=username, n=MINE_POOL + len(voted),
    )
    fresh = [r["id"] for r in rows if r["id"] not in voted]
    if not fresh:
        fresh = [c for c in games.popular_characters(MINE_POOL) if c not in voted]
    # Draw from the best-known few dozen, so the stack mixes favourites with some surprises.
    head = fresh[: max(n * 4, 40)]
    return random.sample(head, min(n, len(head)))


# --------------------------------------------------------------------------- patterns


def _features(ids: list[int]) -> dict[int, list[tuple[str, str, str]]]:
    """For each character, the (kind, key, label) groups they belong to: their main Japanese voice actor, and the
    series, studios and genres of their best-known anime."""
    out: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
    for r in db.run(
        "MATCH (p:Person)-[v:VOICES {language: 'Japanese'}]->(c:Character) WHERE c.id IN $ids "
        "WITH c, p ORDER BY coalesce(v.rank, 999), coalesce(p.favorites, 0) DESC "
        "WITH c, head(collect(p)) AS p RETURN c.id AS c, p.id AS id, p.name AS name",
        ids=ids,
    ):
        out[r["c"]].append(("voice", str(r["id"]), games.natural(r["name"])))
    best = db.run(
        "MATCH (a:Anime)-[:HAS_CHARACTER]->(c:Character) WHERE c.id IN $ids "
        "WITH c, a ORDER BY coalesce(a.members, 0) DESC WITH c, head(collect(a)) AS a "
        "OPTIONAL MATCH (a)-[:PRODUCED_BY]->(s:Studio) "
        "OPTIONAL MATCH (a)-[:HAS_GENRE]->(g:Genre) WHERE g.kind IN ['genre', 'theme'] AND NOT g.name IN $hidden "
        "RETURN c.id AS c, a.id AS anime, " + db.title("a") + " AS title, collect(DISTINCT s.name) AS studios, collect(DISTINCT g.name) AS genres",
        ids=ids, hidden=HIDDEN_GENRES,
    )
    franchise = games.recent_franchises()
    for r in best:
        if r["anime"] is not None:
            out[r["c"]].append(("series", str(franchise.get(r["anime"], r["anime"])), r["title"]))
        out[r["c"]] += [("studio", s, s) for s in r["studios"]]
        out[r["c"]] += [("genre", g, g) for g in r["genres"]]
    return out


def patterns(username: str) -> dict[str, Any]:
    """What the player's yays and nays have in common, against their overall yay rate."""
    votes = {int(k): v for k, v in record(username).items()}
    total, yays = len(votes), sum(votes.values())
    out: dict[str, Any] = {"votes": total, "yay": yays, "need": max(0, MIN_VOTES - total), "likes": [], "dislikes": []}
    if total < MIN_VOTES:
        return out
    rate = yays / total
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for cid, feats in _features(list(votes)).items():
        for kind, key, label in feats:
            g = groups.setdefault((kind, key), {"kind": kind, "label": label, "yay": 0, "total": 0})
            g["total"] += 1
            g["yay"] += votes[cid]
    likes, dislikes = [], []
    for g in groups.values():
        if g["total"] < MIN_GROUP:
            continue
        lift = g["yay"] / g["total"] - rate
        weight = lift * math.sqrt(g["total"])  # a lean over more characters counts for more
        if lift >= MIN_LIFT and g["yay"] >= MIN_GROUP:
            likes.append((weight, g))
        elif lift <= -MIN_LIFT and g["total"] - g["yay"] >= MIN_GROUP:
            dislikes.append((-weight, g))
    out["likes"] = _top(likes)
    out["dislikes"] = _top(dislikes)
    return out


def _top(scored: list[tuple[float, dict[str, Any]]]) -> list[dict[str, Any]]:
    """The strongest patterns, one per kind first so a single genre-heavy stack doesn't fill the list."""
    scored.sort(key=lambda t: (-t[0], t[1]["label"]))
    picked, kinds = [], set()
    for _, g in scored:
        if g["kind"] not in kinds:
            picked.append(g)
            kinds.add(g["kind"])
    for _, g in scored:
        if len(picked) >= MAX_PATTERNS:
            break
        if g not in picked:
            picked.append(g)
    return picked[:MAX_PATTERNS]
