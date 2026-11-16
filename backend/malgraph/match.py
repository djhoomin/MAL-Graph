"""Taste match: compare two people's lists, once both have agreed to it.

Lists are private, so nothing is compared until one person makes an invite link and the other accepts it. An invite
works once and expires after INVITE_DAYS. Either person can unlink at any time, and deleting an account removes its
links and invites. Links live in a file next to the daily games' (GOLF_DIR/match), outside the graph, so the Ask
agent's privacy guard can keep assuming user nodes connect only through LISTED.

The comparison works on series, joining sequels and seasons into one franchise, so four seasons of a show count once.
A person's score for a series is the average of their scores for its seasons.

Score agreement is the cosine similarity of the two people's scores on the series both have scored, each measured
from that person's own average, so someone who scores everything 6 to 8 and someone who uses the whole scale can still
agree. It is scaled by n / (n + SHRINK), so a handful of shared series can't produce a confident number.

Watched overlap is a weighted Jaccard similarity of the series each has watched, weighting every series by
1 / log(members), so a shared obscure show counts for more than one everyone has seen.

Shared makers compare taste even between lists that barely overlap. Each person gets a profile of the studios,
directors, series composers, Japanese voices of main characters and genres behind the series they scored, each with
how far above or below their own average they score that maker's series. The two profiles are compared by cosine
similarity. Agreement takes up to AGREEMENT_WEIGHT of the match, less when few series are scored by both, and shared
makers take the rest after OVERLAP_WEIGHT.

Picks use the same profiles. From what one person scored at least one standard deviation above their own average and
the other hasn't watched, they rank what the other is likely to score highest, and name the maker that counts most for
it. Anime both plan to watch are ranked by both profiles together.

The result is plain data (numbers, series and scores), and the app words it. An LLM can later write a summary from
the same data without changing how the match is computed.
"""
from __future__ import annotations

import json
import math
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from . import db, games, users
from .config import settings

INVITE_DAYS = 7
MAX_LINKS = 20
SHRINK = 10  # shared scored series at which agreement has half its full weight
MIN_SCORED = 3  # shared scored series needed before agreement is computed
LISTED = 5  # series shown in each list of reasons
RARE_MEMBERS = 100_000  # a shared series with fewer members than this counts as rare
AGREEMENT_WEIGHT = 0.5  # of the overall match at most, with shared makers taking what agreement doesn't use
OVERLAP_WEIGHT = 0.2
MAKER_SHRINK = 2  # series behind a maker at which their lean counts for two thirds
MIN_MAKER_SERIES = 2  # series a maker needs in someone's list to count as a reason or a prediction
MAKER_LEAN = 0.5  # points above average both need on a maker for it to be named
MAKERS_LISTED = 6
CACHE_SECONDS = 120
JOBS = {"Director": "director", "Series Composition": "writer"}
HIDDEN_FROM_TASTE = ["Hentai", "Erotica", "Ecchi"]  # genres left out of the makers profile
HIDDEN_GENRES = ["Hentai", "Erotica"]  # anime with these count in the numbers but aren't named as reasons

_lock = threading.Lock()


# --------------------------------------------------------------------------- links and invites


def _path() -> Path:
    path = settings.golf_dir / "match"
    path.mkdir(parents=True, exist_ok=True)
    return path / "links.json"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("links", [])
    data.setdefault("invites", {})
    now = time.time()
    data["invites"] = {t: i for t, i in data["invites"].items() if i["expires"] > now}
    return data


def _save(data: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def _same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def links(username: str) -> list[dict[str, Any]]:
    """The people this user is linked with: [{username, since}], newest first."""
    with _lock:
        data = _load()
    out = []
    for link in data["links"]:
        if _same(link["a"], username):
            out.append({"username": link["b"], "since": link["since"]})
        elif _same(link["b"], username):
            out.append({"username": link["a"], "since": link["since"]})
    return sorted(out, key=lambda x: -x["since"])


def linked(username: str, other: str) -> str | None:
    """The other person's stored username if the two are linked, else None."""
    return next((l["username"] for l in links(username) if _same(l["username"], other)), None)


def my_invite(username: str) -> dict[str, Any] | None:
    with _lock:
        data = _load()
    return next(({"token": t, "expires": i["expires"]} for t, i in data["invites"].items() if _same(i["from"], username)), None)


def invite(username: str) -> dict[str, Any]:
    """A new invite link token, replacing any the user had."""
    with _lock:
        data = _load()
        if sum(1 for l in data["links"] if _same(l["a"], username) or _same(l["b"], username)) >= MAX_LINKS:
            raise ValueError(f"You can link with up to {MAX_LINKS} people. Unlink someone first.")
        data["invites"] = {t: i for t, i in data["invites"].items() if not _same(i["from"], username)}
        token = secrets.token_urlsafe(18)
        expires = int(time.time()) + INVITE_DAYS * 86400
        data["invites"][token] = {"from": username, "expires": expires}
        _save(data)
    return {"token": token, "expires": expires}


def cancel_invite(username: str) -> None:
    with _lock:
        data = _load()
        data["invites"] = {t: i for t, i in data["invites"].items() if not _same(i["from"], username)}
        _save(data)


def invite_from(token: str) -> str | None:
    """Who made this invite, if it is still open."""
    with _lock:
        found = _load()["invites"].get(token)
    return found["from"] if found else None


def accept(token: str, username: str) -> str:
    """Link the invite's maker with this user and use the invite up. Returns the maker's username."""
    with _lock:
        data = _load()
        found = data["invites"].get(token)
        if not found:
            raise LookupError("This invite has expired or has already been used. Ask for a new link.")
        maker = found["from"]
        if _same(maker, username):
            raise ValueError("This is your own invite link. Send it to the person you want to compare with.")
        mine = sum(1 for l in data["links"] if _same(l["a"], username) or _same(l["b"], username))
        already = any({l["a"].lower(), l["b"].lower()} == {maker.lower(), username.lower()} for l in data["links"])
        if not already:
            if mine >= MAX_LINKS:
                raise ValueError(f"You can link with up to {MAX_LINKS} people. Unlink someone first.")
            data["links"].append({"a": maker, "b": username, "since": int(time.time())})
        del data["invites"][token]
        _save(data)
    return maker


def unlink(username: str, other: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["links"])
        data["links"] = [l for l in data["links"] if {l["a"].lower(), l["b"].lower()} != {username.lower(), other.lower()}]
        _save(data)
    return len(data["links"]) < before


def forget(username: str) -> int:
    """Remove every link and invite of a user. Returns how many links were removed."""
    with _lock:
        data = _load()
        before = len(data["links"])
        data["links"] = [l for l in data["links"] if not (_same(l["a"], username) or _same(l["b"], username))]
        data["invites"] = {t: i for t, i in data["invites"].items() if not _same(i["from"], username)}
        _save(data)
    for key in [k for k in _cache if username.lower() in k]:
        _cache.pop(key, None)
    return before - len(data["links"])


# --------------------------------------------------------------------------- the comparison


def _series(username: str, franchise: dict[int, int]) -> tuple[dict[int, dict[str, Any]], set[int]]:
    """Series the user has watched, franchise id -> {score (average of scored seasons, or None), anime ids}, and the
    anime on their plan to watch."""
    out: dict[int, dict[str, Any]] = {}
    planned: set[int] = set()
    for aid, (status, score) in users.user_list(username).entries.items():
        if status == "plan_to_watch":
            planned.add(aid)
            continue
        if not status:
            continue
        s = out.setdefault(franchise.get(aid, aid), {"scores": [], "ids": []})
        s["ids"].append(aid)
        if score:
            s["scores"].append(score)
    for s in out.values():
        s["score"] = sum(s["scores"]) / len(s["scores"]) if s["scores"] else None
    return out, planned


def _mean_sd(series: dict[int, dict[str, Any]]) -> tuple[float, float]:
    scores = [s["score"] for s in series.values() if s["score"] is not None]
    if not scores:
        return 0.0, 1.0
    mean = sum(scores) / len(scores)
    return mean, max(0.5, math.sqrt(sum((x - mean) ** 2 for x in scores) / len(scores)))


def _anime(ids: set[int]) -> dict[int, dict[str, Any]]:
    rows = db.run(
        "MATCH (a:Anime) WHERE a.id IN $ids "
        "OPTIONAL MATCH (a)-[:HAS_GENRE]->(g:Genre) WHERE g.name IN $hidden "
        "RETURN a.id AS id, a.title AS title, a.url AS url, a.image_url AS image, a.members AS members, count(g) > 0 AS hidden",
        ids=list(ids), hidden=HIDDEN_GENRES,
    )
    return {r["id"]: r for r in rows}


Maker = tuple[str, str, str]  # kind, key, name


def _makers(ids: set[int]) -> dict[int, set[Maker]]:
    """For each anime, who and what made it: studios, directors, series composers, the Japanese voices of its main
    characters, and its genres and themes."""
    out: dict[int, set[Maker]] = {i: set() for i in ids}
    ids_ = list(ids)
    for r in db.run("MATCH (a:Anime)-[:PRODUCED_BY]->(s:Studio) WHERE a.id IN $ids RETURN a.id AS a, s.id AS k, s.name AS n", ids=ids_):
        out[r["a"]].add(("studio", str(r["k"]), r["n"]))
    for r in db.run(
        "MATCH (p:Person)-[w:WORKED_ON]->(a:Anime) WHERE a.id IN $ids AND coalesce(p.birthday, '9999') >= '1900' "
        "AND any(j IN w.positions WHERE j IN $jobs) RETURN a.id AS a, p.id AS k, p.name AS n, w.positions AS jobs",
        ids=ids_, jobs=list(JOBS),
    ):
        for job in set(r["jobs"]) & set(JOBS):
            out[r["a"]].add((JOBS[job], str(r["k"]), games.natural(r["n"])))
    for r in db.run(
        "MATCH (a:Anime)-[:HAS_CHARACTER {role: 'Main'}]->(:Character)<-[v:VOICES]-(p:Person) "
        "WHERE a.id IN $ids AND v.language = 'Japanese' AND a.id IN v.anime_ids "
        "RETURN DISTINCT a.id AS a, p.id AS k, p.name AS n",
        ids=ids_,
    ):
        out[r["a"]].add(("voice", str(r["k"]), games.natural(r["n"])))
    for r in db.run(
        "MATCH (a:Anime)-[:HAS_GENRE]->(g:Genre) WHERE a.id IN $ids AND g.kind IN ['genre', 'theme'] AND NOT g.name IN $hidden "
        "RETURN a.id AS a, g.name AS n",
        ids=ids_, hidden=HIDDEN_FROM_TASTE,
    ):
        out[r["a"]].add(("genre", r["n"], r["n"]))
    return out


def _profile(series: dict[int, dict[str, Any]], mean: float, makers: dict[int, set[Maker]]) -> dict[Maker, tuple[float, int]]:
    """Maker -> (how far above or below their own average the person scores its series, how many series). Each
    series counts once per maker, and the lean is pulled towards 0 for makers behind only a few series."""
    sums: dict[Maker, list[float]] = {}
    for s in series.values():
        if s["score"] is None:
            continue
        for m in set().union(*(makers.get(i, set()) for i in s["ids"])):
            sums.setdefault(m, []).append(s["score"] - mean)
    return {m: (sum(v) / len(v) * len(v) / (len(v) + MAKER_SHRINK), len(v)) for m, v in sums.items()}


def _cosine(a: dict[Maker, tuple[float, int]], b: dict[Maker, tuple[float, int]]) -> float | None:
    dot = sum(v * b[m][0] for m, (v, _) in a.items() if m in b)
    norm = math.sqrt(sum(v * v for v, _ in a.values()) * sum(v * v for v, _ in b.values()))
    return dot / norm if norm else None


def _predict(profile: dict[Maker, tuple[float, int]], makers: set[Maker]) -> tuple[float, Maker | None]:
    """How a person would likely score an anime against their average, from the makers they know, and the maker
    that counts most in its favour."""
    known = [(profile[m][0], m) for m in makers if m in profile and profile[m][1] >= MIN_MAKER_SERIES]
    if not known:
        return 0.0, None
    # A studio or a person says more than a genre, so one of those is the reason when any leans the right way.
    top = max(known, key=lambda t: (t[0] > 0 and t[1][0] != "genre", t[0], t[1]))
    return sum(v for v, _ in known) / len(known), top[1] if top[0] > 0 else None


def _maker(m: Maker | None) -> dict[str, str] | None:
    return None if m is None else {"kind": m[0], "name": m[2]}


_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def compare(me: str, them: str) -> dict[str, Any]:
    """The match between two linked people, from the first one's side. Cached for CACHE_SECONDS."""
    key = (me.lower(), them.lower())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    result = _compare(me, them)
    _cache[key] = (time.time(), result)
    return result


def _compare(me: str, them: str) -> dict[str, Any]:
    franchise = games.recent_franchises()
    (mine, my_plan), (theirs, their_plan) = _series(me, franchise), _series(them, franchise)
    shared = set(mine) & set(theirs)

    def ids(f: int, side: dict[int, dict[str, Any]] | None = None) -> set[int]:
        if side is not None:
            return set(side.get(f, {}).get("ids", []))
        return ids(f, mine) | ids(f, theirs)

    watched_ids = {i for f in set(mine) | set(theirs) for i in ids(f)}
    anime = _anime(watched_ids | my_plan | their_plan)
    makers = _makers(watched_ids | my_plan | their_plan)

    def card(pick: int) -> dict[str, Any]:
        a = anime.get(pick, {})
        return {"id": pick, "title": a.get("title") or f"Anime {pick}", "url": a.get("url"), "image": a.get("image"), "members": a.get("members")}

    def best(f: int) -> dict[str, Any]:
        """The series' best-known anime, preferring one both have watched."""
        both = ids(f, mine) & ids(f, theirs)
        return card(max(both or ids(f), key=lambda i: (anime.get(i, {}).get("members") or 0, -i)))

    def members(f: int) -> int:
        return max((anime.get(i, {}).get("members") or 0) for i in ids(f))

    def shown(anime_ids: set[int]) -> bool:
        return not any(anime.get(i, {}).get("hidden") for i in anime_ids)

    # Score agreement.
    (my_mean, my_sd), (their_mean, their_sd) = _mean_sd(mine), _mean_sd(theirs)
    pairs = [(f, mine[f]["score"] - my_mean, theirs[f]["score"] - their_mean) for f in shared
             if mine[f]["score"] is not None and theirs[f]["score"] is not None]
    agreement = None
    if len(pairs) >= MIN_SCORED:
        dot = sum(x * y for _, x, y in pairs)
        norm = math.sqrt(sum(x * x for _, x, _ in pairs) * sum(y * y for _, _, y in pairs))
        agreement = dot / norm if norm else 0.0

    def row(f: int) -> dict[str, Any]:
        return {**best(f), "you": round(mine[f]["score"], 1), "them": round(theirs[f]["score"], 1)}

    named = [p for p in pairs if shown(ids(p[0]))]
    loved = sorted((p for p in named if p[1] > 0 and p[2] > 0), key=lambda p: (-min(p[1], p[2]), -max(p[1], p[2]), p[0]))
    # A split is one of you above your own average and the other below theirs, by 2 points or more between you.
    split = sorted((p for p in named if p[1] * p[2] < 0 and abs(p[1] - p[2]) >= 2), key=lambda p: (-abs(p[1] - p[2]), p[0]))

    # Watched overlap.
    def weight(f: int) -> float:
        return 1 / math.log(max(members(f), 1000))

    union = set(mine) | set(theirs)
    overlap = sum(weight(f) for f in shared) / sum(weight(f) for f in union) if union else 0.0
    rare = sorted((f for f in shared if members(f) < RARE_MEMBERS), key=lambda f: (members(f), f))
    rare_named = [f for f in rare if shown(ids(f))]

    # Shared makers.
    my_profile, their_profile = _profile(mine, my_mean, makers), _profile(theirs, their_mean, makers)
    maker_sim = _cosine(my_profile, their_profile)
    both_like = sorted(
        (m for m in my_profile if m in their_profile
         and min(my_profile[m][1], their_profile[m][1]) >= MIN_MAKER_SERIES
         and min(my_profile[m][0], their_profile[m][0]) >= MAKER_LEAN),
        key=lambda m: (-min(my_profile[m][0], their_profile[m][0]), m),
    )

    # Picks: what one loved that the other hasn't watched, ranked by how the other is likely to score it. A pick shows
    # its series' best-known anime, so the one to start with, and not the third season someone happened to watch.
    seasons: dict[int, list[int]] = {}
    for aid, f in franchise.items():
        seasons.setdefault(f, []).append(aid)
    extra = {i for f in set(theirs) ^ set(mine) for i in seasons.get(f, [])} - set(anime)
    anime.update(_anime(extra))

    def picks(lover: dict[int, dict[str, Any]], mean: float, sd: float, other: dict[int, dict[str, Any]],
              other_profile: dict[Maker, tuple[float, int]], other_plan: set[int]) -> list[dict[str, Any]]:
        found = []
        for f, s in lover.items():
            if f in other or s["score"] is None or s["score"] - mean < sd or not shown(set(s["ids"])):
                continue
            pick = max(set(s["ids"]) | set(seasons.get(f, [])), key=lambda i: (anime.get(i, {}).get("members") or 0, -i))
            predicted, because = _predict(other_profile, set().union(*(makers.get(i, set()) for i in s["ids"])))
            found.append((s["score"] - mean + predicted, f, {
                **card(pick), "score": round(s["score"], 1), "because": _maker(because),
                "planned": any(franchise.get(i, i) == f for i in other_plan),
            }))
        return [p for _, _, p in sorted(found, key=lambda t: (-t[0], t[1]))[:LISTED]]

    # Anime you both plan to watch, one per series, ranked by how both of you are likely to score it.
    together = {}
    for aid in my_plan & their_plan:
        if not shown({aid}):
            continue
        f = franchise.get(aid, aid)
        mine_p, my_because = _predict(my_profile, makers.get(aid, set()))
        theirs_p, their_because = _predict(their_profile, makers.get(aid, set()))
        rank = (mine_p + theirs_p, anime.get(aid, {}).get("members") or 0)
        if f not in together or rank > together[f][0]:
            together[f] = (rank, {**card(aid), "because": _maker(my_because or their_because)})
    planned = [p for _, p in sorted(together.values(), key=lambda t: (-t[0][0], -t[0][1], t[1]["id"]))[:LISTED]]

    # The overall match. Agreement counts for less when few series are scored by both, and shared makers take up
    # the rest, since they compare taste even between lists that barely overlap.
    parts = {
        "agreement": None if agreement is None else round(50 + 50 * agreement),
        "makers": None if maker_sim is None else round(50 + 50 * maker_sim),
        "overlap": round(100 * math.sqrt(overlap)),
    }
    weights = {"agreement": 0.0, "makers": 0.0, "overlap": OVERLAP_WEIGHT}
    if parts["agreement"] is not None:
        weights["agreement"] = AGREEMENT_WEIGHT * len(pairs) / (len(pairs) + SHRINK)
    if parts["makers"] is not None:
        weights["makers"] = 1 - OVERLAP_WEIGHT - weights["agreement"]
    total = sum(weights.values())
    overall = round(sum(weights[k] * (parts[k] or 0) for k in weights) / total)
    return {
        "them": them,
        "match": overall,
        "parts": parts,
        "weights": {k: round(100 * v / total) for k, v in weights.items()},
        "counts": {
            "shared": len(shared),
            "scored": len(pairs),
            "only_you": len(set(mine) - shared),
            "only_them": len(set(theirs) - shared),
            "rare": len(rare),
            "planned": len(together),
        },
        "means": {"you": round(my_mean, 1), "them": round(their_mean, 1)},
        "loved": [row(f) for f, _, _ in loved[:LISTED]],
        "split": [row(f) for f, _, _ in split[:LISTED]],
        "rare": [{**best(f), "you": _score(mine[f]), "them": _score(theirs[f])} for f in rare_named[:LISTED]],
        "makers": [{"kind": m[0], "name": m[2], "you": round(my_profile[m][0], 1), "them": round(their_profile[m][0], 1)}
                   for m in both_like[:MAKERS_LISTED]],
        "for_you": picks(theirs, their_mean, their_sd, mine, my_profile, my_plan),
        "for_them": picks(mine, my_mean, my_sd, theirs, their_profile, their_plan),
        "together": planned,
    }


def _score(s: dict[str, Any]) -> float | None:
    return None if s["score"] is None else round(s["score"], 1)
