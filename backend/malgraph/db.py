"""Memgraph access via the Bolt-compatible neo4j driver."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Iterator

from neo4j import GraphDatabase, Driver

from .config import settings

NODE_LABELS = ["Anime", "Character", "Person", "Studio", "Genre"]

# Whether the viewer chose English anime titles. Set per request by the API middleware from the `titles` cookie.
_english: ContextVar[bool] = ContextVar("malgraph_english_titles", default=False)


def english_titles() -> bool:
    return _english.get()


@contextmanager
def use_english_titles(english: bool) -> Iterator[None]:
    token = _english.set(english)
    try:
        yield
    finally:
        _english.reset(token)


def title(alias: str) -> str:
    """Cypher for an anime's title as the viewer wants it: the English title when they chose English and the anime
    has one, otherwise the main (romanised Japanese) title. `run` fills in $english_titles."""
    return f"coalesce(CASE WHEN $english_titles THEN {alias}.title_english END, {alias}.title)"


def title_params(query: str) -> dict[str, Any]:
    """The $english_titles parameter, for queries run on a session directly instead of through `run`."""
    return {"english_titles": _english.get()} if "$english_titles" in query else {}


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    auth = (settings.memgraph_user, settings.memgraph_password) if settings.memgraph_user else None
    # Check each pooled connection before reuse (one cheap round trip), so a Memgraph restart doesn't fail the next query.
    return GraphDatabase.driver(settings.memgraph_uri, auth=auth, liveness_check_timeout=0)


def run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Run a Cypher query and return records as dicts."""
    params = {**title_params(query), **params}
    with get_driver().session() as session:
        result = session.run(query, **params)
        return [r.data() for r in result]


def migrate_ids() -> int:
    """One-off: nodes used to keep their MyAnimeList id as `mal_id`. It is now `id`, so the graph doesn't assume one
    data source. Moves the property in batches and drops the old constraint and index. Idempotent."""
    moved = 0
    for label in NODE_LABELS:
        while True:
            n = run(f"MATCH (n:{label}) WHERE n.mal_id IS NOT NULL WITH n LIMIT 20000 "
                    "SET n.id = n.mal_id REMOVE n.mal_id RETURN count(n) AS n")[0]["n"]
            moved += n
            if not n:
                break
    for label in NODE_LABELS:
        for query in (f"DROP CONSTRAINT ON (n:{label}) ASSERT n.mal_id IS UNIQUE", f"DROP INDEX ON :{label}(mal_id)"):
            try:
                run(query)
            except Exception:  # already gone
                pass
    return moved


def ensure_schema() -> None:
    """Create uniqueness constraints and lookup indexes (idempotent)."""
    migrate_ids()
    for label in NODE_LABELS:
        run(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.id IS UNIQUE")
        run(f"CREATE INDEX ON :{label}(id)")
    run("CREATE CONSTRAINT ON (n:User) ASSERT n.username IS UNIQUE")
    run("CREATE INDEX ON :User(username)")
    run("CREATE INDEX ON :Anime(title)")
    run("CREATE INDEX ON :Character(name)")
    run("CREATE INDEX ON :Person(name)")
