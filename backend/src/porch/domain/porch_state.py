"""Engine inputs and outputs: params, porch state, stitch result."""

from dataclasses import dataclass

from porch.domain.models import NormBox, Visit


@dataclass(frozen=True, slots=True)
class EngineParams:
    """Plain copy of EngineSettings so the domain stays pydantic-free."""

    visit_merge_gap_s: int
    box_match_iou: float
    box_min_frames: int
    dwell_min_s: int
    min_detection_confidence: float


@dataclass(frozen=True, slots=True)
class TrackedBox:
    box: NormBox
    first_seen_ms: int
    last_seen_ms: int


@dataclass(frozen=True, slots=True)
class PorchState:
    """Confirmed boxes on the porch."""

    boxes: tuple[TrackedBox, ...] = ()


@dataclass(frozen=True, slots=True)
class StitchResult:
    visits: tuple[Visit, ...]
    pending_event_ids: tuple[str, ...]
    state: PorchState
