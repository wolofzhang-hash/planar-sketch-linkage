# -*- coding: utf-8 -*-
"""SketchController selection/menu/command helpers."""

from __future__ import annotations

import time
import uuid

from .controller_common import *
from .controller_selection_io_mixin import ControllerSelectionIOMixin
from .controller_selection_context_menu_mixin import ControllerSelectionContextMenuMixin


class ControllerSelection(ControllerSelectionContextMenuMixin, ControllerSelectionIOMixin):
    def _undo_name_localized(self, en: str, zh: str) -> str:
        return zh if getattr(self, "ui_language", "en") == "zh" else en

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

    def _clear_scene_point_spline_dist_selection(self):
        for pd in getattr(self, "point_spline_dists", {}).values():
            try:
                pd["item"].setSelected(False)
            except Exception:
                pass
        self.selected_point_spline_dist_id = None

    def select_link_single(self, lid: int):
        if lid not in self.links: return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self._clear_scene_point_spline_dist_selection()
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


    def _ensure_sketch_panel_visible(self) -> None:
        win = getattr(self, "win", None)
        if win is None:
            return
        try:
            if hasattr(win, "_activate_sketch_mode"):
                win._activate_sketch_mode()
            elif hasattr(win, "_set_dock_visibility"):
                win._set_dock_visibility(active="sketch")
        except Exception:
            pass

    def focus_link_in_panel(self, lid: int) -> None:
        self.select_link_single(lid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_link(lid)

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

    def focus_angle_in_panel(self, aid: int) -> None:
        self.select_angle_single(aid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_angle(aid)



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

    def focus_coincide_in_panel(self, cid: int) -> None:
        self.select_coincide_single(cid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_constraint_key(f"C{cid}")

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
        self._clear_scene_point_spline_dist_selection()
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

    def focus_point_line_in_panel(self, plid: int) -> None:
        self.select_point_line_single(plid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_constraint_key(f"P{plid}")

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
        self._clear_scene_point_spline_dist_selection()
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

    def focus_point_spline_in_panel(self, psid: int) -> None:
        self.select_point_spline_single(psid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_constraint_key(f"S{psid}")

    def select_point_spline_dist_single(self, pdid: int):
        if not hasattr(self, "point_spline_dists") or pdid not in self.point_spline_dists:
            return
        self.commit_drag_if_any()
        self._clear_scene_point_selection()
        self._clear_scene_link_selection()
        self._clear_scene_angle_selection()
        self._clear_scene_spline_selection()
        self._clear_scene_coincide_selection()
        self._clear_scene_point_line_selection()
        self._clear_scene_point_spline_selection()
        self._clear_scene_point_spline_dist_selection()
        self.point_spline_dists[pdid]["item"].setSelected(True)
        self.selected_point_spline_dist_id = pdid
        self.selected_link_id = None
        self.selected_angle_id = None
        self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            try:
                self.panel.select_constraints_row(f"D{pdid}")
            except Exception:
                pass
        self.update_status()

    def focus_point_spline_dist_in_panel(self, pdid: int) -> None:
        self.select_point_spline_dist_single(pdid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_constraint_key(f"D{pdid}")

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
        self._clear_scene_point_spline_dist_selection()
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

    def focus_body_in_panel(self, bid: int) -> None:
        self.select_body_single(bid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_body(bid)

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
        self._clear_scene_point_spline_dist_selection()
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

    def focus_spline_in_panel(self, sid: int) -> None:
        self.select_spline_single(sid)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_spline(sid)

    def apply_box_selection(self, pids: List[int], toggle: bool):
        pids = [pid for pid in pids if pid in self.points and (not self.is_point_effectively_hidden(pid)) and self.show_points_geometry]
        if not toggle:
            self._clear_scene_link_selection(); self._clear_scene_angle_selection()
            self._clear_scene_spline_selection(); self._clear_scene_coincide_selection()
            self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection(); self._clear_scene_point_spline_dist_selection()
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
            self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection(); self._clear_scene_point_spline_dist_selection()
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
        self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection(); self._clear_scene_point_spline_dist_selection()
        self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_points_multi(sorted(self.selected_point_ids))
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_splines_selection_only()
            self.panel.clear_bodies_selection_only()

    def focus_point_in_panel(self, pid: int) -> None:
        self.select_point_single(pid, keep_others=False)
        self._ensure_sketch_panel_visible()
        if self.panel:
            self.panel.focus_point(pid)

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
        self._clear_scene_point_line_selection(); self._clear_scene_point_spline_selection(); self._clear_scene_point_spline_dist_selection()
        self.selected_link_id = None; self.selected_angle_id = None; self.selected_body_id = None
        self.update_graphics()
        if self.panel:
            self.panel.select_points_multi(sorted(self.selected_point_ids))
            self.panel.clear_links_selection_only()
            self.panel.clear_angles_selection_only()
            self.panel.clear_bodies_selection_only()

    # ------ commands ------
    def _solve_after_model_edit(self):
        """Re-solve geometry after topology/model edits without re-applying saved IO pose.

        Editing actions such as creating points/links/constraints should preserve the
        current live pose and must not snap the model back to driver/output reference
        angles during a refresh.
        """
        self.solve_constraints(use_drive_constraints=False)
        self.update_graphics()

    def cmd_add_point(self, x: float, y: float):
        if not self._confirm_stop_replay("modify the model"):
            return
        x, y = self._snap_point_to_grid(float(x), float(y))
        pid = self._next_pid; self._next_pid += 1
        ctrl = self
        self._last_model_action = "CreatePoint"
        self._last_point_pos = (float(x), float(y))
        class AddPoint(Command):
            name = "Add Point"
            def do(self_):
                ctrl._create_point(pid, x, y, fixed=False, hidden=False, traj_enabled=False)
                ctrl.select_point_single(pid, keep_others=False)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_point(pid)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
                ctrl.update_status()
        self.stack.push(AddPoint())

    def _snap_point_to_grid(self, x: float, y: float) -> tuple[float, float]:
        settings = getattr(self, "grid_settings", {}) or {}
        show_h = bool(settings.get("show_horizontal", False))
        show_v = bool(settings.get("show_vertical", False))
        if not show_h and not show_v:
            return float(x), float(y)
        spacing_x = float(settings.get("spacing_x", 0.0) or 0.0)
        spacing_y = float(settings.get("spacing_y", 0.0) or 0.0)
        cx, cy = settings.get("center", (0.0, 0.0))
        range_x = float(settings.get("range_x", 0.0) or 0.0)
        range_y = float(settings.get("range_y", 0.0) or 0.0)

        def in_range(value: float, center: float, span: float) -> bool:
            if span <= 0.0:
                return True
            return (center - span) <= value <= (center + span)

        if show_v and spacing_x > 0.0 and in_range(x, cx, range_x):
            x = cx + round((x - cx) / spacing_x) * spacing_x
        if show_h and spacing_y > 0.0 and in_range(y, cy, range_y):
            y = cy + round((y - cy) / spacing_y) * spacing_y
        return float(x), float(y)

    def set_grid_visibility(self, show_horizontal: Optional[bool] = None, show_vertical: Optional[bool] = None) -> None:
        if show_horizontal is not None:
            self.grid_settings["show_horizontal"] = bool(show_horizontal)
        if show_vertical is not None:
            self.grid_settings["show_vertical"] = bool(show_vertical)
        self._refresh_grid_item()

    def set_grid_settings(
        self,
        spacing_x: float,
        spacing_y: float,
        range_x: float,
        range_y: float,
        center_x: float,
        center_y: float,
    ) -> None:
        self.grid_settings["spacing_x"] = max(0.1, float(spacing_x))
        self.grid_settings["spacing_y"] = max(0.1, float(spacing_y))
        self.grid_settings["range_x"] = max(0.0, float(range_x))
        self.grid_settings["range_y"] = max(0.0, float(range_y))
        self.grid_settings["center"] = (float(center_x), float(center_y))
        self._refresh_grid_item()

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
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_link(lid)
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_angle(aid)
                ctrl._solve_after_model_edit()
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
                ctrl._create_spline(sid, pts, hidden=False, closed=False)
                ctrl.select_spline_single(sid)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
                ctrl.update_status()
            def undo(self_):
                ctrl._remove_spline(sid)
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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

    def cmd_set_spline_closed(self, sid: int, closed: bool):
        if not self._confirm_stop_replay("modify the model"):
            return
        if sid not in self.splines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetSplineClosed(Command):
            name = "Set Spline Closed"
            def do(self_):
                ctrl.splines[sid]["closed"] = bool(closed)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetSplineClosed())

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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
                    ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelBody())

    def cmd_delete_points(self, pids: List[int]):
        if not self._confirm_stop_replay("modify the model"):
            return
        ids = [pid for pid in pids if pid in self.points]
        if not ids:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class DelPoints(Command):
            name = "Delete Point" if len(ids) == 1 else "Delete Points"
            def do(self_):
                for pid in sorted(ids, reverse=True):
                    if pid in ctrl.points:
                        ctrl._remove_point(pid)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all()
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelPoints())

    def cmd_delete_point(self, pid: int):
        self.cmd_delete_points([pid])

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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
            name = ctrl._undo_name_localized("Add Point On Line", "添加点在线")
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

    def cmd_add_point_line_offset(self, p: int, i: int, j: int, s: float = 0.0, s_expr: str = ""):
        """Add a point-on-line displacement constraint: P = A + unit(B-A) * s."""
        if not self._confirm_stop_replay("modify the model"):
            return
        if p not in self.points or i not in self.points or j not in self.points:
            return
        if i == j:
            return
        if p == i or p == j:
            return
        line_pair = frozenset({int(i), int(j)})
        for pl in self.point_lines.values():
            if int(pl.get("p")) == int(p) and frozenset({int(pl.get("i")), int(pl.get("j"))}) == line_pair:
                return
        ctrl = self
        model_before = self.snapshot_model()
        plid = self._next_plid
        name = self._point_line_offset_name({"p": p, "i": i, "j": j})

        class AddPointLineOffset(Command):
            name = ctrl._undo_name_localized("Add Point On Line (s)", "添加点在线（s）")
            def do(self_):
                ctrl._next_plid = max(ctrl._next_plid, plid + 1)
                ctrl._create_point_line(
                    plid, p, i, j,
                    hidden=False,
                    enabled=True,
                    s=float(s),
                    s_expr=str(s_expr or ""),
                    name=name,
                )
                pp = ctrl.points[p]; pa = ctrl.points[i]; pb = ctrl.points[j]
                lock_p = bool(pp.get("fixed", False))
                lock_a = bool(pa.get("fixed", False))
                lock_b = bool(pb.get("fixed", False))
                ConstraintSolver.solve_point_on_line_offset(pp, pa, pb, float(s), lock_p, lock_a, lock_b, tol=1e-6)
                ctrl.solve_constraints(drag_pid=p)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(AddPointLineOffset())

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
            name = ctrl._undo_name_localized("Add Point On Spline", "添加点在线样条")
            def do(self_):
                ctrl._next_psid = max(ctrl._next_psid, psid + 1)
                ctrl._create_point_spline(psid, p, s, hidden=False, enabled=True)
                pp = ctrl.points[p]
                cp_ids = [pid for pid in ctrl.splines[s].get("points", []) if pid in ctrl.points]
                cps = [ctrl.points[cid] for cid in cp_ids]
                lock_p = bool(pp.get("fixed", False))
                lock_controls = [bool(ctrl.points[cid].get("fixed", False)) for cid in cp_ids]
                ConstraintSolver.solve_point_on_spline(
                    pp,
                    cps,
                    lock_p,
                    lock_controls,
                    tol=1e-6,
                    closed=bool(ctrl.splines[s].get("closed", False)),
                )
                ctrl.solve_constraints(drag_pid=p)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(AddPointSpline())

    def cmd_add_point_spline_dist(self, p: int, s: int, dist: float):
        """Add a point-to-spline distance constraint: dist(P, spline) = dist."""
        if not self._confirm_stop_replay("modify the model"):
            return
        if p not in self.points or s not in self.splines:
            return
        if p in self.splines[s].get("points", []):
            return
        for pd in getattr(self, "point_spline_dists", {}).values():
            if int(pd.get("p", -1)) == int(p) and int(pd.get("s", -1)) == int(s):
                return
        ctrl = self
        model_before = self.snapshot_model()
        pdid = self._next_pdid

        class AddPointSplineDist(Command):
            name = ctrl._undo_name_localized("Add Point-Spline Distance", "添加点-样条距离")

            def do(self_):
                ctrl._next_pdid = max(ctrl._next_pdid, pdid + 1)
                ctrl._create_point_spline_dist(pdid, p, s, float(dist), hidden=False, enabled=True, hint_seg=-1)
                pp = ctrl.points[p]
                cp_ids = [pid for pid in ctrl.splines[s].get("points", []) if pid in ctrl.points]
                cps = [ctrl.points[cid] for cid in cp_ids]
                lock_p = bool(pp.get("fixed", False))
                lock_controls = [bool(ctrl.points[cid].get("fixed", False)) for cid in cp_ids]
                ok, new_hint, _d = ConstraintSolver.solve_point_spline_distance(
                    pp,
                    cps,
                    float(dist),
                    lock_p,
                    lock_controls,
                    hint_seg=-1,
                    tol=1e-6,
                    closed=bool(ctrl.splines[s].get("closed", False)),
                )
                ctrl.point_spline_dists[pdid]["hint_seg"] = int(new_hint)
                if not ok:
                    ctrl.point_spline_dists[pdid]["over"] = True
                ctrl.solve_constraints(drag_pid=p)
                ctrl.update_graphics()
                if ctrl.panel:
                    ctrl.panel.defer_refresh_all(keep_selection=True)

            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        self.stack.push(AddPointSplineDist())

    def cmd_delete_point_line(self, plid: int):
        if not self._confirm_stop_replay("modify the model"):
            return
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class DelPL(Command):
            name = ctrl._undo_name_localized("Delete Point On Line", "删除点在线")
            def do(self_):
                ctrl._remove_point_line(plid)
                ctrl._solve_after_model_edit()
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
            name = ctrl._undo_name_localized("Delete Point On Spline", "删除点在线样条")
            def do(self_):
                ctrl._remove_point_spline(psid)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(DelPS())

    def cmd_delete_point_spline_dist(self, pdid: int):
        if not self._confirm_stop_replay("modify the model"):
            return
        if not hasattr(self, "point_spline_dists") or pdid not in self.point_spline_dists:
            return
        ctrl = self
        model_before = self.snapshot_model()

        class DelPD(Command):
            name = ctrl._undo_name_localized("Delete Point-Spline Distance", "删除点-样条距离")

            def do(self_):
                ctrl._remove_point_spline_dist(pdid)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)

            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        self.stack.push(DelPD())

    def cmd_set_point_line_hidden(self, plid: int, hidden: bool):
        if not self._confirm_stop_replay("modify the model"):
            return
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPLH(Command):
            name = ctrl._undo_name_localized("Set Point On Line Hidden", "设置点在线隐藏")
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
            name = ctrl._undo_name_localized("Set Point On Spline Hidden", "设置点在线样条隐藏")
            def do(self_):
                ctrl.point_splines[psid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPSH())

    def cmd_set_point_spline_dist_hidden(self, pdid: int, hidden: bool):
        if not self._confirm_stop_replay("modify the model"):
            return
        if not hasattr(self, "point_spline_dists") or pdid not in self.point_spline_dists:
            return
        ctrl = self
        model_before = self.snapshot_model()

        class SetPDH(Command):
            name = ctrl._undo_name_localized("Set Point-Spline Distance Hidden", "设置点-样条距离隐藏")

            def do(self_):
                ctrl.point_spline_dists[pdid]["hidden"] = bool(hidden)
                ctrl.update_graphics()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)

            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        self.stack.push(SetPDH())

    def cmd_set_point_line_enabled(self, plid: int, enabled: bool):
        if not self._confirm_stop_replay("modify the model"):
            return
        if plid not in self.point_lines:
            return
        ctrl = self
        model_before = self.snapshot_model()
        class SetPLE(Command):
            name = ctrl._undo_name_localized("Set Point On Line Enabled", "设置点在线启用")
            def do(self_):
                ctrl.point_lines[plid]["enabled"] = bool(enabled)
                ctrl._solve_after_model_edit()
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
            name = ctrl._undo_name_localized("Set Point On Spline Enabled", "设置点在线样条启用")
            def do(self_):
                ctrl.point_splines[psid]["enabled"] = bool(enabled)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
        self.stack.push(SetPSE())

    def cmd_set_point_spline_dist_enabled(self, pdid: int, enabled: bool):
        if not self._confirm_stop_replay("modify the model"):
            return
        if not hasattr(self, "point_spline_dists") or pdid not in self.point_spline_dists:
            return
        ctrl = self
        model_before = self.snapshot_model()

        class SetPDE(Command):
            name = "Set Point-Spline Distance Enabled"

            def do(self_):
                ctrl.point_spline_dists[pdid]["enabled"] = bool(enabled)
                ctrl._solve_after_model_edit()
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)

            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        self.stack.push(SetPDE())

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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
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
                ctrl._solve_after_model_edit()
                try:
                    ctrl._mark_cases_dirty_after_model_edit(clear_run_cache=True)
                except Exception:
                    pass
                if ctrl.panel: ctrl.panel.defer_refresh_all(keep_selection=True)
            def undo(self_):
                ctrl.apply_model_snapshot(model_before)
                try:
                    ctrl._mark_cases_dirty_after_model_edit(clear_run_cache=True)
                except Exception:
                    pass
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
                ctrl._solve_after_model_edit()
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
                ctrl.solve_constraints(use_drive_constraints=False); ctrl.update_graphics()
                ctrl.update_sim_start_pose_snapshot()
                try:
                    ctrl._mark_cases_dirty_after_model_edit(clear_run_cache=True)
                except Exception:
                    pass
                if ctrl.panel: ctrl.panel.refresh_fast()
            def undo(self_):
                ctrl.apply_points_snapshot(before)
                ctrl.solve_constraints(use_drive_constraints=False); ctrl.update_graphics()
                ctrl.update_sim_start_pose_snapshot()
                try:
                    ctrl._mark_cases_dirty_after_model_edit(clear_run_cache=True)
                except Exception:
                    pass
                if ctrl.panel: ctrl.panel.refresh_fast()
        self.stack.push(MoveSystem())

    def cmd_move_point_by_table(self, pid: int, x: float, y: float):
        if not self._confirm_stop_replay("modify the model"):
            return
        if pid not in self.points: return
        before = self.snapshot_points()
        self.points[pid]["x"] = float(x); self.points[pid]["y"] = float(y)
        self.solve_constraints(drag_pid=pid, use_drive_constraints=False)
        after = self.snapshot_points()
        self.cmd_move_system(before, after)

    def on_drag_update(self, pid: int, nx: float, ny: float):
        if pid not in self.points: return
        # Ask to stop replay only once at drag start. Re-checking on every mouse
        # move can make editing feel locked when many cases/runs exist.
        if not self._drag_active:
            if not self._confirm_stop_replay("modify the model"):
                return
            self._drag_active = True
            self._drag_pid = pid
            self._drag_before = self.snapshot_points()
        self.solve_constraints(
            drag_target_pid=pid,
            drag_target_xy=(float(nx), float(ny)),
            drag_pid=None,
            use_drive_constraints=False,
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
        self._set_continuous_model_action("CreateLine" if continuous else None)
        self._line_sel = []
        self.update_status()

    def begin_create_point(self, continuous: bool = False):
        self.commit_drag_if_any()
        self.mode = "CreatePoint"
        self._set_continuous_model_action("CreatePoint" if continuous else None)
        self.update_status()

    def on_scene_clicked_create_point(self, pos: QPointF):
        self.cmd_add_point(float(pos.x()), float(pos.y()))
        if self._continuous_model_action != "CreatePoint":
            self.mode = "Idle"
            self._set_continuous_model_action(None)
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
        self._set_continuous_model_action(None)
        self._co_master = master
        self.update_status()

    def begin_point_on_line(self, master: int):
        """Start point-on-line creation: choose 2 points to define the line."""
        self.commit_drag_if_any()
        self.mode = "PointOnLine"
        self._set_continuous_model_action(None)
        self._pol_master = int(master)
        self._pol_line_sel = []
        self.update_status()

    def begin_point_on_spline(self, master: int):
        """Start point-on-spline creation: choose a spline to constrain."""
        self.commit_drag_if_any()
        self.mode = "PointOnSpline"
        self._set_continuous_model_action(None)
        self._pos_master = int(master)
        self.update_status()

    def begin_point_spline_dist(self, master: int, dist: float):
        """Start point-to-spline distance creation: choose a spline."""
        self.commit_drag_if_any()
        self.mode = "PointSplineDist"
        self._set_continuous_model_action(None)
        self._psd_master = int(master)
        self._psd_dist = float(dist)
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
                self._set_continuous_model_action(None)
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

    def on_spline_clicked_point_spline_dist(self, sid: int):
        master = getattr(self, "_psd_master", None)
        dist = getattr(self, "_psd_dist", 0.0)
        if master is None:
            self.mode = "Idle"
            self.update_status()
            return
        if master not in self.points or sid not in self.splines:
            self.mode = "Idle"
            self.update_status()
            return
        self.mode = "Idle"
        self.cmd_add_point_spline_dist(int(master), int(sid), float(dist))
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
            lang = getattr(self, "ui_language", "en")
            if self.win and self.win.statusBar():
                self.win.statusBar().showMessage(tr(lang, "status.select_three_points"))
            return
        i, j, k = ids[0], ids[1], ids[2]
        if len({i, j, k}) < 3:
            lang = getattr(self, "ui_language", "en")
            if self.win and self.win.statusBar():
                self.win.statusBar().showMessage(tr(lang, "status.select_three_distinct"))
            return
        pi, pj, pk = self.points[i], self.points[j], self.points[k]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        deg = math.degrees(angle_between(v1x, v1y, v2x, v2y))
        self.cmd_add_angle(i, j, k, deg)

    def _add_angle_constraint(self, i: int, j: int, k: int) -> None:
        if i not in self.points or j not in self.points or k not in self.points:
            return
        pi, pj, pk = self.points[i], self.points[j], self.points[k]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        deg = math.degrees(angle_between(v1x, v1y, v2x, v2y))
        self.cmd_add_angle(i, j, k, deg)

    def add_point_line_offset_from_selection(self):
        """Create a point-on-line (s) constraint from the current selection."""
        self.commit_drag_if_any()
        p = None
        i = None
        j = None
        if self.selected_link_id is not None and self.selected_link_id in self.links:
            link = self.links[self.selected_link_id]
            i = int(link.get("i"))
            j = int(link.get("j"))
            if self.selected_point_id is not None:
                p = int(self.selected_point_id)
        else:
            selected = sorted(list(self.selected_point_ids))
            if len(selected) == 3:
                p = int(self.selected_point_id) if self.selected_point_id in selected else int(selected[-1])
                others = [pid for pid in selected if pid != p]
                if len(others) == 2:
                    i, j = int(others[0]), int(others[1])
        if p is None or i is None or j is None:
            lang = getattr(self, "ui_language", "en")
            if self.win and self.win.statusBar():
                self.win.statusBar().showMessage(tr(lang, "status.select_point_line"))
            return
        if p == i or p == j:
            lang = getattr(self, "ui_language", "en")
            if self.win and self.win.statusBar():
                self.win.statusBar().showMessage(tr(lang, "status.point_distinct"))
            return
        self.cmd_add_point_line_offset(p, i, j, s=0.0)

    def show_empty_context_menu(self, global_pos, scene_pos: QPointF):
        lang = getattr(self, "ui_language", "en")
        m = QMenu(self.win)
        m.addAction(tr(lang, "context.create_point"), lambda: self.cmd_add_point(scene_pos.x(), scene_pos.y()))
        m.addAction(tr(lang, "context.create_line"), self.begin_create_line)
        m.addAction(tr(lang, "context.create_spline_from_selection"), self._add_spline_from_selection)
        m.exec(global_pos)

    def _delete_selected_points_multi(self):
        ids = sorted(list(self.selected_point_ids))
        self.cmd_delete_points(ids)

    def _add_spline_from_selection(self):
        ids = sorted(list(self.selected_point_ids))
        if len(ids) < 2:
            return
        self.cmd_add_spline(ids)

    def begin_create_spline(self, continuous: bool = False):
        self.commit_drag_if_any()
        self._set_continuous_model_action("CreateSpline" if continuous else None)
        self._add_spline_from_selection()
        self.update_status()


    def update_graphics(self):
        if self._graphics_update_in_progress:
            self._graphics_update_pending = True
            return
        now = time.monotonic()
        min_interval = self._graphics_update_min_interval
        elapsed = now - self._graphics_update_last
        if min_interval > 0.0 and elapsed < min_interval:
            if not self._graphics_update_scheduled:
                delay_ms = max(1, int((min_interval - elapsed) * 1000))
                self._graphics_update_scheduled = True
                QTimer.singleShot(delay_ms, self._flush_graphics_update)
            self._graphics_update_pending = True
            return
        self._flush_graphics_update()

    def _flush_graphics_update(self):
        if self._graphics_update_in_progress:
            self._graphics_update_pending = True
            return
        self._graphics_update_scheduled = False
        self._graphics_update_pending = False
        self._graphics_update_in_progress = True
        try:
            self._do_update_graphics()
        finally:
            self._graphics_update_in_progress = False
            self._graphics_update_last = time.monotonic()
            if self._graphics_update_pending:
                self._graphics_update_pending = False
                self.update_graphics()

    def _do_update_graphics(self):
        driver_marker_map: Dict[int, Dict[str, Any]] = {}
        active_drivers = self._active_drivers()
        show_driver_index = len(active_drivers) > 1
        for idx, drv in enumerate(active_drivers):
            driver_type = str(drv.get("type", "angle"))
            if driver_type == "translation":
                plid = drv.get("plid")
                if plid not in self.point_lines:
                    continue
                pl = self.point_lines[plid]
                pid = pl.get("p")
                label = "→" if not show_driver_index else f"→{idx + 1}"
                rotation = 0.0
                try:
                    i_id = int(pl.get("i", -1))
                    j_id = int(pl.get("j", -1))
                    if i_id in self.points and j_id in self.points:
                        pa = self.points[i_id]
                        pb = self.points[j_id]
                        rotation = math.degrees(math.atan2(float(pb["y"]) - float(pa["y"]), float(pb["x"]) - float(pa["x"])))
                except Exception:
                    rotation = 0.0
            elif driver_type == "angle":
                pid = drv.get("pivot")
                label = "↻" if not show_driver_index else f"↻{idx + 1}"
                rotation = 0.0
            else:
                continue
            if pid is None:
                continue
            if int(pid) in driver_marker_map:
                driver_marker_map[int(pid)] = {
                    "text": f"{driver_marker_map[int(pid)]['text']},{label}",
                    "rotation": 0.0,
                }
            else:
                driver_marker_map[int(pid)] = {"text": label, "rotation": rotation}
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
                dmark.setText(driver_marker_map[pid]["text"])
                dmark.setRotation(driver_marker_map[pid]["rotation"])
            else:
                dmark.setText("↻")
                dmark.setRotation(0.0)
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

        for bid, b in self.bodies.items():
            it = b.get("solid_item")
            if it is None:
                continue
            try:
                it.sync_style()
                if it.isVisible():
                    it.update_geometry()
            except Exception:
                pass

        for lid, l in self.links.items():
            sit = l.get("solid_item")
            if sit is not None:
                try:
                    sit.sync_style()
                    if sit.isVisible():
                        sit.update_geometry()
                except Exception:
                    pass
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
            samples = build_spline_samples(pts, samples_per_segment=16, closed=bool(s.get("closed", False)))
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

        for pdid, pd in getattr(self, "point_spline_dists", {}).items():
            it: PointSplineDistItem = pd["item"]
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
            for item in self._friction_torque_arrow_items:
                item.setVisible(False)
            return

        load_vectors: List[Dict[str, float]] = []
        torque_vectors: List[Dict[str, float]] = []
        friction_torque_vectors: List[Dict[str, float]] = []
        for ld in self.loads:
            pid = int(ld.get("pid", -1))
            if pid not in self.points:
                continue
            if self.is_point_effectively_hidden(pid) or (not self.show_points_geometry):
                continue
            fx, fy, mz = self._resolve_load_components(ld)
            if abs(mz) > 1e-12:
                p = self.points[pid]
                torque_vectors.append({
                    "x": p["x"],
                    "y": p["y"],
                    "mz": mz,
                    "label": self.format_number(mz),
                })
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

        for entry in self.get_friction_table():
            pid = int(entry.get("pid", -1))
            if pid not in self.points:
                continue
            if self.is_point_effectively_hidden(pid) or (not self.show_points_geometry):
                continue
            torque = entry.get("torque", None)
            if torque is None or abs(torque) <= 1e-12:
                continue
            p = self.points[pid]
            friction_torque_vectors.append({
                "x": p["x"],
                "y": p["y"],
                "mz": float(torque),
                "label": self.format_number(abs(float(torque))),
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

        friction_needed = len(friction_torque_vectors)
        while len(self._friction_torque_arrow_items) < friction_needed:
            item = TorqueArrowItem(QColor(60, 180, 80))
            item.set_line_width(self.torque_arrow_width * 0.8)
            self._friction_torque_arrow_items.append(item)
            self.scene.addItem(item)
        friction_mags = [abs(vec["mz"]) for vec in friction_torque_vectors]
        max_friction = max(friction_mags) if friction_mags else 0.0
        friction_target_radius = 18.0
        friction_scale = (friction_target_radius / max_friction) if max_friction > 1e-9 else 1.0
        friction_scale = max(0.2, min(3.0, friction_scale))
        for idx, item in enumerate(self._friction_torque_arrow_items):
            if idx >= friction_needed:
                item.setVisible(False)
                continue
            item.set_line_width(self.torque_arrow_width * 0.8)
            vec = friction_torque_vectors[idx]
            item.set_torque(
                vec["x"],
                vec["y"],
                vec["mz"],
                scale=friction_scale,
                label=str(vec.get("label", "")),
            )
