"""MCP server: household tools, built on the same context as the REST API."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from porch.api import cards
from porch.api.days import day_bounds, today
from porch.api.deps import AppContext
from porch.api.schemas import Inbox, VisitCard, VisitDetail
from porch.domain import Resident, Visit, VisitKind, spoken_inbox

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_CLOSED = ToolAnnotations(open_world_hint=False)


def _resident(ctx: AppContext, resident_id: str) -> Resident:
    resident = next((r for r in ctx.house.residents if r.id == resident_id), None)
    if resident is None:
        msg = f"unknown resident: {resident_id}"
        raise ToolError(msg)
    return resident


def _is_mine(visit: Visit, resident_id: str) -> bool:
    return (
        visit.kind == VisitKind.DELIVERY
        and visit.box is not None
        and visit.box.recipient_id == resident_id
        and visit.claimed_by in (None, resident_id)
    )


async def _todays_visits(ctx: AppContext) -> list[Visit]:
    day = today(ctx.house, ctx.clock)
    start_ms, end_ms = day_bounds(day, ctx.house)
    return await ctx.repo.visits_between(ctx.house.id, start_ms, end_ms)


def build_mcp(ctx: AppContext) -> MCPServer:
    """The porch-ledger server; every tool closes over the app context."""
    mcp = MCPServer(
        "porch-ledger",
        instructions=(
            "Household porch data for one house. Ask what happened today, "
            "who has boxes waiting, or claim a delivery for a resident."
        ),
    )

    @mcp.tool(annotations=_READ_ONLY)
    async def anything_for_me(resident_id: str) -> Inbox:
        """Spoken summary and delivery cards for one resident, today."""
        resident = _resident(ctx, resident_id)
        visits = await _todays_visits(ctx)
        return Inbox(
            spoken=spoken_inbox(resident, visits, ctx.house),
            items=[cards.to_card(v, ctx) for v in visits if _is_mine(v, resident_id)],
        )

    @mcp.tool(annotations=_READ_ONLY)
    async def todays_visits(kind: str | None = None) -> list[VisitCard]:
        """Today's visit cards; folded kinds appear only when kind asks."""
        visits = await _todays_visits(ctx)
        if kind is None:
            visits = [v for v in visits if v.kind not in cards.FOLDED_KINDS]
        else:
            visits = [v for v in visits if v.kind == kind]
        return [cards.to_card(v, ctx) for v in visits]

    @mcp.tool(annotations=_READ_ONLY)
    async def visit_detail(visit_id: str) -> VisitDetail:
        """Full detail for one visit."""
        visit = await ctx.repo.get_visit(visit_id)
        if visit is None:
            msg = f"unknown visit: {visit_id}"
            raise ToolError(msg)
        return cards.to_detail(visit, ctx)

    @mcp.tool(annotations=_CLOSED)
    async def claim_box(visit_id: str, resident_id: str) -> VisitCard:
        """Mark a delivery as claimed by a resident."""
        _resident(ctx, resident_id)
        claimed = await ctx.repo.claim(visit_id, resident_id)
        if claimed is None:
            msg = f"unknown visit: {visit_id}"
            raise ToolError(msg)
        return cards.to_card(claimed, ctx)

    return mcp
