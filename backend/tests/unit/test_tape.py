import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from porch.adapters.tape import ReplaySource, load_tape
from tests.helpers import FakeClock


def write_tape(path: Path, events_ms: tuple[int, ...] = (1000, 5000, 9000)) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    tape = {
        "format": 1,
        "device_id": "d1",
        "provenance": "replay",
        "events": [
            {
                "id": f"e{i}",
                "kind": "motion",
                "sub_type": None,
                "start_ms": start,
                "end_ms": start + 500,
            }
            for i, start in enumerate(events_ms)
        ],
        "snapshots": [
            {
                "event_id": "e0",
                "at_ms": 1200,
                "file": "s0.jpg",
                "detections": [
                    {
                        "label": "box",
                        "confidence": 0.9,
                        "box": {"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1},
                    }
                ],
            },
            {
                "event_id": "e0",
                "at_ms": 1400,
                "file": "s1.jpg",
                "detections": None,
            },
        ],
        "clips": [{"event_id": "e1", "file": "clip.mp4"}],
    }
    (path / "tape.json").write_text(json.dumps(tape), encoding="utf-8")
    (path / "s0.jpg").write_bytes(b"jpeg")
    return path


def test_load_tape(tmp_path: Path) -> None:
    tape = load_tape(write_tape(tmp_path / "tape"))
    assert tape.device_id == "d1"
    assert tape.provenance == "replay"
    assert [e.id for e in tape.events] == ["e0", "e1", "e2"]
    snaps = tape.snapshots_for("e0")
    assert len(snaps) == 2
    assert snaps[0].detections is not None and len(snaps[0].detections) == 1
    assert snaps[0].detections[0].box is not None
    assert snaps[1].detections is None
    assert tape.clip_for("e1") is not None
    assert tape.clip_for("e0") is None
    assert tape.snapshots_for("e1") == ()


def test_load_tape_rejects_bad_input(tmp_path: Path) -> None:
    path = tmp_path / "bad"
    path.mkdir()
    (path / "tape.json").write_text('{"format": 2}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_tape(path)


def test_replay_poll_scaled(tmp_path: Path) -> None:
    tape = load_tape(write_tape(tmp_path / "tape", events_ms=(1000, 5000, 9000)))
    clock = FakeClock(0)

    class ScalableClock(FakeClock):
        def __init__(self, ms: int) -> None:
            super().__init__(ms)
            self.current = ms

        def now_ms(self) -> int:
            return self.current

    clock = ScalableClock(0)
    source = ReplaySource(tape, speed=2.0, clock=clock)
    assert [e.id for e in asyncio.run(source.poll())] == ["e0"]
    clock.current = 1999
    assert asyncio.run(source.poll()) == []
    clock.current = 2000
    assert [e.id for e in asyncio.run(source.poll())] == ["e1"]
    clock.current = 3999
    assert asyncio.run(source.poll()) == []
    clock.current = 4000
    assert [e.id for e in asyncio.run(source.poll())] == ["e2"]
    assert asyncio.run(source.poll()) == []


def test_all_now_returns_everything_once(tmp_path: Path) -> None:
    tape = load_tape(write_tape(tmp_path / "tape"))
    source = ReplaySource(tape, speed=1.0, clock=FakeClock(0))
    assert [e.id for e in asyncio.run(source.all_now())] == ["e0", "e1", "e2"]
    assert asyncio.run(source.all_now()) == []
