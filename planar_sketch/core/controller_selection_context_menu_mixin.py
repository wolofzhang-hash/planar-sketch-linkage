# -*- coding: utf-8 -*-
"""Context-menu handlers extracted from ControllerSelection.

Boundary/dependencies (provided by host controller):
- scene dicts: ``points``, ``links``, ``coincides``, ``point_lines``, ``point_splines``, ``point_spline_dists``, ``splines``
- selection helpers and scene-state methods: ``commit_drag_if_any()``, ``select_*_single()``
- command methods referenced by menu actions (``cmd_*``, ``set_driver_*``, ``add_measure_*`` ...)
- optional UI refs: ``win``, ``panel`` and ``win.sim_panel``
"""

from __future__ import annotations

from .controller_common import *


class ControllerSelectionContextMenuMixin:
    """Entity right-click context menus for sketch scene."""
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

            # --- Geometry helpers ---
            m.addAction(tr(lang, "context.point_on_line"), lambda: self.begin_point_on_line(pid))
            m.addAction(tr(lang, "context.point_on_spline"), lambda: self.begin_point_on_spline(pid))

            def _ask_psd():
                val, ok = QInputDialog.getDouble(
                    self.win,
                    tr(lang, "dialog.point_spline_dist_title"),
                    tr(lang, "dialog.point_spline_dist_label"),
                    20.0,
                    0.0,
                    1e9,
                    4,
                )
                if ok:
                    self.begin_point_spline_dist(pid, float(val))

            m.addAction(tr(lang, "context.point_spline_dist"), _ask_psd)

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

            if len(nbrs) >= 2:
                m.addSeparator()
                sub_angle_constraint = m.addMenu(tr(lang, "context.add_angle_constraint"))
                for idx, i in enumerate(nbrs[:-1]):
                    for k in nbrs[idx + 1:]:
                        sub_angle_constraint.addAction(
                            f"A(P{i}-P{pid}-P{k})",
                            lambda i=i, k=k: self._add_angle_constraint(i, pid, k),
                        )

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
                sub_load.addAction(tr(lang, "context.add_friction"), lambda: self._prompt_add_friction(pid))
                if nbrs:
                    sub_spring = sub_load.addMenu(tr(lang, "context.add_spring"))
                    for nb in nbrs:
                        sub_spring.addAction(
                            tr(lang, "context.pivot_tip").format(pivot=pid, tip=nb),
                            lambda nb=nb: self._prompt_add_spring(pid, nb),
                        )
                    sub_torsion = sub_load.addMenu(tr(lang, "context.add_torsion_spring"))
                    for nb in nbrs:
                        sub_torsion.addAction(
                            tr(lang, "context.pivot_tip").format(pivot=pid, tip=nb),
                            lambda nb=nb: self._prompt_add_torsion_spring(pid, nb),
                        )
                else:
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
                    self.win.sim_panel._mark_used_solver_unknown()
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

    def show_point_spline_dist_context_menu(self, pdid: int, global_pos):
            self.commit_drag_if_any()
            if not hasattr(self, "point_spline_dists") or pdid not in self.point_spline_dists:
                return
            self.select_point_spline_dist_single(pdid)
            pd = self.point_spline_dists[pdid]
            lang = getattr(self, "ui_language", "en")
            m = QMenu(self.win)
            m.addAction(
                tr(lang, "context.hide") if not pd.get("hidden", False) else tr(lang, "context.show"),
                lambda: self.cmd_set_point_spline_dist_hidden(pdid, not pd.get("hidden", False)),
            )
            m.addAction(
                tr(lang, "context.disable") if pd.get("enabled", True) else tr(lang, "context.enable"),
                lambda: self.cmd_set_point_spline_dist_enabled(pdid, not pd.get("enabled", True)),
            )
            m.addSeparator()
            m.addAction(tr(lang, "context.delete"), lambda: self.cmd_delete_point_spline_dist(pdid))
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
