"""Label reading and door check evaluation on our own labelled photos.

Ground truth lives in a manifest written by hand after looking at each
photo: the resident whose name is on the label (or "not_ours" for a name
outside the household, or "unreadable" for a label turned away), and
whether the box blocks the door. The pipeline under test is the same code
the worker runs: Rekognition finds the box, the crop goes to Textract, the
text is matched to residents, and the box is checked against the door
polygon of the house the photos were taken at.

Run with `--mode record` once against AWS; the responses land in cassettes,
so `--mode replay` reproduces the published numbers with no network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from porch.adapters.cassette import Cassette
from porch.adapters.local.house_file import load_house
from porch.config import Settings
from porch.domain import House, NormBox, match_recipient
from porch.domain.rules import door_check
from porch.pipeline.enrich import crop_label
from porch.ports import Labeler, LabelReader

LabelOutcome = Literal["correct", "abstained", "wrong", "no_box"]


class MissingDoorPolygonError(ValueError):
    """The door eval needs the house's door polygon; a house without one is a setup error."""

    def __init__(self, house_id: str) -> None:
        super().__init__(f"house {house_id} has no door_polygon")


NOT_OURS = "not_ours"
UNREADABLE = "unreadable"


class LabelCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    file: str
    expected: str


class DoorCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    file: str
    blocks_door: bool


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    house: str
    labels: tuple[LabelCase, ...] = ()
    door: tuple[DoorCase, ...] = ()


@dataclass(frozen=True, slots=True)
class Ports:
    labeler: Labeler
    reader: LabelReader


async def largest_box(image: bytes, labeler: Labeler) -> NormBox | None:
    detections = await labeler.detect(image)
    boxes = [d.box for d in detections if d.label == "box" and d.box is not None]
    return max(boxes, key=lambda b: b.area) if boxes else None


def grade_label(expected: str, state: str, resident_id: str | None) -> LabelOutcome:
    """A wrong name is the costly error; saying "not readable" is an abstention."""
    if state == "matched":
        return "correct" if resident_id == expected else "wrong"
    if expected == NOT_OURS:
        return "correct" if state == NOT_OURS else "abstained"
    if expected == UNREADABLE:
        return "correct"
    return "abstained"


async def eval_labels(
    cases: tuple[LabelCase, ...], root: Path, house: House, ports: Ports, settings: Settings
) -> dict[str, object]:
    outcomes: Counter[str] = Counter()
    rows: list[dict[str, str]] = []
    for case in cases:
        image = (root / case.file).read_bytes()
        box = await largest_box(image, ports.labeler)
        if box is None:
            outcome: LabelOutcome = "no_box"
            got = "no_box"
        else:
            lines = await ports.reader.read(crop_label(image, box, settings))
            match = match_recipient(
                lines,
                house.residents,
                settings.vision.recipient_min_score,
                settings.vision.recipient_margin,
            )
            got = match.resident_id or match.state
            outcome = grade_label(case.expected, match.state, match.resident_id)
        outcomes[outcome] += 1
        rows.append({"file": case.file, "expected": case.expected, "got": got, "outcome": outcome})
    total = len(cases)
    return {
        "photos": total,
        "rates": {k: round(outcomes[k] / total, 4) if total else 0.0 for k in sorted(outcomes)},
        "counts": dict(sorted(outcomes.items())),
        "rows": rows,
    }


async def eval_door(
    cases: tuple[DoorCase, ...], root: Path, house: House, ports: Ports, settings: Settings
) -> dict[str, object]:
    if cases and house.door_polygon is None:
        raise MissingDoorPolygonError(house.id)
    confusion: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    for case in cases:
        image = (root / case.file).read_bytes()
        box = await largest_box(image, ports.labeler)
        if box is None:
            predicted: bool | None = None
            overlap: float | None = None
        else:
            predicted, overlap = door_check(
                box, house.door_polygon, settings.vision.door_block_overlap
            )
        key = f"{'blocks' if case.blocks_door else 'clear'}->" + (
            "no_box" if predicted is None else ("blocks" if predicted else "clear")
        )
        confusion[key] += 1
        rows.append({"file": case.file, "expected": case.blocks_door, "overlap": overlap})
    total = len(cases)
    correct = confusion["blocks->blocks"] + confusion["clear->clear"]
    return {
        "photos": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "confusion": dict(sorted(confusion.items())),
        "rows": rows,
    }


def live_ports(settings: Settings, cassette: Cassette) -> Ports:
    from porch.adapters.aws.clients import build_clients  # noqa: PLC0415
    from porch.adapters.aws.rekognition import RekognitionLabeler  # noqa: PLC0415
    from porch.adapters.aws.textract import TextractReader  # noqa: PLC0415

    clients = build_clients(settings)
    return Ports(
        labeler=RekognitionLabeler(clients.rekognition, settings, cassette),
        reader=TextractReader(clients.textract, settings, cassette),
    )


async def run(manifest_path: Path, mode: Literal["record", "replay"]) -> dict[str, object]:
    manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    settings = Settings()
    house = load_house(root / manifest.house)
    cassette = Cassette(root / "cassettes", mode)
    ports = live_ports(settings, cassette)
    return {
        "labels": await eval_labels(manifest.labels, root, house, ports, settings),
        "door": await eval_door(manifest.door, root, house, ports, settings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=Path("../fixtures/own/manifest.json"))
    parser.add_argument("--mode", choices=("record", "replay"), default="replay")
    parser.add_argument("--out", type=Path, default=Path("../docs/eval/footage.json"))
    args = parser.parse_args()
    results = asyncio.run(run(args.manifest, args.mode))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    labels = results["labels"]
    door = results["door"]
    assert isinstance(labels, dict) and isinstance(door, dict)
    print(f"labels: {labels['counts']} of {labels['photos']}")
    print(f"door: accuracy {door['accuracy']} {door['confusion']}")


if __name__ == "__main__":
    main()
