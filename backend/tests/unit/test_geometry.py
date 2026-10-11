import pytest

from porch.domain import NormBox
from porch.domain.geometry import intersection_area, iou, polygon_box_overlap


def test_iou_identical() -> None:
    box = NormBox(x=0.1, y=0.1, w=0.4, h=0.4)
    assert iou(box, box) == pytest.approx(1.0)


def test_iou_disjoint() -> None:
    a = NormBox(x=0.0, y=0.0, w=0.2, h=0.2)
    b = NormBox(x=0.5, y=0.5, w=0.4, h=0.4)
    assert iou(a, b) == 0.0


def test_iou_half_overlap() -> None:
    a = NormBox(x=0.0, y=0.0, w=0.6, h=0.5)
    b = NormBox(x=0.2, y=0.0, w=0.6, h=0.5)
    assert intersection_area(a, b) == pytest.approx(0.2)
    assert iou(a, b) == pytest.approx(0.5)


def test_overlap_polygon_contains_box() -> None:
    box = NormBox(x=0.2, y=0.2, w=0.3, h=0.3)
    unit_square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    assert polygon_box_overlap(box, unit_square) == pytest.approx(1.0)


def test_overlap_triangle_covers_half() -> None:
    box = NormBox(x=0.0, y=0.0, w=1.0, h=1.0)
    triangle = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    assert polygon_box_overlap(box, triangle) == pytest.approx(0.5)


def test_overlap_polygon_outside_box() -> None:
    box = NormBox(x=0.0, y=0.0, w=0.2, h=0.2)
    far = ((0.6, 0.6), (0.9, 0.6), (0.9, 0.9))
    assert polygon_box_overlap(box, far) == 0.0


def test_overlap_partial_cover() -> None:
    # Right half of the box covered by a vertical rectangle.
    box = NormBox(x=0.2, y=0.2, w=0.4, h=0.4)
    right_half = ((0.4, 0.0), (1.0, 0.0), (1.0, 1.0), (0.4, 1.0))
    assert polygon_box_overlap(box, right_half) == pytest.approx(0.5)


def test_polygon_needs_three_points() -> None:
    box = NormBox(x=0.0, y=0.0, w=0.5, h=0.5)
    with pytest.raises(ValueError):
        polygon_box_overlap(box, ((0.0, 0.0), (1.0, 1.0)))
