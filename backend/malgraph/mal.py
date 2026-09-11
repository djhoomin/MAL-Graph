"""Official MAL API v2: fetch a public user's anime list with a Client ID (no OAuth)."""
from __future__ import annotations

from typing import Any, Iterator

import httpx

from .config import settings


class MalError(RuntimeError):
    pass


def iter_user_animelist(username: str | None = None, client_id: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield {node: {...}, list_status: {...}} entries for every anime on the user's list."""
    username = username or settings.mal_username
    client_id = client_id or settings.mal_client_id
    if not username or not client_id:
        raise MalError("MAL_USERNAME and MAL_CLIENT_ID must be set in .env")

    url: str | None = f"{settings.mal_base}/users/{username}/animelist"
    params: dict[str, Any] | None = {
        "fields": "list_status,alternative_titles,media_type,num_episodes,start_season,mean,status,main_picture",
        "limit": 1000,
        "nsfw": "true",
    }
    with httpx.Client(timeout=30, headers={"X-MAL-CLIENT-ID": client_id}) as http:
        while url:
            resp = http.get(url, params=params)
            if resp.status_code == 403:
                raise MalError(f"403 from MAL: is {username}'s anime list public?")
            if resp.status_code == 404:
                raise MalError(f"404 from MAL: user '{username}' not found")
            if resp.status_code != 200:
                raise MalError(f"MAL HTTP {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            yield from body.get("data", [])
            url = body.get("paging", {}).get("next")
            params = None  # `next` already carries the query string
