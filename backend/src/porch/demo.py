"""Offline demo wiring: tape -> IngestService -> visits, no cloud calls.

The demo reader stands in for real OCR: it recognises a label crop by
sha256 of the exact bytes enrich produces, built per event id from the
tape's label_texts. Describer stays quiet so the fallback copy shows,
and weather is a fixed 70% by 4:00 pm.
"""

import hashlib
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcp import Client

from porch.adapters.local import FileMediaStore, SqliteRepository
from porch.adapters.local.house_file import load_house
from porch.adapters.tape import ReplaySource, Tape, TapeMediaFetcher, load_tape
from porch.api.deps import AppContext
from porch.config import Settings
from porch.domain import Detection, DoorEvent, NormBox, RainRisk, Visit, card_text
from porch.mcp_server import build_mcp
from porch.pipeline.agent import PorchClerk
from porch.pipeline.enrich import EnrichPorts, crop_label
from porch.pipeline.ingest import (
    IngestConfig,
    IngestPorts,
    IngestReport,
    IngestService,
)

FIXED_NOW_ENV = "PORCH_FIXED_NOW_MS"
# 5 minutes past the tape's last event keeps "now" inside the demo day
# while closing the trailing stitch group (engine gap is 2 minutes).
DEMO_TAIL_MS = 300_000
DEMO_RAIN = RainRisk(probability_pct=70, by_local_time="4:00 pm")


@dataclass(frozen=True, slots=True)
class FixedClock:
    at_ms: int

    def now_ms(self) -> int:
        return self.at_ms


def demo_clock(tape: Tape) -> FixedClock:
    """PORCH_FIXED_NOW_MS wins; otherwise just after the tape's last event."""
    override = os.environ.get(FIXED_NOW_ENV)
    if override is not None:
        return FixedClock(int(override))
    last = max((e.end_ms for e in tape.events), default=0)
    return FixedClock(last + DEMO_TAIL_MS)


class _NullLabeler:
    async def detect(self, image: bytes) -> tuple[Detection, ...]:
        return ()


class _DemoReader:
    """Replays tape-declared label text keyed by crop hash."""

    def __init__(self, crops: dict[str, tuple[str, ...]]) -> None:
        self._crops = crops

    async def read(self, image: bytes) -> tuple[str, ...]:
        return self._crops.get(hashlib.sha256(image).hexdigest(), ())


def _tape_boxes(tape: Tape) -> set[NormBox]:
    return {
        d.box
        for snap in tape.snapshots
        if snap.detections
        for d in snap.detections
        if d.label == "box" and d.box is not None
    }


def _demo_reader(tape: Tape, settings: Settings) -> _DemoReader:
    """Map sha256(crop) -> label lines for every labeled event's frames.

    Crops are taken at every box region seen anywhere on the tape, so a
    box_gone hero (which crops the missing box's old region) still keys.
    """
    crops: dict[str, tuple[str, ...]] = {}
    boxes = _tape_boxes(tape)
    for event_id, text in tape.label_texts.items():
        for snap in tape.snapshots_for(event_id):
            data = (tape.path / snap.file).read_bytes()
            for box in boxes:
                key = hashlib.sha256(crop_label(data, box, settings)).hexdigest()
                crops.setdefault(key, (text,))
    return _DemoReader(crops)


class _NullDescriber:
    async def describe(self, clip_key: str) -> str | None:
        return None


class _DemoWeather:
    async def max_rain_probability_pct(self, hours: int) -> RainRisk | None:
        return DEMO_RAIN


class _AllNowSource:
    """EventSource whose one poll returns every tape event at once."""

    def __init__(self, source: ReplaySource) -> None:
        self._source = source

    async def poll(self) -> list[DoorEvent]:
        return await self._source.all_now()


def repo_root() -> Path:
    """The repository root, three levels above src/porch."""
    return Path(__file__).resolve().parents[3]


async def echo_fixtures() -> dict[str, object]:
    """StructuredContent of the tools the Echo client consumes.

    Written to echo/src/__fixtures__; the drift test regenerates in memory
    and compares. Claim runs last so inbox fixtures stay unclaimed.
    """
    tape = load_tape(repo_root() / "fixtures" / "tapes" / "synthetic-day")
    with tempfile.TemporaryDirectory() as tmp:
        ctx = demo_context(
            tape, Settings(), Path(tmp), repo_root() / "fixtures" / "house.demo.json"
        )
        await ingest_tape(ctx, tape)
        async with Client(build_mcp(ctx)) as mcp:
            inbox_p = await mcp.call_tool("anything_for_me", {"resident_id": "priya"})
            inbox_s = await mcp.call_tool("anything_for_me", {"resident_id": "sam"})
            roster = await mcp.call_tool("residents", {})
            first = inbox_p.structured_content["items"][0]["id"]
            claim = await mcp.call_tool("claim_box", {"visit_id": first, "resident_id": "priya"})
    return {
        "inbox-priya.json": inbox_p.structured_content,
        "inbox-sam.json": inbox_s.structured_content,
        "residents.json": roster.structured_content,
        "claim-box.json": claim.structured_content,
    }


def demo_enrich_ports(tape: Tape, ctx: AppContext) -> EnrichPorts:
    """The offline enrichment ports ingest_tape wires; shared with tests."""
    return EnrichPorts(
        media=ctx.media,
        reader=_demo_reader(tape, ctx.settings),
        describer=_NullDescriber(),
        weather=_DemoWeather(),
    )


async def ingest_tape(ctx: AppContext, tape: Tape, clerk: PorchClerk | None = None) -> IngestReport:
    """One pass through IngestService with offline ports."""
    service = IngestService(
        ports=IngestPorts(
            source=_AllNowSource(ReplaySource(tape, speed=1.0, clock=ctx.clock)),
            fetcher=TapeMediaFetcher(tape),
            media=ctx.media,
            labeler=_NullLabeler(),
            enrich=demo_enrich_ports(tape, ctx),
            repo=ctx.repo,
        ),
        config=IngestConfig(
            house=ctx.house,
            settings=ctx.settings,
            clock=ctx.clock,
        ),
        clerk=clerk,
    )
    return await service.run_once()


def demo_context(
    tape: Tape,
    settings: Settings,
    local_dir: Path,
    house_file: Path,
) -> AppContext:
    """AppContext backed by a fresh local dir (sqlite + file media)."""
    return AppContext(
        settings=settings,
        repo=SqliteRepository(local_dir / "porch.db"),
        media=FileMediaStore(local_dir / "media", settings.api.public_base_url),
        house=load_house(house_file),
        clock=demo_clock(tape),
    )


def card_lines(visits: Sequence[Visit], ctx: AppContext) -> list[str]:
    """One printable line per visit via domain card copy."""
    out = []
    for visit in visits:
        text = card_text(visit, ctx.house)
        facts = "; ".join(text.facts) if text.facts else "-"
        out.append(f"{text.title} | {text.span} | {facts} | {text.description}")
    return out
