# -*- coding: utf-8 -*-
"""Exudyn kinematic/quasi-static solver backend.

This module provides a thin integration layer for Exudyn. It currently
initializes an Exudyn system to ensure the runtime is available, then
uses the existing constraint solver as a fallback to keep the UI responsive.

The API is designed to be extended with full Exudyn-based constraint and
load handling (hinges, trajectories, springs, friction, etc.).
"""

from __future__ import annotations

from typing import Any, Tuple, Dict, List, Optional
import importlib
import importlib.util
import math
import traceback
from .solver import ConstraintSolver
from .geometry import build_spline_samples


def _load_exudyn():
    spec = importlib.util.find_spec("exudyn")
    if spec is None:
        raise RuntimeError(
            "Exudyn is required for the Exudyn solver. "
            "Please install exudyn (e.g. pip install exudyn)."
        )
    return importlib.import_module("exudyn")


class ExudynKinematicSolver:
    """Integration stub for Exudyn-based solvers."""

    @staticmethod
    def _format_exception(exc: BaseException) -> str:
        tb = traceback.TracebackException.from_exception(exc)
        frames = list(tb.stack)
        details = [f"{type(exc).__name__}: {exc}"]
        if frames:
            head = frames[0]
            details.append(f"at {head.filename}:{head.lineno} in {head.name}")
            tail = frames[-1]
            if tail is not head:
                details.append(f"-> {tail.filename}:{tail.lineno} in {tail.name}")
        return "; ".join(details)

    @staticmethod
    def _point_line_error(plid: int, p_id: Optional[int], detail: str) -> ValueError:
        point_info = f"point {p_id}" if p_id is not None else "point ?"
        return ValueError(f"Point-line {plid} ({point_info}): {detail}")

    @staticmethod
    def _validate_point_lines(ctrl: Any) -> Tuple[bool, str]:
        if not hasattr(ctrl, "point_lines"):
            return True, ""
        for plid, pl in ctrl.point_lines.items():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = pl.get("p")
            if hasattr(ctrl, "_point_line_current_s"):
                raw_current = ctrl._point_line_current_s(pl)
                if raw_current is not None:
                    try:
                        val = float(raw_current)
                    except Exception as exc:
                        return False, str(
                            ExudynKinematicSolver._point_line_error(
                                int(plid),
                                p_id,
                                f"invalid current s value {raw_current!r} ({type(exc).__name__})",
                            )
                        )
                    if not math.isfinite(val):
                        return False, str(
                            ExudynKinematicSolver._point_line_error(
                                int(plid),
                                p_id,
                                f"non-finite current s value {raw_current!r}",
                            )
                        )
            if pl.get("s_expr") and pl.get("s_expr_error"):
                msg = pl.get("s_expr_error_msg") or "invalid s expression"
                return False, str(ExudynKinematicSolver._point_line_error(int(plid), p_id, msg))
            if "s" in pl:
                raw_s = pl.get("s", None)
                if raw_s is None:
                    return False, str(
                        ExudynKinematicSolver._point_line_error(int(plid), p_id, "s value is None")
                    )
                try:
                    val = float(raw_s)
                except Exception as exc:
                    return False, str(
                        ExudynKinematicSolver._point_line_error(
                            int(plid),
                            p_id,
                            f"invalid s value {raw_s!r} ({type(exc).__name__})",
                        )
                    )
                if not math.isfinite(val):
                    return False, str(
                        ExudynKinematicSolver._point_line_error(
                            int(plid), p_id, f"non-finite s value {raw_s!r}"
                        )
                    )
        return True, ""

    @staticmethod
    def _active_drivers(ctrl: Any) -> List[Dict[str, Any]]:
        if hasattr(ctrl, "drivers"):
            return [d for d in getattr(ctrl, "drivers") if d.get("enabled", False)]
        if hasattr(ctrl, "driver") and ctrl.driver.get("enabled"):
            return [ctrl.driver]
        return []

    @staticmethod
    def _active_outputs(ctrl: Any) -> List[Dict[str, Any]]:
        if hasattr(ctrl, "outputs"):
            return [o for o in getattr(ctrl, "outputs") if o.get("enabled", False)]
        if hasattr(ctrl, "output") and ctrl.output.get("enabled"):
            return [ctrl.output]
        return []

    @staticmethod
    def _collect_driven_pids(ctrl: Any) -> set[int]:
        driven_pids: set[int] = set()
        active_drivers: List[Dict[str, Any]] = []
        active_outputs: List[Dict[str, Any]] = []
        if hasattr(ctrl, "_active_drivers"):
            active_drivers = list(ctrl._active_drivers())
        if hasattr(ctrl, "_active_outputs"):
            active_outputs = list(ctrl._active_outputs())

        drive_sources: List[Dict[str, Any]] = []
        if active_drivers:
            drive_sources.extend([dict(drv, mode="driver") for drv in active_drivers])
        elif active_outputs:
            for out in active_outputs:
                drive_sources.append({
                    "mode": "output",
                    "type": "angle",
                    "pivot": out.get("pivot"),
                    "tip": out.get("tip"),
                    "rad": out.get("rad", 0.0),
                })

        for drv in drive_sources:
            if str(drv.get("type", "angle")) == "translation":
                plid = drv.get("plid")
                if hasattr(ctrl, "point_lines") and plid in ctrl.point_lines:
                    p_id = ctrl.point_lines[plid].get("p")
                    if p_id is not None:
                        driven_pids.add(int(p_id))
                continue
            tip = drv.get("tip")
            if tip is not None:
                driven_pids.add(int(tip))
        return driven_pids

    @staticmethod
    def _apply_spring_loads(ctrl: Any, driven_pids: set[int], step_alpha: float = 0.25) -> None:
        if not hasattr(ctrl, "loads") or not hasattr(ctrl, "points"):
            return
        if not hasattr(ctrl, "_resolve_load_components"):
            return
        for load in getattr(ctrl, "loads", []):
            if str(load.get("type", "force")).lower() != "spring":
                continue
            pid = int(load.get("pid", -1))
            if pid not in ctrl.points:
                continue
            p = ctrl.points[pid]
            if bool(p.get("fixed", False)) or pid in driven_pids:
                continue
            fx, fy, _mz = ctrl._resolve_load_components(load)
            k = float(load.get("k", 0.0))
            scale = float(step_alpha)
            if abs(k) > 1e-9:
                scale /= abs(k)
            p["x"] = float(p["x"]) + scale * float(fx)
            p["y"] = float(p["y"]) + scale * float(fy)

    @staticmethod
    def _solve_distance_constraints(ctrl: Any, max_iters: int, driven_pids: set[int]) -> None:
        if not hasattr(ctrl, "points"):
            return

        active_drivers = ExudynKinematicSolver._active_drivers(ctrl)
        active_outputs = ExudynKinematicSolver._active_outputs(ctrl)
        drive_sources: List[Dict[str, Any]] = []
        if active_drivers:
            for drv in active_drivers:
                entry = dict(drv)
                entry["mode"] = "driver"
                drive_sources.append(entry)
        elif active_outputs:
            for out in active_outputs:
                entry = {
                    "mode": "output",
                    "type": "angle",
                    "pivot": out.get("pivot"),
                    "tip": out.get("tip"),
                    "rad": out.get("rad", 0.0),
                }
                drive_sources.append(entry)

        translation_targets: Dict[int, float] = {}
        for drv in drive_sources:
            if str(drv.get("type", "angle")) != "translation":
                continue
            plid = drv.get("plid")
            if not hasattr(ctrl, "point_lines") or plid not in ctrl.point_lines:
                continue
            pl = ctrl.point_lines[plid]
            base_s = 0.0
            if hasattr(ctrl, "_point_line_current_s"):
                raw_s = ctrl._point_line_current_s(pl)
                if raw_s is not None:
                    base_s = float(raw_s)
            else:
                raw_s = pl.get("s", 0.0)
                base_s = float(raw_s)
            offset = float(drv.get("value", 0.0) or 0.0)
            translation_targets[int(plid)] = base_s + offset

        body_edges: List[Tuple[int, int, float]] = []
        if hasattr(ctrl, "bodies"):
            for b in ctrl.bodies.values():
                body_edges.extend(b.get("rigid_edges", []))

        def _project_point_to_spline_normal(
            p: Dict[str, Any],
            control_points: list[Dict[str, Any]],
            *,
            closed: bool,
            samples_per_segment: int = 16,
        ) -> None:
            pts = [(float(cp["x"]), float(cp["y"])) for cp in control_points]
            samples = build_spline_samples(pts, samples_per_segment=samples_per_segment, closed=closed)
            if len(samples) < 2:
                return
            px, py = float(p["x"]), float(p["y"])
            best_dist2 = float("inf")
            best = None
            for idx in range(len(samples) - 1):
                x1, y1, _seg1, _t1 = samples[idx]
                x2, y2, _seg2, _t2 = samples[idx + 1]
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
                if dist2 < best_dist2:
                    best_dist2 = dist2
                    best = (cx, cy, vx, vy)
            if best is None:
                return
            cx, cy, tx, ty = best
            t_norm = (tx * tx + ty * ty) ** 0.5
            if t_norm < 1e-12:
                return
            tx /= t_norm
            ty /= t_norm
            nx, ny = -ty, tx
            offset = (px - cx) * nx + (py - cy) * ny
            p["x"] = px - offset * nx
            p["y"] = py - offset * ny

        for _ in range(max(1, int(max_iters))):
            # Drivers first
            for drv in drive_sources:
                if str(drv.get("type", "angle")) == "translation":
                    continue
                piv = drv.get("pivot")
                tip = drv.get("tip")
                if piv is None or tip is None:
                    continue
                piv = int(piv)
                tip = int(tip)
                if piv not in ctrl.points or tip not in ctrl.points:
                    continue
                piv_pt = ctrl.points[piv]
                tip_pt = ctrl.points[tip]
                lock_piv = bool(piv_pt.get("fixed", False))
                lock_tip = bool(tip_pt.get("fixed", False))
                ConstraintSolver.enforce_driver_angle(
                    piv_pt,
                    tip_pt,
                    float(drv.get("rad", 0.0)),
                    lock_piv,
                    lock_tip=lock_tip,
                )

            for plid, target_s in translation_targets.items():
                pl = ctrl.point_lines.get(plid)
                if not pl or not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1))
                i_id = int(pl.get("i", -1))
                j_id = int(pl.get("j", -1))
                if p_id not in ctrl.points or i_id not in ctrl.points or j_id not in ctrl.points:
                    continue
                pp = ctrl.points[p_id]
                pa = ctrl.points[i_id]
                pb = ctrl.points[j_id]
                lock_p = bool(pp.get("fixed", False)) or (p_id in driven_pids)
                lock_a = bool(pa.get("fixed", False)) or (i_id in driven_pids)
                lock_b = bool(pb.get("fixed", False)) or (j_id in driven_pids)
                ConstraintSolver.solve_point_on_line_offset(
                    pp,
                    pa,
                    pb,
                    float(target_s),
                    lock_p,
                    lock_a,
                    lock_b,
                    tol=1e-6,
                )

            # Point-on-line constraints (distance-based)
            if hasattr(ctrl, "point_lines"):
                for plid, pl in ctrl.point_lines.items():
                    if not bool(pl.get("enabled", True)):
                        continue
                    p_id = int(pl.get("p", -1))
                    i_id = int(pl.get("i", -1))
                    j_id = int(pl.get("j", -1))
                    if p_id not in ctrl.points or i_id not in ctrl.points or j_id not in ctrl.points:
                        continue
                    pp = ctrl.points[p_id]
                    pa = ctrl.points[i_id]
                    pb = ctrl.points[j_id]
                    lock_p = bool(pp.get("fixed", False)) or (p_id in driven_pids)
                    lock_a = bool(pa.get("fixed", False)) or (i_id in driven_pids)
                    lock_b = bool(pb.get("fixed", False)) or (j_id in driven_pids)
                    if plid in translation_targets:
                        continue
                    if "s" in pl:
                        ConstraintSolver.solve_point_on_line_offset(
                            pp,
                            pa,
                            pb,
                            float(pl.get("s", 0.0)),
                            lock_p,
                            lock_a,
                            lock_b,
                            tol=1e-6,
                        )
                    else:
                        ConstraintSolver.solve_point_on_line(pp, pa, pb, lock_p, lock_a, lock_b, tol=1e-6)

            if hasattr(ctrl, "point_splines") and hasattr(ctrl, "splines"):
                for ps in ctrl.point_splines.values():
                    if not bool(ps.get("enabled", True)):
                        continue
                    p_id = int(ps.get("p", -1))
                    s_id = int(ps.get("s", -1))
                    if p_id not in ctrl.points or s_id not in ctrl.splines:
                        continue
                    if bool(ctrl.points[p_id].get("fixed", False)) or (p_id in driven_pids):
                        continue
                    spline = ctrl.splines[s_id]
                    cp_ids = [pid for pid in spline.get("points", []) if pid in ctrl.points]
                    if len(cp_ids) < 2:
                        continue
                    control_points = [ctrl.points[pid] for pid in cp_ids]
                    _project_point_to_spline_normal(
                        ctrl.points[p_id],
                        control_points,
                        closed=bool(spline.get("closed", False)),
                    )

            # Rigid-body edges
            for (i, j, L) in body_edges:
                if i not in ctrl.points or j not in ctrl.points:
                    continue
                p1, p2 = ctrl.points[i], ctrl.points[j]
                lock1 = bool(p1.get("fixed", False)) or (i in driven_pids)
                lock2 = bool(p2.get("fixed", False)) or (j in driven_pids)
                ConstraintSolver.solve_length(p1, p2, float(L), lock1, lock2, tol=1e-6)

            # Length constraints
            if hasattr(ctrl, "links"):
                for l in ctrl.links.values():
                    if l.get("ref", False):
                        continue
                    i = int(l.get("i", -1))
                    j = int(l.get("j", -1))
                    if i not in ctrl.points or j not in ctrl.points:
                        continue
                    p1, p2 = ctrl.points[i], ctrl.points[j]
                    lock1 = bool(p1.get("fixed", False)) or (i in driven_pids)
                    lock2 = bool(p2.get("fixed", False)) or (j in driven_pids)
                    ConstraintSolver.solve_length(p1, p2, float(l.get("L", 0.0)), lock1, lock2, tol=1e-6)

    @staticmethod
    def solve(ctrl: Any, max_iters: int = 80, *, distance_only: bool = False) -> Tuple[bool, str]:
        """Solve the current sketch using Exudyn integration.

        If Exudyn is available, this will initialize an Exudyn system and
        then apply a projection-based kinematic solve that supports angle
        constraints (including driver angles), point-on-spline projections,
        and spring loads.
        """
        warning = None
        exu = None
        try:
            exu = _load_exudyn()
        except Exception as exc:
            detail = ExudynKinematicSolver._format_exception(exc)
            warning = f"Exudyn unavailable (module import failed): {detail}"
        if exu is not None:
            try:
                sc = exu.SystemContainer()
                sc.AddSystem()
            except Exception as exc:
                detail = ExudynKinematicSolver._format_exception(exc)
                warning = f"Exudyn unavailable (init failed): {detail}"
                exu = None

        if hasattr(ctrl, "recompute_from_parameters"):
            ctrl.recompute_from_parameters()

        if not hasattr(ctrl, "solve_constraints") and not distance_only:
            msg = "Exudyn initialized; no constraint solver available"
            if warning:
                msg = f"{warning}. Internal solver skipped; no constraint solver available"
            return True, msg

        has_spring = any(str(ld.get("type", "force")).lower() == "spring" for ld in getattr(ctrl, "loads", []))
        try:
            if distance_only:
                ok, msg = ExudynKinematicSolver._validate_point_lines(ctrl)
                if not ok:
                    return False, msg
            if distance_only:
                driven_pids = ExudynKinematicSolver._collect_driven_pids(ctrl)
                if not has_spring:
                    ExudynKinematicSolver._solve_distance_constraints(ctrl, max_iters, driven_pids)
                else:
                    for _ in range(max(1, int(max_iters))):
                        ExudynKinematicSolver._apply_spring_loads(ctrl, driven_pids)
                        ExudynKinematicSolver._solve_distance_constraints(ctrl, 1, driven_pids)
            else:
                if not has_spring:
                    ctrl.solve_constraints(iters=max_iters)
                else:
                    driven_pids = ExudynKinematicSolver._collect_driven_pids(ctrl)
                    for _ in range(max(1, int(max_iters))):
                        ExudynKinematicSolver._apply_spring_loads(ctrl, driven_pids)
                        ctrl.solve_constraints(iters=1)
        except Exception as exc:
            detail = ExudynKinematicSolver._format_exception(exc)
            return False, f"Exudyn solve failed: {detail}"
        if warning:
            if distance_only:
                msg = f"{warning}. Internal distance-constraint solver applied"
            else:
                msg = f"{warning}. Internal projection solver applied"
        else:
            if distance_only:
                msg = "Exudyn initialized; distance-constraint solver applied"
            else:
                msg = "Exudyn initialized; projection solver applied"
        return True, msg
