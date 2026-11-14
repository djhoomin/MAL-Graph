"""Mystery character: guess the day's character from clues revealed one at a time.

The character is one of the POOL most favourited main characters. Clues go from vague to giving it away, and all
come from the graph: their best-known anime's year, genres, studio and source, a famous role of their voice actor,
the creator, the voice actor's name and finally the anime's title. A wrong guess reveals the next clue, and a wrong
guess with every clue showing ends the game. The score is how many clues were showing when the player got it.
"""
from __future__ import annotations

import random
import secrets
import threading
import time
from collections import deque
from typing import Any

from . import db, games

POOL = 300
MIN_CLUES = 6
TYPES = {"TV": "TV series", "Movie": "movie", "OVA": "OVA", "ONA": "web series", "Special": "special", "TV Special": "TV special"}
SOURCES = {
    "Manga": "a manga", "Light novel": "a light novel", "Web manga": "a web manga", "Novel": "a novel",
    "Visual novel": "a visual novel", "Game": "a game", "Video game": "a video game", "Web novel": "a web novel",
    "4-koma manga": "a four-panel manga", "Card game": "a card game", "Mixed media": "a mixed-media project",
}


def _list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _count(n: int) -> str:
    words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    return f"{words[n] if n < len(words) else n} anime"


def _voice(gender: str | None) -> dict[str, str]:
    if gender == "Female":
        return {"subj": "She", "poss": "Her", "is": "is", "s": "s"}
    if gender == "Male":
        return {"subj": "He", "poss": "His", "is": "is", "s": "s"}
    return {"subj": "They", "poss": "Their", "is": "are", "s": ""}


def clues_for(cid: int, franchise: dict[int, int]) -> list[str]:
    """Clues for one character, vaguest first. Clues the graph has no data for are left out."""
    rows = db.run(
        "MATCH (a:Anime)-[h:HAS_CHARACTER]->(c:Character {mal_id: $id}) "
        "RETURN c.gender AS gender, h.role = 'Main' AS main, a.mal_id AS id, a.title AS title, a.type AS type, a.year AS year, "
        "a.season AS season, a.aired_from AS aired, a.source AS source, coalesce(a.members, 0) AS members ORDER BY members DESC",
        id=cid,
    )
    if not rows:
        return []
    v = _voice(rows[0]["gender"])
    best = rows[0]  # their best-known anime, in any role
    mains = sum(1 for r in rows if r["main"])
    if mains == len(rows):
        clues = [f"{v['subj']} {v['is']} a main character in {_count(mains)}."]
    else:
        clues = [f"{v['subj']} {v['is']} a main character in {_count(mains)} and appear{v['s']} in {_count(len(rows))} in all."]
    year = best["year"] or (int(best["aired"][:4]) if best["aired"] else None)
    if year:
        kind = TYPES.get(best["type"] or "", "anime")
        when = f"{best['season'].capitalize()} {year}" if best["season"] else str(year)
        clues.append(f"{v['poss']} best-known anime is {'an' if kind[0] in 'AEIOU' else 'a'} {kind} from {when}.")

    genres = db.run(
        "MATCH (:Anime {mal_id: $a})-[:HAS_GENRE]->(g:Genre) WHERE g.kind IN ['genre', 'theme'] "
        "AND NOT g.name IN ['Hentai', 'Erotica', 'Ecchi'] RETURN g.name AS name ORDER BY g.kind, g.name LIMIT 3",
        a=best["id"],
    )
    if genres:
        clues.append(f"That anime is listed under {_list([g['name'] for g in genres])}.")
    studios = db.run("MATCH (:Anime {mal_id: $a})-[:PRODUCED_BY]->(s:Studio) RETURN s.name AS name", a=best["id"])
    if studios:
        source = SOURCES.get(best["source"] or "")
        based = f" It is based on {source}." if source else ""
        clues.append(f"It was animated by {_list([s['name'] for s in studios])}.{based}")

    own = {franchise.get(r["id"], r["id"]) for r in rows}
    va = db.run(
        "MATCH (p:Person)-[:VOICES {language: 'Japanese'}]->(:Character {mal_id: $id}) "
        "RETURN p.mal_id AS id, p.name AS name ORDER BY coalesce(p.favorites, 0) DESC LIMIT 1",
        id=cid,
    )
    if va:
        others = db.run(
            "MATCH (:Person {mal_id: $p})-[:VOICES {language: 'Japanese'}]->(o:Character)<-[:HAS_CHARACTER {role: 'Main'}]-(a:Anime) "
            "WHERE o.mal_id <> $id AND o.favorites IS NOT NULL "
            "RETURN o.name AS name, a.mal_id AS anime, a.title AS title ORDER BY o.favorites DESC, coalesce(a.members, 0) DESC LIMIT 20",
            p=va[0]["id"], id=cid,
        )
        other = next((o for o in others if franchise.get(o["anime"], o["anime"]) not in own), None)
        if other:
            clues.append(f"{v['poss']} Japanese voice actor also voices {games.natural(other['name'])} in {other['title']}.")

    staff = db.run(
        "MATCH (p:Person)-[w:WORKED_ON]->(:Anime {mal_id: $a}) WHERE 'Original Creator' IN w.positions OR 'Director' IN w.positions "
        "RETURN p.name AS name, 'Original Creator' IN w.positions AS creator ORDER BY creator DESC LIMIT 1",
        a=best["id"],
    )
    if staff:
        role = "created by" if staff[0]["creator"] else "directed by"
        clues.append(f"{v['poss']} story was {role} {games.natural(staff[0]['name'])}.")
    if va:
        clues.append(f"{v['subj']} {v['is']} voiced by {games.natural(va[0]['name'])} in Japanese.")
    clues.append(f"{v['subj']} appear{v['s']} in {best['title']}.")
    return clues


def make(rng: random.Random) -> dict[str, Any]:
    pool = games.popular_characters(POOL)
    if not pool:
        raise ValueError("the graph has no popular characters yet")
    franchise = games.franchises()
    best: tuple[int, list[str]] | None = None
    for cid in rng.sample(pool, min(30, len(pool))):
        clues = clues_for(cid, franchise)
        if len(clues) >= MIN_CLUES:
            return {"answer": cid, "clues": clues}
        if best is None or len(clues) > len(best[1]):
            best = (cid, clues)
    assert best
    return {"answer": best[0], "clues": best[1]}


def daily(day: str | None = None) -> dict[str, Any]:
    return games.daily("mystery", make, day)


def _new_play() -> dict[str, Any]:
    return {"clues": 1, "guesses": [], "solved": False, "done": False, "at": time.time()}


def state(username: str) -> tuple[dict[str, Any], dict[str, Any]]:
    puzzle = daily()
    return puzzle, games.my_play("mystery", puzzle["date"], username) or _new_play()


def apply(puzzle: dict[str, Any], play: dict[str, Any], action: str, guess: int | None = None) -> bool | None:
    """Apply "clue", "guess" or "give_up" to a play in place. Returns whether a guess was right."""
    total = len(puzzle["clues"])
    if play["done"]:
        return None
    if action == "clue":
        play["clues"] = min(total, play["clues"] + 1)
    elif action == "give_up":
        play["done"] = True
    elif action == "guess" and guess is not None:
        if guess in play["guesses"]:
            return None
        play["guesses"].append(guess)
        if guess == puzzle["answer"]:
            play["solved"] = play["done"] = True
            return True
        if play["clues"] >= total:
            play["done"] = True
        else:
            play["clues"] += 1
        return False
    return None


def act(username: str, action: str, guess: int | None = None) -> tuple[dict[str, Any], dict[str, Any], bool | None]:
    """Apply a move to the player's daily game. Returns the puzzle, the play and whether a guess was right."""
    puzzle = daily()
    correct: list[bool | None] = [None]

    def change(play: dict[str, Any] | None) -> dict[str, Any]:
        play = play or _new_play()
        correct[0] = apply(puzzle, play, action, guess)
        return play

    play = games.update_play("mystery", puzzle["date"], username, change)
    return puzzle, play, correct[0]


def summary(puzzle: dict[str, Any]) -> dict[str, Any]:
    done = [p for p in games.plays("mystery", puzzle["date"]).values() if p["done"]]
    solved = [p["clues"] for p in done if p["solved"]]
    return {"players": len(done), "solved": len(solved), "by_clues": games.histogram(solved)}


# --------------------------------------------------------------------------- from your own list

MINE_POOL = 150  # the most favourited main characters of the anime you've seen
MINE_TTL = 6 * 3600
RECENT = 30  # characters not to repeat for a player

_lock = threading.Lock()
_mine: dict[str, tuple[float, str, dict[str, Any], dict[str, Any]]] = {}  # token -> (expiry, user, puzzle, play)
_recent: dict[str, deque[int]] = {}


def _my_characters(username: str) -> list[int]:
    rows = db.run(
        "MATCH (:User {username: $user})-[l:LISTED]->(a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) "
        "WHERE l.status <> 'plan_to_watch' AND c.favorites IS NOT NULL "
        "WITH DISTINCT c ORDER BY c.favorites DESC LIMIT $n RETURN c.mal_id AS id",
        user=username, n=MINE_POOL,
    )
    return [r["id"] for r in rows]


def new_mine(username: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """A new game with a character from anime the player has seen. Raises ValueError if they have none."""
    pool = _my_characters(username)
    if not pool:
        raise ValueError("Your list has no characters yet. Sync your list, or play today's character instead.")
    with _lock:
        recent = set(_recent.get(username, ()))
    fresh = [c for c in pool if c not in recent] or pool
    rng = random.Random()
    franchise = games.recent_franchises()
    best: tuple[int, list[str]] | None = None
    for cid in rng.sample(fresh, min(15, len(fresh))):
        clues = clues_for(cid, franchise)
        if len(clues) >= MIN_CLUES:
            best = (cid, clues)
            break
        if best is None or len(clues) > len(best[1]):
            best = (cid, clues)
    assert best
    puzzle = {"date": "mine", "answer": best[0], "clues": best[1]}
    play = _new_play()
    token = secrets.token_urlsafe(12)
    now = time.time()
    with _lock:
        for t in [t for t, entry in _mine.items() if entry[0] < now]:
            del _mine[t]
        _mine[token] = (now + MINE_TTL, username, puzzle, play)
        _recent.setdefault(username, deque(maxlen=RECENT)).append(best[0])
    return token, puzzle, play


def act_mine(username: str, token: str, action: str, guess: int | None = None) -> tuple[dict[str, Any], dict[str, Any], bool | None] | None:
    """Apply a move to one of the player's own games. None if the game has expired or isn't theirs."""
    with _lock:
        entry = _mine.get(token)
        if not entry or entry[1] != username or entry[0] < time.time():
            return None
        _, _, puzzle, play = entry
        correct = apply(puzzle, play, action, guess)
        if play["done"]:
            del _mine[token]
    return puzzle, play, correct
