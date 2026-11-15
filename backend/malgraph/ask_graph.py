"""Ask the graph, as a LangGraph agent.

The graph has three nodes:

    START -> agent -> (tool calls?) -> tools -> agent -> ...
                   -> (empty reply, first time?) -> nudge -> agent
                   -> END

`agent` calls the model through OpenRouter with the tools bound. `tools` is LangGraph's prebuilt ToolNode, which runs
the tool calls of one reply in parallel. `nudge` handles a quirk of reasoning models: they sometimes spend their whole
token budget thinking and reply with nothing, so the graph asks once for the answer before giving up.

Conversations are LangGraph threads. Their messages live in a SQLite checkpointer next to the conversation files,
keyed by user and conversation, and the model only sees the last MAX_HISTORY messages of a thread.

The tools are the same ones the hand-written loop used: their JSON schemas from agent.TOOLS, run by agent.execute_tool.
Tools that change the UI (show_on_canvas, present_cards) add to the turn's ToolContext, which reaches them through a
context variable, since the ToolNode runs tools on worker threads that copy the caller's context.

With LANGSMITH_TRACING on and a LANGSMITH_API_KEY, runs of the users listed in LANGSMITH_TRACE_USERS are traced to
LangSmith. Nobody else's questions or lists leave the server that way.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from contextvars import ContextVar
from typing import Any

import aiosqlite
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from .config import settings

MAX_HISTORY = 60  # messages of a thread the model sees, starting at a question
MAX_RESULT = 60_000  # characters of a tool result passed back to the model
NUDGE = "Please write your answer now, from the results you already have. List the results themselves."

# The UI side effects of the current turn. A ContextVar reaches tools on the ToolNode's worker threads.
turn_context: ContextVar[Any] = ContextVar("ask_turn_context")


class AskState(MessagesState):
    nudged: bool  # asked once for an answer after an empty reply, reset every turn


def _run_tool(name: str, args: dict[str, Any]) -> str:
    from .agent import execute_tool  # agent imports this module

    result = execute_tool(name, args, turn_context.get())
    content = json.dumps(result, ensure_ascii=False, default=str)
    return content if len(content) <= MAX_RESULT else content[:MAX_RESULT] + '... (truncated)"}'


def make_tools(specs: list[dict[str, Any]]) -> list[StructuredTool]:
    """LangChain tools from OpenAI-style function specs, keeping the hand-written schemas and descriptions."""
    tools = []
    for spec in specs:
        f = spec["function"]

        def call(_name: str = f["name"], **kwargs: Any) -> str:
            return _run_tool(_name, kwargs)

        tools.append(StructuredTool.from_function(func=call, name=f["name"], description=f["description"], args_schema=f["parameters"]))
    return tools


def make_model(session_id: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base,
        max_tokens=4000,
        stream_usage=True,
        default_headers={"HTTP-Referer": "https://github.com/djhoomin/MAL-Graph", "X-Title": "MAL-Graph"},
        # OpenRouter sticky sessions: every request of a conversation goes to the same provider, so prompt caching hits.
        extra_body={"session_id": session_id, "cache_control": {"type": "ephemeral"}},
    )


def history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The last MAX_HISTORY messages, starting at a question so no tool result loses its call."""
    return trim_messages(messages, strategy="last", max_tokens=MAX_HISTORY, token_counter=len, start_on="human")


def build(model: ChatOpenAI, tools: list[StructuredTool], system: str, checkpointer: AsyncSqliteSaver | None):
    bound = model.bind_tools(tools, tool_choice="auto")

    async def agent(state: AskState, config: RunnableConfig) -> dict[str, Any]:
        reply = await bound.ainvoke([SystemMessage(system), *history(state["messages"])], config)
        return {"messages": [reply]}

    def nudge(state: AskState) -> dict[str, Any]:
        return {"messages": [HumanMessage(NUDGE)], "nudged": True}

    def route(state: AskState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        if not last.text.strip() and not state.get("nudged"):
            return "nudge"
        return END

    g = StateGraph(AskState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(tools, handle_tool_errors=lambda e: f"Error: {e}"))
    g.add_node("nudge", nudge)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["tools", "nudge", END])
    g.add_edge("tools", "agent")
    g.add_edge("nudge", "agent")
    return g.compile(checkpointer=checkpointer, name="Ask")


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
                saver = AsyncSqliteSaver(await aiosqlite.connect(str(path)))
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
    with sqlite3.connect(str(path)) as conn:
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
