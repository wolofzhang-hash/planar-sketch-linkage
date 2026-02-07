# -*- coding: utf-8 -*-
"""Exudyn kinematic/quasi-static solver backend.

This module provides a thin integration layer for Exudyn. It currently
initializes an Exudyn system to ensure the runtime is available, then
uses the existing constraint solver as a fallback to keep the UI responsive.

The API is designed to be extended with full Exudyn-based constraint and
load handling (hinges, trajectories, springs, friction, etc.).
"""

from __future__ import annotations

from typing import Any, Tuple, Dict, List
import importlib
import importlib.util
from .solver import ConstraintSolver


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
                base_s = float(ctrl._point_line_current_s(pl) or 0.0)
            else:
                base_s = float(pl.get("s", 0.0))
            offset = float(drv.get("value", 0.0) or 0.0)
            translation_targets[int(plid)] = base_s + offset

        body_edges: List[Tuple[int, int, float]] = []
        if hasattr(ctrl, "bodies"):
            for b in ctrl.bodies.values():
                body_edges.extend(b.get("rigid_edges", []))

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
        exu = _load_exudyn()
        try:
            sc = exu.SystemContainer()
            sc.AddSystem()
        except Exception as exc:
            return False, f"Exudyn initialization failed: {exc}"

        if hasattr(ctrl, "recompute_from_parameters"):
            ctrl.recompute_from_parameters()

        if not hasattr(ctrl, "solve_constraints") and not distance_only:
            return True, "Exudyn initialized; no constraint solver available"

        has_spring = any(str(ld.get("type", "force")).lower() == "spring" for ld in getattr(ctrl, "loads", []))
        try:
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
            return False, f"Exudyn solve failed: {exc}"
        if distance_only:
            return True, "Exudyn initialized; distance-constraint solver applied"
        return True, "Exudyn initialized; projection solver applied"
