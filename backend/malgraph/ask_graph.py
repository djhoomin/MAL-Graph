"""Ask the graph, as a LangGraph agent.

The graph has four nodes:

    START -> agent -> (tool calls, within the budget?) -> tools -> agent -> ...
                   -> (tool calls past the budget?) -> out_of_steps -> agent
                   -> (empty reply, first time?) -> nudge -> agent
                   -> END

`agent` calls the model through OpenRouter with the tools bound. `tools` runs the tool calls of one reply in parallel
on worker threads, which copy the request's context (the user and their choice of titles). A turn may make MAX_STEPS
tool calls. Calls past that aren't run: `out_of_steps` answers the reply's calls with a note that the budget is used
up, and the model then answers with tools switched off, from what it found. `nudge` handles a quirk of reasoning
models: they sometimes spend their whole token budget thinking and reply with nothing or with an answer cut off, so the
graph asks once for the answer before giving up.

The graph is compiled once. What changes per turn travels as the run's context (AskContext): the system prompt, the
conversation id that keeps OpenRouter on one provider, and the turn's ToolContext, which collects what tools show in
the UI (show_on_canvas, present_cards).

Conversations are LangGraph threads. Their messages live in a SQLite checkpointer next to the conversation files,
keyed by user and conversation. The model sees the current turn in full, and only the questions and answers of earlier
turns, since their tool results can be tens of thousands of characters each.

With LANGSMITH_TRACING on and a LANGSMITH_API_KEY, runs of the users listed in LANGSMITH_TRACE_USERS are traced to
LangSmith. Nobody else's questions or lists leave the server that way.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from typing import Any

import aiosqlite
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.runtime import Runtime

from .config import settings

log = logging.getLogger(__name__)

EARLIER_TURNS = 10  # earlier questions and answers the model sees
EARLIER_CHARS = 30_000  # and at most this many characters of them
MAX_RESULT = 60_000  # characters of a tool result passed back to the model
MAX_STEPS = 20  # tool calls a turn may make before the model must answer
# Thinking a reply may do, out of make_model's max_tokens. Without a cap GLM 5.3 sometimes thinks through all of it.
REASONING_TOKENS = int(os.getenv("ASK_REASONING_TOKENS", "3000"))
NUDGE = "Please write your answer now, from the results you already have. List the results themselves."
OUT_OF_STEPS = ("Not run: this question has used all its tool calls. Answer now from the results you already have, "
                "and say briefly what you couldn't check.")


@dataclass
class AskContext:
    system: str  # the system prompt, which names the user
    session_id: str  # the conversation, for OpenRouter's sticky sessions
    turn: Any  # agent.ToolContext: the UI side effects of this turn


class AskState(MessagesState):
    nudged: bool  # asked once for an answer after an empty reply, reset every turn
    steps: int  # tool calls the model has made this turn, reset every turn
    stopped: bool  # the model was told its tool calls are used up, reset every turn


def make_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base,
        max_tokens=8000,  # reasoning models spend much of it thinking (GLM 5.3 cut an answer off at 4000)
        stream_usage=True,
        default_headers={"HTTP-Referer": "https://aniweb.eu", "X-Title": "Aniweb"},
    )


DISPLAY_TOOLS = {"show_on_canvas", "present_cards"}


def shown_with(m: BaseMessage) -> str:
    """The text of a reply that only calls display tools. Models often write their whole answer and then call
    show_on_canvas, so this text is part of the answer, not a preamble."""
    if isinstance(m, AIMessage) and m.tool_calls and all(c["name"] in DISPLAY_TOOLS for c in m.tool_calls):
        return m.text.strip()
    return ""


def cut_off(m: BaseMessage) -> bool:
    """A reply that ran out of tokens before it finished its answer. Streamed replies can repeat the finish reason
    ("lengthlength"), so this looks for it inside the string."""
    return (isinstance(m, AIMessage) and not m.tool_calls
            and "length" in str(m.response_metadata.get("finish_reason") or ""))


def history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """What the model sees of a thread: the current turn in full, from its question on, and before it only questions
    and final answers, the last EARLIER_TURNS of them within EARLIER_CHARS."""
    start = next((i for i in range(len(messages) - 1, -1, -1)
                  if isinstance(messages[i], HumanMessage) and messages[i].text != NUDGE), 0)
    earlier: list[BaseMessage] = []
    for m in messages[:start]:
        if isinstance(m, HumanMessage) and m.text != NUDGE:
            earlier.append(HumanMessage(m.text))
        elif isinstance(m, AIMessage) and not m.tool_calls and m.text.strip():
            earlier.append(AIMessage(m.text))
        elif shown_with(m):  # an answer written before showing it, merged with what followed
            earlier.append(AIMessage(shown_with(m)))
    kept: list[BaseMessage] = []
    chars = 0
    for m in reversed(earlier):
        chars += len(m.text)
        if chars > EARLIER_CHARS or sum(isinstance(k, HumanMessage) for k in kept) >= EARLIER_TURNS:
            break
        kept.insert(0, m)
    while kept and not isinstance(kept[0], HumanMessage):  # start on a question
        kept.pop(0)
    return kept + messages[start:]


def _run_tool(name: str, args: dict[str, Any], turn: Any, call_id: str) -> str:
    from .agent import execute_tool, trail  # agent imports this module

    result = execute_tool(name, args, turn)
    content = json.dumps(result, ensure_ascii=False, default=str)
    try:  # the UI's picture of what the step found, which must never fail the step itself
        found = trail(name, args, content)
        if found:
            turn.trail.append({"id": call_id, **found})
    except Exception:  # noqa: BLE001
        log.exception("trail for %s failed", name)
    return content if len(content) <= MAX_RESULT else content[:MAX_RESULT] + '... (truncated)"}'


def build(specs: list[dict[str, Any]], checkpointer: AsyncSqliteSaver | None):
    """The agent graph, over tools given as OpenAI-style function specs (agent.TOOLS)."""
    model = make_model()
    bound = model.bind_tools(specs, tool_choice="auto")
    # Past the budget the tools stay declared, since the messages refer to them, but the model may not call them.
    answer_only = model.bind_tools(specs, tool_choice="none")

    async def agent(state: AskState, config: RunnableConfig, runtime: Runtime[AskContext]) -> dict[str, Any]:
        steps = state.get("steps") or 0
        llm = (answer_only if steps > MAX_STEPS else bound).bind(
            # OpenRouter sticky sessions: every request of a conversation goes to the same provider, so caching hits.
            extra_body={"session_id": runtime.context.session_id, "cache_control": {"type": "ephemeral"},
                        "reasoning": {"max_tokens": REASONING_TOKENS}})
        reply = await llm.ainvoke([SystemMessage(runtime.context.system), *history(state["messages"])], config)
        return {"messages": [reply], "steps": steps + len(reply.tool_calls)}

    async def tools(state: AskState, runtime: Runtime[AskContext]) -> dict[str, Any]:
        calls = state["messages"][-1].tool_calls

        async def one(call: dict[str, Any]) -> ToolMessage:
            try:
                content = await asyncio.to_thread(_run_tool, call["name"], call["args"], runtime.context.turn,
                                                  call["id"] or "")
                return ToolMessage(content, tool_call_id=call["id"], name=call["name"])
            except Exception as e:  # noqa: BLE001
                return ToolMessage(f"Error: {e}", tool_call_id=call["id"], name=call["name"], status="error")

        return {"messages": list(await asyncio.gather(*(one(c) for c in calls)))}

    def nudge(state: AskState) -> dict[str, Any]:
        return {"messages": [HumanMessage(NUDGE)], "nudged": True}

    def out_of_steps(state: AskState) -> dict[str, Any]:
        last = state["messages"][-1]
        return {"messages": [ToolMessage(OUT_OF_STEPS, tool_call_id=c["id"], name=c["name"]) for c in last.tool_calls],
                "stopped": True}

    def route(state: AskState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            if (state.get("steps") or 0) <= MAX_STEPS:
                return "tools"
            return END if state.get("stopped") else "out_of_steps"  # a model that ignores tool_choice gets one note
        if (not last.text.strip() or cut_off(last)) and not state.get("nudged"):
            return "nudge"  # an empty or cut-off answer gets one more try
        return END

    g = StateGraph(AskState, context_schema=AskContext)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("nudge", nudge)
    g.add_node("out_of_steps", out_of_steps)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["tools", "out_of_steps", "nudge", END])
    g.add_edge("tools", "agent")
    g.add_edge("out_of_steps", "agent")
    g.add_edge("nudge", "agent")
    return g.compile(checkpointer=checkpointer, name="Ask")


_graph: tuple[Any, Any] | None = None  # (checkpointer, compiled graph)


async def graph(specs: list[dict[str, Any]]):
    """The compiled graph, built once per checkpointer (scripts close and reopen theirs)."""
    global _graph
    saver = await checkpointer()
    if _graph is None or _graph[0] is not saver:
        _graph = (saver, build(specs, saver))
    return _graph[1]


_saver: AsyncSqliteSaver | None = None
_opening: asyncio.Lock | None = None


async def checkpointer() -> AsyncSqliteSaver:
    """One SQLite checkpointer for every conversation, opened on first use in the server's event loop.

    The lock stops two questions arriving together from each opening a connection. The one left over would never be
    closed, and its thread would keep a script from exiting.
    """
    global _saver, _opening
    if _saver is None:
        _opening = _opening or asyncio.Lock()
        async with _opening:
            if _saver is None:
                path = settings.conversations_dir / "checkpoints.sqlite"
                path.parent.mkdir(parents=True, exist_ok=True)
                conn = await aiosqlite.connect(str(path), timeout=30)
                # WAL lets the delete routes write while a turn is saving, instead of failing with "database is locked".
                await conn.execute("PRAGMA journal_mode=WAL")
                saver = AsyncSqliteSaver(conn)
                await saver.setup()
                _saver = saver
    return _saver


async def close() -> None:
    """Close the checkpointer's connection, for scripts that exit (the server keeps it open)."""
    global _saver, _opening
    if _saver is not None:
        await _saver.conn.close()
        _saver = None
    _opening = None  # a lock belongs to one event loop


def thread_id(user_folder: str, conversation_id: str) -> str:
    return f"{user_folder}/{conversation_id}"


def delete_threads(user_folder: str, conversation_id: str | None = None) -> None:
    """Delete one conversation's thread, or all of a user's. Synchronous, for the delete routes and account removal."""
    path = settings.conversations_dir / "checkpoints.sqlite"
    if not path.exists():
        return
    pattern = thread_id(user_folder, conversation_id) if conversation_id else thread_id(user_folder, "%")
    with sqlite3.connect(str(path), timeout=30) as conn:
        for table in ("checkpoints", "writes"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id LIKE ?", (pattern,))


def traced(username: str | None) -> bool:
    """Whether this user's runs go to LangSmith."""
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true" or not os.getenv("LANGSMITH_API_KEY") or not username:
        return False
    allowed = {u.strip().lower() for u in os.getenv("LANGSMITH_TRACE_USERS", "").split(",") if u.strip()}
    return username.lower() in allowed


def tool_errors(update: dict[str, Any]) -> list[ToolMessage]:
    return [m for m in update.get("messages", []) if isinstance(m, ToolMessage) and m.status == "error"]
