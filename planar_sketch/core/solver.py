# -*- coding: utf-8 -*-
"""Constraint primitives used by the controller.

This keeps the math side independent from Qt UI code.
"""

from __future__ import annotations

import math
from typing import Dict, Any

from .geometry import angle_between, clamp_angle_rad, rot2


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
    def enforce_driver_joint_angle(p_i: Dict[str, Any], p_j: Dict[str, Any], p_k: Dict[str, Any],
                                  theta_target: float, lock_i: bool, lock_j: bool, lock_k: bool,
                                  tol: float = 1e-8) -> bool:
        """Hard-set the joint angle at j for (i-j-k).

        This rotates i and/or k around j to match theta_target while preserving |ji| and |jk|.
        """
        v1x, v1y = p_i["x"] - p_j["x"], p_i["y"] - p_j["y"]
        v2x, v2y = p_k["x"] - p_j["x"], p_k["y"] - p_j["y"]
        d1 = math.hypot(v1x, v1y)
        d2 = math.hypot(v2x, v2y)
        if d1 < 1e-12 or d2 < 1e-12:
            return False

        cur = angle_between(v1x, v1y, v2x, v2y)
        err = clamp_angle_rad(cur - theta_target)
        if abs(err) <= tol:
            return True

        # If both ends are locked, can't enforce.
        if lock_i and lock_k:
            return False

        # Prefer rotating the unlocked endpoint(s) about j. If both unlocked, split the correction.
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

        if lock_p and lock_a and lock_b:
            return False

        w_p = 0.0 if lock_p else 1.0
        w_a = 0.0 if lock_a else 1.0
        w_b = 0.0 if lock_b else 1.0
        w = w_p + w_a + w_b
        if w <= 0.0:
            return False

        # Move P towards its projection, while translating the line (A,B) oppositely.
        # This converges well over iterations even when only one endpoint is free.
        if w_p > 0.0:
            p["x"] = px + (w_p / w) * dx
            p["y"] = py + (w_p / w) * dy
        if w_a > 0.0:
            a["x"] = ax - (w_a / w) * dx
            a["y"] = ay - (w_a / w) * dy
        if w_b > 0.0:
            b["x"] = bx - (w_b / w) * dx
            b["y"] = by - (w_b / w) * dy

        return True
