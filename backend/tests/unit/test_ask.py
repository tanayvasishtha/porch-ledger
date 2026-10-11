import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp import Client

from porch.adapters.local import SqliteRepository
from porch.api.deps import AppContext
from porch.config import AgentSettings, Settings
from porch.domain import VisitKind
from porch.mcp_server import build_mcp
from porch.pipeline.ask import AskAnswer, HouseholdAsk
from porch.ports import Repository
from tests.helpers import (
    FakeClock,
    ScriptedModel,
    demo_house,
    mkvisit,
)
from tests.unit.test_api import mkctx

NOW_MS = int(datetime(2026, 6, 1, 19, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)


def mkservice(
    tmp_path: Path, model: ScriptedModel, settings: Settings | None = None
) -> HouseholdAsk:
    return HouseholdAsk(
        model=model,
        repo=SqliteRepository(tmp_path / "ask.db"),
        house=demo_house(),
        settings=settings or Settings(),
        clock=FakeClock(NOW_MS),
    )


async def _seeded(repo: Repository) -> list[str]:
    visit = mkvisit("del-1", NOW_MS - 3_600_000, VisitKind.DELIVERY)
    await repo.save_visits([visit])
    return [visit.id]


def test_answer_cites_returned_ids(tmp_path: Path) -> None:
    """The answer cites only ids the tools returned this run."""
    repo = SqliteRepository(tmp_path / "ask.db")
    visit_ids = asyncio.run(_seeded(repo))
    model = ScriptedModel(
        turns=[
            [{"tool": "list_visits", "input": {"day": "2026-06-01"}}],
            [
                {
                    "tool": "AskAnswer",
                    "input": {"answer": "One delivery today.", "visit_ids": visit_ids},
                }
            ],
        ]
    )
    service = HouseholdAsk(
        model=model,
        repo=repo,
        house=demo_house(),
        settings=Settings(),
        clock=FakeClock(NOW_MS),
    )
    out = asyncio.run(service.answer("what came today?"))
    assert out.answer == "One delivery today."
    assert out.visit_ids == visit_ids


def test_unknown_ids_are_dropped(tmp_path: Path) -> None:
    model = ScriptedModel(
        turns=[
            [{"tool": "list_visits", "input": {"day": "2026-06-01"}}],
            [
                {
                    "tool": "AskAnswer",
                    "input": {
                        "answer": "Something happened.",
                        "visit_ids": ["bogus-id"],
                    },
                }
            ],
        ]
    )
    service = mkservice(tmp_path, model)
    asyncio.run(_seeded(service._repo))
    out = asyncio.run(service.answer("what came today?"))
    assert out.visit_ids == []


def test_timeout_returns_fallback(tmp_path: Path) -> None:
    model = ScriptedModel(sleep_s=5.0)
    settings = Settings(agent=AgentSettings(timeout_s=1))
    service = mkservice(tmp_path, model, settings)
    out = asyncio.run(service.answer("what came today?"))
    assert out.answer == "I could not answer that just now."
    assert out.visit_ids == []


def _ask_ctx(tmp_path: Path, ask: HouseholdAsk | None) -> AppContext:
    ctx = mkctx(tmp_path)
    return AppContext(
        settings=ctx.settings,
        repo=ctx.repo,
        media=ctx.media,
        house=ctx.house,
        clock=ctx.clock,
        ask=ask,
    )


def test_ask_tool_without_model_returns_fallback(tmp_path: Path) -> None:
    """ctx.ask=None: the tool answers with the fallback sentence."""

    async def scenario() -> AskAnswer:
        async with Client(build_mcp(_ask_ctx(tmp_path, None))) as mcp:
            result = await mcp.call_tool("ask", {"question": "did anything come today?"})
            return AskAnswer.model_validate(result.structured_content)

    out = asyncio.run(scenario())
    assert out.answer == "I could not answer that just now."


def test_ask_tool_rejects_long_question(tmp_path: Path) -> None:
    async def scenario() -> bool:
        async with Client(build_mcp(_ask_ctx(tmp_path, None))) as mcp:
            result = await mcp.call_tool("ask", {"question": "x" * 301})
            return bool(result.is_error)

    assert asyncio.run(scenario()) is True
