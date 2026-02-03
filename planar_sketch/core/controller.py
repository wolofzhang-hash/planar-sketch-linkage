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
from PyQt6.QtGui import QPainterPath, QColor, QImage, QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QMenu, QInputDialog, QGraphicsPixmapItem, QMessageBox

import numpy as np

import numpy as np

from .commands import Command, CommandStack
from .geometry import clamp_angle_rad, angle_between, build_spline_samples, closest_point_on_samples
from .solver import ConstraintSolver
from .constraints_registry import ConstraintRegistry
from .parameters import ParameterRegistry
from .scipy_kinematics import SciPyKinematicSolver
from ..ui.items import (
    TextMarker,
    PointItem,
    LinkItem,
    AngleItem,
    CoincideItem,
    PointLineItem,
    SplineItem,
    PointSplineItem,
    TrajectoryItem,
    ForceArrowItem,
    TorqueArrowItem,
)
from ..ui.i18n import tr
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
        self.display_precision = 3
        self.load_arrow_width = 1.6
        self.torque_arrow_width = 1.6
        self.ui_language = "en"

        self.background_image: Dict[str, Any] = {
            "path": None,
            "visible": True,
            "opacity": 0.6,
            "grayscale": False,
            "scale": 1.0,
            "pos": (0.0, 0.0),
        }
        self._background_item: Optional[QGraphicsPixmapItem] = None
        self._background_image_original: Optional[QImage] = None
        self._background_pick_points: List[QPointF] = []

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
        self._last_model_action: Optional[str] = None
        self._continuous_model_action: Optional[str] = None
        self._last_scene_pos: Optional[Tuple[float, float]] = None
        self._last_point_pos: Optional[Tuple[float, float]] = None

        # --- Linkage-style simulation configuration ---
        # Driver: either a world-angle of a vector (pivot->tip) or a joint angle (i-j-k).
        # type: "vector" or "joint"
        self.driver: Dict[str, Any] = self._default_driver()
        # Multiple drivers (primary driver is drivers[0] when present)
        self.drivers: List[Dict[str, Any]] = []
        # Output: measured angle of (pivot -> tip) relative to world +X.
        self.output: Dict[str, Any] = self._default_output()
        # Multiple outputs (primary output is outputs[0] when present)
        self.outputs: List[Dict[str, Any]] = []
        # Extra measurements: a list of {type,name,...} items.
        self.measures: List[Dict[str, Any]] = []
        # Load measurements: a list of {type,name,...} items.
        self.load_measures: List[Dict[str, Any]] = []
        # Quasi-static loads: list of {type,pid,fx,fy,mz}
        self.loads: List[Dict[str, Any]] = []
        # Display items for load arrows.
        self._load_arrow_items: List[ForceArrowItem] = []
        self._torque_arrow_items: List[TorqueArrowItem] = []
        self._last_joint_loads: List[Dict[str, Any]] = []
        self._last_quasistatic_summary: Dict[str, Any] = {}
        # Pose snapshots for "reset to initial".
        self._pose_initial: Optional[Dict[int, Tuple[float, float]]] = None
        self._pose_last_sim_start: Optional[Dict[int, Tuple[float, float]]] = None

        # Simulation "relative zero" (0° == pose at Play-start)
        self._sim_zero_input_rad: Optional[float] = None
        self._sim_zero_output_rad: Optional[float] = None
        self._sim_zero_driver_rad: List[Optional[float]] = []
        self._sim_zero_meas_deg: Dict[str, float] = {}
        self.sweep_settings: Dict[str, float] = {"start": 0.0, "end": 360.0, "step": 200.0}

    @staticmethod
    def _default_driver() -> Dict[str, Any]:
        return {
            "enabled": False,
            "type": "vector",
            "pivot": None, "tip": None,
            "i": None, "j": None, "k": None,
            "rad": 0.0,
            "sweep_start": None,
            "sweep_end": None,
        }

    @staticmethod
    def _default_output() -> Dict[str, Any]:
        return {"enabled": False, "pivot": None, "tip": None, "rad": 0.0}

    def _normalize_driver(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            sweep_start = float(data.get("sweep_start", self.sweep_settings.get("start", 0.0)))
        except Exception:
            sweep_start = float(self.sweep_settings.get("start", 0.0))
        try:
            sweep_end = float(data.get("sweep_end", self.sweep_settings.get("end", 360.0)))
        except Exception:
            sweep_end = float(self.sweep_settings.get("end", 360.0))
        return {
            "enabled": bool(data.get("enabled", True)),
            "type": str(data.get("type", "vector")),
            "pivot": data.get("pivot"),
            "tip": data.get("tip"),
            "i": data.get("i"),
            "j": data.get("j"),
            "k": data.get("k"),
            "rad": float(data.get("rad", 0.0) or 0.0),
            "sweep_start": sweep_start,
            "sweep_end": sweep_end,
        }

    def _normalize_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "enabled": bool(data.get("enabled", True)),
            "pivot": data.get("pivot"),
            "tip": data.get("tip"),
            "rad": float(data.get("rad", 0.0) or 0.0),
        }

    def _active_drivers(self) -> List[Dict[str, Any]]:
        return [d for d in self.drivers if d.get("enabled", False)]

    def _active_outputs(self) -> List[Dict[str, Any]]:
        return [o for o in self.outputs if o.get("enabled", False)]

    def _sync_primary_driver(self) -> None:
        if self.drivers:
            self.driver = dict(self.drivers[0])
        else:
            self.driver = self._default_driver()

    def _sync_primary_output(self) -> None:
        if self.outputs:
            self.output = dict(self.outputs[0])
        else:
            self.output = self._default_output()

    def _primary_driver(self) -> Optional[Dict[str, Any]]:
        return self.drivers[0] if self.drivers else None

    def _primary_output(self) -> Optional[Dict[str, Any]]:
        return self.outputs[0] if self.outputs else None

    def _check_overconstraint_and_warn(self) -> None:
        if not hasattr(self.win, "statusBar"):
            return
        over, detail = self.check_overconstraint()
        if not over:
            return
        lang = getattr(self, "ui_language", "en")
        QMessageBox.warning(
            self.win,
            tr(lang, "sim.overconstrained_title"),
            tr(lang, "sim.overconstrained_body").format(detail=detail),
        )

    def status_text(self) -> str:
        if self.mode == "CreateLine":
            if self._continuous_model_action == "CreateLine":
                return "Create Line (continuous): select 2 points (LMB)."
            return "Create Line: select 2 points (LMB)."
        if self.mode == "CreatePoint":
            if self._continuous_model_action == "CreatePoint":
                return "Create Point (continuous): click to place points."
            return "Create Point: click to place a point."
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
        if self.mode == "BackgroundImagePick":
            if len(self._background_pick_points) == 0:
                return "Background Image: click the first reference point."
            if len(self._background_pick_points) == 1:
                return "Background Image: click the second reference point."
            return "Background Image: configuring..."
        return "Idle | BoxSelect: drag LMB on empty. Ctrl+Box toggles. Ctrl+Click toggles points."

    def format_number(self, value: Optional[float], unit: str = "", default: str = "--") -> str:
        if value is None:
            return default
        try:
            precision = int(self.display_precision)
        except Exception:
            precision = 3
        return f"{float(value):.{precision}f}{unit}"

    def update_status(self):
        self.win.statusBar().showMessage(self.status_text())

    def has_background_image(self) -> bool:
        return self._background_item is not None and self._background_image_original is not None

    def load_background_image(self, path: str) -> bool:
        image = QImage(path)
        if image.isNull():
            QMessageBox.critical(self.win, "Background Image", "Failed to load image.")
            return False
        self._background_image_original = image
        self.background_image["path"] = path
        self._ensure_background_item()
        self._apply_background_pixmap()
        self._start_background_pick()
        return True

    def clear_background_image(self):
        if self._background_item is not None:
            self.scene.removeItem(self._background_item)
        self._background_item = None
        self._background_image_original = None
        self.background_image["path"] = None
        self._background_pick_points = []
        if self.mode == "BackgroundImagePick":
            self.mode = "Idle"
        self.update_status()

    def set_background_visible(self, visible: bool):
        self.background_image["visible"] = bool(visible)
        if self._background_item is not None:
            self._background_item.setVisible(bool(visible))

    def set_background_opacity(self, opacity: float):
        opacity = max(0.0, min(1.0, float(opacity)))
        self.background_image["opacity"] = opacity
        if self._background_item is not None:
            self._background_item.setOpacity(opacity)

    def set_background_grayscale(self, grayscale: bool):
        self.background_image["grayscale"] = bool(grayscale)
        if self._background_item is not None:
            self._apply_background_pixmap()

    def _ensure_background_item(self):
        if self._background_item is None:
            self._background_item = QGraphicsPixmapItem()
            self._background_item.setZValue(-1000)
            self._background_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(self._background_item)
        self._background_item.setVisible(bool(self.background_image.get("visible", True)))
        self._background_item.setOpacity(float(self.background_image.get("opacity", 0.6)))

    def _apply_background_pixmap(self):
        if self._background_item is None or self._background_image_original is None:
            return
        if self.background_image.get("grayscale", False):
            img = self._background_image_original.convertToFormat(QImage.Format.Format_Grayscale8)
        else:
            img = self._background_image_original
        self._background_item.setPixmap(QPixmap.fromImage(img))

    def _start_background_pick(self):
        if self._background_item is None or self._background_image_original is None:
            return
        self.mode = "BackgroundImagePick"
        self._background_pick_points = []
        self.background_image["scale"] = 1.0
        self.background_image["pos"] = (0.0, 0.0)
        self._background_item.setScale(1.0)
        self._background_item.setPos(0.0, 0.0)
        self.update_status()

    def on_background_pick(self, scene_pos: QPointF) -> bool:
        if self.mode != "BackgroundImagePick":
            return False
        if self._background_item is None or self._background_image_original is None:
            return False
        item_pos = self._background_item.mapFromScene(scene_pos)
        if (
            item_pos.x() < 0
            or item_pos.y() < 0
            or item_pos.x() > self._background_image_original.width()
            or item_pos.y() > self._background_image_original.height()
        ):
            return True
        self._background_pick_points.append(item_pos)
        if len(self._background_pick_points) < 2:
            self.update_status()
            return True
        self._finish_background_pick()
        return True

    def _finish_background_pick(self):
        if len(self._background_pick_points) < 2:
            return
        p1_img = self._background_pick_points[0]
        p2_img = self._background_pick_points[1]
        dx = p2_img.x() - p1_img.x()
        dy = p2_img.y() - p1_img.y()
        pixel_dist = (dx * dx + dy * dy) ** 0.5
        if pixel_dist <= 1e-6:
            QMessageBox.warning(self.win, "Background Image", "Reference points are too close.")
            self.mode = "Idle"
            self.update_status()
            return
        dist, ok = QInputDialog.getDouble(
            self.win,
            "Background Image Scale",
            "Distance between the two points (model units):",
            100.0,
            0.000001,
            1e9,
            6,
        )
        if not ok:
            self.mode = "Idle"
            self.update_status()
            return
        x1, ok = QInputDialog.getDouble(
            self.win,
            "Background Image Position",
            "First point X coordinate (model units):",
            0.0,
            -1e9,
            1e9,
            6,
        )
        if not ok:
            self.mode = "Idle"
            self.update_status()
            return
        y1, ok = QInputDialog.getDouble(
            self.win,
            "Background Image Position",
            "First point Y coordinate (model units):",
            0.0,
            -1e9,
            1e9,
            6,
        )
        if not ok:
            self.mode = "Idle"
            self.update_status()
            return
        scale = float(dist) / float(pixel_dist)
        pos_x = float(x1) - scale * p1_img.x()
        pos_y = float(y1) - scale * p1_img.y()
        self.background_image["scale"] = scale
        self.background_image["pos"] = (pos_x, pos_y)
        if self._background_item is not None:
            self._background_item.setScale(scale)
            self._background_item.setPos(pos_x, pos_y)
        self.mode = "Idle"
        self.update_status()

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
        self.load_dict(data, clear_undo=False, action="apply a model snapshot")

    def _confirm_stop_replay(self, action: str) -> bool:
        win = getattr(self, "win", None)
        sim_panel = getattr(win, "sim_panel", None) if win else None
        animation_tab = getattr(sim_panel, "animation_tab", None) if sim_panel else None
        if animation_tab is not None and hasattr(animation_tab, "confirm_stop_replay"):
            return animation_tab.confirm_stop_replay(action)
        return True

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

    def solve_constraints(
        self,
        iters: int = 60,
        drag_pid: Optional[int] = None,
        drag_target_pid: Optional[int] = None,
        drag_target_xy: Optional[Tuple[float, float]] = None,
        drag_alpha: float = 0.45,
    ):
        """Solve geometric constraints (interactive PBD backend).

        Notes:
        - Called frequently (e.g. during point dragging).
        - Must keep the dragged point locked via drag_pid to avoid fighting user input.
        - drag_target_pid + drag_target_xy allows soft dragging: we attract a point
          toward the cursor while still enforcing constraints.
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
        active_drivers = self._active_drivers()
        active_outputs = self._active_outputs()
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
                    "type": "vector",
                    "pivot": out.get("pivot"),
                    "tip": out.get("tip"),
                    "rad": out.get("rad", 0.0),
                }
                drive_sources.append(entry)

        for drv in drive_sources:
            dtype = str(drv.get("type", "vector"))
            if dtype == "joint":
                i = drv.get("i")
                k = drv.get("k")
                if i is not None:
                    driven_pids.add(int(i))
                if k is not None:
                    driven_pids.add(int(k))
            else:
                tip = drv.get("tip")
                if tip is not None:
                    driven_pids.add(int(tip))

        # Allow editing lengths that belong to the active drivers (avoid false OVER).
        driver_length_pairs: set[frozenset[int]] = set()
        for drv in drive_sources:
            dtype = str(drv.get("type", "vector"))
            if dtype == "joint":
                i = drv.get("i")
                j = drv.get("j")
                k = drv.get("k")
                if i is not None and j is not None:
                    driver_length_pairs.add(frozenset({int(i), int(j)}))
                if j is not None and k is not None:
                    driver_length_pairs.add(frozenset({int(j), int(k)}))
            else:
                piv = drv.get("pivot")
                tip = drv.get("tip")
                if piv is not None and tip is not None:
                    driver_length_pairs.add(frozenset({int(piv), int(tip)}))

        # PBD-style iterations
        for _ in range(max(1, int(iters))):
            if (
                drag_target_pid is not None
                and drag_target_xy is not None
                and drag_target_pid in self.points
                and drag_target_pid not in driven_pids
            ):
                tp = self.points[drag_target_pid]
                if not bool(tp.get("fixed", False)):
                    tx, ty = float(drag_target_xy[0]), float(drag_target_xy[1])
                    a = max(0.0, min(1.0, float(drag_alpha)))
                    tp["x"] = float(tp["x"]) + a * (tx - float(tp["x"]))
                    tp["y"] = float(tp["y"]) + a * (ty - float(tp["y"]))
            # (1) Hard drivers first
            for drv in drive_sources:
                dtype = str(drv.get("type", "vector"))
                if dtype == "joint":
                    i = drv.get("i")
                    j = drv.get("j")
                    k = drv.get("k")
                    if i is None or j is None or k is None:
                        continue
                    i = int(i); j = int(j); k = int(k)
                    if drag_pid in (i, j, k):
                        continue
                    if i in self.points and j in self.points and k in self.points:
                        pi = self.points[i]
                        pj = self.points[j]
                        pk = self.points[k]
                        lock_i = bool(pi.get("fixed", False)) or (drag_pid == i)
                        lock_j = bool(pj.get("fixed", False)) or (drag_pid == j)
                        lock_k = bool(pk.get("fixed", False)) or (drag_pid == k)
                        ConstraintSolver.enforce_driver_joint_angle(
                            pi, pj, pk,
                            float(drv.get("rad", 0.0)),
                            lock_i, lock_j, lock_k,
                        )
                else:
                    piv = drv.get("pivot")
                    tip = drv.get("tip")
                    if piv is None or tip is None:
                        continue
                    piv = int(piv); tip = int(tip)
                    if drag_pid in (piv, tip):
                        continue
                    if piv in self.points and tip in self.points:
                        piv_pt = self.points[piv]
                        tip_pt = self.points[tip]
                        lock_piv = bool(piv_pt.get("fixed", False)) or (drag_pid == piv)
                        lock_tip = bool(tip_pt.get("fixed", False)) or (drag_pid == tip)
                        ConstraintSolver.enforce_driver_angle(
                            piv_pt, tip_pt,
                            float(drv.get("rad", 0.0)),
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

    def check_overconstraint(self) -> Tuple[bool, str]:
        """Check for structural over-constraint (constraint count > DOF)."""
        n_points = len(self.points)
        if n_points == 0:
            return False, "No points"

        adjacency: Dict[int, set[int]] = {pid: set() for pid in self.points.keys()}

        def _link(a: Optional[int], b: Optional[int]) -> None:
            if a is None or b is None:
                return
            if a not in adjacency or b not in adjacency:
                return
            adjacency[a].add(b)
            adjacency[b].add(a)

        for l in self.links.values():
            if l.get("ref", False):
                continue
            _link(l.get("i"), l.get("j"))

        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i, j, k = a.get("i"), a.get("j"), a.get("k")
            _link(i, j)
            _link(j, k)
            _link(i, k)

        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            _link(c.get("a"), c.get("b"))

        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p, i, j = pl.get("p"), pl.get("i"), pl.get("j")
            _link(p, i)
            _link(p, j)

        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = ps.get("p")
            s_id = ps.get("s")
            if p_id is None or s_id not in self.splines:
                continue
            for cid in self.splines[s_id].get("points", []) or []:
                _link(p_id, cid)

        for b in self.bodies.values():
            for (i, j, _L) in b.get("rigid_edges", []) or []:
                _link(i, j)

        visited: set[int] = set()
        components: List[set[int]] = []
        for pid in adjacency:
            if pid in visited:
                continue
            stack = [pid]
            comp: set[int] = set()
            visited.add(pid)
            while stack:
                cur = stack.pop()
                comp.add(cur)
                for nb in adjacency[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
            components.append(comp)

        details: List[str] = []
        over_any = False
        for idx, comp in enumerate(components, start=1):
            dof = 2 * len(comp)
            fixed = sum(1 for pid in comp if bool(self.points.get(pid, {}).get("fixed", False)))
            coincide = sum(
                1
                for c in self.coincides.values()
                if bool(c.get("enabled", True)) and int(c.get("a", -1)) in comp and int(c.get("b", -1)) in comp
            )
            point_lines = sum(
                1
                for pl in self.point_lines.values()
                if bool(pl.get("enabled", True))
                and int(pl.get("p", -1)) in comp
                and int(pl.get("i", -1)) in comp
                and int(pl.get("j", -1)) in comp
            )
            point_splines = sum(
                1
                for ps in self.point_splines.values()
                if bool(ps.get("enabled", True))
                and int(ps.get("p", -1)) in comp
                and all(int(cid) in comp for cid in self.splines.get(int(ps.get("s", -1)), {}).get("points", []) or [])
            )
            links = sum(
                1
                for l in self.links.values()
                if not bool(l.get("ref", False))
                and int(l.get("i", -1)) in comp
                and int(l.get("j", -1)) in comp
            )
            angles = sum(
                1
                for a in self.angles.values()
                if bool(a.get("enabled", True))
                and int(a.get("i", -1)) in comp
                and int(a.get("j", -1)) in comp
                and int(a.get("k", -1)) in comp
            )
            rigid_edges = 0
            for b in self.bodies.values():
                rigid_edges += sum(1 for i, j, _L in b.get("rigid_edges", []) if i in comp and j in comp)

            total = (
                fixed * 2
                + coincide * 2
                + point_lines
                + point_splines
                + links
                + angles
                + rigid_edges
            )
            over = total > dof
            over_any = over_any or over
            details.append(
                f"component#{idx}: constraints={total} > dof={dof} "
                f"(fixed={fixed}, links={links}, angles={angles}, coincide={coincide}, "
                f"line={point_lines}, spline={point_splines}, rigid={rigid_edges})"
            )

        return over_any, " | ".join(details)

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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._active_drivers() and not self._active_outputs():
            return False, "Driver or output not set"
        primary_driver = self._primary_driver()
        primary_output = self._primary_output()
        if primary_driver and primary_driver.get("enabled"):
            if self._sim_zero_input_rad is not None:
                target = float(self._sim_zero_input_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_driver["rad"] = float(target)
            self.drivers[0] = primary_driver
            self._sync_primary_driver()
        elif primary_output and primary_output.get("enabled"):
            if self._sim_zero_output_rad is not None:
                target = float(self._sim_zero_output_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_output["rad"] = float(target)
            self.outputs[0] = primary_output
            self._sync_primary_output()
        return self.solve_constraints_scipy(max_nfev=max_nfev)

    def drive_to_multi_deg_scipy(self, deg_list: List[float], max_nfev: int = 250) -> tuple[bool, str]:
        """Drive multiple active drivers to relative angles (deg) and solve with SciPy."""
        active_drivers = self._active_drivers()
        if not active_drivers:
            return False, "Driver not set"
        for idx, drv in enumerate(active_drivers):
            if idx >= len(deg_list):
                break
            base_rad = None
            if idx < len(self._sim_zero_driver_rad):
                base_rad = self._sim_zero_driver_rad[idx]
            if base_rad is None:
                base_rad = self._get_driver_angle_abs_rad(drv)
            target = math.radians(float(deg_list[idx]))
            if base_rad is not None:
                target = float(base_rad) + target
            drv["rad"] = float(target)
        self._sync_primary_driver()
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
        cmark = TextMarker("△", font_point_size=14.0, bold=True)
        self.points[pid]["constraint_marker"] = cmark
        self.scene.addItem(cmark)
        dmark = TextMarker("↻", font_point_size=14.0, bold=True)
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
        if not self._confirm_stop_replay("modify the model"):
            return
        pid = self._next_pid; self._next_pid += 1
        ctrl = self
        self._last_model_action = "CreatePoint"
        self._last_point_pos = (float(x), float(y))
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
        if not self._confirm_stop_replay("modify the model"):
            return
        if i == j or i not in self.points or j not in self.points: return
        lid = self._next_lid; self._next_lid += 1
        p1, p2 = self.points[i], self.points[j]
        L = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
        ctrl = self
        self._last_model_action = "CreateLine"
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
            if not self._confirm_stop_replay("modify the model"):
                return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
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
        if not self._confirm_stop_replay("modify the model"):
            return
        ctrl = self
        class MoveSystem(Command):
            name = "Move"
            def do(self_):
                ctrl.apply_points_snapshot(after)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.refresh_fast()
            def undo(self_):
                ctrl.apply_points_snapshot(before)
                ctrl.solve_constraints(); ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.refresh_fast()
        self.stack.push(MoveSystem())

    def cmd_move_point_by_table(self, pid: int, x: float, y: float):
        if not self._confirm_stop_replay("modify the model"):
            return
        if pid not in self.points: return
        before = self.snapshot_points()
        self.points[pid]["x"] = float(x); self.points[pid]["y"] = float(y)
        self.solve_constraints(drag_pid=pid)
        after = self.snapshot_points()
        self.cmd_move_system(before, after)

    def on_drag_update(self, pid: int, nx: float, ny: float):
        if not self._confirm_stop_replay("modify the model"):
            return
        if pid not in self.points: return
        if not self._drag_active:
            self._drag_active = True
            self._drag_pid = pid
            self._drag_before = self.snapshot_points()
        self.solve_constraints(
            drag_target_pid=pid,
            drag_target_xy=(float(nx), float(ny)),
            drag_pid=None,
        )
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

    def begin_create_line(self, continuous: bool = False):
        self.commit_drag_if_any()
        self.mode = "CreateLine"
        self._continuous_model_action = "CreateLine" if continuous else None
        self._line_sel = []
        self.update_status()

    def begin_create_point(self, continuous: bool = False):
        self.commit_drag_if_any()
        self.mode = "CreatePoint"
        self._continuous_model_action = "CreatePoint" if continuous else None
        self.update_status()

    def on_scene_clicked_create_point(self, pos: QPointF):
        self.cmd_add_point(float(pos.x()), float(pos.y()))
        if self._continuous_model_action != "CreatePoint":
            self.mode = "Idle"
            self._continuous_model_action = None
        self.update_status()

    def update_last_scene_pos(self, pos: QPointF):
        self._last_scene_pos = (float(pos.x()), float(pos.y()))

    def repeat_last_model_action(self):
        self.commit_drag_if_any()
        if self._last_model_action == "CreatePoint":
            pos = self._last_scene_pos or self._last_point_pos or (0.0, 0.0)
            self.cmd_add_point(pos[0], pos[1])
            return
        if self._last_model_action == "CreateLine":
            self.begin_create_line()
            return
        if self.win and self.win.statusBar():
            self.win.statusBar().showMessage("No previous modeling action.")

    def begin_coincide(self, master: int):
        self.commit_drag_if_any()
        self.mode = "Coincide"
        self._continuous_model_action = None
        self._co_master = master
        self.update_status()

    def begin_point_on_line(self, master: int):
        """Start point-on-line creation: choose 2 points to define the line."""
        self.commit_drag_if_any()
        self.mode = "PointOnLine"
        self._continuous_model_action = None
        self._pol_master = int(master)
        self._pol_line_sel = []
        self.update_status()

    def begin_point_on_spline(self, master: int):
        """Start point-on-spline creation: choose a spline to constrain."""
        self.commit_drag_if_any()
        self.mode = "PointOnSpline"
        self._continuous_model_action = None
        self._pos_master = int(master)
        self.update_status()

    def on_point_clicked_create_line(self, pid: int):
        if pid not in self.points or self.is_point_effectively_hidden(pid) or (not self.show_points_geometry): return
        if pid in self._line_sel: return
        self._line_sel.append(pid)
        if len(self._line_sel) >= 2:
            i, j = self._line_sel[0], self._line_sel[1]
            if self._continuous_model_action == "CreateLine":
                self.mode = "CreateLine"
            else:
                self.mode = "Idle"
                self._continuous_model_action = None
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
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.toggle_point(pid)
        else:
            self.select_point_single(pid, keep_others=False)
        self.update_status()

    def _selected_points_for_angle(self) -> List[int]:
        if self.panel:
            ids = self.panel.selected_points_from_table(include_hidden=False)
        else:
            ids = sorted(self.selected_point_ids)
        return [pid for pid in ids if pid in self.points]

    def _add_angle_from_selection(self):
        ids = self._selected_points_for_angle()
        if len(ids) < 3:
            QMessageBox.information(self.win, "Need 3 points", "Select 3 points (2nd is vertex).")
            return
        i, j, k = ids[0], ids[1], ids[2]
        if len({i, j, k}) < 3:
            QMessageBox.information(self.win, "Need 3 points", "Select 3 distinct points (2nd is vertex).")
            return
        pi, pj, pk = self.points[i], self.points[j], self.points[k]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        deg = math.degrees(angle_between(v1x, v1y, v2x, v2y))
        self.cmd_add_angle(i, j, k, deg)

    def show_empty_context_menu(self, global_pos, scene_pos: QPointF):
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(tr(lang, "context.create_point"), lambda: self.cmd_add_point(scene_pos.x(), scene_pos.y()))
        m.addAction(tr(lang, "context.create_line"), self.begin_create_line)
        m.addAction(tr(lang, "context.create_spline_from_selection"), self._add_spline_from_selection)
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
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(
            tr(lang, "context.fix") if not p.get("fixed", False) else tr(lang, "context.unfix"),
            lambda: self.cmd_set_point_fixed(pid, not p.get("fixed", False)),
        )
        m.addAction(
            tr(lang, "context.hide") if not p.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_point_hidden(pid, not p.get("hidden", False)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.coincide_with"), lambda: self.begin_coincide(pid))

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
            sub_drv = m.addMenu(tr(lang, "context.set_driver"))

            # Vector driver: choose a neighbor as tip
            sub_vec = sub_drv.addMenu(tr(lang, "context.vector_pivot_tip"))
            for nb in nbrs:
                sub_vec.addAction(
                    tr(lang, "context.pivot_tip").format(pivot=pid, tip=nb),
                    lambda nb=nb: self.set_driver(pid, nb),
                )

            # Joint driver: choose two neighbors as i and k
            sub_joint = sub_drv.addMenu(tr(lang, "context.joint_angle"))
            if len(nbrs) >= 2:
                for i in nbrs:
                    for k in nbrs:
                        if i == k:
                            continue
                        sub_joint.addAction(f"P{i}-P{pid}-P{k}", lambda i=i, k=k: self.set_driver_joint(i, pid, k))

            sub_drv.addSeparator()
            sub_drv.addAction(tr(lang, "context.clear_driver"), self.clear_driver)

            sub_meas = m.addMenu(tr(lang, "context.add_measurement"))

            sub_mvec = sub_meas.addMenu(tr(lang, "context.vector_world"))
            for nb in nbrs:
                sub_mvec.addAction(f"V(P{pid}->P{nb})", lambda nb=nb: self.add_measure_vector(pid, nb))

            sub_mjoint = sub_meas.addMenu(tr(lang, "context.joint_angle"))
            if len(nbrs) >= 2:
                for i in nbrs:
                    for k in nbrs:
                        if i == k:
                            continue
                        sub_mjoint.addAction(f"A(P{i}-P{pid}-P{k})", lambda i=i, k=k: self.add_measure_joint(i, pid, k))

            sub_load_meas = sub_meas.addMenu(tr(lang, "context.load"))
            sub_load_meas.addAction(tr(lang, "context.joint_load_fx"), lambda: self.add_load_measure_joint(pid, "fx"))
            sub_load_meas.addAction(tr(lang, "context.joint_load_fy"), lambda: self.add_load_measure_joint(pid, "fy"))
            sub_load_meas.addAction(tr(lang, "context.joint_load_mag"), lambda: self.add_load_measure_joint(pid, "mag"))

            sub_meas.addSeparator()
            sub_meas.addAction(tr(lang, "context.clear_measurements"), self.clear_measures)

            sub_out = m.addMenu(tr(lang, "context.set_output"))
            for nb in nbrs:
                sub_out.addAction(
                    tr(lang, "context.pivot_tip").format(pivot=pid, tip=nb),
                    lambda nb=nb: self.set_output(pid, nb),
                )
            sub_out.addSeparator()
            sub_out.addAction(tr(lang, "context.clear_output"), self.clear_output)

            sub_load = m.addMenu(tr(lang, "context.loads"))
            sub_load.addAction(tr(lang, "context.add_force"), lambda: self._prompt_add_force(pid))
            sub_load.addAction(tr(lang, "context.add_torque"), lambda: self._prompt_add_torque(pid))
            sub_load.addSeparator()
            sub_load.addAction(tr(lang, "context.clear_loads"), self.clear_loads)

        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_point(pid))
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
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        l = self.links[lid]
        m.addAction(
            tr(lang, "context.hide") if not l.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_link_hidden(lid, not l.get("hidden", False)),
        )
        m.addAction(
            tr(lang, "context.set_as_constraint") if l.get("ref", False) else tr(lang, "context.set_as_reference"),
            lambda: self.cmd_set_link_reference(lid, not l.get("ref", False)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_link(lid))
        m.exec(global_pos)
        self.update_status()


    def show_coincide_context_menu(self, cid: int, global_pos):
        self.commit_drag_if_any()
        if cid not in self.coincides:
            return
        self.select_coincide_single(cid)
        c = self.coincides[cid]
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(
            tr(lang, "context.hide") if not c.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_coincide_hidden(cid, not c.get("hidden", False)),
        )
        m.addAction(
            tr(lang, "context.disable") if c.get("enabled", True) else tr(lang, "context.enable"),
            lambda: self.cmd_set_coincide_enabled(cid, not c.get("enabled", True)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_coincide(cid))
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
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(
            tr(lang, "context.hide") if not pl.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_point_line_hidden(plid, not pl.get("hidden", False)),
        )
        m.addAction(
            tr(lang, "context.disable") if pl.get("enabled", True) else tr(lang, "context.enable"),
            lambda: self.cmd_set_point_line_enabled(plid, not pl.get("enabled", True)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_point_line(plid))
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
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(
            tr(lang, "context.hide") if not ps.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_point_spline_hidden(psid, not ps.get("hidden", False)),
        )
        m.addAction(
            tr(lang, "context.disable") if ps.get("enabled", True) else tr(lang, "context.enable"),
            lambda: self.cmd_set_point_spline_enabled(psid, not ps.get("enabled", True)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_point_spline(psid))
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
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(
            tr(lang, "context.hide") if not s.get("hidden", False) else tr(lang, "context.show"),
            lambda: self.cmd_set_spline_hidden(sid, not s.get("hidden", False)),
        )
        m.addSeparator()
        m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_spline(sid))
        m.exec(global_pos)
        self.update_status()
        try:
            if self.panel: self.panel.defer_refresh_all(keep_selection=True)
        except Exception:
            pass

    def update_graphics(self):
        driver_marker_map: Dict[int, str] = {}
        active_drivers = self._active_drivers()
        show_driver_index = len(active_drivers) > 1
        for idx, drv in enumerate(active_drivers):
            driver_type = str(drv.get("type", "vector"))
            if driver_type == "joint":
                pid = drv.get("j")
            else:
                pid = drv.get("pivot")
            if pid is None:
                continue
            label = "↻" if not show_driver_index else f"↻{idx + 1}"
            if int(pid) in driver_marker_map:
                driver_marker_map[int(pid)] = f"{driver_marker_map[int(pid)]},{label}"
            else:
                driver_marker_map[int(pid)] = label
        output_marker_pid = None
        primary_output = self._primary_output()
        if primary_output and primary_output.get("enabled"):
            pid = primary_output.get("pivot")
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
            if pid in driver_marker_map:
                dmark.setText(driver_marker_map[pid])
            else:
                dmark.setText("↻")
            dmark_bounds = dmark.boundingRect()
            dmark.setPos(p["x"] + 8, p["y"] - dmark_bounds.height() - 4)
            show_driver = (
                self.show_dim_markers
                and pid in driver_marker_map
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
            if tau_out is None:
                tmark.setText("τ")
            else:
                tmark.setText(f"τ={self.format_number(tau_out)}")
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
                mk.setText(f"({self.format_number(curL)})")
            else:
                mk.setText(f"L={self.format_number(l['L'])}")
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
            for item in self._torque_arrow_items:
                item.setVisible(False)
            return

        load_vectors: List[Dict[str, float]] = []
        torque_vectors: List[Dict[str, float]] = []
        for ld in self.loads:
            if str(ld.get("type", "force")).lower() != "force":
                if str(ld.get("type", "")).lower() == "torque":
                    pid = int(ld.get("pid", -1))
                    if pid not in self.points:
                        continue
                    if self.is_point_effectively_hidden(pid) or (not self.show_points_geometry):
                        continue
                    mz = float(ld.get("mz", 0.0))
                    if abs(mz) < 1e-12:
                        continue
                    p = self.points[pid]
                    torque_vectors.append({
                        "x": p["x"],
                        "y": p["y"],
                        "mz": mz,
                        "label": self.format_number(mz),
                    })
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
            load_vectors.append({
                "x": p["x"],
                "y": p["y"],
                "fx": fx,
                "fy": fy,
                "label": self.format_number(mag),
            })

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
            load_vectors.append({
                "x": p["x"],
                "y": p["y"],
                "fx": fx,
                "fy": fy,
                "label": self.format_number(mag),
            })

        needed = len(load_vectors)
        while len(self._load_arrow_items) < needed:
            item = ForceArrowItem(QColor(220, 40, 40))
            item.set_line_width(self.load_arrow_width)
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
            item.set_line_width(self.load_arrow_width)
            vec = load_vectors[idx]
            item.set_vector(
                vec["x"],
                vec["y"],
                vec["fx"],
                vec["fy"],
                scale=scale,
                label=str(vec.get("label", "")),
            )

        torque_needed = len(torque_vectors)
        while len(self._torque_arrow_items) < torque_needed:
            item = TorqueArrowItem(QColor(220, 40, 40))
            item.set_line_width(self.torque_arrow_width)
            self._torque_arrow_items.append(item)
            self.scene.addItem(item)
        torque_mags = [abs(vec["mz"]) for vec in torque_vectors]
        max_torque = max(torque_mags) if torque_mags else 0.0
        target_radius = 26.0
        torque_scale = (target_radius / max_torque) if max_torque > 1e-9 else 1.0
        torque_scale = max(0.2, min(3.0, torque_scale))
        for idx, item in enumerate(self._torque_arrow_items):
            if idx >= torque_needed:
                item.setVisible(False)
                continue
            item.set_line_width(self.torque_arrow_width)
            vec = torque_vectors[idx]
            item.set_torque(
                vec["x"],
                vec["y"],
                vec["mz"],
                scale=torque_scale,
                label=str(vec.get("label", "")),
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "2.7.0",
            "display_precision": int(getattr(self, "display_precision", 3)),
            "load_arrow_width": float(getattr(self, "load_arrow_width", 1.6)),
            "torque_arrow_width": float(getattr(self, "torque_arrow_width", 1.6)),
            "parameters": self.parameters.to_list(),
            "background_image": {
                "path": self.background_image.get("path"),
                "visible": bool(self.background_image.get("visible", True)),
                "opacity": float(self.background_image.get("opacity", 0.6)),
                "grayscale": bool(self.background_image.get("grayscale", False)),
                "scale": float(self.background_image.get("scale", 1.0)),
                "pos": list(self.background_image.get("pos", (0.0, 0.0))),
            },
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
            "driver": {
                "enabled": bool(self.driver.get("enabled", False)),
                "type": str(self.driver.get("type", "vector")),
                "pivot": self.driver.get("pivot"),
                "tip": self.driver.get("tip"),
                "i": self.driver.get("i"),
                "j": self.driver.get("j"),
                "k": self.driver.get("k"),
                "rad": float(self.driver.get("rad", 0.0)),
                "sweep_start": self.driver.get("sweep_start"),
                "sweep_end": self.driver.get("sweep_end"),
            },
            "drivers": [
                {
                    "enabled": bool(d.get("enabled", False)),
                    "type": str(d.get("type", "vector")),
                    "pivot": d.get("pivot"),
                    "tip": d.get("tip"),
                    "i": d.get("i"),
                    "j": d.get("j"),
                    "k": d.get("k"),
                    "rad": float(d.get("rad", 0.0)),
                    "sweep_start": d.get("sweep_start"),
                    "sweep_end": d.get("sweep_end"),
                }
                for d in self.drivers
            ],
            "output": {
                "enabled": bool(self.output.get("enabled", False)),
                "pivot": self.output.get("pivot"),
                "tip": self.output.get("tip"),
                "rad": float(self.output.get("rad", 0.0)),
            },
            "outputs": [
                {
                    "enabled": bool(o.get("enabled", False)),
                    "pivot": o.get("pivot"),
                    "tip": o.get("tip"),
                    "rad": float(o.get("rad", 0.0)),
                }
                for o in self.outputs
            ],
            "measures": [
                {
                    "type": str(m.get("type", "")),
                    "name": str(m.get("name", "")),
                    "pivot": m.get("pivot"),
                    "tip": m.get("tip"),
                    "i": m.get("i"),
                    "j": m.get("j"),
                    "k": m.get("k"),
                }
                for m in self.measures
            ],
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
            "sweep": {
                "start": float(self.sweep_settings.get("start", 0.0)),
                "end": float(self.sweep_settings.get("end", 360.0)),
                "step": float(self.sweep_settings.get("step", 200.0)),
            },
        }

    def load_dict(self, data: Dict[str, Any], clear_undo: bool = True, action: str = "load a new model") -> bool:
        if not self._confirm_stop_replay(action):
            return False
        if hasattr(self.win, "sim_panel"):
            self.win.sim_panel.stop()
            if hasattr(self.win.sim_panel, "animation_tab"):
                self.win.sim_panel.animation_tab.stop_replay()
        self._drag_active = False
        self._drag_pid = None
        self._drag_before = None
        background_info = data.get("background_image") or data.get("background") or {}
        self.background_image = {
            "path": None,
            "visible": True,
            "opacity": 0.6,
            "grayscale": False,
            "scale": 1.0,
            "pos": (0.0, 0.0),
        }
        if isinstance(background_info, dict):
            self.background_image["path"] = background_info.get("path")
            self.background_image["visible"] = bool(background_info.get("visible", True))
            self.background_image["opacity"] = float(background_info.get("opacity", 0.6))
            self.background_image["grayscale"] = bool(background_info.get("grayscale", False))
            self.background_image["scale"] = float(background_info.get("scale", 1.0))
            pos = background_info.get("pos", (0.0, 0.0))
            try:
                self.background_image["pos"] = (float(pos[0]), float(pos[1]))
            except Exception:
                self.background_image["pos"] = (0.0, 0.0)
        sweep_info = data.get("sweep", {}) or {}
        try:
            sweep_start = float(sweep_info.get("start", self.sweep_settings.get("start", 0.0)))
        except Exception:
            sweep_start = self.sweep_settings.get("start", 0.0)
        try:
            sweep_end = float(sweep_info.get("end", self.sweep_settings.get("end", 360.0)))
        except Exception:
            sweep_end = self.sweep_settings.get("end", 360.0)
        try:
            sweep_step = float(sweep_info.get("step", self.sweep_settings.get("step", 200.0)))
        except Exception:
            sweep_step = self.sweep_settings.get("step", 200.0)
        sweep_step = abs(sweep_step)
        if sweep_step == 0:
            sweep_step = float(self.sweep_settings.get("step", 200.0)) or 200.0
        self.sweep_settings = {"start": sweep_start, "end": sweep_end, "step": sweep_step}
        if hasattr(self.win, "sim_panel"):
            self.win.sim_panel.apply_sweep_settings(self.sweep_settings)
        self.scene.blockSignals(True)
        try:
            self.scene.clear()
            self.points.clear(); self.links.clear(); self.angles.clear(); self.splines.clear(); self.bodies.clear(); self.coincides.clear(); self.point_lines.clear(); self.point_splines.clear()
            self._background_item = None
            self._background_image_original = None
        finally:
            self.scene.blockSignals(False)
        self._load_arrow_items = []
        self._torque_arrow_items = []
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
        if constraints_list:
            spls = data.get("splines", [])
            legacy_point_lines = data.get("point_lines", []) or []
            legacy_point_splines = data.get("point_splines", []) or []
            existing_plids = {int(pl.get("id", -1)) for pl in (pls or [])}
            existing_psids = {int(ps.get("id", -1)) for ps in (pss or [])}
            for pl in legacy_point_lines:
                try:
                    plid = int(pl.get("id", -1))
                except Exception:
                    continue
                if plid in existing_plids:
                    continue
                pls = list(pls or []) + [pl]
                existing_plids.add(plid)
            for ps in legacy_point_splines:
                try:
                    psid = int(ps.get("id", -1))
                except Exception:
                    continue
                if psid in existing_psids:
                    continue
                pss = list(pss or []) + [ps]
                existing_psids.add(psid)
        bods = data.get("bodies", [])
        driver = data.get("driver", {}) or {}
        output = data.get("output", {}) or {}
        drivers_list = data.get("drivers", None)
        outputs_list = data.get("outputs", None)
        measures = data.get("measures", []) or []
        self.display_precision = int(data.get("display_precision", getattr(self, "display_precision", 3)))
        self.load_arrow_width = float(data.get("load_arrow_width", getattr(self, "load_arrow_width", 1.6)))
        self.torque_arrow_width = float(data.get("torque_arrow_width", getattr(self, "torque_arrow_width", 1.6)))
        loads = data.get("loads", []) or []
        load_measures = data.get("load_measures", []) or []
        bg_path = self.background_image.get("path")
        if bg_path:
            image = QImage(bg_path)
            if not image.isNull():
                self._background_image_original = image
                self._ensure_background_item()
                self._apply_background_pixmap()
                scale = float(self.background_image.get("scale", 1.0))
                pos = self.background_image.get("pos", (0.0, 0.0))
                if self._background_item is not None:
                    self._background_item.setScale(scale)
                    self._background_item.setPos(float(pos[0]), float(pos[1]))
                self.set_background_visible(bool(self.background_image.get("visible", True)))
                self.set_background_opacity(float(self.background_image.get("opacity", 0.6)))
                self.set_background_grayscale(bool(self.background_image.get("grayscale", False)))
            else:
                self.background_image["path"] = None
                self._background_image_original = None
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

        self.drivers = []
        if isinstance(drivers_list, list) and drivers_list:
            for drv in drivers_list:
                if not isinstance(drv, dict):
                    continue
                normalized = self._normalize_driver(drv)
                if "rad" not in drv:
                    normalized["_needs_rad"] = True
                self.drivers.append(normalized)
        elif isinstance(driver, dict):
            legacy_driver = self._normalize_driver(driver)
            if legacy_driver.get("enabled"):
                if "rad" not in driver:
                    legacy_driver["_needs_rad"] = True
                self.drivers.append(legacy_driver)

        for drv in self.drivers:
            if not drv.pop("_needs_rad", False):
                continue
            dtype = str(drv.get("type", "vector"))
            if dtype == "joint":
                i = drv.get("i")
                j = drv.get("j")
                k = drv.get("k")
                if i is not None and j is not None and k is not None:
                    ang = self.get_joint_angle_rad(int(i), int(j), int(k))
                    if ang is not None:
                        drv["rad"] = float(ang)
            else:
                piv = drv.get("pivot")
                tip = drv.get("tip")
                if piv is not None and tip is not None:
                    ang = self.get_vector_angle_rad(int(piv), int(tip))
                    if ang is not None:
                        drv["rad"] = float(ang)
        self._sync_primary_driver()

        self.outputs = []
        if isinstance(outputs_list, list) and outputs_list:
            for out in outputs_list:
                if not isinstance(out, dict):
                    continue
                normalized = self._normalize_output(out)
                if "rad" not in out:
                    normalized["_needs_rad"] = True
                self.outputs.append(normalized)
        elif isinstance(output, dict):
            legacy_output = self._normalize_output(output)
            if legacy_output.get("enabled"):
                if "rad" not in output:
                    legacy_output["_needs_rad"] = True
                self.outputs.append(legacy_output)

        for out in self.outputs:
            if not out.pop("_needs_rad", False):
                continue
            piv = out.get("pivot")
            tip = out.get("tip")
            if piv is not None and tip is not None:
                ang = self.get_vector_angle_rad(int(piv), int(tip))
                if ang is not None:
                    out["rad"] = float(ang)
        self._sync_primary_output()
        self.measures = []
        for m in measures:
            mtype = str(m.get("type", "")).lower()
            name = str(m.get("name", ""))
            if mtype == "vector":
                pivot = m.get("pivot")
                tip = m.get("tip")
                if pivot is None or tip is None:
                    continue
                if int(pivot) in self.points and int(tip) in self.points:
                    self.measures.append({
                        "type": "vector",
                        "pivot": int(pivot),
                        "tip": int(tip),
                        "name": name or f"vec P{int(pivot)}->P{int(tip)}",
                    })
            elif mtype == "joint":
                i = m.get("i")
                j = m.get("j")
                k = m.get("k")
                if i is None or j is None or k is None:
                    continue
                if int(i) in self.points and int(j) in self.points and int(k) in self.points:
                    self.measures.append({
                        "type": "joint",
                        "i": int(i),
                        "j": int(j),
                        "k": int(k),
                        "name": name or f"ang P{int(i)}-P{int(j)}-P{int(k)}",
                    })
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
        return True


    # -------------------- Linkage-style simulation API --------------------
    def set_driver(self, pivot_pid: int, tip_pid: int):
        """Set the input driver as a world-angle vector (pivot -> tip)."""
        driver = self._normalize_driver({
            "enabled": True,
            "type": "vector",
            "pivot": int(pivot_pid),
            "tip": int(tip_pid),
            "i": None, "j": None, "k": None,
            "sweep_start": self.sweep_settings.get("start", 0.0),
            "sweep_end": self.sweep_settings.get("end", 360.0),
        })
        ang = self.get_vector_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            driver["rad"] = float(ang)
        self.drivers.insert(0, driver)
        self._sync_primary_driver()

    def set_driver_joint(self, i_pid: int, j_pid: int, k_pid: int):
        """Set the input driver as a joint angle (i-j-k), signed and clamped to (-pi, pi]."""
        driver = self._normalize_driver({
            "enabled": True,
            "type": "joint",
            "pivot": None, "tip": None,
            "i": int(i_pid), "j": int(j_pid), "k": int(k_pid),
            "sweep_start": self.sweep_settings.get("start", 0.0),
            "sweep_end": self.sweep_settings.get("end", 360.0),
        })
        ang = self.get_joint_angle_rad(int(i_pid), int(j_pid), int(k_pid))
        if ang is not None:
            driver["rad"] = float(ang)
        self.drivers.insert(0, driver)
        self._sync_primary_driver()

    def clear_driver(self):
        self.drivers = []
        self._sim_zero_driver_rad = []
        self._sync_primary_driver()

    def set_output(self, pivot_pid: int, tip_pid: int):
        """Set the output measurement vector (pivot -> tip)."""
        output = self._normalize_output({
            "enabled": True,
            "pivot": int(pivot_pid),
            "tip": int(tip_pid),
        })
        ang = self.get_vector_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            output["rad"] = float(ang)
        self.outputs.insert(0, output)
        self._sync_primary_output()

    def clear_output(self):
        self.outputs = []
        self._sync_primary_output()

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
        active_drivers = self._active_drivers()
        active_outputs = self._active_outputs()
        if active_drivers:
            for drv in active_drivers:
                if drv.get("type") == "joint":
                    i = drv.get("i")
                    j = drv.get("j")
                    k = drv.get("k")
                    if i in idx_map and j in idx_map and k in idx_map:
                        target = float(drv.get("rad", 0.0))

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
                    piv = drv.get("pivot")
                    tip = drv.get("tip")
                    if piv in idx_map and tip in idx_map:
                        target = float(drv.get("rad", 0.0))

                        def _drv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                            px, py = _xy(q, int(piv))
                            tx, ty = _xy(q, int(tip))
                            dx, dy = tx - px, ty - py
                            if abs(dx) + abs(dy) < 1e-12:
                                return 0.0
                            return clamp_angle_rad(math.atan2(dy, dx) - target)

                        funcs.append(_drv)
        elif active_outputs:
            for out in active_outputs:
                piv = out.get("pivot")
                tip = out.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(out.get("rad", 0.0))

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
        if include_output:
            for out in self._active_outputs():
                piv = out.get("pivot")
                tip = out.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(out.get("rad", 0.0))

                    def _out(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    _add(_out, "output", {"type": "output_angle", "pivot": int(piv), "tip": int(tip)})
        elif include_driver:
            for drv in self._active_drivers():
                if drv.get("type") == "joint":
                    i = drv.get("i")
                    j = drv.get("j")
                    k = drv.get("k")
                    if i in idx_map and j in idx_map and k in idx_map:
                        target = float(drv.get("rad", 0.0))

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
                    piv = drv.get("pivot")
                    tip = drv.get("tip")
                    if piv in idx_map and tip in idx_map:
                        target = float(drv.get("rad", 0.0))

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
        applied_force: Dict[int, Tuple[float, float]] = {pid: (0.0, 0.0) for pid in point_ids}

        # Collect applied torques and convert them to equivalent force couples
        applied_torque: Dict[int, float] = {pid: 0.0 for pid in point_ids}

        def _pick_torque_neighbor(pid: int, qvec: np.ndarray) -> Optional[int]:
            # Prefer link neighbors, then rigid edges. Choose the farthest neighbor
            # to reduce the required force magnitude for a given torque.
            neigh: List[int] = []
            for l in self.links.values():
                if l.get("ref", False):
                    continue
                i, j = int(l.get("i", -1)), int(l.get("j", -1))
                if i == pid and j in idx_map:
                    neigh.append(j)
                elif j == pid and i in idx_map:
                    neigh.append(i)
            if not neigh:
                for b in self.bodies.values():
                    for (i, j, _L) in b.get("rigid_edges", []):
                        if i == pid and j in idx_map:
                            neigh.append(int(j))
                        elif j == pid and i in idx_map:
                            neigh.append(int(i))
            if not neigh:
                return None
            i = idx_map[pid]
            xi, yi = float(qvec[2 * i]), float(qvec[2 * i + 1])
            best_nb = None
            best_r2 = -1.0
            for nb in neigh:
                j = idx_map[nb]
                dx = float(qvec[2 * j]) - xi
                dy = float(qvec[2 * j + 1]) - yi
                r2 = dx * dx + dy * dy
                if r2 > best_r2:
                    best_r2 = r2
                    best_nb = nb
            return best_nb

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
            if abs(fx) > 0.0 or abs(fy) > 0.0:
                cur_fx, cur_fy = applied_force[pid]
                applied_force[pid] = (cur_fx + fx, cur_fy + fy)
            if abs(mz) > 0.0:
                applied_torque[pid] = applied_torque.get(pid, 0.0) + mz

        # Convert each applied torque into a force couple (net force = 0, net moment = Mz)
        for pid, mz in list(applied_torque.items()):
            if abs(mz) < 1e-12:
                continue
            nb = _pick_torque_neighbor(pid, q)
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
        use_output = bool(self._active_outputs())
        funcs, roles, meta = self._build_quasistatic_constraints(
            point_ids,
            include_driver=bool(self._active_drivers()) and (not use_output),
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

        summary: Dict[str, Any] = {"mode": "output" if use_output else ("driver" if self._active_drivers() else "none")}
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
        mask_nonrigid = np.array(
            [
                1.0
                if (roles[k] == "passive" and meta[k].get("type") not in {"rigid_edge", *fixed_types})
                else 0.0
                for k in range(len(roles))
            ],
            dtype=float,
        )
        lam_passive = lam * mask_passive
        lam_net = lam * mask_net
        lam_fixed = lam * mask_fixed
        lam_nonrigid = lam * mask_nonrigid
        reaction_passive = J.T @ lam_passive if J.size else np.zeros_like(f_ext)
        reaction_net = J.T @ lam_net if J.size else np.zeros_like(f_ext)
        reaction_fixed = J.T @ lam_fixed if J.size else np.zeros_like(f_ext)
        reaction_nonrigid = J.T @ lam_nonrigid if J.size else np.zeros_like(f_ext)

        link_reactions: Dict[int, Tuple[float, float, float]] = {}
        if J.size:
            for k, info in enumerate(meta):
                if info.get("type") != "link_len":
                    continue
                for end_key in ("i", "j"):
                    pid = int(info.get(end_key, -1))
                    if pid not in idx_map:
                        continue
                    idx = idx_map[pid]
                    fx_k = float(J[k, 2 * idx] * lam[k])
                    fy_k = float(J[k, 2 * idx + 1] * lam[k])
                    mag_k = math.hypot(fx_k, fy_k)
                    if mag_k <= 0.0:
                        continue
                    prev = link_reactions.get(pid)
                    if prev is None or mag_k > prev[2]:
                        link_reactions[pid] = (fx_k, fy_k, mag_k)

        spline_reactions: Dict[int, Tuple[float, float, float]] = {}
        if J.size:
            for k, info in enumerate(meta):
                if info.get("type") != "point_spline":
                    continue
                pid = int(info.get("p", -1))
                if pid not in idx_map:
                    continue
                idx = idx_map[pid]
                fx_k = float(J[k, 2 * idx] * lam[k])
                fy_k = float(J[k, 2 * idx + 1] * lam[k])
                mag_k = math.hypot(fx_k, fy_k)
                if mag_k <= 0.0:
                    continue
                prev = spline_reactions.get(pid)
                if prev is None or mag_k > prev[2]:
                    spline_reactions[pid] = (fx_k, fy_k, mag_k)

        joint_loads: List[Dict[str, Any]] = []
        for idx, pid in enumerate(point_ids):
            point = self.points[pid]
            if bool(point.get("fixed", False)):
                fx = float(reaction_fixed[2 * idx])
                fy = float(reaction_fixed[2 * idx + 1])
            elif pid in link_reactions:
                fx, fy, _mag = link_reactions[pid]
            elif pid in spline_reactions:
                fx, fy, _mag = spline_reactions[pid]
            else:
                applied_fx, applied_fy = applied_force.get(pid, (0.0, 0.0))
                if abs(applied_fx) > 0.0 or abs(applied_fy) > 0.0:
                    fx = float(reaction_net[2 * idx])
                    fy = float(reaction_net[2 * idx + 1])
                else:
                    fx = float(reaction_nonrigid[2 * idx])
                    fy = float(reaction_nonrigid[2 * idx + 1])
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
        self.load_measures = []

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

    def remove_load_measure_at(self, index: int):
        if index < 0 or index >= len(self.load_measures):
            return
        self.load_measures.pop(index)

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
        primary = self._primary_driver()
        if not primary or not primary.get("enabled"):
            return None
        if primary.get("type") == "joint":
            i, j, k = primary.get("i"), primary.get("j"), primary.get("k")
            if i is None or j is None or k is None:
                return None
            return self.get_joint_angle_rad(int(i), int(j), int(k))
        piv = primary.get("pivot")
        tip = primary.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_vector_angle_rad(int(piv), int(tip))

    def _get_output_angle_abs_rad(self) -> Optional[float]:
        primary = self._primary_output()
        if not primary or not primary.get("enabled"):
            return None
        piv = primary.get("pivot")
        tip = primary.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_vector_angle_rad(int(piv), int(tip))

    def _get_output_angle_abs_rad_for(self, output: Dict[str, Any]) -> Optional[float]:
        if not output or not output.get("enabled"):
            return None
        piv = output.get("pivot")
        tip = output.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_vector_angle_rad(int(piv), int(tip))

    def _get_driver_angle_abs_rad(self, driver: Dict[str, Any]) -> Optional[float]:
        if not driver or not driver.get("enabled"):
            return None
        if driver.get("type") == "joint":
            i, j, k = driver.get("i"), driver.get("j"), driver.get("k")
            if i is None or j is None or k is None:
                return None
            return self.get_joint_angle_rad(int(i), int(j), int(k))
        piv = driver.get("pivot")
        tip = driver.get("tip")
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

    def get_driver_angles_deg(self) -> List[Optional[float]]:
        """Current driver angles in degrees (relative to Play-start if available)."""
        result: List[Optional[float]] = []
        drivers = self._active_drivers()
        for idx, drv in enumerate(drivers):
            ang = self._get_driver_angle_abs_rad(drv)
            if ang is None:
                result.append(None)
                continue
            abs_deg = math.degrees(ang)
            base_rad: Optional[float] = None
            if self._sim_zero_driver_rad and idx < len(self._sim_zero_driver_rad):
                base_rad = self._sim_zero_driver_rad[idx]
            elif idx == 0 and self._sim_zero_input_rad is not None:
                base_rad = self._sim_zero_input_rad
            if base_rad is None:
                result.append(abs_deg)
            else:
                result.append(self._rel_deg(abs_deg, math.degrees(base_rad)))
        return result

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

    def get_output_angles_deg(self) -> List[Optional[float]]:
        """Current output angles in degrees (relative to Play-start for the primary)."""
        result: List[Optional[float]] = []
        outputs = [o for o in self.outputs if o.get("enabled")]
        for idx, out in enumerate(outputs):
            ang = self._get_output_angle_abs_rad_for(out)
            if ang is None:
                result.append(None)
                continue
            abs_deg = math.degrees(ang)
            if idx == 0 and self._sim_zero_output_rad is not None:
                result.append(self._rel_deg(abs_deg, math.degrees(self._sim_zero_output_rad)))
            else:
                result.append(abs_deg)
        return result

    def drive_to_deg(self, deg: float, iters: int = 80):
        """Drive the mechanism to a *relative* input angle (deg) and solve constraints.

        If Play has started, 0° corresponds to the Play-start pose.
        """
        if not self._active_drivers() and not self._active_outputs():
            return

        # Target = (Play-start absolute angle) + delta
        primary_driver = self._primary_driver()
        primary_output = self._primary_output()
        if primary_driver and primary_driver.get("enabled"):
            if self._sim_zero_input_rad is not None:
                target = float(self._sim_zero_input_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_driver["rad"] = float(target)
            self.drivers[0] = primary_driver
            self._sync_primary_driver()
        elif primary_output and primary_output.get("enabled"):
            if self._sim_zero_output_rad is not None:
                target = float(self._sim_zero_output_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_output["rad"] = float(target)
            self.outputs[0] = primary_output
            self._sync_primary_output()
        self.solve_constraints(iters=iters)
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()

    def drive_to_multi_deg(self, deg_list: List[float], iters: int = 80):
        """Drive multiple active drivers to relative angles (deg) and solve constraints."""
        active_drivers = self._active_drivers()
        if not active_drivers:
            return
        for idx, drv in enumerate(active_drivers):
            if idx >= len(deg_list):
                break
            base_rad = None
            if idx < len(self._sim_zero_driver_rad):
                base_rad = self._sim_zero_driver_rad[idx]
            if base_rad is None:
                base_rad = self._get_driver_angle_abs_rad(drv)
            target = math.radians(float(deg_list[idx]))
            if base_rad is not None:
                target = float(base_rad) + target
            drv["rad"] = float(target)
        self._sync_primary_driver()
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
        self._sim_zero_driver_rad = []
        for drv in self._active_drivers():
            self._sim_zero_driver_rad.append(self._get_driver_angle_abs_rad(drv))
        if self._sim_zero_output_rad is not None and self.outputs:
            self.outputs[0]["rad"] = float(self._sim_zero_output_rad)
            self._sync_primary_output()

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
        if self.drivers and self._sim_zero_input_rad is not None:
            self.drivers[0]["rad"] = float(self._sim_zero_input_rad)
            self._sync_primary_driver()
        if self._sim_zero_driver_rad:
            for idx, drv in enumerate(self._active_drivers()):
                if idx >= len(self._sim_zero_driver_rad):
                    break
                if self._sim_zero_driver_rad[idx] is not None:
                    drv["rad"] = float(self._sim_zero_driver_rad[idx])
        if self.outputs and self._sim_zero_output_rad is not None:
            self.outputs[0]["rad"] = float(self._sim_zero_output_rad)
            self._sync_primary_output()
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
