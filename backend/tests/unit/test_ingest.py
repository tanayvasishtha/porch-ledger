import asyncio
import json
from pathlib import Path

from porch.adapters.local import FileMediaStore
from porch.adapters.tape import TapeMediaFetcher, load_tape
from porch.config import Settings
from porch.domain import Detection, NormBox, VisitKind
from porch.pipeline.enrich import EnrichPorts
from porch.pipeline.ingest import IngestConfig, IngestPorts, IngestService
from tests.helpers import (
    FakeClock,
    FakeDescriber,
    FakeLabeler,
    FakeReader,
    FakeRepo,
    FakeSource,
    FakeWeather,
    demo_house,
    make_jpeg,
)

VEHICLE = {"label": "vehicle", "confidence": 0.9, "box": {"x": 0.7, "y": 0.6, "w": 0.2, "h": 0.15}}
BOX = {"label": "box", "confidence": 0.95, "box": {"x": 0.7, "y": 0.6, "w": 0.1, "h": 0.15}}


def write_ingest_tape(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    tape = {
        "format": 1,
        "device_id": "d1",
        "provenance": "replay",
        "events": [
            {"id": "car", "kind": "motion", "sub_type": None, "start_ms": 0, "end_ms": 15000},
            {
                "id": "del",
                "kind": "on_demand",
                "sub_type": None,
                "start_ms": 140000,
                "end_ms": 200000,
            },
        ],
        "snapshots": [
            {"event_id": "car", "at_ms": 0, "file": "car0.jpg", "detections": [VEHICLE]},
            {"event_id": "car", "at_ms": 10000, "file": "car1.jpg", "detections": [VEHICLE]},
            {"event_id": "del", "at_ms": 140000, "file": "d0.jpg", "detections": [BOX]},
            {"event_id": "del", "at_ms": 150000, "file": "d1.jpg", "detections": [BOX]},
            {"event_id": "del", "at_ms": 160000, "file": "d2.jpg", "detections": [BOX]},
        ],
        "clips": [],
    }
    (path / "tape.json").write_text(json.dumps(tape), encoding="utf-8")
    for name in ("car0.jpg", "car1.jpg", "d0.jpg", "d1.jpg", "d2.jpg"):
        (path / name).write_bytes(make_jpeg())
    return path


def mk_service(
    tmp_path: Path, tape_path: Path, clock: FakeClock
) -> tuple[IngestService, FakeRepo, FileMediaStore]:
    tape = load_tape(tape_path)
    repo = FakeRepo()
    media = FileMediaStore(tmp_path / "media", "http://x")
    ports = EnrichPorts(
        media=media,
        reader=FakeReader(["PRIYA SHAH"]),
        describer=FakeDescriber(),
        weather=FakeWeather(),
    )
    service = IngestService(
        ports=IngestPorts(
            source=FakeSource(list(tape.events)),
            fetcher=TapeMediaFetcher(tape),
            media=media,
            labeler=FakeLabeler(),
            enrich=ports,
            repo=repo,
        ),
        config=IngestConfig(
            house=demo_house(),
            settings=Settings(),
            clock=clock,
        ),
    )
    return service, repo, media


def test_ingest_two_visits_then_noop(tmp_path: Path) -> None:
    tape_path = write_ingest_tape(tmp_path / "tape")
    service, repo, _media = mk_service(tmp_path, tape_path, FakeClock(500_000))
    report = asyncio.run(service.run_once())
    assert report.events == 2
    assert report.snapshots == 5
    assert report.visits_closed == 2
    assert report.pending == 0
    visits = asyncio.run(repo.visits_between("demo", 0, 10**15))
    kinds = {v.id: v.kind for v in visits}
    assert sorted(kinds.values(), key=str) == [VisitKind.CARS_PASSED, VisitKind.DELIVERY]
    delivery = next(v for v in visits if v.kind == VisitKind.DELIVERY)
    assert delivery.box is not None
    assert delivery.box.recipient_id == "priya"
    assert delivery.hero_media_key is not None
    assert (tmp_path / "media" / delivery.hero_media_key).exists()
    second = asyncio.run(service.run_once())
    assert second == type(second)(events=0, snapshots=0, visits_closed=0, pending=0)
    assert asyncio.run(repo.visits_between("demo", 0, 10**15)) == visits


def test_pending_carried_across_runs(tmp_path: Path) -> None:
    tape_path = write_ingest_tape(tmp_path / "tape")
    clock = FakeClock(150_000)
    service, repo, _media = mk_service(tmp_path, tape_path, clock)
    first = asyncio.run(service.run_once())
    assert first.visits_closed == 1
    assert first.pending == 1
    clock.current = 400_000
    second = asyncio.run(service.run_once())
    assert second.events == 0
    assert second.visits_closed == 1
    assert second.pending == 0
    kinds = [v.kind for v in asyncio.run(repo.visits_between("demo", 0, 10**15))]
    assert sorted(kinds, key=str) == [VisitKind.CARS_PASSED, VisitKind.DELIVERY]


def test_unannotated_snapshots_call_labeler(tmp_path: Path) -> None:
    tape_path = write_ingest_tape(tmp_path / "tape")
    tape_json = json.loads((tape_path / "tape.json").read_text(encoding="utf-8"))
    for snap in tape_json["snapshots"]:
        snap["detections"] = None
    (tape_path / "tape.json").write_text(json.dumps(tape_json), encoding="utf-8")
    tape = load_tape(tape_path)
    repo = FakeRepo()
    media = FileMediaStore(tmp_path / "media", "http://x")
    labeler = FakeLabeler(
        [Detection(label="box", confidence=0.9, box=NormBox(x=0.7, y=0.6, w=0.1, h=0.15))]
    )
    service = IngestService(
        ports=IngestPorts(
            source=FakeSource(list(tape.events)),
            fetcher=TapeMediaFetcher(tape),
            media=media,
            labeler=labeler,
            enrich=EnrichPorts(
                media=media,
                reader=FakeReader(),
                describer=FakeDescriber(),
                weather=FakeWeather(),
            ),
            repo=repo,
        ),
        config=IngestConfig(
            house=demo_house(),
            settings=Settings(),
            clock=FakeClock(500_000),
        ),
    )
    report = asyncio.run(service.run_once())
    assert report.visits_closed == 2
    assert labeler.calls == 5
