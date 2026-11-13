"""Background fetching of listed anime from Jikan, shared by every user.

One worker thread keeps the load on Jikan/MAL predictable. It takes turns between users (round-robin), so a long list
that is still fetching doesn't hold up someone who just joined. The graph is shared, so an anime another user's job
already fetched is skipped, and each user's progress is tracked separately.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from . import db, ingest, users
from . import jikan
from .jikan import JikanError

log = logging.getLogger(__name__)
IDLE_EXIT = 30  # seconds the worker waits for new work before stopping


class FetchQueue:
    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._pending: dict[str, deque[int]] = {}
        self._order: deque[str] = deque()  # users with pending work, in turn order
        self._progress: dict[str, dict[str, Any]] = {}
        self._current: tuple[str, int] | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ public

    def enqueue(self, username: str, ids: list[int]) -> int:
        """Queue these anime for `username`. Returns how many were newly queued."""
        with self._cv:
            queue = self._pending.get(username)
            active = queue is not None or (self._current is not None and self._current[0] == username)
            seen = set(queue or ())
            new = [i for i in dict.fromkeys(ids) if i not in seen]
            if not new:
                return 0
            if active:
                self._progress[username]["total"] += len(new)
            else:
                self._progress[username] = {"total": len(new), "done": 0, "failed": [], "started_at": time.time(), "finished_at": None}
            if queue is None:
                self._pending[username] = queue = deque()
                self._order.append(username)
            queue.extend(new)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="fetch-queue", daemon=True)
                self._thread.start()
            self._cv.notify()
            return len(new)

    def status(self, username: str | None) -> dict[str, Any]:
        with self._cv:
            p = self._progress.get(username or "")
            running = bool(username) and (username in self._pending or (self._current is not None and self._current[0] == username))
            others = sum(1 for u in self._order if u != username)
            return {
                "running": running,
                "total": p["total"] if p else 0,
                "done": p["done"] if p else 0,
                "failed": list(p["failed"]) if p else [],
                "current": self._current[1] if running and self._current and self._current[0] == username else None,
                "others_in_queue": others,
            }

    # ------------------------------------------------------------------ worker

    def _next(self) -> tuple[str, int] | None:
        """Pop the next anime, taking turns between users. Caller holds the lock."""
        while self._order:
            username = self._order[0]
            self._order.rotate(-1)
            queue = self._pending.get(username)
            if queue:
                return username, queue.popleft()
            self._pending.pop(username, None)
            self._order.remove(username)
        return None

    def _run(self) -> None:
        while True:
            with self._cv:
                item = self._next()
                if item is None:
                    self._cv.wait(timeout=IDLE_EXIT)
                    item = self._next()
                    if item is None:
                        self._thread = None
                        return
                self._current = item
            username, mal_id = item
            error = self._fetch(mal_id)
            with self._cv:
                self._current = None
                p = self._progress[username]
                p["done"] += 1
                if error:
                    p["failed"].append({"mal_id": mal_id, "error": error})
                if not self._pending.get(username):
                    self._pending.pop(username, None)
                    if username in self._order:
                        self._order.remove(username)
                    p["finished_at"] = time.time()
                    users.invalidate(username)  # newly fetched relations can widen the franchise set

    def _fetch(self, mal_id: int) -> str | None:
        """Fetch one anime unless another user's job got there first. Returns an error message or None."""
        try:
            if db.run("MATCH (a:Anime {mal_id: $id}) WHERE a.fetched_at IS NOT NULL RETURN 1 AS x", id=mal_id):
                return None
            ingest.expand_anime(jikan.shared(), mal_id)
            return None
        except JikanError as e:
            return str(e)
        except Exception as e:  # keep the worker alive for everyone else
            log.exception("fetching anime %s failed", mal_id)
            return f"{type(e).__name__}: {e}"


queue = FetchQueue()
