"""/api/match: taste match between two people who have both agreed to compare lists."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import match, users

router = APIRouter(prefix="/api/match")


def _user() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to compare lists.")
    return username


@router.get("")
def overview() -> dict[str, Any]:
    """Who you're linked with and how well your tastes match, plus your open invite link."""
    me = _user()
    out = []
    for link in match.links(me):
        result = match.compare(me, link["username"])
        out.append({**link, "match": result["match"], "shared": result["counts"]["shared"]})
    return {"links": out, "invite": match.my_invite(me), "invite_days": match.INVITE_DAYS}


@router.post("/invite")
def make_invite() -> dict[str, Any]:
    try:
        return match.invite(_user())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/invite")
def cancel_invite() -> Response:
    match.cancel_invite(_user())
    return Response(status_code=204)


@router.get("/invite/{token}")
def see_invite(token: str) -> dict[str, Any]:
    me = _user()
    maker = match.invite_from(token)
    if not maker:
        raise HTTPException(404, "This invite has expired or has already been used. Ask for a new link.")
    return {"from": maker, "own": maker.lower() == me.lower(), "linked": match.linked(me, maker) is not None}


@router.post("/invite/{token}")
def accept_invite(token: str) -> dict[str, Any]:
    try:
        return {"username": match.accept(token, _user())}
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/with/{username}")
def compare(username: str) -> dict[str, Any]:
    me = _user()
    other = match.linked(me, username)
    if not other:
        raise HTTPException(404, "You aren't linked with that person. Send them an invite link first.")
    return match.compare(me, other)


@router.delete("/with/{username}")
def unlink(username: str) -> Response:
    match.unlink(_user(), username)
    return Response(status_code=204)
