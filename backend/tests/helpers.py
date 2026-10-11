"""Shared fakes and factories for adapter and API tests."""

import asyncio
import io
import json
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar

from PIL import Image
from strands.models import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from porch.domain import (
    Detection,
    DoorEvent,
    House,
    RainRisk,
    Resident,
    Visit,
    VisitKind,
)
from porch.ports import PortError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_FIXTURE = REPO_ROOT / "fixtures" / "house.demo.json"


def demo_house() -> House:
    return House(
        id="demo",
        timezone="America/Los_Angeles",
        residents=(
            Resident(id="priya", display_name="Priya Shah", aliases=("P Shah",)),
            Resident(id="sam", display_name="Sam Okafor"),
            Resident(id="jo", display_name="Jo Lindqvist"),
        ),
        door_polygon=None,
        latitude=47.6205,
        longitude=-122.3493,
    )


def mkvisit(
    vid: str,
    start_ms: int,
    kind: VisitKind = VisitKind.ACTIVITY,
    house_id: str = "demo",
) -> Visit:
    return Visit(
        id=vid,
        house_id=house_id,
        device_id="d1",
        kind=kind,
        start_ms=start_ms,
        end_ms=start_ms + 1000,
        event_ids=("e1",),
        hero_media_key=None,
        clip_media_key=None,
        box=None,
        description=None,
        rain=None,
        provenance="replay",
        trace=(),
        claimed_by=None,
        version=1,
    )


class FakeRepo:
    """In-memory Repository for API tests."""

    def __init__(self, visits: list[Visit] | None = None) -> None:
        self._visits = {v.id: v for v in (visits or [])}
        self._versions: dict[str, int] = {}
        self._cursors: dict[str, int] = {}

    async def save_visits(self, visits: list[Visit]) -> None:
        changed = False
        for visit in visits:
            if self._visits.get(visit.id) != visit:
                self._visits[visit.id] = visit
                changed = True
        if changed:
            houses = {v.house_id for v in visits}
            for house_id in houses:
                await self.bump_version(house_id)

    async def visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        found = [
            v
            for v in self._visits.values()
            if v.house_id == house_id and start_ms <= v.start_ms < end_ms
        ]
        return sorted(found, key=lambda v: (v.start_ms, v.id))

    async def get_visit(self, visit_id: str) -> Visit | None:
        return self._visits.get(visit_id)

    async def claim(self, visit_id: str, resident_id: str) -> Visit | None:
        visit = self._visits.get(visit_id)
        if visit is None:
            return None
        updated = replace(visit, claimed_by=resident_id, version=visit.version + 1)
        self._visits[visit_id] = updated
        await self.bump_version(visit.house_id)
        return updated

    async def house_version(self, house_id: str) -> int:
        return self._versions.get(house_id, 0)

    async def bump_version(self, house_id: str) -> int:
        self._versions[house_id] = self._versions.get(house_id, 0) + 1
        return self._versions[house_id]

    async def get_cursor(self, device_id: str) -> int | None:
        return self._cursors.get(device_id)

    async def set_cursor(self, device_id: str, ms: int) -> None:
        self._cursors[device_id] = ms


class FakeClock:
    def __init__(self, now_ms: int) -> None:
        self.current = now_ms

    def now_ms(self) -> int:
        return self.current


def make_jpeg(width: int = 200, height: int = 200, color: str = "gray") -> bytes:
    """Tiny real JPEG; enrich crops it with Pillow."""
    image = Image.new("RGB", (width, height), color)
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


class FakeSource:
    """EventSource that yields its events once, in order."""

    def __init__(self, events: Sequence[DoorEvent]) -> None:
        self._events = list(events)

    async def poll(self) -> list[DoorEvent]:
        out, self._events = self._events, []
        return out


class FakeLabeler:
    def __init__(self, detections: Sequence[Detection] = ()) -> None:
        self._detections = tuple(detections)
        self.calls = 0

    async def detect(self, image: bytes) -> tuple[Detection, ...]:
        self.calls += 1
        return self._detections


class FakeReader:
    def __init__(self, lines: Sequence[str] = (), error: PortError | None = None) -> None:
        self._lines = tuple(lines)
        self._error = error

    async def read(self, image: bytes) -> tuple[str, ...]:
        if self._error is not None:
            raise self._error
        return self._lines


class FakeDescriber:
    def __init__(self, text: str | None = None, error: PortError | None = None) -> None:
        self._text = text
        self._error = error

    async def describe(self, clip_key: str) -> str | None:
        if self._error is not None:
            raise self._error
        return self._text


class FakeWeather:
    def __init__(self, risk: RainRisk | None = None, error: PortError | None = None) -> None:
        self._risk = risk
        self._error = error

    async def max_rain_probability_pct(self, hours: int) -> RainRisk | None:
        if self._error is not None:
            raise self._error
        return self._risk


T = TypeVar("T")


class ScriptedModel(Model):
    """Strands Model that replays scripted turns then a text reply.

    Each turn is a list of {"tool": name, "input": {...}} or {"text": "..."}
    items. `policy` picks a turn from the messages when given. `sleep_s`
    stalls the stream for timeout tests; `exc` makes the stream raise.
    """

    def __init__(
        self,
        turns: list[list[dict[str, Any]]] | None = None,
        policy: Callable[[Messages], list[dict[str, Any]]] | None = None,
        sleep_s: float = 0.0,
        exc: Exception | None = None,
    ) -> None:
        self._turns = list(turns) if turns is not None else None
        self._policy = policy
        self._sleep = sleep_s
        self._exc = exc
        self._config: dict[str, Any] = {"model_id": "scripted"}
        self.calls = 0
        self.specs: list[str] = []

    def get_config(self) -> dict[str, Any]:
        return self._config

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    async def structured_output(
        self,
        output_model: type[T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        yield {"output": output_model()}

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._exc is not None:
            raise self._exc
        self.calls += 1
        if tool_specs:
            self.specs = [spec["name"] for spec in tool_specs]
        if self._policy is not None:
            turn = self._policy(messages)
        elif self._turns:
            turn = self._turns.pop(0)
        else:
            turn = [{"text": "done"}]
        use_tool = False
        yield {"messageStart": {"role": "assistant"}}
        for index, item in enumerate(turn):
            if "tool" in item:
                use_tool = True
                yield {
                    "contentBlockStart": {
                        "start": {"toolUse": {"toolUseId": f"call{index}", "name": item["tool"]}}
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "delta": {"toolUse": {"input": json.dumps(item.get("input", {}))}}
                    }
                }
                yield {"contentBlockStop": {}}
            else:
                yield {"contentBlockDelta": {"delta": {"text": item["text"]}}}
                yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if use_tool else "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        }
