"""Reading the anime list export that MyAnimeList lets every user download (Profile, Export lists).

The export is XML, usually gzipped, with one <anime> element per entry. It's turned into the same shape the
MyAnimeList API returns, so ingest.upsert_user_list reads it like a sync. This lets people bring a MyAnimeList list
without the MyAnimeList API, such as AniList users with a MyAnimeList list, or everyone if API access ends.

Only ids, statuses, scores and episode counts are read. Comments, tags, dates and the rest of the file are ignored.
The file is untrusted, so its size is capped before and after unzipping, and anything with a DOCTYPE is refused,
since real exports have none and DOCTYPEs are how XML entity attacks start.
"""
from __future__ import annotations

import zlib
from typing import Any
from xml.etree import ElementTree

MAX_UPLOAD = 5 * 1024 * 1024  # bytes as sent, gzipped or not
MAX_XML = 40 * 1024 * 1024  # bytes once unzipped, far above the largest real lists

STATUS = {
    "watching": "watching", "1": "watching",
    "completed": "completed", "2": "completed",
    "on-hold": "on_hold", "on hold": "on_hold", "3": "on_hold",
    "dropped": "dropped", "4": "dropped",
    "plan to watch": "plan_to_watch", "6": "plan_to_watch",
}
TYPES = {"TV": "tv", "Movie": "movie", "OVA": "ova", "ONA": "ona", "Special": "special", "Music": "music",
         "TV Special": "tv_special", "CM": "cm", "PV": "pv"}


class ExportError(ValueError):
    """The message is shown to the person who uploaded the file."""


def _unzip(data: bytes) -> bytes:
    if data[:2] != b"\x1f\x8b":
        return data
    inflate = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = inflate.decompress(data, MAX_XML + 1)
    except zlib.error as e:
        raise ExportError("That file looks gzipped but couldn't be unzipped. Download the export again.") from e
    if len(out) > MAX_XML or inflate.unconsumed_tail:
        raise ExportError("That file is too big to be a MyAnimeList anime list export.")
    return out


def _int(text: str | None) -> int:
    try:
        return int((text or "0").strip() or 0)
    except ValueError:
        return 0


def parse(data: bytes) -> tuple[str | None, list[dict[str, Any]]]:
    """The export's username and its entries in the MyAnimeList API's shape. Raises ExportError for anything that
    isn't an anime list export."""
    if len(data) > MAX_UPLOAD:
        raise ExportError("That file is too big to be a MyAnimeList anime list export.")
    xml = _unzip(data)
    if b"<!DOCTYPE" in xml[:4096].upper() or b"<!ENTITY" in xml.upper():
        raise ExportError("That file isn't a MyAnimeList list export.")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise ExportError("That file isn't a MyAnimeList list export. Upload the .xml.gz file from Export lists.") from e
    if root.tag != "myanimelist":
        raise ExportError("That file isn't a MyAnimeList list export. Upload the .xml.gz file from Export lists.")
    if root.find("manga") is not None and root.find("anime") is None:
        raise ExportError("That's a manga list export. Export your anime list instead.")
    info = root.find("myinfo")
    username = (info.findtext("user_name") or "").strip() or None if info is not None else None
    entries: dict[int, dict[str, Any]] = {}
    for a in root.iter("anime"):
        aid = _int(a.findtext("series_animedb_id"))
        status = STATUS.get((a.findtext("my_status") or "").strip().lower())
        if not aid or not status:
            continue
        kind = (a.findtext("series_type") or "").strip()
        entries[aid] = {
            "node": {
                "id": aid,
                "title": (a.findtext("series_title") or "").strip() or None,
                "media_type": TYPES.get(kind, kind.lower() or None),
                "num_episodes": _int(a.findtext("series_episodes")) or None,
            },
            "list_status": {
                "status": status,
                "score": min(10, max(0, _int(a.findtext("my_score")))),
                "num_episodes_watched": _int(a.findtext("my_watched_episodes")),
                "is_rewatching": (a.findtext("my_rewatching") or "0").strip() == "1",
                "updated_at": None,
            },
        }
    if not entries:
        raise ExportError("That export has no anime in it. Export your anime list, not your manga list.")
    return username, list(entries.values())
