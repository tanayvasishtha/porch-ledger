import math

from hypothesis import given, settings
from hypothesis import strategies as st

from porch.domain import NormBox
from porch.domain.geometry import iou, polygon_box_overlap

UNIT_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


@st.composite
def boxes(draw: st.DrawFn) -> NormBox:
    x = draw(st.floats(0.0, 0.99))
    y = draw(st.floats(0.0, 0.99))
    w = draw(st.floats(0.001, 1.0 - x))
    h = draw(st.floats(0.001, 1.0 - y))
    return NormBox(x=x, y=y, w=w, h=h)


@st.composite
def polygons(draw: st.DrawFn) -> tuple[tuple[float, float], ...]:
    n = draw(st.integers(3, 8))
    pts = [(draw(st.floats(-0.5, 1.5)), draw(st.floats(-0.5, 1.5))) for _ in range(n)]
    return tuple(pts)


@given(boxes(), boxes())
@settings(max_examples=200)
def test_iou_symmetric_and_unit(a: NormBox, b: NormBox) -> None:
    assert iou(a, b) == iou(b, a)
    assert 0.0 <= iou(a, b) <= 1.0


@given(boxes(), polygons())
@settings(max_examples=200)
def test_overlap_in_unit_range(a: NormBox, poly: tuple[tuple[float, float], ...]) -> None:
    overlap = polygon_box_overlap(a, poly)
    assert 0.0 <= overlap <= 1.0


@given(boxes())
def test_overlap_unit_square_covers_box(a: NormBox) -> None:
    assert math.isclose(polygon_box_overlap(a, UNIT_SQUARE), 1.0, rel_tol=1e-9)
