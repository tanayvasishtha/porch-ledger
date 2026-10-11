import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from strands.types.content import Messages

from porch.adapters.local import FileMediaStore
from porch.adapters.tape import load_tape
from porch.config import AgentSettings, Settings
from porch.demo import demo_context, demo_enrich_ports, ingest_tape
from porch.domain import BoxFacts, NormBox, Visit, VisitKind
from porch.pipeline.agent import PorchClerk
from porch.pipeline.enrich import EnrichPorts
from tests.helpers import (
    DEMO_FIXTURE,
    REPO_ROOT,
    FakeClock,
    FakeDescriber,
    FakeReader,
    FakeWeather,
    ScriptedModel,
    demo_house,
    mkvisit,
)

TAPE_DIR = REPO_ROOT / "fixtures" / "tapes" / "synthetic-day"
BOX = NormBox(x=0.1, y=0.5, w=0.2, h=0.2)


def mkdel() -> Visit:
    return replace(
        mkvisit("v1", 1000, VisitKind.DELIVERY),
        box=BoxFacts(
            box=BOX,
            recipient_id=None,
            recipient_state="not_checked",
            blocks_door=None,
            door_overlap=None,
        ),
        hero_media_key="hero",
    )


def mkports(tmp_path: Path) -> EnrichPorts:
    return EnrichPorts(
        media=FileMediaStore(tmp_path / "media", "http://x"),
        reader=FakeReader(),
        describer=FakeDescriber(),
        weather=FakeWeather(),
    )


def clerk(
    model: ScriptedModel,
    ports: EnrichPorts,
    settings: Settings | None = None,
) -> PorchClerk:
    return PorchClerk(
        model,
        ports,
        demo_house(),
        settings or Settings(),
        FakeClock(10_000),
    )


def enrich_policy(messages: Messages) -> list[dict[str, Any]]:
    """Calls exactly the tools whose preconditions hold for the visit JSON."""
    facts: dict[str, Any] | None = None
    for message in messages:
        for block in message.get("content", []):
            text = block.get("text", "")
            if text.startswith("{") and '"visit"' in text:
                facts = json.loads(text)["visit"]
    if facts is None:
        return [{"text": "done"}]
    tools: list[dict[str, Any]] = []
    if facts["kind"] in ("delivery", "box_gone") and facts["has_box"] and facts["has_hero"]:
        tools.append({"tool": "read_label"})
    if facts["kind"] == "delivery" and facts["has_box"]:
        tools.append({"tool": "check_door"})
    if facts["kind"] == "delivery":
        tools.append({"tool": "rain_outlook"})
    if facts["has_clip"]:
        tools.append({"tool": "describe_clip"})
    done = sum(
        1 for message in messages for block in message.get("content", []) if "toolResult" in block
    )
    pending = tools[done:]
    return pending[:1] or [{"text": "done"}]


def test_agent_matches_deterministic_for_the_demo_day(tmp_path: Path) -> None:
    """Every visit the synthetic day yields is identical through both paths,
    except for the trailing agent ToolCall on the clerk-run visits."""
    tape = load_tape(TAPE_DIR)
    settings = Settings()
    baseline_ctx = demo_context(tape, settings, tmp_path / "base", DEMO_FIXTURE)
    asyncio.run(ingest_tape(baseline_ctx, tape))

    clerk_ctx = demo_context(tape, settings, tmp_path / "clerk", DEMO_FIXTURE)
    porch_clerk = PorchClerk(
        ScriptedModel(policy=enrich_policy),
        demo_enrich_ports(tape, clerk_ctx),
        clerk_ctx.house,
        settings,
        clerk_ctx.clock,
    )
    asyncio.run(ingest_tape(clerk_ctx, tape, clerk=porch_clerk))

    end = max(e.end_ms for e in tape.events) + 1
    baseline = {v.id: v for v in asyncio.run(baseline_ctx.repo.visits_between("demo", 0, end))}
    acted = {v.id: v for v in asyncio.run(clerk_ctx.repo.visits_between("demo", 0, end))}
    assert baseline.keys() == acted.keys()
    for visit_id, expected in baseline.items():
        actual = acted[visit_id]
        assert actual.trace[-1].tool == "agent"
        assert actual.trace[-1].ok is True
        assert replace(actual, trace=actual.trace[:-1]) == expected


def test_tool_limit_falls_back(tmp_path: Path) -> None:
    ports = mkports(tmp_path)
    model = ScriptedModel(
        turns=[
            [{"tool": "read_label"}],
            [{"tool": "check_door"}],
            [{"text": "x"}],
        ]
    )
    settings = Settings(agent=AgentSettings(max_tool_calls=1))
    out = asyncio.run(clerk(model, ports, settings).enrich(mkdel()))
    assert out.trace[-1].tool == "agent"
    assert out.trace[-1].ok is False
    assert "tool limit" in out.trace[-1].note


def test_timeout_falls_back(tmp_path: Path) -> None:
    ports = mkports(tmp_path)
    model = ScriptedModel(sleep_s=5.0)
    settings = Settings(agent=AgentSettings(timeout_s=1))
    out = asyncio.run(clerk(model, ports, settings).enrich(mkdel()))
    assert out.trace[-1].tool == "agent"
    assert out.trace[-1].ok is False


def test_model_error_falls_back(tmp_path: Path) -> None:
    ports = mkports(tmp_path)
    model = ScriptedModel(exc=RuntimeError("model dead"))
    out = asyncio.run(clerk(model, ports).enrich(mkdel()))
    assert out.trace[-1].tool == "agent"
    assert out.trace[-1].ok is False


def test_precondition_false_tool_is_skipped(tmp_path: Path) -> None:
    """A visitor asked for check_door: skipped, no ToolCall recorded."""
    ports = mkports(tmp_path)
    visitor = mkvisit("v5", 5000, VisitKind.VISITOR)
    model = ScriptedModel(turns=[[{"tool": "check_door"}], [{"text": "done"}]])
    out = asyncio.run(clerk(model, ports).enrich(visitor))
    assert not any(call.tool == "check_door" for call in out.trace)
    assert out.trace[-1].tool == "agent"
    assert out.trace[-1].ok is True
