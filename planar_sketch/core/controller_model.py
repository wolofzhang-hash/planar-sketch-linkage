# -*- coding: utf-8 -*-
"""SketchController model, geometry, and constraint editing methods."""

from __future__ import annotations

from .controller_common import *


class ControllerModel:
    def _set_continuous_model_action(self, action: Optional[str]) -> None:
        self._continuous_model_action = action
        if self.win and hasattr(self.win, "update_model_action_state"):
            self.win.update_model_action_state()

    def cancel_model_action(self) -> None:
        self.commit_drag_if_any()
        self.mode = "Idle"
        self._line_sel = []
        self._co_master = None
        self._pol_master = None
        self._pol_line_sel = []
        self._pos_master = None
        self._background_pick_points = []
        self._set_continuous_model_action(None)
        self.update_status()

    @staticmethod
    def _default_driver() -> Dict[str, Any]:
        return {
            "enabled": False,
            "type": "angle",
            "pivot": None, "tip": None,
            "rad": 0.0,
            "plid": None,
            "s_base": 0.0,
            "value": 0.0,
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
            "type": str(data.get("type", "angle")),
            "pivot": data.get("pivot"),
            "tip": data.get("tip"),
            "rad": float(data.get("rad", 0.0) or 0.0),
            "plid": data.get("plid"),
            "s_base": float(data.get("s_base", 0.0) or 0.0),
            "value": float(data.get("value", 0.0) or 0.0),
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
        lang = getattr(self, "ui_language", "en")
        if self.mode == "CreateLine":
            if self._continuous_model_action == "CreateLine":
                return tr(lang, "status.create_line_continuous")
            return tr(lang, "status.create_line")
        if self.mode == "CreatePoint":
            if self._continuous_model_action == "CreatePoint":
                return tr(lang, "status.create_point_continuous")
            return tr(lang, "status.create_point")
        if self.mode == "Coincide":
            if self._co_master is None:
                return tr(lang, "status.coincide_pick_master")
            return tr(lang, "status.coincide_pick_target").format(master=int(self._co_master))
        if self.mode == "PointOnLine":
            if self._pol_master is None:
                return tr(lang, "status.point_on_line_pick_point")
            if len(self._pol_line_sel) == 0:
                return tr(lang, "status.point_on_line_pick_line_1").format(master=int(self._pol_master))
            if len(self._pol_line_sel) == 1:
                return tr(lang, "status.point_on_line_pick_line_2").format(master=int(self._pol_master))
            return tr(lang, "status.point_on_line_selecting")
        if self.mode == "PointOnSpline":
            if self._pos_master is None:
                return tr(lang, "status.point_on_spline_pick_point")
            return tr(lang, "status.point_on_spline_pick_spline").format(master=int(self._pos_master))
        if self.mode == "BackgroundImagePick":
            if len(self._background_pick_points) == 0:
                return tr(lang, "status.background_pick_first")
            if len(self._background_pick_points) == 1:
                return tr(lang, "status.background_pick_second")
            return tr(lang, "status.background_configuring")
        return tr(lang, "status.idle_help")

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
                    "type": "angle",
                    "pivot": out.get("pivot"),
                    "tip": out.get("tip"),
                    "rad": out.get("rad", 0.0),
                }
                drive_sources.append(entry)

        for drv in drive_sources:
            if str(drv.get("type", "angle")) == "translation":
                plid = drv.get("plid")
                if plid in self.point_lines:
                    p_id = self.point_lines[plid].get("p")
                    if p_id is not None:
                        driven_pids.add(int(p_id))
                continue
            tip = drv.get("tip")
            if tip is not None:
                driven_pids.add(int(tip))

        # Allow editing lengths that belong to the active drivers (avoid false OVER).
        driver_length_pairs: set[frozenset[int]] = set()
        for drv in drive_sources:
            piv = drv.get("pivot")
            tip = drv.get("tip")
            if piv is not None and tip is not None:
                driver_length_pairs.add(frozenset({int(piv), int(tip)}))

        translation_targets: Dict[int, float] = {}
        for drv in drive_sources:
            if str(drv.get("type", "angle")) != "translation":
                continue
            plid = drv.get("plid")
            if plid not in self.point_lines:
                continue
            pl = self.point_lines[plid]
            base_s = float(drv.get("s_base", self._point_line_current_s(pl)) or 0.0)
            offset = float(drv.get("value", 0.0) or 0.0)
            translation_targets[int(plid)] = base_s + offset

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
                if str(drv.get("type", "angle")) == "translation":
                    continue
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

            for plid, target_s in translation_targets.items():
                pl = self.point_lines.get(plid)
                if not pl or not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1)); i_id = int(pl.get("i", -1)); j_id = int(pl.get("j", -1))
                if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                    continue
                if drag_pid in (p_id, i_id, j_id):
                    continue
                pp = self.points[p_id]; pa = self.points[i_id]; pb = self.points[j_id]
                lock_p = bool(pp.get("fixed", False)) or (drag_pid == p_id)
                lock_a = bool(pa.get("fixed", False)) or (drag_pid == i_id)
                lock_b = bool(pb.get("fixed", False)) or (drag_pid == j_id)
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
            for plid, pl in self.point_lines.items():
                if not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1)); i_id = int(pl.get("i", -1)); j_id = int(pl.get("j", -1))
                if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                    continue
                pp = self.points[p_id]; pa = self.points[i_id]; pb = self.points[j_id]
                lock_p = bool(pp.get("fixed", False)) or (drag_pid == p_id) or (p_id in driven_pids)
                lock_a = bool(pa.get("fixed", False)) or (drag_pid == i_id) or (i_id in driven_pids)
                lock_b = bool(pb.get("fixed", False)) or (drag_pid == j_id) or (j_id in driven_pids)
                if plid in translation_targets:
                    ok = ConstraintSolver.solve_point_on_line_offset(
                        pp,
                        pa,
                        pb,
                        float(translation_targets[plid]),
                        lock_p,
                        lock_a,
                        lock_b,
                        tol=1e-6,
                    )
                elif "s" in pl:
                    ok = ConstraintSolver.solve_point_on_line_offset(
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
                ok = ConstraintSolver.solve_point_on_spline(
                    pp,
                    cps,
                    lock_p,
                    lock_controls,
                    tol=1e-6,
                    closed=bool(spline.get("closed", False)),
                )
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
                samples = build_spline_samples(pts, samples_per_segment=16, closed=bool(spline.get("closed", False)))
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

        translation_targets: Dict[int, float] = {}
        for drv in self._active_drivers():
            if str(drv.get("type", "angle")) != "translation":
                continue
            try:
                plid = int(drv.get("plid", -1))
            except (TypeError, ValueError):
                continue
            if plid not in self.point_lines:
                continue
            pl = self.point_lines[plid]
            base_s = float(drv.get("s_base", self._point_line_current_s(pl)) or 0.0)
            offset = float(drv.get("value", 0.0) or 0.0)
            translation_targets[plid] = base_s + offset

        # Point-on-line constraints
        for plid, pl in self.point_lines.items():
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
                    if plid in translation_targets:
                        target_s = float(translation_targets[plid])
                        ux, uy = abx / denom, aby / denom
                        target_x = ax + ux * target_s
                        target_y = ay + uy * target_s
                        dist = math.hypot(px - target_x, py - target_y)
                    elif "s" in pl:
                        ux, uy = abx / denom, aby / denom
                        target_x = ax + ux * float(pl.get("s", 0.0))
                        target_y = ay + uy * float(pl.get("s", 0.0))
                        dist = math.hypot(px - target_x, py - target_y)
                    else:
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
            samples = build_spline_samples(pts, samples_per_segment=16, closed=bool(self.splines[s_id].get("closed", False)))
            if len(samples) < 2:
                continue
            px, py = float(self.points[p_id]["x"]), float(self.points[p_id]["y"])
            _cx, _cy, _seg_idx, _t_seg, dist2 = closest_point_on_samples(px, py, samples)
            max_ps = max(max_ps, math.sqrt(dist2))

        max_err = max(max_len, max_ang, max_coin, max_pl, max_ps)
        return max_err, {'length': max_len, 'angle': max_ang, 'coincide': max_coin, 'point_line': max_pl, 'point_spline': max_ps}

    def check_overconstraint(self) -> Tuple[bool, str]:
        """Check for structural over-constraint (constraint count > DOF)."""
        summaries = self.constraint_dof_summary()
        if not summaries:
            return False, "No points"

        details: List[str] = []
        over_any = False
        for item in summaries:
            dof = item["dof"]
            total = item["total"]
            over = total > dof
            over_any = over_any or over
            details.append(
                f"component#{item['component']}: constraints={total} > dof={dof} "
                f"(fixed={item['fixed']}, links={item['links']}, angles={item['angles']}, "
                f"coincide={item['coincide']}, line={item['point_lines']}, "
                f"spline={item['point_splines']}, rigid={item['rigid_edges']})"
            )

        return over_any, " | ".join(details)

    def constraint_dof_summary(self) -> List[Dict[str, int]]:
        """Return per-component DOF/constraint counts."""
        if len(self.points) == 0:
            return []

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

        summary: List[Dict[str, int]] = []
        for idx, comp in enumerate(components, start=1):
            dof = 2 * len(comp)
            fixed = sum(1 for pid in comp if bool(self.points.get(pid, {}).get("fixed", False)))
            coincide = sum(
                1
                for c in self.coincides.values()
                if bool(c.get("enabled", True)) and int(c.get("a", -1)) in comp and int(c.get("b", -1)) in comp
            )
            point_lines = sum(
                (2 if "s" in pl else 1)
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
            summary.append(
                {
                    "component": idx,
                    "dof": dof,
                    "fixed": fixed,
                    "links": links,
                    "angles": angles,
                    "coincide": coincide,
                    "point_lines": point_lines,
                    "point_splines": point_splines,
                    "rigid_edges": rigid_edges,
                    "total": total,
                }
            )

        return summary

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

        # Point-on-line (s): s_expr
        for plid, pl in self.point_lines.items():
            if "s" not in pl:
                continue
            expr = pl.get("s_expr", "")
            if not expr:
                pl.pop("s_expr_error", None)
                pl.pop("s_expr_error_msg", None)
                continue
            val, err = self.parameters.eval_expr(str(expr))
            if err is None and val is not None:
                pl["s"] = float(val)
                pl.pop("s_expr_error", None)
                pl.pop("s_expr_error_msg", None)
            else:
                pl["s_expr_error"] = True
                pl["s_expr_error_msg"] = str(err)

        # Friction joints: mu_expr / diameter_expr
        for fj in self.friction_joints:
            for key_num, key_expr in (("mu", "mu_expr"), ("diameter", "diameter_expr")):
                expr = fj.get(key_expr, "")
                if not expr:
                    fj.pop(f"{key_expr}_error", None)
                    fj.pop(f"{key_expr}_error_msg", None)
                    continue
                val, err = self.parameters.eval_expr(str(expr))
                if err is None and val is not None:
                    fj[key_num] = float(val)
                    fj.pop(f"{key_expr}_error", None)
                    fj.pop(f"{key_expr}_error_msg", None)
                else:
                    fj[f"{key_expr}_error"] = True
                    fj[f"{key_expr}_error_msg"] = str(err)

        # Loads: fx_expr / fy_expr / mz_expr / k_expr / load_expr
        for ld in self.loads:
            ltype = str(ld.get("type", "force")).lower()
            if ltype in ("spring", "torsion_spring"):
                key_pairs = (("k", "k_expr"), ("load", "load_expr"))
            else:
                key_pairs = (("fx", "fx_expr"), ("fy", "fy_expr"), ("mz", "mz_expr"))
            for key_num, key_expr in key_pairs:
                expr = ld.get(key_expr, "")
                if not expr:
                    ld.pop(f"{key_expr}_error", None)
                    ld.pop(f"{key_expr}_error_msg", None)
                    continue
                val, err = self.parameters.eval_expr(str(expr))
                if err is None and val is not None:
                    ld[key_num] = float(val)
                    ld.pop(f"{key_expr}_error", None)
                    ld.pop(f"{key_expr}_error_msg", None)
                else:
                    ld[f"{key_expr}_error"] = True
                    ld[f"{key_expr}_error_msg"] = str(err)

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
                samples = build_spline_samples(pts, samples_per_segment=16, closed=bool(self.splines[sid].get("closed", False)))
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

    def solve_constraints_exudyn(self, max_iters: int = 80) -> tuple[bool, str]:
        """Solve using Exudyn backend (quasi-static / kinematics)."""
        self.recompute_from_parameters()
        try:
            ok, msg = ExudynKinematicSolver.solve(self, max_iters=int(max_iters), distance_only=True)
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

    def drive_to_deg_exudyn(self, deg: float, max_iters: int = 80) -> tuple[bool, str]:
        """Drive to a relative input angle (deg) and solve with Exudyn."""
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
        return self.solve_constraints_exudyn(max_iters=max_iters)

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

    def drive_to_multi_deg_exudyn(self, deg_list: List[float], max_iters: int = 80) -> tuple[bool, str]:
        """Drive multiple active drivers to relative angles (deg) and solve with Exudyn."""
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
        return self.solve_constraints_exudyn(max_iters=max_iters)

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
        self._remove_point_dependents({pid})
        to_del_l = [lid for lid, l in self.links.items() if l["i"] == pid or l["j"] == pid]
        for lid in to_del_l: self._remove_link(lid)
        to_del_a = [aid for aid, a in self.angles.items() if a["i"] == pid or a["j"] == pid or a["k"] == pid]
        for aid in to_del_a: self._remove_angle(aid)
        to_del_c = [
            cid
            for cid, c in self.coincides.items()
            if self._safe_int(c.get("a")) == pid or self._safe_int(c.get("b")) == pid
        ]
        for cid in to_del_c: self._remove_coincide(cid)
        to_del_pl = [
            plid
            for plid, pl in self.point_lines.items()
            if self._safe_int(pl.get("p")) == pid
            or self._safe_int(pl.get("i")) == pid
            or self._safe_int(pl.get("j")) == pid
        ]
        for plid in to_del_pl:
            self._remove_point_line(plid)
        to_del_ps = [psid for psid, ps in self.point_splines.items() if self._safe_int(ps.get("p")) == pid]
        for psid in to_del_ps:
            self._remove_point_spline(psid)
        to_del_spl = [sid for sid, s in self.splines.items() if pid in s.get("points", [])]
        for sid in to_del_spl:
            self._remove_spline(sid)
        for bid in [bid for bid, b in self.bodies.items() if pid in b.get("points", [])]:
            self._remove_body(bid)
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

    
    def _remove_point_dependents(self, pids: set[int]) -> None:
        if not pids:
            return
        self.loads = [ld for ld in self.loads if self._safe_int(ld.get("pid", -1)) not in pids]
        self.load_measures = [lm for lm in self.load_measures if self._safe_int(lm.get("pid", -1)) not in pids]
        self.friction_joints = [fj for fj in self.friction_joints if self._safe_int(fj.get("pid", -1)) not in pids]
        removed_meas_names: List[str] = []
        kept_measures: List[Dict[str, Any]] = []
        for m in self.measures:
            mtype = m.get("type")
            if mtype == "angle":
                if self._safe_int(m.get("pivot", -1)) in pids or self._safe_int(m.get("tip", -1)) in pids:
                    removed_meas_names.append(str(m.get("name", "")))
                    continue
            elif mtype == "joint":
                if {
                    self._safe_int(m.get("i", -1)),
                    self._safe_int(m.get("j", -1)),
                    self._safe_int(m.get("k", -1)),
                } & pids:
                    removed_meas_names.append(str(m.get("name", "")))
                    continue
            kept_measures.append(m)
        self.measures = kept_measures
        for name in removed_meas_names:
            self._sim_zero_meas_deg.pop(name, None)

        kept_drivers: List[Dict[str, Any]] = []
        for drv in self.drivers:
            dtype = drv.get("type")
            if dtype == "angle":
                if self._safe_int(drv.get("pivot", -1)) in pids or self._safe_int(drv.get("tip", -1)) in pids:
                    continue
            elif dtype == "translation":
                plid = self._safe_int(drv.get("plid", -1))
                if plid not in self.point_lines:
                    continue
                pl = self.point_lines.get(plid, {})
                if self._safe_int(pl.get("p", -1)) in pids:
                    continue
            kept_drivers.append(drv)
        if len(kept_drivers) != len(self.drivers):
            self.drivers = kept_drivers
            self._sim_zero_driver_rad = []
            self._sync_primary_driver()

        kept_outputs: List[Dict[str, Any]] = []
        for out in self.outputs:
            if self._safe_int(out.get("pivot", -1)) in pids or self._safe_int(out.get("tip", -1)) in pids:
                continue
            kept_outputs.append(out)
        if len(kept_outputs) != len(self.outputs):
            self.outputs = kept_outputs
            self._sync_primary_output()

    @staticmethod
    def _safe_int(value: Any, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

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


    def _create_point_line(
        self,
        plid: int,
        p: int,
        i: int,
        j: int,
        hidden: bool,
        enabled: bool = True,
        s: Optional[float] = None,
        s_expr: str = "",
        name: str = "",
    ):
        entry: Dict[str, Any] = {
            "p": int(p),
            "i": int(i),
            "j": int(j),
            "hidden": bool(hidden),
            "enabled": bool(enabled),
            "over": False,
        }
        if s is not None:
            entry["s"] = float(s)
            entry["s_expr"] = str(s_expr or "")
            if name:
                entry["name"] = str(name)
        self.point_lines[plid] = entry
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

    def _point_line_offset_name(self, pl: Dict[str, Any]) -> str:
        try:
            p = int(pl.get("p", -1))
            i = int(pl.get("i", -1))
            j = int(pl.get("j", -1))
        except Exception:
            return "point line s"
        return f"s P{p} on (P{i}-P{j})"

    def _point_line_current_s(self, pl: Dict[str, Any]) -> float:
        try:
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
        except Exception:
            return 0.0
        if p_id not in self.points or i_id not in self.points or j_id not in self.points:
            return 0.0
        pp = self.points[p_id]
        pa = self.points[i_id]
        pb = self.points[j_id]
        ax, ay = float(pa["x"]), float(pa["y"])
        bx, by = float(pb["x"]), float(pb["y"])
        px, py = float(pp["x"]), float(pp["y"])
        abx, aby = bx - ax, by - ay
        ab_len = math.hypot(abx, aby)
        if ab_len < 1e-12:
            return 0.0
        ux, uy = abx / ab_len, aby / ab_len
        return (px - ax) * ux + (py - ay) * uy

    def _create_spline(self, sid: int, point_ids: List[int], hidden: bool, closed: bool = False):
        pts = [pid for pid in point_ids if pid in self.points]
        self.splines[sid] = {"points": pts, "hidden": bool(hidden), "closed": bool(closed), "over": False}
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
