"""Build API cards and details from domain visits; shared by REST and MCP."""

from porch.api.deps import AppContext
from porch.api.schemas import BoxOut, ToolCallOut, VisitCard, VisitDetail
from porch.domain import Visit, card_text


def media_url(ctx: AppContext, key: str | None) -> str | None:
    if key is None:
        return None
    base = ctx.settings.api.public_base_url.rstrip("/")
    return f"{base}/v1/media/{key}"


def to_card(visit: Visit, ctx: AppContext) -> VisitCard:
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
        hero_url=media_url(ctx, visit.hero_media_key),
        clip_url=media_url(ctx, visit.clip_media_key),
        recipient_id=visit.box.recipient_id if visit.box else None,
        blocks_door=visit.box.blocks_door if visit.box else None,
        claimed_by=visit.claimed_by,
        provenance=visit.provenance,
        version=visit.version,
    )


def to_detail(visit: Visit, ctx: AppContext) -> VisitDetail:
    card = to_card(visit, ctx)
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
    )
