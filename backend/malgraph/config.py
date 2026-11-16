"""Environment-driven settings. Loads .env from the repo root."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    mal_client_id: str = os.getenv("MAL_CLIENT_ID", "")
    mal_client_secret: str = os.getenv("MAL_CLIENT_SECRET", "")  # only for MAL apps of type "web"
    mal_username: str = os.getenv("MAL_USERNAME", "")  # CLI default, and the API's user when sign-in is off
    # Where the site is served, e.g. https://app.mal-graph.eu. Setting it turns on "Sign in with MyAnimeList";
    # the MAL app's redirect URL must be {PUBLIC_URL}/api/auth/callback.
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")
    session_secret: str = os.getenv("SESSION_SECRET", "")
    # "Sign in with AniList": an AniList API client whose redirect URL is {PUBLIC_URL}/api/auth/anilist/callback.
    anilist_client_id: str = os.getenv("ANILIST_CLIENT_ID", "")
    anilist_client_secret: str = os.getenv("ANILIST_API_KEY", "")  # the client's secret
    # Where anime, characters and people come from: "mal" (MyAnimeList through Jikan) or "anilist". Each needs its
    # own Memgraph data, since the ids differ. An AniList deployment signs people in with AniList only.
    data_source: str = "anilist" if os.getenv("DATA_SOURCE", "mal").strip().lower() == "anilist" else "mal"
    genders_worker: bool = os.getenv("GENDERS_WORKER", "1") != "0"  # fill character genders in from AniList in the background
    privacy_contact: str = os.getenv("PRIVACY_CONTACT", "")  # who runs the site and how to reach them, shown on the privacy page
    memgraph_uri: str = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
    memgraph_user: str = os.getenv("MEMGRAPH_USER", "")
    memgraph_password: str = os.getenv("MEMGRAPH_PASSWORD", "")
    # Relative paths resolve against the repo root (dev); the container sets absolute paths under /app/data.
    cache_dir: Path = Path(os.getenv("CACHE_DIR", "data/cache")) if os.path.isabs(os.getenv("CACHE_DIR", "")) else REPO_ROOT / os.getenv("CACHE_DIR", "data/cache")
    conversations_dir: Path = Path(os.getenv("CONVERSATIONS_DIR")) if os.getenv("CONVERSATIONS_DIR") else (Path(os.getenv("CACHE_DIR", "data/cache")) if os.path.isabs(os.getenv("CACHE_DIR", "")) else REPO_ROOT / os.getenv("CACHE_DIR", "data/cache")).parent / "conversations"
    golf_dir: Path = Path(os.getenv("GOLF_DIR")) if os.getenv("GOLF_DIR") else REPO_ROOT / "data" / "golf"  # daily holes and scores
    jikan_base: str = os.getenv("JIKAN_BASE", "http://localhost:8080/v4")
    mal_base: str = "https://api.myanimelist.net/v2"
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5")
    ask_daily_limit: int = int(os.getenv("ASK_DAILY_LIMIT", "30"))  # questions per user per day; 0 means no cap
    ask_unlimited_users: str = os.getenv("ASK_UNLIMITED_USERS", "")  # comma list; MAL_USERNAME is always unlimited
    openrouter_base: str = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    @property
    def anilist_source(self) -> bool:
        return self.data_source == "anilist"

    @property
    def source_name(self) -> str:
        return "AniList" if self.anilist_source else "MyAnimeList"

    @property
    def mal_sign_in(self) -> bool:
        return bool(self.public_url and self.mal_client_id and not self.anilist_source)

    @property
    def anilist_sign_in(self) -> bool:
        return bool(self.public_url and self.anilist_client_id and self.anilist_client_secret
                    and (self.anilist_source or self.mal_client_id))

    @property
    def sign_in(self) -> bool:
        """Any sign-in is configured, so users come from session cookies instead of MAL_USERNAME."""
        return self.mal_sign_in or self.anilist_sign_in


settings = Settings()
