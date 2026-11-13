"""/api/golf: the daily hole, practice holes, legal moves, and finished rounds."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import golf, users
from . import routes as R
from .serialize import PayloadBuilder, node_payload

router = APIRouter(prefix="/api/golf")
PRACTICE_COOLDOWN = 5  # seconds between new practice holes per user
_last_practice: dict[str, float] = {}


def _user() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    return username


def _node(ref: str) -> dict[str, Any]:
    label, key = golf.parse(ref)
    return node_payload(R._node(label, key))


def _public(hole: dict[str, Any]) -> dict[str, Any]:
    """What a player sees before finishing: tee, hole and par (not the shortest length)."""
    return {"date": hole.get("date"), "par": hole["par"], "start": _node(hole["start"]), "end": _node(hole["end"])}


def _solution(start: str, end: str) -> dict[str, Any]:
    path = golf.shortest_path(start, end)
    if path is None:
        return {"nodes": [], "edges": [], "paths": []}
    builder = PayloadBuilder()
    builder.add(path)
    return builder.build(paths=[[R.node_id_of(n) for n in path.nodes]])


class Round(BaseModel):
    moves: list[str] = Field(min_length=1, max_length=golf.MAX_MOVES + 1)
    mulligans: int = Field(0, ge=0, le=1)
    gave_up: bool = False


class PracticeRound(Round):
    start: str
    end: str


@router.get("/moves/{ref}")
def moves(ref: str) -> dict[str, Any]:
    """Every node one golf move away (all of them, so the right move is never cut off)."""
    try:
        golf.parse(ref)
    except golf.GolfError as e:
        raise HTTPException(400, str(e))
    return R.neighbors(ref, rels=",".join(golf.RELS), lang=golf.LANG, limit=2000)


@router.get("/daily")
async def daily() -> dict[str, Any]:
    username = _user()
    try:
        hole = await run_in_threadpool(golf.daily_hole)
    except golf.GolfError as e:
        raise HTTPException(503, str(e))
    out = await run_in_threadpool(_public, hole)
    mine = golf.my_round(hole["date"], username)
    if mine:  # already played today: show the result again
        out["round"] = mine
        out["shortest"] = hole["shortest"]
        out["summary"] = golf.summary(hole["date"], username, hole["par"])
        out["solution"] = await run_in_threadpool(_solution, hole["start"], hole["end"])
    return out


@router.post("/daily")
async def play_daily(body: Round) -> dict[str, Any]:
    username = _user()
    hole = await run_in_threadpool(golf.daily_hole)
    if body.gave_up:
        if body.moves[0] != hole["start"]:
            raise HTTPException(400, "a round must start at the tee")
        entry = {"strokes": len(body.moves) - 1, "mulligans": body.mulligans, "gave_up": True, "moves": body.moves}
    else:
        try:
            strokes = await run_in_threadpool(golf.check_round, hole, body.moves)
        except golf.GolfError as e:
            raise HTTPException(400, str(e))
        entry = {"strokes": strokes, "mulligans": body.mulligans, "gave_up": False, "moves": body.moves}
    counted = golf.record(hole["date"], username, entry)
    return {
        "round": counted,
        "first_round": counted["moves"] == entry["moves"] and counted.get("gave_up") == entry["gave_up"],
        "par": hole["par"],
        "shortest": hole["shortest"],
        "summary": golf.summary(hole["date"], username, hole["par"]),
        "solution": await run_in_threadpool(_solution, hole["start"], hole["end"]),
    }


@router.get("/practice")
async def practice() -> dict[str, Any]:
    username = _user()
    wait = PRACTICE_COOLDOWN - (time.time() - _last_practice.get(username.lower(), 0))
    if wait > 0:
        raise HTTPException(429, f"Wait {int(wait) + 1} seconds for another practice hole.")
    _last_practice[username.lower()] = time.time()
    try:
        hole = await run_in_threadpool(golf.practice_hole)
    except golf.GolfError as e:
        raise HTTPException(503, str(e))
    return await run_in_threadpool(_public, hole)


@router.post("/practice")
async def finish_practice(body: PracticeRound) -> dict[str, Any]:
    _user()
    hole = {"start": body.start, "end": body.end}
    try:
        golf.parse(body.start), golf.parse(body.end)
        if not body.gave_up:
            await run_in_threadpool(golf.check_round, hole, body.moves)
    except golf.GolfError as e:
        raise HTTPException(400, str(e))
    solution = await run_in_threadpool(_solution, body.start, body.end)
    return {"shortest": len(solution["paths"][0]) - 1 if solution["paths"] else None, "solution": solution}
