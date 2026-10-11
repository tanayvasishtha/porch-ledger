from random import Random

from hypothesis import given
from hypothesis import strategies as st

from porch.domain import (
    Detection,
    DetectionLabel,
    DoorEvent,
    EngineParams,
    EventKind,
    NormBox,
    PorchState,
    Snapshot,
    StitchResult,
    stitch,
)

PARAMS = EngineParams(
    visit_merge_gap_s=120,
    box_match_iou=0.3,
    box_min_frames=2,
    dwell_min_s=45,
    min_detection_confidence=0.6,
)
HOUSE = "prop-house"
DEVICE = "dev-0"
FAR_FUTURE_MS = 10**12
GRID = (0.0, 0.25, 0.5)
SIZES = (0.25, 0.5)
LABELS: tuple[DetectionLabel, ...] = ("vehicle", "person", "box")
KINDS: tuple[EventKind, ...] = ("motion", "ding", "on_demand", "own")

Scenario = tuple[list[DoorEvent], dict[str, list[Snapshot]]]


@st.composite
def scenario(draw: st.DrawFn, base_ms: int, span_ms: int, prefix: str) -> Scenario:
    """Events on one device with random detections on a coarse box grid."""
    events: list[DoorEvent] = []
    snaps: dict[str, list[Snapshot]] = {}
    for i in range(draw(st.integers(1, 6))):
        start = base_ms + draw(st.integers(0, span_ms))
        dur = draw(st.integers(0, 60_000))
        eid = f"{prefix}{i}"
        events.append(
            DoorEvent(
                id=eid,
                device_id=DEVICE,
                kind=draw(st.sampled_from(KINDS)),
                sub_type=None,
                start_ms=start,
                end_ms=start + dur,
                provenance="replay",
            )
        )
        snap_list = [
            Snapshot(
                event_id=eid,
                at_ms=start + draw(st.integers(0, dur)),
                media_key=f"{eid}-s{j}",
                detections=tuple(draw(detection()) for _ in range(draw(st.integers(0, 3)))),
            )
            for j in range(draw(st.integers(0, 3)))
        ]
        if snap_list:
            snaps[eid] = snap_list
    return events, snaps


@st.composite
def detection(draw: st.DrawFn) -> Detection:
    label = draw(st.sampled_from(LABELS))
    box = None
    if label == "box":
        box = NormBox(
            x=draw(st.sampled_from(GRID)),
            y=draw(st.sampled_from(GRID)),
            w=draw(st.sampled_from(SIZES)),
            h=draw(st.sampled_from(SIZES)),
        )
    return Detection(label=label, confidence=draw(st.floats(0.0, 1.0)), box=box)


def run(data: Scenario, now_ms: int = FAR_FUTURE_MS) -> StitchResult:
    events, snaps = data
    return stitch(events, snaps, PorchState(), PARAMS, HOUSE, now_ms)


@given(scenario(0, 1_000_000, "e"))
def test_idempotent(data: Scenario) -> None:
    assert run(data) == run(data)


@given(scenario(0, 1_000_000, "e"), st.randoms())
def test_order_invariant(data: Scenario, rnd: Random) -> None:
    events, snaps = data
    shuffled = list(events)
    rnd.shuffle(shuffled)
    assert run(data) == stitch(shuffled, snaps, PorchState(), PARAMS, HOUSE, FAR_FUTURE_MS)


@given(scenario(0, 120_000, "a"), scenario(1_000_000, 120_000, "b"))
def test_incremental_equivalence(a_data: Scenario, b_data: Scenario) -> None:
    a_events, a_snaps = a_data
    b_events, b_snaps = b_data
    all_snaps = {**a_snaps, **b_snaps}
    split_now_ms = 500_000
    final_now_ms = 2_000_000

    full = run((a_events + b_events, all_snaps), final_now_ms)
    pre = run(a_data, split_now_ms)
    assert pre.pending_event_ids == ()
    post = stitch(b_events, b_snaps, pre.state, PARAMS, HOUSE, final_now_ms)

    assert pre.visits + post.visits == full.visits
    assert post.state == full.state
    assert post.pending_event_ids == full.pending_event_ids


@given(scenario(0, 1_000_000, "e"))
def test_partition(data: Scenario) -> None:
    events, _ = data
    res = run(data)
    seen = [eid for v in res.visits for eid in v.event_ids]
    seen.extend(res.pending_event_ids)
    assert sorted(seen) == sorted(e.id for e in events)
    assert len(seen) == len(set(seen))


@given(scenario(0, 1_000_000, "e"))
def test_visits_ordered_and_non_overlapping(data: Scenario) -> None:
    res = run(data)
    starts = [v.start_ms for v in res.visits]
    assert starts == sorted(starts)
    for first, second in zip(res.visits, res.visits[1:], strict=False):
        assert second.start_ms > first.end_ms
