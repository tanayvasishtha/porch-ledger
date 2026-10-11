from porch.domain import NormBox, door_check

DOOR = ((0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5))


def test_no_polygon() -> None:
    assert door_check(NormBox(x=0.0, y=0.0, w=0.2, h=0.2), None, 0.25) == (None, None)


def test_box_inside_polygon_blocks() -> None:
    blocks, overlap = door_check(NormBox(x=0.1, y=0.1, w=0.2, h=0.2), DOOR, 0.25)
    assert blocks is True
    assert overlap == 1.0


def test_box_outside_polygon_does_not_block() -> None:
    blocks, overlap = door_check(NormBox(x=0.6, y=0.6, w=0.2, h=0.2), DOOR, 0.25)
    assert blocks is False
    assert overlap == 0.0


def test_threshold_edge_is_inclusive() -> None:
    # Polygon covers the left half of the box: overlap is exactly 0.5.
    half = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.5), (0.0, 0.5))
    blocks, overlap = door_check(NormBox(x=0.0, y=0.0, w=0.2, h=0.5), half, 0.5)
    assert overlap == 0.5
    assert blocks is True
