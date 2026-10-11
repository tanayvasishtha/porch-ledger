"""create_app: wire ctx, CORS, problem+json handlers and the routers."""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from porch.api.auth import bearer_guard
from porch.api.deps import AppContext
from porch.api.routes import health_router, router
from porch.api.schemas import Problem

PROBLEM_MEDIA_TYPE = "application/problem+json"


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
    app = FastAPI(title="Porch Ledger")
    app.state.ctx = ctx
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
    return app
