"""App context: everything a request needs, stored on app.state once."""

from dataclasses import dataclass

from fastapi import Request

from porch.config import Settings
from porch.domain import House
from porch.ports import Clock, MediaStore, Repository


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    repo: Repository
    media: MediaStore
    house: House
    clock: Clock


def get_ctx(request: Request) -> AppContext:
    """FastAPI dependency: pull the context off app.state."""
    ctx: AppContext = request.app.state.ctx
    return ctx
