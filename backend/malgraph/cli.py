"""`malgraph` command line: sync your MAL list and expand the graph via Jikan."""
from __future__ import annotations

import typer
from rich import print as rprint
from rich.progress import Progress

from . import db, ingest
from .config import settings
from .jikan import JikanClient, JikanError
from .mal import iter_user_animelist

app = typer.Typer(help="MyAnimeList → Memgraph graph builder", no_args_is_help=True)


@app.command()
def init_schema() -> None:
    """Create constraints and indexes in Memgraph."""
    db.ensure_schema()
    rprint("[green]schema ok[/green]")


@app.command()
def sync_list(username: str = typer.Option(None, help="Defaults to MAL_USERNAME")) -> None:
    """Fetch your MAL anime list (official API) and upsert User/Anime/LISTED."""
    db.ensure_schema()
    username = username or settings.mal_username
    n = ingest.upsert_user_list(username, iter_user_animelist(username))
    rprint(f"[green]synced {n} list entries for {username}[/green]")


@app.command()
def expand(kind: str = typer.Argument(..., help="anime | person | character"), mal_id: int = typer.Argument(...)) -> None:
    """Fetch one node's full neighbourhood from Jikan."""
    db.ensure_schema()
    j = JikanClient()
    fn = {"anime": ingest.expand_anime, "person": ingest.expand_person, "character": ingest.expand_character}.get(kind)
    if fn is None:
        raise typer.BadParameter("kind must be anime, person or character")
    rprint(fn(j, mal_id), j.stats)


@app.command()
def expand_list(
    limit: int = typer.Option(0, help="Only expand the first N unfetched anime (0 = all)"),
    username: str = typer.Option(None),
) -> None:
    """Expand every anime on your list that hasn't been fetched from Jikan yet (resumable)."""
    db.ensure_schema()
    ids = ingest.listed_stub_ids(username or settings.mal_username or None, limit or None)
    if not ids:
        rprint("[green]nothing to expand[/green]")
        return
    j = JikanClient()
    failed: list[tuple[int, str]] = []
    with Progress() as progress:
        task = progress.add_task(f"expanding {len(ids)} anime", total=len(ids))
        for mal_id in ids:
            try:
                ingest.expand_anime(j, mal_id)
            except JikanError as e:
                failed.append((mal_id, str(e)))
            progress.advance(task)
    ingest.mark_seen_franchise()
    rprint(f"done. jikan requests={j.stats['requests']} cache hits={j.stats['hits']}")
    if failed:
        rprint(f"[yellow]{len(failed)} failed (re-run to retry):[/yellow]")
        for mal_id, err in failed[:20]:
            rprint(f"  {mal_id}: {err}")


@app.command()
def enrich(
    top_va: int = typer.Option(100, help="Expand filmographies of the top N voice actors (by presence in watched anime)"),
    top_staff: int = typer.Option(40, help="Top N per staff position (Director, Music, Character Design, Original Creator, Series Composition)"),
    min_links: int = typer.Option(2, help="Then fetch metadata for unseen anime connected to at least this many of those people"),
    max_anime: int = typer.Option(1500, help="Cap on anime to fetch"),
    lang: str = typer.Option("Japanese"),
) -> None:
    """Grow the graph beyond your list: your people's full filmographies + metadata of the anime they share (for recommendations)."""
    db.ensure_schema()
    j = JikanClient()
    kinds = ["va", "Director", "Music", "Character Design", "Original Creator", "Series Composition"]
    people: list[int] = []
    for kind in kinds:
        ids = ingest.top_people_ids(kind, top_va if kind == "va" else top_staff, lang)
        people += [i for i in ids if i not in people]
    failed: list[tuple[int, str]] = []
    with Progress() as progress:
        task = progress.add_task(f"expanding {len(people)} people", total=len(people))
        for mal_id in people:
            try:
                ingest.expand_person(j, mal_id)
            except JikanError as e:
                failed.append((mal_id, str(e)))
            progress.advance(task)
    stubs = ingest.linked_stub_ids(min_links, max_anime)
    with Progress() as progress:
        task = progress.add_task(f"fetching metadata for {len(stubs)} anime", total=len(stubs))
        for mal_id in stubs:
            try:
                ingest.expand_anime_light(j, mal_id)
            except JikanError as e:
                failed.append((mal_id, str(e)))
            progress.advance(task)
    n = ingest.mark_seen_franchise()
    rprint(f"done. jikan requests={j.stats['requests']} cache hits={j.stats['hits']}; {n} anime flagged as seen franchises")
    if failed:
        rprint(f"[yellow]{len(failed)} failed (re-run to retry):[/yellow] {failed[:10]}")


@app.command()
def stats() -> None:
    """Node / edge counts."""
    for k, v in ingest.stats().items():
        rprint(f"{k:>18}: {v}")


if __name__ == "__main__":
    app()
