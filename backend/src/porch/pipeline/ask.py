"""HouseholdAsk: agent answers household questions from saved visits.

Read-only tools expose visit cards; the model composes an answer and
cites visit ids. Cited ids are validated against what the tools actually
returned, so a made-up id never reaches the caller. Any failure returns
a plain fallback sentence.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel
from strands import Agent, tool
from strands.models import Model
from strands.types.exceptions import EventLoopException

from porch.api.cards import FOLDED_KINDS
from porch.api.days import day_bounds, today
from porch.config import Settings
from porch.domain import House, Visit, card_text
from porch.pipeline.agent import _ToolCounter
from porch.ports import Clock, Repository

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the household clerk for Porch Ledger.

Answer the resident's question using only facts returned by the tools.
Call list_visits for a day first, then get_visit for detail when needed.
Never invent visits, names or events. Cite only visit ids the tools
returned. Keep the answer to one or two plain sentences.
"""

_FALLBACK = "I could not answer that just now."


class AskAnswer(BaseModel):
    answer: str
    visit_ids: list[str]


@dataclass(slots=True)
class _Working:
    """Ids the tools handed out this run; citations must come from here."""

    returned_ids: set[str] = field(default_factory=set)


def _card_dict(visit: Visit, house: House) -> dict[str, object]:
    text = card_text(visit, house)
    return {
        "id": visit.id,
        "kind": str(visit.kind),
        "title": text.title,
        "span": text.span,
        "facts": list(text.facts),
        "description": text.description,
        "recipient_id": visit.box.recipient_id if visit.box else None,
        "blocks_door": visit.box.blocks_door if visit.box else None,
        "claimed_by": visit.claimed_by,
        "folded": visit.kind in FOLDED_KINDS,
    }


class HouseholdAsk:
    def __init__(
        self,
        model: Model,
        repo: Repository,
        house: House,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._model = model
        self._repo = repo
        self._house = house
        self._settings = settings
        self._clock = clock

    async def answer(self, question: str, resident_id: str | None = None) -> AskAnswer:
        """Run the agent; any failure yields the plain fallback sentence."""
        working = _Working()
        counter = _ToolCounter(self._settings.agent.max_tool_calls)
        agent = Agent(
            model=self._model,
            system_prompt=_SYSTEM_PROMPT,
            tools=self._tools(working),
            hooks=[counter],
            callback_handler=None,
        )
        prompt = json.dumps(
            {"question": question, "resident_id": resident_id},
            separators=(",", ":"),
        )
        reason: str | None = None
        try:
            result = await asyncio.wait_for(
                agent.invoke_async(prompt, structured_output_model=AskAnswer),
                timeout=self._settings.agent.timeout_s,
            )
        except TimeoutError:
            reason = "timeout"
        except EventLoopException as exc:
            reason = type(exc.original_exception).__name__
        except Exception as exc:
            # Deliberate boundary: any SDK or model failure degrades to the
            # fallback sentence rather than failing the tool call.
            reason = type(exc).__name__
        if reason is not None:
            logger.warning("HouseholdAsk failed (%s); fallback answer", reason)
            return AskAnswer(answer=_FALLBACK, visit_ids=[])
        out = result.structured_output
        if not isinstance(out, AskAnswer):
            return AskAnswer(answer=_FALLBACK, visit_ids=[])
        cited = [vid for vid in out.visit_ids if vid in working.returned_ids]
        return AskAnswer(answer=out.answer, visit_ids=cited)

    def _tools(self, working: _Working) -> list[object]:
        repo, house, clock = self._repo, self._house, self._clock

        @tool
        async def list_visits(day: str | None = None) -> str:
            """Visit cards for one local day, ISO date or empty for today."""
            local_day = today(house, clock) if not day else date.fromisoformat(day)
            start_ms, end_ms = day_bounds(local_day, house)
            visits = await repo.visits_between(house.id, start_ms, end_ms)
            working.returned_ids.update(visit.id for visit in visits)
            return json.dumps([_card_dict(visit, house) for visit in visits])

        @tool
        async def get_visit(visit_id: str) -> str:
            """Full detail for one visit, including the tool trace."""
            visit = await repo.get_visit(visit_id)
            if visit is None:
                return json.dumps({"error": f"unknown visit: {visit_id}"})
            working.returned_ids.add(visit.id)
            detail = _card_dict(visit, house)
            detail["rain"] = (
                None
                if visit.rain is None
                else {
                    "probability_pct": visit.rain.probability_pct,
                    "by_local_time": visit.rain.by_local_time,
                }
            )
            detail["trace"] = [
                {"tool": call.tool, "ok": call.ok, "note": call.note} for call in visit.trace
            ]
            return json.dumps(detail)

        return [list_visits, get_visit]
