# -*- coding: utf-8 -*-
"""Geometry helpers."""

from __future__ import annotations

import math
from typing import List


def clamp_angle_rad(a: float) -> float:
    """Wrap angle to (-pi, pi]."""
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def angle_between(v1x: float, v1y: float, v2x: float, v2y: float) -> float:
    cross = v1x * v2y - v1y * v2x
    dot = v1x * v2x + v1y * v2y
    return math.atan2(cross, dot)


def rot2(x: float, y: float, a: float) -> tuple[float, float]:
    ca, sa = math.cos(a), math.sin(a)
    return ca * x - sa * y, sa * x + ca * y


def parse_id_list(s: str) -> List[int]:
    s = (s or "").strip()
    if not s:
        return []
    out: List[int] = []
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out


def catmull_rom_point(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float) -> tuple[float, float]:
    """Evaluate a uniform Catmull-Rom spline segment at t in [0,1]."""
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        (2.0 * p1[0])
        + (-p0[0] + p2[0]) * t
        + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        (2.0 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
    )
    return x, y


def build_spline_samples(points: List[tuple[float, float]], samples_per_segment: int = 16) -> List[tuple[float, float, int, float]]:
    """Return spline samples as (x, y, segment_index, t_segment)."""
    if len(points) < 2:
        return []
    n = len(points)
    samples: List[tuple[float, float, int, float]] = []
    seg_samples = max(4, int(samples_per_segment))
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        for s in range(seg_samples + 1):
            if i > 0 and s == 0:
                continue
            t = s / seg_samples
            if n == 2:
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
            else:
                x, y = catmull_rom_point(p0, p1, p2, p3, t)
            samples.append((x, y, i, t))
    return samples


def closest_point_on_samples(px: float, py: float, samples: List[tuple[float, float, int, float]]) -> tuple[float, float, int, float, float]:
    """Find the closest point on a sampled polyline.

    Returns (cx, cy, segment_index, t_segment, dist2).
    """
    if len(samples) < 2:
        return px, py, -1, 0.0, float("inf")
    best = (px, py, -1, 0.0, float("inf"))
    for idx in range(len(samples) - 1):
        x1, y1, seg1, t1 = samples[idx]
        x2, y2, seg2, t2 = samples[idx + 1]
        vx = x2 - x1
        vy = y2 - y1
        denom = vx * vx + vy * vy
        if denom <= 1e-18:
            continue
        u = ((px - x1) * vx + (py - y1) * vy) / denom
        u = max(0.0, min(1.0, u))
        cx = x1 + u * vx
        cy = y1 + u * vy
        dx = cx - px
        dy = cy - py
        dist2 = dx * dx + dy * dy
        if dist2 < best[4]:
            if seg1 == seg2:
                t_seg = t1 + u * (t2 - t1)
                seg_index = seg1
            else:
                seg_index = seg2 if u > 0.5 else seg1
                t_seg = t2 if u > 0.5 else t1
            best = (cx, cy, seg_index, t_seg, dist2)
    return best
