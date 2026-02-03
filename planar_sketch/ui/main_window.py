# -*- coding: utf-8 -*-
"""Main window + menus."""

from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QGraphicsScene, QDockWidget, QStatusBar,
    QFileDialog, QMessageBox, QInputDialog, QToolBar, QStyle
)

from ..core.controller import SketchController
from .view import SketchView
from .panel import SketchPanel
from .items import PointItem, LinkItem, AngleItem, SplineItem, PointSplineItem
from .sim_panel import SimulationPanel
from .settings_dialog import SettingsDialog
from .i18n import tr


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Planar Sketch v2.8.2")
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
        self.sim_dock = QDockWidget("Analysis", self)
        self.sim_panel = SimulationPanel(self.ctrl)
        self.sim_dock.setWidget(self.sim_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sim_dock)
        self.tabifyDockWidget(self.dock, self.sim_dock)
        self.sim_dock.raise_()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(tr(self.ctrl.ui_language, "status.idle"))
        self.current_file: Optional[str] = None
        self._build_menus()
        self._build_toolbars()
        self.apply_language()
        self.file_new()
        self.update_undo_redo_actions()
        self.ctrl.update_status()
        self.scene.selectionChanged.connect(self._scene_selection_changed)

    def _scene_selection_changed(self):
        if self.panel.sync_guard: return
        self.panel.sync_guard = True
        try:
            items = self.scene.selectedItems()
            pids, lids, aids, sids, psids = [], [], [], [], []
            for it in items:
                if isinstance(it, PointItem) and (not self.ctrl.is_point_effectively_hidden(it.pid)) and self.ctrl.show_points_geometry:
                    pids.append(it.pid)
                elif isinstance(it, LinkItem):
                    lids.append(it.lid)
                elif isinstance(it, AngleItem):
                    aids.append(it.aid)
                elif isinstance(it, SplineItem):
                    sids.append(it.sid)
                elif isinstance(it, PointSplineItem):
                    psids.append(it.psid)
            self.ctrl.selected_point_ids = set(pids)
            self.ctrl.selected_point_id = pids[-1] if pids else None
            self.ctrl.selected_link_id = lids[-1] if lids else None
            self.ctrl.selected_angle_id = aids[-1] if aids else None
            self.ctrl.selected_spline_id = sids[-1] if sids else None
            self.ctrl.selected_point_spline_id = psids[-1] if psids else None
            if (self.ctrl.selected_link_id is not None) or (self.ctrl.selected_angle_id is not None) or (self.ctrl.selected_spline_id is not None):
                self.ctrl.selected_body_id = None
            self.panel.select_points_multi(sorted(self.ctrl.selected_point_ids))
            if self.ctrl.selected_link_id is not None:
                self.panel.select_link(self.ctrl.selected_link_id)
                self.panel.clear_angles_selection_only(); self.panel.clear_splines_selection_only(); self.panel.clear_bodies_selection_only()
            elif self.ctrl.selected_angle_id is not None:
                self.panel.select_angle(self.ctrl.selected_angle_id)
                self.panel.clear_links_selection_only(); self.panel.clear_splines_selection_only(); self.panel.clear_bodies_selection_only()
            elif self.ctrl.selected_spline_id is not None:
                self.panel.select_spline(self.ctrl.selected_spline_id)
                self.panel.clear_links_selection_only(); self.panel.clear_angles_selection_only(); self.panel.clear_bodies_selection_only()
            else:
                self.panel.clear_links_selection_only(); self.panel.clear_angles_selection_only(); self.panel.clear_splines_selection_only()
            self.ctrl.update_graphics()
            self.ctrl.update_status()
            self.sim_panel.refresh_labels()
            if hasattr(self, "sim_panel"):
                self.sim_panel.refresh_labels()
        finally:
            self.panel.sync_guard = False

    def _build_menus(self):
        mb = self.menuBar()
        self.menu_file = mb.addMenu("")
        self.menu_file.aboutToShow.connect(lambda: self._set_active_ribbon("file"))
        self.act_file_new = QAction("", self)
        self.act_file_new.triggered.connect(self.file_new)
        self.menu_file.addAction(self.act_file_new)
        self.act_file_open = QAction("", self)
        self.act_file_open.triggered.connect(self.file_open)
        self.menu_file.addAction(self.act_file_open)
        self.act_file_save = QAction("", self)
        self.act_file_save.triggered.connect(self.file_save)
        self.menu_file.addAction(self.act_file_save)
        self.act_file_save_as = QAction("", self)
        self.act_file_save_as.triggered.connect(self.file_save_as)
        self.menu_file.addAction(self.act_file_save_as)
        self.menu_file.addSeparator()
        self.act_file_exit = QAction("", self)
        self.act_file_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.act_file_exit)

        self.menu_edit = mb.addMenu("")
        self.menu_edit.aboutToShow.connect(lambda: self._set_active_ribbon("edit"))
        self.act_undo = QAction("", self); self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.ctrl.stack.undo); self.menu_edit.addAction(self.act_undo)
        self.act_redo = QAction("", self); self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.ctrl.stack.redo); self.menu_edit.addAction(self.act_redo)
        self.menu_edit.addSeparator()
        self.act_delete_selected = QAction("", self); self.act_delete_selected.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete_selected.triggered.connect(self.delete_selected); self.menu_edit.addAction(self.act_delete_selected)
        self.act_repeat_model = QAction("", self)
        self.act_repeat_model.setShortcut(QKeySequence("F4"))
        self.act_repeat_model.triggered.connect(self.ctrl.repeat_last_model_action)
        self.menu_edit.addAction(self.act_repeat_model)
        self.menu_edit.addSeparator()
        self.act_settings = QAction("", self)
        self.act_settings.triggered.connect(self.open_settings)
        self.menu_edit.addAction(self.act_settings)

        self.menu_sketch = mb.addMenu("")
        self.menu_sketch.aboutToShow.connect(lambda: self._set_active_ribbon("sketch"))
        self.act_create_line = QAction("", self)
        self.act_create_line.triggered.connect(self.ctrl.begin_create_line)
        self.menu_sketch.addAction(self.act_create_line)
        self.act_create_spline = QAction("", self)
        self.act_create_spline.triggered.connect(self.ctrl._add_spline_from_selection)
        self.menu_sketch.addAction(self.act_create_spline)
        self.act_solve_accurate = QAction("", self)
        self.act_solve_accurate.triggered.connect(self.solve_accurate_scipy)
        self.menu_sketch.addAction(self.act_solve_accurate)

        self.menu_view = mb.addMenu("")
        self.menu_view.aboutToShow.connect(lambda: self._set_active_ribbon("view"))
        self.act_pm = QAction("", self, checkable=True); self.act_pm.setChecked(True)
        self.act_pm.triggered.connect(lambda c: self._toggle_pm(c)); self.menu_view.addAction(self.act_pm)
        self.act_dm = QAction("", self, checkable=True); self.act_dm.setChecked(True)
        self.act_dm.triggered.connect(lambda c: self._toggle_dm(c)); self.menu_view.addAction(self.act_dm)
        self.act_body_color = QAction("", self, checkable=True); self.act_body_color.setChecked(True)
        self.act_body_color.triggered.connect(lambda c: self._toggle_body_coloring(c)); self.menu_view.addAction(self.act_body_color)
        self.act_splines = QAction("", self, checkable=True); self.act_splines.setChecked(True)
        self.act_splines.triggered.connect(lambda c: self._toggle_splines(c)); self.menu_view.addAction(self.act_splines)
        self.act_load_arrows = QAction("", self, checkable=True); self.act_load_arrows.setChecked(True)
        self.act_load_arrows.triggered.connect(lambda c: self._toggle_load_arrows(c)); self.menu_view.addAction(self.act_load_arrows)
        self.menu_view.addSeparator()
        self.menu_bg = self.menu_view.addMenu("")
        self.act_bg_load = QAction("", self)
        self.act_bg_load.triggered.connect(self.load_background_image)
        self.menu_bg.addAction(self.act_bg_load)
        self.act_bg_visible = QAction("", self, checkable=True); self.act_bg_visible.setChecked(True)
        self.act_bg_visible.triggered.connect(lambda c: self._toggle_background_visible(c)); self.menu_bg.addAction(self.act_bg_visible)
        self.act_bg_gray = QAction("", self, checkable=True)
        self.act_bg_gray.triggered.connect(lambda c: self._toggle_background_grayscale(c)); self.menu_bg.addAction(self.act_bg_gray)
        self.act_bg_opacity = QAction("", self)
        self.act_bg_opacity.triggered.connect(self.set_background_opacity)
        self.menu_bg.addAction(self.act_bg_opacity)
        self.act_bg_clear = QAction("", self)
        self.act_bg_clear.triggered.connect(self.clear_background_image)
        self.menu_bg.addAction(self.act_bg_clear)
        self.menu_presets = self.menu_view.addMenu("")
        self.act_preset_show_all = QAction("", self)
        self.act_preset_show_all.triggered.connect(self.preset_show_all)
        self.menu_presets.addAction(self.act_preset_show_all)
        self.act_preset_points_only = QAction("", self)
        self.act_preset_points_only.triggered.connect(self.preset_points_only)
        self.menu_presets.addAction(self.act_preset_points_only)
        self.act_preset_links_only = QAction("", self)
        self.act_preset_links_only.triggered.connect(self.preset_links_only)
        self.menu_presets.addAction(self.act_preset_links_only)
        self.menu_view.addSeparator()
        self.act_reset_view = QAction("", self)
        self.act_reset_view.triggered.connect(self.view.reset_view)
        self.menu_view.addAction(self.act_reset_view)
        self.act_fit_all = QAction("", self)
        self.act_fit_all.triggered.connect(self.view.fit_all)
        self.menu_view.addAction(self.act_fit_all)

    def _build_toolbars(self) -> None:
        icon_size = QSize(20, 20)
        self.toolbar_file = QToolBar(self)
        self.toolbar_file.setIconSize(icon_size)
        self.toolbar_file.setMovable(False)
        self.toolbar_file.setFloatable(False)
        self.toolbar_file.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar_file)
        self.toolbar_file.addAction(self.act_file_new)
        self.toolbar_file.addAction(self.act_file_open)
        self.toolbar_file.addAction(self.act_file_save)
        self.toolbar_file.addAction(self.act_file_save_as)

        self.toolbar_edit = QToolBar(self)
        self.toolbar_edit.setIconSize(icon_size)
        self.toolbar_edit.setMovable(False)
        self.toolbar_edit.setFloatable(False)
        self.toolbar_edit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar_edit)
        self.toolbar_edit.addAction(self.act_undo)
        self.toolbar_edit.addAction(self.act_redo)
        self.toolbar_edit.addAction(self.act_delete_selected)
        self.toolbar_edit.addAction(self.act_repeat_model)
        self.toolbar_edit.addSeparator()
        self.toolbar_edit.addAction(self.act_settings)

        self.toolbar_sketch = QToolBar(self)
        self.toolbar_sketch.setIconSize(icon_size)
        self.toolbar_sketch.setMovable(False)
        self.toolbar_sketch.setFloatable(False)
        self.toolbar_sketch.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar_sketch)
        self.toolbar_sketch.addAction(self.act_create_line)
        self.toolbar_sketch.addAction(self.act_create_spline)
        self.toolbar_sketch.addAction(self.act_solve_accurate)

        self.toolbar_view = QToolBar(self)
        self.toolbar_view.setIconSize(icon_size)
        self.toolbar_view.setMovable(False)
        self.toolbar_view.setFloatable(False)
        self.toolbar_view.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar_view)
        self.toolbar_view.addAction(self.act_pm)
        self.toolbar_view.addAction(self.act_dm)
        self.toolbar_view.addAction(self.act_body_color)
        self.toolbar_view.addAction(self.act_splines)
        self.toolbar_view.addAction(self.act_load_arrows)
        self.toolbar_view.addSeparator()
        self.toolbar_view.addAction(self.act_bg_load)
        self.toolbar_view.addAction(self.act_bg_visible)
        self.toolbar_view.addAction(self.act_bg_gray)
        self.toolbar_view.addAction(self.act_bg_opacity)
        self.toolbar_view.addAction(self.act_bg_clear)
        self.toolbar_view.addSeparator()
        self.toolbar_view.addAction(self.act_preset_show_all)
        self.toolbar_view.addAction(self.act_preset_points_only)
        self.toolbar_view.addAction(self.act_preset_links_only)
        self.toolbar_view.addSeparator()
        self.toolbar_view.addAction(self.act_reset_view)
        self.toolbar_view.addAction(self.act_fit_all)

        self._apply_action_icons()
        self._set_active_ribbon("file")

    def _set_active_ribbon(self, key: str) -> None:
        toolbars = {
            "file": self.toolbar_file,
            "edit": self.toolbar_edit,
            "sketch": self.toolbar_sketch,
            "view": self.toolbar_view,
        }
        for name, toolbar in toolbars.items():
            toolbar.setVisible(name == key)

    def _apply_action_icons(self) -> None:
        style = self.style()
        self.act_file_new.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.act_file_open.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.act_file_save.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.act_file_save_as.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.act_file_exit.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
        self.act_undo.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.act_redo.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.act_delete_selected.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.act_repeat_model.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.act_settings.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.act_create_line.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton))
        self.act_create_spline.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.act_solve_accurate.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.act_pm.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.act_dm.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.act_body_color.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DriveDVDIcon))
        self.act_splines.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        self.act_load_arrows.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.act_bg_load.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.act_bg_visible.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.act_bg_gray.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.act_bg_opacity.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.act_bg_clear.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton))
        self.act_preset_show_all.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.act_preset_points_only.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogNoButton))
        self.act_preset_links_only.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogNoButton))
        self.act_reset_view.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.act_fit_all.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))

    def apply_language(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        self.menu_file.setTitle(tr(lang, "menu.file"))
        self.menu_edit.setTitle(tr(lang, "menu.edit"))
        self.menu_sketch.setTitle(tr(lang, "menu.sketch"))
        self.menu_view.setTitle(tr(lang, "menu.view"))
        self.menu_bg.setTitle(tr(lang, "menu.background_image"))
        self.menu_presets.setTitle(tr(lang, "menu.presets"))
        if hasattr(self, "toolbar_file"):
            self.toolbar_file.setWindowTitle(tr(lang, "menu.file"))
            self.toolbar_edit.setWindowTitle(tr(lang, "menu.edit"))
            self.toolbar_sketch.setWindowTitle(tr(lang, "menu.sketch"))
            self.toolbar_view.setWindowTitle(tr(lang, "menu.view"))
        self.act_file_new.setText(tr(lang, "action.new"))
        self.act_file_open.setText(tr(lang, "action.open"))
        self.act_file_save.setText(tr(lang, "action.save"))
        self.act_file_save_as.setText(tr(lang, "action.save_as"))
        self.act_file_exit.setText(tr(lang, "action.exit"))
        self.act_undo.setText(tr(lang, "action.undo"))
        self.act_redo.setText(tr(lang, "action.redo"))
        self.act_delete_selected.setText(tr(lang, "action.delete_selected"))
        self.act_repeat_model.setText(tr(lang, "action.repeat_last_model_action"))
        self.act_settings.setText(tr(lang, "action.settings"))
        self.act_create_line.setText(tr(lang, "action.create_line"))
        self.act_create_spline.setText(tr(lang, "action.create_spline"))
        self.act_solve_accurate.setText(tr(lang, "action.solve_accurate_scipy"))
        self.act_pm.setText(tr(lang, "action.show_point_markers"))
        self.act_dm.setText(tr(lang, "action.show_dimension_markers"))
        self.act_body_color.setText(tr(lang, "action.show_rigid_body_coloring"))
        self.act_splines.setText(tr(lang, "action.show_splines"))
        self.act_load_arrows.setText(tr(lang, "action.show_load_arrows"))
        self.act_bg_load.setText(tr(lang, "action.load_background"))
        self.act_bg_visible.setText(tr(lang, "action.show_background"))
        self.act_bg_gray.setText(tr(lang, "action.grayscale"))
        self.act_bg_opacity.setText(tr(lang, "action.set_opacity"))
        self.act_bg_clear.setText(tr(lang, "action.clear"))
        self.act_preset_show_all.setText(tr(lang, "action.preset_show_all"))
        self.act_preset_points_only.setText(tr(lang, "action.preset_points_only"))
        self.act_preset_links_only.setText(tr(lang, "action.preset_links_only"))
        self.act_reset_view.setText(tr(lang, "action.reset_view"))
        self.act_fit_all.setText(tr(lang, "action.fit_all"))
        self.dock.setWindowTitle(tr(lang, "dock.sketch"))
        self.sim_dock.setWindowTitle(tr(lang, "dock.analysis"))
        self.panel.apply_language()
        self.sim_panel.apply_language()

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
        self.ctrl.show_splines_geometry = True
        self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)

    def preset_points_only(self):
        self.ctrl.show_points_geometry = True
        self.ctrl.show_links_geometry = False
        self.ctrl.show_angles_geometry = False
        self.ctrl.show_splines_geometry = False
        self.ctrl.update_graphics()
        self.panel.defer_refresh_all(keep_selection=True)

    def preset_links_only(self):
        self.ctrl.show_points_geometry = True
        self.ctrl.show_links_geometry = True
        self.ctrl.show_angles_geometry = False
        self.ctrl.show_splines_geometry = False
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
    def _toggle_splines(self, checked: bool):
        self.ctrl.show_splines_geometry = bool(checked)
        self.ctrl.update_graphics()
    def _toggle_load_arrows(self, checked: bool):
        self.ctrl.show_load_arrows = bool(checked)
        self.ctrl.update_graphics()
    def _toggle_background_visible(self, checked: bool):
        self.ctrl.set_background_visible(bool(checked))
    def _toggle_background_grayscale(self, checked: bool):
        self.ctrl.set_background_grayscale(bool(checked))

    def open_settings(self):
        dlg = SettingsDialog(self.ctrl, self)
        if dlg.exec():
            self.ctrl.display_precision = dlg.decimal_places()
            self.ctrl.load_arrow_width = dlg.load_arrow_width()
            self.ctrl.torque_arrow_width = dlg.torque_arrow_width()
            selected_language = dlg.language()
            if selected_language != getattr(self.ctrl, "ui_language", "en"):
                self.ctrl.ui_language = selected_language
                self.apply_language()
            self.ctrl.update_graphics()
            self.panel.defer_refresh_all(keep_selection=True)
            if hasattr(self, "sim_panel"):
                self.sim_panel.refresh_labels()

    def load_background_image(self):
        self.ctrl.commit_drag_if_any()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Background Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)",
        )
        if not path:
            return
        if self.ctrl.load_background_image(path):
            self.act_bg_visible.setChecked(True)
            self.act_bg_gray.setChecked(bool(self.ctrl.background_image.get("grayscale", False)))
            self.view.fit_all()

    def clear_background_image(self):
        self.ctrl.clear_background_image()
        self.act_bg_visible.setChecked(True)
        self.act_bg_gray.setChecked(False)

    def set_background_opacity(self):
        current = float(self.ctrl.background_image.get("opacity", 0.6)) * 100.0
        val, ok = QInputDialog.getDouble(
            self,
            "Background Opacity",
            "Opacity (0-100):",
            current,
            0.0,
            100.0,
            0,
        )
        if not ok:
            return
        self.ctrl.set_background_opacity(val / 100.0)

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
        if self.ctrl.selected_spline_id is not None:
            self.ctrl.cmd_delete_spline(self.ctrl.selected_spline_id); return
        if self.ctrl.selected_body_id is not None:
            self.ctrl.cmd_delete_body(self.ctrl.selected_body_id); return

    def file_new(self):
        self.ctrl.commit_drag_if_any()
        if not self.ctrl.load_dict(
            {
                "points": [],
                "links": [],
                "angles": [],
                "splines": [],
                "point_splines": [],
                "bodies": [],
                "parameters": [],
                "version": "2.7.0",
            },
            action="start a new file",
        ):
            return
        self.ctrl.stack.clear()
        self.current_file = None
        if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
            self.sim_panel.animation_tab.refresh_cases()

    def file_open(self):
        self.ctrl.commit_drag_if_any()
        path, _ = QFileDialog.getOpenFileName(self, "Open Sketch", "", "Sketch JSON (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not self.ctrl.load_dict(data, action="open a new file"):
                return
            self.current_file = path
            if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
                self.sim_panel.animation_tab.refresh_cases()
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
        if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
            self.sim_panel.animation_tab.refresh_cases()
