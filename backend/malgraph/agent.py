"""'Ask the graph': a tool-using agent over the graph API, run through OpenRouter (OpenAI-compatible)."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from . import db
from .config import settings
from .api import queries as Q
from .api import routes as R
from .api.serialize import PayloadBuilder, node_payload

MAX_STEPS = 16
MAX_ROWS = 200
FORBIDDEN = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|INDEX|CONSTRAINT|LOAD\s+CSV|IMPORT|ALTER|STORAGE\s+MODE|FREE\s+MEMORY|CREATE\s+TRIGGER)\b", re.I)

SYSTEM_PROMPT = """You are the guide for MAL-Graph, a personal graph of one MyAnimeList user's anime list, stored in Memgraph.
The user is {username}. Answer their questions by exploring the graph with the tools; never invent data.

Graph model (all ids are MAL ids; node refs look like "Anime:5114", "Character:12", "Person:8", "Studio:4", "Genre:1"):
  (:User {{username}})-[:LISTED {{status, score, episodes_watched}}]->(:Anime)
  (:Anime {{mal_id, title, title_english, type, episodes, year, season, score, members, list_status, my_score, watched, fetched_at}})
  (:Anime)-[:HAS_CHARACTER {{role: 'Main'|'Supporting'}}]->(:Character {{mal_id, name, image_url, favorites}})
  (:Person {{mal_id, name, image_url}})-[:VOICES {{language, anime_ids}}]->(:Character)
  (:Person)-[:WORKED_ON {{positions: [..]}}]->(:Anime)      e.g. positions contain 'Director', 'Music', 'Character Design'
  (:Anime)-[:RELATED_TO {{relation: 'Sequel'|'Prequel'|'Side Story'|...}}]->(:Anime)
  (:Anime)-[:PRODUCED_BY]->(:Studio {{mal_id, name}})      (:Anime)-[:HAS_GENRE]->(:Genre {{mal_id, name, kind}})
List statuses: completed, watching, on_hold, dropped, plan_to_watch. "watched"/"seen" means status <> plan_to_watch (Anime.watched = true).
Anime with fetched_at IS NULL are stubs known only by title (sequels etc. not on the list); persons/characters can be stubs too.
Only anime on the user's list have been fully fetched, so a voice actor's roles are only known for those anime.

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


def cypher_read(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if FORBIDDEN.search(query):
        raise ValueError("only read queries are allowed (no CREATE/MERGE/SET/DELETE/...)")
    rows = []
    with db.get_driver().session() as session:
        for rec in session.run(query, **(params or {})):
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

_sessions: dict[str, dict[str, Any]] = {}


def _session(session_id: str | None) -> tuple[str, dict[str, Any]]:
    now = time.time()
    for sid in [s for s, v in _sessions.items() if now - v["updated"] > 3 * 3600]:
        del _sessions[sid]
    sid = session_id or uuid.uuid4().hex
    sess = _sessions.setdefault(sid, {"messages": [], "updated": now})
    sess["updated"] = now
    return sid, sess


def configured() -> bool:
    return bool(settings.openrouter_api_key)


async def run(session_id: str | None, user_message: str) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn; yields UI events (tool_call, tool_result, canvas, cards, answer, done, error)."""
    if not configured():
        yield {"type": "error", "message": "OPENROUTER_API_KEY is not configured on the server"}
        return
    sid, sess = _session(session_id)
    # If the client sent a session id we no longer have (restart / expiry), say so — the model starts fresh.
    yield {"type": "session", "id": sid, "model": settings.openrouter_model, "resumed": bool(session_id) and sid == session_id and bool(sess["messages"])}
    client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base,
                         default_headers={"HTTP-Referer": "https://github.com/djhoomin/MAL-Graph", "X-Title": "MAL-Graph"})
    system = SYSTEM_PROMPT.format(username=settings.mal_username or "the user")
    messages: list[dict[str, Any]] = sess["messages"]
    messages.append({"role": "user", "content": user_message})
    ctx = ToolContext()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    try:
        for _ in range(MAX_STEPS):
            resp = await client.chat.completions.create(
                model=settings.openrouter_model, messages=[{"role": "system", "content": system}, *messages],
                tools=TOOLS, tool_choice="auto", max_tokens=4000,
            )
            if resp.usage:
                usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
                usage["completion_tokens"] += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            messages.append({"role": "assistant", "content": msg.content or "", **({"tool_calls": [tc.model_dump() for tc in msg.tool_calls]} if msg.tool_calls else {})})
            if not msg.tool_calls:
                yield {"type": "answer", "text": msg.content or ""}
                break
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_call", "name": name, "args": args}
                try:
                    result = await asyncio.to_thread(execute_tool, name, args, ctx)
                    content = json.dumps(result, ensure_ascii=False, default=str)
                    if len(content) > 60_000:
                        content = content[:60_000] + '... (truncated)"}'
                except Exception as e:  # noqa: BLE001 - report tool failures to the model
                    content = json.dumps({"error": str(e)})
                    yield {"type": "tool_error", "name": name, "message": str(e)}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                while ctx.canvas:
                    yield {"type": "canvas", "payload": ctx.canvas.pop(0)}
                while ctx.cards:
                    yield {"type": "cards", **ctx.cards.pop(0)}
        else:
            yield {"type": "answer", "text": "I ran out of steps before finishing — try a narrower question."}
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
    # keep the transcript bounded
    if len(messages) > 60:
        del messages[: len(messages) - 60]
        while messages and messages[0]["role"] != "user":
            del messages[0]
    yield {"type": "done", "usage": usage}
