"""Who is asking, and what is on their list.

The graph itself is shared: anime, characters, people and studios are the same for every user. What is personal
lives only on (:User)-[:LISTED]->(:Anime). Queries that need "watched" or "same franchise as something I've seen"
take those sets as parameters ($watched, $franchise) for the current user, and serialisation adds the user's
status and score to each anime it returns.
"""
from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from . import db
from .config import settings

# Set per request by the API middleware (and inherited by threads started with asyncio.to_thread).
_current: ContextVar[str | None] = ContextVar("malgraph_user", default=None)


def current_username() -> str | None:
    return _current.get() or settings.mal_username or None


@contextmanager
def use_user(username: str | None) -> Iterator[None]:
    token = _current.set(username)
    try:
        yield
    finally:
        _current.reset(token)


class UserList:
    """One user's list, loaded once and cached. `franchise` (BFS over RELATED_TO) is computed on first use."""

    def __init__(self, username: str | None, rows: list[dict[str, Any]]) -> None:
        self.username = username
        self.entries: dict[int, tuple[str | None, int | None]] = {r["id"]: (r["status"], r["score"]) for r in rows}
        self.watched: list[int] = [i for i, (st, _) in self.entries.items() if st and st != "plan_to_watch"]
        self._franchise: list[int] | None = None
        self._lock = threading.Lock()

    @property
    def franchise(self) -> list[int]:
        """Every anime in the same franchise (sequel/prequel/side-story chains) as anything on the list."""
        with self._lock:
            if self._franchise is None:
                self._franchise = [] if not self.username else [r["id"] for r in db.run(FRANCHISE, user=self.username)]
            return self._franchise

    def personal(self, mal_id: int | None) -> tuple[str | None, int | None]:
        return self.entries.get(mal_id, (None, None)) if mal_id is not None else (None, None)


LIST = "MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) RETURN a.mal_id AS id, l.status AS status, l.score AS score"
FRANCHISE = """
    MATCH (u:User {username: $user})-[:LISTED]->(x:Anime)
    MATCH (x)-[:RELATED_TO *BFS 0..6 (r, n | r.relation <> 'Character')]-(f:Anime)
    RETURN DISTINCT f.mal_id AS id
"""

_TTL = 300  # seconds; a sync invalidates immediately, the TTL only guards against other writers
_cache: dict[str, tuple[float, UserList]] = {}
_cache_lock = threading.Lock()


def user_list(username: str | None = None) -> UserList:
    username = username or current_username()
    if not username:
        return UserList(None, [])
    with _cache_lock:
        hit = _cache.get(username)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]
    ul = UserList(username, db.run(LIST, user=username))
    with _cache_lock:
        _cache[username] = (time.time(), ul)
    return ul


def invalidate(username: str | None = None) -> None:
    with _cache_lock:
        if username is None:
            _cache.clear()
        else:
            _cache.pop(username, None)


_PARAM = {name: re.compile(rf"\${name}\b") for name in ("user", "watched", "franchise")}


def params_for(query: str) -> dict[str, Any]:
    """The per-user parameters this query refers to, filled in for the current user."""
    out: dict[str, Any] = {}
    if _PARAM["user"].search(query):
        out["user"] = current_username()
    if _PARAM["watched"].search(query):
        out["watched"] = user_list().watched
    if _PARAM["franchise"].search(query):
        out["franchise"] = user_list().franchise
    return out


def run(query: str, **params: Any) -> list[dict[str, Any]]:
    """db.run with $user / $watched / $franchise filled in for the current user (explicit params win)."""
    return db.run(query, **{**params_for(query), **params})
