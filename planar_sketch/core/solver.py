# -*- coding: utf-8 -*-
"""Constraint primitives used by the controller.

This keeps the math side independent from Qt UI code.
"""

from __future__ import annotations

import math
from typing import Dict, Any

from .geometry import (
    angle_between,
    clamp_angle_rad,
    rot2,
    build_spline_samples,
    closest_point_on_samples,
    closest_point_on_samples_hint,
)


class ConstraintSolver:
    @staticmethod
    def solve_length(p1: Dict[str, Any], p2: Dict[str, Any], L: float,
                     lock1: bool, lock2: bool, tol: float = 1e-8) -> bool:
        dx = p2["x"] - p1["x"]
        dy = p2["y"] - p1["y"]
        d = math.hypot(dx, dy)
        if d < 1e-12:
            if lock1 and lock2 and L > tol:
                return False
            return True
        if lock1 and lock2:
            return abs(d - L) <= tol
        w1 = 0.0 if lock1 else 1.0
        w2 = 0.0 if lock2 else 1.0
        w = w1 + w2
        if w <= 0.0:
            return abs(d - L) <= tol
        C = d - L
        nx, ny = dx / d, dy / d
        p1["x"] += (w1 / w) * C * nx
        p1["y"] += (w1 / w) * C * ny
        p2["x"] -= (w2 / w) * C * nx
        p2["y"] -= (w2 / w) * C * ny
        return True

    @staticmethod
    def solve_angle(p_i: Dict[str, Any], p_j: Dict[str, Any], p_k: Dict[str, Any],
                    theta_target: float, lock_i: bool, lock_j: bool, lock_k: bool,
                    tol: float = 1e-6) -> bool:
        v1x, v1y = p_i["x"] - p_j["x"], p_i["y"] - p_j["y"]
        v2x, v2y = p_k["x"] - p_j["x"], p_k["y"] - p_j["y"]
        d1 = math.hypot(v1x, v1y)
        d2 = math.hypot(v2x, v2y)
        if d1 < 1e-12 or d2 < 1e-12:
            return True
        cur = angle_between(v1x, v1y, v2x, v2y)
        err = clamp_angle_rad(cur - theta_target)
        if abs(err) <= tol:
            return True
        if lock_i and lock_k:
            return False
        if lock_i and not lock_k:
            rv2x, rv2y = rot2(v2x, v2y, -err)
            p_k["x"] = p_j["x"] + rv2x
            p_k["y"] = p_j["y"] + rv2y
            return True
        if lock_k and not lock_i:
            rv1x, rv1y = rot2(v1x, v1y, +err)
            p_i["x"] = p_j["x"] + rv1x
            p_i["y"] = p_j["y"] + rv1y
            return True
        half = err * 0.5
        rv1x, rv1y = rot2(v1x, v1y, +half)
        rv2x, rv2y = rot2(v2x, v2y, -half)
        p_i["x"] = p_j["x"] + rv1x
        p_i["y"] = p_j["y"] + rv1y
        p_k["x"] = p_j["x"] + rv2x
        p_k["y"] = p_j["y"] + rv2y
        return True

    @staticmethod
    def enforce_driver_angle(p_pivot: Dict[str, Any], p_tip: Dict[str, Any],
                             theta_target: float, lock_pivot: bool, lock_tip: bool) -> bool:
        """Hard-set the tip point to a desired polar angle around pivot.

        The radius is the current pivot-tip distance (or a stored 'driver_L' if present).
        """
        if lock_tip:
            # Can't move the tip; consider it a contradiction.
            return False

        dx = p_tip["x"] - p_pivot["x"]
        dy = p_tip["y"] - p_pivot["y"]
        r = math.hypot(dx, dy)
        # allow storing a stable radius on the tip point (helps when starting from coincident)
        if r < 1e-9:
            r = float(p_tip.get("driver_L", 0.0))
        else:
            p_tip["driver_L"] = r

        if r < 1e-9:
            return False

        p_tip["x"] = p_pivot["x"] + r * math.cos(theta_target)
        p_tip["y"] = p_pivot["y"] + r * math.sin(theta_target)
        return True



    @staticmethod
    def solve_point_on_line(
        p: Dict[str, Any],
        a: Dict[str, Any],
        b: Dict[str, Any],
        lock_p: bool,
        lock_a: bool,
        lock_b: bool,
        tol: float = 1e-8,
    ) -> bool:
        """Enforce point P to lie on the infinite line through A-B.

        PBD-style correction. If all participating points are locked, this returns
        whether the constraint is already satisfied within tol.
        """

        ax, ay = float(a["x"]), float(a["y"])
        bx, by = float(b["x"]), float(b["y"])
        px, py = float(p["x"]), float(p["y"])

        abx, aby = bx - ax, by - ay
        ab2 = abx * abx + aby * aby
        if ab2 < 1e-18:
            # Degenerate line; can't do much.
            return True

        apx, apy = px - ax, py - ay
        t = (apx * abx + apy * aby) / ab2
        projx = ax + t * abx
        projy = ay + t * aby

        dx = projx - px
        dy = projy - py
        if dx * dx + dy * dy <= tol * tol:
            return True

        if lock_p:
            if lock_a and lock_b:
                return False
            if lock_a and not lock_b:
                apx, apy = px - ax, py - ay
                ap2 = apx * apx + apy * apy
                if ap2 < 1e-18:
                    return True
                t = ((bx - ax) * apx + (by - ay) * apy) / ap2
                b["x"] = ax + t * apx
                b["y"] = ay + t * apy
                return True
            if lock_b and not lock_a:
                bpx, bpy = px - bx, py - by
                bp2 = bpx * bpx + bpy * bpy
                if bp2 < 1e-18:
                    return True
                t = ((ax - bx) * bpx + (ay - by) * bpy) / bp2
                a["x"] = bx + t * bpx
                a["y"] = by + t * bpy
                return True
            a["x"] = ax + dx
            a["y"] = ay + dy
            b["x"] = bx + dx
            b["y"] = by + dy
            return True

        p["x"] = projx
        p["y"] = projy
        return True

    @staticmethod
    def solve_point_on_line_offset(
        p: Dict[str, Any],
        a: Dict[str, Any],
        b: Dict[str, Any],
        s: float,
        lock_p: bool,
        lock_a: bool,
        lock_b: bool,
        tol: float = 1e-8,
    ) -> bool:
        """Enforce point P to sit at A + unit(B-A) * s.

        This pins the point to a specific displacement along the AB direction.
        """
        ax, ay = float(a["x"]), float(a["y"])
        bx, by = float(b["x"]), float(b["y"])
        px, py = float(p["x"]), float(p["y"])

        abx, aby = bx - ax, by - ay
        ab_len = math.hypot(abx, aby)
        if ab_len < 1e-12:
            return True

        ux, uy = abx / ab_len, aby / ab_len
        target_x = ax + ux * float(s)
        target_y = ay + uy * float(s)

        dx = target_x - px
        dy = target_y - py
        if dx * dx + dy * dy <= tol * tol:
            return True

        if lock_p:
            if lock_a and lock_b:
                return False
            if lock_a and not lock_b:
                apx, apy = px - ax, py - ay
                ap_len = math.hypot(apx, apy)
                if ap_len < 1e-12:
                    return abs(float(s)) <= tol
                ux, uy = apx / ap_len, apy / ap_len
                proj = (bx - ax) * ux + (by - ay) * uy
                b["x"] = ax + proj * ux
                b["y"] = ay + proj * uy
                return abs(ap_len - float(s)) <= tol
            if lock_b and not lock_a:
                bpx, bpy = bx - px, by - py
                bp_len = math.hypot(bpx, bpy)
                if bp_len < 1e-12:
                    return False
                ux, uy = bpx / bp_len, bpy / bp_len
                a["x"] = px - ux * float(s)
                a["y"] = py - uy * float(s)
                return True
            if ab_len < 1e-12:
                ux, uy = 1.0, 0.0
            else:
                ux, uy = abx / ab_len, aby / ab_len
            a["x"] = px - ux * float(s)
            a["y"] = py - uy * float(s)
            b["x"] = a["x"] + ux * ab_len
            b["y"] = a["y"] + uy * ab_len
            return True

        p["x"] = target_x
        p["y"] = target_y
        return True

    @staticmethod
    def solve_point_on_spline(
        p: Dict[str, Any],
        control_points: list[Dict[str, Any]],
        lock_p: bool,
        lock_controls: list[bool],
        tol: float = 1e-8,
        samples_per_segment: int = 16,
        closed: bool = False,
    ) -> bool:
        """Enforce point P to lie on a spline defined by control points."""
        if len(control_points) < 2:
            return True
        pts = [(float(cp["x"]), float(cp["y"])) for cp in control_points]
        samples = build_spline_samples(pts, samples_per_segment=samples_per_segment, closed=closed)
        if len(samples) < 2:
            return True

        px, py = float(p["x"]), float(p["y"])
        cx, cy, seg_idx, t_seg, dist2 = closest_point_on_samples(px, py, samples)
        if dist2 <= tol * tol:
            return True

        if lock_p and all(lock_controls):
            return False

        w_p = 0.0 if lock_p else 1.0
        weights = [0.0 for _ in control_points]
        if 0 <= seg_idx < len(control_points) - 1:
            weights[seg_idx] = max(0.0, min(1.0, 1.0 - t_seg))
            weights[seg_idx + 1] = max(0.0, min(1.0, t_seg))

        w = w_p
        for idx, w_i in enumerate(weights):
            if not lock_controls[idx]:
                w += w_i
        if w <= 0.0:
            return False

        dx = cx - px
        dy = cy - py
        if w_p > 0.0:
            p["x"] = px + (w_p / w) * dx
            p["y"] = py + (w_p / w) * dy
        for idx, w_i in enumerate(weights):
            if w_i <= 0.0 or lock_controls[idx]:
                continue
            control_points[idx]["x"] = control_points[idx]["x"] - (w_i / w) * dx
            control_points[idx]["y"] = control_points[idx]["y"] - (w_i / w) * dy
        return True

    @staticmethod
    def solve_point_spline_distance(
        p: Dict[str, Any],
        control_points: list[Dict[str, Any]],
        target_dist: float,
        lock_p: bool,
        lock_controls: list[bool],
        hint_seg: int = -1,
        tol: float = 1e-8,
        samples_per_segment: int = 16,
        closed: bool = False,
    ) -> tuple[bool, int, float]:
        """Enforce distance from point P to a spline equals target_dist.

        Returns (ok, new_hint_seg, current_dist).

        Notes:
        - This models a roller-follower contact when P is the roller center and target_dist is roller radius.
        - hint_seg helps avoid jumping to a different local minimum on closed curves.
        """
        if len(control_points) < 2:
            return True, int(hint_seg) if hint_seg is not None else -1, 0.0

        pts = [(float(cp["x"]), float(cp["y"])) for cp in control_points]
        samples = build_spline_samples(pts, samples_per_segment=samples_per_segment, closed=closed)
        if len(samples) < 2:
            return True, int(hint_seg) if hint_seg is not None else -1, 0.0

        px, py = float(p["x"]), float(p["y"])
        cx, cy, seg_idx, _t_seg, dist2 = closest_point_on_samples_hint(px, py, samples, hint_seg=int(hint_seg or -1), seg_window=3)
        d = math.sqrt(max(0.0, dist2))

        err = d - float(target_dist)
        if abs(err) <= tol:
            return True, int(seg_idx), d

        if lock_p and all(lock_controls):
            return False, int(seg_idx), d

        # Direction from closest point to P
        vx = px - cx
        vy = py - cy
        vlen = math.hypot(vx, vy)
        if vlen < 1e-12:
            # Degenerate; choose a stable direction.
            vx, vy = 1.0, 0.0
            vlen = 1.0
        nx, ny = vx / vlen, vy / vlen

        # Correction moves P along the normal to satisfy distance.
        # PBD-style weighting: distribute between P and (optionally) spline control points.
        w_p = 0.0 if lock_p else 1.0
        w_ctrl = 0.0 if all(lock_controls) else 0.25  # keep spline mostly rigid
        w = w_p + w_ctrl
        if w <= 0.0:
            return False, int(seg_idx), d

        dx = -err * nx
        dy = -err * ny

        if w_p > 0.0:
            p["x"] = px + (w_p / w) * dx
            p["y"] = py + (w_p / w) * dy

        if w_ctrl > 0.0 and len(control_points) >= 2:
            # Spread small opposite correction to all unlocked control points (keeps continuity).
            # This avoids needing segment->control weight mapping, and works well if the spline is part of a rigid body.
            free = [idx for idx, lk in enumerate(lock_controls) if not lk]
            if free:
                per = (w_ctrl / w) / float(len(free))
                for idx in free:
                    control_points[idx]["x"] = float(control_points[idx]["x"]) - per * dx
                    control_points[idx]["y"] = float(control_points[idx]["y"]) - per * dy

        return True, int(seg_idx), d
