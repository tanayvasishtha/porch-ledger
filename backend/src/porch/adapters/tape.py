"""Tape format: a directory with tape.json plus media files.

`detections: null` on a snapshot means "not annotated, run the Labeler";
a list (even empty) means the tape carries pre-annotated detections.
`label_texts` is optional demo metadata: the OCR text drawn into a frame,
keyed by event id, used by the offline demo's fake LabelReader.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from porch.domain import (
    Detection,
    DetectionLabel,
    DoorEvent,
    EventKind,
    NormBox,
    Provenance,
)
from porch.ports import Clock

TAPE_FILE = "tape.json"
TAPE_FORMAT = 1


@dataclass(frozen=True, slots=True)
class TapeSnapshot:
    event_id: str
    at_ms: int
    file: str
    detections: tuple[Detection, ...] | None


@dataclass(frozen=True, slots=True)
class TapeClip:
    event_id: str
    file: str


@dataclass(frozen=True, slots=True)
class Tape:
    path: Path
    device_id: str
    provenance: Provenance
    events: tuple[DoorEvent, ...]
    snapshots: tuple[TapeSnapshot, ...]
    clips: tuple[TapeClip, ...]
    label_texts: Mapping[str, str]

    def snapshots_for(self, event_id: str) -> tuple[TapeSnapshot, ...]:
        return tuple(s for s in self.snapshots if s.event_id == event_id)

    def clip_for(self, event_id: str) -> TapeClip | None:
        return next((c for c in self.clips if c.event_id == event_id), None)


class _DetectionFile(BaseModel):
    label: DetectionLabel
    confidence: float
    box: NormBox | None = None


class _SnapshotFile(BaseModel):
    event_id: str
    at_ms: int
    file: str
    detections: list[_DetectionFile] | None = None


class _ClipFile(BaseModel):
    event_id: str
    file: str


class _EventFile(BaseModel):
    id: str
    kind: EventKind
    sub_type: str | None = None
    start_ms: int
    end_ms: int


class _TapeFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal[1]
    device_id: str
    provenance: Provenance
    events: tuple[_EventFile, ...]
    snapshots: tuple[_SnapshotFile, ...] = ()
    clips: tuple[_ClipFile, ...] = ()
    label_texts: dict[str, str] = {}


def load_tape(path: Path) -> Tape:
    """Parse tape.json; pydantic names the offending field on bad input."""
    parsed = _TapeFile.model_validate_json((path / TAPE_FILE).read_text(encoding="utf-8"))
    events = tuple(
        DoorEvent(
            id=e.id,
            device_id=parsed.device_id,
            kind=e.kind,
            sub_type=e.sub_type,
            start_ms=e.start_ms,
            end_ms=e.end_ms,
            provenance=parsed.provenance,
        )
        for e in parsed.events
    )
    snapshots = tuple(
        TapeSnapshot(
            event_id=s.event_id,
            at_ms=s.at_ms,
            file=s.file,
            detections=None
            if s.detections is None
            else tuple(
                Detection(label=d.label, confidence=d.confidence, box=d.box) for d in s.detections
            ),
        )
        for s in parsed.snapshots
    )
    clips = tuple(TapeClip(event_id=c.event_id, file=c.file) for c in parsed.clips)
    return Tape(
        path=path,
        device_id=parsed.device_id,
        provenance=parsed.provenance,
        events=events,
        snapshots=snapshots,
        clips=clips,
        label_texts=parsed.label_texts,
    )


class ReplaySource:
    """EventSource that replays a tape's events scaled against a clock.

    The tape's first event lands when the source is created; later events
    are shifted by (start_ms - first) / speed. Each poll returns events
    whose shifted start is <= now and not already returned.
    """

    def __init__(self, tape: Tape, speed: float, clock: Clock) -> None:
        self._tape = tape
        self._clock = clock
        created_ms = clock.now_ms()
        first = min((e.start_ms for e in tape.events), default=0)
        self._schedule = sorted(
            ((int((e.start_ms - first) / speed) + created_ms, e) for e in tape.events),
            key=lambda item: (item[0], item[1].id),
        )
        self._cursor = 0

    async def poll(self) -> list[DoorEvent]:
        now_ms = self._clock.now_ms()
        due = [e for at_ms, e in self._schedule[self._cursor :] if at_ms <= now_ms]
        self._cursor += len(due)
        return due

    async def all_now(self) -> list[DoorEvent]:
        """Every remaining event at once, for batch demo and eval runs."""
        out = [e for _, e in self._schedule[self._cursor :]]
        self._cursor = len(self._schedule)
        return out
