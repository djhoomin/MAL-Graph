"""AniList as the graph's data source (DATA_SOURCE=anilist).

AniListSource answers the same calls as JikanClient (anime_full, anime_characters, anime_staff, person, person_full,
character_full, character_voices) and returns the same Jikan shapes, so ingest builds the same graph from either.
The ids are AniList's, so an AniList deployment needs its own Memgraph data, since characters and staff have no
MyAnimeList ids to join on.

AniList's terms allow non-commercial use but forbid "hoarding or mass collection", so nothing here crawls. It fetches
what users have on their lists and what they open, at about 25 requests a minute (AniList allows 30), and caches each
answer on disk like the Jikan client does. Large casts and careers are capped at the best-known entries, since every
page of 25 is one more request.

The functions at the bottom stand in for the MyAnimeList API calls the Ask agent uses (search, recommendations,
season, ranking) and return its node shape.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import threading
import time
import zlib
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .jikan import JikanError

log = logging.getLogger(__name__)

URL = "https://graphql.anilist.co"
PER_MINUTE = 25
PER_PAGE = 25  # AniList's cap for nested connections
ANIME_PAGES = 2  # characters and staff, each up to 50, main characters and key staff first
PERSON_PAGES = 6  # a person's roles, up to 150, most popular anime first
CHARACTER_PAGES = 2

FORMAT = {"TV": "TV", "TV_SHORT": "TV", "MOVIE": "Movie", "SPECIAL": "Special", "OVA": "OVA", "ONA": "ONA",
          "MUSIC": "Music"}
STATUS = {"FINISHED": "Finished Airing", "RELEASING": "Currently Airing", "NOT_YET_RELEASED": "Not yet aired",
          "CANCELLED": "Cancelled", "HIATUS": "On Hiatus"}
SOURCE = {"ORIGINAL": "Original", "MANGA": "Manga", "LIGHT_NOVEL": "Light novel", "VISUAL_NOVEL": "Visual novel",
          "VIDEO_GAME": "Game", "NOVEL": "Novel", "DOUJINSHI": "Doujinshi", "ANIME": "Other", "WEB_NOVEL": "Web novel",
          "LIVE_ACTION": "Other", "GAME": "Game", "COMIC": "Other", "MULTIMEDIA_PROJECT": "Other",
          "PICTURE_BOOK": "Picture book", "OTHER": "Other"}
RELATION = {"SEQUEL": "Sequel", "PREQUEL": "Prequel", "SIDE_STORY": "Side Story", "PARENT": "Parent Story",
            "SPIN_OFF": "Spin-Off", "ALTERNATIVE": "Alternative Version", "SUMMARY": "Summary", "COMPILATION": "Summary",
            "CONTAINS": "Full Story", "CHARACTER": "Character", "OTHER": "Other"}
ROLE = {"MAIN": "Main", "SUPPORTING": "Supporting", "BACKGROUND": "Supporting"}
LANGUAGE = {"Portuguese": "Portuguese (BR)", "Chinese": "Mandarin"}  # the rest already read like MyAnimeList's
SEASONS = {"winter": "WINTER", "spring": "SPRING", "summer": "SUMMER", "fall": "FALL"}

# AniList genres are names without ids. They get fixed ids above AniList's tag ids, which are below 10000.
GENRES = ["Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Hentai", "Horror", "Mahou Shoujo", "Mecha",
          "Music", "Mystery", "Psychological", "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural",
          "Thriller"]
GENRE_BASE = 100_000
EXPLICIT_GENRES = {"Hentai"}
# Tags that become themes, as MyAnimeList's themes are: the few that fit best, without spoilers or cast traits
THEME_CATEGORIES = ("Theme", "Setting")
THEME_RANK = 70
THEMES_KEPT = 5

MEDIA = """id idMal title { romaji english native } format status episodes duration source season seasonYear
  startDate { year month day } averageScore popularity favourites isAdult siteUrl description(asHtml: false)
  coverImage { large medium } genres
  rankings { rank type allTime } stats { scoreDistribution { amount } }
  tags { id name rank category isMediaSpoiler isAdult }
  studios { edges { isMain node { id name siteUrl } } }
  relations { edges { relationType node { id type title { romaji } coverImage { large } siteUrl } } }"""
PERSON = "id name { userPreferred native } image { large } siteUrl"
CHARACTER = "id name { userPreferred } image { large } siteUrl favourites gender"
VOICES = f"voiceActorRoles(sort: [LANGUAGE, RELEVANCE]) {{ voiceActor {{ {PERSON} languageV2 }} }}"
CAST = f"""characters(page: $page, perPage: {PER_PAGE}, sort: [ROLE, RELEVANCE, ID]) {{ pageInfo {{ hasNextPage }}
  edges {{ role node {{ {CHARACTER} }} {VOICES} }} }}
  staff(page: $page, perPage: {PER_PAGE}, sort: [RELEVANCE, ID]) {{ pageInfo {{ hasNextPage }}
  edges {{ role node {{ {PERSON} }} }} }}"""
ANIME_QUERY = f"query ($id: Int, $page: Int) {{ Media(id: $id, type: ANIME) {{ {MEDIA} {CAST} }} }}"
CAST_QUERY = f"query ($id: Int, $page: Int) {{ Media(id: $id, type: ANIME) {{ {CAST} }} }}"
PERSON_QUERY = f"""query ($id: Int, $page: Int) {{ Staff(id: $id) {{ {PERSON} name {{ first last }}
  dateOfBirth {{ year month day }} favourites description(asHtml: false)
  characterMedia(page: $page, perPage: {PER_PAGE}, sort: [POPULARITY_DESC]) {{ pageInfo {{ hasNextPage }}
    edges {{ characterRole node {{ id type title {{ romaji }} coverImage {{ large }} siteUrl }}
             characters {{ {CHARACTER} }} }} }}
  staffMedia(page: $page, perPage: {PER_PAGE}, type: ANIME, sort: [POPULARITY_DESC]) {{ pageInfo {{ hasNextPage }}
    edges {{ staffRole node {{ id title {{ romaji }} coverImage {{ large }} siteUrl }} }} }} }} }}"""
CHECK_QUERY = "query ($id: Int) { Staff(id: $id) { id dateOfBirth { year month day } favourites } }"
CHARACTER_QUERY = f"""query ($id: Int, $page: Int) {{ Character(id: $id) {{ {CHARACTER} name {{ native alternative }}
  description(asHtml: false)
  media(page: $page, perPage: {PER_PAGE}, type: ANIME, sort: [POPULARITY_DESC]) {{ pageInfo {{ hasNextPage }}
    edges {{ characterRole node {{ id title {{ romaji }} coverImage {{ large }} siteUrl }} {VOICES} }} }} }} }}"""


class RateLimiter:
    """At most PER_MINUTE requests a minute, spaced evenly, shared by every thread."""

    def __init__(self, per_minute: int = PER_MINUTE) -> None:
        self.gap = 60 / per_minute
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next)
            self.next = at + self.gap
        if at > now:
            time.sleep(at - now)


def _text(s: str | None) -> str | None:
    """AniList descriptions carry some HTML and markdown spoiler marks. Plain text, as Jikan gives."""
    if not s:
        return None
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"~!.*?!~", "", s, flags=re.S)  # spoilers
    s = re.sub(r"__(.+?)__|\*\*(.+?)\*\*", lambda m: m.group(1) or m.group(2), s)
    return html.unescape(re.sub(r"\n{3,}", "\n\n", s)).strip() or None


def _images(url: str | None) -> dict[str, Any]:
    return {"jpg": {"image_url": url}}


def _date(d: dict[str, Any] | None) -> str | None:
    if not d or not d.get("year"):
        return None
    return f"{d['year']:04d}-{d.get('month') or 1:02d}-{d.get('day') or 1:02d}T00:00:00+00:00"


def _anime_ref(m: dict[str, Any]) -> dict[str, Any]:
    return {"mal_id": m["id"], "title": (m.get("title") or {}).get("romaji"),
            "images": _images((m.get("coverImage") or {}).get("large")), "url": m.get("siteUrl")}


def _person_ref(p: dict[str, Any]) -> dict[str, Any]:
    return {"mal_id": p["id"], "name": (p.get("name") or {}).get("userPreferred"),
            "images": _images((p.get("image") or {}).get("large")), "url": p.get("siteUrl")}


def _character_ref(c: dict[str, Any]) -> dict[str, Any]:
    return {**_person_ref(c), "gender": c.get("gender")}


def _language(lang: str | None) -> str | None:
    return LANGUAGE.get(lang or "", lang)


def _voices(roles: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [{"person": _person_ref(r["voiceActor"]), "language": _language(r["voiceActor"].get("languageV2"))}
            for r in roles or [] if r.get("voiceActor")]


def genre_id(name: str) -> int:
    return GENRE_BASE + (GENRES.index(name) if name in GENRES else 1000 + zlib.crc32(name.encode()) % 50_000)


def _genres(m: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    genres = [{"mal_id": genre_id(g), "name": g} for g in m.get("genres") or [] if g not in EXPLICIT_GENRES]
    explicit = [{"mal_id": genre_id(g), "name": g} for g in m.get("genres") or [] if g in EXPLICIT_GENRES]
    demographics, themes = [], []
    for t in sorted(m.get("tags") or [], key=lambda t: -(t.get("rank") or 0)):
        category = t.get("category") or ""
        if t.get("isMediaSpoiler") or t.get("isAdult"):
            continue
        if category == "Demographic":
            demographics.append({"mal_id": t["id"], "name": t["name"]})
        elif category.startswith(THEME_CATEGORIES) and (t.get("rank") or 0) >= THEME_RANK and len(themes) < THEMES_KEPT:
            themes.append({"mal_id": t["id"], "name": t["name"]})
    return {"genres": genres, "explicit_genres": explicit, "themes": themes, "demographics": demographics[:1]}


def _rank(m: dict[str, Any], kind: str) -> int | None:
    return next((r["rank"] for r in m.get("rankings") or [] if r["type"] == kind and r.get("allTime")), None)


def anime_payload(m: dict[str, Any]) -> dict[str, Any]:
    """An AniList Media in the shape of Jikan's /anime/{id}/full."""
    relations: dict[str, list[dict[str, Any]]] = {}
    for e in (m.get("relations") or {}).get("edges") or []:
        name = RELATION.get(e.get("relationType") or "")
        if name and (e.get("node") or {}).get("type") == "ANIME":
            ref = _anime_ref(e["node"])
            relations.setdefault(name, []).append({"mal_id": ref["mal_id"], "type": "anime", "name": ref["title"], "url": ref["url"]})
    start = m.get("startDate") or {}
    scored = sum(s.get("amount") or 0 for s in (m.get("stats") or {}).get("scoreDistribution") or []) or None
    return {
        "mal_id": m["id"],
        "id_mal": m.get("idMal"),
        "title": m["title"].get("romaji"),
        "title_english": m["title"].get("english"),
        "title_japanese": m["title"].get("native"),
        "type": FORMAT.get(m.get("format") or "", m.get("format")),
        "episodes": m.get("episodes"),
        "status": STATUS.get(m.get("status") or "", m.get("status")),
        "year": m.get("seasonYear") or start.get("year"),
        "season": (m.get("season") or "").lower() or None,
        "score": m["averageScore"] / 10 if m.get("averageScore") else None,
        "scored_by": scored,
        "rank": _rank(m, "RATED"),
        "popularity": _rank(m, "POPULAR"),
        "members": m.get("popularity"),
        "favorites": m.get("favourites"),
        "rating": "Rx - Hentai" if m.get("isAdult") else None,
        "source": SOURCE.get(m.get("source") or ""),
        "duration": f"{m['duration']} min per ep" if m.get("duration") else None,
        "aired": {"from": _date(start), "prop": {"from": {"year": start.get("year")}}},
        "synopsis": _text(m.get("description")),
        "images": _images((m.get("coverImage") or {}).get("large")),
        "url": m.get("siteUrl"),
        "studios": [{"mal_id": e["node"]["id"], "name": e["node"]["name"], "url": e["node"].get("siteUrl")}
                    for e in (m.get("studios") or {}).get("edges") or [] if e.get("isMain")],
        **_genres(m),
        "relations": [{"relation": k, "entry": v} for k, v in relations.items()],
    }


def _node(m: dict[str, Any]) -> dict[str, Any]:
    """An AniList Media in the MyAnimeList API's node shape, for the Ask agent's catalogue tools."""
    p = anime_payload(m)
    return {
        "id": p["mal_id"], "title": p["title"], "media_type": (m.get("format") or "").lower() or None,
        "start_season": {"year": p["year"], "season": p["season"]}, "num_episodes": p["episodes"],
        "mean": p["score"], "num_list_users": p["members"], "status": (m.get("status") or "").lower() or None,
        "genres": [{"name": g["name"]} for g in p["genres"] + p["themes"]],
        "studios": [{"name": s["name"]} for s in p["studios"]],
        "main_picture": {"medium": (m.get("coverImage") or {}).get("medium")},
    }


class AniListSource:
    def __init__(self, cache_dir: Path | None = None, max_retries: int = 4) -> None:
        self.cache_dir = (cache_dir or settings.cache_dir) / "anilist"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = RateLimiter()
        self.max_retries = max_retries
        self.http = httpx.Client(timeout=30, headers={"User-Agent": "MAL-Graph (non-commercial)", "Accept": "application/json"})
        self.stats = {"hits": 0, "requests": 0}

    # ------------------------------------------------------------------ transport

    def query(self, query: str, variables: dict[str, Any], *, refresh: bool = False) -> dict[str, Any]:
        key = json.dumps({"q": hashlib.sha1(query.encode()).hexdigest()[:10], **variables}, sort_keys=True)
        cache = self.cache_dir / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".json")
        if cache.exists() and not refresh:
            self.stats["hits"] += 1
            return json.loads(cache.read_text())
        delay = 2.0
        for attempt in range(self.max_retries):
            self.limiter.wait()
            self.stats["requests"] += 1
            try:
                resp = self.http.post(URL, json={"query": query, "variables": variables})
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise JikanError(f"AniList: {e}") from e
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry = resp.headers.get("Retry-After")
                wait = int(retry) + 1 if retry and retry.isdigit() else delay
                log.warning("AniList HTTP %s, waiting %s s (limit %s, remaining %s)", resp.status_code, wait,
                            resp.headers.get("X-RateLimit-Limit"), resp.headers.get("X-RateLimit-Remaining"))
                time.sleep(wait)
                delay *= 2
                continue
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 404 or any(e.get("status") == 404 for e in body.get("errors") or []):
                raise JikanError(f"AniList {variables}: 404 not found")
            if resp.status_code != 200 or body.get("errors"):
                text = "; ".join(str(e.get("message")) for e in body.get("errors") or []) or resp.text[:200]
                raise JikanError(f"AniList HTTP {resp.status_code}: {text}")
            data = body["data"]
            cache.write_text(json.dumps(data))
            return data
        raise JikanError(f"AniList {variables}: gave up after {self.max_retries} attempts")

    def _anime(self, anime_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """The Media with its first ANIME_PAGES pages of characters and staff merged in."""
        m = dict(self.query(ANIME_QUERY, {"id": anime_id, "page": 1}, refresh=refresh)["Media"])
        chars, staff = list(m["characters"]["edges"]), list(m["staff"]["edges"])
        more_chars, more_staff = m["characters"]["pageInfo"]["hasNextPage"], m["staff"]["pageInfo"]["hasNextPage"]
        page = 2
        while (more_chars or more_staff) and page <= ANIME_PAGES:
            p = self.query(CAST_QUERY, {"id": anime_id, "page": page}, refresh=refresh)["Media"]
            if more_chars:
                chars += p["characters"]["edges"]
                more_chars = p["characters"]["pageInfo"]["hasNextPage"]
            if more_staff:
                staff += p["staff"]["edges"]
                more_staff = p["staff"]["pageInfo"]["hasNextPage"]
            page += 1
        m["characters"], m["staff"] = chars, staff
        return m

    def _pages(self, query: str, root: str, fields: list[str], entity_id: int, pages: int) -> dict[str, Any]:
        """Fetch up to `pages` pages of the paged `fields` under `root`, merged into the first page's object."""
        first = dict(self.query(query, {"id": entity_id, "page": 1})[root])
        merged = {f: list(first[f]["edges"]) for f in fields}
        more = {f: first[f]["pageInfo"]["hasNextPage"] for f in fields}
        page = 2
        while any(more.values()) and page <= pages:
            p = self.query(query, {"id": entity_id, "page": page})[root]
            for f in fields:
                if more[f]:
                    merged[f] += p[f]["edges"]
                    more[f] = p[f]["pageInfo"]["hasNextPage"]
            page += 1
        first.update(merged)
        return first

    # ------------------------------------------------------------------ JikanClient's calls

    def anime_full(self, anime_id: int) -> dict[str, Any]:
        return anime_payload(self._anime(anime_id))

    def anime_characters(self, anime_id: int) -> list[dict[str, Any]]:
        return [{"character": _character_ref(e["node"]), "role": ROLE.get(e.get("role") or "", "Supporting"),
                 "favorites": e["node"].get("favourites"), "voice_actors": _voices(e.get("voiceActorRoles"))}
                for e in self._anime(anime_id)["characters"]]

    def anime_staff(self, anime_id: int) -> list[dict[str, Any]]:
        people: dict[int, dict[str, Any]] = {}
        for e in self._anime(anime_id)["staff"]:
            row = people.setdefault(e["node"]["id"], {"person": _person_ref(e["node"]), "positions": []})
            if e.get("role"):
                row["positions"].append(e["role"])
        return list(people.values())

    def person(self, person_id: int) -> dict[str, Any]:
        s = self.query(CHECK_QUERY, {"id": person_id})["Staff"]
        return {"birthday": _date(s.get("dateOfBirth")) if (s.get("dateOfBirth") or {}).get("month") else None,
                "favorites": s.get("favourites")}

    def person_full(self, person_id: int) -> dict[str, Any]:
        s = self._pages(PERSON_QUERY, "Staff", ["characterMedia", "staffMedia"], person_id, PERSON_PAGES)
        voices = [{"anime": _anime_ref(e["node"]), "character": _character_ref(c), "role": ROLE.get(e.get("characterRole") or "", "Supporting")}
                  for e in s["characterMedia"] if (e.get("node") or {}).get("type") == "ANIME" for c in e.get("characters") or [] if c]
        work = [{"anime": _anime_ref(e["node"]), "position": e.get("staffRole") or ""} for e in s["staffMedia"]]
        return {
            **_person_ref(s),
            "given_name": s["name"].get("first"),
            "family_name": s["name"].get("last"),
            "birthday": _date(s.get("dateOfBirth")) if (s.get("dateOfBirth") or {}).get("month") else None,
            "favorites": s.get("favourites"),
            "about": _text(s.get("description")),
            "voices": voices,
            "anime": work,
        }

    def character_full(self, character_id: int) -> dict[str, Any]:
        c = self._pages(CHARACTER_QUERY, "Character", ["media"], character_id, CHARACTER_PAGES)
        voices: dict[int, dict[str, Any]] = {}
        for e in c["media"]:
            for v in _voices(e.get("voiceActorRoles")):
                voices.setdefault(v["person"]["mal_id"], v)
        return {
            **_character_ref(c),
            "name_kanji": c["name"].get("native"),
            "nicknames": c["name"].get("alternative") or [],
            "favorites": c.get("favourites"),
            "about": _text(c.get("description")),
            "anime": [{"anime": _anime_ref(e["node"]), "role": ROLE.get(e.get("characterRole") or "", "Supporting")} for e in c["media"]],
            "voices": list(voices.values()),
        }

    def character_voices(self, character_id: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        if refresh:
            self.query(CHARACTER_QUERY, {"id": character_id, "page": 1}, refresh=True)
        return self.character_full(character_id)["voices"]

    # ------------------------------------------------------------------ catalogue, for the Ask agent

    def _page(self, args: tuple[str, str], variables: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        """Up to `limit` anime from Page.media, with `args` as (variable declarations, media arguments)."""
        decl = f", {args[0]}" if args[0] else ""
        q = f"query ($page: Int, $per: Int{decl}) {{ Page(page: $page, perPage: $per) {{ pageInfo {{ hasNextPage }} media({args[1]}, type: ANIME) {{ {MEDIA} }} }} }}"
        out: list[dict[str, Any]] = []
        page = 1
        while len(out) < limit:
            p = self.query(q, {**variables, "page": page, "per": min(50, limit)})["Page"]
            out += p["media"]
            if not p["pageInfo"]["hasNextPage"]:
                break
            page += 1
        return [_node(m) for m in out[:limit]]

    def search_anime(self, q: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._page(("$q: String", "search: $q, sort: [SEARCH_MATCH]"), {"q": q}, limit)

    def season(self, year: int, season_name: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._page(("$year: Int, $season: MediaSeason", "seasonYear: $year, season: $season, sort: [POPULARITY_DESC]"),
                          {"year": year, "season": SEASONS.get(season_name.lower(), season_name.upper())}, limit)

    def ranking(self, ranking_type: str = "all", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        sort = {"bypopularity": "POPULARITY_DESC", "favorite": "FAVOURITES_DESC"}.get(ranking_type, "SCORE_DESC")
        formats = {"tv": "TV", "movie": "MOVIE", "ova": "OVA", "ona": "ONA", "special": "SPECIAL"}
        args = f"sort: [{sort}], isAdult: false" + (f", format: {formats[ranking_type]}" if ranking_type in formats else "")
        if ranking_type == "airing":
            args += ", status: RELEASING"
        if ranking_type == "upcoming":
            args = "sort: [POPULARITY_DESC], status: NOT_YET_RELEASED, isAdult: false"
        return self._page(("", args), {}, limit + offset)[offset:]

    def anime_details(self, anime_id: int, fields: str = "") -> dict[str, Any]:
        q = """query ($id: Int) { Media(id: $id, type: ANIME) { id title { romaji }
          recommendations(perPage: 25, sort: [RATING_DESC]) { nodes { rating mediaRecommendation { id title { romaji } } } } } }"""
        m = self.query(q, {"id": anime_id})["Media"]
        return {"id": m["id"], "title": m["title"]["romaji"], "recommendations": [
            {"node": {"id": r["mediaRecommendation"]["id"], "title": r["mediaRecommendation"]["title"]["romaji"]}, "num_recommendations": r.get("rating")}
            for r in m["recommendations"]["nodes"] if r.get("mediaRecommendation")]}

    def mal_to_anilist(self, mal_ids: list[int]) -> dict[int, int]:
        """AniList ids for MyAnimeList ids, for a MyAnimeList export uploaded to an AniList deployment."""
        q = "query ($ids: [Int], $page: Int) { Page(page: $page, perPage: 50) { pageInfo { hasNextPage } media(idMal_in: $ids, type: ANIME) { id idMal } } }"
        out: dict[int, int] = {}
        for i in range(0, len(mal_ids), 50):
            chunk, page = mal_ids[i:i + 50], 1
            while True:
                p = self.query(q, {"ids": chunk, "page": page})["Page"]
                out.update({m["idMal"]: m["id"] for m in p["media"] if m.get("idMal")})
                if not p["pageInfo"]["hasNextPage"]:
                    break
                page += 1
        return out


_shared: AniListSource | None = None
_lock = threading.Lock()


def shared() -> AniListSource:
    global _shared
    with _lock:
        if _shared is None:
            _shared = AniListSource()
        return _shared
