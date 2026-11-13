"""Per-visitor request limits, so one person (or script) can't hog the server or the MAL fetch queue.

A visitor is their MAL username when signed in, otherwise their IP address (Caddy passes it on and uvicorn runs with
--proxy-headers). Each rule is a sliding window: at most `limit` requests per `window` seconds. A request counts
against the first rule whose method and path prefix match, and also against the overall cap.
Limits live in memory, which is fine for one API process. They reset when the API restarts.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

from .. import users


@dataclass(frozen=True)
class Rule:
    name: str
    method: str | None  # None matches any method
    prefix: str
    limit: int
    window: int  # seconds


RULES = [
    Rule("sign-in", None, "/api/auth/login", 10, 60),
    Rule("sign-in", None, "/api/auth/callback", 10, 60),
    Rule("expand", "POST", "/api/expand/", 40, 60),  # may fetch from MAL
    Rule("path", "GET", "/api/path", 30, 60),
    Rule("golf", "GET", "/api/golf/moves/", 120, 60),
    Rule("search", "GET", "/api/search", 120, 60),
]
OVERALL = Rule("overall", None, "/api/", 600, 60)
ANONYMOUS = Rule("overall", None, "/api/", 120, 60)  # visitors who haven't signed in


class Limiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def hit(self, key: str, rule: Rule) -> float:
        """Record a request. Returns 0 if allowed, otherwise the seconds until the next one would be."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault((key, rule.name), deque())
            while q and now - q[0] >= rule.window:
                q.popleft()
            if len(q) >= rule.limit:
                return rule.window - (now - q[0])
            q.append(now)
            if now - self._last_sweep > 300:  # forget visitors who have gone quiet
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < 600}
                self._last_sweep = now
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = Limiter()


class RateLimitMiddleware:
    """Must run inside UserMiddleware, so the signed-in user is known."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        username = users.current_username()
        client = scope.get("client")
        key = f"user:{username.lower()}" if username else f"ip:{client[0] if client else 'unknown'}"
        rules = [r for r in RULES if path.startswith(r.prefix) and (r.method is None or r.method == scope.get("method"))][:1]
        rules.append(OVERALL if username else ANONYMOUS)
        for rule in rules:
            wait = limiter.hit(key, rule)
            if wait:
                await _too_many(send, wait)
                return
        await self.app(scope, receive, send)


async def _too_many(send: Send, wait: float) -> None:
    seconds = int(wait) + 1
    body = json.dumps({"detail": f"Too many requests. Try again in {seconds} seconds."}).encode()
    await send({
        "type": "http.response.start",
        "status": 429,
        "headers": [(b"content-type", b"application/json"), (b"retry-after", str(seconds).encode()), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})
