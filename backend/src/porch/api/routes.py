"""REST routes: visit cards with ETag, claims, residents, local media."""

from __future__ import annotations

import mimetypes
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from porch.adapters.local import FileMediaStore, MediaKeyError
from porch.adapters.ring.recorder import load_env_value
from porch.adapters.ring.webhook import (
    MAX_BODY_BYTES,
    WebhookSignatureError,
    parse_webhook,
    verify_signature,
)
from porch.api import cards
from porch.api.days import day_bounds, today
from porch.api.deps import AppContext, get_ctx
from porch.api.schemas import (
    ClaimRequest,
    Folded,
    ResidentOut,
    SpeechOut,
    SpeechRequest,
    VisitCard,
    VisitDetail,
    VisitList,
)
from porch.domain import House, Visit, VisitKind
from porch.ports import PortError

router = APIRouter()
health_router = APIRouter()
# Unguarded: Ring signs webhooks with HMAC, it cannot send a house bearer.
webhook_router = APIRouter()


def _require_house(ctx: AppContext, house_id: str) -> House:
    if house_id != ctx.house.id:
        raise HTTPException(status_code=404, detail=f"unknown house: {house_id}")
    return ctx.house


def _split_folded(visits: list[Visit]) -> tuple[list[Visit], Folded]:
    shown = [v for v in visits if v.kind not in cards.FOLDED_KINDS]
    folded = Folded(
        cars_passed=sum(1 for v in visits if v.kind == VisitKind.CARS_PASSED),
        activity=sum(1 for v in visits if v.kind == VisitKind.ACTIVITY),
    )
    return shown, folded


@health_router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/houses/{house_id}/visits", response_model=VisitList)
async def list_visits(
    request: Request,
    response: Response,
    house_id: str,
    ctx: Annotated[AppContext, Depends(get_ctx)],
    day: date | None = None,
) -> VisitList | Response:
    house = _require_house(ctx, house_id)
    day = day or today(house, ctx.clock)
    start_ms, end_ms = day_bounds(day, house)
    version = await ctx.repo.house_version(house_id)
    etag = f'"v{version}-{day.isoformat()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    visits = await ctx.repo.visits_between(house_id, start_ms, end_ms)
    shown, folded = _split_folded(visits)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"
    return VisitList(
        house_id=house_id,
        day=day.isoformat(),
        version=version,
        cards=tuple(cards.to_card(v, ctx) for v in shown),
        folded=folded,
    )


@router.get("/v1/visits/{visit_id}", response_model=VisitDetail)
async def visit_detail(visit_id: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> VisitDetail:
    visit = await ctx.repo.get_visit(visit_id)
    if visit is None:
        raise HTTPException(status_code=404, detail=f"unknown visit: {visit_id}")
    return cards.to_detail(visit, ctx)


@router.post("/v1/visits/{visit_id}/claim", response_model=VisitCard)
async def claim_visit(
    visit_id: str,
    body: ClaimRequest,
    ctx: Annotated[AppContext, Depends(get_ctx)],
) -> VisitCard:
    if not any(r.id == body.resident_id for r in ctx.house.residents):
        raise HTTPException(status_code=422, detail=f"unknown resident: {body.resident_id}")
    claimed = await ctx.repo.claim(visit_id, body.resident_id)
    if claimed is None:
        raise HTTPException(status_code=404, detail=f"unknown visit: {visit_id}")
    return cards.to_card(claimed, ctx)


@router.post("/v1/speech", response_model=SpeechOut)
async def speech(body: SpeechRequest, ctx: Annotated[AppContext, Depends(get_ctx)]) -> SpeechOut:
    """Synthesize text to audio; 404 when no Speech port is configured."""
    if ctx.speech is None:
        raise HTTPException(status_code=404, detail="speech is not configured")
    key = await ctx.speech.synthesize(body.text)
    return SpeechOut(url=await ctx.media.url(key, ctx.settings.api.media_url_ttl_s))


@router.get("/v1/houses/{house_id}/residents", response_model=list[ResidentOut])
async def list_residents(
    house_id: str, ctx: Annotated[AppContext, Depends(get_ctx)]
) -> list[ResidentOut]:
    house = _require_house(ctx, house_id)
    return [ResidentOut(id=r.id, display_name=r.display_name) for r in house.residents]


@webhook_router.post("/ring/webhook", include_in_schema=False)
async def ring_webhook(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Response:
    """Ring webhook: verify HMAC, parse, hand to the configured sink."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="webhook body too large")
    secret = load_env_value(ctx.settings.ring.webhook_secret_env, Path.cwd())
    if secret is None:
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    try:
        verify_signature(request.headers, body, secret)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=401, detail="bad signature") from exc
    event = parse_webhook(body)
    if event is None:
        return Response(status_code=204)
    if ctx.sink is None:
        raise HTTPException(status_code=503, detail="no event sink configured")
    await ctx.sink.accept(event)
    return Response(status_code=202)


@router.get("/v1/media/{key}")
async def get_media(key: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Response:
    if not isinstance(ctx.media, FileMediaStore):
        raise HTTPException(status_code=404, detail="media not served here")
    try:
        data = await ctx.media.get(key)
    except (MediaKeyError, PortError) as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type)
