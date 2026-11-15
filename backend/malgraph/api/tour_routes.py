"""/api/tour: the graph tour, questions about your list answered from the graph's structure."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from .. import db, tour, users, voice_tour
from .serialize import PayloadBuilder

router = APIRouter(prefix="/api/tour")


def _user() -> str:
    username = users.current_username()
    if not username:
        raise HTTPException(401, "Sign in to take the tour.")
    return username


@router.get("")
def get_tour() -> dict[str, Any]:
    """Your taste clusters and the people and studios that bridge them, with the queries that found them."""
    return tour.public(tour.tour(_user()))


def _payload(ids: dict[str, list[int]] | None, query: str = tour.SHOW) -> dict[str, Any]:
    if ids is None:
        raise HTTPException(404, "That isn't part of your tour any more. Reload the tour.")
    builder = PayloadBuilder()
    with db.get_driver().session() as session:
        for r in session.run(query, **ids):
            builder.add(list(r.values()))
    return builder.build()


@router.get("/voices")
def get_voice_tour() -> dict[str, Any]:
    """The voice tour: bridges, twins, duos and distance on the graph of main characters' voice actors."""
    return tour.public(voice_tour.voices(_user()))


@router.get("/voices/{step}/{index}")
def voice_graph(step: Literal["bridges", "twins", "duos", "distance"], index: int) -> dict[str, Any]:
    """One card of the voice tour as graph data: the anime, the voice actors and the main characters they voice."""
    return _payload(voice_tour.show_item(_user(), step, index), voice_tour.SHOW)


@router.get("/cluster/{index}")
def cluster_graph(index: int) -> dict[str, Any]:
    """One cluster as graph data: all its anime and the people and studios behind two or more of them."""
    return _payload(tour.show_cluster(_user(), index))


@router.get("/bridge/{ref}")
def bridge_graph(ref: str) -> dict[str, Any]:
    """A bridge as graph data: the person or studio and one anime from each cluster they join."""
    return _payload(tour.show_bridge(_user(), ref))


@router.get("/{step}/{index}")
def step_graph(step: Literal["twins", "recs", "teams", "distance"], index: int) -> dict[str, Any]:
    """One card of the twins, recommendations, teams or distance step as graph data."""
    return _payload(tour.show_item(_user(), step, index))
