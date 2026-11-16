"""Sign in with AniList, and reading an AniList user's anime list.

AniList uses OAuth 2 with an authorization code. The state travels in a short-lived signed cookie, as with
MyAnimeList, and the access token is used once during the callback to read the list, then discarded.

With MyAnimeList as the data source, an AniList list joins the graph through each anime's MyAnimeList id (idMal), and
anime that aren't on MyAnimeList are skipped and counted. With DATA_SOURCE=anilist the graph uses AniList ids, so
nothing is skipped. Entries are turned into the same shape the MyAnimeList API returns, so ingest.upsert_user_list
reads both.

AniList users are stored as "<name>@anilist". MyAnimeList usernames can't contain "@", so the two never clash, and
someone with both accounts has two separate lists.
"""
from __future__ import annotations

import hmac
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Iterator
from urllib.parse import urlencode

import httpx

from . import auth
from .config import settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"
GRAPHQL_URL = "https://graphql.anilist.co"
OAUTH_COOKIE = "malgraph_oauth_anilist"
SUFFIX = "@anilist"
PER_CHUNK = 500

STATUS = {"CURRENT": "watching", "REPEATING": "watching", "COMPLETED": "completed", "PAUSED": "on_hold",
          "DROPPED": "dropped", "PLANNING": "plan_to_watch"}
FORMAT = {"TV": "tv", "TV_SHORT": "tv", "MOVIE": "movie", "SPECIAL": "special", "OVA": "ova", "ONA": "ona", "MUSIC": "music"}

VIEWER = "query { Viewer { id name } }"
LIST = """query ($id: Int, $name: String, $chunk: Int, $per: Int) {
  MediaListCollection(userId: $id, userName: $name, type: ANIME, chunk: $chunk, perChunk: $per) {
    hasNextChunk
    lists { isCustomList entries {
      status score(format: POINT_10) progress updatedAt
      media { id idMal title { romaji english } format episodes season seasonYear averageScore coverImage { medium } siteUrl }
    } }
  }
}"""


class AniListError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def is_anilist(username: str | None) -> bool:
    return bool(username) and username.lower().endswith(SUFFIX)


def name_of(username: str) -> str:
    return username[: -len(SUFFIX)] if is_anilist(username) else username


def redirect_uri() -> str:
    return f"{settings.public_url}/api/auth/anilist/callback"


def start() -> tuple[str, str]:
    """The AniList authorization URL, and the signed cookie value that remembers this attempt."""
    state = secrets.token_urlsafe(24)
    url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": settings.anilist_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "state": state,
    })
    return url, auth._sign({"s": state, "exp": int(time.time()) + auth.OAUTH_MINUTES * 60}, "oauth-anilist")


def finish(code: str, state: str, oauth_cookie: str | None) -> tuple[str, str, int]:
    """Exchange the authorization code. Returns (stored username, access token, AniList user id)."""
    attempt = auth._verify(oauth_cookie, "oauth-anilist")
    if not attempt or not hmac.compare_digest(attempt["s"], state):
        raise auth.AuthError("expired")
    with httpx.Client(timeout=20, headers={"Accept": "application/json"}) as http:
        resp = http.post(TOKEN_URL, json={
            "grant_type": "authorization_code",
            "client_id": settings.anilist_client_id,
            "client_secret": settings.anilist_client_secret,
            "redirect_uri": redirect_uri(),
            "code": code,
        })
        if resp.status_code != 200:
            log.warning("AniList token exchange failed: %s %s", resp.status_code, resp.text[:300])
            raise auth.AuthError("rejected")
        token = resp.json()["access_token"]
        me = http.post(GRAPHQL_URL, json={"query": VIEWER}, headers={"Authorization": f"Bearer {token}"})
        viewer = (me.json().get("data") or {}).get("Viewer") if me.status_code == 200 else None
        if not viewer:
            raise auth.AuthError("profile")
    return viewer["name"] + SUFFIX, token, viewer["id"]


def _entry(e: dict[str, Any]) -> dict[str, Any] | None:
    """An AniList list entry in the MyAnimeList API's shape, or None for anime that aren't on MyAnimeList when the
    graph uses MyAnimeList ids."""
    m = e["media"]
    own = settings.anilist_source
    if not own and not m.get("idMal"):
        return None
    updated = datetime.fromtimestamp(e["updatedAt"], timezone.utc).isoformat() if e.get("updatedAt") else None
    return {
        "node": {
            "id": m["id"] if own else m["idMal"],
            "url": m.get("siteUrl") if own else None,
            "main_picture": {"medium": (m.get("coverImage") or {}).get("medium")} if own else None,
            "title": m["title"].get("romaji") or m["title"].get("english"),
            "alternative_titles": {"en": m["title"].get("english")},
            "media_type": FORMAT.get(m.get("format") or "", (m.get("format") or "").lower() or None),
            "num_episodes": m.get("episodes"),
            "start_season": {"year": m.get("seasonYear"), "season": (m.get("season") or "").lower() or None},
            "mean": m["averageScore"] / 10 if m.get("averageScore") else None,
        },
        "list_status": {
            "status": STATUS.get(e["status"]),
            "score": e.get("score") or 0,
            "num_episodes_watched": e.get("progress"),
            "is_rewatching": e["status"] == "REPEATING",
            "updated_at": updated,
        },
    }


def iter_list(username: str, token: str | None = None, user_id: int | None = None, skipped: list[int] | None = None) -> Iterator[dict[str, Any]]:
    """Yield the user's list in the MyAnimeList API's shape. With a token, a private list can be read too. The ids of
    AniList anime that have no MyAnimeList id are appended to `skipped`."""
    name = name_of(username)
    headers = {"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    seen: set[int] = set()
    with httpx.Client(timeout=30, headers=headers) as http:
        chunk = 1
        while True:
            variables = {"chunk": chunk, "per": PER_CHUNK, **({"id": user_id} if user_id else {"name": name})}
            resp = http.post(GRAPHQL_URL, json={"query": LIST, "variables": variables})
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            errors = body.get("errors") or []
            if errors or resp.status_code != 200:
                text = " ".join(str(e.get("message", "")) for e in errors).lower()
                if "private" in text:
                    raise AniListError(f"{name}'s anime list is private on AniList. Sign in again to sync a private list.", 403)
                if resp.status_code == 404 or "not found" in text:
                    raise AniListError(f"There is no AniList user called {name}", 404)
                raise AniListError(f"AniList HTTP {resp.status_code}: {text[:200] or resp.text[:200]}", resp.status_code)
            collection = body["data"]["MediaListCollection"]
            for lst in collection["lists"]:
                if lst.get("isCustomList"):
                    continue  # custom lists repeat entries from the status lists
                for e in lst["entries"]:
                    out = _entry(e)
                    if out is None:
                        if skipped is not None:
                            skipped.append(e["media"]["id"])
                    elif out["node"]["id"] not in seen:
                        seen.add(out["node"]["id"])
                        yield out
            if not collection.get("hasNextChunk"):
                break
            chunk += 1
