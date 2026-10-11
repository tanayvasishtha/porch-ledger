"""App context: everything a request needs, stored on app.state once."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request

from porch.config import Settings
from porch.domain import House

if TYPE_CHECKING:
    from porch.pipeline.ask import HouseholdAsk
from porch.ports import Clock, EventSink, MediaStore, Repository, Speech


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    repo: Repository
    media: MediaStore
    house: House
    clock: Clock
    # Where verified webhook events go; None means POST /ring/webhook is off.
    sink: EventSink | None = None
    # Household question agent; None makes the ask tool return its fallback.
    # Household question agent; None makes the ask tool return its fallback.
    ask: HouseholdAsk | None = None
    # Speech synthesis; None means /v1/speech answers 404 (local demo).
    speech: Speech | None = None


def get_ctx(request: Request) -> AppContext:
    """FastAPI dependency: pull the context off app.state."""
    ctx: AppContext = request.app.state.ctx
    return ctx
