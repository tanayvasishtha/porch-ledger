"""Bearer auth against a stored sha256 of the house key.

Open when house_key_sha256 is None (local replay only); otherwise every
v1 request and the mounted MCP endpoint need `Authorization: Bearer <key>`
matching the hash. Router dependencies do not reach mounted ASGI apps, so
the mount gets its own middleware.
"""

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from porch.api.deps import AppContext, get_ctx
from porch.api.schemas import PROBLEM_MEDIA_TYPE, Problem

BEARER = "bearer"


def _key_matches(header: str | None, expected: str) -> bool:
    scheme, _, token = (header or "").partition(" ")
    candidate = hashlib.sha256(token.encode()).hexdigest() if scheme.lower() == BEARER else ""
    return hmac.compare_digest(candidate, expected)


def bearer_guard(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> None:
    """FastAPI dependency raising 401 unless the bearer key matches."""
    expected = ctx.settings.api.house_key_sha256
    if expected is not None and not _key_matches(request.headers.get("authorization"), expected):
        raise HTTPException(status_code=401, detail="missing or invalid house key")


class BearerASGIMiddleware:
    """ASGI-level bearer check for mounted apps like the MCP endpoint."""

    def __init__(self, app: ASGIApp, expected: str | None) -> None:
        self._app = app
        self._expected = expected

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._expected is None:
            await self._app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        if _key_matches(headers.get("authorization"), self._expected):
            await self._app(scope, receive, send)
            return
        problem = Problem(
            type="about:blank",
            title="Unauthorized",
            status=401,
            detail="missing or invalid house key",
        )
        response = JSONResponse(
            status_code=401,
            media_type=PROBLEM_MEDIA_TYPE,
            content=problem.model_dump(),
        )
        await response(scope, receive, send)
