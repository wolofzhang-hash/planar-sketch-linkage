# -*- coding: utf-8 -*-
"""Main window + menus."""

from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QGraphicsScene, QDockWidget, QStatusBar,
    QFileDialog, QMessageBox
)

from ..core.controller import SketchController
from .view import SketchView
from .panel import SketchPanel
from .items import PointItem, LinkItem, AngleItem
from .sim_panel import SimulationPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Planar Sketch v2.6.6")
        self.resize(1400, 900)
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.ctrl = SketchController(self.scene, self)
        self.view = SketchView(self.scene, self.ctrl)
        self.setCentralWidget(self.view)
        self.dock = QDockWidget("Sketch", self)
        self.panel = SketchPanel(self.ctrl)
        self.dock.setWidget(self.panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        # Simulation dock (driver/measurements, I/O curve export)
        self.sim_dock = QDockWidget("Simulation", self)
        self.sim_panel = SimulationPanel(self.ctrl)
        self.sim_dock.setWidget(self.sim_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sim_dock)
        self.tabifyDockWidget(self.dock, self.sim_dock)
        self.sim_dock.raise_()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Idle")
        self.current_file: Optional[str] = None
        self._build_menus()
        self._init_demo()
        self.update_undo_redo_actions()
        self.ctrl.update_status()
        self.scene.selectionChanged.connect(self._scene_selection_changed)

    def _scene_selection_changed(self):
        if self.panel.sync_guard: return
        self.panel.sync_guard = True
        try:
            items = self.scene.selectedItems()
            pids, lids, aids = [], [], []
            for it in items:
                if isinstance(it, PointItem) and (not self.ctrl.is_point_effectively_hidden(it.pid)) and self.ctrl.show_points_geometry:
                    pids.append(it.pid)
                elif isinstance(it, LinkItem):
                    lids.append(it.lid)
                elif isinstance(it, AngleItem):
                    aids.append(it.aid)
            self.ctrl.selected_point_ids = set(pids)
            self.ctrl.selected_point_id = pids[-1] if pids else None
            self.ctrl.selected_link_id = lids[-1] if lids else None
            self.ctrl.selected_angle_id = aids[-1] if aids else None
            if (self.ctrl.selected_link_id is not None) or (self.ctrl.selected_angle_id is not None):
                self.ctrl.selected_body_id = None
            self.panel.select_points_multi(sorted(self.ctrl.selected_point_ids))
            if self.ctrl.selected_link_id is not None:
                self.panel.select_link(self.ctrl.selected_link_id)
                self.panel.clear_angles_selection_only(); self.panel.clear_bodies_selection_only()
            elif self.ctrl.selected_angle_id is not None:
                self.panel.select_angle(self.ctrl.selected_angle_id)
                self.panel.clear_links_selection_only(); self.panel.clear_bodies_selection_only()
            else:
                self.panel.clear_links_selection_only(); self.panel.clear_angles_selection_only()
            self.ctrl.update_graphics()
            self.ctrl.update_status()
            self.sim_panel.refresh_labels()
            if hasattr(self, "sim_panel"):
                self.sim_panel.refresh_labels()
        finally:
            self.panel.sync_guard = False

    def _build_menus(self):
        mb = self.menuBar()
        m_file = mb.addMenu("File")
        m_file.addAction("New", self.file_new)
        m_file.addAction("Open...", self.file_open)
        m_file.addAction("Save", self.file_save)
        m_file.addAction("Save As...", self.file_save_as)
        m_file.addSeparator()
        m_file.addAction("Exit", self.close)

        m_edit = mb.addMenu("Edit")
        self.act_undo = QAction("Undo", self); self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.ctrl.stack.undo); m_edit.addAction(self.act_undo)
        self.act_redo = QAction("Redo", self); self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.ctrl.stack.redo); m_edit.addAction(self.act_redo)
        m_edit.addSeparator()
        act_delete = QAction("Delete Selected", self); act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        act_delete.triggered.connect(self.delete_selected); m_edit.addAction(act_delete)

        m_sketch = mb.addMenu("Sketch")
        m_sketch.addAction("Create Line", self.ctrl.begin_create_line)
        m_sketch.addAction("Solve Accurate (SciPy)", self.solve_accurate_scipy)

        m_view = mb.addMenu("View")
        self.act_pm = QAction("Show Point Markers", self, checkable=True); self.act_pm.setChecked(True)
        self.act_pm.triggered.connect(lambda c: self._toggle_pm(c)); m_view.addAction(self.act_pm)
        self.act_dm = QAction("Show Dimension Markers", self, checkable=True); self.act_dm.setChecked(True)
        self.act_dm.triggered.connect(lambda c: self._toggle_dm(c)); m_view.addAction(self.act_dm)
        self.act_body_color = QAction("Show Rigid Body Coloring", self, checkable=True); self.act_body_color.setChecked(True)
        self.act_body_color.triggered.connect(lambda c: self._toggle_body_coloring(c)); m_view.addAction(self.act_body_color)
        m_view.addSeparator()
        m_presets = m_view.addMenu("Presets")
        m_presets.addAction("Show All", self.preset_show_all)
        m_presets.addAction("Points Only", self.preset_points_only)
        m_presets.addAction("Links Only", self.preset_links_only)
        m_view.addSeparator()
        m_view.addAction("Reset View", self.view.reset_view)
        m_view.addAction("Fit All", self.view.fit_all)

    def solve_accurate_scipy(self):
        """Run SciPy kinematics solver once."""
        self.ctrl.commit_drag_if_any()
        ok, msg = self.ctrl.solve_constraints_scipy(max_nfev=300)
        if not ok:
            QMessageBox.warning(self, "SciPy Solver", msg)
        else:
            self.statusBar().showMessage("SciPy solve OK")

    def preset_show_all(self):
        self.ctrl.show_points_geometry = True
        self.ctrl.show_links_geometry = True
        self.ctrl.show_angles_geometry = True
        self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)

    def preset_points_only(self):
        self.ctrl.show_points_geometry = True
        self.ctrl.show_links_geometry = False
        self.ctrl.show_angles_geometry = False
        self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)

    def preset_links_only(self):
        self.ctrl.show_points_geometry = True
        self.ctrl.show_links_geometry = True
        self.ctrl.show_angles_geometry = False
        self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)

    def update_undo_redo_actions(self):
        self.act_undo.setEnabled(self.ctrl.stack.can_undo())
        self.act_redo.setEnabled(self.ctrl.stack.can_redo())

    def _toggle_pm(self, checked: bool):
        self.ctrl.show_point_markers = bool(checked)
        self.ctrl.update_graphics()
    def _toggle_dm(self, checked: bool):
        self.ctrl.show_dim_markers = bool(checked)
        self.ctrl.update_graphics()
    def _toggle_body_coloring(self, checked: bool):
        self.ctrl.show_body_coloring = bool(checked)
        self.ctrl.update_graphics()

    def delete_selected(self):
        self.ctrl.commit_drag_if_any()
        if self.ctrl.selected_point_ids:
            for pid in sorted(list(self.ctrl.selected_point_ids), reverse=True):
                self.ctrl.cmd_delete_point(pid)
            return
        if self.ctrl.selected_link_id is not None:
            self.ctrl.cmd_delete_link(self.ctrl.selected_link_id); return
        if self.ctrl.selected_angle_id is not None:
            self.ctrl.cmd_delete_angle(self.ctrl.selected_angle_id); return
        if self.ctrl.selected_body_id is not None:
            self.ctrl.cmd_delete_body(self.ctrl.selected_body_id); return

    def file_new(self):
        self.ctrl.commit_drag_if_any()
        self.ctrl.load_dict({"points": [], "links": [], "angles": [], "bodies": [], "parameters": [], "version": "2.6.0"})
        self.ctrl.stack.clear()
        self.current_file = None

    def file_open(self):
        self.ctrl.commit_drag_if_any()
        path, _ = QFileDialog.getOpenFileName(self, "Open Sketch", "", "Sketch JSON (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.ctrl.load_dict(data)
            self.current_file = path
            self.view.fit_all()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def file_save(self):
        self.ctrl.commit_drag_if_any()
        if not self.current_file:
            return self.file_save_as()
        try:
            data = self.ctrl.to_dict()
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def file_save_as(self):
        self.ctrl.commit_drag_if_any()
        path, _ = QFileDialog.getSaveFileName(self, "Save Sketch As", "", "Sketch JSON (*.json)")
        if not path: return
        if not path.lower().endswith(".json"): path += ".json"
        self.current_file = path
        self.file_save()

    def _init_demo(self):
        self.ctrl.cmd_add_point(0, 0)
        self.ctrl.cmd_add_point(160, 0)
        self.ctrl.cmd_add_point(80, 120)
        self.ctrl.cmd_add_link(0, 1)
        self.ctrl.cmd_add_link(1, 2)
        self.ctrl.cmd_add_angle(0, 1, 2, 45.0)
        self.ctrl.cmd_add_body_from_points([0, 1, 2])
        self.ctrl.cmd_set_body_color(0, "Green")
        self.ctrl.solve_constraints(); self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)
