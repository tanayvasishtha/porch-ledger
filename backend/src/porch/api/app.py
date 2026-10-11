"""create_app: wire ctx, CORS, problem+json handlers, routers and MCP."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from porch.api.auth import BearerASGIMiddleware, bearer_guard
from porch.api.deps import AppContext
from porch.api.routes import health_router, router, webhook_router
from porch.api.schemas import PROBLEM_MEDIA_TYPE, Problem
from porch.mcp_server import build_mcp


def _problem_response(status: int, detail: str) -> JSONResponse:
    titles = {401: "Unauthorized", 404: "Not Found", 422: "Unprocessable Content"}
    problem = Problem(
        type="about:blank",
        title=titles.get(status, "Error"),
        status=status,
        detail=detail,
    )
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        content=problem.model_dump(),
    )


def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return _problem_response(500, "internal error")
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"
    return _problem_response(exc.status_code, detail)


def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return _problem_response(500, "internal error")
    errors = exc.errors()
    first = errors[0] if errors else {}
    detail = f"invalid request: {first.get('msg', 'validation failed')}"
    return _problem_response(422, detail)


def create_app(ctx: AppContext) -> FastAPI:
    """Build the app around an explicit context; nothing lives in globals."""
    mcp = build_mcp(ctx)
    # Stateless JSON responses: no sessions to leak between requests.
    mcp_http = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A mounted app's own lifespan never runs; the host must enter
        # the session manager itself.
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Porch Ledger", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.mcp = mcp
    origins = ctx.settings.api.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.include_router(health_router)
    app.include_router(router, dependencies=[Depends(bearer_guard)])
    app.include_router(webhook_router)
    app.mount(
        "/mcp",
        BearerASGIMiddleware(mcp_http, ctx.settings.api.house_key_sha256),
    )
    return app
