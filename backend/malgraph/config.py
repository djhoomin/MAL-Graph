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
    mal_username: str = os.getenv("MAL_USERNAME", "")
    memgraph_uri: str = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
    memgraph_user: str = os.getenv("MEMGRAPH_USER", "")
    memgraph_password: str = os.getenv("MEMGRAPH_PASSWORD", "")
    # Relative paths resolve against the repo root (dev); the container sets absolute paths under /app/data.
    cache_dir: Path = Path(os.getenv("CACHE_DIR", "data/cache")) if os.path.isabs(os.getenv("CACHE_DIR", "")) else REPO_ROOT / os.getenv("CACHE_DIR", "data/cache")
    conversations_dir: Path = Path(os.getenv("CONVERSATIONS_DIR")) if os.getenv("CONVERSATIONS_DIR") else (Path(os.getenv("CACHE_DIR", "data/cache")) if os.path.isabs(os.getenv("CACHE_DIR", "")) else REPO_ROOT / os.getenv("CACHE_DIR", "data/cache")).parent / "conversations"
    jikan_base: str = os.getenv("JIKAN_BASE", "http://localhost:8080/v4")
    mal_base: str = "https://api.myanimelist.net/v2"
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5")
    openrouter_base: str = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")


settings = Settings()
