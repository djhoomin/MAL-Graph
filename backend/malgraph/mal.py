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


# --------------------------------------------------------------------------- discovery (official API, read-only)

ANIME_FIELDS = "id,title,main_picture,mean,num_list_users,media_type,start_season,genres,num_episodes,status,studios"


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if not settings.mal_client_id:
        raise MalError("MAL_CLIENT_ID must be set in .env")
    with httpx.Client(timeout=30, headers={"X-MAL-CLIENT-ID": settings.mal_client_id}) as http:
        resp = http.get(f"{settings.mal_base}/{path}", params=params)
        if resp.status_code != 200:
            raise MalError(f"MAL HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()


def _nodes(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [d["node"] for d in body.get("data", [])]


def search_anime(q: str, limit: int = 20) -> list[dict[str, Any]]:
    return _nodes(_get("anime", {"q": q, "limit": min(limit, 100), "fields": ANIME_FIELDS, "nsfw": "true"}))


def ranking(ranking_type: str = "all", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """ranking_type: all | airing | upcoming | tv | ova | movie | special | bypopularity | favorite"""
    return _nodes(_get("anime/ranking", {"ranking_type": ranking_type, "limit": min(limit, 500), "offset": offset, "fields": ANIME_FIELDS, "nsfw": "true"}))


def season(year: int, season_name: str, limit: int = 100) -> list[dict[str, Any]]:
    return _nodes(_get(f"anime/season/{year}/{season_name}", {"limit": min(limit, 500), "sort": "anime_num_list_users", "fields": ANIME_FIELDS, "nsfw": "true"}))


def anime_details(mal_id: int, fields: str = ANIME_FIELDS + ",recommendations,related_anime,synopsis,rank,popularity") -> dict[str, Any]:
    return _get(f"anime/{mal_id}", {"fields": fields})
