"""PorchClerk: agent-driven visit enrichment with a deterministic fallback.

The Strands agent calls the same step functions as pipeline.enrich; the
model only picks the order. Every tool re-checks its precondition, so a
wrong choice returns a skipped note instead of touching the visit. Any
agent failure falls back to the deterministic enrich() and records it.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, replace
from typing import Any

from strands import Agent, tool
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import BeforeToolCallEvent
from strands.models import Model
from strands.types.exceptions import EventLoopException

from porch.config import Settings
from porch.domain import House, ToolCall, Visit
from porch.pipeline.enrich import (
    EnrichPorts,
    check_door_step,
    describe_clip_step,
    enrich,
    needs_clip,
    needs_door_check,
    needs_label,
    needs_rain,
    rain_outlook_step,
    read_label_step,
)
from porch.ports import Clock

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are PorchClerk, the clerk that enriches one doorstep visit.

Rules:
- Call read_label only when the visit has a box and a hero image.
- Call check_door only for deliveries.
- Call rain_outlook only for deliveries.
- Call describe_clip only when the visit has a clip.
- Never invent names or facts; the tools do the real work.
- Stop when every useful step has run.
"""

_SKIPPED = json.dumps({"skipped": True})
_DONE = json.dumps({"ok": True})


class ToolCallLimitError(Exception):
    """The model asked for more tools than AgentSettings.max_tool_calls."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"tool limit {limit}")


class _ToolCounter(HookProvider):
    """Counts tool invocations; over the limit ends the run via an error."""

    def __init__(self, limit: int) -> None:
        self.count = 0
        self._limit = limit

    def register_hooks(self, registry: HookRegistry, **kwargs: object) -> None:
        registry.add_callback(BeforeToolCallEvent, self._count)

    def _count(self, event: BeforeToolCallEvent[Any]) -> None:
        self.count += 1
        if self.count > self._limit:
            raise ToolCallLimitError(self._limit)


@dataclass(slots=True)
class _Working:
    """Mutable per-run state the tool closures update."""

    visit: Visit


class PorchClerk:
    def __init__(
        self,
        model: Model,
        ports: EnrichPorts,
        house: House,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._model = model
        self._ports = ports
        self._house = house
        self._settings = settings
        self._clock = clock

    async def enrich(self, visit: Visit) -> Visit:
        """Run the agent; on any failure fall back to deterministic enrich."""
        working = _Working(visit)
        counter = _ToolCounter(self._settings.agent.max_tool_calls)
        agent = Agent(
            model=self._model,
            system_prompt=_SYSTEM_PROMPT,
            tools=self._tools(working),
            hooks=[counter],
            callback_handler=None,
        )
        reason: str | None = None
        try:
            await asyncio.wait_for(
                agent.invoke_async(_prompt_for(visit)),
                timeout=self._settings.agent.timeout_s,
            )
        except TimeoutError:
            reason = "timeout"
        except EventLoopException as exc:
            # The SDK wraps hook and model errors; name the original cause.
            if isinstance(exc.original_exception, ToolCallLimitError):
                reason = "tool limit"
            else:
                reason = type(exc.original_exception).__name__
        except Exception as exc:
            # Deliberate boundary: any SDK or model failure degrades to the
            # deterministic enrich rather than losing the visit.
            reason = type(exc).__name__
        if reason is not None:
            logger.warning("PorchClerk failed (%s); falling back to enrich", reason)
            fallback = await enrich(visit, self._house, self._ports, self._settings, self._clock)
            return replace(
                fallback,
                trace=(
                    *fallback.trace,
                    ToolCall(
                        tool="agent",
                        ok=False,
                        latency_ms=0,
                        note=f"fallback: {reason}",
                    ),
                ),
            )
        result = working.visit
        return replace(
            result,
            trace=(
                *result.trace,
                ToolCall(
                    tool="agent",
                    ok=True,
                    latency_ms=0,
                    note=f"{counter.count} tools",
                ),
            ),
        )

    def _tools(self, working: _Working) -> list[object]:
        ports, house, settings, clock = (
            self._ports,
            self._house,
            self._settings,
            self._clock,
        )

        @tool
        async def read_label() -> str:
            """OCR the delivery label on the hero image and match a resident."""
            if not needs_label(working.visit):
                return _SKIPPED
            working.visit = await read_label_step(working.visit, house, ports, settings, clock)
            return _DONE

        @tool
        async def check_door() -> str:
            """Check whether a delivery box blocks the door zone."""
            if not needs_door_check(working.visit):
                return _SKIPPED
            working.visit = check_door_step(working.visit, house, settings, clock)
            return _DONE

        @tool
        async def rain_outlook() -> str:
            """Fetch the rain outlook for a delivery."""
            if not needs_rain(working.visit):
                return _SKIPPED
            working.visit = await rain_outlook_step(working.visit, ports, settings, clock)
            return _DONE

        @tool
        async def describe_clip() -> str:
            """Describe the visit's video clip in one sentence."""
            if not needs_clip(working.visit):
                return _SKIPPED
            working.visit = await describe_clip_step(working.visit, ports, clock)
            return _DONE

        return [read_label, check_door, rain_outlook, describe_clip]


def _prompt_for(visit: Visit) -> str:
    facts = {
        "kind": str(visit.kind),
        "has_box": visit.box is not None,
        "has_hero": visit.hero_media_key is not None,
        "has_clip": visit.clip_media_key is not None,
    }
    return json.dumps({"visit": facts}, separators=(",", ":"))
