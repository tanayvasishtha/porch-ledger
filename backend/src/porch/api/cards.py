"""Build API cards and details from domain visits; shared by REST and MCP."""

import asyncio
from collections.abc import Iterable, Mapping

from porch.api.deps import AppContext
from porch.api.schemas import BoxOut, ToolCallOut, VisitCard, VisitDetail
from porch.domain import Visit, VisitKind, card_text

FOLDED_KINDS = {VisitKind.CARS_PASSED, VisitKind.ACTIVITY}


async def media_urls(ctx: AppContext, visits: Iterable[Visit]) -> dict[str, str]:
    """One gather per response; the store decides relative vs pre-signed."""
    keys = {
        key
        for visit in visits
        for key in (visit.hero_media_key, visit.clip_media_key)
        if key is not None
    }
    ttl_s = ctx.settings.api.media_url_ttl_s
    urls = await asyncio.gather(*(ctx.media.url(key, ttl_s) for key in keys))
    return dict(zip(keys, urls, strict=True))


def to_card(visit: Visit, ctx: AppContext, urls: Mapping[str, str]) -> VisitCard:
    text = card_text(visit, ctx.house)
    return VisitCard(
        id=visit.id,
        kind=str(visit.kind),
        start_ms=visit.start_ms,
        end_ms=visit.end_ms,
        title=text.title,
        span=text.span,
        facts=text.facts,
        description=text.description,
        hero_url=urls.get(visit.hero_media_key) if visit.hero_media_key else None,
        clip_url=urls.get(visit.clip_media_key) if visit.clip_media_key else None,
        recipient_id=visit.box.recipient_id if visit.box else None,
        blocks_door=visit.box.blocks_door if visit.box else None,
        claimed_by=visit.claimed_by,
        provenance=visit.provenance,
        version=visit.version,
    )


def to_detail(visit: Visit, ctx: AppContext, urls: Mapping[str, str]) -> VisitDetail:
    card = to_card(visit, ctx, urls)
    box = visit.box
    return VisitDetail(
        **card.model_dump(),
        box=BoxOut(
            x=box.box.x,
            y=box.box.y,
            w=box.box.w,
            h=box.box.h,
            recipient_id=box.recipient_id,
            recipient_state=box.recipient_state,
            blocks_door=box.blocks_door,
        )
        if box is not None
        else None,
        door_overlap=box.door_overlap if box is not None else None,
        trace=[
            ToolCallOut(
                tool=call.tool,
                ok=call.ok,
                latency_ms=call.latency_ms,
                note=call.note,
            )
            for call in visit.trace
        ],
        door_polygon=(
            [[x, y] for x, y in ctx.house.door_polygon]
            if ctx.house.door_polygon is not None
            else None
        ),
    )
