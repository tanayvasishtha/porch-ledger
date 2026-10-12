"""Stitching evaluation on seeded synthetic days with known ground truth.

The generator writes door events and snapshot detections for scripted
scenarios (a delivery whose driver is never on camera, a delivery with a
person, cars passing, a car stopping, a visitor, a box picked up, low
confidence noise), adds detection errors (dropped frames, box jitter,
single-frame false boxes), runs the visit engine, and scores each scenario
by the kind of the visit that holds its events.

The baseline is a per-event notifier: one alert for every event with any
detection at or above the confidence threshold. It is what a camera that
alerts on each event would send, and it is the noise Porch Ledger folds.

These are synthetic scenarios written by us. They measure the engine's
logic under controlled noise; they are not a field accuracy claim.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from porch.config import EngineSettings, from_settings
from porch.domain import (
    Detection,
    DetectionLabel,
    DoorEvent,
    EngineParams,
    NormBox,
    PorchState,
    Snapshot,
    VisitKind,
    stitch,
)

ScenarioKind = Literal[
    "delivery_no_driver",
    "delivery_with_person",
    "car_passes",
    "car_stops",
    "visitor",
    "box_picked_up",
    "noise",
]

EXPECTED: dict[ScenarioKind, VisitKind] = {
    "delivery_no_driver": VisitKind.DELIVERY,
    "delivery_with_person": VisitKind.DELIVERY,
    "car_passes": VisitKind.CARS_PASSED,
    "car_stops": VisitKind.CAR_STOPPED,
    "visitor": VisitKind.VISITOR,
    "box_picked_up": VisitKind.BOX_GONE,
    "noise": VisitKind.ACTIVITY,
}
FOLDED = {VisitKind.CARS_PASSED, VisitKind.ACTIVITY}

DEVICE = "eval-doorbell"
HOUSE = "eval"
MS = 1000
SCENARIO_SPACING_S = 900
DAY_START_MS = 1_780_300_800_000
SNAPS_PER_EVENT = 3
HIGH_CONF = (0.75, 0.98)
LOW_CONF = (0.2, 0.5)
BOX_SPOTS = (
    NormBox(0.40, 0.62, 0.12, 0.14),
    NormBox(0.15, 0.58, 0.14, 0.16),
    NormBox(0.62, 0.64, 0.11, 0.13),
)
VEHICLE_BOX = NormBox(0.05, 0.10, 0.45, 0.30)
PERSON_BOX = NormBox(0.45, 0.20, 0.15, 0.55)
PICKUP_CHANCE = 0.35


@dataclass(frozen=True, slots=True)
class Noise:
    """Detection error rates applied to every generated snapshot."""

    drop_box_frame: float
    false_box_frame: float
    jitter: float


@dataclass(frozen=True, slots=True)
class EventSpec:
    start_ms: int
    duration_s: int
    labels_per_snap: list[list[DetectionLabel]]
    kind: Literal["motion", "ding", "on_demand"] = "motion"
    new_box: NormBox | None = None
    low_conf: bool = False


@dataclass(frozen=True, slots=True)
class Scenario:
    kind: ScenarioKind
    event_ids: tuple[str, ...]


@dataclass(slots=True)
class _Day:
    rng: random.Random
    noise: Noise
    events: list[DoorEvent] = field(default_factory=list)
    snapshots: dict[str, list[Snapshot]] = field(default_factory=dict)
    scenarios: list[Scenario] = field(default_factory=list)
    porch_box: NormBox | None = None
    counter: int = 0

    def next_id(self) -> str:
        self.counter += 1
        return f"e{self.counter:04d}"

    def conf(self, low: bool = False) -> float:
        lo, hi = LOW_CONF if low else HIGH_CONF
        return round(self.rng.uniform(lo, hi), 3)

    def jittered(self, box: NormBox) -> NormBox:
        j = self.noise.jitter
        dx = self.rng.uniform(-j, j)
        dy = self.rng.uniform(-j, j)
        x = min(max(box.x + dx, 0.0), 1.0 - box.w)
        y = min(max(box.y + dy, 0.0), 1.0 - box.h)
        return NormBox(round(x, 4), round(y, 4), box.w, box.h)

    def add_event(self, spec: EventSpec) -> str:
        event_id = self.next_id()
        start_ms, end_ms = spec.start_ms, spec.start_ms + spec.duration_s * MS
        self.events.append(DoorEvent(event_id, DEVICE, spec.kind, None, start_ms, end_ms, "replay"))
        snaps: list[Snapshot] = []
        last = max(len(spec.labels_per_snap) - 1, 1)
        for i, labels in enumerate(spec.labels_per_snap):
            at_ms = start_ms + (end_ms - start_ms) * i // last
            dets = [self._detection(label, spec.new_box, spec.low_conf) for label in labels]
            dets.extend(self._porch_box_detections())
            if self.rng.random() < self.noise.false_box_frame:
                spot = self.rng.choice(BOX_SPOTS)
                dets.append(Detection("box", self.conf(), self.jittered(spot)))
            kept = tuple(d for d in dets if d is not None)
            snaps.append(Snapshot(event_id, at_ms, f"{event_id}-{i}.jpg", kept))
        self.snapshots[event_id] = snaps
        return event_id

    def _detection(
        self, label: DetectionLabel, new_box: NormBox | None, low_conf: bool
    ) -> Detection | None:
        if label == "box":
            if new_box is None or self.rng.random() < self.noise.drop_box_frame:
                return None
            return Detection("box", self.conf(low_conf), self.jittered(new_box))
        base = VEHICLE_BOX if label == "vehicle" else PERSON_BOX
        return Detection(label, self.conf(low_conf), self.jittered(base))

    def _porch_box_detections(self) -> list[Detection | None]:
        if self.porch_box is None or self.rng.random() < self.noise.drop_box_frame:
            return []
        return [Detection("box", self.conf(), self.jittered(self.porch_box))]


def _free_spot(day: _Day) -> NormBox:
    spots = [s for s in BOX_SPOTS if s != day.porch_box]
    return day.rng.choice(spots)


def _scenario(day: _Day, kind: ScenarioKind, t0: int) -> Scenario:
    ids: list[str]
    if kind == "delivery_no_driver":
        spot = _free_spot(day)
        van = day.add_event(EventSpec(t0, 20, [["vehicle"]] * SNAPS_PER_EVENT))
        gap_s = day.rng.randint(45, 110)
        drop_at = t0 + (20 + gap_s) * MS
        drop = day.add_event(EventSpec(drop_at, 20, [["box"]] * SNAPS_PER_EVENT, "on_demand", spot))
        ids = [van, drop]
        day.porch_box = spot
    elif kind == "delivery_with_person":
        spot = _free_spot(day)
        labels: list[list[DetectionLabel]] = [["person"], ["person", "box"], ["box"]]
        ids = [day.add_event(EventSpec(t0, 30, labels, "motion", spot))]
        day.porch_box = spot
    elif kind == "car_passes":
        ids = [day.add_event(EventSpec(t0, day.rng.randint(4, 12), [["vehicle"], ["vehicle"], []]))]
    elif kind == "car_stops":
        minutes = day.rng.randint(2, 8)
        ids = []
        step_s = 90
        for k in range(minutes * 60 // step_s + 1):
            ids.append(day.add_event(EventSpec(t0 + k * step_s * MS, 15, [["vehicle"]] * 2)))
    elif kind == "visitor":
        ids = [day.add_event(EventSpec(t0, 25, [["person"]] * SNAPS_PER_EVENT, "ding"))]
    elif kind == "box_picked_up":
        ids = [day.add_event(EventSpec(t0, 25, [["person"], ["person"], []]))]
        day.snapshots[ids[0]][-1] = _without_boxes(day.snapshots[ids[0]][-1])
        day.porch_box = None
    else:
        noise_labels: list[list[DetectionLabel]] = [["person"], ["vehicle"], []]
        ids = [day.add_event(EventSpec(t0, 10, noise_labels, low_conf=True))]
    return Scenario(kind, tuple(ids))


def _without_boxes(snap: Snapshot) -> Snapshot:
    kept = tuple(d for d in snap.detections if d.label != "box")
    return Snapshot(snap.event_id, snap.at_ms, snap.media_key, kept)


def _plan(rng: random.Random, scenarios_per_day: int) -> list[ScenarioKind]:
    """A plausible order: pickups only follow a delivery that left a box."""
    kinds: list[ScenarioKind] = []
    box_waiting = False
    choices: list[ScenarioKind] = [
        "delivery_no_driver",
        "delivery_with_person",
        "car_passes",
        "car_passes",
        "car_passes",
        "car_stops",
        "visitor",
        "noise",
    ]
    for _ in range(scenarios_per_day):
        if box_waiting and rng.random() < PICKUP_CHANCE:
            kinds.append("box_picked_up")
            box_waiting = False
            continue
        kind = rng.choice(choices)
        if kind.startswith("delivery") and box_waiting:
            kind = "car_passes"
        box_waiting = box_waiting or kind.startswith("delivery")
        kinds.append(kind)
    return kinds


def generate_day(seed: int, scenarios_per_day: int, noise: Noise) -> _Day:
    rng = random.Random(seed)
    day = _Day(rng=rng, noise=noise)
    for i, kind in enumerate(_plan(rng, scenarios_per_day)):
        t0 = DAY_START_MS + i * SCENARIO_SPACING_S * MS
        day.scenarios.append(_scenario(day, kind, t0))
    return day


@dataclass(frozen=True, slots=True)
class DayScore:
    confusion: Counter[tuple[str, str]]
    baseline_alerts: int
    cards_shown: int
    folded: int


def score_day(day: _Day, params: EngineParams) -> DayScore:
    now_ms = max(e.end_ms for e in day.events) + 3600 * MS
    result = stitch(day.events, day.snapshots, PorchState(), params, HOUSE, now_ms)
    by_event = {eid: v for v in result.visits for eid in v.event_ids}
    confusion: Counter[tuple[str, str]] = Counter()
    for sc in day.scenarios:
        kinds = {by_event[e].kind for e in sc.event_ids if e in by_event}
        predicted = kinds.pop().value if len(kinds) == 1 else "split"
        confusion[(EXPECTED[sc.kind].value, predicted)] += 1
    baseline = sum(
        1
        for e in day.events
        if any(
            d.confidence >= params.min_detection_confidence
            for s in day.snapshots[e.id]
            for d in s.detections
        )
    )
    shown = sum(1 for v in result.visits if v.kind not in FOLDED)
    folded = len(result.visits) - shown
    return DayScore(confusion, baseline, shown, folded)


def _precision_recall(confusion: Counter[tuple[str, str]], kind: str) -> tuple[float, float]:
    tp = confusion[(kind, kind)]
    predicted = sum(n for (_, p), n in confusion.items() if p == kind)
    actual = sum(n for (t, _), n in confusion.items() if t == kind)
    precision = tp / predicted if predicted else 1.0
    recall = tp / actual if actual else 1.0
    return round(precision, 4), round(recall, 4)


def run(days: int, scenarios_per_day: int, noise: Noise, seed: int) -> dict[str, object]:
    params = from_settings(EngineSettings())
    total: Counter[tuple[str, str]] = Counter()
    baseline = shown = folded = 0
    for d in range(days):
        score = score_day(generate_day(seed + d, scenarios_per_day, noise), params)
        total.update(score.confusion)
        baseline += score.baseline_alerts
        shown += score.cards_shown
        folded += score.folded
    kinds = sorted({k.value for k in EXPECTED.values()})
    per_kind = {}
    for k in kinds:
        precision, recall = _precision_recall(total, k)
        per_kind[k] = {"precision": precision, "recall": recall}
    scenarios = sum(total.values())
    correct = sum(n for (t, p), n in total.items() if t == p)
    return {
        "seed": seed,
        "days": days,
        "scenarios_per_day": scenarios_per_day,
        "noise": {
            "drop_box_frame": noise.drop_box_frame,
            "false_box_frame": noise.false_box_frame,
            "jitter": noise.jitter,
        },
        "scenarios": scenarios,
        "accuracy": round(correct / scenarios, 4),
        "per_kind": per_kind,
        "confusion": {f"{t}->{p}": n for (t, p), n in sorted(total.items())},
        "baseline_alerts": baseline,
        "cards_shown": shown,
        "folded_visits": folded,
        "alert_reduction": round(1 - shown / baseline, 4) if baseline else 0.0,
    }


NOISE_LEVELS = {
    "clean": Noise(drop_box_frame=0.0, false_box_frame=0.0, jitter=0.0),
    "moderate": Noise(drop_box_frame=0.15, false_box_frame=0.05, jitter=0.02),
    "harsh": Noise(drop_box_frame=0.3, false_box_frame=0.12, jitter=0.04),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=50)
    parser.add_argument("--scenarios-per-day", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--out", type=Path, default=Path("../docs/eval/stitching.json"))
    args = parser.parse_args()
    results = {
        name: run(args.days, args.scenarios_per_day, noise, args.seed)
        for name, noise in NOISE_LEVELS.items()
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, r in results.items():
        print(
            f"{name}: accuracy {r['accuracy']} | baseline alerts {r['baseline_alerts']} "
            f"| cards shown {r['cards_shown']} | per kind {r['per_kind']}"
        )


if __name__ == "__main__":
    main()
