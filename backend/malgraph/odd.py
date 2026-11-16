"""Odd one out: four characters, three of which share a hidden link. Pick the one that doesn't belong.

The link is a Japanese voice actor, a studio, an original creator or an anime season. Characters come from the
POOL most favourited main characters, so players have a chance of knowing them. A round is only offered when the
graph guarantees exactly one answer: the three never share a franchise (that would be too easy), the odd one has
none of the three's franchises, and no other group of three among the four shares any link at all.

The daily set has ROUNDS rounds. Practice rounds are endless and kept in memory until answered.
"""
from __future__ import annotations

import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from . import db, games

POOL = 800
ROUNDS = 5
KINDS = {"va": 3, "studio": 2, "creator": 2, "season": 2}  # how often each kind of link is drawn
SEASONS = {"winter": "Winter", "spring": "Spring", "summer": "Summer", "fall": "Fall"}
FACTS_TTL = 600  # seconds to reuse the link index for practice rounds
PRACTICE_TTL = 3600


@dataclass
class Facts:
    ids: list[int]
    feats: dict[int, set[str]] = field(default_factory=dict)  # character -> link keys, including "anime:<id>"
    labels: dict[str, str] = field(default_factory=dict)  # link key -> name
    index: dict[str, set[int]] = field(default_factory=dict)  # link key -> characters
    via: dict[tuple[int, str], tuple[int, str]] = field(default_factory=dict)  # (character, link) -> (members, anime title)

    def anime(self, c: int) -> set[str]:
        return {f for f in self.feats[c] if f.startswith("anime:")}  # franchises, in fact (see facts())

    def add(self, c: int, key: str, label: str | None = None, title: str | None = None, members: int = 0) -> None:
        self.feats.setdefault(c, set()).add(key)
        self.index.setdefault(key, set()).add(c)
        if label:
            self.labels[key] = label
        if title and members >= self.via.get((c, key), (-1, ""))[0]:  # the best-known anime that gives the link
            self.via[(c, key)] = (members, title)


def facts() -> Facts:
    """Every link between the pool's characters, from a handful of queries.

    Each character's "anime:" keys are the franchises of every anime they appear in, in any role. Promotional
    specials often have no related-anime links, but their characters also appear in the main series, so this
    still puts them in the right franchise. Seasons, studios and creators count only anime with a main role."""
    f = Facts(games.popular_characters(POOL))
    franchise = games.franchises()
    for c in f.ids:
        f.feats[c] = set()
    rows = db.run(
        "MATCH (a:Anime)-[h:HAS_CHARACTER]->(c:Character) WHERE c.id IN $ids "
        "RETURN c.id AS c, a.id AS a, h.role = 'Main' AS main, a.season AS season, a.year AS year, "
        "a.title AS title, coalesce(a.members, 0) AS members",
        ids=f.ids,
    )
    for r in rows:
        f.add(r["c"], f"anime:{franchise.get(r['a'], r['a'])}")
        if r["main"] and r["season"] in SEASONS and r["year"]:
            f.add(r["c"], f"season:{r['year']}-{r['season']}", f"{SEASONS[r['season']]} {r['year']}", r["title"], r["members"])
    for kind, query in [
        ("va", "MATCH (p:Person)-[:VOICES {language: 'Japanese'}]->(c:Character) WHERE c.id IN $ids "
               "RETURN c.id AS c, p.id AS k, p.name AS label"),
        ("studio", "MATCH (s:Studio)<-[:PRODUCED_BY]-(a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) WHERE c.id IN $ids "
                   "RETURN c.id AS c, s.id AS k, s.name AS label, a.title AS title, coalesce(a.members, 0) AS members"),
        ("creator", "MATCH (p:Person)-[w:WORKED_ON]->(a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) "
                    "WHERE c.id IN $ids AND 'Original Creator' IN w.positions "
                    "RETURN c.id AS c, p.id AS k, p.name AS label, a.title AS title, coalesce(a.members, 0) AS members"),
    ]:
        for r in db.run(query, ids=f.ids):
            f.add(r["c"], f"{kind}:{r['k']}", r["label"], r.get("title"), r.get("members") or 0)
    return f


def describe(f: Facts, key: str) -> dict[str, str]:
    """The link as a sentence, with the name in it and where that name links to: the voice actor's roster in the
    app, or the studio, creator or season on MyAnimeList."""
    kind, rest = key.split(":", 1)
    label = f.labels.get(key, "")
    if kind in ("va", "creator"):
        label = games.natural(label)
    text = {
        "va": f"All three are voiced by {label} in Japanese.",
        "studio": f"All three are main characters in anime by {label}.",
        "creator": f"All three were created by {label}.",
        "season": f"All three are main characters in anime from {label}.",
    }[kind]
    if kind == "season":
        year, season = rest.split("-")
        href = f"https://myanimelist.net/anime/season/{year}/{season}"
    else:
        href = {
            "va": f"#/roster/{rest}",
            "studio": f"https://myanimelist.net/anime/producer/{rest}",
            "creator": f"https://myanimelist.net/people/{rest}",
        }[kind]
    return {"text": text, "name": label, "href": href}


def links(rnd: dict[str, Any]) -> list[dict[str, str]]:
    """A round's links as objects. Rounds made before links had names stored plain sentences."""
    return [x if isinstance(x, dict) else {"text": x} for x in rnd["links"]]


def _shared(f: Facts, chars: list[int]) -> set[str]:
    return set.intersection(*(f.feats[c] for c in chars))


def make_round(f: Facts, rng: random.Random, kind: str, used: set[int] = frozenset()) -> dict[str, Any] | None:
    """One round with a link of the given kind, avoiding characters already used. None if none was found."""
    keys = [k for k, cs in f.index.items() if k.startswith(f"{kind}:") and len(cs - used) >= 3]
    rng.shuffle(keys)
    for key in keys[:40]:
        members = sorted(f.index[key] - used)
        rng.shuffle(members)
        trio: list[int] = []
        for c in members:  # three characters who share no anime with each other
            if all(not (f.anime(c) & f.anime(t)) for t in trio):
                trio.append(c)
            if len(trio) == 3:
                break
        if len(trio) < 3:
            continue
        outsiders = [c for c in f.ids if c not in used and key not in f.feats[c]]
        for odd in rng.sample(outsiders, min(300, len(outsiders))):
            if any(f.anime(odd) & f.anime(t) for t in trio):
                continue
            if any(_shared(f, [odd, x, y]) for x, y in combinations(trio, 2)):
                continue  # another three would also share a link, so there'd be two answers
            cards = [*trio, odd]
            rng.shuffle(cards)
            also = sorted(k for k in _shared(f, trio) if k != key and not k.startswith("anime:"))
            # Each of the three shows the anime that carries the link, since their best-known one may not.
            shown = {str(c): f.via[(c, key)][1] for c in trio if (c, key) in f.via}
            return {"cards": cards, "answer": odd, "links": [describe(f, k) for k in [key, *also]], "shown": shown}
    return None


def make_set(f: Facts, rng: random.Random, n: int) -> list[dict[str, Any]]:
    """n rounds with no character twice, spreading the kinds of link."""
    kinds = list(KINDS)
    rng.shuffle(kinds)
    order = [kinds[i % len(kinds)] for i in range(n)]
    used: set[int] = set()
    rounds = []
    for kind in order:
        rnd = make_round(f, rng, kind, used)
        for other in (k for k in KINDS if k != kind):  # fall back to another kind if this one has nothing left
            if rnd:
                break
            rnd = make_round(f, rng, other, used)
        if rnd:
            used.update(rnd["cards"])
            rounds.append(rnd)
    return rounds


# --------------------------------------------------------------------------- daily set

def daily(day: str | None = None) -> dict[str, Any]:
    return games.daily("odd", lambda rng: {"rounds": make_set(facts(), rng, ROUNDS)}, day)


def answer_daily(username: str, index: int, pick: int) -> dict[str, Any]:
    """Record a player's pick for one round. Only the first pick of each round counts."""
    puzzle = daily()
    rounds = puzzle["rounds"]
    if not 0 <= index < len(rounds):
        raise ValueError("no such round")
    rnd = rounds[index]
    if pick not in rnd["cards"]:
        raise ValueError("that character isn't in this round")

    def change(play: dict[str, Any] | None) -> dict[str, Any]:
        play = play or {"picks": [None] * len(rounds), "at": time.time()}
        if play["picks"][index] is None:
            play["picks"][index] = pick
        return play

    play = games.update_play("odd", puzzle["date"], username, change)
    return reveal(puzzle, index, play["picks"][index])


def reveal(puzzle: dict[str, Any], index: int, pick: int) -> dict[str, Any]:
    rnd = puzzle["rounds"][index]
    picks = [p["picks"][index] for p in games.plays("odd", puzzle["date"]).values() if p["picks"][index] is not None]
    return {
        "pick": pick,
        "correct": pick == rnd["answer"],
        "answer": rnd["answer"],
        "links": links(rnd),
        "players": len(picks),
        "right": sum(1 for p in picks if p == rnd["answer"]),
    }


def summary(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Scores of everyone who finished the day's set, as counts only."""
    answers = [r["answer"] for r in puzzle["rounds"]]
    finished = [p for p in games.plays("odd", puzzle["date"]).values() if all(x is not None for x in p["picks"])]
    scores = [sum(1 for x, a in zip(p["picks"], answers) if x == a) for p in finished]
    return {"players": len(finished), "by_score": games.histogram(scores)}


# --------------------------------------------------------------------------- practice

_lock = threading.Lock()
_facts: tuple[float, Facts] | None = None
_practice: dict[str, tuple[float, dict[str, Any]]] = {}  # token -> (expiry, round)


def _cached_facts() -> Facts:
    global _facts
    with _lock:
        if _facts is None or time.time() - _facts[0] > FACTS_TTL:
            _facts = (time.time(), facts())
        return _facts[1]


def practice_round() -> dict[str, Any] | None:
    rng = random.Random()
    f = _cached_facts()
    kinds = list(KINDS)
    rnd = None
    for kind in rng.sample(kinds, len(kinds)):
        rnd = make_round(f, rng, kind)
        if rnd:
            break
    if not rnd:
        return None
    token = secrets.token_urlsafe(12)
    now = time.time()
    with _lock:
        for t in [t for t, (exp, _) in _practice.items() if exp < now]:
            del _practice[t]
        _practice[token] = (now + PRACTICE_TTL, rnd)
    return {"token": token, "cards": rnd["cards"], "shown": rnd["shown"]}


def answer_practice(token: str, pick: int) -> dict[str, Any] | None:
    with _lock:
        entry = _practice.pop(token, None)
    if not entry:
        return None
    rnd = entry[1]
    return {"pick": pick, "correct": pick == rnd["answer"], "answer": rnd["answer"], "links": links(rnd)}
