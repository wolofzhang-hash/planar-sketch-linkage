from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple


Point = Tuple[float, float]


def _pairwise_max_distance(points: Sequence[Point]) -> Tuple[int, int, float]:
    """Return (i, j, dist) for farthest pair (O(n^2), but n is small: ~200)."""
    best_i, best_j, best_d2 = 0, 0, -1.0
    for i in range(len(points)):
        xi, yi = points[i]
        for j in range(i + 1, len(points)):
            xj, yj = points[j]
            d2 = (xi - xj) ** 2 + (yi - yj) ** 2
            if d2 > best_d2:
                best_d2 = d2
                best_i, best_j = i, j
    return best_i, best_j, math.sqrt(best_d2) if best_d2 > 0 else 0.0


def normalize_path(points: Sequence[Point]) -> List[Point]:
    """Normalize a 2D polyline/point-cloud in a LINKS-style manner.

    Steps (high-level):
    1) Find the maximum-distance chord of the path.
    2) Rotate so that chord is horizontal.
    3) Scale so that chord length becomes 1.
    4) Translate so that the result is centered in a 1x1 box.

    Notes:
    - This is intended for *shape* comparison; absolute placement/scale is discarded.
    - For cab-door design you may want to keep scale; in that case, do not scale.
    """
    pts = list(points)
    if len(pts) < 2:
        return pts

    i, j, d = _pairwise_max_distance(pts)
    if d <= 1e-12:
        return [(0.5, 0.5) for _ in pts]

    (x1, y1), (x2, y2) = pts[i], pts[j]
    ang = math.atan2(y2 - y1, x2 - x1)
    ca, sa = math.cos(-ang), math.sin(-ang)

    # rotate
    rot = []
    for x, y in pts:
        xr = ca * x - sa * y
        yr = sa * x + ca * y
        rot.append((xr, yr))

    # scale so that max chord length = 1
    s = 1.0 / d
    scl = [(x * s, y * s) for x, y in rot]

    # center in 1x1 box
    xs = [p[0] for p in scl]
    ys = [p[1] for p in scl]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cx = (minx + maxx) * 0.5
    cy = (miny + maxy) * 0.5
    out = [(x - cx + 0.5, y - cy + 0.5) for x, y in scl]
    return out


def _min_sq_dist(p: Point, cloud: Sequence[Point]) -> float:
    px, py = p
    best = float("inf")
    for qx, qy in cloud:
        d2 = (px - qx) ** 2 + (py - qy) ** 2
        if d2 < best:
            best = d2
    return best


def bidirectional_chamfer(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Bi-directional chamfer distance between two point sets."""
    if not a or not b:
        return float("inf")
    da = sum(_min_sq_dist(p, b) for p in a) / len(a)
    db = sum(_min_sq_dist(p, a) for p in b) / len(b)
    return math.sqrt(da + db)


def angle_series_from_point_series(
    series_a: Sequence[Point], series_b: Sequence[Point], *, unwrap: bool = True
) -> List[float]:
    """Compute angle(t) of vector A->B from two point series."""
    out: List[float] = []
    for (ax, ay), (bx, by) in zip(series_a, series_b):
        out.append(math.atan2(by - ay, bx - ax))

    if not unwrap or len(out) < 2:
        return out

    # unwrap to keep continuity
    unwrapped = [out[0]]
    for k in range(1, len(out)):
        x = out[k]
        prev = unwrapped[-1]
        while x - prev > math.pi:
            x -= 2 * math.pi
        while x - prev < -math.pi:
            x += 2 * math.pi
        unwrapped.append(x)
    return unwrapped
