"""Pure geometry helpers: box IoU and polygon overlap, no dependencies."""

from collections.abc import Callable

from porch.domain.models import DomainError, NormBox

Point = tuple[float, float]
Polygon = tuple[Point, ...]
InsideFn = Callable[[Point], bool]
IntersectFn = Callable[[Point, Point], Point]

MIN_POLYGON_POINTS = 3


class PolygonError(DomainError):
    """A polygon without enough points to enclose an area."""

    def __init__(self, points: int) -> None:
        super().__init__(f"polygon has {points} points, needs at least {MIN_POLYGON_POINTS}")


def intersection_area(a: NormBox, b: NormBox) -> float:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if w <= 0.0 or h <= 0.0:
        return 0.0
    return w * h


def iou(a: NormBox, b: NormBox) -> float:
    inter = intersection_area(a, b)
    union = a.area + b.area - inter
    return min(inter / union, 1.0)


def _cross_x(p1: Point, p2: Point, x: float) -> Point:
    """Point where segment p1-p2 crosses the vertical line x."""
    x1, y1 = p1
    x2, y2 = p2
    t = (x - x1) / (x2 - x1)
    return (x, y1 + t * (y2 - y1))


def _cross_y(p1: Point, p2: Point, y: float) -> Point:
    """Point where segment p1-p2 crosses the horizontal line y."""
    x1, y1 = p1
    x2, y2 = p2
    t = (y - y1) / (y2 - y1)
    return (x1 + t * (x2 - x1), y)


def _clip_half_plane(points: list[Point], inside: InsideFn, intersect: IntersectFn) -> list[Point]:
    """Sutherland-Hodgman: clip a polygon by one half-plane."""
    if not points:
        return []
    out: list[Point] = []
    prev = points[-1]
    prev_in = inside(prev)
    for cur in points:
        cur_in = inside(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect(prev, cur))
        prev = cur
        prev_in = cur_in
    return out


def _shoelace(points: list[Point]) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_box_overlap(box: NormBox, polygon: Polygon) -> float:
    """area(box ∩ polygon) / area(box); 1.0 when the polygon covers the box."""
    if len(polygon) < MIN_POLYGON_POINTS:
        raise PolygonError(len(polygon))
    xmin, ymin = box.x, box.y
    xmax, ymax = box.x + box.w, box.y + box.h
    points = list(polygon)
    points = _clip_half_plane(points, lambda p: p[0] >= xmin, lambda a, b: _cross_x(a, b, xmin))
    points = _clip_half_plane(points, lambda p: p[0] <= xmax, lambda a, b: _cross_x(a, b, xmax))
    points = _clip_half_plane(points, lambda p: p[1] >= ymin, lambda a, b: _cross_y(a, b, ymin))
    points = _clip_half_plane(points, lambda p: p[1] <= ymax, lambda a, b: _cross_y(a, b, ymax))
    if len(points) < MIN_POLYGON_POINTS:
        return 0.0
    overlap = _shoelace(points) / box.area
    return min(max(overlap, 0.0), 1.0)
