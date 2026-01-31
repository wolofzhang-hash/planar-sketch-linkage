# -*- coding: utf-8 -*-
"""Model + controller logic.

Extracted from the monolithic script (PyQt6) into a module so we can extend it.

Additions in this modular version:
- Driver / Output angle configuration (Linkage-style)
- A "drive" mode: set a target input angle and solve, enabling animation and I/O curves
"""

from __future__ import annotations

import json
import math
from typing import Dict, Any, Optional, List, Tuple, Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QColor
from PyQt6.QtWidgets import QGraphicsScene, QMenu, QInputDialog

import numpy as np

import numpy as np

from .commands import Command, CommandStack
from .geometry import clamp_angle_rad, angle_between, build_spline_samples, closest_point_on_samples
from .solver import ConstraintSolver
from .constraints_registry import ConstraintRegistry
from .parameters import ParameterRegistry
from .scipy_kinematics import SciPyKinematicSolver
from ..ui.items import TextMarker, PointItem, LinkItem, AngleItem, CoincideItem, PointLineItem, SplineItem, PointSplineItem, TrajectoryItem, ForceArrowItem
from ..utils.constants import BODY_COLORS


class SketchController:
    def __init__(self, scene: QGraphicsScene, win: "MainWindow"):
        self.scene = scene
        self.win = win
        # Global parameters used by expression fields (x_expr / L_expr / deg_expr / ...)
        self.parameters = ParameterRegistry()
        self.points: Dict[int, Dict[str, Any]] = {}
        self.links: Dict[int, Dict[str, Any]] = {}
        self.angles: Dict[int, Dict[str, Any]] = {}
        self.splines: Dict[int, Dict[str, Any]] = {}
        self.bodies: Dict[int, Dict[str, Any]] = {}
        self.coincides: Dict[int, Dict[str, Any]] = {}
        # Point-on-line constraints: {id: {p,i,j,hidden,enabled,over}}
        self.point_lines: Dict[int, Dict[str, Any]] = {}
        # Point-on-spline constraints: {id: {p,s,hidden,enabled,over}}
        self.point_splines: Dict[int, Dict[str, Any]] = {}

        # Parameters + expressions
        self.parameters = ParameterRegistry()
        self.constraint_registry = ConstraintRegistry(self)
        self._next_pid = 0; self._next_lid = 0; self._next_aid = 0; self._next_sid = 0; self._next_bid = 0; self._next_cid = 0; self._next_plid = 0; self._next_psid = 0
        self.selected_point_ids: set = set()
        self.selected_point_id: Optional[int] = None
        self.selected_link_id: Optional[int] = None
        self.selected_angle_id: Optional[int] = None
        self.selected_spline_id: Optional[int] = None
        self.selected_body_id: Optional[int] = None
        self.selected_coincide_id: Optional[int] = None
        self.selected_point_line_id: Optional[int] = None
        self.selected_point_spline_id: Optional[int] = None

        self.show_point_markers = True
        self.show_dim_markers = True

        self.show_points_geometry = True
        self.show_links_geometry = True
        self.show_angles_geometry = True
        self.show_splines_geometry = True
        self.show_body_coloring = True
        self.show_trajectories = False
        self.show_load_arrows = True

        self.mode = "Idle"
        self._line_sel: List[int] = []
        self._co_master: Optional[int] = None
        self._pol_master: Optional[int] = None
        self._pol_line_sel: List[int] = []
        self._pos_master: Optional[int] = None
        self.panel: Optional["SketchPanel"] = None
        self.stack = CommandStack(on_change=self.win.update_undo_redo_actions)
        self._drag_active = False
        self._drag_pid: Optional[int] = None
        self._drag_before: Optional[Dict[int, Tuple[float, float]]] = None

        # --- Linkage-style simulation configuration ---
        # Driver: either a world-angle of a vector (pivot->tip) or a joint angle (i-j-k).
        # type: "vector" or "joint"
        self.driver: Dict[str, Any] = {
            "enabled": False,
            "type": "vector",
            "pivot": None, "tip": None,  # for vector
            "i": None, "j": None, "k": None,  # for joint
            "rad": 0.0,
        }
        # Output: measured angle of (pivot -> tip) relative to world +X.
        self.output: Dict[str, Any] = {"enabled": False, "pivot": None, "tip": None, "rad": 0.0}
        # Extra measurements: a list of {type,name,...} items.
        self.measures: List[Dict[str, Any]] = []
        # Load measurements: a list of {type,name,...} items.
        self.load_measures: List[Dict[str, Any]] = []
        # Quasi-static loads: list of {type,pid,fx,fy,mz}
        self.loads: List[Dict[str, Any]] = []
        # Display items for load arrows.
        self._load_arrow_items: List[ForceArrowItem] = []
        self._last_joint_loads: List[Dict[str, Any]] = []
        self._last_quasistatic_summary: Dict[str, Any] = {}
        # Pose snapshots for "reset to initial".
        self._pose_initial: Optional[Dict[int, Tuple[float, float]]] = None
        self._pose_last_sim_start: Optional[Dict[int, Tuple[float, float]]] = None

        # Simulation "relative zero" (0° == pose at Play-start)
        self._sim_zero_input_rad: Optional[float] = None
        self._sim_zero_output_rad: Optional[float] = None
        self._sim_zero_meas_deg: Dict[str, float] = {}

    def status_text(self) -> str:
        if self.mode == "CreateLine":
            return "Create Line: select 2 points (LMB)."
        if self.mode == "Coincide":
            if self._co_master is None:
                return "Coincide: select the point to constrain."
            return f"Coincide: select a point/line/spline for P{int(self._co_master)}."
        if self.mode == "PointOnLine":
            if self._pol_master is None:
                return "Point On Line: select the point (RMB on point -> Point On Line...)."
            if len(self._pol_line_sel) == 0:
                return f"Point On Line: select line point #1 (for P{int(self._pol_master)})."
            if len(self._pol_line_sel) == 1:
                return f"Point On Line: select line point #2 (for P{int(self._pol_master)})."
            return "Point On Line: selecting..."
        if self.mode == "PointOnSpline":
            if self._pos_master is None:
                return "Point On Spline: select the point (RMB on point -> Point On Spline...)."
            return f"Point On Spline: select a spline for P{int(self._pos_master)}."
        return "Idle | BoxSelect: drag LMB on empty. Ctrl+Box toggles. Ctrl+Click toggles points."

    def update_status(self):
        self.win.statusBar().showMessage(self.status_text())

    def point_body(self, pid: int) -> Optional[int]:
        for bid, b in self.bodies.items():
            if pid in b.get("points", []):
                return bid
        return None

    def is_point_effectively_hidden(self, pid: int) -> bool:
        if pid not in self.points: return True
        if bool(self.points[pid].get("hidden", False)): return True
        bid = self.point_body(pid)
        if bid is not None and bool(self.bodies[bid].get("hidden", False)): return True
        return False

    def snapshot_points(self) -> Dict[int, Tuple[float, float]]:
        return {pid: (p["x"], p["y"]) for pid, p in self.points.items()}

    def apply_points_snapshot(self, snap: Dict[int, Tuple[float, float]]):
        for pid, (x, y) in snap.items():
            if pid in self.points:
                self.points[pid]["x"] = float(x); self.points[pid]["y"] = float(y)

    def snapshot_model(self) -> Dict[str, Any]:
        return self.to_dict()

    def apply_model_snapshot(self, data: Dict[str, Any]):
        self.load_dict(data, clear_undo=False)

    def compute_body_rigid_edges(self, point_ids: List[int]) -> List[Tuple[int, int, float]]:
        pts = [pid for pid in point_ids if pid in self.points]
        if len(pts) < 2:
            return []
        edges: List[Tuple[int, int, float]] = []
        for idx, i in enumerate(pts):
            pi = self.points[i]
            for j in pts[idx + 1:]:
                pj = self.points[j]
                L = math.hypot(pj["x"] - pi["x"], pj["y"] - pi["y"])
                edges.append((i, j, L))
        return edges

    def solve_constraints(self, iters: int = 60, drag_pid: Optional[int] = None):
        """Solve geometric constraints (interactive PBD backend).

        Notes:
        - Called frequently (e.g. during point dragging).
        - Must keep the dragged point locked via drag_pid to avoid fighting user input.
        - Expression-bound numeric fields are recomputed before solving.
        """
        # Update any expression-bound values before solving.
        self.recompute_from_parameters()

        # Reset over-constraint flags
        for l in self.links.values():
            l["over"] = False
        for a in self.angles.values():
            a["over"] = False
        for c in self.coincides.values():
            c["over"] = False

        for pl in self.point_lines.values():
            pl["over"] = False
        for ps in self.point_splines.values():
            ps["over"] = False

        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))

        driven_pids: set[int] = set()
        driver_type: Optional[str] = None
        driver_pivot: Optional[int] = None
        driver_tip: Optional[int] = None
        driver_i: Optional[int] = None
        driver_j: Optional[int] = None
        driver_k: Optional[int] = None
        if self.driver.get("enabled"):
            driver_type = str(self.driver.get("type", "vector"))
            if driver_type == "joint" and self.driver.get("i") is not None and self.driver.get("j") is not None and self.driver.get("k") is not None:
                driver_i = int(self.driver["i"])
                driver_j = int(self.driver["j"])
                driver_k = int(self.driver["k"])
                driven_pids = {driver_i, driver_k}
            elif self.driver.get("pivot") is not None and self.driver.get("tip") is not None:
                driver_pivot = int(self.driver["pivot"])
                driver_tip = int(self.driver["tip"])
                driven_pids = {driver_tip}
        elif self.output.get("enabled") and self.output.get("pivot") is not None and self.output.get("tip") is not None:
            driver_type = "output"
            driver_pivot = int(self.output["pivot"])
            driver_tip = int(self.output["tip"])
            driven_pids = {driver_tip}

        # Allow editing lengths that belong to the active driver (avoid false OVER).
        driver_length_pairs: set[frozenset[int]] = set()
        if driver_type == "joint" and driver_i is not None and driver_j is not None and driver_k is not None:
            driver_length_pairs.add(frozenset({driver_i, driver_j}))
            driver_length_pairs.add(frozenset({driver_j, driver_k}))
        elif driver_type in ("vector", "output") and driver_pivot is not None and driver_tip is not None:
            driver_length_pairs.add(frozenset({driver_pivot, driver_tip}))

        # PBD-style iterations
        for _ in range(max(1, int(iters))):
            # (1) Hard driver first
            if driver_type == "joint" and driver_i is not None and driver_j is not None and driver_k is not None:
                if drag_pid in (driver_i, driver_j, driver_k):
                    pass
                elif driver_i in self.points and driver_j in self.points and driver_k in self.points:
                    pi = self.points[driver_i]
                    pj = self.points[driver_j]
                    pk = self.points[driver_k]
                    lock_i = bool(pi.get("fixed", False)) or (drag_pid == driver_i)
                    lock_j = bool(pj.get("fixed", False)) or (drag_pid == driver_j)
                    lock_k = bool(pk.get("fixed", False)) or (drag_pid == driver_k)
                    ConstraintSolver.enforce_driver_joint_angle(
                        pi, pj, pk,
                        float(self.driver.get("rad", 0.0)),
                        lock_i, lock_j, lock_k,
                    )
            elif driver_pivot is not None and driver_tip is not None:
                if drag_pid in (driver_pivot, driver_tip):
                    pass
                elif driver_pivot in self.points and driver_tip in self.points:
                    piv = self.points[driver_pivot]
                    tip = self.points[driver_tip]
                    lock_piv = bool(piv.get("fixed", False)) or (drag_pid == driver_pivot)
                    lock_tip = bool(tip.get("fixed", False)) or (drag_pid == driver_tip)
                    target = self.driver.get("rad", 0.0) if driver_type == "vector" else self.output.get("rad", 0.0)
                    ConstraintSolver.enforce_driver_angle(
                        piv, tip,
                        float(target),
                        lock_piv,
                        lock_tip=lock_tip,
                    )

            # (2) Coincide constraints
            for c in self.coincides.values():
                if not bool(c.get("enabled", True)):
                    continue
                a = int(c.get("a", -1)); b = int(c.get("b", -1))
                if a not in self.points or b not in self.points:
                    continue
                pa = self.points[a]; pb = self.points[b]
                ax, ay = float(pa["x"]), float(pa["y"])
                bx, by = float(pb["x"]), float(pb["y"])
                lock_a = bool(pa.get("fixed", False)) or (drag_pid == a)
                lock_b = bool(pb.get("fixed", False)) or (drag_pid == b)

                if lock_a and lock_b:
                    if (ax - bx) * (ax - bx) + (ay - by) * (ay - by) > 1e-6:
                        c["over"] = True
                    continue

                if lock_a and (not lock_b):
                    pb["x"], pb["y"] = ax, ay
                elif lock_b and (not lock_a):
                    pa["x"], pa["y"] = bx, by
                else:
                    mx = 0.5 * (ax + bx)
                    my = 0.5 * (ay + by)
                    pa["x"], pa["y"] = mx, my
                    pb["x"], pb["y"] = mx, my

            # (3) Point-on-line constraints
            for pl in self.point_lines.values():
                if not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1)); i_id = int(pl.get("i", -1)); j_id = int(pl.get("j", -1))
                if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                    continue
                pp = self.points[p_id]; pa = self.points[i_id]; pb = self.points[j_id]
                lock_p = bool(pp.get("fixed", False)) or (drag_pid == p_id) or (p_id in driven_pids)
                lock_a = bool(pa.get("fixed", False)) or (drag_pid == i_id) or (i_id in driven_pids)
                lock_b = bool(pb.get("fixed", False)) or (drag_pid == j_id) or (j_id in driven_pids)
                ok = ConstraintSolver.solve_point_on_line(pp, pa, pb, lock_p, lock_a, lock_b, tol=1e-6)
                if not ok:
                    pl["over"] = True

            # (3b) Point-on-spline constraints
            for ps in self.point_splines.values():
                if not bool(ps.get("enabled", True)):
                    continue
                p_id = int(ps.get("p", -1)); s_id = int(ps.get("s", -1))
                if p_id not in self.points or s_id not in self.splines:
                    continue
                spline = self.splines[s_id]
                cp_ids = [pid for pid in spline.get("points", []) if pid in self.points]
                if len(cp_ids) < 2:
                    continue
                pp = self.points[p_id]
                cps = [self.points[cid] for cid in cp_ids]
                lock_p = bool(pp.get("fixed", False)) or (drag_pid == p_id) or (p_id in driven_pids)
                lock_controls = []
                for cid in cp_ids:
                    lock_controls.append(bool(self.points[cid].get("fixed", False)) or (drag_pid == cid) or (cid in driven_pids))
                ok = ConstraintSolver.solve_point_on_spline(pp, cps, lock_p, lock_controls, tol=1e-6)
                if not ok:
                    ps["over"] = True

            # (3) Rigid-body edges
            for (i, j, L) in body_edges:
                if i not in self.points or j not in self.points:
                    continue
                p1, p2 = self.points[i], self.points[j]
                pair = frozenset({i, j})
                allow_move_driven = (pair in driver_length_pairs)
                lock1 = bool(p1.get("fixed", False)) or (drag_pid == i) or ((i in driven_pids) and (not allow_move_driven))
                lock2 = bool(p2.get("fixed", False)) or (drag_pid == j) or ((j in driven_pids) and (not allow_move_driven))
                ConstraintSolver.solve_length(p1, p2, float(L), lock1, lock2, tol=1e-6)

            # (4) Length constraints
            for lid, l in self.links.items():
                if l.get("ref", False):
                    continue
                i, j = l["i"], l["j"]
                if i not in self.points or j not in self.points:
                    continue
                p1, p2 = self.points[i], self.points[j]
                pair = frozenset({i, j})
                allow_move_driven = (pair in driver_length_pairs)
                lock1 = bool(p1.get("fixed", False)) or (drag_pid == i) or ((i in driven_pids) and (not allow_move_driven))
                lock2 = bool(p2.get("fixed", False)) or (drag_pid == j) or ((j in driven_pids) and (not allow_move_driven))
                ok = ConstraintSolver.solve_length(p1, p2, float(l["L"]), lock1, lock2, tol=1e-6)
                if not ok:
                    l["over"] = True

            # (5) Angle constraints
            for aid, a in self.angles.items():
                if not a.get("enabled", True):
                    continue
                i, j, k = a["i"], a["j"], a["k"]
                if i not in self.points or j not in self.points or k not in self.points:
                    continue
                pi, pj, pk = self.points[i], self.points[j], self.points[k]
                lock_i = bool(pi.get("fixed", False)) or (drag_pid == i) or (i in driven_pids)
                lock_j = bool(pj.get("fixed", False)) or (drag_pid == j) or (j in driven_pids)
                lock_k = bool(pk.get("fixed", False)) or (drag_pid == k) or (k in driven_pids)
                ok = ConstraintSolver.solve_angle(pi, pj, pk, float(a["rad"]), lock_i, lock_j, lock_k, tol=1e-5)
                if not ok:
                    a["over"] = True

        # Post-check: fixed-fixed constraint violation should be flagged as OVER.
        for lid, l in self.links.items():
            if l.get("ref", False):
                continue
            i, j = l["i"], l["j"]
            if i not in self.points or j not in self.points:
                continue
            p1, p2 = self.points[i], self.points[j]
            if bool(p1.get("fixed", False)) and bool(p2.get("fixed", False)):
                d = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                if abs(d - float(l["L"])) > 1e-6:
                    l["over"] = True

        for aid, a in self.angles.items():
            if not a.get("enabled", True):
                continue
            i, j, k = a["i"], a["j"], a["k"]
            if i not in self.points or j not in self.points or k not in self.points:
                continue
            pi, pj, pk = self.points[i], self.points[j], self.points[k]
            if bool(pi.get("fixed", False)) and bool(pk.get("fixed", False)):
                v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
                v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
                if math.hypot(v1x, v1y) > 1e-9 and math.hypot(v2x, v2y) > 1e-9:
                    cur = angle_between(v1x, v1y, v2x, v2y)
                    err = abs(clamp_angle_rad(cur - float(a["rad"])))
                    if err > 1e-5:
                        a["over"] = True

        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = int(pl.get("p", -1)); i_id = int(pl.get("i", -1)); j_id = int(pl.get("j", -1))
            if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                continue
            pp = self.points[p_id]; pa = self.points[i_id]; pb = self.points[j_id]
            if bool(pp.get("fixed", False)) and bool(pa.get("fixed", False)) and bool(pb.get("fixed", False)):
                ax, ay = float(pa["x"]), float(pa["y"])
                bx, by = float(pb["x"]), float(pb["y"])
                px, py = float(pp["x"]), float(pp["y"])
                abx, aby = bx - ax, by - ay
                denom = (abx * abx + aby * aby) ** 0.5
                if denom > 1e-9:
                    dist = abs((px - ax) * (-aby) + (py - ay) * (abx)) / denom
                    if dist > 1e-6:
                        pl["over"] = True

        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = int(ps.get("p", -1)); s_id = int(ps.get("s", -1))
            if p_id not in self.points or s_id not in self.splines:
                continue
            spline = self.splines[s_id]
            cp_ids = [pid for pid in spline.get("points", []) if pid in self.points]
            if len(cp_ids) < 2:
                continue
            if bool(self.points[p_id].get("fixed", False)) and all(bool(self.points[cid].get("fixed", False)) for cid in cp_ids):
                pts = [(self.points[cid]["x"], self.points[cid]["y"]) for cid in cp_ids]
                samples = build_spline_samples(pts, samples_per_segment=16)
                if len(samples) >= 2:
                    px, py = float(self.points[p_id]["x"]), float(self.points[p_id]["y"])
                    _cx, _cy, _seg_idx, _t_seg, dist2 = closest_point_on_samples(px, py, samples)
                    if dist2 > 1e-6:
                        ps["over"] = True


    def max_constraint_error(self) -> tuple[float, dict[str, float]]:
        """Return max constraint residual (used to detect infeasible sweep steps)."""
        # Length-like errors (links + rigid-body edges)
        max_len = 0.0
        # Angle errors
        max_ang = 0.0
        # Coincide errors
        max_coin = 0.0
        # Point-on-line errors
        max_pl = 0.0
        # Point-on-spline errors
        max_ps = 0.0

        # Rigid-body edges
        body_edges = []
        for b in self.bodies.values():
            body_edges.extend(b.get('rigid_edges', []))
        for (i, j, L) in body_edges:
            if i in self.points and j in self.points:
                p1, p2 = self.points[i], self.points[j]
                d = math.hypot(p2['x'] - p1['x'], p2['y'] - p1['y'])
                max_len = max(max_len, abs(d - float(L)))

        # Length constraints
        for l in self.links.values():
            if bool(l.get('ref', False)):
                continue
            i, j = int(l.get('i', -1)), int(l.get('j', -1))
            if i in self.points and j in self.points:
                p1, p2 = self.points[i], self.points[j]
                d = math.hypot(p2['x'] - p1['x'], p2['y'] - p1['y'])
                max_len = max(max_len, abs(d - float(l.get('L', 0.0))))

        # Angle constraints
        for a in self.angles.values():
            if not bool(a.get('enabled', True)):
                continue
            i, j, k = int(a.get('i', -1)), int(a.get('j', -1)), int(a.get('k', -1))
            if i in self.points and j in self.points and k in self.points:
                pi, pj, pk = self.points[i], self.points[j], self.points[k]
                v1x, v1y = pi['x'] - pj['x'], pi['y'] - pj['y']
                v2x, v2y = pk['x'] - pj['x'], pk['y'] - pj['y']
                if math.hypot(v1x, v1y) > 1e-12 and math.hypot(v2x, v2y) > 1e-12:
                    cur = angle_between(v1x, v1y, v2x, v2y)
                    err = abs(clamp_angle_rad(cur - float(a.get('rad', 0.0))))
                    max_ang = max(max_ang, err)

        # Coincide constraints
        for c in self.coincides.values():
            if not bool(c.get('enabled', True)):
                continue
            a_id, b_id = int(c.get('a', -1)), int(c.get('b', -1))
            if a_id in self.points and b_id in self.points:
                pa, pb = self.points[a_id], self.points[b_id]
                max_coin = max(max_coin, math.hypot(pa['x'] - pb['x'], pa['y'] - pb['y']))

        # Point-on-line constraints
        for pl in self.point_lines.values():
            if not bool(pl.get('enabled', True)):
                continue
            p_id, i_id, j_id = int(pl.get('p', -1)), int(pl.get('i', -1)), int(pl.get('j', -1))
            if p_id in self.points and i_id in self.points and j_id in self.points:
                pp, pa, pb = self.points[p_id], self.points[i_id], self.points[j_id]
                ax, ay = float(pa['x']), float(pa['y'])
                bx, by = float(pb['x']), float(pb['y'])
                px, py = float(pp['x']), float(pp['y'])
                abx, aby = bx - ax, by - ay
                denom = math.hypot(abx, aby)
                if denom > 1e-12:
                    dist = abs((px - ax) * (-aby) + (py - ay) * (abx)) / denom
                    max_pl = max(max_pl, dist)

        # Point-on-spline constraints
        for ps in self.point_splines.values():
            if not bool(ps.get('enabled', True)):
                continue
            p_id = int(ps.get('p', -1)); s_id = int(ps.get('s', -1))
            if p_id not in self.points or s_id not in self.splines:
                continue
            cp_ids = [pid for pid in self.splines[s_id].get("points", []) if pid in self.points]
            if len(cp_ids) < 2:
                continue
            pts = [(self.points[cid]["x"], self.points[cid]["y"]) for cid in cp_ids]
            samples = build_spline_samples(pts, samples_per_segment=16)
            if len(samples) < 2:
                continue
            px, py = float(self.points[p_id]["x"]), float(self.points[p_id]["y"])
            _cx, _cy, _seg_idx, _t_seg, dist2 = closest_point_on_samples(px, py, samples)
            max_ps = max(max_ps, math.sqrt(dist2))

        max_err = max(max_len, max_ang, max_coin, max_pl, max_ps)
        return max_err, {'length': max_len, 'angle': max_ang, 'coincide': max_coin, 'point_line': max_pl, 'point_spline': max_ps}
    def recompute_from_parameters(self):
        """Recompute all numeric fields that are backed by expressions.

        Notes:
        - This method is safe to call frequently (e.g., before solving).
        - On evaluation failure, we keep the previous numeric value and set
          an "expr_error" flag (and a short message).
        """

        # Points: x_expr / y_expr
        for pid, p in self.points.items():
            for key_num, key_expr in (("x", "x_expr"), ("y", "y_expr")):
                expr = p.get(key_expr, "")
                if not expr:
                    p.pop(f"{key_expr}_error", None)
                    p.pop(f"{key_expr}_error_msg", None)
                    continue
                val, err = self.parameters.eval_expr(str(expr))
                if err is None and val is not None:
                    p[key_num] = float(val)
                    p.pop(f"{key_expr}_error", None)
                    p.pop(f"{key_expr}_error_msg", None)
                else:
                    p[f"{key_expr}_error"] = True
                    p[f"{key_expr}_error_msg"] = str(err)

        # Links: L_expr (only when not in Reference mode)
        for lid, l in self.links.items():
            expr = l.get("L_expr", "")
            if not expr or bool(l.get("ref", False)):
                l.pop("L_expr_error", None)
                l.pop("L_expr_error_msg", None)
                continue
            val, err = self.parameters.eval_expr(str(expr))
            if err is None and val is not None:
                l["L"] = float(val)
                l.pop("L_expr_error", None)
                l.pop("L_expr_error_msg", None)
            else:
                l["L_expr_error"] = True
                l["L_expr_error_msg"] = str(err)

        # Angles: deg_expr
        for aid, a in self.angles.items():
            expr = a.get("deg_expr", "")
            if not expr:
                a.pop("deg_expr_error", None)
                a.pop("deg_expr_error_msg", None)
                continue
            val, err = self.parameters.eval_expr(str(expr))
            if err is None and val is not None:
                a["deg"] = float(val)
                a.pop("deg_expr_error", None)
                a.pop("deg_expr_error_msg", None)
            else:
                a["deg_expr_error"] = True
                a["deg_expr_error_msg"] = str(err)

    # --- Parameter commands (Undo/Redo) ---
    def cmd_set_param(self, name: str, value: float):
        name = str(name).strip()
        before = dict(self.parameters.params)

        def do():
            self.parameters.set_param(name, float(value))
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        def undo():
            self.parameters.params.clear()
            self.parameters.params.update(before)
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        self.stack.push(Command(do=do, undo=undo, desc=f"Set Param {name}"))

    def cmd_delete_param(self, name: str):
        name = str(name).strip()
        before = dict(self.parameters.params)

        def do():
            self.parameters.delete_param(name)
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        def undo():
            self.parameters.params.clear()
            self.parameters.params.update(before)
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        self.stack.push(Command(do=do, undo=undo, desc=f"Delete Param {name}"))

    def cmd_rename_param(self, old: str, new: str):
        old = str(old).strip(); new = str(new).strip()
        before = dict(self.parameters.params)

        def do():
            self.parameters.rename_param(old, new)
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        def undo():
            self.parameters.params.clear()
            self.parameters.params.update(before)
            self.recompute_from_parameters()
            self.solve_constraints(iters=30)
            self.update_graphics()
            if self.panel:
                self.panel.defer_refresh_all(keep_selection=True)

        self.stack.push(Command(do=do, undo=undo, desc=f"Rename Param {old}->{new}"))

    def cmd_set_point_expr(self, pid: int, x_text: str, y_text: str):
        if pid not in self.points:
            return
        p = self.points[pid]
        before = {k: p.get(k) for k in ("x", "y", "x_expr", "y_expr")}

        def apply_text(key_num: str, key_expr: str, text: str):
            text = (text or "").strip()
            # If numeric, clear expr. Else store expr and compute if possible.
            try:
                v = float(text)
                p[key_num] = v
                p[key_expr] = ""
                p.pop(f"{key_expr}_error", None)
                p.pop(f"{key_expr}_error_msg", None)
            except Exception:
                p[key_expr] = text
                val, err = self.parameters.eval_expr(text)
                if err is None and val is not None:
                    p[key_num] = float(val)
                    p.pop(f"{key_expr}_error", None)
                    p.pop(f"{key_expr}_error_msg", None)
                else:
                    p[f"{key_expr}_error"] = True
                    p[f"{key_expr}_error_msg"] = str(err)

        def do():
            apply_text("x", "x_expr", x_text)
            apply_text("y", "y_expr", y_text)
            self.solve_constraints(iters=30)
            self.update_graphics()

        def undo():
            p["x"] = before.get("x", p["x"])
            p["y"] = before.get("y", p["y"])
            p["x_expr"] = before.get("x_expr", "") or ""
            p["y_expr"] = before.get("y_expr", "") or ""
            self.solve_constraints(iters=30)
            self.update_graphics()

        self.stack.push(Command(do=do, undo=undo, desc=f"Set Point Expr P{pid}"))

    def cmd_set_link_expr(self, lid: int, L_text: str):
        if lid not in self.links:
            return
        l = self.links[lid]
        before = {k: l.get(k) for k in ("L", "L_expr")}

        def do():
            text = (L_text or "").strip()
            try:
                v = float(text)
                l["L"] = v
                l["L_expr"] = ""
                l.pop("L_expr_error", None)
                l.pop("L_expr_error_msg", None)
            except Exception:
                l["L_expr"] = text
                val, err = self.parameters.eval_expr(text)
                if err is None and val is not None:
                    l["L"] = float(val)
                    l.pop("L_expr_error", None)
                    l.pop("L_expr_error_msg", None)
                else:
                    l["L_expr_error"] = True
                    l["L_expr_error_msg"] = str(err)
            self.solve_constraints(iters=30)
            self.update_graphics()

        def undo():
            l["L"] = before.get("L", l["L"])
            l["L_expr"] = before.get("L_expr", "") or ""
            self.solve_constraints(iters=30)
            self.update_graphics()

        self.stack.push(Command(do=do, undo=undo, desc=f"Set Link Expr L{lid}"))

    def cmd_set_angle_expr(self, aid: int, deg_text: str):
        if aid not in self.angles:
            return
        a = self.angles[aid]
        before = {k: a.get(k) for k in ("deg", "deg_expr")}

        def do():
            text = (deg_text or "").strip()
            try:
                v = float(text)
                a["deg"] = v
                a["deg_expr"] = ""
                a.pop("deg_expr_error", None)
                a.pop("deg_expr_error_msg", None)
            except Exception:
                a["deg_expr"] = text
                val, err = self.parameters.eval_expr(text)
                if err is None and val is not None:
                    a["deg"] = float(val)
                    a.pop("deg_expr_error", None)
                    a.pop("deg_expr_error_msg", None)
                else:
                    a["deg_expr_error"] = True
                    a["deg_expr_error_msg"] = str(err)
            self.solve_constraints(iters=30)
            self.update_graphics()

        def undo():
            a["deg"] = before.get("deg", a["deg"])
            a["deg_expr"] = before.get("deg_expr", "") or ""
            self.solve_constraints(iters=30)
            self.update_graphics()

        self.stack.push(Command(do=do, undo=undo, desc=f"Set Angle Expr A{aid}"))


    def _check_over_flags_only(self):
        """Update ONLY the 'over' flags based on the current pose.

        This function must NOT change any point positions.
        """
        # Reset all flags
        for l in self.links.values():
            l["over"] = False
        for a in self.angles.values():
            a["over"] = False
        for c in self.coincides.values():
            c["over"] = False
        for pl in self.point_lines.values():
            pl["over"] = False
        for ps in self.point_splines.values():
            ps["over"] = False

        # Coincide fixed-fixed
        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1)); b = int(c.get("b", -1))
            if a not in self.points or b not in self.points:
                continue
            pa = self.points[a]; pb = self.points[b]
            if bool(pa.get("fixed", False)) and bool(pb.get("fixed", False)):
                dx = float(pa["x"]) - float(pb["x"])
                dy = float(pa["y"]) - float(pb["y"])
                if dx*dx + dy*dy > 1e-10:
                    c["over"] = True

        # Length fixed-fixed
        for l in self.links.values():
            if bool(l.get("ref", False)):
                continue
            i = int(l.get("i", -1)); j = int(l.get("j", -1))
            if i not in self.points or j not in self.points:
                continue
            p1 = self.points[i]; p2 = self.points[j]
            if bool(p1.get("fixed", False)) and bool(p2.get("fixed", False)):
                d = math.hypot(float(p2["x"]) - float(p1["x"]), float(p2["y"]) - float(p1["y"]))
                if abs(d - float(l.get("L", 0.0))) > 1e-6:
                    l["over"] = True

        # Angle fixed-fixed (i and k fixed)
        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i = int(a.get("i", -1)); j = int(a.get("j", -1)); k = int(a.get("k", -1))
            if i not in self.points or j not in self.points or k not in self.points:
                continue
            pi = self.points[i]; pj = self.points[j]; pk = self.points[k]
            if bool(pi.get("fixed", False)) and bool(pk.get("fixed", False)):
                v1x, v1y = float(pi["x"]) - float(pj["x"]), float(pi["y"]) - float(pj["y"])
                v2x, v2y = float(pk["x"]) - float(pj["x"]), float(pk["y"]) - float(pj["y"])
                if math.hypot(v1x, v1y) > 1e-9 and math.hypot(v2x, v2y) > 1e-9:
                    cur = angle_between(v1x, v1y, v2x, v2y)
                    err = abs(clamp_angle_rad(cur - float(a.get("rad", 0.0))))
                    if err > 1e-5:
                        a["over"] = True

        # Point-on-line fixed-fixed-fixed
        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            pid = int(pl.get("p", -1)); i = int(pl.get("i", -1)); j = int(pl.get("j", -1))
            if pid not in self.points or i not in self.points or j not in self.points:
                continue
            pp = self.points[pid]; pa = self.points[i]; pb = self.points[j]
            if bool(pp.get("fixed", False)) and bool(pa.get("fixed", False)) and bool(pb.get("fixed", False)):
                ax, ay = float(pa["x"]), float(pa["y"])
                bx, by = float(pb["x"]), float(pb["y"])
                px, py = float(pp["x"]), float(pp["y"])
                vx, vy = (bx - ax), (by - ay)
                denom = math.hypot(vx, vy)
                if denom > 1e-9:
                    err = abs((px - ax) * vy - (py - ay) * vx) / denom
                    if err > 1e-5:
                        pl["over"] = True

        # Point-on-spline fixed-fixed
        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            pid = int(ps.get("p", -1)); sid = int(ps.get("s", -1))
            if pid not in self.points or sid not in self.splines:
                continue
            cp_ids = [pid for pid in self.splines[sid].get("points", []) if pid in self.points]
            if len(cp_ids) < 2:
                continue
            if bool(self.points[pid].get("fixed", False)) and all(bool(self.points[cid].get("fixed", False)) for cid in cp_ids):
                pts = [(self.points[cid]["x"], self.points[cid]["y"]) for cid in cp_ids]
                samples = build_spline_samples(pts, samples_per_segment=16)
                if len(samples) < 2:
                    continue
                px, py = float(self.points[pid]["x"]), float(self.points[pid]["y"])
                _cx, _cy, _seg_idx, _t_seg, dist2 = closest_point_on_samples(px, py, samples)
                if dist2 > 1e-5:
                    ps["over"] = True

    def solve_constraints_scipy(self, max_nfev: int = 250) -> tuple[bool, str]:
        """Solve using SciPy backend (accurate, warm-started)."""
        self.recompute_from_parameters()
        try:
            ok, msg, _cost = SciPyKinematicSolver.solve(self, max_nfev=int(max_nfev))
        except Exception as e:
            return False, str(e)
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()
        return bool(ok), str(msg)

    def solve_current_scipy(self):
        """Convenience action: run SciPy solver once and show a toast/message."""
        ok, msg = self.solve_constraints_scipy(max_nfev=300)
        if hasattr(self.win, 'statusBar'):
            self.win.statusBar().showMessage(("SciPy solve OK" if ok else "SciPy solve FAILED") + f": {msg}")

    def drive_to_deg_scipy(self, deg: float, max_nfev: int = 250) -> tuple[bool, str]:
        """Drive to a relative input angle (deg) and solve with SciPy.

        Returns (ok, message).
        """
        if not self.driver.get("enabled") and not self.output.get("enabled"):
            return False, "Driver or output not set"
        if self.driver.get("enabled"):
            if self._sim_zero_input_rad is not None:
                target = float(self._sim_zero_input_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            self.driver["rad"] = float(target)
        else:
            if self._sim_zero_output_rad is not None:
                target = float(self._sim_zero_output_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            self.output["rad"] = float(target)
        return self.solve_constraints_scipy(max_nfev=max_nfev)

    def _create_point(self, pid: int, x: float, y: float, fixed: bool, hidden: bool, traj_enabled: bool = False):
        self.points[pid] = {
            "x": float(x),
            "y": float(y),
            "fixed": bool(fixed),
            "hidden": bool(hidden),
            "traj": bool(traj_enabled),
        }
        traj = TrajectoryItem(pid, self)
        self.points[pid]["traj_item"] = traj
        self.scene.addItem(traj)
        it = PointItem(pid, self)
        it._internal = True
        it.setPos(float(x), float(y))
        it._internal = False
        self.points[pid]["item"] = it
        self.scene.addItem(it)
        mk = TextMarker(f"P{pid}")
        self.points[pid]["marker"] = mk
        self.scene.addItem(mk)
        cmark = TextMarker("△")
        self.points[pid]["constraint_marker"] = cmark
        self.scene.addItem(cmark)
        dmark = TextMarker("↻")
        self.points[pid]["driver_marker"] = dmark
        self.scene.addItem(dmark)
        omark = TextMarker("OUT")
        self.points[pid]["output_marker"] = omark
        self.scene.addItem(omark)
        tmark = TextMarker("τ")
        self.points[pid]["output_torque_marker"] = tmark
        self.scene.addItem(tmark)

    def _remove_point(self, pid: int):
        if pid not in self.points: return
        to_del_l = [lid for lid, l in self.links.items() if l["i"] == pid or l["j"] == pid]
        for lid in to_del_l: self._remove_link(lid)
        to_del_a = [aid for aid, a in self.angles.items() if a["i"] == pid or a["j"] == pid or a["k"] == pid]
        for aid in to_del_a: self._remove_angle(aid)
        to_del_c = [cid for cid, c in self.coincides.items() if int(c.get("a")) == pid or int(c.get("b")) == pid]
        for cid in to_del_c: self._remove_coincide(cid)
        to_del_pl = [plid for plid, pl in self.point_lines.items() if int(pl.get("p")) == pid or int(pl.get("i")) == pid or int(pl.get("j")) == pid]
        for plid in to_del_pl:
            self._remove_point_line(plid)
        to_del_ps = [psid for psid, ps in self.point_splines.items() if int(ps.get("p")) == pid]
        for psid in to_del_ps:
            self._remove_point_spline(psid)
        to_del_spl = [sid for sid, s in self.splines.items() if pid in s.get("points", [])]
        for sid in to_del_spl:
            self._remove_spline(sid)
        for b in self.bodies.values():
            if pid in b.get("points", []):
                b["points"] = [x for x in b["points"] if x != pid]
                b["rigid_edges"] = self.compute_body_rigid_edges(b["points"])
        p = self.points[pid]
        if "traj_item" in p:
            self.scene.removeItem(p["traj_item"])
        self.scene.removeItem(p["item"]); self.scene.removeItem(p["marker"])
        if "constraint_marker" in p:
            self.scene.removeItem(p["constraint_marker"])
        if "driver_marker" in p:
            self.scene.removeItem(p["driver_marker"])
        if "output_marker" in p:
            self.scene.removeItem(p["output_marker"])
        if "output_torque_marker" in p:
            self.scene.removeItem(p["output_torque_marker"])
        del self.points[pid]
        self.selected_point_ids.discard(pid)
        if self.selected_point_id == pid:
            self.selected_point_id = next(iter(self.selected_point_ids), None)

    

    def _create_coincide(self, cid: int, a: int, b: int, hidden: bool, enabled: bool = True):
        self.coincides[cid] = {"a": int(a), "b": int(b), "hidden": bool(hidden), "enabled": bool(enabled), "over": False}
        it = CoincideItem(cid, self)
        self.coincides[cid]["item"] = it
        self.scene.addItem(it)

    def _remove_coincide(self, cid: int):
        if cid not in self.coincides: return
        c = self.coincides[cid]
        try:
            self.scene.removeItem(c["item"])
        except Exception:
            pass
        del self.coincides[cid]
        if self.selected_coincide_id == cid:
            self.selected_coincide_id = None


    def _create_point_line(self, plid: int, p: int, i: int, j: int, hidden: bool, enabled: bool = True):
        self.point_lines[plid] = {
            "p": int(p),
            "i": int(i),
            "j": int(j),
            "hidden": bool(hidden),
            "enabled": bool(enabled),
            "over": False,
        }
        it = PointLineItem(plid, self)
        self.point_lines[plid]["item"] = it
        self.scene.addItem(it)

    def _remove_point_line(self, plid: int):
        if plid not in self.point_lines:
            return
        pl = self.point_lines[plid]
        try:
            self.scene.removeItem(pl["item"])
        except Exception:
            pass
        del self.point_lines[plid]
        if self.selected_point_line_id == plid:
            self.selected_point_line_id = None

    def _create_spline(self, sid: int, point_ids: List[int], hidden: bool):
        pts = [pid for pid in point_ids if pid in self.points]
        self.splines[sid] = {"points": pts, "hidden": bool(hidden), "over": False}
        it = SplineItem(sid, self)
        self.splines[sid]["item"] = it
        self.scene.addItem(it)

    def _remove_spline(self, sid: int):
        if sid not in self.splines:
            return
        s = self.splines[sid]
        try:
            self.scene.removeItem(s["item"])
        except Exception:
            pass
        to_del_ps = [psid for psid, ps in self.point_splines.items() if int(ps.get("s", -1)) == sid]
        for psid in to_del_ps:
            self._remove_point_spline(psid)
        del self.splines[sid]
        if self.selected_spline_id == sid:
            self.selected_spline_id = None

    def _create_point_spline(self, psid: int, p: int, s: int, hidden: bool, enabled: bool = True):
        self.point_splines[psid] = {
            "p": int(p),
            "s": int(s),
            "hidden": bool(hidden),
            "enabled": bool(enabled),
            "over": False,
        }
        it = PointSplineItem(psid, self)
        self.point_splines[psid]["item"] = it
        self.scene.addItem(it)

    def _remove_point_spline(self, psid: int):
        if psid not in self.point_splines:
            return
        ps = self.point_splines[psid]
        try:
            self.scene.removeItem(ps["item"])
        except Exception:
            pass
        del self.point_splines[psid]
        if self.selected_point_spline_id == psid:
            self.selected_point_spline_id = None

    def _create_link(self, lid: int, i: int, j: int, L: float, hidden: bool):
        self.links[lid] = {"i": int(i), "j": int(j), "L": float(L), "hidden": bool(hidden), "over": False, "ref": False}
        it = LinkItem(lid, self)
        self.links[lid]["item"] = it
        self.scene.addItem(it)
        mk = TextMarker("")
        self.links[lid]["marker"] = mk
        self.scene.addItem(mk)

    def _remove_link(self, lid: int):
        if lid not in self.links: return
        l = self.links[lid]
        self.scene.removeItem(l["item"]); self.scene.removeItem(l["marker"])
        del self.links[lid]
        if self.selected_link_id == lid:
            self.selected_link_id = None

    def _create_angle(self, aid: int, i: int, j: int, k: int, deg: float, hidden: bool):
        rad = math.radians(float(deg))
        self.angles[aid] = {"i": int(i), "j": int(j), "k": int(k), "deg": float(deg), "rad": float(rad),
                            "hidden": bool(hidden), "over": False}
        mk = AngleItem(aid, self)
        self.angles[aid]["marker"] = mk
        self.scene.addItem(mk)

    def _remove_angle(self, aid: int):
        if aid not in self.angles: return
        a = self.angles[aid]
        if "marker" in a: self.scene.removeItem(a["marker"])
        del self.angles[aid]
        if self.selected_angle_id == aid:
            self.selected_angle_id = None

    def _create_body(self, bid: int, name: str, point_ids: List[int], hidden: bool, color_name: str = "Blue"):
        pts = [pid for pid in point_ids if pid in self.points]
        if color_name not in BODY_COLORS:
            color_name = "Blue"
        self.bodies[bid] = {"name": str(name), "points": pts, "hidden": bool(hidden), "color_name": color_name}
        self.bodies[bid]["rigid_edges"] = self.compute_body_rigid_edges(pts)

    def _remove_body(self, bid: int):
        if bid not in self.bodies: return
        del self.bodies[bid]
        if self.selected_body_id == bid:
            self.selected_body_id = None

    # ------ selection helpers ------
    def _clear_scene_link_selection(self):
        for l in self.links.values(): l["item"].setSelected(False)
    def _clear_scene_angle_selection(self):
        for a in self.angles.values(): a["marker"].setSelected(False)
    def _clear_scene_spline_selection(self):
        for s in self.splines.values():
            try:
                s["item"].setSelected(False)
            except Exception:
                pass
        self.selected_spline_id = None
    def _clear_scene_point_selection(self):
        for pid in list(self.selected_point_ids):
            if pid in self.points:
                self.points[pid]["item"].setSelected(False)
        self.selected_point_ids.clear()
        self.selected_point_id = None

    def _clear_scene_coincide_selection(self):
        for c in self.coincides.values():
            try:
                c["item"].setSelected(False)
            except Exception:
                pass
        self.selected_coincide_id = None

    def _clear_scene_point_line_selection(self):
        for pl in self.point_lines.values():
            try:
                pl["item"].setSelected(False)
            except Exception:
                pass
        self.selected_point_line_id = None
    def _clear_scene_point_spline_selection(self):
        for ps in self.point_splines.values():
            try:
                ps["item"].setSelected(False)
            except Exception:
                pass
        self.selected_point_spline_id = None

    def select_link_single(self, lid: int):
        if lid not in self.links: return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self._clear_scene_link_selection()
        self.links[lid]["item"].setSelected(True)
        self.selected_link_id = lid
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_link(lid)
            self.panel.clear_points_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_splines_selection_only()
            self.panel.clear_bodies_selection_only()
        self.update_status()

    def select_angle_single(self, aid: int):
        if aid not in self.angles: return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.angles[aid]["marker"].setSelected(True)
        self.selected_angle_id = aid
        self.selected_link_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_angle(aid)
            self.panel.clear_points_selection_only()
            self.panel.clear_links_selection_only()
            self.panel.clear_splines_selection_only()
            self.panel.clear_bodies_selection_only()
        self.update_status()



    def select_coincide_single(self, cid: int):
        if cid not in self.coincides: return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.coincides[cid]["item"].setSelected(True)
        self.selected_coincide_id = cid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            try:
                self.panel.select_constraints_row(f"C{cid}")
            except Exception:
                pass
        self.update_status()

    def select_point_line_single(self, plid: int):
        if plid not in self.point_lines:
            return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.point_lines[plid]["item"].setSelected(True)
        self.selected_point_line_id = plid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            try:
                self.panel.select_constraints_row(f"P{plid}")
            except Exception:
                pass
        self.update_status()

    def select_point_spline_single(self, psid: int):
        if psid not in self.point_splines:
            return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.point_splines[psid]["item"].setSelected(True)
        self.selected_point_spline_id = psid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            try:
                self.panel.select_constraints_row(f"S{psid}")
            except Exception:
                pass
        self.update_status()

    def select_body_single(self, bid: int):
        if bid not in self.bodies: return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.selected_body_id = bid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_body(bid)
            self.panel.clear_points_selection_only()
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_splines_selection_only()
        self.update_status()

    def select_spline_single(self, sid: int):
        if sid not in self.splines:
            return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self.splines[sid]["item"].setSelected(True)
        self.selected_spline_id = sid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            try:
                self.panel.select_spline(sid)
                self.panel.clear_points_selection_only()
                self.panel.clear_links_selection_only()
                self.panel.clear_angles_selection_only()
                self.panel.clear_bodies_selection_only()
            except Exception:
                pass
        self.update_status()

    def apply_box_selection(self, pids: List[int], toggle: bool):
        pids = [pid for pid in pids if pid in self.points and (not self.is_point_effectively_hidden(pid)) and self.show_points_geometry]
        if not toggle:
            self._clear_scene_link_selection(); self._clear_scene_angle_selection()
            self._clear_scene_spline_selection(); self._clear_scene_coincide_selection()
            self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection()
            self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
            for pid in list(self.selected_point_ids):
                if pid in self.points:
                    self.points[pid]["item"].setSelected(False)
            self.selected_point_ids.clear()
            for pid in pids:
                self.selected_point_ids.add(pid)
                self.points[pid]["item"].setSelected(True)
            self.selected_point_id = pids[-1] if pids else None
        else:
            for pid in pids:
                if pid in self.selected_point_ids:
                    self.selected_point_ids.remove(pid)
                    self.points[pid]["item"].setSelected(False)
                else:
                    self.selected_point_ids.add(pid)
                    self.points[pid]["item"].setSelected(True)
                    self.selected_point_id = pid
            self._clear_scene_link_selection(); self._clear_scene_angle_selection()
            self._clear_scene_spline_selection(); self._clear_scene_coincide_selection()
            self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection()
            self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_points_multi(sorted(self.selected_point_ids))
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_splines_selection_only()
            self.panel.clear_bodies_selection_only()
        self.update_status()

    def select_point_single(self, pid: int, keep_others: bool = False):
        if pid not in self.points: return
        if not keep_others:
            for opid in list(self.selected_point_ids):
                if opid in self.points:
                    self.points[opid]["item"].setSelected(False)
            self.selected_point_ids.clear()
        self.selected_point_ids.add(pid)
        self.points[pid]["item"].setSelected(True)
        self.selected_point_id = pid
        self._clear_scene_link_selection(); self._clear_scene_angle_selection()
        self._clear_scene_spline_selection(); self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection()
        self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_points_multi(sorted(self.selected_point_ids))
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_splines_selection_only()
            self.panel.clear_bodies_selection_only()

    def toggle_point(self, pid: int):
        if pid not in self.points: return
        if pid in self.selected_point_ids:
            self.selected_point_ids.remove(pid)
            self.points[pid]["item"].setSelected(False)
            if self.selected_point_id == pid:
                self.selected_point_id = next(iter(self.selected_point_ids), None)
        else:
            self.selected_point_ids.add(pid)
            self.points[pid]["item"].setSelected(True)
            self.selected_point_id = pid
        self._clear_scene_link_selection(); self._clear_scene_angle_selection()
        self._clear_scene_spline_selection(); self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection()
        self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_points_multi(sorted(self.selected_point_ids))
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_bodies_selection_only()

    # ------ commands ------
    def cmd_add_point(self, x: float, y: float):
        pid = self._next_pid; self._next_pid += 1
        ctrl = self
        class AddPoint(Command):
            name = "Add Point"
            def do(self_):
                ctrl._create_point(pid, x, y, fixed=False, hidden=False, traj_enabled=False)
                ctrl.select_point_single(pid, keep_others=False)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_point(pid)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
                ctrl.update_status()
        self.stack.push(AddPoint())

    def cmd_add_link(self, i: int, j: int):
        if i == j or i not in self.points or j not in self.points: return
        lid = self._next_lid; self._next_lid += 1
        p1, p2 = self.points[i], self.points[j]
        L = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
        ctrl = self
        class AddLink(Command):
            name = "Add Link"
            def do(self_):
                ctrl._create_link(lid, i, j, L, hidden=False)
                ctrl.select_link_single(lid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_link(lid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
                ctrl.update_status()
        self.stack.push(AddLink())

    def cmd_add_angle(self, i: int, j: int, k: int, deg: float):
        if len({i, j, k}) < 3: return
        if i not in self.points or j not in self.points or k not in self.points: return
        aid = self._next_aid; self._next_aid += 1
        ctrl = self
        class AddAngle(Command):
            name = "Add Angle"
            def do(self_):
                ctrl._create_angle(aid, i, j, k, deg, hidden=False)
                ctrl.select_angle_single(aid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_angle(aid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
                ctrl.update_status()
        self.stack.push(AddAngle())

    
    def cmd_add_spline(self, point_ids: List[int]):
        pts = [pid for pid in point_ids if pid in self.points]
        if len(pts) < 2:
            return
        sid = self._next_sid; self._next_sid += 1
        ctrl = self
        class AddSpline(Command):
            name = "Add Spline"
            def do(self_):
                ctrl._create_spline(sid, pts, hidden=False)
                ctrl.select_spline_single(sid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_spline(sid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
                ctrl.update_status()
        self.stack.push(AddSpline())

    def cmd_set_spline_points(self, sid: int, point_ids: List[int]):
        if sid not in self.splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetSplinePoints(Command):
            name = "Set Spline Points"
            def do(self_):
                pts = [pid for pid in point_ids if pid in ctrl.points]
                ctrl.splines[sid]["points"] = pts
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetSplinePoints())

    def cmd_set_spline_hidden(self, sid: int, hidden: bool):
        if sid not in self.splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetSplineHidden(Command):
            name = "Set Spline Hidden"
            def do(self_):
                ctrl.splines[sid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetSplineHidden())

    def cmd_delete_spline(self, sid: int):
        if sid not in self.splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class DelSpline(Command):
            name = "Delete Spline"
            def do(self_):
                ctrl._remove_spline(sid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelSpline())


    def cmd_set_angle_enabled(self, aid: int, enabled: bool):
        if aid not in self.angles: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetAE(Command):
            name = "Set Angle Enabled"
            def do(self_):
                ctrl.angles[aid]["enabled"] = bool(enabled)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetAE())
    def cmd_add_body_from_points(self, point_ids: List[int]):
            pts = [pid for pid in point_ids if pid in self.points]
            if len(pts) < 2: return
            bid = self._next_bid; self._next_bid += 1
            name = f"B{bid}"
            ctrl = self
            model_before = self.snapshot_model()
            class AddBody(Command):
                name = "Add Body"
                def do(self_):
                    for b in ctrl.bodies.values():
                        b["points"] = [p for p in b.get("points", []) if p not in pts]
                        b["rigid_edges"] = ctrl.compute_body_rigid_edges(b["points"])
                    ctrl._create_body(bid, name, pts, hidden=False, color_name="Blue")
                    ctrl.select_body_single(bid)
                    ctrl.solve_constraints(); ctrl.update_graphics()
                    if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                def undo(self_):
                    ctrl.apply_model_snapshot(model_before)
            self.stack.push(AddBody())

    def cmd_body_set_members(self, bid: int, new_points: List[int]):
        if bid not in self.bodies: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetMembers(Command):
            name = "Edit Body"
            def do(self_):
                pts = [pid for pid in new_points if pid in ctrl.points]
                for obid, b in ctrl.bodies.items():
                    if obid == bid: continue
                    b["points"] = [p for p in b.get("points", []) if p not in pts]
                    b["rigid_edges"] = ctrl.compute_body_rigid_edges(b["points"])
                ctrl.bodies[bid]["points"] = pts
                ctrl.bodies[bid]["rigid_edges"] = ctrl.compute_body_rigid_edges(pts)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetMembers())

    def cmd_set_body_color(self, bid: int, color_name: str):
        if bid not in self.bodies: return
        if color_name not in BODY_COLORS: return
        prev = self.bodies[bid].get("color_name", "Blue")
        if prev == color_name: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetBodyColor(Command):
            name = "Set Body Color"
            def do(self_):
                ctrl.bodies[bid]["color_name"] = color_name
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetBodyColor())

    def cmd_delete_body(self, bid: int):
        if bid not in self.bodies: return
        ctrl = self
        model_before = self.snapshot_model()
        class DelBody(Command):
            name = "Delete Body"
            def do(self_):
                ctrl._remove_body(bid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelBody())

    def cmd_delete_point(self, pid: int):
        if pid not in self.points: return
        ctrl = self
        model_before = self.snapshot_model()
        class DelPoint(Command):
            name = "Delete Point"
            def do(self_):
                ctrl._remove_point(pid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelPoint())

    def cmd_delete_link(self, lid: int):
        if lid not in self.links: return
        ctrl = self
        model_before = self.snapshot_model()
        class DelLink(Command):
            name = "Delete Link"
            def do(self_):
                ctrl._remove_link(lid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelLink())

    def cmd_delete_angle(self, aid: int):
        if aid not in self.angles: return
        ctrl = self
        model_before = self.snapshot_model()
        class DelAngle(Command):
            name = "Delete Angle"
            def do(self_):
                ctrl._remove_angle(aid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelAngle())


    def cmd_add_coincide(self, a: int, b: int):
        """Add a coincidence (point-on-point) constraint between points a and b."""
        if a == b or a not in self.points or b not in self.points:
            return
        # avoid duplicates (unordered pair)
        pair = frozenset({int(a), int(b)})
        for c in self.coincides.values():
            if frozenset({int(c.get("a")), int(c.get("b"))}) == pair:
                return
        ctrl = self
        model_before = self.snapshot_model()
        cid = self._next_cid
        class AddCoincide(Command):
            name = "Add Coincide"
            def do(self_):
                ctrl._next_cid = max(ctrl._next_cid, cid + 1)
                ctrl._create_coincide(cid, a, b, hidden=False, enabled=True)
                # snap b onto a for immediate satisfaction
                ax, ay = ctrl.points[a]["x"], ctrl.points[a]["y"]
                ctrl.points[b]["x"] = ax; ctrl.points[b]["y"] = ay
                ctrl.solve_constraints(drag_pid=b)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(AddCoincide())

    def cmd_delete_coincide(self, cid: int):
        if cid not in self.coincides: return
        ctrl = self
        model_before = self.snapshot_model()
        class DelCoincide(Command):
            name = "Delete Coincide"
            def do(self_):
                ctrl._remove_coincide(cid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelCoincide())

    def cmd_set_coincide_hidden(self, cid: int, hidden: bool):
        if cid not in self.coincides: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetCH(Command):
            name = "Set Coincide Hidden"
            def do(self_):
                ctrl.coincides[cid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetCH())

    def cmd_set_coincide_enabled(self, cid: int, enabled: bool):
        if cid not in self.coincides: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetCE(Command):
            name = "Set Coincide Enabled"
            def do(self_):
                ctrl.coincides[cid]["enabled"] = bool(enabled)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetCE())

    def cmd_add_point_line(self, p: int, i: int, j: int):
        """Add a point-on-line constraint: point p lies on the infinite line through points i-j."""
        if p not in self.points or i not in self.points or j not in self.points:
            return
        if i == j:
            return
        if p == i or p == j:
            # trivial; avoid degenerate constraints
            return
        line_pair = frozenset({int(i), int(j)})
        for pl in self.point_lines.values():
            if int(pl.get("p")) == int(p) and frozenset({int(pl.get("i")), int(pl.get("j"))}) == line_pair:
                return
        ctrl = self
        model_before = self.snapshot_model()
        plid = self._next_plid
        class AddPointLine(Command):
            name = "Add Point On Line"
            def do(self_):
                ctrl._next_plid = max(ctrl._next_plid, plid + 1)
                ctrl._create_point_line(plid, p, i, j, hidden=False, enabled=True)
                # Try to satisfy immediately by projecting p onto the line (if movable)
                pp = ctrl.points[p]; pa = ctrl.points[i]; pb = ctrl.points[j]
                lock_p = bool(pp.get("fixed", False))
                lock_a = bool(pa.get("fixed", False))
                lock_b = bool(pb.get("fixed", False))
                ConstraintSolver.solve_point_on_line(pp, pa, pb, lock_p, lock_a, lock_b, tol=1e-6)
                ctrl.solve_constraints(drag_pid=p)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(AddPointLine())

    def cmd_add_point_spline(self, p: int, s: int):
        """Add a point-on-spline constraint: point p lies on spline s."""
        if p not in self.points or s not in self.splines:
            return
        if p in self.splines[s].get("points", []):
            return
        for ps in self.point_splines.values():
            if int(ps.get("p", -1)) == int(p) and int(ps.get("s", -1)) == int(s):
                return
        ctrl = self
        model_before = self.snapshot_model()
        psid = self._next_psid
        class AddPointSpline(Command):
            name = "Add Point On Spline"
            def do(self_):
                ctrl._next_psid = max(ctrl._next_psid, psid + 1)
                ctrl._create_point_spline(psid, p, s, hidden=False, enabled=True)
                pp = ctrl.points[p]
                cp_ids = [pid for pid in ctrl.splines[s].get("points", []) if pid in ctrl.points]
                cps = [ctrl.points[cid] for cid in cp_ids]
                lock_p = bool(pp.get("fixed", False))
                lock_controls = [bool(ctrl.points[cid].get("fixed", False)) for cid in cp_ids]
                ConstraintSolver.solve_point_on_spline(pp, cps, lock_p, lock_controls, tol=1e-6)
                ctrl.solve_constraints(drag_pid=p)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(AddPointSpline())

    def cmd_delete_point_line(self, plid: int):
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class DelPL(Command):
            name = "Delete Point On Line"
            def do(self_):
                ctrl._remove_point_line(plid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelPL())

    def cmd_delete_point_spline(self, psid: int):
        if psid not in self.point_splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class DelPS(Command):
            name = "Delete Point On Spline"
            def do(self_):
                ctrl._remove_point_spline(psid)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelPS())

    def cmd_set_point_line_hidden(self, plid: int, hidden: bool):
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPLH(Command):
            name = "Set Point On Line Hidden"
            def do(self_):
                ctrl.point_lines[plid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPLH())

    def cmd_set_point_spline_hidden(self, psid: int, hidden: bool):
        if psid not in self.point_splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPSH(Command):
            name = "Set Point On Spline Hidden"
            def do(self_):
                ctrl.point_splines[psid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPSH())

    def cmd_set_point_line_enabled(self, plid: int, enabled: bool):
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPLE(Command):
            name = "Set Point On Line Enabled"
            def do(self_):
                ctrl.point_lines[plid]["enabled"] = bool(enabled)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPLE())

    def cmd_set_point_spline_enabled(self, psid: int, enabled: bool):
        if psid not in self.point_splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPSE(Command):
            name = "Set Point On Spline Enabled"
            def do(self_):
                ctrl.point_splines[psid]["enabled"] = bool(enabled)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPSE())

    def cmd_set_point_fixed(self, pid: int, fixed: bool):
        if pid not in self.points: return
        prev = bool(self.points[pid].get("fixed", False))
        fixed = bool(fixed)
        if prev == fixed: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetFixed(Command):
            name = "Set Fixed"
            def do(self_):
                ctrl.points[pid]["fixed"] = fixed
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetFixed())

    def cmd_set_point_hidden(self, pid: int, hidden: bool):
        if pid not in self.points: return
        prev = bool(self.points[pid].get("hidden", False))
        hidden = bool(hidden)
        if prev == hidden: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetHidden(Command):
            name = "Hide/Show Point"
            def do(self_):
                ctrl.points[pid]["hidden"] = hidden
                if hidden:
                    ctrl.selected_point_ids.discard(pid)
                    ctrl.points[pid]["item"].setSelected(False)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetHidden())

    def cmd_set_point_trajectory(self, pid: int, enabled: bool):
        if pid not in self.points:
            return
        prev = bool(self.points[pid].get("traj", False))
        enabled = bool(enabled)
        if prev == enabled:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetTrajectory(Command):
            name = "Set Point Trajectory"
            def do(self_):
                ctrl.points[pid]["traj"] = enabled
                if enabled:
                    ctrl.show_trajectories = True
                    titem = ctrl.points[pid].get("traj_item")
                    if titem is not None:
                        titem.reset_path(ctrl.points[pid]["x"], ctrl.points[pid]["y"])
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetTrajectory())

    def cmd_set_link_hidden(self, lid: int, hidden: bool):
        if lid not in self.links: return
        prev = bool(self.links[lid].get("hidden", False))
        hidden = bool(hidden)
        if prev == hidden: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetHiddenL(Command):
            name = "Hide/Show Link"
            def do(self_):
                ctrl.links[lid]["hidden"] = hidden
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetHiddenL())


    def cmd_set_link_reference(self, lid: int, is_ref: bool):
        """Toggle a length between Constraint and Reference.

        - Constraint (is_ref=False): enforces the stored L.
        - Reference (is_ref=True): does NOT enforce; L is shown as a measurement.
          When switching back to Constraint, L is set to the current measured length.
        """
        if lid not in self.links:
            return
        is_ref = bool(is_ref)
        prev = bool(self.links[lid].get("ref", False))
        if prev == is_ref:
            return

        ctrl = self
        model_before = self.snapshot_model()

        def _measured_length() -> Optional[float]:
            l = ctrl.links[lid]
            i, j = int(l.get("i")), int(l.get("j"))
            if i not in ctrl.points or j not in ctrl.points:
                return None
            p1, p2 = ctrl.points[i], ctrl.points[j]
            return float(math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"]))

        class SetRef(Command):
            name = "Set Length Reference"
            def do(self_):
                ctrl.links[lid]["ref"] = is_ref
                if not is_ref:
                    curL = _measured_length()
                    if curL is not None and curL > 1e-9:
                        ctrl.links[lid]["L"] = float(curL)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        self.stack.push(SetRef())

    def cmd_set_angle_hidden(self, aid: int, hidden: bool):
        if aid not in self.angles: return
        prev = bool(self.angles[aid].get("hidden", False))
        hidden = bool(hidden)
        if prev == hidden: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetHiddenA(Command):
            name = "Hide/Show Angle"
            def do(self_):
                ctrl.angles[aid]["hidden"] = hidden
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetHiddenA())

    def cmd_set_link_length(self, lid: int, L: float):
        if lid not in self.links: return
        L = float(L)
        if L <= 1e-9: return
        ctrl = self
        model_before = self.snapshot_model()
        class SetLen(Command):
            name = "Set Length"
            def do(self_):
                ctrl.links[lid]["L"] = L
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetLen())

    def cmd_set_angle_deg(self, aid: int, deg: float):
        if aid not in self.angles: return
        deg = float(deg)
        ctrl = self
        model_before = self.snapshot_model()
        class SetAng(Command):
            name = "Set Angle"
            def do(self_):
                ctrl.angles[aid]["deg"] = deg
                ctrl.angles[aid]["rad"] = math.radians(deg)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetAng())

    def cmd_move_system(self, before: Dict[int, Tuple[float, float]], after: Dict[int, Tuple[float, float]]):
        ctrl = self
        model_before = self.snapshot_model()
        class MoveSystem(Command):
            name = "Move"
            def do(self_):
                ctrl.apply_points_snapshot(after)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.refresh_fast()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(MoveSystem())

    def cmd_move_point_by_table(self, pid: int, x: float, y: float):
        if pid not in self.points: return
        before = self.snapshot_points()
        self.points[pid]["x"] = float(x); self.points[pid]["y"] = float(y)
        self.solve_constraints(drag_pid=pid)
        after = self.snapshot_points()
        self.cmd_move_system(before, after)

    def on_drag_update(self, pid: int, nx: float, ny: float):
        if pid not in self.points: return
        if not self._drag_active:
            self._drag_active = True
            self._drag_pid = pid
            self._drag_before = self.snapshot_points()
        self.points[pid]["x"] = float(nx); self.points[pid]["y"] = float(ny)
        self.solve_constraints(drag_pid=pid)
        self.update_graphics()
        self.append_trajectories()
        if self.panel: self.panel.refresh_fast()

    def commit_drag_if_any(self):
        if not self._drag_active or self._drag_before is None: return
        before = self._drag_before
        after = self.snapshot_points()
        self._drag_active = False
        self._drag_pid = None
        self._drag_before = None
        self.cmd_move_system(before, after)

    def begin_create_line(self):
        self.commit_drag_if_any()
        self.mode = "CreateLine"
        self._line_sel = []
        self.update_status()

    def begin_coincide(self, master: int):
        self.commit_drag_if_any()
        self.mode = "Coincide"
        self._co_master = master
        self.update_status()

    def begin_point_on_line(self, master: int):
        """Start point-on-line creation: choose 2 points to define the line."""
        self.commit_drag_if_any()
        self.mode = "PointOnLine"
        self._pol_master = int(master)
        self._pol_line_sel = []
        self.update_status()

    def begin_point_on_spline(self, master: int):
        """Start point-on-spline creation: choose a spline to constrain."""
        self.commit_drag_if_any()
        self.mode = "PointOnSpline"
        self._pos_master = int(master)
        self.update_status()

    def on_point_clicked_create_line(self, pid: int):
        if pid not in self.points or self.is_point_effectively_hidden(pid) or (not self.show_points_geometry): return
        if pid in self._line_sel: return
        self._line_sel.append(pid)
        if len(self._line_sel) >= 2:
            i, j = self._line_sel[0], self._line_sel[1]
            self.mode = "Idle"
            self._line_sel = []
            self.cmd_add_link(i, j)
        self.update_status()

    
    def on_point_clicked_coincide(self, pid: int):
        if self._co_master is None or self._co_master not in self.points:
            self.mode = "Idle"; self._co_master = None; self.update_status(); return
        if pid == self._co_master:
            return
        master = int(self._co_master)
        self.mode = "Idle"; self._co_master = None
        # Create a persistent coincidence constraint (so it won't drift apart when dragging).
        self.cmd_add_coincide(master, int(pid))
        self.update_status()

    def on_link_clicked_coincide(self, lid: int):
        if self._co_master is None or self._co_master not in self.points:
            self.mode = "Idle"; self._co_master = None; self.update_status(); return
        if lid not in self.links:
            return
        p = int(self._co_master)
        self.mode = "Idle"; self._co_master = None
        l = self.links[lid]
        self.cmd_add_point_line(p, int(l.get("i")), int(l.get("j")))
        self.update_status()

    def on_spline_clicked_coincide(self, sid: int):
        if self._co_master is None or self._co_master not in self.points:
            self.mode = "Idle"; self._co_master = None; self.update_status(); return
        if sid not in self.splines:
            return
        p = int(self._co_master)
        self.mode = "Idle"; self._co_master = None
        self.cmd_add_point_spline(p, sid)
        self.update_status()

    def on_point_clicked_point_on_line(self, pid: int):
        if self._pol_master is None or self._pol_master not in self.points:
            self.mode = "Idle"
            self._pol_master = None
            self._pol_line_sel = []
            self.update_status()
            return
        if pid == self._pol_master:
            return
        if pid in self._pol_line_sel:
            return
        self._pol_line_sel.append(int(pid))
        if len(self._pol_line_sel) >= 2:
            p = int(self._pol_master)
            i, j = int(self._pol_line_sel[0]), int(self._pol_line_sel[1])
            self.mode = "Idle"
            self._pol_master = None
            self._pol_line_sel = []
            self.cmd_add_point_line(p, i, j)
        self.update_status()

    def on_spline_clicked_point_on_spline(self, sid: int):
        if self._pos_master is None or self._pos_master not in self.points:
            self.mode = "Idle"
            self._pos_master = None
            self.update_status()
            return
        if sid not in self.splines:
            return
        p = int(self._pos_master)
        self.mode = "Idle"
        self._pos_master = None
        self.cmd_add_point_spline(p, sid)
        self.update_status()

    def on_point_clicked_idle(self, pid: int, modifiers):
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.toggle_point(pid)
        else:
            self.select_point_single(pid, keep_others=False)
        self.update_status()

    def show_empty_context_menu(self, global_pos, scene_pos: QPointF):
        m = QMenu(self.win)
        m.addAction("Create Point", lambda: self.cmd_add_point(scene_pos.x(), scene_pos.y()))
        m.addAction("Create Line", self.begin_create_line)
        m.addAction("Create Spline (from selected points)", self._add_spline_from_selection)
        m.exec(global_pos)

    def _delete_selected_points_multi(self):
        ids = sorted(list(self.selected_point_ids))
        for pid in reversed(ids):
            self.cmd_delete_point(pid)

    def _add_spline_from_selection(self):
        ids = sorted(list(self.selected_point_ids))
        if len(ids) < 2:
            return
        self.cmd_add_spline(ids)

    def show_point_context_menu(self, pid: int, global_pos):
        self.commit_drag_if_any()
        self.select_point_single(pid, keep_others=False)
        p = self.points[pid]
        m = QMenu(self.win)
        m.addAction("Fix" if not p.get("fixed", False) else "Unfix",
                    lambda: self.cmd_set_point_fixed(pid, not p.get("fixed", False)))
        m.addAction("Hide" if not p.get("hidden", False) else "Show",
                    lambda: self.cmd_set_point_hidden(pid, not p.get("hidden", False)))
        m.addSeparator()
        m.addAction("Coincide With (point/line/spline)...", lambda: self.begin_coincide(pid))

        # --- Simulation helpers (driver / measurement) ---
        nbrs = []
        for l in self.links.values():
            i, j = int(l.get("i")), int(l.get("j"))
            if i == pid and j != pid:
                nbrs.append(j)
            elif j == pid and i != pid:
                nbrs.append(i)
        # unique, stable order
        seen = set()
        nbrs = [x for x in nbrs if (x not in seen and not seen.add(x))]

        if nbrs:
            m.addSeparator()
            sub_drv = m.addMenu("Set Driver")

            # Vector driver: choose a neighbor as tip
            sub_vec = sub_drv.addMenu("Vector (pivot->tip)")
            for nb in nbrs:
                sub_vec.addAction(f"pivot P{pid} -> tip P{nb}", lambda nb=nb: self.set_driver(pid, nb))

            # Joint driver: choose two neighbors as i and k
            sub_joint = sub_drv.addMenu("Joint angle (i-j-k)")
            if len(nbrs) >= 2:
                for i in nbrs:
                    for k in nbrs:
                        if i == k:
                            continue
                        sub_joint.addAction(f"P{i}-P{pid}-P{k}", lambda i=i, k=k: self.set_driver_joint(i, pid, k))

            sub_drv.addSeparator()
            sub_drv.addAction("Clear Driver", self.clear_driver)

            sub_meas = m.addMenu("Add Measurement")

            sub_mvec = sub_meas.addMenu("Vector (world)")
            for nb in nbrs:
                sub_mvec.addAction(f"V(P{pid}->P{nb})", lambda nb=nb: self.add_measure_vector(pid, nb))

            sub_mjoint = sub_meas.addMenu("Joint angle")
            if len(nbrs) >= 2:
                for i in nbrs:
                    for k in nbrs:
                        if i == k:
                            continue
                        sub_mjoint.addAction(f"A(P{i}-P{pid}-P{k})", lambda i=i, k=k: self.add_measure_joint(i, pid, k))

            sub_meas.addSeparator()
            sub_meas.addAction("Clear Measurements", self.clear_measures)
            sub_load_meas = sub_meas.addMenu("Add Load Measurement")
            sub_load_meas.addAction("Joint Load Fx", lambda: self.add_load_measure_joint(pid, "fx"))
            sub_load_meas.addAction("Joint Load Fy", lambda: self.add_load_measure_joint(pid, "fy"))
            sub_load_meas.addAction("Joint Load Mag", lambda: self.add_load_measure_joint(pid, "mag"))
            sub_meas.addAction("Clear Load Measurements", self.clear_load_measures)

            sub_out = m.addMenu("Set Output")
            for nb in nbrs:
                sub_out.addAction(f"pivot P{pid} -> tip P{nb}", lambda nb=nb: self.set_output(pid, nb))
            sub_out.addSeparator()
            sub_out.addAction("Clear Output", self.clear_output)

            sub_load = m.addMenu("Loads")
            sub_load.addAction("Add Force (Fx,Fy)", lambda: self._prompt_add_force(pid))
            sub_load.addAction("Add Torque (Mz)", lambda: self._prompt_add_torque(pid))
            sub_load.addSeparator()
            sub_load.addAction("Clear Loads", self.clear_loads)

        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_point(pid))
        m.exec(global_pos)
        self.update_status()

        # refresh sim panel labels if present
        try:
            if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
                self.win.sim_panel.refresh_labels()
        except Exception:
            pass

    def show_link_context_menu(self, lid: int, global_pos):
        self.commit_drag_if_any()
        self.select_link_single(lid)
        m = QMenu(self.win)
        l = self.links[lid]
        m.addAction("Hide" if not l.get("hidden", False) else "Show",
                    lambda: self.cmd_set_link_hidden(lid, not l.get("hidden", False)))
        m.addAction("Set as Constraint" if l.get("ref", False) else "Set as Reference",
                    lambda: self.cmd_set_link_reference(lid, not l.get("ref", False)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_link(lid))
        m.exec(global_pos)
        self.update_status()


    def show_coincide_context_menu(self, cid: int, global_pos):
        self.commit_drag_if_any()
        if cid not in self.coincides:
            return
        self.select_coincide_single(cid)
        c = self.coincides[cid]
        m = QMenu(self.win)
        m.addAction("Hide" if not c.get("hidden", False) else "Show",
                    lambda: self.cmd_set_coincide_hidden(cid, not c.get("hidden", False)))
        m.addAction("Disable" if c.get("enabled", True) else "Enable",
                    lambda: self.cmd_set_coincide_enabled(cid, not c.get("enabled", True)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_coincide(cid))
        m.exec(global_pos)
        self.update_status()
        try:
            if self.panel: self.panel.defer_refresh_all(keep_selection=True)
        except Exception:
            pass

    def show_point_line_context_menu(self, plid: int, global_pos):
        self.commit_drag_if_any()
        if plid not in self.point_lines:
            return
        self.select_point_line_single(plid)
        pl = self.point_lines[plid]
        m = QMenu(self.win)
        m.addAction("Hide" if not pl.get("hidden", False) else "Show",
                    lambda: self.cmd_set_point_line_hidden(plid, not pl.get("hidden", False)))
        m.addAction("Disable" if pl.get("enabled", True) else "Enable",
                    lambda: self.cmd_set_point_line_enabled(plid, not pl.get("enabled", True)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_point_line(plid))
        m.exec(global_pos)
        self.update_status()
        try:
            if self.panel: self.panel.defer_refresh_all(keep_selection=True)
        except Exception:
            pass

    def show_point_spline_context_menu(self, psid: int, global_pos):
        self.commit_drag_if_any()
        if psid not in self.point_splines:
            return
        self.select_point_spline_single(psid)
        ps = self.point_splines[psid]
        m = QMenu(self.win)
        m.addAction("Hide" if not ps.get("hidden", False) else "Show",
                    lambda: self.cmd_set_point_spline_hidden(psid, not ps.get("hidden", False)))
        m.addAction("Disable" if ps.get("enabled", True) else "Enable",
                    lambda: self.cmd_set_point_spline_enabled(psid, not ps.get("enabled", True)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_point_spline(psid))
        m.exec(global_pos)
        self.update_status()
        try:
            if self.panel: self.panel.defer_refresh_all(keep_selection=True)
        except Exception:
            pass

    def show_spline_context_menu(self, sid: int, global_pos):
        self.commit_drag_if_any()
        if sid not in self.splines:
            return
        self.select_spline_single(sid)
        s = self.splines[sid]
        m = QMenu(self.win)
        m.addAction("Hide" if not s.get("hidden", False) else "Show",
                    lambda: self.cmd_set_spline_hidden(sid, not s.get("hidden", False)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.cmd_delete_spline(sid))
        m.exec(global_pos)
        self.update_status()
        try:
            if self.panel: self.panel.defer_refresh_all(keep_selection=True)
        except Exception:
            pass

    def update_graphics(self):
        driver_marker_pid = None
        if self.driver.get("enabled"):
            driver_type = str(self.driver.get("type", "vector"))
            if driver_type == "joint":
                pid = self.driver.get("j")
                if pid is not None:
                    driver_marker_pid = int(pid)
            else:
                pid = self.driver.get("pivot")
                if pid is not None:
                    driver_marker_pid = int(pid)
        output_marker_pid = None
        if self.output.get("enabled"):
            pid = self.output.get("pivot")
            if pid is not None:
                output_marker_pid = int(pid)
        tau_out = self._last_quasistatic_summary.get("tau_output")
        for pid, p in self.points.items():
            it: PointItem = p["item"]
            it._internal = True
            it.setPos(p["x"], p["y"])
            it._internal = False
            it.sync_style()
            mk: TextMarker = p["marker"]
            mk.setText(f"P{pid}")
            mk.setPos(p["x"] + 6, p["y"] + 6)
            mk.setVisible(self.show_point_markers and (not self.is_point_effectively_hidden(pid)) and self.show_points_geometry)
            cmark: TextMarker = p["constraint_marker"]
            cmark_bounds = cmark.boundingRect()
            cmark.setPos(p["x"] - cmark_bounds.width() / 2.0, p["y"] + 4)
            show_constraint = (
                self.show_dim_markers
                and bool(p.get("fixed", False))
                and (not self.is_point_effectively_hidden(pid))
                and self.show_points_geometry
            )
            cmark.setVisible(show_constraint)
            dmark: TextMarker = p["driver_marker"]
            dmark_bounds = dmark.boundingRect()
            dmark.setPos(p["x"] + 8, p["y"] - dmark_bounds.height() - 4)
            show_driver = (
                self.show_dim_markers
                and driver_marker_pid == pid
                and (not self.is_point_effectively_hidden(pid))
                and self.show_points_geometry
            )
            dmark.setVisible(show_driver)
            omark: TextMarker = p["output_marker"]
            omark_bounds = omark.boundingRect()
            omark.setPos(p["x"] - omark_bounds.width() - 8, p["y"] - omark_bounds.height() - 4)
            show_output = (
                self.show_dim_markers
                and output_marker_pid == pid
                and (not self.is_point_effectively_hidden(pid))
                and self.show_points_geometry
            )
            omark.setVisible(show_output)
            tmark: TextMarker = p["output_torque_marker"]
            tmark_bounds = tmark.boundingRect()
            tmark.setPos(p["x"] - tmark_bounds.width() - 8, p["y"] + 6)
            show_output_torque = (
                self.show_dim_markers
                and output_marker_pid == pid
                and tau_out is not None
                and abs(float(tau_out)) > 1e-9
                and (not self.is_point_effectively_hidden(pid))
                and self.show_points_geometry
            )
            tmark.setVisible(show_output_torque)
            titem = p.get("traj_item")
            if titem is not None:
                show_traj = (
                    self.show_trajectories
                    and (not self._drag_active)
                    and bool(p.get("traj", False))
                    and (not self.is_point_effectively_hidden(pid))
                )
                titem.setVisible(show_traj)

        for lid, l in self.links.items():
            it: LinkItem = l["item"]
            it.update_position()
            it.sync_style()
            p1, p2 = self.points[l["i"]], self.points[l["j"]]
            mx, my = (p1["x"] + p2["x"]) / 2.0, (p1["y"] + p2["y"]) / 2.0
            mk: TextMarker = l["marker"]
            if l.get("ref", False):
                # Reference length: show current (measured) length, but do not constrain.
                curL = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                mk.setText(f"({curL:.6g})")
            else:
                mk.setText(f"L={l['L']:.6g}")
            mk.setPos(mx, my)
            mk.setVisible(self.show_dim_markers and self.show_links_geometry and not l.get("hidden", False))

        for sid, s in self.splines.items():
            it: SplineItem = s["item"]
            cp_ids = [pid for pid in s.get("points", []) if pid in self.points]
            pts = [(self.points[pid]["x"], self.points[pid]["y"]) for pid in cp_ids]
            samples = build_spline_samples(pts, samples_per_segment=16)
            path = QPainterPath()
            if samples:
                x0, y0 = samples[0][0], samples[0][1]
                path.moveTo(x0, y0)
                for x, y, _seg, _t in samples[1:]:
                    path.lineTo(x, y)
            it.setPath(path)
            it.sync_style()

        for cid, c in self.coincides.items():
            it: CoincideItem = c["item"]
            it.sync()

        for plid, pl in self.point_lines.items():
            it: PointLineItem = pl["item"]
            it.sync()

        for psid, ps in self.point_splines.items():
            it: PointSplineItem = ps["item"]
            it.sync()

        for aid, a in self.angles.items():
            a["marker"].sync()

        self._sync_load_arrows()

    def _sync_load_arrows(self):
        if not self.show_load_arrows:
            for item in self._load_arrow_items:
                item.setVisible(False)
            return

        load_vectors: List[Dict[str, float]] = []
        for ld in self.loads:
            if str(ld.get("type", "force")).lower() != "force":
                continue
            pid = int(ld.get("pid", -1))
            if pid not in self.points:
                continue
            if self.is_point_effectively_hidden(pid) or (not self.show_points_geometry):
                continue
            fx = float(ld.get("fx", 0.0))
            fy = float(ld.get("fy", 0.0))
            if abs(fx) + abs(fy) < 1e-12:
                continue
            p = self.points[pid]
            mag = math.hypot(fx, fy)
            load_vectors.append({"x": p["x"], "y": p["y"], "fx": fx, "fy": fy, "label": f"{mag:.3f}"})

        for jl in self._last_joint_loads:
            pid = int(jl.get("pid", -1))
            if pid not in self.points:
                continue
            if self.is_point_effectively_hidden(pid) or (not self.show_points_geometry):
                continue
            fx = float(jl.get("fx", 0.0))
            fy = float(jl.get("fy", 0.0))
            if abs(fx) + abs(fy) < 1e-12:
                continue
            p = self.points[pid]
            mag = math.hypot(fx, fy)
            load_vectors.append({"x": p["x"], "y": p["y"], "fx": fx, "fy": fy, "label": f"{mag:.3f}"})

        needed = len(load_vectors)
        while len(self._load_arrow_items) < needed:
            item = ForceArrowItem(QColor(220, 40, 40))
            self._load_arrow_items.append(item)
            self.scene.addItem(item)
        mags = [math.hypot(vec["fx"], vec["fy"]) for vec in load_vectors]
        max_mag = max(mags) if mags else 0.0
        target_len = 90.0
        scale = (target_len / max_mag) if max_mag > 1e-9 else 1.0
        scale = max(0.02, min(2.0, scale))
        for idx, item in enumerate(self._load_arrow_items):
            if idx >= needed:
                item.setVisible(False)
                continue
            vec = load_vectors[idx]
            item.set_vector(
                vec["x"],
                vec["y"],
                vec["fx"],
                vec["fy"],
                scale=scale,
                label=str(vec.get("label", "")),
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "2.7.0",
            "parameters": self.parameters.to_list(),
            "points": [
                {
                    "id": pid,
                    "x": p["x"], "y": p["y"],
                    "x_expr": (p.get("x_expr") or ""),
                    "y_expr": (p.get("y_expr") or ""),
                    "fixed": bool(p.get("fixed", False)),
                    "hidden": bool(p.get("hidden", False)),
                    "traj": bool(p.get("traj", False)),
                }
                for pid, p in sorted(self.points.items(), key=lambda kv: kv[0])
            ],
            "constraints": self.constraint_registry.to_list(),
            "links": [
                {
                    "id": lid, "i": l["i"], "j": l["j"],
                    "L": l["L"],
                    "L_expr": (l.get("L_expr") or ""),
                    "hidden": bool(l.get("hidden", False)),
                    "ref": bool(l.get("ref", False)),
                }
                for lid, l in sorted(self.links.items(), key=lambda kv: kv[0])
            ],
            "angles": [
                {
                    "id": aid, "i": a["i"], "j": a["j"], "k": a["k"],
                    "deg": a["deg"],
                    "deg_expr": (a.get("deg_expr") or ""),
                    "hidden": bool(a.get("hidden", False)),
                    "enabled": bool(a.get("enabled", True)),
                }
                for aid, a in sorted(self.angles.items(), key=lambda kv: kv[0])
            ],
            "splines": [
                {
                    "id": sid,
                    "points": list(s.get("points", [])),
                    "hidden": bool(s.get("hidden", False)),
                }
                for sid, s in sorted(self.splines.items(), key=lambda kv: kv[0])
            ],
            "coincides": [
                {"id": cid, "a": c["a"], "b": c["b"], "hidden": bool(c.get("hidden", False)), "enabled": bool(c.get("enabled", True))}
                for cid, c in sorted(self.coincides.items(), key=lambda kv: kv[0])
            ],
            "point_lines": [
                {"id": plid, "p": pl.get("p"), "i": pl.get("i"), "j": pl.get("j"),
                 "hidden": bool(pl.get("hidden", False)), "enabled": bool(pl.get("enabled", True))}
                for plid, pl in sorted(self.point_lines.items(), key=lambda kv: kv[0])
            ],
            "point_splines": [
                {"id": psid, "p": ps.get("p"), "s": ps.get("s"),
                 "hidden": bool(ps.get("hidden", False)), "enabled": bool(ps.get("enabled", True))}
                for psid, ps in sorted(self.point_splines.items(), key=lambda kv: kv[0])
            ],
            "bodies": [
                {"id": bid, "name": b.get("name", f"B{bid}"), "points": list(b.get("points", [])),
                 "hidden": bool(b.get("hidden", False)), "color_name": b.get("color_name", "Blue"),
                 "rigid_edges": list(b.get("rigid_edges", []))}
                for bid, b in sorted(self.bodies.items(), key=lambda kv: kv[0])
            ],
            "output": {
                "enabled": bool(self.output.get("enabled", False)),
                "pivot": self.output.get("pivot"),
                "tip": self.output.get("tip"),
                "rad": float(self.output.get("rad", 0.0)),
            },
            "loads": [
                {
                    "type": str(ld.get("type", "force")),
                    "pid": int(ld.get("pid", -1)),
                    "fx": float(ld.get("fx", 0.0)),
                    "fy": float(ld.get("fy", 0.0)),
                    "mz": float(ld.get("mz", 0.0)),
                }
                for ld in self.loads
            ],
            "load_measures": [
                {
                    "type": str(lm.get("type", "joint_load")),
                    "pid": int(lm.get("pid", -1)),
                    "component": str(lm.get("component", "mag")),
                    "name": str(lm.get("name", "")),
                }
                for lm in self.load_measures
            ],
        }

    def load_dict(self, data: Dict[str, Any], clear_undo: bool = True):
        self.scene.clear()
        self.points.clear(); self.links.clear(); self.angles.clear(); self.splines.clear(); self.bodies.clear(); self.coincides.clear(); self.point_lines.clear(); self.point_splines.clear()
        self._load_arrow_items = []
        self._last_joint_loads = []
        # Load parameters early so expression fields can be evaluated during/after construction.
        self.parameters.load_list(list(data.get("parameters", []) or []))
        self.selected_point_ids.clear()
        self.selected_point_id = None; self.selected_link_id = None; self.selected_angle_id = None; self.selected_spline_id = None; self.selected_body_id = None; self.selected_coincide_id = None; self.selected_point_line_id = None; self.selected_point_spline_id = None
        pts = data.get("points", [])
        # Unified constraints list (Stage-1). If present, it overrides legacy links/angles/coincides.
        constraints_list = data.get("constraints", None)
        if constraints_list:
            from .constraints_registry import ConstraintRegistry as _CR
            lks, angs, spls, coincs, pls, pss = _CR.split_constraints(constraints_list)
        else:
            lks = data.get("links", [])
            angs = data.get("angles", [])
            spls = data.get("splines", [])
            coincs = data.get("coincides", [])
            pls = data.get("point_lines", [])
            pss = data.get("point_splines", [])
        bods = data.get("bodies", [])
        output = data.get("output", {}) or {}
        loads = data.get("loads", []) or []
        load_measures = data.get("load_measures", []) or []
        max_pid = -1
        any_traj_enabled = False
        for p in pts:
            pid = int(p["id"]); max_pid = max(max_pid, pid)
            self._create_point(
                pid,
                float(p.get("x", 0.0)),
                float(p.get("y", 0.0)),
                bool(p.get("fixed", False)),
                bool(p.get("hidden", False)),
                traj_enabled=bool(p.get("traj", False)),
            )
            any_traj_enabled = any_traj_enabled or bool(p.get("traj", False))
            if pid in self.points:
                self.points[pid]["x_expr"] = str(p.get("x_expr", "") or "")
                self.points[pid]["y_expr"] = str(p.get("y_expr", "") or "")
        if any_traj_enabled:
            self.show_trajectories = True
        max_lid = -1
        for l in lks:
            lid = int(l["id"]); max_lid = max(max_lid, lid)
            self._create_link(lid, int(l.get("i")), int(l.get("j")), float(l.get("L", 1.0)),
                              bool(l.get("hidden", False)))
            self.links[lid]["ref"] = bool(l.get("ref", False))
            self.links[lid]["L_expr"] = str(l.get("L_expr", "") or "")
        max_aid = -1
        for a in angs:
            aid = int(a["id"]); max_aid = max(max_aid, aid)
            self._create_angle(aid, int(a.get("i")), int(a.get("j")), int(a.get("k")),
                               float(a.get("deg", 0.0)), bool(a.get("hidden", False)))
            if aid in self.angles:
                self.angles[aid]["deg_expr"] = str(a.get("deg_expr", "") or "")
        max_sid = -1
        for s in spls:
            sid = int(s.get("id", -1)); max_sid = max(max_sid, sid)
            pts = list(s.get("points", []))
            self._create_spline(sid, pts, bool(s.get("hidden", False)))
        max_bid = -1
        for b in bods:
            bid = int(b["id"]); max_bid = max(max_bid, bid)
            self._create_body(bid, b.get("name", f"B{bid}"), list(b.get("points", [])),
                              bool(b.get("hidden", False)), color_name=b.get("color_name", "Blue"))
            if "rigid_edges" in b and b["rigid_edges"]:
                self.bodies[bid]["rigid_edges"] = [tuple(x) for x in b["rigid_edges"]]

        self.output = {
            "enabled": bool(output.get("enabled", False)),
            "pivot": output.get("pivot"),
            "tip": output.get("tip"),
            "rad": float(output.get("rad", 0.0) or 0.0),
        }
        if self.output.get("enabled") and "rad" not in output:
            piv = self.output.get("pivot")
            tip = self.output.get("tip")
            if piv is not None and tip is not None:
                ang = self.get_vector_angle_rad(int(piv), int(tip))
                if ang is not None:
                    self.output["rad"] = float(ang)
        self.loads = []
        for ld in loads:
            pid = int(ld.get("pid", -1))
            if pid not in self.points:
                continue
            ltype = str(ld.get("type", "force")).lower()
            fx = float(ld.get("fx", 0.0))
            fy = float(ld.get("fy", 0.0))
            mz = float(ld.get("mz", 0.0))
            if ltype == "torque":
                self.add_load_torque(pid, mz)
            else:
                self.add_load_force(pid, fx, fy)

        self.load_measures = []
        for lm in load_measures:
            pid = int(lm.get("pid", -1))
            if pid not in self.points:
                continue
            comp = str(lm.get("component", "mag"))
            name = str(lm.get("name", "")) or f"load P{pid} {comp}"
            self.load_measures.append({
                "type": str(lm.get("type", "joint_load")),
                "pid": int(pid),
                "component": comp,
                "name": name,
            })
        
        # --- Coincide constraints ---
        coincs = coincs or []
        max_cid = -1
        for c in coincs:
            try:
                cid = int(c.get("id"))
                a = int(c.get("a")); b = int(c.get("b"))
            except Exception:
                continue
            max_cid = max(max_cid, cid)
            if a in self.points and b in self.points:
                self._create_coincide(
                    cid, a, b,
                    hidden=bool(c.get("hidden", False)),
                    enabled=bool(c.get("enabled", True)),
                )
        self._next_cid = max(max_cid + 1, 0)

        # --- Point-on-line constraints ---
        pls = pls or []
        max_plid = -1
        for pl in pls:
            try:
                plid = int(pl.get("id"))
                p = int(pl.get("p")); i = int(pl.get("i")); j = int(pl.get("j"))
            except Exception:
                continue
            max_plid = max(max_plid, plid)
            if p in self.points and i in self.points and j in self.points and i != j and p != i and p != j:
                self._create_point_line(
                    plid, p, i, j,
                    hidden=bool(pl.get("hidden", False)),
                    enabled=bool(pl.get("enabled", True)),
                )
        self._next_plid = max(max_plid + 1, 0)

        # --- Point-on-spline constraints ---
        pss = pss or []
        max_psid = -1
        for ps in pss:
            try:
                psid = int(ps.get("id"))
                p = int(ps.get("p")); s = int(ps.get("s"))
            except Exception:
                continue
            max_psid = max(max_psid, psid)
            if p in self.points and s in self.splines:
                self._create_point_spline(
                    psid, p, s,
                    hidden=bool(ps.get("hidden", False)),
                    enabled=bool(ps.get("enabled", True)),
                )
        self._next_psid = max(max_psid + 1, 0)

        self._next_pid = max(max_pid + 1, 0)
        self._next_lid = max(max_lid + 1, 0)
        self._next_aid = max(max_aid + 1, 0)
        self._next_sid = max(max_sid + 1, 0)
        self._next_bid = max(max_bid + 1, 0)
        self.mode = "Idle"; self._line_sel = []; self._co_master = None; self._pol_master = None; self._pol_line_sel = []; self._pos_master = None
        self.solve_constraints(); self.update_graphics()
        if self.panel: self.panel.defer_refresh_all()
        if clear_undo: self.stack.clear()
        self.update_status()


    # -------------------- Linkage-style simulation API --------------------
    def set_driver(self, pivot_pid: int, tip_pid: int):
        """Set the input driver as a world-angle vector (pivot -> tip)."""
        self.driver.update({
            "enabled": True,
            "type": "vector",
            "pivot": int(pivot_pid),
            "tip": int(tip_pid),
            "i": None, "j": None, "k": None,
        })
        ang = self.get_vector_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            self.driver["rad"] = float(ang)

    def set_driver_joint(self, i_pid: int, j_pid: int, k_pid: int):
        """Set the input driver as a joint angle (i-j-k), signed and clamped to (-pi, pi]."""
        self.driver.update({
            "enabled": True,
            "type": "joint",
            "pivot": None, "tip": None,
            "i": int(i_pid), "j": int(j_pid), "k": int(k_pid),
        })
        ang = self.get_joint_angle_rad(int(i_pid), int(j_pid), int(k_pid))
        if ang is not None:
            self.driver["rad"] = float(ang)

    def clear_driver(self):
        self.driver = {
            "enabled": False,
            "type": "vector",
            "pivot": None, "tip": None,
            "i": None, "j": None, "k": None,
            "rad": 0.0,
        }

    def set_output(self, pivot_pid: int, tip_pid: int):
        """Set the output measurement vector (pivot -> tip)."""
        self.output["enabled"] = True
        self.output["pivot"] = int(pivot_pid)
        self.output["tip"] = int(tip_pid)
        ang = self.get_vector_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            self.output["rad"] = float(ang)

    def clear_output(self):
        self.output = {"enabled": False, "pivot": None, "tip": None, "rad": 0.0}

    # ---- Quasi-static loads ----
    def add_load_force(self, pid: int, fx: float, fy: float):
        self.loads.append({"type": "force", "pid": int(pid), "fx": float(fx), "fy": float(fy), "mz": 0.0})

    def add_load_torque(self, pid: int, mz: float):
        self.loads.append({"type": "torque", "pid": int(pid), "fx": 0.0, "fy": 0.0, "mz": float(mz)})

    def remove_load_at(self, index: int):
        if 0 <= index < len(self.loads):
            del self.loads[index]

    def clear_loads(self):
        self.loads = []

    def _prompt_add_force(self, pid: int):
        fx, ok = QInputDialog.getDouble(self.win, "Force X", f"P{pid} Fx", 0.0, decimals=4)
        if not ok:
            return
        fy, ok = QInputDialog.getDouble(self.win, "Force Y", f"P{pid} Fy", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_force(pid, fx, fy)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _prompt_add_torque(self, pid: int):
        mz, ok = QInputDialog.getDouble(self.win, "Torque", f"P{pid} Mz", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_torque(pid, mz)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _build_quasistatic_constraints(self, point_ids: List[int]) -> List[Callable[[np.ndarray], float]]:
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        funcs: List[Callable[[np.ndarray], float]] = []

        def _xy(q: np.ndarray, pid: int) -> tuple[float, float]:
            idx = idx_map[pid]
            return float(q[2 * idx]), float(q[2 * idx + 1])

        # Fixed points (x, y lock)
        for pid in point_ids:
            p = self.points[pid]
            if not bool(p.get("fixed", False)):
                continue
            x0, y0 = float(p["x"]), float(p["y"])
            funcs.append(lambda q, pid=pid, x0=x0: _xy(q, pid)[0] - x0)
            funcs.append(lambda q, pid=pid, y0=y0: _xy(q, pid)[1] - y0)

        # Coincide constraints (point-point)
        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1))
            b = int(c.get("b", -1))
            if a not in idx_map or b not in idx_map:
                continue
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[0] - _xy(q, b)[0])
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[1] - _xy(q, b)[1])

        # Point-on-line constraints
        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
            if p_id not in idx_map or i_id not in idx_map or j_id not in idx_map:
                continue

            def _pol(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id) -> float:
                px, py = _xy(q, p_id)
                ax, ay = _xy(q, i_id)
                bx, by = _xy(q, j_id)
                abx, aby = bx - ax, by - ay
                denom = math.hypot(abx, aby)
                if denom < 1e-9:
                    return 0.0
                return ((px - ax) * (-aby) + (py - ay) * abx) / denom

            funcs.append(_pol)

        # Point-on-spline constraints (distance to closest sampled point)
        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = int(ps.get("p", -1))
            s_id = int(ps.get("s", -1))
            if p_id not in idx_map or s_id not in self.splines:
                continue
            spline = self.splines[s_id]
            cp_ids = [pid for pid in spline.get("points", []) if pid in idx_map]
            if len(cp_ids) < 2:
                continue

            def _pos(q: np.ndarray, p_id=p_id, cp_ids=cp_ids) -> float:
                px, py = _xy(q, p_id)
                samples = build_spline_samples([_xy(q, cid) for cid in cp_ids])
                _, _, _, _, dist2 = closest_point_on_samples(px, py, samples)
                return math.sqrt(dist2)

            funcs.append(_pos)

        # Rigid body edges
        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))
        for (i, j, L) in body_edges:
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=L) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            funcs.append(_len)

        # Length constraints (links)
        for l in self.links.values():
            if l.get("ref", False):
                continue
            i, j = int(l.get("i", -1)), int(l.get("j", -1))
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=l["L"]) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            funcs.append(_len)

        # Angle constraints
        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i, j, k = int(a.get("i", -1)), int(a.get("j", -1)), int(a.get("k", -1))
            if i not in idx_map or j not in idx_map or k not in idx_map:
                continue
            target = float(a.get("rad", 0.0))

            def _ang(q: np.ndarray, i=i, j=j, k=k, target=target) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                xk, yk = _xy(q, k)
                v1x, v1y = xi - xj, yi - yj
                v2x, v2y = xk - xj, yk - yj
                if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
                    return 0.0
                cur = angle_between(v1x, v1y, v2x, v2y)
                return clamp_angle_rad(cur - target)

            funcs.append(_ang)

        # Driver constraint (if enabled)
        if self.driver.get("enabled"):
            if self.driver.get("type") == "joint":
                i = self.driver.get("i")
                j = self.driver.get("j")
                k = self.driver.get("k")
                if i in idx_map and j in idx_map and k in idx_map:
                    target = float(self.driver.get("rad", 0.0))

                    def _drv(q: np.ndarray, i=i, j=j, k=k, target=target) -> float:
                        xi, yi = _xy(q, int(i))
                        xj, yj = _xy(q, int(j))
                        xk, yk = _xy(q, int(k))
                        v1x, v1y = xi - xj, yi - yj
                        v2x, v2y = xk - xj, yk - yj
                        if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
                            return 0.0
                        cur = angle_between(v1x, v1y, v2x, v2y)
                        return clamp_angle_rad(cur - target)

                    funcs.append(_drv)
            else:
                piv = self.driver.get("pivot")
                tip = self.driver.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(self.driver.get("rad", 0.0))

                    def _drv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    funcs.append(_drv)
        elif self.output.get("enabled"):
            piv = self.output.get("pivot")
            tip = self.output.get("tip")
            if piv in idx_map and tip in idx_map:
                target = float(self.output.get("rad", 0.0))

                def _odrv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                    px, py = _xy(q, int(piv))
                    tx, ty = _xy(q, int(tip))
                    dx, dy = tx - px, ty - py
                    if abs(dx) + abs(dy) < 1e-12:
                        return 0.0
                    return clamp_angle_rad(math.atan2(dy, dx) - target)

                funcs.append(_odrv)

        return funcs

    def compute_quasistatic_joint_loads(self) -> List[Dict[str, Any]]:
        point_ids = sorted(list(self.points.keys()))
        if not point_ids:
            return []

        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        q = np.array([coord for pid in point_ids for coord in (self.points[pid]["x"], self.points[pid]["y"])], dtype=float)
        ndof = len(q)
        f_ext = np.zeros(ndof, dtype=float)
        torque_map: Dict[int, float] = {pid: 0.0 for pid in point_ids}
        for load in self.loads:
            pid = int(load.get("pid", -1))
            if pid not in self.points:
                continue
            idx = idx_map[pid]
            fx = float(load.get("fx", 0.0))
            fy = float(load.get("fy", 0.0))
            f_ext[2 * idx] += fx
            f_ext[2 * idx + 1] += fy
            torque_map[pid] = torque_map.get(pid, 0.0) + float(load.get("mz", 0.0))

        funcs = self._build_quasistatic_constraints(point_ids)
        if not funcs:
            out = []
            for idx, pid in enumerate(point_ids):
                fx = -float(f_ext[2 * idx])
                fy = -float(f_ext[2 * idx + 1])
                fz = float(torque_map.get(pid, 0.0))
                mag = math.sqrt(fx * fx + fy * fy + fz * fz)
                out.append({"pid": pid, "fx": fx, "fy": fy, "fz": fz, "mag": mag})
            return out

        def eval_constraints(qvec: np.ndarray) -> np.ndarray:
            return np.array([fn(qvec) for fn in funcs], dtype=float)

        eps = 1e-6
        m = len(eval_constraints(q))
        J = np.zeros((m, ndof), dtype=float)
        for i in range(ndof):
            dq = np.zeros_like(q)
            dq[i] = eps
            fp = eval_constraints(q + dq)
            fm = eval_constraints(q - dq)
            J[:, i] = (fp - fm) / (2.0 * eps)

        if J.size == 0:
            reaction = np.zeros_like(f_ext)
        else:
            try:
                lam, *_ = np.linalg.lstsq(J.T, -f_ext, rcond=None)
                reaction = J.T @ lam
            except np.linalg.LinAlgError:
                reaction = np.zeros_like(f_ext)

        out: List[Dict[str, Any]] = []
        for idx, pid in enumerate(point_ids):
            fx = float(reaction[2 * idx])
            fy = float(reaction[2 * idx + 1])
            fz = float(torque_map.get(pid, 0.0))
            mag = math.sqrt(fx * fx + fy * fy + fz * fz)
            out.append({"pid": pid, "fx": fx, "fy": fy, "fz": fz, "mag": mag})
        return out

    # ---- Quasi-static loads ----
    def add_load_force(self, pid: int, fx: float, fy: float):
        self.loads.append({"type": "force", "pid": int(pid), "fx": float(fx), "fy": float(fy), "mz": 0.0})

    def add_load_torque(self, pid: int, mz: float):
        self.loads.append({"type": "torque", "pid": int(pid), "fx": 0.0, "fy": 0.0, "mz": float(mz)})

    def clear_loads(self):
        self.loads = []
    def _build_quasistatic_constraints(
        self,
        point_ids: List[int],
        *,
        include_driver: bool,
        include_output: bool,
    ) -> Tuple[List[Callable[[np.ndarray], float]], List[str], List[Dict[str, Any]]]:
        """Build constraint functions for quasi-static evaluation.

        Returns (funcs, roles, meta) where:
          - roles[i] in {"passive","actuator","output"} for funcs[i]
          - meta[i] provides small bits of info (e.g., type, pivot) for reporting torques.
        """
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        funcs: List[Callable[[np.ndarray], float]] = []
        roles: List[str] = []
        meta: List[Dict[str, Any]] = []

        def _xy(q: np.ndarray, pid: int) -> tuple[float, float]:
            idx = idx_map[pid]
            return float(q[2 * idx]), float(q[2 * idx + 1])

        def _add(fn: Callable[[np.ndarray], float], role: str, info: Optional[Dict[str, Any]] = None):
            funcs.append(fn)
            roles.append(role)
            meta.append(info or {})

        # Fixed points (x, y lock)
        for pid in point_ids:
            p = self.points[pid]
            if not bool(p.get("fixed", False)):
                continue
            x0, y0 = float(p["x"]), float(p["y"])
            _add(lambda q, pid=pid, x0=x0: _xy(q, pid)[0] - x0, "passive", {"type": "fixed_x", "pid": pid})
            _add(lambda q, pid=pid, y0=y0: _xy(q, pid)[1] - y0, "passive", {"type": "fixed_y", "pid": pid})

        # Coincide constraints (point-point)
        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1))
            b = int(c.get("b", -1))
            if a not in idx_map or b not in idx_map:
                continue
            _add(lambda q, a=a, b=b: _xy(q, a)[0] - _xy(q, b)[0], "passive", {"type": "coincide_x", "a": a, "b": b})
            _add(lambda q, a=a, b=b: _xy(q, a)[1] - _xy(q, b)[1], "passive", {"type": "coincide_y", "a": a, "b": b})

        # Point-on-line constraints
        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
            if p_id not in idx_map or i_id not in idx_map or j_id not in idx_map:
                continue

            def _pol(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id) -> float:
                px, py = _xy(q, p_id)
                ax, ay = _xy(q, i_id)
                bx, by = _xy(q, j_id)
                abx, aby = bx - ax, by - ay
                denom = math.hypot(abx, aby)
                if denom < 1e-9:
                    return 0.0
                return ((px - ax) * (-aby) + (py - ay) * abx) / denom

            _add(_pol, "passive", {"type": "point_line", "p": p_id, "i": i_id, "j": j_id})

        # Point-on-spline constraints (distance to closest sampled point)
        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = int(ps.get("p", -1))
            s_id = int(ps.get("s", -1))
            if p_id not in idx_map or s_id not in self.splines:
                continue
            spline = self.splines[s_id]
            cp_ids = [pid for pid in spline.get("points", []) if pid in idx_map]
            if len(cp_ids) < 2:
                continue

            def _pos(q: np.ndarray, p_id=p_id, cp_ids=cp_ids) -> float:
                px, py = _xy(q, p_id)
                samples = build_spline_samples([_xy(q, cid) for cid in cp_ids])
                _, _, _, _, dist2 = closest_point_on_samples(px, py, samples)
                return math.sqrt(dist2)

            _add(_pos, "passive", {"type": "point_spline", "p": p_id, "s": s_id})

        # Rigid body edges
        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))
        for (i, j, L) in body_edges:
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=L) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            _add(_len, "passive", {"type": "rigid_edge", "i": i, "j": j})

        # Length constraints (links)
        for l in self.links.values():
            if l.get("ref", False):
                continue
            i, j = int(l.get("i", -1)), int(l.get("j", -1))
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=l["L"]) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            _add(_len, "passive", {"type": "link_len", "i": i, "j": j})

        # Angle constraints
        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i, j, k = int(a.get("i", -1)), int(a.get("j", -1)), int(a.get("k", -1))
            if i not in idx_map or j not in idx_map or k not in idx_map:
                continue
            target = float(a.get("rad", 0.0))

            def _ang(q: np.ndarray, i=i, j=j, k=k, target=target) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                xk, yk = _xy(q, k)
                v1x, v1y = xi - xj, yi - yj
                v2x, v2y = xk - xj, yk - yj
                if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
                    return 0.0
                cur = angle_between(v1x, v1y, v2x, v2y)
                return clamp_angle_rad(cur - target)

            _add(_ang, "passive", {"type": "angle", "i": i, "j": j, "k": k})

        # Closure / actuator constraints
        # Policy:
        #   - Kinematics uses self.driver (motion input).
        #   - Quasi-static closure uses output constraint if enabled; otherwise uses driver.
        #   - The closure constraint is NOT counted into "Joint Loads" (it is reported separately as a torque).
        if include_output and self.output.get("enabled"):
            piv = self.output.get("pivot")
            tip = self.output.get("tip")
            if piv in idx_map and tip in idx_map:
                target = float(self.output.get("rad", 0.0))

                def _out(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                    px, py = _xy(q, int(piv))
                    tx, ty = _xy(q, int(tip))
                    dx, dy = tx - px, ty - py
                    if abs(dx) + abs(dy) < 1e-12:
                        return 0.0
                    return clamp_angle_rad(math.atan2(dy, dx) - target)

                _add(_out, "output", {"type": "output_angle", "pivot": int(piv), "tip": int(tip)})
        elif include_driver and self.driver.get("enabled"):
            if self.driver.get("type") == "joint":
                i = self.driver.get("i")
                j = self.driver.get("j")
                k = self.driver.get("k")
                if i in idx_map and j in idx_map and k in idx_map:
                    target = float(self.driver.get("rad", 0.0))

                    def _drv(q: np.ndarray, i=i, j=j, k=k, target=target) -> float:
                        xi, yi = _xy(q, int(i))
                        xj, yj = _xy(q, int(j))
                        xk, yk = _xy(q, int(k))
                        v1x, v1y = xi - xj, yi - yj
                        v2x, v2y = xk - xj, yk - yj
                        if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
                            return 0.0
                        cur = angle_between(v1x, v1y, v2x, v2y)
                        return clamp_angle_rad(cur - target)

                    _add(_drv, "actuator", {"type": "driver_joint", "i": int(i), "j": int(j), "k": int(k)})
            else:
                piv = self.driver.get("pivot")
                tip = self.driver.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(self.driver.get("rad", 0.0))

                    def _drv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    _add(_drv, "actuator", {"type": "driver_angle", "pivot": int(piv), "tip": int(tip)})

        return funcs, roles, meta

    def compute_quasistatic_report(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Compute quasi-static joint loads and a small summary.

        - Motion input (driver) is used for kinematics.
        - If output is enabled, quasi-static closure uses output constraint (so driver will not
          appear as a huge 'constraint load' at the input joint).
        - The closure constraint torque is reported separately as input/output torque.
        """
        point_ids = sorted(list(self.points.keys()))
        if not point_ids:
            summary = {"mode": "none", "tau_input": None, "tau_output": None}
            self._last_quasistatic_summary = dict(summary)
            return [], summary

        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        q = np.array([coord for pid in point_ids for coord in (self.points[pid]["x"], self.points[pid]["y"])], dtype=float)
        ndof = len(q)

        # External forces on translational DOFs
        f_ext = np.zeros(ndof, dtype=float)

        # Collect applied torques and convert them to equivalent force couples
        applied_torque: Dict[int, float] = {pid: 0.0 for pid in point_ids}

        def _pick_neighbor(pid: int) -> Optional[int]:
            # Prefer link neighbors, then rigid edges.
            neigh: List[int] = []
            for l in self.links.values():
                if l.get("ref", False):
                    continue
                i, j = int(l.get("i", -1)), int(l.get("j", -1))
                if i == pid and j in idx_map:
                    neigh.append(j)
                elif j == pid and i in idx_map:
                    neigh.append(i)
            if neigh:
                return neigh[0]
            for b in self.bodies.values():
                for (i, j, _L) in b.get("rigid_edges", []):
                    if i == pid and j in idx_map:
                        return int(j)
                    if j == pid and i in idx_map:
                        return int(i)
            return None

        # Apply loads
        for load in self.loads:
            pid = int(load.get("pid", -1))
            if pid not in idx_map:
                continue
            idx = idx_map[pid]
            fx = float(load.get("fx", 0.0))
            fy = float(load.get("fy", 0.0))
            mz = float(load.get("mz", 0.0))
            f_ext[2 * idx] += fx
            f_ext[2 * idx + 1] += fy
            if abs(mz) > 0.0:
                applied_torque[pid] = applied_torque.get(pid, 0.0) + mz

        # Convert each applied torque into a force couple (net force = 0, net moment = Mz)
        for pid, mz in list(applied_torque.items()):
            if abs(mz) < 1e-12:
                continue
            nb = _pick_neighbor(pid)
            if nb is None:
                # No neighbor => cannot form a couple; keep it only for display.
                continue
            i = idx_map[pid]
            j = idx_map[nb]
            xi, yi = float(q[2 * i]), float(q[2 * i + 1])
            xj, yj = float(q[2 * j]), float(q[2 * j + 1])
            rx, ry = (xj - xi), (yj - yi)
            r2 = rx * rx + ry * ry
            if r2 < 1e-12:
                continue
            # F such that r x F = mz  =>  F = (mz/r^2) * (-ry, rx)
            scale = float(mz) / r2
            Fx, Fy = (-ry * scale), (rx * scale)
            # Apply +F at neighbor, -F at pid
            f_ext[2 * j] += Fx
            f_ext[2 * j + 1] += Fy
            f_ext[2 * i] -= Fx
            f_ext[2 * i + 1] -= Fy

        # Build constraints for quasi-static
        use_output = bool(self.output.get("enabled"))
        funcs, roles, meta = self._build_quasistatic_constraints(
            point_ids,
            include_driver=bool(self.driver.get("enabled")) and (not use_output),
            include_output=use_output,
        )

        if not funcs:
            # No constraints -> reactions are just the negative external forces.
            joint_loads: List[Dict[str, Any]] = []
            for idx, pid in enumerate(point_ids):
                fx = -float(f_ext[2 * idx])
                fy = -float(f_ext[2 * idx + 1])
                mag = math.hypot(fx, fy)
                joint_loads.append({"pid": pid, "fx": fx, "fy": fy, "mag": mag})
            self._last_joint_loads = list(joint_loads)
            summary = {"mode": "none", "tau_input": None, "tau_output": None}
            self._last_quasistatic_summary = dict(summary)
            return joint_loads, summary

        def eval_constraints(qvec: np.ndarray) -> np.ndarray:
            return np.array([fn(qvec) for fn in funcs], dtype=float)

        eps = 1e-6
        c0 = eval_constraints(q)
        m = int(c0.size)
        J = np.zeros((m, ndof), dtype=float)
        for i in range(ndof):
            dq = np.zeros_like(q)
            dq[i] = eps
            fp = eval_constraints(q + dq)
            fm = eval_constraints(q - dq)
            J[:, i] = (fp - fm) / (2.0 * eps)

        summary: Dict[str, Any] = {"mode": "output" if use_output else ("driver" if self.driver.get("enabled") else "none")}
        summary["tau_input"] = None
        summary["tau_output"] = None

        if J.size == 0:
            lam = np.zeros(m, dtype=float)
        else:
            try:
                lam, *_ = np.linalg.lstsq(J.T, -f_ext, rcond=None)
            except np.linalg.LinAlgError:
                lam = np.zeros(m, dtype=float)

        # Report closure torques (do NOT include in joint loads table)
        lam = np.asarray(lam, dtype=float)
        for k, role in enumerate(roles):
            if role == "actuator":
                # Driver torque (only used when output is disabled)
                summary["tau_input"] = float(lam[k]) if summary.get("tau_input") is None else float(summary["tau_input"]) + float(lam[k])
            elif role == "output":
                summary["tau_output"] = float(lam[k]) if summary.get("tau_output") is None else float(summary["tau_output"]) + float(lam[k])

        # Joint loads: use passive constraints for pin force, and include output closure for net balance.
        mask_passive = np.array([1.0 if r == "passive" else 0.0 for r in roles], dtype=float)
        mask_net = np.array(
            [1.0 if (r == "passive" or (use_output and r == "output")) else 0.0 for r in roles],
            dtype=float,
        )
        fixed_types = {"fixed_x", "fixed_y"}
        mask_fixed = np.array(
            [1.0 if meta[k].get("type") in fixed_types else 0.0 for k in range(len(roles))],
            dtype=float,
        )
        lam_passive = lam * mask_passive
        lam_net = lam * mask_net
        lam_fixed = lam * mask_fixed
        reaction_passive = J.T @ lam_passive if J.size else np.zeros_like(f_ext)
        reaction_net = J.T @ lam_net if J.size else np.zeros_like(f_ext)
        reaction_fixed = J.T @ lam_fixed if J.size else np.zeros_like(f_ext)

        applied_force: Dict[int, Tuple[float, float]] = {pid: (0.0, 0.0) for pid in point_ids}
        for load in self.loads:
            pid = int(load.get("pid", -1))
            if pid not in applied_force:
                continue
            fx = float(load.get("fx", 0.0))
            fy = float(load.get("fy", 0.0))
            if abs(fx) > 0.0 or abs(fy) > 0.0:
                cur_fx, cur_fy = applied_force[pid]
                applied_force[pid] = (cur_fx + fx, cur_fy + fy)

        joint_loads: List[Dict[str, Any]] = []
        for idx, pid in enumerate(point_ids):
            point = self.points[pid]
            if bool(point.get("fixed", False)):
                fx = float(reaction_fixed[2 * idx])
                fy = float(reaction_fixed[2 * idx + 1])
            else:
                applied_fx, applied_fy = applied_force.get(pid, (0.0, 0.0))
                if abs(applied_fx) > 0.0 or abs(applied_fy) > 0.0:
                    fx = float(reaction_net[2 * idx])
                    fy = float(reaction_net[2 * idx + 1])
                else:
                    best_fx, best_fy, best_mag = 0.0, 0.0, 0.0
                    for k, role in enumerate(roles):
                        if role != "passive":
                            continue
                        if meta[k].get("type") in fixed_types:
                            continue
                        fx_k = float(J[k, 2 * idx] * lam[k])
                        fy_k = float(J[k, 2 * idx + 1] * lam[k])
                        mag_k = math.hypot(fx_k, fy_k)
                        if mag_k > best_mag:
                            best_fx, best_fy, best_mag = fx_k, fy_k, mag_k
                    fx, fy = best_fx, best_fy
            mag = math.hypot(fx, fy)
            joint_loads.append({"pid": pid, "fx": fx, "fy": fy, "mag": mag})

        self._last_joint_loads = list(joint_loads)
        self._last_quasistatic_summary = dict(summary)
        return joint_loads, summary

    def compute_quasistatic_joint_loads(self) -> List[Dict[str, Any]]:
        # Backwards-compatible wrapper for UI code that expects just the table rows.
        joint_loads, _summary = self.compute_quasistatic_report()
        return joint_loads


    # ---- Trajectories ----
    def set_show_trajectories(self, enabled: bool, reset: bool = False):
        self.show_trajectories = bool(enabled)
        if reset:
            self.reset_trajectories()
        self.update_graphics()

    def reset_trajectories(self):
        for pid, p in self.points.items():
            titem = p.get("traj_item")
            if titem is not None:
                titem.reset_path(p["x"], p["y"])

    def append_trajectories(self):
        if not self.show_trajectories or self._drag_active:
            return
        for pid, p in self.points.items():
            if not bool(p.get("traj", False)):
                continue
            titem = p.get("traj_item")
            if titem is not None:
                titem.add_point(p["x"], p["y"])

    # ---- Measurements ----
    def add_measure_vector(self, pivot_pid: int, tip_pid: int):
        name = f"vec P{int(pivot_pid)}->P{int(tip_pid)}"
        self.measures.append({"type": "vector", "pivot": int(pivot_pid), "tip": int(tip_pid), "name": name})

    def add_measure_joint(self, i_pid: int, j_pid: int, k_pid: int):
        name = f"ang P{int(i_pid)}-P{int(j_pid)}-P{int(k_pid)}"
        self.measures.append({"type": "joint", "i": int(i_pid), "j": int(j_pid), "k": int(k_pid), "name": name})

    def clear_measures(self):
        self.measures = []

    def remove_measure_at(self, index: int):
        if index < 0 or index >= len(self.measures):
            return
        self.measures.pop(index)

    def add_load_measure_joint(self, pid: int, component: str):
        component = component.lower()
        label = {"fx": "Fx", "fy": "Fy", "mag": "Mag"}.get(component, component)
        name = f"load P{int(pid)} {label}"
        self.load_measures.append({"type": "joint_load", "pid": int(pid), "component": component, "name": name})

    def clear_load_measures(self):
        self.load_measures = []

    def get_measure_values_deg(self) -> List[tuple[str, Optional[float]]]:
        """Return measurement values in degrees.

        If a sweep has started (Play), values are reported relative to the Play-start pose
        (i.e., value==0 at the starting pose).
        """
        out: List[tuple[str, Optional[float]]] = []
        for m in self.measures:
            nm = str(m.get("name", ""))
            abs_deg: Optional[float] = None
            if m.get("type") == "vector":
                ang = self.get_vector_angle_rad(int(m.get("pivot")), int(m.get("tip")))
                abs_deg = None if ang is None else math.degrees(ang)
            elif m.get("type") == "joint":
                ang = self.get_joint_angle_rad(int(m.get("i")), int(m.get("j")), int(m.get("k")))
                abs_deg = None if ang is None else math.degrees(ang)

            if abs_deg is None:
                out.append((nm, None))
                continue

            if nm in self._sim_zero_meas_deg:
                out.append((nm, self._rel_deg(abs_deg, float(self._sim_zero_meas_deg[nm]))))
            else:
                out.append((nm, abs_deg))
        return out
        return out

    def get_load_measure_values(self) -> List[tuple[str, Optional[float]]]:
        out: List[tuple[str, Optional[float]]] = []
        if not self.load_measures:
            return out
        load_map: Dict[int, Dict[str, float]] = {}
        for jl in self.compute_quasistatic_joint_loads():
            pid = int(jl.get("pid", -1))
            if pid < 0:
                continue
            load_map[pid] = {
                "fx": float(jl.get("fx", 0.0)),
                "fy": float(jl.get("fy", 0.0)),
                "mag": float(jl.get("mag", 0.0)),
            }
        for m in self.load_measures:
            nm = str(m.get("name", ""))
            pid = int(m.get("pid", -1))
            comp = str(m.get("component", "mag")).lower()
            val = None
            if pid in load_map and comp in load_map[pid]:
                val = float(load_map[pid][comp])
            out.append((nm, val))
        return out

    # ---- Angles ----
    def get_vector_angle_rad(self, pivot_pid: int, tip_pid: int) -> Optional[float]:
        if pivot_pid not in self.points or tip_pid not in self.points:
            return None
        p = self.points[pivot_pid]
        q = self.points[tip_pid]
        dx = q["x"] - p["x"]
        dy = q["y"] - p["y"]
        if abs(dx) + abs(dy) < 1e-12:
            return None
        return math.atan2(dy, dx)

    def get_joint_angle_rad(self, i_pid: int, j_pid: int, k_pid: int) -> Optional[float]:
        if i_pid not in self.points or j_pid not in self.points or k_pid not in self.points:
            return None
        pi, pj, pk = self.points[i_pid], self.points[j_pid], self.points[k_pid]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
            return None
        return angle_between(v1x, v1y, v2x, v2y)

    # ---- Relative-zero helpers (for simulation) ----
    @staticmethod
    def _rel_deg(abs_deg: float, base_deg: float) -> float:
        """Return relative angle in [0, 360) degrees."""
        return (abs_deg - base_deg) % 360.0

    def _get_input_angle_abs_rad(self) -> Optional[float]:
        if not self.driver.get("enabled"):
            return None
        if self.driver.get("type") == "joint":
            i, j, k = self.driver.get("i"), self.driver.get("j"), self.driver.get("k")
            if i is None or j is None or k is None:
                return None
            return self.get_joint_angle_rad(int(i), int(j), int(k))
        piv = self.driver.get("pivot")
        tip = self.driver.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_vector_angle_rad(int(piv), int(tip))

    def _get_output_angle_abs_rad(self) -> Optional[float]:
        if not self.output.get("enabled"):
            return None
        piv = self.output.get("pivot")
        tip = self.output.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_vector_angle_rad(int(piv), int(tip))

    def get_input_angle_deg(self) -> Optional[float]:
        """Current input angle in degrees.

        When a sweep has started (Play), 0° is defined as the pose at Play-start.
        """
        ang = self._get_input_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_input_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_input_rad)
        return self._rel_deg(abs_deg, base_deg)


    def get_output_angle_deg(self) -> Optional[float]:
        """Current output angle in degrees (relative to Play-start if available)."""
        ang = self._get_output_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_output_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_output_rad)
        return self._rel_deg(abs_deg, base_deg)


    def drive_to_deg(self, deg: float, iters: int = 80):
        """Drive the mechanism to a *relative* input angle (deg) and solve constraints.

        If Play has started, 0° corresponds to the Play-start pose.
        """
        if not self.driver.get("enabled") and not self.output.get("enabled"):
            return

        # Target = (Play-start absolute angle) + delta
        if self.driver.get("enabled"):
            if self._sim_zero_input_rad is not None:
                target = float(self._sim_zero_input_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            self.driver["rad"] = float(target)
        else:
            if self._sim_zero_output_rad is not None:
                target = float(self._sim_zero_output_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            self.output["rad"] = float(target)
        self.solve_constraints(iters=iters)
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()

    # ---- Pose snapshots ----
    def capture_initial_pose_if_needed(self):
        if self._pose_initial is None:
            self._pose_initial = self.snapshot_points()

    def mark_sim_start_pose(self):
        """Capture pose + set the 'relative zero' for input/output/measures."""
        self._pose_last_sim_start = self.snapshot_points()
        self.capture_initial_pose_if_needed()

        # Set relative-zero angles based on the current pose.
        self._sim_zero_input_rad = self._get_input_angle_abs_rad()
        self._sim_zero_output_rad = self._get_output_angle_abs_rad()
        if self._sim_zero_output_rad is not None:
            self.output["rad"] = float(self._sim_zero_output_rad)

        self._sim_zero_meas_deg = {}
        for (nm, val) in self.get_measure_values_deg():
            # At this moment get_measure_values_deg returns ABS (since _sim_zero_meas_deg is cleared)
            if val is not None:
                self._sim_zero_meas_deg[str(nm)] = float(val)

    def update_sim_start_pose_snapshot(self):
        """Update the stored sweep start pose without touching the relative-zero angles."""
        self._pose_last_sim_start = self.snapshot_points()
        self.capture_initial_pose_if_needed()

    def reset_pose_to_sim_start(self) -> bool:
        if not self._pose_last_sim_start:
            return False
        self.apply_points_snapshot(self._pose_last_sim_start)
        if self.driver.get("enabled") and self._sim_zero_input_rad is not None:
            self.driver["rad"] = float(self._sim_zero_input_rad)
        if self.output.get("enabled") and self._sim_zero_output_rad is not None:
            self.output["rad"] = float(self._sim_zero_output_rad)
        self.solve_constraints()
        self.update_graphics()
        if self.panel:
            self.panel.defer_refresh_all(keep_selection=True)
        return True

    def reset_pose_to_initial(self) -> bool:
        if not self._pose_initial:
            return False
        self.apply_points_snapshot(self._pose_initial)
        self.solve_constraints()
        self.update_graphics()
        if self.panel:
            self.panel.defer_refresh_all(keep_selection=True)
        return True
