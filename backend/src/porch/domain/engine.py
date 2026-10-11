"""Visit engine: stitches door events and snapshot detections into visits.

Pure function of its inputs: no I/O, no clock (now_ms is passed in), no
randomness. All thresholds arrive via EngineParams. Detections below
min_detection_confidence are ignored everywhere. One device per call;
mixed input raises MixedDevicesError.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from porch.domain.geometry import iou
from porch.domain.models import (
    BoxFacts,
    DetectionLabel,
    DoorEvent,
    MixedDevicesError,
    NormBox,
    Snapshot,
    Visit,
    VisitKind,
    visit_id,
)
from porch.domain.porch_state import (
    EngineParams,
    PorchState,
    StitchResult,
    TrackedBox,
)

MS_PER_S = 1000
MIN_SPAN_SNAPSHOTS = 2


@dataclass(frozen=True, slots=True)
class _Ctx:
    """Per-call constants shared by the group helpers."""

    snapshots: Mapping[str, Sequence[Snapshot]]
    params: EngineParams
    house_id: str
    device_id: str


@dataclass(frozen=True, slots=True)
class _Signals:
    """Everything the classifier needs from one closed group."""

    confirmed_new: tuple[_Cluster, ...]
    gone: tuple[TrackedBox, ...]
    vehicle_span_s: float
    has_person: bool
    has_ding: bool
    has_vehicle: bool


@dataclass(frozen=True, slots=True)
class _BoxRef:
    """A box detection tied to the snapshot it came from."""

    box: NormBox
    at_ms: int
    media_key: str
    event_id: str


@dataclass(slots=True)
class _Cluster:
    """Box detections greedily merged by IoU, kept in time order."""

    refs: list[_BoxRef]

    @property
    def latest_box(self) -> NormBox:
        return self.refs[-1].box

    @property
    def first_seen_ms(self) -> int:
        return self.refs[0].at_ms

    @property
    def last_seen_ms(self) -> int:
        return self.refs[-1].at_ms


def stitch(  # noqa: PLR0913, PLR0917
    # Public API signature is part of the port contract.
    events: Sequence[DoorEvent],
    snapshots: Mapping[str, Sequence[Snapshot]],
    prior: PorchState,
    params: EngineParams,
    house_id: str,
    now_ms: int,
) -> StitchResult:
    """Group events into visits, classify each, and thread box state through."""
    device_ids = {e.device_id for e in events}
    if len(device_ids) > 1:
        raise MixedDevicesError(device_ids)
    ordered = sorted(events, key=lambda e: (e.start_ms, e.id))
    if not ordered:
        return StitchResult(visits=(), pending_event_ids=(), state=prior)
    gap_ms = params.visit_merge_gap_s * MS_PER_S
    groups = _group_events(ordered, gap_ms)
    last_end_ms = max(e.end_ms for e in groups[-1])
    trailing_open = now_ms - last_end_ms <= gap_ms
    closed_groups = groups[:-1] if trailing_open else groups
    ctx = _Ctx(
        snapshots=snapshots,
        params=params,
        house_id=house_id,
        device_id=ordered[0].device_id,
    )
    state = prior
    visits: list[Visit] = []
    for group in closed_groups:
        visit, state = _process_group(group, state, ctx)
        visits.append(visit)
    pending = tuple(e.id for e in groups[-1]) if trailing_open else ()
    return StitchResult(visits=tuple(visits), pending_event_ids=pending, state=state)


def _group_events(ordered: list[DoorEvent], gap_ms: int) -> list[list[DoorEvent]]:
    groups: list[list[DoorEvent]] = [[ordered[0]]]
    group_end_ms = ordered[0].end_ms
    for event in ordered[1:]:
        if event.start_ms - group_end_ms <= gap_ms:
            groups[-1].append(event)
            group_end_ms = max(group_end_ms, event.end_ms)
        else:
            groups.append([event])
            group_end_ms = event.end_ms
    return groups


def _snapshots_for(event: DoorEvent, snapshots: Mapping[str, Sequence[Snapshot]]) -> list[Snapshot]:
    return sorted(snapshots.get(event.id, ()), key=lambda s: s.at_ms)


def _box_refs(
    group: list[DoorEvent],
    snapshots: Mapping[str, Sequence[Snapshot]],
    min_confidence: float,
) -> list[_BoxRef]:
    """Every geometry-carrying box detection in the group, in time order."""
    refs: list[_BoxRef] = []
    for event in group:
        for snap in _snapshots_for(event, snapshots):
            for det in snap.detections:
                if det.label != "box" or det.confidence < min_confidence:
                    continue
                if det.box is None:
                    continue
                refs.append(
                    _BoxRef(
                        box=det.box,
                        at_ms=snap.at_ms,
                        media_key=snap.media_key,
                        event_id=event.id,
                    )
                )
    return sorted(refs, key=lambda r: r.at_ms)


def _cluster_boxes(refs: list[_BoxRef], match_iou: float) -> list[_Cluster]:
    """Greedy match: join the cluster with the highest IoU to its latest box."""
    clusters: list[_Cluster] = []
    for ref in refs:
        best: _Cluster | None = None
        best_iou = match_iou
        for cluster in clusters:
            score = iou(ref.box, cluster.latest_box)
            if score >= best_iou:
                best_iou = score
                best = cluster
        if best is None:
            clusters.append(_Cluster([ref]))
        else:
            best.refs.append(ref)
    return clusters


def _last_event_with_snapshots(
    group: list[DoorEvent],
    snapshots: Mapping[str, Sequence[Snapshot]],
) -> DoorEvent | None:
    for event in reversed(group):
        if snapshots.get(event.id):
            return event
    return None


def _confirmed_new(
    clusters: list[_Cluster],
    before: tuple[TrackedBox, ...],
    last_ev: DoorEvent | None,
    params: EngineParams,
) -> list[_Cluster]:
    """Clusters that are stable, visible at the end, and not an existing box."""
    if last_ev is None:
        return []
    return [
        c
        for c in clusters
        if len(c.refs) >= params.box_min_frames
        and any(r.event_id == last_ev.id for r in c.refs)
        and all(iou(c.latest_box, b.box) < params.box_match_iou for b in before)
    ]


def _gone_boxes(
    before: tuple[TrackedBox, ...],
    last_refs: list[_BoxRef],
    match_iou: float,
) -> list[TrackedBox]:
    """Tracked boxes no longer visible in the final view; occlusion does not count."""
    return [b for b in before if not any(iou(b.box, r.box) >= match_iou for r in last_refs)]


def _label_hit_ms(
    group: list[DoorEvent],
    snapshots: Mapping[str, Sequence[Snapshot]],
    label: DetectionLabel,
    min_confidence: float,
) -> list[int]:
    """at_ms of each snapshot containing the label at usable confidence."""
    hits: list[int] = []
    for event in group:
        for snap in _snapshots_for(event, snapshots):
            if any(d.label == label and d.confidence >= min_confidence for d in snap.detections):
                hits.append(snap.at_ms)
    return hits


def _classify(signals: _Signals, dwell_min_s: int) -> VisitKind:
    if signals.confirmed_new:
        return VisitKind.DELIVERY
    if signals.gone:
        return VisitKind.BOX_GONE
    if signals.vehicle_span_s >= dwell_min_s:
        return VisitKind.CAR_STOPPED
    if signals.has_person or signals.has_ding:
        return VisitKind.VISITOR
    if signals.has_vehicle:
        return VisitKind.CARS_PASSED
    return VisitKind.ACTIVITY


def _update_state(
    before: tuple[TrackedBox, ...],
    gone: list[TrackedBox],
    confirmed: list[_Cluster],
    refs: list[_BoxRef],
    match_iou: float,
) -> PorchState:
    survivors = [b for b in before if b not in gone]
    updated = [replace(b, last_seen_ms=_matched_last_seen(b, refs, match_iou)) for b in survivors]
    added = [
        TrackedBox(box=c.latest_box, first_seen_ms=c.first_seen_ms, last_seen_ms=c.last_seen_ms)
        for c in confirmed
    ]
    return PorchState(boxes=tuple(updated + added))


def _matched_last_seen(box: TrackedBox, refs: list[_BoxRef], match_iou: float) -> int:
    hits = [r.at_ms for r in refs if iou(box.box, r.box) >= match_iou]
    return max(hits) if hits else box.last_seen_ms


def _box_facts(
    kind: VisitKind,
    confirmed: list[_Cluster],
    gone: list[TrackedBox],
) -> tuple[BoxFacts | None, _Cluster | None]:
    """Facts for the visit's box field; the second value is the delivery cluster."""
    if kind == VisitKind.DELIVERY and confirmed:
        chosen = max(confirmed, key=lambda c: c.latest_box.area)
        return _facts(chosen.latest_box), chosen
    if kind == VisitKind.BOX_GONE and gone:
        gone_box = max(gone, key=lambda b: b.box.area)
        return _facts(gone_box.box), None
    return None, None


def _facts(box: NormBox) -> BoxFacts:
    return BoxFacts(
        box=box,
        recipient_id=None,
        recipient_state="not_checked",
        blocks_door=None,
        door_overlap=None,
    )


def _hero_media_key(
    kind: VisitKind,
    chosen: _Cluster | None,
    last_ev: DoorEvent | None,
    group: list[DoorEvent],
    ctx: _Ctx,
) -> str | None:
    if kind == VisitKind.DELIVERY and chosen is not None:
        return max(chosen.refs, key=lambda r: r.box.area).media_key
    if kind == VisitKind.BOX_GONE and last_ev is not None:
        return max(_snapshots_for(last_ev, ctx.snapshots), key=lambda s: s.at_ms).media_key
    best_key: str | None = None
    best_confidence = ctx.params.min_detection_confidence
    for event in group:
        for snap in _snapshots_for(event, ctx.snapshots):
            for det in snap.detections:
                if det.confidence >= best_confidence:
                    best_confidence = det.confidence
                    best_key = snap.media_key
    return best_key


def _process_group(
    group: list[DoorEvent],
    state: PorchState,
    ctx: _Ctx,
) -> tuple[Visit, PorchState]:
    min_confidence = ctx.params.min_detection_confidence
    match_iou = ctx.params.box_match_iou
    refs = _box_refs(group, ctx.snapshots, min_confidence)
    clusters = _cluster_boxes(refs, match_iou)
    last_ev = _last_event_with_snapshots(group, ctx.snapshots)
    confirmed = _confirmed_new(clusters, state.boxes, last_ev, ctx.params)
    last_refs = [r for r in refs if last_ev is not None and r.event_id == last_ev.id]
    gone = _gone_boxes(state.boxes, last_refs, match_iou) if last_ev is not None else []
    after = _update_state(state.boxes, gone, confirmed, refs, match_iou)
    vehicle_ms = _label_hit_ms(group, ctx.snapshots, "vehicle", min_confidence)
    vehicle_span_s = (
        (max(vehicle_ms) - min(vehicle_ms)) / MS_PER_S
        if len(vehicle_ms) >= MIN_SPAN_SNAPSHOTS
        else 0.0
    )
    kind = _classify(
        _Signals(
            confirmed_new=tuple(confirmed),
            gone=tuple(gone),
            vehicle_span_s=vehicle_span_s,
            has_person=bool(_label_hit_ms(group, ctx.snapshots, "person", min_confidence)),
            has_ding=any(e.kind == "ding" for e in group),
            has_vehicle=bool(vehicle_ms),
        ),
        ctx.params.dwell_min_s,
    )
    box_facts, chosen = _box_facts(kind, confirmed, gone)
    visit = Visit(
        id=visit_id(ctx.device_id, group[0].id),
        house_id=ctx.house_id,
        device_id=ctx.device_id,
        kind=kind,
        start_ms=min(e.start_ms for e in group),
        end_ms=max(e.end_ms for e in group),
        event_ids=tuple(e.id for e in group),
        hero_media_key=_hero_media_key(kind, chosen, last_ev, group, ctx),
        clip_media_key=None,
        box=box_facts,
        description=None,
        rain=None,
        provenance=group[0].provenance,
        trace=(),
        claimed_by=None,
        version=1,
    )
    return visit, after
