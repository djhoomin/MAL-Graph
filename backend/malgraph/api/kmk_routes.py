"""/api/kmk: Kiss Marry Kill themes from the player's own graph."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import games, genders, kmk, users

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


def _daily_view(username: str) -> dict[str, Any]:
    try:
        puzzle = kmk.daily()
    except ValueError as e:
        raise HTTPException(503, str(e))
    play = games.my_play("kmk", puzzle["date"], username)
    out: dict[str, Any] = {"date": puzzle["date"], "title": puzzle["title"], "cards": games.character_cards(puzzle["cards"])}
    if play:
        out["choices"] = play["choices"]
        out["tally"] = kmk.tally(puzzle)
    return out


@router.get("/daily")
async def daily() -> dict[str, Any]:
    """Today's three, the same for everyone. After playing, also your choices and everyone's tally."""
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    return await run_in_threadpool(_daily_view, username)


class DailyChoices(BaseModel):
    choices: dict[str, str]  # character id -> kiss, marry or kill


@router.post("/daily")
async def play_daily(body: DailyChoices) -> dict[str, Any]:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    try:
        await run_in_threadpool(kmk.play_daily, username, body.choices)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await run_in_threadpool(_daily_view, username)
