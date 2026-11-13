"""'Ask the graph': a tool-using agent over the graph API, run through OpenRouter (OpenAI-compatible)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from . import db, ingest, mal, users
from .config import settings
from .api import queries as Q
from .api import routes as R
from .api.serialize import PayloadBuilder, node_payload

log = logging.getLogger(__name__)
MAX_STEPS = 20
MAX_ROWS = 200
FORBIDDEN = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|INDEX|CONSTRAINT|LOAD\s+CSV|IMPORT|ALTER|STORAGE\s+MODE|FREE\s+MEMORY|CREATE\s+TRIGGER)\b", re.I)

SYSTEM_PROMPT = """You are the guide for MAL-Graph, a personal graph of one MyAnimeList user's anime list, stored in Memgraph.
The user is {username}. Answer their questions by exploring the graph with the tools; never invent data.

Graph model (all ids are MAL ids; node refs look like "Anime:5114", "Character:12", "Person:8", "Studio:4", "Genre:1"):
  (:User {{username}})-[:LISTED {{status, score, episodes_watched}}]->(:Anime)
  (:Anime {{mal_id, title, title_english, type, episodes, year, season, score, members, fetched_at}})
  (:Anime)-[:HAS_CHARACTER {{role: 'Main'|'Supporting'}}]->(:Character {{mal_id, name, image_url, favorites}})
  (:Person {{mal_id, name, image_url}})-[:VOICES {{language, anime_ids}}]->(:Character)
  (:Person)-[:WORKED_ON {{positions: [..]}}]->(:Anime)      e.g. positions contain 'Director', 'Music', 'Character Design'
  (:Anime)-[:RELATED_TO {{relation: 'Sequel'|'Prequel'|'Side Story'|...}}]->(:Anime)
  (:Anime)-[:PRODUCED_BY]->(:Studio {{mal_id, name}})      (:Anime)-[:HAS_GENRE]->(:Genre {{mal_id, name, kind}})
List statuses: completed, watching, on_hold, dropped, plan_to_watch. "watched"/"seen" means LISTED.status <> 'plan_to_watch'.
The graph is shared by several users, so the user's list exists only as their LISTED edges. Other users' lists are private.
cypher_read enforces three rules: reach the list only as (u:User {{username: $user}})-[l:LISTED]->(a:Anime) (the $user
parameter is filled in for you), give every node you start from a label, and give every relationship a type, also in
variable-length and BFS patterns. Anime nodes carry no personal fields.
Anime with fetched_at IS NULL are stubs known only by title (sequels etc. not on the list); persons/characters can be stubs too.
Only anime on the user's list have been fully fetched, so a voice actor's roles are only known for those anime.

The graph contains the user's list, related anime, and (after enrichment) the filmographies of their favourite people and
metadata for anime those people share. For RECOMMENDATIONS, follow this playbook and keep it to ~6 tool calls:
  1. `taste_profile` — one call that gives their favourite VAs, directors, composers, studios, genres and top-rated anime. Never
     re-derive this with cypher_read.
  2. `recommendations` (via va / staff / studio) — graph-based candidates with the people/studio as the reason.
  3. Widen with MAL when asked for genres, popularity or novelty: `mal_top` (rankings filtered by genre, skips their list),
     `mal_recommendations` (MAL users' picks for an anime they loved), `mal_search`, `mal_season`. Results carry `on_list`.
  4. Answer. Explain *why* each pick fits (people, studio, genres, their scores for the related work) and call present_cards.
`fetch_from_mal` pulls any anime/person/character into the graph when you need details or connections that are missing.

Guidance:
- Prefer the dedicated tools; use cypher_read for anything they can't express. Keep queries small; always add LIMIT.
- Japanese is the default voice-actor language unless the user says otherwise (VOICES.language = 'Japanese').
- When the user asks to see something, call show_on_canvas with the relevant node refs so it appears in their graph view.
- When the answer is a set of characters or anime to choose between (e.g. picking three characters for a game),
  call present_cards with the node refs and a one-line caption each — do this in addition to a short text answer.
- Be concise. Use markdown lists; mention the anime and the user's score where relevant. Do not describe your tool calls.
"""

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "search", "description": "Full-text-ish search over titles/names. Returns node refs.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}, "kinds": {"type": "string", "description": "Comma list of Anime,Character,Person,Studio,Genre", "default": "Anime,Character,Person,Studio"}, "limit": {"type": "integer", "default": 8}}, "required": ["q"]}}},
    {"type": "function", "function": {"name": "node", "description": "Full properties of one node plus its relationship counts.", "parameters": {"type": "object", "properties": {"ref": {"type": "string", "description": "e.g. Anime:5114"}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "neighbors", "description": "1-hop neighbourhood of a node from the database.", "parameters": {"type": "object", "properties": {"ref": {"type": "string"}, "rels": {"type": "string", "description": "Comma list of LISTED,HAS_CHARACTER,VOICES,WORKED_ON,RELATED_TO,PRODUCED_BY,HAS_GENRE"}, "only_watched": {"type": "boolean", "default": False}, "lang": {"type": "string", "description": "VOICES language filter, e.g. Japanese"}, "limit": {"type": "integer", "default": 60}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "shortest_path", "description": "Shortest path between two nodes (BFS). rels limits which relationship types may be traversed.", "parameters": {"type": "object", "properties": {"from_ref": {"type": "string"}, "to_ref": {"type": "string"}, "max_hops": {"type": "integer", "default": 8}, "only_watched": {"type": "boolean", "default": False}, "rels": {"type": "string", "default": "VOICES,HAS_CHARACTER,WORKED_ON,RELATED_TO,PRODUCED_BY"}, "lang": {"type": "string", "default": "Japanese"}, "all_paths": {"type": "boolean", "default": False}}, "required": ["from_ref", "to_ref"]}}},
    {"type": "function", "function": {"name": "va_roles", "description": "Characters a voice actor plays, with the anime, filtered to the user's watched anime by default.", "parameters": {"type": "object", "properties": {"person_id": {"type": "integer"}, "only_watched": {"type": "boolean", "default": True}, "lang": {"type": "string", "default": "Japanese"}}, "required": ["person_id"]}}},
    {"type": "function", "function": {"name": "roster", "description": "Voice actors ranked by how many distinct characters they play in the user's watched anime.", "parameters": {"type": "object", "properties": {"min_characters": {"type": "integer", "default": 3}, "main_only": {"type": "boolean", "default": False}, "only_watched": {"type": "boolean", "default": True}, "lang": {"type": "string", "default": "Japanese"}, "q": {"type": "string"}, "limit": {"type": "integer", "default": 30}}}}},
    {"type": "function", "function": {"name": "people", "description": "Ranked people by anime count on the user's list. kind='va' or a staff position like 'Director', 'Music', 'Character Design', 'Original Creator', 'Series Composition'.", "parameters": {"type": "object", "properties": {"kind": {"type": "string", "default": "va"}, "statuses": {"type": "string", "default": "completed,watching,on_hold,dropped"}, "lang": {"type": "string", "default": "Japanese"}, "min_anime": {"type": "integer", "default": 2}, "limit": {"type": "integer", "default": 30}}}}},
    {"type": "function", "function": {"name": "gaps", "description": "Related anime (sequels, prequels, ...) of anime the user has seen that are NOT on their list.", "parameters": {"type": "object", "properties": {"statuses": {"type": "string", "default": "completed,watching,on_hold"}, "relations": {"type": "string", "default": "Sequel,Prequel"}}}}},
    {"type": "function", "function": {"name": "cypher_read", "description": "Run a read-only Cypher query (MATCH/RETURN; no writes). Max 200 rows. Nodes are returned as refs with key properties.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "params": {"type": "object", "description": "Query parameters", "additionalProperties": True}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "taste_profile", "description": "One-call summary of the user's taste: top voice actors, directors, composers, studios, genres (with their average score) and their highest-rated anime. Use this first for any recommendation or 'what do I like' question.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "recommendations", "description": "Graph-based recommendations: unseen anime ranked by how many of the user's favourite voice actors (via='va'), key staff (via='staff') or studios (via='studio') are involved, with the names as 'via'. Excludes sequels/prequels of seen anime.", "parameters": {"type": "object", "properties": {"via": {"type": "string", "enum": ["va", "staff", "studio"], "default": "va"}, "min_score": {"type": "number", "default": 7.0}, "types": {"type": "string", "default": "TV,Movie,ONA"}, "limit": {"type": "integer", "default": 20}}}}},
    {"type": "function", "function": {"name": "fetch_from_mal", "description": "Fetch a node from MyAnimeList into the graph (anime: metadata+characters+staff; person: full filmography; character: appearances+voice actors). Use when the graph lacks details or connections for something.", "parameters": {"type": "object", "properties": {"ref": {"type": "string", "description": "Anime:<id> | Person:<id> | Character:<id>"}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "mal_search", "description": "Search MyAnimeList by title (beyond the graph). Results include on_list (the user's status or null).", "parameters": {"type": "object", "properties": {"q": {"type": "string"}, "limit": {"type": "integer", "default": 15}}, "required": ["q"]}}},
    {"type": "function", "function": {"name": "mal_top", "description": "MyAnimeList rankings, optionally filtered by genre names client-side. ranking_type: all (top rated) | airing | upcoming | tv | movie | bypopularity | favorite. Scans up to `scan` top entries and returns those matching the filters, so use scan=500 for narrow genre filters.", "parameters": {"type": "object", "properties": {"ranking_type": {"type": "string", "default": "all"}, "genres": {"type": "string", "description": "Comma list of genre/theme names that must ALL be present, e.g. 'Mystery,Psychological'"}, "exclude_on_list": {"type": "boolean", "default": True}, "min_year": {"type": "integer"}, "scan": {"type": "integer", "default": 200}, "limit": {"type": "integer", "default": 20}}}}},
    {"type": "function", "function": {"name": "mal_recommendations", "description": "MyAnimeList users' 'if you liked X you might like Y' pairs for an anime, with vote counts.", "parameters": {"type": "object", "properties": {"anime_id": {"type": "integer"}}, "required": ["anime_id"]}}},
    {"type": "function", "function": {"name": "mal_season", "description": "Anime of a season, most popular first.", "parameters": {"type": "object", "properties": {"year": {"type": "integer"}, "season": {"type": "string", "description": "winter | spring | summer | fall"}, "limit": {"type": "integer", "default": 30}}, "required": ["year", "season"]}}},
    {"type": "function", "function": {"name": "show_on_canvas", "description": "Display these nodes (and the edges between them) in the user's graph view.", "parameters": {"type": "object", "properties": {"refs": {"type": "array", "items": {"type": "string"}}, "select": {"type": "string", "description": "Optional ref to select"}}, "required": ["refs"]}}},
    {"type": "function", "function": {"name": "present_cards", "description": "Show a card grid (image, name, caption) — use for sets of characters/anime the user should look at or choose between.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "cards": {"type": "array", "items": {"type": "object", "properties": {"ref": {"type": "string"}, "caption": {"type": "string"}}, "required": ["ref"]}}}, "required": ["cards"]}}},
]


# --------------------------------------------------------------------------- tool execution

def _compact_node(n: dict[str, Any]) -> dict[str, Any]:
    """Trim a node payload for the model (no images / long text)."""
    out = {"ref": n["id"], "name": n["name"]}
    for k in ("watched", "list_status"):
        if n.get(k) is not None:
            out[k] = n[k]
    for k in ("year", "type", "score", "my_score", "episodes", "favorites", "kind"):
        v = n["props"].get(k)
        if v not in (None, ""):
            out[k] = v
    if not n.get("fetched", True):
        out["stub"] = True
    return out


def _compact_payload(p: dict[str, Any], limit_nodes: int = 80) -> dict[str, Any]:
    nodes = [_compact_node(n) for n in p["nodes"][:limit_nodes]]
    edges = [{"from": e["source"], "to": e["target"], "type": e["type"], **{k: v for k, v in e["props"].items() if k in ("role", "language", "relation", "status", "score", "positions")}} for e in p["edges"][:200]]
    out: dict[str, Any] = {"nodes": nodes, "edges": edges}
    for k in ("found", "hops", "paths", "roles", "center"):
        if k in p:
            out[k] = p[k]
    if len(p["nodes"]) > limit_nodes:
        out["truncated_nodes"] = len(p["nodes"]) - limit_nodes
    return out


def _cypher_value(v: Any) -> Any:
    from neo4j.graph import Node, Path, Relationship

    if isinstance(v, Node):
        return _compact_node(node_payload(v))
    if isinstance(v, Relationship):
        from .api.serialize import edge_payload
        e = edge_payload(v)
        return {"from": e["source"], "to": e["target"], "type": e["type"], **e["props"]}
    if isinstance(v, Path):
        return [_cypher_value(n) for n in v.nodes]
    if isinstance(v, list):
        return [_cypher_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _cypher_value(x) for k, x in v.items()}
    return v


# Lists are private, but the graph is shared, so the agent's free-form Cypher is checked in two layers.
# 1. The text may name users or lists only as the current user's own anchor pattern below.
OWN_LIST = re.compile(r"\(\s*\w*\s*:\s*User\s*\{\s*username\s*:\s*\$user\s*\}\s*\)(\s*-\s*\[\s*\w*\s*:\s*LISTED\s*\]\s*->)?", re.I)
OTHER_USERS = re.compile(r"\b(User|LISTED|username)\b", re.I)
# 2. The query plan may not reach a user node any other way. User nodes connect only through LISTED, so it is enough
#    that every scan has a label, every relationship step has a type, and nothing looks nodes up by internal id or
#    calls a procedure (procedures can return any node).
PLAN_FORBIDDEN = re.compile(r"\b(ScanAllById|ScanAllByEdgeId|CallProcedure)\b")
PLAN_STEP = re.compile(r"\b(Expand|ExpandVariable|BFSExpand|DFSExpand|WeightedShortestPath|AllShortestPath|ScanAllByEdge\w*)\b")
PLAN_SCAN = re.compile(r"\bScanAll \((\w+)\)")
PRIVACY_HINT = ("Write MATCH patterns with a label on every node you start from, e.g. (a:Anime), and a type on every "
                "relationship, e.g. -[:HAS_CHARACTER]->. Reach the user's list only as (u:User {username: $user})-[l:LISTED]->(a:Anime).")


def check_private(query: str, params: dict[str, Any]) -> None:
    """Raise ValueError unless the query can only see the current user's list (see the two layers above)."""
    if OTHER_USERS.search(OWN_LIST.sub("", query)):
        raise ValueError("user lists are private. " + PRIVACY_HINT)
    plan = [str(list(r.values())[0]) for r in db.run("EXPLAIN " + query, **params)]
    for line in plan:
        if PLAN_FORBIDDEN.search(line):
            raise ValueError("lookups by internal id and procedure calls are not allowed. " + PRIVACY_HINT)
        if PLAN_STEP.search(line) and not re.search(r"\[\w+:\w", line):
            raise ValueError("every relationship needs a type. " + PRIVACY_HINT)
    for var in set(PLAN_SCAN.findall("\n".join(plan))):
        scans = sum(line.count(f"ScanAll ({var})") for line in plan)
        labelled = sum(1 for line in plan if re.search(rf"\bFilter\b.*\({re.escape(var)} :\w", line))
        if labelled < scans:
            raise ValueError(f"every node you start from needs a label, and ({var}) has none. " + PRIVACY_HINT)


# Queries the guard must refuse and accept. If an upgrade changes how Memgraph words its plans, the self-test
# notices at startup and free-form Cypher stays off rather than letting the guard fail open.
_MUST_REFUSE = [
    "MATCH (n) WHERE n.status IS NOT NULL RETURN n LIMIT 1",
    "MATCH (a:Anime)-[r]-(x) RETURN properties(r) LIMIT 1",
    "MATCH (a:Anime)-[*1..2]-(f) RETURN f LIMIT 1",
    "MATCH p=(a:Anime {mal_id: 1})-[*BFS ..3]-(b:Anime {mal_id: 2}) RETURN p",
    "MATCH (n) WHERE id(n) = 0 RETURN n",
    "CALL pagerank.get() YIELD node RETURN node LIMIT 1",
    "MATCH (a:Anime) RETURN [(a)-[r]-(x) | properties(r)] AS xs LIMIT 1",
    "MATCH (n) WHERE n:Anime OR n.x IS NOT NULL RETURN n LIMIT 1",
    "MATCH (a:Anime) WITH count(a) AS c MATCH (a) RETURN a LIMIT 1",
]
_MUST_ACCEPT = [
    "MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) RETURN a.title LIMIT 1",
    "MATCH (a:Anime)-[:HAS_CHARACTER]->(c)<-[v:VOICES]-(p:Person) RETURN p.name LIMIT 1",
    "MATCH (a:Anime {mal_id: 1})-[:RELATED_TO *BFS 0..6]-(f:Anime) RETURN f.title LIMIT 1",
]
_guard_ok: bool | None = None  # None until the self-test has run


def guard_self_test() -> bool:
    """Check the privacy guard against known queries. Free-form Cypher is only allowed once this has passed."""
    global _guard_ok
    params = {"user": "\u0000self-test"}
    ok = True
    for q in _MUST_REFUSE:
        try:
            check_private(q, params)
            log.error("Ask privacy guard let through %r; free-form Cypher is off", q)
            ok = False
        except ValueError:
            pass
        except Exception as e:  # noqa: BLE001 - a query Memgraph can't plan is refused anyway
            log.debug("self-test query failed to plan: %s", e)
    for q in _MUST_ACCEPT:
        try:
            check_private(q, params)
        except Exception as e:  # noqa: BLE001
            log.error("Ask privacy guard refused a safe query %r (%s); free-form Cypher is off", q, e)
            ok = False
    _guard_ok = ok
    return ok


def cypher_read(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if _guard_ok is None:
        guard_self_test()
    if not _guard_ok:
        raise ValueError("free-form Cypher is unavailable on this server right now; answer with the other tools")
    if FORBIDDEN.search(query):
        raise ValueError("only read queries are allowed (no CREATE/MERGE/SET/DELETE/...)")
    params = {**(params or {}), **users.params_for(query)}  # the current user's values always win
    check_private(query, params)
    rows = []
    with db.get_driver().session() as session:
        for rec in session.run(query, **params):
            rows.append({k: _cypher_value(v) for k, v in rec.items()})
            if len(rows) >= MAX_ROWS:
                break
    return {"rows": rows, "count": len(rows), "truncated": len(rows) >= MAX_ROWS}


def _subgraph(refs: list[str]) -> dict[str, Any]:
    """Nodes for these refs plus every edge between them."""
    parsed = [R._parse_ref(r) for r in refs]
    builder = PayloadBuilder()
    with db.get_driver().session() as session:
        for label, key in parsed:
            q = Q.NODE_USER if label == "User" else Q.NODE % label
            for rec in session.run(q, id=key):
                builder.add(rec["n"])
        ids = [k for label, k in parsed if label != "User"]
        wanted = set(builder.nodes)
        # Return the endpoint nodes too: relationship-only results carry unlabelled node stubs.
        for rec in session.run("MATCH (a)-[r]->(b) WHERE a.mal_id IN $ids AND b.mal_id IN $ids RETURN a, r, b", ids=ids):
            if R.node_id_of(rec["a"]) in wanted and R.node_id_of(rec["b"]) in wanted:
                builder.add(rec["r"])
    return builder.build()


def _annotate_on_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ul = users.user_list()
    for i in items:
        status, score = ul.personal(i["mal_id"])
        i["on_list"] = status
        if score:
            i["my_score"] = score
    return items


def _compact_mal_anime(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": f"Anime:{a['id']}", "mal_id": a["id"], "title": a.get("title"), "type": a.get("media_type"),
        "year": (a.get("start_season") or {}).get("year"), "episodes": a.get("num_episodes") or None,
        "score": a.get("mean"), "members": a.get("num_list_users"), "status": a.get("status"),
        "genres": [g["name"] for g in a.get("genres") or []][:6],
        "studios": [s["name"] for s in a.get("studios") or []][:2],
    }


def _mal_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "mal_search":
        return _annotate_on_list([_compact_mal_anime(a) for a in mal.search_anime(args["q"], int(args.get("limit") or 15))])
    if name == "mal_recommendations":
        d = mal.anime_details(int(args["anime_id"]), fields="id,title,recommendations")
        items = [{"ref": f"Anime:{r['node']['id']}", "mal_id": r["node"]["id"], "title": r["node"].get("title"), "votes": r.get("num_recommendations")} for r in d.get("recommendations") or []]
        return _annotate_on_list(items[:20])
    if name == "mal_season":
        items = [_compact_mal_anime(a) for a in mal.season(int(args["year"]), args["season"], int(args.get("limit") or 30))]
        return _annotate_on_list(items)
    # mal_top: scan the ranking and filter client-side
    scan = min(int(args.get("scan") or 200), 500)
    want = {g.strip().lower() for g in (args.get("genres") or "").split(",") if g.strip()}
    items = _annotate_on_list([_compact_mal_anime(a) for a in mal.ranking(args.get("ranking_type") or "all", scan)])
    out = []
    for i in items:
        if want and not want.issubset({g.lower() for g in i["genres"]}):
            continue
        if args.get("exclude_on_list", True) and i["on_list"]:
            continue
        if args.get("min_year") and (i["year"] or 0) < int(args["min_year"]):
            continue
        out.append(i)
    return out[: int(args.get("limit") or 20)]


def taste_profile() -> dict[str, Any]:
    statuses = "completed,watching,on_hold,dropped"
    out: dict[str, Any] = {}
    for key, kind in (("voice_actors", "va"), ("directors", "Director"), ("composers", "Music"), ("character_designers", "Character Design"), ("original_creators", "Original Creator")):
        r = R.insights_people(kind=kind, statuses=statuses, lang="Japanese" if kind == "va" else None, min_anime=2, limit=8)
        out[key] = [{"ref": x["person"]["id"], "name": x["person"]["name"], "anime": len(x["anime_ids"]), "avg_my_score": round(x["avg_my_score"], 1) if x["avg_my_score"] else None} for x in r["people"]]
    out["studios"] = users.run("""
        MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime)-[:PRODUCED_BY]->(s:Studio) WHERE l.status <> 'plan_to_watch'
        WITH s, count(DISTINCT a) AS n, avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg
        RETURN s.name AS name, n AS anime, round(avg * 10) / 10 AS avg_my_score ORDER BY n DESC LIMIT 8""")
    out["genres"] = users.run("""
        MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime)-[:HAS_GENRE]->(g:Genre) WHERE l.status <> 'plan_to_watch' AND g.kind <> 'explicit'
        WITH g, count(DISTINCT a) AS n, avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg
        RETURN g.name AS name, n AS anime, round(avg * 10) / 10 AS avg_my_score ORDER BY n DESC LIMIT 12""")
    out["top_rated"] = users.run("""
        MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) WHERE l.score >= 9
        RETURN 'Anime:' + toString(a.mal_id) AS ref, a.title AS title, l.score AS my_score, a.year AS year ORDER BY l.score DESC, a.members DESC LIMIT 20""")
    out["counts"] = users.run("MATCH (u:User {username: $user})-[l:LISTED]->(a:Anime) RETURN l.status AS status, count(*) AS n ORDER BY n DESC")
    return out


class ToolContext:
    """Collects UI side-effects (canvas payloads, cards) produced during one turn."""

    def __init__(self) -> None:
        self.canvas: list[dict[str, Any]] = []
        self.cards: list[dict[str, Any]] = []


def execute_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> Any:
    if name == "search":
        r = R.search(q=args["q"], kinds=args.get("kinds") or "Anime,Character,Person,Studio", limit=int(args.get("limit") or 8))
        return {k: [_compact_node(n) for n in v] for k, v in r["results"].items() if v}
    if name == "node":
        r = R.node_detail(args["ref"])
        n = _compact_node(r["node"])
        n["props"] = {k: v for k, v in r["node"]["props"].items() if k not in ("synopsis", "about", "image_url", "url") and v not in (None, "")}
        n["degrees"] = r["degrees"]
        return n
    if name == "neighbors":
        p = R.neighbors(args["ref"], rels=args.get("rels") or ",".join(Q.REL_TYPES), only_watched=bool(args.get("only_watched")), lang=args.get("lang"), limit=int(args.get("limit") or 60))
        return _compact_payload(p)
    if name == "shortest_path":
        p = R.path(from_=args["from_ref"], to=args["to_ref"], max_hops=int(args.get("max_hops") or 8), only_watched=bool(args.get("only_watched")),
                   exclude="User,Genre", rels=args.get("rels") or "VOICES,HAS_CHARACTER,WORKED_ON,RELATED_TO,PRODUCED_BY", lang=args.get("lang") or "Japanese",
                   all_paths=bool(args.get("all_paths")), limit=10)
        return _compact_payload(p)
    if name == "va_roles":
        p = R.person_characters(int(args["person_id"]), only_watched=args.get("only_watched", True), lang=args.get("lang") or "Japanese")
        return {"roles": [{"character": _compact_node(r["character"]), "anime": _compact_node(r["anime"]), "role": r["role"], "language": r["language"]} for r in p["roles"]]}
    if name == "roster":
        r = R.roster(only_watched=args.get("only_watched", True), main_only=bool(args.get("main_only")), lang=args.get("lang") or "Japanese",
                     min_characters=int(args.get("min_characters") or 3), q=args.get("q"), limit=int(args.get("limit") or 30))
        return [{"person": _compact_node(x["person"]), "characters": x["characters"], "anime": x["anime"]} for x in r["people"]]
    if name == "people":
        r = R.insights_people(kind=args.get("kind") or "va", statuses=args.get("statuses"), lang=args.get("lang") or "Japanese", min_anime=int(args.get("min_anime") or 2), limit=int(args.get("limit") or 30))
        return [{"person": _compact_node(x["person"]), "anime_count": len(x["anime_ids"]), "anime_ids": x["anime_ids"][:20], "characters": x["characters"], "avg_my_score": x["avg_my_score"]} for x in r["people"]]
    if name == "gaps":
        r = R.insights_gaps(statuses=args.get("statuses") or "completed,watching,on_hold", relations=args.get("relations") or "Sequel,Prequel")
        return [{"ref": f"Anime:{g['mal_id']}", "title": g["title"], "score": g["score"], "year": g["year"], "via": g["via"][:3]} for g in r["gaps"][:60]]
    if name == "cypher_read":
        return cypher_read(args["query"], args.get("params"))
    if name == "taste_profile":
        return taste_profile()
    if name == "recommendations":
        r = R.insights_recommendations(via=args.get("via") or "va", lang="Japanese", min_score=args.get("min_score", 7.0), types=args.get("types") or "TV,Movie,ONA", limit=int(args.get("limit") or 20))
        return [{"anime": _compact_node(x["anime"]), "score": x["score"], "via": x["via"], "n_people": x["n_people"]} for x in r["recommendations"]]
    if name == "fetch_from_mal":
        label, key = R._parse_ref(args["ref"])
        fn = {"Anime": ingest.expand_anime, "Person": ingest.expand_person, "Character": ingest.expand_character}.get(label)
        if fn is None:
            raise ValueError("only Anime, Person and Character can be fetched")
        summary = fn(R.jikan(), key)
        n = R.node_detail(args["ref"])["node"]
        return {"fetched": _compact_node(n), **summary}
    if name in ("mal_search", "mal_top", "mal_recommendations", "mal_season"):
        return _mal_tool(name, args)
    if name == "show_on_canvas":
        p = _subgraph(args["refs"][:150])
        if not p["nodes"]:
            raise ValueError("no refs resolved; use refs like Anime:<mal_id> / Person:<mal_id> from tool results")
        if args.get("select"):
            p["select"] = args["select"]
        ctx.canvas.append(p)
        return {"shown": len(p["nodes"]), "edges": len(p["edges"])}
    if name == "present_cards":
        p = _subgraph([c["ref"] for c in args["cards"][:24]])
        by_id = {n["id"]: n for n in p["nodes"]}
        cards = [{"node": by_id[c["ref"]], "caption": c.get("caption", "")} for c in args["cards"] if c["ref"] in by_id]
        missing = [c["ref"] for c in args["cards"] if c["ref"] not in by_id]
        if not cards:
            raise ValueError(f"no cards resolved; refs must be like Character:<mal_id> taken from tool results (got {missing[:5]})")
        ctx.cards.append({"title": args.get("title", ""), "cards": cards})
        return {"presented": len(cards), **({"unresolved": missing} if missing else {})}
    raise ValueError(f"unknown tool {name}")


# --------------------------------------------------------------------------- sessions + loop

CONV_DIR = settings.conversations_dir  # one folder per user: CONV_DIR/<username, lower case>/<id>.json
_sessions: dict[tuple[str, str], dict[str, Any]] = {}  # hot cache keyed by (user folder, conversation id)


def _user_dir() -> Path:
    username = users.current_username()
    if not username:
        raise PermissionError("sign in first")
    return CONV_DIR / username.lower()


def _conv_path(cid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", cid):
        raise ValueError("bad conversation id")
    return _user_dir() / f"{cid}.json"


def _key(cid: str) -> tuple[str, str]:
    return (_user_dir().name, cid)


def forget_conversations(username: str) -> None:
    """Delete a user's conversations and Ask usage (the whole folder)."""
    folder = CONV_DIR / username.lower()
    for key in [k for k in _sessions if k[0] == folder.name]:
        _sessions.pop(key, None)
    if folder.exists():
        shutil.rmtree(folder)


def migrate_conversations() -> int:
    """Conversations from before they were per user belong to MAL_USERNAME. Returns how many were moved."""
    if not settings.mal_username or not CONV_DIR.exists():
        return 0
    dest = CONV_DIR / settings.mal_username.lower()
    moved = 0
    for path in CONV_DIR.glob("*.json"):
        dest.mkdir(parents=True, exist_ok=True)
        path.replace(dest / path.name)
        moved += 1
    return moved


def _new_conversation(cid: str) -> dict[str, Any]:
    now = time.time()
    return {"id": cid, "title": "", "model": settings.openrouter_model, "created_at": now, "updated_at": now, "messages": [], "turns": []}


def load_conversation(cid: str) -> dict[str, Any] | None:
    key = _key(cid)
    if key in _sessions:
        return _sessions[key]
    path = _conv_path(cid)
    if path.exists():
        conv = json.loads(path.read_text())
        _sessions[key] = conv
        return conv
    return None


def save_conversation(conv: dict[str, Any]) -> None:
    path = _conv_path(conv["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    conv["updated_at"] = time.time()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(conv, ensure_ascii=False, default=str))
    tmp.replace(path)
    _sessions[_key(conv["id"])] = conv


def list_conversations() -> list[dict[str, Any]]:
    out = []
    folder = _user_dir()
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                c = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if "id" not in c:
                continue  # usage.json lives here too
            out.append({"id": c["id"], "title": c.get("title") or "(untitled)", "model": c.get("model"), "updated_at": c["updated_at"], "turns": len(c.get("turns", []))})
    return sorted(out, key=lambda c: -c["updated_at"])


def delete_conversation(cid: str) -> bool:
    _sessions.pop(_key(cid), None)
    path = _conv_path(cid)
    if path.exists():
        path.unlink()
        return True
    return False


def rename_conversation(cid: str, title: str) -> dict[str, Any] | None:
    conv = load_conversation(cid)
    if conv is None:
        return None
    conv["title"] = title.strip()[:120]
    save_conversation(conv)
    return conv


def _session(session_id: str | None) -> tuple[str, dict[str, Any], bool]:
    """Returns (id, conversation, resumed). Unknown ids start a fresh conversation under a new id."""
    if session_id:
        conv = load_conversation(session_id)
        if conv is not None:
            return session_id, conv, bool(conv["messages"])
    cid = uuid.uuid4().hex
    conv = _new_conversation(cid)
    _sessions[_key(cid)] = conv
    return cid, conv, False


def configured() -> bool:
    return bool(settings.openrouter_api_key)


async def run(session_id: str | None, user_message: str) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn; yields UI events (tool_call, tool_result, canvas, cards, answer, done, error)."""
    if not configured():
        yield {"type": "error", "message": "OPENROUTER_API_KEY is not configured on the server"}
        return
    sid, conv, resumed = _session(session_id)
    # Unknown/expired session ids start a new conversation; the UI shows a notice when that happens mid-chat.
    yield {"type": "session", "id": sid, "model": settings.openrouter_model, "resumed": resumed}
    client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base,
                         default_headers={"HTTP-Referer": "https://github.com/djhoomin/MAL-Graph", "X-Title": "MAL-Graph"})
    system = SYSTEM_PROMPT.format(username=users.current_username() or "the user")
    messages: list[dict[str, Any]] = conv["messages"]
    messages.append({"role": "user", "content": user_message})
    if not conv["title"]:
        conv["title"] = user_message.strip()[:80]
    turn: dict[str, Any] = {"role": "assistant", "text": "", "steps": [], "cards": [], "usage": None, "error": None}
    conv["turns"].append({"role": "user", "text": user_message, "steps": [], "cards": []})
    conv["turns"].append(turn)
    ctx = ToolContext()
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    # OpenRouter sticky sessions: route every request of a conversation to the same provider so prompt caching
    # (automatic on DeepSeek/OpenAI; cache_control breakpoints on Anthropic) actually hits.
    extra_body = {"session_id": sid, "cache_control": {"type": "ephemeral"}}

    try:
        for _ in range(MAX_STEPS):
            resp = await client.chat.completions.create(
                model=settings.openrouter_model, messages=[{"role": "system", "content": system}, *messages],
                tools=TOOLS, tool_choice="auto", max_tokens=4000, extra_body=extra_body,
            )
            if resp.usage:
                usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
                usage["completion_tokens"] += resp.usage.completion_tokens or 0
                details = getattr(resp.usage, "prompt_tokens_details", None)
                usage["cached_tokens"] += (getattr(details, "cached_tokens", None) or 0) if details else 0
            msg = resp.choices[0].message
            messages.append({"role": "assistant", "content": msg.content or "", **({"tool_calls": [tc.model_dump() for tc in msg.tool_calls]} if msg.tool_calls else {})})
            if not msg.tool_calls:
                turn["text"] = msg.content or ""
                yield {"type": "answer", "text": turn["text"]}
                break
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                step = {"name": name, "args": args}
                turn["steps"].append(step)
                yield {"type": "tool_call", "name": name, "args": args}
                try:
                    result = await asyncio.to_thread(execute_tool, name, args, ctx)
                    content = json.dumps(result, ensure_ascii=False, default=str)
                    if len(content) > 60_000:
                        content = content[:60_000] + '... (truncated)"}'
                except Exception as e:  # noqa: BLE001 - report tool failures to the model
                    content = json.dumps({"error": str(e)})
                    step["error"] = str(e)
                    yield {"type": "tool_error", "name": name, "message": str(e)}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                while ctx.canvas:
                    yield {"type": "canvas", "payload": ctx.canvas.pop(0)}
                while ctx.cards:
                    group = ctx.cards.pop(0)
                    turn["cards"].append(group)
                    yield {"type": "cards", **group}
        else:
            turn["text"] = "I ran out of steps before finishing — try a narrower question."
            yield {"type": "answer", "text": turn["text"]}
    except Exception as e:  # noqa: BLE001
        turn["error"] = f"{type(e).__name__}: {e}"
        yield {"type": "error", "message": turn["error"]}
    # keep the model transcript bounded (the rendered turns are kept in full)
    if len(messages) > 60:
        del messages[: len(messages) - 60]
        while messages and messages[0]["role"] != "user":
            del messages[0]
    turn["usage"] = usage
    save_conversation(conv)
    yield {"type": "done", "usage": usage}
