# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Tuple
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker

if TYPE_CHECKING:
    from ..core.controller import SketchController


@dataclass
class BodyRenderParams:
    half_width: float = 10.0
    hole_radius: float = 4.0
    boss_radius: float = 8.0


def _unique_points(points: List[QPointF], eps: float = 1e-6) -> List[QPointF]:
    out: List[QPointF] = []
    for p in points:
        ok = True
        for q in out:
            if (p.x()-q.x())**2 + (p.y()-q.y())**2 <= eps*eps:
                ok = False
                break
        if ok:
            out.append(p)
    return out


def _cross(o: QPointF, a: QPointF, b: QPointF) -> float:
    return (a.x()-o.x())*(b.y()-o.y()) - (a.y()-o.y())*(b.x()-o.x())


def convex_hull(points: List[QPointF]) -> List[QPointF]:
    pts = sorted(points, key=lambda p: (p.x(), p.y()))
    if len(pts) <= 1:
        return pts
    lower: List[QPointF] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[QPointF] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _capsule_path(p1: QPointF, p2: QPointF, r: float) -> QPainterPath:
    path = QPainterPath(p1)
    path.lineTo(p2)
    s = QPainterPathStroker()
    s.setWidth(max(0.1, 2.0 * r))
    s.setCapStyle(Qt.PenCapStyle.RoundCap)
    s.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return s.createStroke(path)


def _poly_path(poly: List[QPointF]) -> QPainterPath:
    path = QPainterPath()
    if not poly:
        return path
    path.moveTo(poly[0])
    for p in poly[1:]:
        path.lineTo(p)
    path.closeSubpath()
    return path


def _circle_path(c: QPointF, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(c, r, r)
    return path


def _auto_params(points: List[QPointF], scale: float = 1.0) -> BodyRenderParams:
    dists = []
    for i in range(len(points)):
        for j in range(i+1, len(points)):
            dx = points[i].x()-points[j].x(); dy = points[i].y()-points[j].y()
            d = (dx*dx+dy*dy)**0.5
            if d > 1e-6:
                dists.append(d)
    if dists:
        dists.sort()
        ref = dists[len(dists)//2]
    else:
        ref = 80.0
    half_w = max(4.0, min(22.0, 0.08 * ref)) * float(scale)
    hole_r = max(2.0, min(10.0, 0.35 * half_w))
    boss_r = max(hole_r + 1.5, 0.75 * half_w)
    return BodyRenderParams(half_width=half_w, hole_radius=hole_r, boss_radius=boss_r)


def build_body_paths(ctrl: "SketchController", bid: int):
    body = ctrl.bodies.get(bid)
    if not body:
        return QPainterPath(), [], []
    pts = []
    for pid in body.get('points', []) or []:
        p = ctrl.points.get(pid)
        if p is None:
            continue
        pts.append(QPointF(float(p['x']), float(p['y'])))
    pts = _unique_points(pts)
    if not pts:
        return QPainterPath(), [], []
    scale = float(getattr(ctrl, 'body_solid_scale', 1.0) or 1.0)
    prm = _auto_params(pts, scale=scale)

    fill = QPainterPath()
    if len(pts) == 1:
        fill = _circle_path(pts[0], prm.boss_radius)
    elif len(pts) == 2:
        fill = _capsule_path(pts[0], pts[1], prm.half_width)
        fill = fill.united(_circle_path(pts[0], prm.boss_radius)).united(_circle_path(pts[1], prm.boss_radius))
    else:
        hull = convex_hull(pts)
        if len(hull) < 3:
            # degenerate -> union of capsules from sorted points
            spts = sorted(pts, key=lambda p: (p.x(), p.y()))
            fill = QPainterPath()
            for i in range(len(spts)-1):
                fill = fill.united(_capsule_path(spts[i], spts[i+1], prm.half_width))
        else:
            base = _poly_path(hull)
            stroker = QPainterPathStroker()
            stroker.setWidth(max(0.1, 2.0 * prm.half_width))
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            ring = stroker.createStroke(base)
            fill = base.united(ring)
            # make sure all joints are visually wrapped (internal points included)
            for p in pts:
                fill = fill.united(_circle_path(p, prm.boss_radius))

    boss_paths = [_circle_path(p, prm.boss_radius) for p in pts]
    hole_paths = [_circle_path(p, prm.hole_radius) for p in pts]
    for hp in hole_paths:
        fill = fill.subtracted(hp)
    return fill, boss_paths, hole_paths


def build_link_paths(ctrl: "SketchController", lid: int):
    """Solid-style geometry for a single link (capsule + joint pads)."""
    l = ctrl.links.get(lid)
    if not l:
        return QPainterPath(), [], []
    i = int(l.get("i", -1))
    j = int(l.get("j", -1))
    if i not in ctrl.points or j not in ctrl.points:
        return QPainterPath(), [], []
    p1 = ctrl.points[i]
    p2 = ctrl.points[j]
    a = QPointF(float(p1["x"]), float(p1["y"]))
    b = QPointF(float(p2["x"]), float(p2["y"]))
    scale = float(getattr(ctrl, 'body_solid_scale', 1.0) or 1.0)
    prm = _auto_params([a, b], scale=scale)
    fill = _capsule_path(a, b, prm.half_width)
    boss_paths = [_circle_path(a, prm.boss_radius), _circle_path(b, prm.boss_radius)]
    hole_paths = [_circle_path(a, prm.hole_radius), _circle_path(b, prm.hole_radius)]
    for bp in boss_paths:
        fill = fill.united(bp)
    for hp in hole_paths:
        fill = fill.subtracted(hp)
    return fill, boss_paths, hole_paths
