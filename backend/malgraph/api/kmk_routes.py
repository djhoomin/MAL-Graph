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
    """A random theme with its character pool (or a named one: kind=va&key=7263). `avoid` is a comma-separated list of
    recent themes (kind:key, most recent last), which are skipped, and whose kinds are tried last.
    `gender` (Female, Male) keeps only characters recorded with that gender."""
    if not users.current_username():
        raise HTTPException(401, "Sign in to play")
    if gender not in (None, "", *genders.GENDERS):
        raise HTTPException(400, "unknown gender filter")
    parsed: Any = int(key) if key and key.isdigit() else key
    out = await run_in_threadpool(kmk.theme, avoid, kind, parsed, gender or None)
    if not out or len(out["pool"]) < 3:
        raise HTTPException(404, "There aren't enough characters for a round with these settings. Try another filter, or sync your list.")
    return out


class GenderFix(BaseModel):
    gender: str | None  # one of genders.GENDERS, or null for unknown


@router.post("/character/{character_id}/gender")
async def fix_gender(character_id: int, body: GenderFix) -> dict[str, Any]:
    """Correct a character's gender. The fix is shared, and AniList updates never overwrite it."""
    if not users.current_username():
        raise HTTPException(401, "Sign in to make corrections")
    if body.gender is not None and body.gender not in genders.GENDERS:
        raise HTTPException(400, "unknown gender")
    if not await run_in_threadpool(genders.correct, character_id, body.gender):
        raise HTTPException(404, "character not found")
    return {"id": character_id, "gender": body.gender}


def _daily_view(username: str) -> dict[str, Any]:
    try:
        puzzle = kmk.daily()
    except ValueError as e:
        raise HTTPException(503, str(e))
    play = games.my_play("kmk", puzzle["date"], username)
    out: dict[str, Any] = {"date": puzzle["date"], "title": puzzle["title"], "cards": games.character_cards(puzzle["cards"])}
    if play:
        out["choices"] = play["choices"]
        out["round_id"] = play.get("round_id")
        out["rescued"] = kmk.was_rescued(username, play.get("round_id"))
        out["tally"] = kmk.tally(puzzle)
    return out


@router.get("/daily")
async def daily() -> dict[str, Any]:
    """Today's three, the same for everyone. After playing, also your choices and everyone's tally."""
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to play")
    return await run_in_threadpool(_daily_view, username)


class DailyChoices(BaseModel):
    choices: dict[str, str]  # character id -> kiss, marry or kill


@router.post("/daily")
async def play_daily(body: DailyChoices) -> dict[str, Any]:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to play")
    try:
        await run_in_threadpool(kmk.play_daily, username, body.choices)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await run_in_threadpool(_daily_view, username)


def _player() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to play")
    return username


class FinishedRound(BaseModel):
    title: str
    choices: dict[str, str]  # character id -> kiss, marry or kill


@router.post("/rounds")
async def finish_round(body: FinishedRound) -> dict[str, Any]:
    """Add a round played from your own list to your history. Daily rounds are added when you lock them in."""
    username = _player()
    try:
        rid = await run_in_threadpool(kmk.record_round, username, body.title, "theme", body.choices)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"round_id": rid}


@router.post("/rounds/{round_id}/rescue")
async def rescue(round_id: str) -> dict[str, Any]:
    """Put the round's killed character in your terrarium instead."""
    username = _player()
    try:
        killed = await run_in_threadpool(kmk.rescue, username, round_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"rescued": killed}


@router.get("/history")
async def history() -> dict[str, Any]:
    """Your harem, hookups, graveyard and terrarium, from every round you've finished."""
    return await run_in_threadpool(kmk.history, _player())
