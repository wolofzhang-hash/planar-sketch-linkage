# -*- coding: utf-8 -*-
"""SciPy kinematic solver backend.

Used for accurate constraint satisfaction and for stable sweep simulation.

If SciPy is not available at runtime, the solver will raise RuntimeError.
"""

from __future__ import annotations

import math
from typing import Dict, Any, List, Tuple, Optional

import numpy as np

from .geometry import build_spline_samples, closest_point_on_samples

def _least_squares():
    """Import least_squares lazily to keep the app usable without SciPy."""
    try:
        from scipy.optimize import least_squares  # type: ignore
    except Exception as e:  # ImportError or runtime issues
        raise RuntimeError(
            "SciPy is required for the accurate kinematics solver. "
            "Please install scipy (e.g. pip install scipy)."
        ) from e
    return least_squares


def _angle_residual_rad(cur: float, target: float) -> Tuple[float, float]:
    """Return a wrap-safe 2D residual for an angle (cos,sin difference)."""
    return (math.cos(cur) - math.cos(target), math.sin(cur) - math.sin(target))


def _joint_angle_rad(px: float, py: float, jx: float, jy: float, kx: float, ky: float) -> float:
    """Angle at J formed by P-J-K in radians, in [0, pi]."""
    v1x, v1y = px - jx, py - jy
    v2x, v2y = kx - jx, ky - jy
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    dot = (v1x * v2x + v1y * v2y) / (n1 * n2)
    dot = max(-1.0, min(1.0, dot))
    return math.acos(dot)

class SciPyKinematicSolver:
    """Nonlinear least squares solver for the sketch constraints."""

    @staticmethod
    def solve(
        ctrl: Any,
        max_nfev: int = 200,
        ftol: float = 1e-10,
        xtol: float = 1e-10,
        gtol: float = 1e-10,
    ) -> Tuple[bool, str, float]:
        """Solve the current sketch.

        Parameters
        ----------
        ctrl:
            SketchController.
        max_nfev:
            Maximum function evaluations.

        Returns
        -------
        (ok, message, cost)
        """
        least_squares = _least_squares()

        # Variable points: all non-fixed points.
        var_pids: List[int] = [pid for pid, p in ctrl.points.items() if not bool(p.get("fixed", False))]
        idx_of: Dict[int, int] = {pid: i for i, pid in enumerate(var_pids)}

        if not var_pids:
            # Nothing to optimize, but still check over flags.
            ctrl._check_over_flags_only()
            return True, "No free points", 0.0

        x0 = np.zeros(2 * len(var_pids), dtype=float)
        for i, pid in enumerate(var_pids):
            p = ctrl.points[pid]
            x0[2 * i + 0] = float(p["x"])
            x0[2 * i + 1] = float(p["y"])

        def get_xy(pid: int, x: np.ndarray) -> Tuple[float, float]:
            if pid in idx_of:
                ii = idx_of[pid]
                return float(x[2 * ii + 0]), float(x[2 * ii + 1])
            p = ctrl.points[pid]
            return float(p["x"]), float(p["y"])

        def _active_drivers() -> List[Dict[str, Any]]:
            if hasattr(ctrl, "drivers"):
                return [d for d in getattr(ctrl, "drivers") if d.get("enabled", False)]
            if ctrl.driver.get("enabled"):
                return [ctrl.driver]
            return []

        def _active_outputs() -> List[Dict[str, Any]]:
            if hasattr(ctrl, "outputs"):
                return [o for o in getattr(ctrl, "outputs") if o.get("enabled", False)]
            if ctrl.output.get("enabled"):
                return [ctrl.output]
            return []

        def residuals(x: np.ndarray) -> np.ndarray:
            r: List[float] = []

            # Drivers (hard) as residuals
            active_drivers = _active_drivers()
            active_outputs = _active_outputs()
            if active_drivers:
                for drv in active_drivers:
                    dtype = str(drv.get("type", "angle"))
                    target = float(drv.get("rad", 0.0))
                    if dtype != "angle":
                        continue
                    piv = drv.get("pivot")
                    tip = drv.get("tip")
                    if piv is not None and tip is not None and int(piv) in ctrl.points and int(tip) in ctrl.points:
                        piv = int(piv); tip = int(tip)
                        ax, ay = get_xy(piv, x)
                        bx, by = get_xy(tip, x)
                        cur = math.atan2(by - ay, bx - ax)
                        c0, c1 = _angle_residual_rad(cur, target)
                        r.extend([c0, c1])
            elif active_outputs:
                for out in active_outputs:
                    piv = out.get("pivot")
                    tip = out.get("tip")
                    target = float(out.get("rad", 0.0))
                    if piv is not None and tip is not None and int(piv) in ctrl.points and int(tip) in ctrl.points:
                        piv = int(piv); tip = int(tip)
                        ax, ay = get_xy(piv, x)
                        bx, by = get_xy(tip, x)
                        cur = math.atan2(by - ay, bx - ax)
                        c0, c1 = _angle_residual_rad(cur, target)
                        r.extend([c0, c1])

            # Coincide constraints
            for c in ctrl.coincides.values():
                if not bool(c.get("enabled", True)):
                    continue
                a = int(c.get("a", -1)); b = int(c.get("b", -1))
                if a not in ctrl.points or b not in ctrl.points:
                    continue
                ax, ay = get_xy(a, x)
                bx, by = get_xy(b, x)
                r.extend([ax - bx, ay - by])

            # Point-on-line constraints: signed distance to infinite line
            for pl in ctrl.point_lines.values():
                if not bool(pl.get("enabled", True)):
                    continue
                p = int(pl.get("p", -1)); i = int(pl.get("i", -1)); j = int(pl.get("j", -1))
                if p not in ctrl.points or i not in ctrl.points or j not in ctrl.points:
                    continue
                px, py = get_xy(p, x)
                ix, iy = get_xy(i, x)
                jx, jy = get_xy(j, x)
                vx, vy = (jx - ix), (jy - iy)
                denom = math.hypot(vx, vy)
                if denom < 1e-12:
                    continue
                if "s" in pl:
                    ux, uy = vx / denom, vy / denom
                    target_x = ix + ux * float(pl.get("s", 0.0))
                    target_y = iy + uy * float(pl.get("s", 0.0))
                    r.extend([px - target_x, py - target_y])
                else:
                    # cross((P-I),(J-I)) / |J-I|
                    dist = ((px - ix) * vy - (py - iy) * vx) / denom
                    r.append(dist)

            # Point-on-spline constraints: closest point residual
            for ps in ctrl.point_splines.values():
                if not bool(ps.get("enabled", True)):
                    continue
                p = int(ps.get("p", -1)); s = int(ps.get("s", -1))
                if p not in ctrl.points or s not in ctrl.splines:
                    continue
                cp_ids = [pid for pid in ctrl.splines[s].get("points", []) if pid in ctrl.points]
                if len(cp_ids) < 2:
                    continue
                pts = [get_xy(pid, x) for pid in cp_ids]
                samples = build_spline_samples([(float(px), float(py)) for px, py in pts], samples_per_segment=12)
                if len(samples) < 2:
                    continue
                px, py = get_xy(p, x)
                cx, cy, _seg_idx, _t_seg, _dist2 = closest_point_on_samples(px, py, samples)
                r.extend([px - cx, py - cy])

            # Rigid body edges
            for b in ctrl.bodies.values():
                for (i, j, L) in b.get("rigid_edges", []):
                    if i not in ctrl.points or j not in ctrl.points:
                        continue
                    ix, iy = get_xy(int(i), x)
                    jx, jy = get_xy(int(j), x)
                    d = math.hypot(jx - ix, jy - iy)
                    r.append(d - float(L))

            # Length constraints
            for l in ctrl.links.values():
                if bool(l.get("ref", False)):
                    continue
                i = int(l.get("i", -1)); j = int(l.get("j", -1))
                if i not in ctrl.points or j not in ctrl.points:
                    continue
                ix, iy = get_xy(i, x)
                jx, jy = get_xy(j, x)
                d = math.hypot(jx - ix, jy - iy)
                r.append(d - float(l.get("L", 0.0)))

            # Angle constraints
            for a in ctrl.angles.values():
                if not bool(a.get("enabled", True)):
                    continue
                i = int(a.get("i", -1)); j = int(a.get("j", -1)); k = int(a.get("k", -1))
                if i not in ctrl.points or j not in ctrl.points or k not in ctrl.points:
                    continue
                ix, iy = get_xy(i, x)
                jx, jy = get_xy(j, x)
                kx, ky = get_xy(k, x)
                cur = _joint_angle_rad(ix, iy, jx, jy, kx, ky)
                target = float(a.get("rad", 0.0))
                c0, c1 = _angle_residual_rad(cur, target)
                r.extend([c0, c1])

            if not r:
                return np.zeros(0, dtype=float)
            return np.asarray(r, dtype=float)

        res = least_squares(
            residuals,
            x0,
            max_nfev=int(max_nfev),
            ftol=float(ftol),
            xtol=float(xtol),
            gtol=float(gtol),
        )

        # Apply result back to controller
        x_opt = res.x
        for i, pid in enumerate(var_pids):
            ctrl.points[pid]["x"] = float(x_opt[2 * i + 0])
            ctrl.points[pid]["y"] = float(x_opt[2 * i + 1])

        # Update over flags (without moving points)
        ctrl._check_over_flags_only()

        ok = bool(res.success)
        msg = str(res.message)
        return ok, msg, float(res.cost)
