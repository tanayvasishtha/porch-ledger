"""Small decision rules over domain values."""

from porch.domain.geometry import polygon_box_overlap
from porch.domain.models import NormBox, Polygon

OVERLAP_DECIMALS = 3


def door_check(
    box: NormBox,
    polygon: Polygon | None,
    threshold: float,
) -> tuple[bool | None, float | None]:
    """(blocks_door, overlap) or (None, None) when no door polygon is set."""
    if polygon is None:
        return None, None
    overlap = polygon_box_overlap(box, polygon)
    return overlap >= threshold, round(overlap, OVERLAP_DECIMALS)
