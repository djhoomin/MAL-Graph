"""Jikan v4 client: on-disk cache, rate limiting (3/s, 60/min), retries on transient errors."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from .config import settings

TRANSIENT = {429, 500, 502, 503, 504}


class RateLimiter:
    """Sliding-window limiter honouring both per-second and per-minute caps."""

    def __init__(self, per_second: int = 3, per_minute: int = 60):
        self.per_second, self.per_minute = per_second, per_minute
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] > 60:
                    self.calls.popleft()
                last_sec = sum(1 for t in self.calls if now - t < 1.0)
                if len(self.calls) < self.per_minute and last_sec < self.per_second:
                    self.calls.append(now)
                    return
                oldest_min = self.calls[0] if self.calls else now
                sleep_for = 0.35 if last_sec >= self.per_second else max(0.05, 60 - (now - oldest_min))
            time.sleep(sleep_for)


class JikanError(RuntimeError):
    pass


class JikanClient:
    def __init__(self, cache_dir: Path | None = None, max_retries: int = 6):
        self.base = settings.jikan_base.rstrip("/")
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = RateLimiter()
        self.max_retries = max_retries
        self.http = httpx.Client(timeout=30, headers={"User-Agent": "mal-graph/0.1", "Accept-Encoding": "gzip"})
        self.stats = {"hits": 0, "requests": 0}

    def _cache_path(self, path: str, params: dict[str, Any] | None) -> Path:
        key = path.strip("/") + ("?" + json.dumps(params, sort_keys=True) if params else "")
        digest = hashlib.sha1(key.encode()).hexdigest()[:12]
        safe = key.replace("/", "_").replace("?", "_").replace("=", "-")[:80]
        return self.cache_dir / f"{safe}_{digest}.json"

    def get(self, path: str, params: dict[str, Any] | None = None, *, refresh: bool = False) -> dict[str, Any]:
        """GET /v4/{path}; returns the parsed JSON body. Cached forever unless refresh=True."""
        cache = self._cache_path(path, params)
        if cache.exists() and not refresh:
            self.stats["hits"] += 1
            return json.loads(cache.read_text())

        url = f"{self.base}/{path.lstrip('/')}"
        delay = 1.0
        for attempt in range(self.max_retries):
            self.limiter.wait()
            self.stats["requests"] += 1
            try:
                resp = self.http.get(url, params=params)
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise JikanError(f"{url}: {e}") from e
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue

            if resp.status_code == 200:
                body = resp.json()
                cache.write_text(json.dumps(body))
                return body
            if resp.status_code == 404:
                raise JikanError(f"{url}: 404 not found")
            if resp.status_code in TRANSIENT:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                time.sleep(wait)
                delay = min(delay * 2, 30)
                continue
            raise JikanError(f"{url}: HTTP {resp.status_code}: {resp.text[:200]}")
        raise JikanError(f"{url}: gave up after {self.max_retries} attempts")

    def get_paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Collect `data` across all pages for list endpoints."""
        params = dict(params or {})
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self.get(path, {**params, "page": page})
            items.extend(body.get("data", []))
            if not body.get("pagination", {}).get("has_next_page"):
                return items
            page += 1

    # Convenience wrappers
    def anime_full(self, mal_id: int) -> dict[str, Any]:
        return self.get(f"anime/{mal_id}/full")["data"]

    def anime_characters(self, mal_id: int) -> list[dict[str, Any]]:
        return self.get(f"anime/{mal_id}/characters")["data"]

    def anime_staff(self, mal_id: int) -> list[dict[str, Any]]:
        return self.get(f"anime/{mal_id}/staff")["data"]

    def person_full(self, mal_id: int) -> dict[str, Any]:
        return self.get(f"people/{mal_id}/full")["data"]

    def character_full(self, mal_id: int) -> dict[str, Any]:
        return self.get(f"characters/{mal_id}/full")["data"]
