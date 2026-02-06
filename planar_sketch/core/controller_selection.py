# -*- coding: utf-8 -*-
"""SketchController selection/menu/command helpers."""

from __future__ import annotations

import uuid

from .controller_common import *


class ControllerSelection:
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

    def focus_link_in_panel(self, lid: int) -> None:
        self.select_link_single(lid)
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
        if self.panel:
            self.panel.focus_constraint_key(f"S{psid}")

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

    def focus_body_in_panel(self, bid: int) -> None:
        self.select_body_single(bid)
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
        if self.panel:
            self.panel.focus_spline(sid)

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

    def focus_point_in_panel(self, pid: int) -> None:
        self.select_point_single(pid, keep_others=False)
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
                ctrl._create_spline(sid, pts, hidden=False, closed=False)
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
                ctrl.solve_constraints(); ctrl.update_graphics()
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
                ctrl.solve_constraints(); ctrl.update_graphics()
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
            name = "Add Point On Line (s)"
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
            name = "Add Point On Spline"
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

        point_line_ids = [plid for plid, pl in self.point_lines.items() if int(pl.get("p", -1)) == pid]
        if nbrs or point_line_ids:
            m.addSeparator()
            sub_drv = m.addMenu(tr(lang, "context.set_driver"))

            if nbrs:
                sub_angle = sub_drv.addMenu(tr(lang, "context.angle_pivot_tip"))
                for nb in nbrs:
                    sub_angle.addAction(
                        tr(lang, "context.pivot_tip").format(pivot=pid, tip=nb),
                        lambda nb=nb: self.set_driver_angle(pid, nb),
                    )
            if point_line_ids:
                if nbrs:
                    sub_drv.addSeparator()
                if len(point_line_ids) == 1:
                    plid = point_line_ids[0]
                    sub_drv.addAction(tr(lang, "context.set_translation_driver"), lambda plid=plid: self.set_driver_translation(plid))
                else:
                    sub_trans = sub_drv.addMenu(tr(lang, "context.set_translation_driver"))
                    for plid in point_line_ids:
                        pl = self.point_lines.get(plid, {})
                        sub_trans.addAction(
                            tr(lang, "context.translation_line").format(
                                p=pl.get("p"),
                                i=pl.get("i"),
                                j=pl.get("j"),
                            ),
                            lambda plid=plid: self.set_driver_translation(plid),
                        )

            sub_drv.addSeparator()
            sub_drv.addAction(tr(lang, "context.clear_driver"), self.clear_driver)

            sub_meas = m.addMenu(tr(lang, "context.add_measurement"))

            sub_mvec = sub_meas.addMenu(tr(lang, "context.angle_world"))
            for nb in nbrs:
                sub_mvec.addAction(f"A(P{pid}->P{nb})", lambda nb=nb: self.add_measure_angle(pid, nb))

            sub_mjoint = sub_meas.addMenu(tr(lang, "context.joint_angle"))
            if len(nbrs) >= 2:
                for i in nbrs:
                    for k in nbrs:
                        if i == k:
                            continue
                        sub_mjoint.addAction(f"A(P{i}-P{pid}-P{k})", lambda i=i, k=k: self.add_measure_joint(i, pid, k))

            if point_line_ids:
                if len(point_line_ids) == 1:
                    plid = point_line_ids[0]
                    sub_meas.addAction(
                        tr(lang, "context.translation_measurement"),
                        lambda plid=plid: self.add_measure_translation(plid),
                    )
                else:
                    sub_trans_meas = sub_meas.addMenu(tr(lang, "context.translation_measurement"))
                    for plid in point_line_ids:
                        pl = self.point_lines.get(plid, {})
                        sub_trans_meas.addAction(
                            tr(lang, "context.translation_line").format(
                                p=pl.get("p"),
                                i=pl.get("i"),
                                j=pl.get("j"),
                            ),
                            lambda plid=plid: self.add_measure_translation(plid),
                        )

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
            sub_load.addAction(tr(lang, "context.add_spring"), lambda: self._prompt_add_spring(pid))
            sub_load.addAction(tr(lang, "context.add_torsion_spring"), lambda: self._prompt_add_torsion_spring(pid))
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
        m.addAction(tr(lang, "context.set_translation_driver"), lambda: self.set_driver_translation(plid))
        sub_meas = m.addMenu(tr(lang, "context.add_measurement"))
        sub_meas.addAction(tr(lang, "context.translation_measurement"), lambda: self.add_measure_translation(plid))
        sub_meas.addSeparator()
        sub_meas.addAction(tr(lang, "context.clear_measurements"), self.clear_measures)
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
        payload = self.default_project_dict(project_uuid=self._ensure_project_uuid())
        payload.update(
            {
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
                        "closed": bool(s.get("closed", False)),
                    }
                    for sid, s in sorted(self.splines.items(), key=lambda kv: kv[0])
                ],
                "coincides": [
                    {"id": cid, "a": c["a"], "b": c["b"], "hidden": bool(c.get("hidden", False)), "enabled": bool(c.get("enabled", True))}
                    for cid, c in sorted(self.coincides.items(), key=lambda kv: kv[0])
                ],
                "point_lines": [
                    {
                        "id": plid,
                        "p": pl.get("p"),
                        "i": pl.get("i"),
                        "j": pl.get("j"),
                        "hidden": bool(pl.get("hidden", False)),
                        "enabled": bool(pl.get("enabled", True)),
                        **({"s": float(pl.get("s", 0.0))} if "s" in pl else {}),
                        **({"s_expr": str(pl.get("s_expr", ""))} if pl.get("s_expr") else {}),
                        **({"name": str(pl.get("name", ""))} if pl.get("name") else {}),
                    }
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
                    "type": str(self.driver.get("type", "angle")),
                    "pivot": self.driver.get("pivot"),
                    "tip": self.driver.get("tip"),
                    "rad": float(self.driver.get("rad", 0.0)),
                    "plid": self.driver.get("plid"),
                    "s_base": self.driver.get("s_base"),
                    "value": self.driver.get("value"),
                    "sweep_start": self.driver.get("sweep_start"),
                    "sweep_end": self.driver.get("sweep_end"),
                },
                "drivers": [
                    {
                        "enabled": bool(d.get("enabled", False)),
                        "type": str(d.get("type", "angle")),
                        "pivot": d.get("pivot"),
                        "tip": d.get("tip"),
                        "rad": float(d.get("rad", 0.0)),
                        "plid": d.get("plid"),
                        "s_base": d.get("s_base"),
                        "value": d.get("value"),
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
        )
        return payload

    def _ensure_project_uuid(self, candidate: Optional[str] = None) -> str:
        if candidate and isinstance(candidate, str) and candidate.strip():
            self.project_uuid = candidate.strip()
        if not getattr(self, "project_uuid", ""):
            self.project_uuid = str(uuid.uuid4())
        return self.project_uuid

    def default_project_dict(self, project_uuid: Optional[str] = None, force_new_uuid: bool = False) -> Dict[str, Any]:
        if force_new_uuid:
            uuid_val = str(uuid.uuid4())
            self.project_uuid = uuid_val
        else:
            uuid_val = self._ensure_project_uuid(project_uuid)
        return {
            "version": "2.7.0",
            "project_uuid": uuid_val,
            "display_precision": int(getattr(self, "display_precision", 3)),
            "load_arrow_width": float(getattr(self, "load_arrow_width", 1.6)),
            "torque_arrow_width": float(getattr(self, "torque_arrow_width", 1.6)),
            "parameters": [],
            "background_image": {
                "path": None,
                "visible": True,
                "opacity": 0.6,
                "grayscale": False,
                "scale": 1.0,
                "pos": [0.0, 0.0],
            },
            "points": [],
            "constraints": [],
            "links": [],
            "angles": [],
            "splines": [],
            "coincides": [],
            "point_lines": [],
            "point_splines": [],
            "bodies": [],
            "driver": dict(self._default_driver()),
            "drivers": [],
            "output": dict(self._default_output()),
            "outputs": [],
            "measures": [],
            "loads": [],
            "load_measures": [],
            "sweep": {
                "start": float(self.sweep_settings.get("start", 0.0)),
                "end": float(self.sweep_settings.get("end", 360.0)),
                "step": float(self.sweep_settings.get("step", 200.0)),
            },
        }

    def merge_project_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        has_uuid = isinstance(data, dict) and str(data.get("project_uuid", "")).strip()
        base = self.default_project_dict(
            project_uuid=(data.get("project_uuid") if has_uuid else None),
            force_new_uuid=not has_uuid,
        )
        if not isinstance(data, dict):
            return base
        for key, val in data.items():
            if key in ("background_image", "driver", "output", "sweep") and isinstance(val, dict):
                base[key] = {**base.get(key, {}), **val}
            else:
                base[key] = val
        return base

    def validate_project_schema(self, data: Any) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []
        if not isinstance(data, dict):
            errors.append("Project data must be a JSON object.")
            return warnings, errors
        schema_keys = {
            "version",
            "project_uuid",
            "display_precision",
            "load_arrow_width",
            "torque_arrow_width",
            "parameters",
            "background_image",
            "points",
            "constraints",
            "links",
            "angles",
            "splines",
            "coincides",
            "point_lines",
            "point_splines",
            "bodies",
            "driver",
            "drivers",
            "output",
            "outputs",
            "measures",
            "loads",
            "load_measures",
            "sweep",
        }
        for key in sorted(schema_keys):
            if key not in data:
                warnings.append(f"Missing key: {key}")
        list_keys = [
            "points",
            "constraints",
            "links",
            "angles",
            "splines",
            "coincides",
            "point_lines",
            "point_splines",
            "bodies",
            "parameters",
            "drivers",
            "outputs",
            "measures",
            "loads",
            "load_measures",
        ]
        dict_keys = ["background_image", "driver", "output", "sweep"]
        for key in list_keys:
            if key in data and not isinstance(data.get(key), list):
                errors.append(f"Key '{key}' should be a list.")
        for key in dict_keys:
            if key in data and not isinstance(data.get(key), dict):
                errors.append(f"Key '{key}' should be an object.")
        if "project_uuid" in data and not isinstance(data.get("project_uuid"), str):
            errors.append("Key 'project_uuid' should be a string.")
        return warnings, errors

    def load_dict(self, data: Dict[str, Any], clear_undo: bool = True, action: str = "load a new model") -> bool:
        if not self._confirm_stop_replay(action):
            return False
        if isinstance(data, dict):
            self._ensure_project_uuid(data.get("project_uuid"))
        else:
            self._ensure_project_uuid()
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
            self._create_spline(sid, pts, bool(s.get("hidden", False)), closed=bool(s.get("closed", False)))
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
        elif isinstance(driver, dict) and driver:
            legacy_driver = self._normalize_driver(driver)
            if legacy_driver.get("enabled"):
                if "rad" not in driver:
                    legacy_driver["_needs_rad"] = True
                self.drivers.append(legacy_driver)

        for drv in self.drivers:
            if not drv.pop("_needs_rad", False):
                continue
            dtype = str(drv.get("type", "angle"))
            if dtype != "angle":
                continue
            piv = drv.get("pivot")
            tip = drv.get("tip")
            if piv is not None and tip is not None:
                ang = self.get_angle_rad(int(piv), int(tip))
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
        elif isinstance(output, dict) and output:
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
                ang = self.get_angle_rad(int(piv), int(tip))
                if ang is not None:
                    out["rad"] = float(ang)
        self._sync_primary_output()
        self.measures = []
        for m in measures:
            mtype = str(m.get("type", "")).lower()
            name = str(m.get("name", ""))
            if mtype == "angle":
                pivot = m.get("pivot")
                tip = m.get("tip")
                if pivot is None or tip is None:
                    continue
                if int(pivot) in self.points and int(tip) in self.points:
                    self.measures.append({
                        "type": "angle",
                        "pivot": int(pivot),
                        "tip": int(tip),
                        "name": name or f"ang P{int(pivot)}->P{int(tip)}",
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
            elif ltype == "spring":
                ref_pid = int(ld.get("ref_pid", -1))
                k = float(ld.get("k", 0.0))
                f0 = float(ld.get("f0", 0.0))
                if ref_pid in self.points:
                    self.add_load_spring(pid, ref_pid, k, f0)
            elif ltype == "torsion_spring":
                ref_pid = int(ld.get("ref_pid", -1))
                k = float(ld.get("k", 0.0))
                theta0 = float(ld.get("theta0", 0.0))
                m0 = float(ld.get("m0", 0.0))
                if ref_pid in self.points:
                    self.add_load_torsion_spring(pid, ref_pid, k, theta0, m0)
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
                s_expr = str(pl.get("s_expr", ""))
                name = str(pl.get("name", ""))
                s_val = None
                if "s" in pl or s_expr:
                    try:
                        s_val = float(pl.get("s", 0.0))
                    except Exception:
                        s_val = 0.0
                self._create_point_line(
                    plid, p, i, j,
                    hidden=bool(pl.get("hidden", False)),
                    enabled=bool(pl.get("enabled", True)),
                    s=s_val,
                    s_expr=s_expr,
                    name=name,
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
