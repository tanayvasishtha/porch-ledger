import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from porch.config import Settings
from porch.domain import Detection, NormBox
from porch.evals.footage import (
    DoorCase,
    LabelCase,
    MissingDoorPolygonError,
    Ports,
    eval_door,
    eval_labels,
    grade_label,
)
from tests.helpers import FakeLabeler, FakeReader, demo_house, make_jpeg

IN_DOOR = NormBox(0.10, 0.50, 0.20, 0.20)
AWAY = NormBox(0.70, 0.60, 0.15, 0.15)


@pytest.mark.parametrize(
    ("expected", "state", "resident", "outcome"),
    [
        ("priya", "matched", "priya", "correct"),
        ("priya", "matched", "jo", "wrong"),
        ("priya", "unreadable", None, "abstained"),
        ("priya", "not_ours", None, "abstained"),
        ("not_ours", "not_ours", None, "correct"),
        ("not_ours", "matched", "sam", "wrong"),
        ("unreadable", "unreadable", None, "correct"),
        ("unreadable", "matched", "sam", "wrong"),
    ],
)
def test_grade_label(expected: str, state: str, resident: str | None, outcome: str) -> None:
    assert grade_label(expected, state, resident) == outcome


def _photo(tmp_path: Path) -> Path:
    path = tmp_path / "p.jpg"
    path.write_bytes(make_jpeg())
    return path


def test_label_eval_counts_outcomes(tmp_path: Path) -> None:
    _photo(tmp_path)
    ports = Ports(
        labeler=FakeLabeler([Detection("box", 0.9, IN_DOOR)]),
        reader=FakeReader(["T0: PR1YA SHAH 42"]),
    )
    cases = (LabelCase(file="p.jpg", expected="priya"), LabelCase(file="p.jpg", expected="jo"))
    result = asyncio.run(eval_labels(cases, tmp_path, demo_house(), ports, Settings()))
    assert result["counts"] == {"correct": 1, "wrong": 1}


def test_label_eval_reports_missing_box(tmp_path: Path) -> None:
    _photo(tmp_path)
    ports = Ports(labeler=FakeLabeler([]), reader=FakeReader([]))
    cases = (LabelCase(file="p.jpg", expected="priya"),)
    result = asyncio.run(eval_labels(cases, tmp_path, demo_house(), ports, Settings()))
    assert result["counts"] == {"no_box": 1}


def test_door_eval_confusion(tmp_path: Path) -> None:
    _photo(tmp_path)
    door = ((0.05, 0.35), (0.38, 0.35), (0.38, 0.98), (0.05, 0.98))
    house = replace(demo_house(), door_polygon=door)
    blocking = Ports(labeler=FakeLabeler([Detection("box", 0.9, IN_DOOR)]), reader=FakeReader())
    clear = Ports(labeler=FakeLabeler([Detection("box", 0.9, AWAY)]), reader=FakeReader())
    cases = (DoorCase(file="p.jpg", blocks_door=True),)
    hit = asyncio.run(eval_door(cases, tmp_path, house, blocking, Settings()))
    miss = asyncio.run(eval_door(cases, tmp_path, house, clear, Settings()))
    assert hit["accuracy"] == 1.0
    assert miss["confusion"] == {"blocks->clear": 1}


def test_door_eval_requires_a_polygon(tmp_path: Path) -> None:
    _photo(tmp_path)
    ports = Ports(labeler=FakeLabeler([Detection("box", 0.9, IN_DOOR)]), reader=FakeReader())
    cases = (DoorCase(file="p.jpg", blocks_door=True),)
    with pytest.raises(MissingDoorPolygonError):
        asyncio.run(eval_door(cases, tmp_path, demo_house(), ports, Settings()))
