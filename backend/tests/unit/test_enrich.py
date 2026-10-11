import asyncio
from dataclasses import replace
from pathlib import Path

from porch.adapters.local import FileMediaStore
from porch.config import Settings
from porch.domain import BoxFacts, House, NormBox, RainRisk, Visit, VisitKind
from porch.pipeline.enrich import EnrichPorts, enrich
from porch.ports import (
    ClipDescriber,
    Clock,
    LabelReader,
    MediaStore,
    PortError,
    Weather,
)
from tests.helpers import (
    FakeClock,
    FakeDescriber,
    FakeReader,
    FakeWeather,
    demo_house,
    make_jpeg,
    mkvisit,
)

BOX = NormBox(x=0.1, y=0.5, w=0.2, h=0.2)
DOOR_POLY = ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))


def mkdel(clip_media_key: str | None = None) -> Visit:
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
        clip_media_key=clip_media_key,
    )


def mkports(
    tmp_path: Path,
    media: MediaStore | None = None,
    reader: LabelReader | None = None,
    describer: ClipDescriber | None = None,
    weather: Weather | None = None,
) -> EnrichPorts:
    return EnrichPorts(
        media=media or FileMediaStore(tmp_path / "media", "http://x"),
        reader=reader or FakeReader(),
        describer=describer or FakeDescriber(),
        weather=weather or FakeWeather(),
    )


def run(
    visit: Visit,
    ports: EnrichPorts,
    house: House | None = None,
    clock: Clock | None = None,
) -> Visit:
    return asyncio.run(
        enrich(
            visit,
            house or demo_house(),
            ports,
            Settings(),
            clock or FakeClock(10_000),
        )
    )


def test_label_match_and_door_check(tmp_path: Path) -> None:
    media = FileMediaStore(tmp_path / "media", "http://x")
    key = asyncio.run(media.put(make_jpeg(), ".jpg"))
    visit = replace(mkdel(), hero_media_key=key)
    house = replace(demo_house(), door_polygon=DOOR_POLY)
    ports = mkports(tmp_path, media=media, reader=FakeReader(["PRIYA SHAH"]))
    out = run(visit, ports, house=house)
    assert out.box is not None
    assert out.box.recipient_state == "matched"
    assert out.box.recipient_id == "priya"
    assert out.box.blocks_door is True
    assert out.box.door_overlap == 1.0
    tools = [c.tool for c in out.trace]
    assert tools == ["read_label", "check_door", "rain_outlook"]
    assert all(c.ok for c in out.trace)


def test_label_read_failure_recorded_others_run(tmp_path: Path) -> None:
    media = FileMediaStore(tmp_path / "media", "http://x")
    key = asyncio.run(media.put(make_jpeg(), ".jpg"))
    visit = replace(mkdel(), hero_media_key=key)
    house = replace(demo_house(), door_polygon=DOOR_POLY)
    ports = mkports(
        tmp_path,
        media=media,
        reader=FakeReader(error=PortError("down")),
        weather=FakeWeather(RainRisk(80, "4:00 pm")),
    )
    out = run(visit, ports, house=house)
    by_tool = {c.tool: c for c in out.trace}
    assert by_tool["read_label"].ok is False
    assert by_tool["read_label"].note == "PortError: down"
    assert by_tool["check_door"].ok is True
    assert by_tool["rain_outlook"].ok is True
    assert out.rain is not None
    assert out.box is not None and out.box.recipient_state == "not_checked"


def test_rain_below_threshold_dropped(tmp_path: Path) -> None:
    visit = mkdel()
    ports = mkports(tmp_path, weather=FakeWeather(RainRisk(30, "4:00 pm")))
    out = run(visit, ports)
    assert out.rain is None
    call = next(c for c in out.trace if c.tool == "rain_outlook")
    assert call.ok is True


def test_describe_clip_and_gating(tmp_path: Path) -> None:
    visit = replace(mkdel(clip_media_key="clip1"), hero_media_key=None)
    ports = mkports(tmp_path, describer=FakeDescriber("A courier left a box."))
    out = run(visit, ports)
    assert out.description == "A courier left a box."
    assert [c.tool for c in out.trace] == [
        "check_door",
        "rain_outlook",
        "describe_clip",
    ]
    visitor = replace(mkvisit("v2", 1000, VisitKind.VISITOR), clip_media_key="clip1")
    out2 = run(visitor, ports)
    assert [c.tool for c in out2.trace] == ["describe_clip"]


def test_box_gone_reads_label(tmp_path: Path) -> None:
    media = FileMediaStore(tmp_path / "media", "http://x")
    key = asyncio.run(media.put(make_jpeg(), ".jpg"))
    visit = replace(
        mkvisit("v1", 1000, VisitKind.BOX_GONE),
        box=BoxFacts(
            box=BOX,
            recipient_id=None,
            recipient_state="not_checked",
            blocks_door=None,
            door_overlap=None,
        ),
        hero_media_key=key,
    )
    ports = mkports(tmp_path, media=media, reader=FakeReader(["SAM OKAFOR"]))
    out = run(visit, ports)
    assert out.box is not None
    assert out.box.recipient_state == "matched"
    assert out.box.recipient_id == "sam"
    assert [c.tool for c in out.trace] == ["read_label"]
