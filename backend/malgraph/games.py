"""Shared storage for the daily games (Odd one out, Mystery character, Daily Kiss Marry Kill and Yay or Nay).

Each game has one puzzle per UTC day, made from the date as a random seed and saved so it stays the same all day
even as the graph grows. Each player's play of the day is stored per game and day under their username, so it can
be deleted with their data. Results shown to players are counts only and never name anyone.
Files live next to Graph Golf's in GOLF_DIR (data/golf), which the nightly backup already includes.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import db
from .config import settings

GAMES = ("odd", "mystery", "kmk", "yay")

_make_locks = {g: threading.Lock() for g in GAMES}  # one puzzle is made at a time per game
_play_lock = threading.Lock()


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _dir(game: str, kind: str) -> Path:
    path = settings.golf_dir / game / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def daily(game: str, make: Callable[[random.Random], dict[str, Any]], day: str | None = None) -> dict[str, Any]:
    """The day's puzzle for a game, made on first request from a date-seeded random generator. It is saved with the
    main anime titles, whoever asks first, and shown with English ones to viewers who chose them."""
    day = day or today()
    path = _dir(game, "puzzles") / f"{day}.json"
    puzzle = _read(path)
    if not puzzle:
        with _make_locks[game]:
            puzzle = _read(path)  # another request may have made it while this one waited
            if not puzzle:
                with db.use_english_titles(False):
                    puzzle = {"date": day, **make(random.Random(f"mal-graph-{game}-{day}"))}
                _write(path, puzzle)
    return english(puzzle, f"{game}:{day}")


ENGLISH_FOR = """
UNWIND $strings AS s
MATCH (a:Anime) WHERE a.title_english IS NOT NULL AND a.title_english <> a.title AND size(a.title) >= 3
  AND s CONTAINS a.title
RETURN a.title AS title, a.title_english AS english ORDER BY coalesce(a.members, 0) DESC
"""
_english_swaps: dict[str, dict[str, str]] = {}
SKIP_KEYS = {"href", "url", "image_url"}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in SKIP_KEYS for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def english(puzzle: dict[str, Any], key: str) -> dict[str, Any]:
    """A saved puzzle with the anime titles in its text swapped for English ones, when the viewer chose English.
    Odd one out and Mystery character write titles into their cards and clues, so the swap finds the main titles
    that appear as whole words in the puzzle's strings, longest first, in one pass. Swaps are kept per puzzle."""
    if not db.english_titles():
        return puzzle
    swaps = _english_swaps.get(key)
    if swaps is None:
        swaps = {}
        for r in db.run(ENGLISH_FOR, strings=sorted(set(_strings(puzzle)))):
            swaps.setdefault(r["title"], r["english"])  # the most-watched anime of a shared title wins
        if len(_english_swaps) > 50:
            _english_swaps.clear()
        _english_swaps[key] = swaps
    if not swaps:
        return puzzle
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in sorted(swaps, key=len, reverse=True)) + r")(?!\w)")

    def swap(value: Any) -> Any:
        if isinstance(value, str):
            return pattern.sub(lambda m: swaps[m.group(1)], value)
        if isinstance(value, dict):
            return {k: v if k in SKIP_KEYS else swap(v) for k, v in value.items()}
        if isinstance(value, list):
            return [swap(v) for v in value]
        return value

    return swap(puzzle)


def plays(game: str, day: str) -> dict[str, Any]:
    """Every player's play of the day, keyed by lower-case username."""
    return _read(_dir(game, "plays") / f"{day}.json") or {}


def my_play(game: str, day: str, username: str) -> dict[str, Any] | None:
    return plays(game, day).get(username.lower())


def update_play(game: str, day: str, username: str, change: Callable[[dict[str, Any] | None], dict[str, Any]]) -> dict[str, Any]:
    """Read, change and save one player's play under a lock, so two requests can't overwrite each other."""
    with _play_lock:
        path = _dir(game, "plays") / f"{day}.json"
        everyone = _read(path) or {}
        play = change(everyone.get(username.lower()))
        everyone[username.lower()] = play
        _write(path, everyone)
        return play


def forget(username: str) -> int:
    """Remove a user's plays from every game and day. Returns how many were removed."""
    key, removed = username.lower(), 0
    with _play_lock:
        for game in GAMES:
            for path in _dir(game, "plays").glob("*.json"):
                everyone = _read(path)
                if everyone and everyone.pop(key, None) is not None:
                    _write(path, everyone)
                    removed += 1
    return removed


def histogram(values: list[int]) -> list[dict[str, int]]:
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return [{"value": k, "players": n} for k, n in sorted(counts.items())]


def character_cards(ids: list[int], shown: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Cards for characters in the given order: the API's node shape plus the title of their best-known anime, or
    of the anime in `shown` (by character id). The shape matches Kiss Marry Kill's, so the UI can reuse its cards."""
    from .api.serialize import node_payload  # imported late: the API package imports the game modules

    with db.get_driver().session() as session:
        rows = list(session.run(
            "MATCH (c:Character) WHERE c.id IN $ids "
            "OPTIONAL MATCH (a:Anime)-[h:HAS_CHARACTER]->(c) "
            "WITH c, a ORDER BY CASE WHEN a IS NULL THEN 0 ELSE coalesce(a.members, 0) END DESC "
            f"RETURN c, collect({db.title('a')}) AS anime",
            ids=ids, **db.title_params(db.title("a")),
        ))
    by_id = {r["c"]["id"]: r for r in rows}
    shown = shown or {}
    return [
        {"character": node_payload(by_id[i]["c"]), "anime": [shown[str(i)]] if str(i) in shown else by_id[i]["anime"][:1], "main": True}
        for i in ids if i in by_id
    ]


def popular_characters(limit: int) -> list[int]:
    """The most favourited main characters of fully fetched anime, most popular first."""
    from . import db

    rows = db.run(
        # Cypher sorts missing values first when descending, so leave out characters without a count.
        "MATCH (a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(c:Character) WHERE a.fetched_at IS NOT NULL AND c.favorites IS NOT NULL "
        "WITH DISTINCT c ORDER BY c.favorites DESC LIMIT $n RETURN c.id AS id",
        n=limit,
    )
    return [r["id"] for r in rows]


def franchises() -> dict[int, int]:
    """Anime id -> franchise id, joining sequels, prequels, side stories and the like. Crossovers ("Other" and
    "Character" relations) don't join franchises. Anime without relations are missing and are their own franchise."""
    from . import db

    parent: dict[int, int] = {}

    def root(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rows = db.run("MATCH (a:Anime)-[r:RELATED_TO]->(b:Anime) WHERE NOT r.relation IN ['Other', 'Character'] RETURN a.id AS a, b.id AS b")
    for r in rows:
        parent[root(r["a"])] = root(r["b"])
    return {x: root(x) for x in parent}


_franchise_cache: tuple[float, dict[int, int]] | None = None
FRANCHISE_TTL = 600


def recent_franchises() -> dict[int, int]:
    """franchises(), reused for FRANCHISE_TTL seconds, for features that run on demand."""
    global _franchise_cache
    cached = _franchise_cache
    if cached and time.time() - cached[0] < FRANCHISE_TTL:
        return cached[1]
    fresh = franchises()
    _franchise_cache = (time.time(), fresh)
    return fresh


def natural(name: str | None) -> str:
    """MyAnimeList writes people as "Last, First". Sentences read better as "First Last"."""
    if name and name.count(",") == 1:
        last, first = (s.strip() for s in name.split(","))
        return f"{first} {last}" if first and last else name
    return name or ""
