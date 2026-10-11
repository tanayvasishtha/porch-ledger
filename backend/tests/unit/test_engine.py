from collections.abc import Mapping, Sequence

import pytest

from porch.config import EngineSettings, from_settings
from porch.domain import (
    Detection,
    DetectionLabel,
    DoorEvent,
    EngineParams,
    EventKind,
    MixedDevicesError,
    NormBox,
    PorchState,
    Snapshot,
    StitchResult,
    TrackedBox,
    VisitKind,
    stitch,
)

MS = 1000
DEVICE = "dev-1"
HOUSE = "house-1"
NOW_MS = 10_000_000
PARAMS = EngineParams(
    visit_merge_gap_s=120,
    box_match_iou=0.3,
    box_min_frames=2,
    dwell_min_s=45,
    min_detection_confidence=0.6,
)


def ev(eid: str, start_s: float, dur_s: float = 5.0, kind: EventKind = "motion") -> DoorEvent:
    return DoorEvent(
        id=eid,
        device_id=DEVICE,
        kind=kind,
        sub_type=None,
        start_ms=int(start_s * MS),
        end_ms=int((start_s + dur_s) * MS),
        provenance="replay",
    )


def snap(eid: str, at_s: float, *dets: Detection) -> Snapshot:
    return Snapshot(
        event_id=eid,
        at_ms=int(at_s * MS),
        media_key=f"{eid}-s{int(at_s)}",
        detections=dets,
    )


def det(label: DetectionLabel, conf: float = 0.9, box: NormBox | None = None) -> Detection:
    return Detection(label=label, confidence=conf, box=box)


def bx(x: float, y: float, w: float, h: float) -> NormBox:
    return NormBox(x=x, y=y, w=w, h=h)


def stitch_all(
    events: Sequence[DoorEvent],
    snaps: Mapping[str, Sequence[Snapshot]] | None = None,
    prior: PorchState | None = None,
    params: EngineParams = PARAMS,
    now_ms: int = NOW_MS,
) -> StitchResult:
    return stitch(events, snaps or {}, prior or PorchState(), params, HOUSE, now_ms)


def test_engine_params_from_settings() -> None:
    params = from_settings(EngineSettings())
    assert params == PARAMS


def test_delivery_without_person() -> None:
    events = [ev("e1", 0, kind="on_demand"), ev("e2", 90, kind="on_demand")]
    snaps = {
        "e1": [snap("e1", 1, det("vehicle"))],
        "e2": [
            snap("e2", 91, det("box", box=bx(0.4, 0.4, 0.2, 0.2))),
            snap("e2", 92, det("box", box=bx(0.41, 0.4, 0.2, 0.2))),
            snap("e2", 93, det("box", box=bx(0.4, 0.4, 0.25, 0.25))),
        ],
    }
    res = stitch_all(events, snaps)
    assert len(res.visits) == 1
    visit = res.visits[0]
    assert visit.kind == VisitKind.DELIVERY
    assert visit.box is not None
    assert visit.box.recipient_state == "not_checked"
    assert visit.hero_media_key == "e2-s93"
    assert visit.event_ids == ("e1", "e2")
    assert len(res.state.boxes) == 1
    assert res.pending_event_ids == ()


def test_delivery_with_person() -> None:
    events = [ev("e1", 0, kind="on_demand")]
    snaps = {
        "e1": [
            snap("e1", 1, det("person"), det("box", box=bx(0.3, 0.3, 0.2, 0.2))),
            snap("e1", 2, det("box", box=bx(0.31, 0.3, 0.2, 0.2))),
        ],
    }
    res = stitch_all(events, snaps)
    assert res.visits[0].kind == VisitKind.DELIVERY


def test_single_frame_box_flicker_is_not_delivery() -> None:
    events = [ev("e1", 0, kind="on_demand"), ev("e2", 90, kind="on_demand")]
    snaps = {
        "e1": [snap("e1", 1, det("vehicle"))],
        "e2": [snap("e2", 91, det("box", box=bx(0.4, 0.4, 0.2, 0.2)))],
    }
    res = stitch_all(events, snaps)
    visit = res.visits[0]
    assert visit.kind == VisitKind.CARS_PASSED
    assert visit.box is None
    assert res.state.boxes == ()


def test_box_occluded_mid_group_is_not_gone() -> None:
    box = bx(0.3, 0.3, 0.2, 0.2)
    prior = PorchState(boxes=(TrackedBox(box=box, first_seen_ms=0, last_seen_ms=0),))
    events = [ev("e1", 0), ev("e2", 30), ev("e3", 60)]
    snaps = {
        "e1": [snap("e1", 1, det("box", box=box))],
        "e2": [snap("e2", 31, det("person"))],
        "e3": [snap("e3", 61, det("box", box=bx(0.31, 0.3, 0.2, 0.2)))],
    }
    res = stitch_all(events, snaps, prior=prior)
    visit = res.visits[0]
    assert visit.kind != VisitKind.BOX_GONE
    assert len(res.state.boxes) == 1
    assert res.state.boxes[0].last_seen_ms == 61 * MS


def test_box_gone() -> None:
    box = bx(0.3, 0.3, 0.2, 0.2)
    prior = PorchState(boxes=(TrackedBox(box=box, first_seen_ms=0, last_seen_ms=0),))
    events = [ev("e1", 0, kind="on_demand")]
    snaps = {"e1": [snap("e1", 1, det("person")), snap("e1", 2, det("person"))]}
    res = stitch_all(events, snaps, prior=prior)
    visit = res.visits[0]
    assert visit.kind == VisitKind.BOX_GONE
    assert visit.box is not None
    assert visit.box.box == box
    assert visit.hero_media_key == "e1-s2"
    assert res.state.boxes == ()


def test_car_stopped() -> None:
    events = [ev("e1", 0, dur_s=70, kind="on_demand")]
    snaps = {"e1": [snap("e1", 1, det("vehicle")), snap("e1", 61, det("vehicle"))]}
    res = stitch_all(events, snaps)
    assert res.visits[0].kind == VisitKind.CAR_STOPPED


def test_cars_passed() -> None:
    events = [ev("e1", 0, dur_s=15, kind="on_demand")]
    snaps = {"e1": [snap("e1", 1, det("vehicle")), snap("e1", 11, det("vehicle"))]}
    res = stitch_all(events, snaps)
    assert res.visits[0].kind == VisitKind.CARS_PASSED


def test_visitor_via_ding_without_detections() -> None:
    res = stitch_all([ev("e1", 0, kind="ding")])
    assert res.visits[0].kind == VisitKind.VISITOR


def test_merge_gap_boundary() -> None:
    merged = stitch_all([ev("e1", 0), ev("e2", 125)])
    assert len(merged.visits) == 1
    assert merged.visits[0].event_ids == ("e1", "e2")
    split = stitch_all([ev("e1", 0), ev("e2", 126)])
    assert len(split.visits) == 2


def test_trailing_group_pending_then_closed() -> None:
    events = [ev("e1", 0), ev("e2", 200)]
    within_gap = stitch_all(events, now_ms=int(260 * MS))
    assert len(within_gap.visits) == 1
    assert within_gap.pending_event_ids == ("e2",)
    assert within_gap.state.boxes == ()
    beyond_gap = stitch_all(events)
    assert len(beyond_gap.visits) == 2
    assert beyond_gap.pending_event_ids == ()


def test_low_confidence_detections_ignored() -> None:
    events = [ev("e1", 0, kind="on_demand")]
    snaps = {
        "e1": [
            snap("e1", 1, det("box", conf=0.3, box=bx(0.4, 0.4, 0.2, 0.2))),
            snap("e1", 2, det("box", conf=0.3, box=bx(0.4, 0.4, 0.2, 0.2))),
            snap("e1", 3, det("person", conf=0.2)),
        ],
    }
    res = stitch_all(events, snaps)
    assert res.visits[0].kind == VisitKind.ACTIVITY
    assert res.state.boxes == ()


def test_mixed_devices_raises() -> None:
    e1 = ev("e1", 0)
    e2 = DoorEvent(
        id="e2",
        device_id="dev-2",
        kind="motion",
        sub_type=None,
        start_ms=10 * MS,
        end_ms=15 * MS,
        provenance="replay",
    )
    with pytest.raises(MixedDevicesError):
        stitch_all([e1, e2])


def test_no_snapshots_yields_no_hero() -> None:
    res = stitch_all([ev("e1", 0)])
    assert res.visits[0].kind == VisitKind.ACTIVITY
    assert res.visits[0].hero_media_key is None


def test_empty_events_returns_prior_state() -> None:
    prior = PorchState(
        boxes=(TrackedBox(box=bx(0.1, 0.1, 0.2, 0.2), first_seen_ms=0, last_seen_ms=0),)
    )
    res = stitch_all([], prior=prior)
    assert res.visits == ()
    assert res.pending_event_ids == ()
    assert res.state == prior


def test_box_detection_without_geometry_ignored() -> None:
    events = [ev("e1", 0, kind="on_demand")]
    snaps = {"e1": [snap("e1", 1, det("box")), snap("e1", 2, det("box"))]}
    res = stitch_all(events, snaps)
    assert res.visits[0].kind == VisitKind.ACTIVITY
    assert res.state.boxes == ()


def test_pending_group_does_not_consume_state() -> None:
    box = bx(0.3, 0.3, 0.2, 0.2)
    events = [ev("e1", 0, kind="on_demand"), ev("e2", 200)]
    snaps = {
        "e1": [
            snap("e1", 1, det("box", box=box)),
            snap("e1", 2, det("box", box=bx(0.31, 0.3, 0.2, 0.2))),
        ],
    }
    res = stitch_all(events, snaps, now_ms=int(260 * MS))
    assert res.visits[0].kind == VisitKind.DELIVERY
    assert res.pending_event_ids == ("e2",)
    # The confirmed box survives into the state returned before the pending group.
    assert len(res.state.boxes) == 1
