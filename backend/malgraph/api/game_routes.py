"""/api/odd and /api/mystery: Odd one out and Mystery character. Daily Kiss Marry Kill lives in kmk_routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import games, mystery, odd, users

router = APIRouter()


def _user() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in with MyAnimeList to play")
    return username


class Pick(BaseModel):
    pick: int


# --------------------------------------------------------------------------- Odd one out

def _odd_daily(username: str) -> dict[str, Any]:
    puzzle = odd.daily()
    rounds = puzzle["rounds"]
    if not rounds:
        raise HTTPException(503, "The graph is too small for Odd one out yet")
    play = games.my_play("odd", puzzle["date"], username)
    picks = play["picks"] if play else [None] * len(rounds)
    out: dict[str, Any] = {
        "date": puzzle["date"],
        "rounds": [
            {"cards": games.character_cards(r["cards"], r.get("shown")), **({"result": odd.reveal(puzzle, i, picks[i])} if picks[i] is not None else {})}
            for i, r in enumerate(rounds)
        ],
    }
    if all(p is not None for p in picks):
        out["summary"] = odd.summary(puzzle)
    return out


@router.get("/api/odd/daily")
async def odd_daily() -> dict[str, Any]:
    return await run_in_threadpool(_odd_daily, _user())


@router.post("/api/odd/daily/{index}")
async def odd_answer(index: int, body: Pick) -> dict[str, Any]:
    username = _user()
    try:
        result = await run_in_threadpool(odd.answer_daily, username, index, body.pick)
    except ValueError as e:
        raise HTTPException(400, str(e))
    puzzle = odd.daily()
    play = games.my_play("odd", puzzle["date"], username)
    done = bool(play) and all(p is not None for p in play["picks"])
    return {"result": result, **({"summary": odd.summary(puzzle)} if done else {})}


@router.get("/api/odd/practice")
async def odd_practice() -> dict[str, Any]:
    _user()
    rnd = await run_in_threadpool(odd.practice_round)
    if not rnd:
        raise HTTPException(503, "The graph is too small for Odd one out yet")
    return {"token": rnd["token"], "cards": await run_in_threadpool(games.character_cards, rnd["cards"], rnd.get("shown"))}


class PracticePick(Pick):
    token: str


@router.post("/api/odd/practice")
def odd_practice_answer(body: PracticePick) -> dict[str, Any]:
    _user()
    result = odd.answer_practice(body.token, body.pick)
    if not result:
        raise HTTPException(410, "That round has expired. Here's a new one.")
    return {"result": result}


# --------------------------------------------------------------------------- Mystery character

def _mystery_view(puzzle: dict[str, Any], play: dict[str, Any], correct: bool | None = None) -> dict[str, Any]:
    clues = mystery.sequence(puzzle, play)
    out: dict[str, Any] = {
        "date": puzzle["date"],
        "total": len(clues),
        "clues": clues[: play["clues"]],
        "branch": play.get("branch"),  # how many anime clues came before the character clues, once they took over
        "used": play["clues"],  # clues shown when the game ended, for the score
        "guesses": [c["character"] for c in games.character_cards(play["guesses"])],
        "right_anime": mystery.right_anime(puzzle["answer"], play["guesses"]),  # wrong guesses from the answer's anime
        "solved": play["solved"],
        "done": play["done"],
    }
    if correct is not None:
        out["correct"] = correct
    if play["done"]:
        out["clues"] = clues
        out["answer"] = games.character_cards([puzzle["answer"]])[0]
        if puzzle["date"] != "mine":  # games from your own list have no one to compare with
            out["summary"] = mystery.summary(puzzle)
    return out


@router.get("/api/mystery/daily")
async def mystery_daily() -> dict[str, Any]:
    username = _user()
    try:
        puzzle, play = await run_in_threadpool(mystery.state, username)
    except ValueError as e:
        raise HTTPException(503, str(e))
    return await run_in_threadpool(_mystery_view, puzzle, play)


class MysteryMove(BaseModel):
    action: str  # "clue", "guess" or "give_up"
    guess: int | None = None


@router.post("/api/mystery/daily")
async def mystery_move(body: MysteryMove) -> dict[str, Any]:
    username = _user()
    if body.action not in ("clue", "guess", "give_up") or (body.action == "guess" and body.guess is None):
        raise HTTPException(400, "unknown move")
    puzzle, play, correct = await run_in_threadpool(mystery.act, username, body.action, body.guess)
    return await run_in_threadpool(_mystery_view, puzzle, play, correct)


@router.get("/api/mystery/mine")
async def mystery_mine() -> dict[str, Any]:
    """A new game with a character from the player's own list."""
    username = _user()
    try:
        token, puzzle, play = await run_in_threadpool(mystery.new_mine, username)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {**(await run_in_threadpool(_mystery_view, puzzle, play)), "token": token}


class MineMove(MysteryMove):
    token: str


@router.post("/api/mystery/mine")
async def mystery_mine_move(body: MineMove) -> dict[str, Any]:
    username = _user()
    if body.action not in ("clue", "guess", "give_up") or (body.action == "guess" and body.guess is None):
        raise HTTPException(400, "unknown move")
    moved = await run_in_threadpool(mystery.act_mine, username, body.token, body.action, body.guess)
    if moved is None:
        raise HTTPException(410, "This game has expired. Start a new one.")
    puzzle, play, correct = moved
    return {**(await run_in_threadpool(_mystery_view, puzzle, play, correct)), "token": body.token}
