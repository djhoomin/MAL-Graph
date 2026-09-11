"""Convert neo4j-driver graph objects into the shared GraphPayload shape used by the UI."""
from __future__ import annotations

from typing import Any, Iterable

from neo4j.graph import Node, Path, Relationship

LABEL_ORDER = ["Anime", "Character", "Person", "Studio", "Genre", "User"]
HEAVY_PROPS = {"synopsis", "about"}  # only sent on /node detail


def node_id(n: Node) -> str:
    labels = [l for l in LABEL_ORDER if l in n.labels] or list(n.labels)
    label = labels[0]
    key = n.get("username") if label == "User" else n.get("mal_id")
    return f"{label}:{key}"


def node_payload(n: Node, *, full: bool = False) -> dict[str, Any]:
    label = node_id(n).split(":", 1)[0]
    props = {k: v for k, v in n.items() if full or k not in HEAVY_PROPS}
    return {
        "id": node_id(n),
        "label": label,
        "mal_id": n.get("mal_id"),
        "name": n.get("title") or n.get("name") or n.get("username"),
        "image_url": n.get("image_url"),
        "watched": bool(n.get("watched")) if label == "Anime" else None,
        "list_status": n.get("list_status") if label == "Anime" else None,
        "fetched": n.get("fetched_at") is not None if label in ("Anime", "Person", "Character") else True,
        "props": props,
    }


def edge_payload(r: Relationship) -> dict[str, Any]:
    src, dst = node_id(r.start_node), node_id(r.end_node)
    return {
        "id": f"{r.type}:{src}>{dst}",
        "source": src,
        "target": dst,
        "type": r.type,
        "props": dict(r.items()),
    }


class PayloadBuilder:
    """Accumulates nodes/edges from arbitrary query results, deduplicated by id."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def add(self, value: Any) -> None:
        if isinstance(value, Node):
            self.nodes.setdefault(node_id(value), node_payload(value))
        elif isinstance(value, Relationship):
            self.add(value.start_node)
            self.add(value.end_node)
            e = edge_payload(value)
            self.edges.setdefault(e["id"], e)
        elif isinstance(value, Path):
            for n in value.nodes:
                self.add(n)
            for r in value.relationships:
                self.add(r)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self.add(v)
        elif isinstance(value, dict):
            for v in value.values():
                self.add(v)

    def add_records(self, records: Iterable[Any]) -> "PayloadBuilder":
        for rec in records:
            self.add(list(rec.values()))
        return self

    def build(self, **extra: Any) -> dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values()), **extra}
