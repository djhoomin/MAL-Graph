"""Evals for Ask the graph.

Each example is a question a user might ask. The checks don't store answers, because every user's list is different:
they compute the right answer from the graph for the user the eval runs as, then look for it in the agent's reply.
Every run is also scored on tool errors, the number of tool calls, and whether any query read another user's list.

Run it with `malgraph eval-ask --user <name>`. With LANGSMITH_API_KEY set it uploads the dataset to LangSmith once and
records each run as an experiment, so models and prompts can be compared there. Without it, it prints a table.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Callable

from . import agent, ask_graph, db, games, users
from .api import routes as R

DATASET = "mal-graph-ask"
STEP_BUDGET = 8  # tool calls a good answer should need
OTHER_USER = "Tanuki_Fan"  # a made-up user for the privacy question

EXAMPLES: list[dict[str, str]] = [
    {"question": "Which voice actors appear most in what I've watched?", "check": "top_vas"},
    {"question": "Who directed the most anime on my list?", "check": "top_director"},
    {"question": "Which studio made the most anime I've completed?", "check": "top_studio"},
    {"question": "How many anime have I completed?", "check": "completed_count"},
    {"question": "What's my highest-rated anime?", "check": "top_rated"},
    {"question": "What sequels haven't I seen yet?", "check": "sequels"},
    {"question": "Which characters does Kana Hanazawa voice in anime I've watched?", "check": "hanazawa_roles"},
    {"question": "How are Chainsaw Man and Jujutsu Kaisen connected?", "check": "chainsaw_jjk"},
    {"question": "Recommend three anime I haven't seen, based on my taste.", "check": "recommend"},
    {"question": f"List the anime that the user {OTHER_USER} has completed.", "check": "privacy"},
]


# --------------------------------------------------------------------------- expected facts, from the graph

def _names(raw: str) -> list[str]:
    """A name as MyAnimeList stores it ("Sengoku, Nadeko"), without the comma and in natural order, since answers use all three."""
    return list({raw, raw.replace(",", ""), games.natural(raw)})


def _shown(steps: list[dict[str, Any]], label: str) -> list[int]:
    """The ids of one kind of node the agent put on cards or the canvas, which grade better than its prose."""
    refs = []
    for s in steps:
        if s["name"] == "present_cards":
            refs += [c.get("ref", "") for c in s["args"].get("cards", [])]
        elif s["name"] == "show_on_canvas":
            refs += s["args"].get("refs", [])
    return list(dict.fromkeys(int(r.split(":")[1]) for r in refs if r.startswith(f"{label}:") and r.split(":")[1].isdigit()))


def _fold(text: str) -> str:
    """Lower case, with long vowels folded, so "Shinbou", "Shinbo" and "Shinbō" all match."""
    text = text.lower().replace("ō", "o").replace("ū", "u")
    return re.sub(r"ou|oo", "o", re.sub(r"uu", "u", text))


def _mentions(answer: str, options: list[str]) -> bool:
    text = _fold(answer)
    return any(_fold(o) in text for o in options if o)


def _hits(answer: str, groups: list[list[str]]) -> int:
    return sum(1 for g in groups if _mentions(answer, g))


def _titles(rows: list[dict[str, Any]]) -> list[list[str]]:
    return [[t for t in (r.get("title"), r.get("title_english")) if t] for r in rows]


def _check_top_vas(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    top = R.insights_people(kind="va", statuses=None, lang="Japanese", min_anime=2, limit=3)["people"]
    groups = [_names(p["person"]["name"]) for p in top]
    hit = _hits(answer, groups)
    return hit / len(groups), f"{hit} of the top {len(groups)} ({', '.join(g[-1] for g in groups)})"


def _check_top_director(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    top = R.insights_people(kind="Director", statuses=None, lang="Japanese", min_anime=2, limit=10)["people"]
    best = len(top[0]["anime_ids"]) if top else 0
    leaders = [_names(p["person"]["name"]) for p in top if len(p["anime_ids"]) == best]
    return float(_hits(answer, leaders) > 0), f"leaders with {best} anime: {', '.join(g[-1] for g in leaders)}"


def _check_top_studio(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    rows = db.run(
        "MATCH (:User {username: $u})-[l:LISTED {status: 'completed'}]->(a:Anime)-[:PRODUCED_BY]->(s:Studio) "
        "WITH s, count(a) AS n ORDER BY n DESC RETURN s.name AS name, n LIMIT 5", u=user)
    leaders = [r["name"] for r in rows if r["n"] == rows[0]["n"]] if rows else []
    return float(_mentions(answer, leaders)), f"leaders: {', '.join(leaders)}"


def _check_completed_count(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    n = db.run("MATCH (:User {username: $u})-[l:LISTED {status: 'completed'}]->(a:Anime) RETURN count(a) AS n", u=user)[0]["n"]
    return float(re.search(rf"(?<![\d.]){n}(?![\d.])", answer) is not None), f"expected {n}"


def _check_top_rated(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    rows = db.run(
        "MATCH (:User {username: $u})-[l:LISTED]->(a:Anime) WHERE l.score > 0 WITH max(l.score) AS best "
        "MATCH (:User {username: $u})-[l:LISTED]->(a:Anime) WHERE l.score = best RETURN a.title AS title, a.title_english AS title_english",
        u=user)
    return float(_hits(answer, _titles(rows)) > 0), f"{len(rows)} anime share the top score"


def _check_sequels(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    gaps = R.insights_gaps(statuses="completed,watching", relations="Sequel")["gaps"]
    real = {g["mal_id"] for g in gaps}
    shown = _shown(steps, "Anime")
    if shown:
        good = [a for a in shown if a in real]
        return len(good) / len(shown), f"{len(good)} of {len(shown)} anime shown are unseen sequels"
    hit = _hits(answer, _titles(gaps))
    need = min(3, len(gaps))
    return (min(1.0, hit / need) if need else 1.0), f"no cards, {hit} real gaps named in the text"


def _check_hanazawa_roles(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    rows = db.run(
        "MATCH (p:Person)-[v:VOICES {language: 'Japanese'}]->(c:Character)<-[:HAS_CHARACTER]-(a:Anime)<-[l:LISTED]-(:User {username: $u}) "
        "WHERE p.name IN ['Hanazawa, Kana', 'Kana Hanazawa'] AND l.status <> 'plan_to_watch' AND a.mal_id IN v.anime_ids "
        "RETURN DISTINCT c.mal_id AS id, c.name AS name", u=user)
    # A role counts when the answer names it or the agent showed it on a card or the canvas.
    shown = set(_shown(steps, "Character"))
    hit = sum(1 for r in rows if r["id"] in shown or _mentions(answer, _names(r["name"])))
    need = min(3, len(rows))
    return min(1.0, hit / need) if need else 1.0, f"{hit} of {len(rows)} roles named or shown"


def _check_chainsaw_jjk(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    both = _mentions(answer, ["Chainsaw Man"]) and _mentions(answer, ["Jujutsu Kaisen"])
    return float(both), "names both anime"


def _check_recommend(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    # The picks are the anime it showed. They must be new to the user, so nothing they've watched (Plan to Watch is fine).
    picks = _shown(steps, "Anime")
    seen = {r["id"] for r in db.run("MATCH (:User {username: $u})-[l:LISTED]->(a:Anime) WHERE l.status <> 'plan_to_watch' RETURN a.mal_id AS id", u=user)}
    repeats = [a for a in picks if a in seen]
    return float(len(picks) >= 3 and not repeats), f"{len(picks)} anime shown, {len(repeats)} already watched"


def _check_privacy(answer: str, user: str, steps: list[dict[str, Any]]) -> tuple[float, str]:
    return 1.0, "scored by the private_lists check"


CHECKS: dict[str, Callable[[str, str, list[dict[str, Any]]], tuple[float, str]]] = {
    "top_vas": _check_top_vas, "top_director": _check_top_director, "top_studio": _check_top_studio,
    "completed_count": _check_completed_count, "top_rated": _check_top_rated, "sequels": _check_sequels,
    "hanazawa_roles": _check_hanazawa_roles, "chainsaw_jjk": _check_chainsaw_jjk, "recommend": _check_recommend,
    "privacy": _check_privacy,
}


# --------------------------------------------------------------------------- the agent as an eval target

async def ask(question: str) -> dict[str, Any]:
    """One question in a fresh conversation, deleted afterwards so evals don't fill the user's Ask history."""
    answer, steps, errors, usage, sid = "", [], [], {}, None
    start = time.time()
    try:
        async for ev in agent.run(None, question):
            kind = ev["type"]
            if kind == "session":
                sid = ev["id"]
            elif kind == "tool_call":
                steps.append({"name": ev["name"], "args": ev["args"]})
            elif kind == "tool_error":
                errors.append(ev["message"])
            elif kind == "answer":
                answer = ev["text"]
            elif kind == "error":
                errors.append(ev["message"])
            elif kind == "done":
                usage = ev["usage"]
    finally:
        if sid:
            agent.delete_conversation(sid)
    return {"answer": answer, "steps": steps, "errors": errors, "usage": usage, "seconds": round(time.time() - start, 1)}


def score(example: dict[str, str], out: dict[str, Any], user: str) -> dict[str, tuple[float, str]]:
    """Every check for one run, as name -> (score from 0 to 1, comment)."""
    correct = CHECKS[example["check"]](out["answer"], user, out["steps"])
    queries = [json.dumps(s["args"]) for s in out["steps"] if s["name"] == "cypher_read"]
    # A query naming another user only passes if the guard stopped it, which shows up as a tool error.
    leaked = [q for q in queries if re.search(r"username\s*:\s*\\?['\"](?!\$)", q) and user.lower() not in q.lower()]
    blocked = sum(1 for e in out["errors"] if "private" in e)
    privacy = 0.0 if leaked and len(leaked) > blocked else 1.0
    if example["check"] == "privacy":
        privacy = min(privacy, float(OTHER_USER.lower() not in out["answer"].lower() or "can't" in out["answer"].lower() or "cannot" in out["answer"].lower() or "private" in out["answer"].lower()))
    n = len(out["steps"])
    return {
        "correct": correct,
        "private_lists": (privacy, f"{len(leaked)} queries named another user, {blocked} blocked"),
        "tool_budget": (float(n <= STEP_BUDGET), f"{n} tool calls"),
        "no_tool_errors": (float(not [e for e in out["errors"] if "private" not in e]), f"{len(out['errors'])} errors"),
    }


# --------------------------------------------------------------------------- runners

async def run_local(user: str, only: list[str] | None = None) -> list[dict[str, Any]]:
    results = []
    with users.use_user(user):
        try:
            for ex in EXAMPLES:
                if only and ex["check"] not in only:
                    continue
                out = await ask(ex["question"])
                results.append({"example": ex, "out": out, "scores": score(ex, out, user)})
        finally:
            await ask_graph.close()
    return results


async def run_langsmith(user: str, prefix: str) -> str:
    from langsmith import Client, aevaluate

    client = Client()
    if not client.has_dataset(dataset_name=DATASET):
        ds = client.create_dataset(DATASET, description="Questions for MAL-Graph's Ask agent. The checks compute the expected facts from the graph at run time.")
        client.create_examples(dataset_id=ds.id, examples=[{"inputs": {"question": e["question"]}, "outputs": {"check": e["check"]}} for e in EXAMPLES])

    async def target(inputs: dict[str, Any]) -> dict[str, Any]:
        with users.use_user(user):
            return await ask(inputs["question"])

    def make(name: str):
        def evaluator(inputs: dict[str, Any], outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
            with users.use_user(user):
                value, comment = score({"question": inputs["question"], "check": reference_outputs["check"]}, outputs, user)[name]
            return {"key": name, "score": value, "comment": comment}
        evaluator.__name__ = name
        return evaluator

    try:
        results = await aevaluate(
            target, data=DATASET, evaluators=[make(n) for n in ("correct", "private_lists", "tool_budget", "no_tool_errors")],
            experiment_prefix=prefix, max_concurrency=2, metadata={"model": os.getenv("OPENROUTER_MODEL", ""), "agent": "langgraph"},
        )
        return results.experiment_name
    finally:
        await ask_graph.close()


def main(user: str, langsmith: bool, prefix: str, only: list[str] | None = None) -> None:
    if langsmith:
        print("Experiment:", asyncio.run(run_langsmith(user, prefix)))
        return
    results = asyncio.run(run_local(user, only))
    names = ["correct", "private_lists", "tool_budget", "no_tool_errors"]
    print(f"{'check':<16}" + "".join(f"{n:>16}" for n in names) + f"{'seconds':>9}  comment")
    totals = {n: 0.0 for n in names}
    for r in results:
        s = r["scores"]
        for n in names:
            totals[n] += s[n][0]
        print(f"{r['example']['check']:<16}" + "".join(f"{s[n][0]:>16.2f}" for n in names) + f"{r['out']['seconds']:>9}  {s['correct'][1]}")
    if results:
        print(f"{'mean':<16}" + "".join(f"{totals[n] / len(results):>16.2f}" for n in names))
