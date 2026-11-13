"""/api/auth: sign in with MyAnimeList, sign out, and who is signed in."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .. import auth, privacy, users
from ..config import settings
from .routes import sync_user

router = APIRouter(prefix="/api/auth")


def _home(**params: str) -> RedirectResponse:
    """Back to the app, optionally with ?auth_error=<code>. The app words each code itself, so a crafted link
    can't put text of its own on the page."""
    return RedirectResponse(f"{settings.public_url or ''}/" + (f"?{urlencode(params)}" if params else ""), status_code=303)


@router.get("/me")
def me() -> dict[str, Any]:
    return {"username": users.current_username(), "sign_in": settings.sign_in, "contact": settings.privacy_contact or None}


@router.delete("/account")
async def delete_account() -> Response:
    """Delete everything stored about the signed-in user, then sign them out."""
    username = users.current_username()
    if not username or not settings.sign_in:
        raise HTTPException(401, "Sign in to delete your data")
    await run_in_threadpool(privacy.delete_user, username)
    resp = Response(status_code=204)
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


@router.get("/login")
def login() -> RedirectResponse:
    if not settings.sign_in:
        raise HTTPException(404, "Sign-in is not configured on this server")
    url, attempt = auth.start()
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(auth.OAUTH_COOKIE, attempt, **auth.cookie_options(auth.OAUTH_MINUTES * 60, path="/api/auth"))
    return resp


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error or not code or not state:
        # "access_denied" when the user clicks Cancel on MAL's consent page
        return _home(auth_error="cancelled" if error == "access_denied" else "incomplete")
    try:
        username, token = await run_in_threadpool(auth.finish, code, state, request.cookies.get(auth.OAUTH_COOKIE))
    except auth.AuthError as e:
        return _home(auth_error=e.code)

    username = await run_in_threadpool(users.canonical, username)
    # Read the list now, while we hold a token that can see it even if it is private.
    params: dict[str, str] = {"signed_in": "1"}
    try:
        with users.use_user(username):
            await run_in_threadpool(sync_user, username, token)
    except HTTPException as e:
        if e.status_code != 429:  # a sync a moment ago already did the job
            params["auth_error"] = "list"
    resp = _home(**params)
    resp.set_cookie(auth.SESSION_COOKIE, auth.session_value(username), **auth.cookie_options(auth.SESSION_DAYS * 86400))
    resp.delete_cookie(auth.OAUTH_COOKIE, path="/api/auth")
    return resp


@router.post("/logout")
def logout() -> Response:
    resp = Response(status_code=204)
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp
