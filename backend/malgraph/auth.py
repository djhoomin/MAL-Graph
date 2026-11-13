"""Sign in with MyAnimeList (OAuth 2 with PKCE) and the session cookie that follows.

MAL only supports the "plain" PKCE method, so the code verifier doubles as the challenge. The verifier and the
state travel in a short-lived signed cookie between /auth/login and /auth/callback, so nothing is kept in memory.
After sign-in the session cookie carries just the MAL username, signed with SESSION_SECRET. MAL tokens are used
once, to read the user's list during the callback, and are not stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
SESSION_COOKIE = "malgraph_session"
OAUTH_COOKIE = "malgraph_oauth"
SESSION_DAYS = 30
OAUTH_MINUTES = 10

_secret = settings.session_secret.encode()
if not _secret:
    # Fine for local development. Sessions end whenever the API restarts.
    _secret = secrets.token_bytes(32)
    if settings.sign_in:
        log.warning("SESSION_SECRET is not set, so sign-ins will not survive an API restart")


class AuthError(RuntimeError):
    """`code` is one of the sign-in error codes the web app knows how to word (see web/src/components/Welcome.tsx)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- signed values

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: dict[str, Any], purpose: str) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(_secret, f"{purpose}.{body}".encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def _verify(value: str | None, purpose: str) -> dict[str, Any] | None:
    """The payload of a value made by _sign for this purpose, or None if it is forged, garbled or expired."""
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    expected = hmac.new(_secret, f"{purpose}.{body}".encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_unb64(mac), expected):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def session_value(username: str) -> str:
    return _sign({"u": username, "exp": int(time.time()) + SESSION_DAYS * 86400}, "session")


def session_user(cookie: str | None) -> str | None:
    payload = _verify(cookie, "session")
    return payload.get("u") if payload else None


def cookie_options(max_age: int, path: str = "/") -> dict[str, Any]:
    return {"max_age": max_age, "path": path, "httponly": True, "samesite": "lax", "secure": settings.public_url.startswith("https://")}


# --------------------------------------------------------------------------- OAuth

def redirect_uri() -> str:
    return f"{settings.public_url}/api/auth/callback"


def start() -> tuple[str, str]:
    """The MAL authorization URL to send the browser to, and the signed cookie value that remembers this attempt."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)[:128]  # 43 to 128 characters
    url = AUTHORIZE_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": settings.mal_client_id,
        "state": state,
        "redirect_uri": redirect_uri(),
        "code_challenge": verifier,
        "code_challenge_method": "plain",
    })
    return url, _sign({"s": state, "v": verifier, "exp": int(time.time()) + OAUTH_MINUTES * 60}, "oauth")


def finish(code: str, state: str, oauth_cookie: str | None) -> tuple[str, str]:
    """Exchange the authorization code. Returns (MAL username, access token)."""
    attempt = _verify(oauth_cookie, "oauth")
    if not attempt or not hmac.compare_digest(attempt["s"], state):
        raise AuthError("expired")
    data = {
        "client_id": settings.mal_client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": attempt["v"],
        "redirect_uri": redirect_uri(),
    }
    if settings.mal_client_secret:
        data["client_secret"] = settings.mal_client_secret
    with httpx.Client(timeout=20) as http:
        resp = http.post(TOKEN_URL, data=data)
        if resp.status_code != 200:
            log.warning("MAL token exchange failed: %s %s", resp.status_code, resp.text[:300])
            raise AuthError("rejected")
        token = resp.json()["access_token"]
        me = http.get(f"{settings.mal_base}/users/@me", headers={"Authorization": f"Bearer {token}"})
        if me.status_code != 200:
            raise AuthError("profile")
        return me.json()["name"], token
