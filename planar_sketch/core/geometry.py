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
