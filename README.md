# MAL-Graph

MyAnimeList as an explorable graph: your watch list, its characters, voice actors, staff,
studios and related anime, stored in **Memgraph** and explored through a React + Cytoscape UI.

```
MAL API (your list)          ─┐
                              ├─►  malgraph CLI (Python)  ─►  Memgraph  ◄─  FastAPI  ◄─  Vite/React UI
Jikan v4, self-hosted (:8080) ┘                            :7687         :8000         :5173
```

## Setup

1. **Docker** (Memgraph + Memgraph Lab + a self-hosted Jikan with MongoDB):
   ```sh
   docker compose up -d          # Lab UI at http://localhost:3000, Jikan at http://localhost:8080/v4
   ```
   Jikan is self-hosted because the public `api.jikan.moe` has been intermittently returning
   504s since mid-2026 (MAL throttles it — jikan-rest issue #610). Your own instance scrapes MAL
   from your IP and caches into Mongo. Set `JIKAN_BASE=https://api.jikan.moe/v4` in `.env` to use
   the public one instead.
2. **Python backend** (needs Python ≥ 3.12; `.venv` is created with Homebrew's 3.13):
   ```sh
   python3.13 -m venv .venv && .venv/bin/pip install -e backend
   ```
3. **MAL credentials**: copy `.env.example` to `.env`, then register a free app at
   <https://myanimelist.net/apiconfig> (App Type: *other*, any name/redirect) and paste the
   **Client ID** plus your MAL username. Your anime list must be public.
4. **Web UI**:
   ```sh
   cd web && npm install
   ```

## Run

```sh
.venv/bin/malgraph sync-list              # your list -> User/Anime/LISTED
.venv/bin/malgraph expand-list            # characters/VAs/staff/relations for every listed anime (resumable)
.venv/bin/malgraph expand anime 5114      # one node's neighbourhood (anime | person | character)
.venv/bin/malgraph stats

.venv/bin/uvicorn malgraph.api.main:app --app-dir backend --reload   # API on :8000
cd web && npm run dev                                                # UI on :5173
```

The client stays under 3 req/s and 60 req/min (be polite to MAL); every response is cached under
`data/cache/`, so re-runs are free and `expand-list` can be interrupted and resumed. Transient
errors are retried with backoff; failed ids are listed at the end and retried on the next run.

## Deploying

See [deploy/README.md](deploy/README.md) — `docker-compose.prod.yml` adds Caddy (HTTPS + basic auth)
in front of the API and a static build of the UI; it runs on a small Scaleway Instance.

## Graph model

| Edge | Meaning |
|---|---|
| `(User)-[:LISTED {status, score}]->(Anime)` | your list; `Anime.watched` = status ≠ plan_to_watch |
| `(Anime)-[:HAS_CHARACTER {role}]->(Character)` | Main / Supporting |
| `(Person)-[:VOICES {language, anime_ids}]->(Character)` | one edge per VA/character; `anime_ids` = where |
| `(Person)-[:WORKED_ON {positions}]->(Anime)` | staff |
| `(Anime)-[:RELATED_TO {relation}]->(Anime)` | Sequel, Prequel, Side Story… (targets may be stubs) |
| `(Anime)-[:PRODUCED_BY]->(Studio)`, `(Anime)-[:HAS_GENRE]->(Genre {kind})` | |

Nodes without `fetched_at` are **stubs** (known only by id/title); the UI draws them dashed and
"Fetch from MAL" fills them in.

## UI

- **Search** adds a node and its DB neighbours. Click = select, double-click = expand
  neighbours, right-click = fetch from MAL / set path endpoints / remove.
- **Shortest path** uses Memgraph's native BFS (`[*BFS]`, or `[*ALLSHORTEST]` for all paths),
  optionally restricted to anime you've seen and excluding hub nodes (genres, your User node).
- **Voice roles** (Person) lists every character they voice, grouped by anime, filtered to your
  list by default.
- **Sync list** (status bar) re-fetches your MAL list and then fetches any newly added anime from
  MAL in the background, showing progress — the same as `malgraph sync-list && malgraph expand-list`.
- **VA roster** (`#/roster`, or the link in the header) is a URL-addressable card view: voice actors
  ranked by how many distinct characters they play in anime you've seen (`#/roster/<person id>`
  shows one VA's characters with role, anime and watch status, plus a random pick of three).

Handy Cypher for Memgraph Lab:

```cypher
// VAs who appear most across anime I've completed
MATCH (u:User)-[l:LISTED {status:'completed'}]->(a:Anime)-[:HAS_CHARACTER]->(c)<-[v:VOICES {language:'Japanese'}]-(p:Person)
RETURN p.name, count(DISTINCT a) AS anime, count(DISTINCT c) AS characters ORDER BY anime DESC LIMIT 20;
```
