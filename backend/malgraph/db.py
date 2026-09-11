"""Memgraph access via the Bolt-compatible neo4j driver."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from neo4j import GraphDatabase, Driver

from .config import settings

NODE_LABELS = ["Anime", "Character", "Person", "Studio", "Genre"]


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    auth = (settings.memgraph_user, settings.memgraph_password) if settings.memgraph_user else None
    return GraphDatabase.driver(settings.memgraph_uri, auth=auth)


def run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Run a Cypher query and return records as dicts."""
    with get_driver().session() as session:
        result = session.run(query, **params)
        return [r.data() for r in result]


def ensure_schema() -> None:
    """Create uniqueness constraints and lookup indexes (idempotent)."""
    for label in NODE_LABELS:
        run(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.mal_id IS UNIQUE")
        run(f"CREATE INDEX ON :{label}(mal_id)")
    run("CREATE CONSTRAINT ON (n:User) ASSERT n.username IS UNIQUE")
    run("CREATE INDEX ON :User(username)")
    run("CREATE INDEX ON :Anime(title)")
    run("CREATE INDEX ON :Character(name)")
    run("CREATE INDEX ON :Person(name)")
