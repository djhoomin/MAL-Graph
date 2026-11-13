"""/api/kmk: Kiss Marry Kill themes from the player's own graph."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from .. import kmk, users

router = APIRouter(prefix="/api/kmk")


@router.get("/theme")
async def theme(avoid: str | None = None, kind: str | None = None, key: str | None = None) -> dict[str, Any]:
    """A random theme with its character pool (or a named one: kind=va&key=7263). `avoid` skips the current theme."""
    if not users.current_username():
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    parsed: Any = int(key) if key and key.isdigit() else key
    out = await run_in_threadpool(kmk.theme, avoid, kind, parsed)
    if not out or len(out["pool"]) < 3:
        raise HTTPException(404, "Your list doesn't have enough characters for a round yet. Sync your list and try again.")
    return out
