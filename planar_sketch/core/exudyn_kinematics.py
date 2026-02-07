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
    def solve(ctrl: Any, max_iters: int = 80) -> Tuple[bool, str]:
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

        if not hasattr(ctrl, "solve_constraints"):
            return True, "Exudyn initialized; no constraint solver available"

        has_spring = any(str(ld.get("type", "force")).lower() == "spring" for ld in getattr(ctrl, "loads", []))
        try:
            if not has_spring:
                ctrl.solve_constraints(iters=max_iters)
            else:
                driven_pids = ExudynKinematicSolver._collect_driven_pids(ctrl)
                for _ in range(max(1, int(max_iters))):
                    ExudynKinematicSolver._apply_spring_loads(ctrl, driven_pids)
                    ctrl.solve_constraints(iters=1)
        except Exception as exc:
            return False, f"Exudyn solve failed: {exc}"
        return True, "Exudyn initialized; projection solver applied"
