"""/api/kmk: Kiss Marry Kill themes from the player's own graph."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import genders, kmk, users

router = APIRouter(prefix="/api/kmk")


@router.get("/theme")
async def theme(avoid: str | None = None, kind: str | None = None, key: str | None = None, gender: str | None = None) -> dict[str, Any]:
    """A random theme with its character pool (or a named one: kind=va&key=7263). `avoid` skips the current theme.
    `gender` (Female, Male) keeps only characters recorded with that gender."""
    if not users.current_username():
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    if gender not in (None, "", *genders.GENDERS):
        raise HTTPException(400, "unknown gender filter")
    parsed: Any = int(key) if key and key.isdigit() else key
    out = await run_in_threadpool(kmk.theme, avoid, kind, parsed, gender or None)
    if not out or len(out["pool"]) < 3:
        raise HTTPException(404, "There aren't enough characters for a round with these settings. Try another filter, or sync your list.")
    return out


class GenderFix(BaseModel):
    gender: str | None  # one of genders.GENDERS, or null for unknown


@router.post("/character/{mal_id}/gender")
async def fix_gender(mal_id: int, body: GenderFix) -> dict[str, Any]:
    """Correct a character's gender. The fix is shared, and AniList updates never overwrite it."""
    if not users.current_username():
        raise HTTPException(401, "Sign in with MyAnimeList to make corrections")
    if body.gender is not None and body.gender not in genders.GENDERS:
        raise HTTPException(400, "unknown gender")
    if not await run_in_threadpool(genders.correct, mal_id, body.gender):
        raise HTTPException(404, "character not found")
    return {"mal_id": mal_id, "gender": body.gender}
