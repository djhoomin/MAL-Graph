"""Per-user limits on "Ask the graph": a daily question allowance and one question at a time.

Usage is kept next to the user's conversations (CONV_DIR/<user>/usage.json), so it survives restarts.
Days are UTC. The owner (MAL_USERNAME) and anyone in ASK_UNLIMITED_USERS have no daily cap.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import settings


class LimitReached(RuntimeError):
    pass


STALE = 600  # seconds after which a slot counts as abandoned (an answer never takes this long)
_lock = threading.Lock()
_in_flight: dict[str, float] = {}  # user -> when their current question started


def _path(username: str) -> Path:
    return settings.conversations_dir / username.lower() / "usage.json"


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _load(username: str) -> dict[str, Any]:
    try:
        usage = json.loads(_path(username).read_text())
    except (OSError, json.JSONDecodeError):
        usage = {}
    if usage.get("day") != _today():
        usage = {"day": _today(), "questions": 0, "prompt_tokens": 0, "completion_tokens": 0}
    return usage


def _save(username: str, usage: dict[str, Any]) -> None:
    path = _path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(usage))
    tmp.replace(path)


def daily_limit(username: str) -> int | None:
    """Questions per day for this user, or None for no cap."""
    unlimited = {u.strip().lower() for u in settings.ask_unlimited_users.split(",") if u.strip()}
    if settings.mal_username:
        unlimited.add(settings.mal_username.lower())
    if username.lower() in unlimited or settings.ask_daily_limit <= 0:
        return None
    return settings.ask_daily_limit


def remaining(username: str) -> int | None:
    limit = daily_limit(username)
    if limit is None:
        return None
    with _lock:
        return max(0, limit - _load(username)["questions"])


@contextmanager
def ask_slot(username: str) -> Iterator[dict[str, int]]:
    """Hold the user's one question slot and count the question. Yields a dict to add token usage to."""
    key = username.lower()
    with _lock:
        if time.time() - _in_flight.get(key, 0) < STALE:
            raise LimitReached("Your previous question is still being answered. Wait for it to finish, or stop it first.")
        usage = _load(username)
        limit = daily_limit(username)
        if limit is not None and usage["questions"] >= limit:
            raise LimitReached(f"You have used all {limit} questions for today. The allowance resets at midnight UTC.")
        usage["questions"] += 1
        _save(username, usage)
        _in_flight[key] = time.time()
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        yield tokens
    finally:
        with _lock:
            _in_flight.pop(key, None)
            usage = _load(username)
            usage["prompt_tokens"] += tokens["prompt_tokens"]
            usage["completion_tokens"] += tokens["completion_tokens"]
            _save(username, usage)
