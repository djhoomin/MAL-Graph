"""`malgraph` command line: sync your MAL list and expand the graph via Jikan."""
from __future__ import annotations

import typer
from rich import print as rprint
from rich.progress import Progress

from . import db, ingest, jikan
from .config import settings
from .jikan import JikanError
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
    j = jikan.shared()
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
    j = jikan.shared()
    failed: list[tuple[int, str]] = []
    with Progress() as progress:
        task = progress.add_task(f"expanding {len(ids)} anime", total=len(ids))
        for mal_id in ids:
            try:
                ingest.expand_anime(j, mal_id)
            except JikanError as e:
                failed.append((mal_id, str(e)))
            progress.advance(task)
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
    username: str = typer.Option(None, help="Whose favourite people to follow. Defaults to MAL_USERNAME"),
) -> None:
    """Grow the graph beyond your list: your people's full filmographies + metadata of the anime they share (for recommendations)."""
    db.ensure_schema()
    j = jikan.shared()
    kinds = ["va", "Director", "Music", "Character Design", "Original Creator", "Series Composition"]
    people: list[int] = []
    for kind in kinds:
        ids = ingest.top_people_ids(kind, top_va if kind == "va" else top_staff, lang, username or settings.mal_username)
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
    rprint(f"done. jikan requests={j.stats['requests']} cache hits={j.stats['hits']}")
    if failed:
        rprint(f"[yellow]{len(failed)} failed (re-run to retry):[/yellow] {failed[:10]}")


@app.command()
def migrate() -> None:
    """Remove per-user flags that older versions stored on shared Anime nodes (safe to re-run)."""
    rprint(f"[green]cleaned {ingest.drop_legacy_user_props()} anime nodes[/green]")


@app.command("fix-voices")
def fix_voices(
    min_favorites: int = typer.Option(500, help="Refetch voice actors for main characters with at least this many favourites"),
    refetch: bool = typer.Option(True, help="Also refetch from Jikan, not only fill languages from the graph"),
) -> None:
    """Fill missing voice languages, and refetch the voice actor order of popular characters (safe to re-run)."""
    rprint(f"[green]filled the language of {ingest.fill_voice_languages()} voice links[/green]")
    if not refetch:
        return
    ids = ingest.voices_to_refresh(min_favorites)
    rprint(f"refetching voice actors for {len(ids)} characters")
    j = jikan.shared()
    failed = []
    with Progress() as progress:
        task = progress.add_task("voices", total=len(ids))
        for cid in ids:
            try:
                ingest.refresh_voices(j, cid)
            except Exception as e:  # noqa: BLE001 - one character failing shouldn't stop the rest
                failed.append((cid, str(e)[:80]))
            progress.advance(task)
    rprint(f"[green]filled {ingest.fill_voice_languages()} more[/green]")
    if failed:
        rprint(f"[yellow]{len(failed)} failed (re-run to retry):[/yellow] {failed[:5]}")


@app.command()
def stats() -> None:
    """Node / edge counts."""
    for k, v in ingest.stats().items():
        rprint(f"{k:>18}: {v}")


@app.command()
def eval_ask(
    user: str = typer.Option(None, help="Whose list the questions are about. Defaults to MAL_USERNAME"),
    langsmith: bool = typer.Option(False, help="Record the run as a LangSmith experiment (needs LANGSMITH_API_KEY)"),
    prefix: str = typer.Option("ask", help="LangSmith experiment name prefix"),
    only: str = typer.Option("", help="Comma list of checks to run, locally only"),
) -> None:
    """Run the Ask agent on the eval questions and score the answers against the graph."""
    from . import ask_eval

    ask_eval.main(user or settings.mal_username, langsmith, prefix, [c for c in only.split(",") if c] or None)
if __name__ == "__main__":
    app()
