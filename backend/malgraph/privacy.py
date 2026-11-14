"""Deleting everything MAL-Graph stores about a user ("Delete my data").

Personal data lives in four places: the user's node and LISTED edges in Memgraph, their Ask conversations and
usage (one folder), their plays of Graph Golf and the other daily games, and short-lived memory (sync queue, caches,
cooldowns). The shared graph of anime, characters and people is public MAL data and stays. Nightly backups age out within 30 days.
"""
from __future__ import annotations

import logging
from typing import Any

from . import agent, db, games, golf, jobs, kmk, users

log = logging.getLogger(__name__)


def delete_user(username: str) -> dict[str, Any]:
    username = users.canonical(username)
    jobs.queue.cancel(username)
    rows = db.run(
        "MATCH (u:User {username: $u}) OPTIONAL MATCH (u)-[l:LISTED]->() WITH u, count(l) AS n DETACH DELETE u RETURN n",
        u=username,
    )
    users.invalidate(username)
    agent.forget_conversations(username)
    rounds = golf.forget(username)
    plays = games.forget(username)
    kmk.forget_history(username)
    # Imported here: routes imports this module's callers, and the cooldown is only an in-memory dict.
    from .api import routes
    routes._last_sync.pop(username.lower(), None)
    summary = {"list_entries": rows[0]["n"] if rows else 0, "golf_rounds": rounds, "game_plays": plays}
    log.info("deleted a user's data: %s", summary)  # no username in the log
    return summary
