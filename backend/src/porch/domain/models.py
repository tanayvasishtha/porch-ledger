"""Domain model: frozen dataclasses shared by the engine, ports and API."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

DetectionLabel = Literal["vehicle", "person", "box"]
EventKind = Literal["motion", "ding", "on_demand", "own"]
Provenance = Literal["ring", "own", "replay"]
RecipientState = Literal["matched", "unreadable", "not_ours", "not_checked"]

MAX_PROBABILITY_PCT = 100


class DomainError(ValueError):
    """A domain invariant was violated."""


class InvalidNormBoxError(DomainError):
    """NormBox coordinates or size fall outside the unit square."""

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        super().__init__(f"x={x} y={y} w={w} h={h}")


class InvalidTimeRangeError(DomainError):
    """An event or visit ends before it starts."""

    def __init__(self, start_ms: int, end_ms: int) -> None:
        super().__init__(f"end_ms={end_ms} before start_ms={start_ms}")


class InvalidConfidenceError(DomainError):
    """Detection confidence outside [0, 1]."""

    def __init__(self, confidence: float) -> None:
        super().__init__(f"confidence={confidence} outside [0, 1]")


class InvalidProbabilityError(DomainError):
    """Rain probability percentage outside [0, 100]."""

    def __init__(self, probability_pct: int) -> None:
        super().__init__(f"probability_pct={probability_pct} outside [0, {MAX_PROBABILITY_PCT}]")


@dataclass(frozen=True, slots=True)
class NormBox:
    """Normalised bounding box, top-left x/y plus w/h, all in [0, 1]."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise InvalidNormBoxError(self.x, self.y, self.w, self.h)
        if not (0.0 < self.w <= 1.0 and 0.0 < self.h <= 1.0):
            raise InvalidNormBoxError(self.x, self.y, self.w, self.h)
        if self.x + self.w > 1.0 or self.y + self.h > 1.0:
            raise InvalidNormBoxError(self.x, self.y, self.w, self.h)

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(frozen=True, slots=True)
class Detection:
    label: DetectionLabel
    confidence: float
    box: NormBox | None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidConfidenceError(self.confidence)


@dataclass(frozen=True, slots=True)
class DoorEvent:
    id: str
    device_id: str
    kind: EventKind
    sub_type: str | None
    start_ms: int
    end_ms: int
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise InvalidTimeRangeError(self.start_ms, self.end_ms)


@dataclass(frozen=True, slots=True)
class Snapshot:
    event_id: str
    at_ms: int
    media_key: str
    detections: tuple[Detection, ...]


class VisitKind(StrEnum):
    DELIVERY = "delivery"
    BOX_GONE = "box_gone"
    CAR_STOPPED = "car_stopped"
    VISITOR = "visitor"
    CARS_PASSED = "cars_passed"
    ACTIVITY = "activity"


@dataclass(frozen=True, slots=True)
class BoxFacts:
    box: NormBox
    recipient_id: str | None
    recipient_state: RecipientState
    blocks_door: bool | None
    door_overlap: float | None


@dataclass(frozen=True, slots=True)
class RainRisk:
    probability_pct: int
    by_local_time: str

    def __post_init__(self) -> None:
        if not 0 <= self.probability_pct <= MAX_PROBABILITY_PCT:
            raise InvalidProbabilityError(self.probability_pct)


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool: str
    ok: bool
    latency_ms: int
    note: str


@dataclass(frozen=True, slots=True)
class Visit:
    id: str
    house_id: str
    device_id: str
    kind: VisitKind
    start_ms: int
    end_ms: int
    event_ids: tuple[str, ...]
    hero_media_key: str | None
    clip_media_key: str | None
    box: BoxFacts | None
    description: str | None
    rain: RainRisk | None
    provenance: Provenance
    trace: tuple[ToolCall, ...]
    claimed_by: str | None
    version: int


def visit_id(device_id: str, first_event_id: str) -> str:
    """Deterministic visit id, first 16 hex chars of sha256."""
    digest = hashlib.sha256(f"{device_id}:{first_event_id}".encode()).hexdigest()
    return digest[:16]
