# -*- coding: utf-8 -*-
"""Main window + menus."""

from __future__ import annotations

import json
import os
from pathlib import Path
import traceback
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QSignalBlocker, QCoreApplication, QUrl
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QGraphicsScene, QDockWidget, QStatusBar,
    QFileDialog, QMessageBox, QInputDialog, QStyle, QToolButton, QLabel, QComboBox, QWidget, QHBoxLayout
)

from ..core.controller import SketchController
from .view import SketchView
from .panel import SketchPanel
from .items import PointItem, LinkItem, AngleItem, SplineItem, PointSplineItem
from .sim_panel import SimulationPanel
from .settings_dialog import SettingsDialog
from .grid_settings_dialog import GridSettingsDialog
from .i18n import tr
from ..common_ui.ribbon.action_registry import ActionRegistry
from ..common_ui.ribbon.icon_manager import assign_default_icons
from ..common_ui.ribbon.ribbon_factory import build
from ..common_ui.ribbon.ribbon_spec import build_planar_ribbon_spec


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Planar Sketch v2.9.0")
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
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
        self.setStatusBar(QStatusBar())
        self.statusBar().setVisible(True)
        self.statusBar().show()
        self.statusBar().showMessage(tr(self.ctrl.ui_language, "status.idle"))
        self.current_file: Optional[str] = None
        self.project_dir: Optional[str] = None
        self._build_menus()
        self._build_ribbon()
        self.apply_language()
        self.menuBar().setVisible(True)
        self.file_new(prompt_for_folder=False)
        self.update_undo_redo_actions()
        self.ctrl.update_status()
        self.scene.selectionChanged.connect(self._scene_selection_changed)

    def _scene_selection_changed(self):
        if self.panel.sync_guard: return
        self.panel.sync_guard = True
        try:
            scene = getattr(self, "scene", None)
            if scene is None:
                return
            try:
                items = scene.selectedItems()
            except RuntimeError:
                # The Qt scene can already be destroyed while a queued
                # selectionChanged signal is still being delivered.
                return
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
        self.menu_file_action = mb.addAction("")
        self.menu_file_action.setCheckable(True)
        self.menu_file_action.triggered.connect(lambda: self._set_active_ribbon("file"))
        self.act_file_new = QAction("", self)
        self.act_file_new.triggered.connect(self.file_new)
        self.act_file_open = QAction("", self)
        self.act_file_open.triggered.connect(self.file_open)
        self.act_file_save = QAction("", self)
        self.act_file_save.triggered.connect(self.file_save)
        self.act_file_save_as = QAction("", self)
        self.act_file_save_as.triggered.connect(self.file_save_as)
        self.act_file_exit = QAction("", self)
        self.act_file_exit.triggered.connect(self.close)

        self.menu_edit_action = mb.addAction("")
        self.menu_edit_action.setCheckable(True)
        self.menu_edit_action.triggered.connect(lambda: self._set_active_ribbon("edit"))
        self.act_undo = QAction("", self)
        self.act_undo.setShortcuts([QKeySequence.StandardKey.Undo, QKeySequence("Ctrl+Z")])
        self.act_undo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_undo.triggered.connect(self.ctrl.stack.undo)
        self.shortcut_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.shortcut_undo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_undo.activated.connect(self.ctrl.stack.undo)
        self.act_redo = QAction("", self)
        self.act_redo.setShortcuts([QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Y")])
        self.act_redo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_redo.triggered.connect(self.ctrl.stack.redo)
        self.shortcut_redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.shortcut_redo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_redo.activated.connect(self.ctrl.stack.redo)
        self.act_delete_selected = QAction("", self)
        self.act_delete_selected.setShortcuts([QKeySequence.StandardKey.Delete, QKeySequence("Backspace")])
        self.act_delete_selected.triggered.connect(self.delete_selected)
        self.act_cancel_model = QAction("", self)
        self.act_cancel_model.setShortcut(QKeySequence("Escape"))
        self.act_cancel_model.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_cancel_model.triggered.connect(self.ctrl.cancel_model_action)
        self.act_repeat_model = QAction("", self)
        self.act_repeat_model.setShortcut(QKeySequence("F4"))
        self.act_repeat_model.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.act_repeat_model.triggered.connect(self.ctrl.repeat_last_model_action)
        self.shortcut_repeat_model = QShortcut(QKeySequence("F4"), self)
        self.shortcut_repeat_model.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_repeat_model.activated.connect(self.ctrl.repeat_last_model_action)
        self.act_settings = QAction("", self)
        self.act_settings.triggered.connect(self.open_settings)

        self.menu_sketch_action = mb.addAction("")
        self.menu_sketch_action.setCheckable(True)
        self.menu_sketch_action.triggered.connect(self._activate_sketch_mode)
        self.act_create_point = QAction("", self)
        self.act_create_point.setCheckable(True)
        self.act_create_point.toggled.connect(lambda checked: self._toggle_create_action("point", checked))
        self.act_create_line = QAction("", self)
        self.act_create_line.setCheckable(True)
        self.act_create_line.toggled.connect(lambda checked: self._toggle_create_action("line", checked))
        self.act_create_spline = QAction("", self)
        self.act_create_spline.setCheckable(True)
        self.act_create_spline.toggled.connect(lambda checked: self._toggle_create_action("spline", checked))

        self.menu_boundary_action = mb.addAction("")
        self.menu_boundary_action.setCheckable(True)
        self.menu_boundary_action.triggered.connect(lambda: self._set_active_ribbon("boundary"))

        self.menu_analysis_action = mb.addAction("")
        self.menu_analysis_action.setCheckable(True)
        self.menu_analysis_action.triggered.connect(self._activate_analysis_mode)

        self.menu_view_action = mb.addAction("")
        self.menu_view_action.setCheckable(True)
        self.menu_view_action.triggered.connect(lambda: self._set_active_ribbon("view"))
        self.menu_background_action = mb.addAction("")
        self.menu_background_action.setCheckable(True)
        self.menu_background_action.triggered.connect(lambda: self._set_active_ribbon("background"))
        self.menu_help_action = mb.addAction("")
        self.menu_help_action.setCheckable(True)
        self.menu_help_action.triggered.connect(lambda: self._set_active_ribbon("help"))
        self.act_pm = QAction("", self, checkable=True); self.act_pm.setChecked(True)
        self.act_pm.triggered.connect(lambda c: self._toggle_pm(c))
        self.act_dm = QAction("", self, checkable=True); self.act_dm.setChecked(True)
        self.act_dm.triggered.connect(lambda c: self._toggle_dm(c))
        self.act_body_color = QAction("", self, checkable=True); self.act_body_color.setChecked(True)
        self.act_body_color.triggered.connect(lambda c: self._toggle_body_coloring(c))
        self.act_splines = QAction("", self, checkable=True); self.act_splines.setChecked(True)
        self.act_splines.triggered.connect(lambda c: self._toggle_splines(c))
        self.act_load_arrows = QAction("", self, checkable=True); self.act_load_arrows.setChecked(True)
        self.act_load_arrows.triggered.connect(lambda c: self._toggle_load_arrows(c))
        self.act_bg_load = QAction("", self)
        self.act_bg_load.triggered.connect(self.load_background_image)
        self.act_bg_visible = QAction("", self, checkable=True); self.act_bg_visible.setChecked(True)
        self.act_bg_visible.triggered.connect(lambda c: self._toggle_background_visible(c))
        self.act_bg_gray = QAction("", self, checkable=True)
        self.act_bg_gray.triggered.connect(lambda c: self._toggle_background_grayscale(c))
        self.act_bg_opacity = QAction("", self)
        self.act_bg_opacity.triggered.connect(self.set_background_opacity)
        self.act_bg_clear = QAction("", self)
        self.act_bg_clear.triggered.connect(self.clear_background_image)
        self.act_grid_horizontal = QAction("", self, checkable=True)
        self.act_grid_horizontal.setChecked(bool(self.ctrl.grid_settings.get("show_horizontal", False)))
        self.act_grid_horizontal.triggered.connect(lambda c: self._toggle_grid_horizontal(c))
        self.act_grid_vertical = QAction("", self, checkable=True)
        self.act_grid_vertical.setChecked(bool(self.ctrl.grid_settings.get("show_vertical", False)))
        self.act_grid_vertical.triggered.connect(lambda c: self._toggle_grid_vertical(c))
        self.act_grid_settings = QAction("", self)
        self.act_grid_settings.triggered.connect(self.open_grid_settings)
        self.act_preset_show_all = QAction("", self)
        self.act_preset_show_all.triggered.connect(self.preset_show_all)
        self.act_preset_points_only = QAction("", self)
        self.act_preset_points_only.triggered.connect(self.preset_points_only)
        self.act_preset_links_only = QAction("", self)
        self.act_preset_links_only.triggered.connect(self.preset_links_only)
        self.act_reset_view = QAction("", self)
        self.act_reset_view.triggered.connect(self.view.reset_view)
        self.act_fit_all = QAction("", self)
        self.act_fit_all.triggered.connect(self.view.fit_all)

        self.act_analysis_play = QAction("", self)
        self.act_analysis_play.triggered.connect(self.sim_panel.play)
        self.act_analysis_stop = QAction("", self)
        self.act_analysis_stop.triggered.connect(self.sim_panel.stop)
        self.act_analysis_reset_pose = QAction("", self)
        self.act_analysis_reset_pose.triggered.connect(self.sim_panel.reset_pose)
        self.act_analysis_check = QAction("", self)
        self.act_analysis_check.triggered.connect(self.sim_panel._run_analysis_check)
        self.act_analysis_export = QAction("", self)
        self.act_analysis_export.triggered.connect(self.sim_panel.export_csv)
        self.act_analysis_save_run = QAction("", self)
        self.act_analysis_save_run.triggered.connect(self.sim_panel.save_last_run)

        self.act_boundary_constraints = QAction("", self)
        self.act_boundary_constraints.triggered.connect(self.show_constraints_tab)
        self.act_boundary_loads = QAction("", self)
        self.act_boundary_loads.triggered.connect(self.show_loads_tab)
        self.act_boundary_add_force = QAction("", self)
        self.act_boundary_add_force.triggered.connect(self.sim_panel._add_force_from_selection)
        self.act_boundary_add_torque = QAction("", self)
        self.act_boundary_add_torque.triggered.connect(self.sim_panel._add_torque_from_selection)
        self.act_boundary_clear_loads = QAction("", self)
        self.act_boundary_clear_loads.triggered.connect(self.sim_panel._clear_loads)
        self.act_boundary_fix = QAction("", self)
        self.act_boundary_fix.triggered.connect(self.fix_selected_points)

        self.act_help_manual = QAction("", self)
        self.act_help_manual.triggered.connect(self.open_help_manual)
        self.act_help_about = QAction("", self)
        self.act_help_about.triggered.connect(self.show_about_dialog)

    def _build_ribbon(self) -> None:
        self._build_analysis_solver_widget()
        self._apply_action_icons()
        lang = getattr(self.ctrl, "ui_language", "en")
        spec = build_planar_ribbon_spec(lambda key, default: tr(lang, key, default))
        registry = self._build_action_registry()
        self.ribbon_result = build(self, spec, registry)
        self.setMenuBar(self.ribbon_result.ribbon)
        self._set_active_ribbon("home")
        self._install_sketch_double_clicks()

    def _rebuild_ribbon(self) -> None:
        active_key = getattr(self, "_active_ribbon", "home")
        visible = getattr(self, "_toolbars_enabled", True)
        self._build_ribbon()
        self._set_toolbars_visible(visible)
        self._set_active_ribbon(active_key)

    def _build_action_registry(self) -> ActionRegistry:
        return ActionRegistry(
            actions={
                name: getattr(self, name)
                for name in (
                    "act_file_new", "act_file_open", "act_file_save", "act_file_save_as",
                    "act_undo", "act_redo", "act_delete_selected", "act_repeat_model", "act_cancel_model", "act_settings",
                    "act_create_point", "act_create_line", "act_create_spline",
                    "act_boundary_constraints", "act_boundary_loads", "act_boundary_add_force", "act_boundary_add_torque",
                    "act_boundary_clear_loads", "act_boundary_fix",
                    "act_analysis_play", "act_analysis_stop", "act_analysis_reset_pose", "act_analysis_check",
                    "act_analysis_export", "act_analysis_save_run",
                    "act_pm", "act_dm", "act_body_color", "act_splines", "act_load_arrows",
                    "act_preset_show_all", "act_preset_points_only", "act_preset_links_only", "act_reset_view", "act_fit_all",
                    "act_grid_horizontal", "act_grid_vertical", "act_grid_settings",
                    "act_bg_load", "act_bg_visible", "act_bg_gray", "act_bg_opacity", "act_bg_clear",
                    "act_help_manual", "act_help_about",
                )
            },
            widgets={
                "analysis_solver_widget": lambda: self.analysis_solver_widget,
            },
        )

    def _install_sketch_double_clicks(self) -> None:
        self._double_click_action_widgets = {}
        for action_key, handler in (
            ("act_create_point", lambda: self.ctrl.begin_create_point(continuous=True)),
            ("act_create_line", lambda: self.ctrl.begin_create_line(continuous=True)),
            ("act_create_spline", lambda: self.ctrl.begin_create_spline(continuous=True)),
        ):
            widgets = self.ribbon_result.action_buttons.get(action_key, [])
            for widget in widgets:
                widget.installEventFilter(self)
                self._double_click_action_widgets[widget] = handler

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonDblClick:
            handler = getattr(self, "_double_click_action_widgets", {}).get(obj)
            if handler is not None:
                handler()
                return True
        return super().eventFilter(obj, event)

    def _set_toolbars_visible(self, visible: bool) -> None:
        self._toolbars_enabled = visible
        if hasattr(self, "ribbon_result"):
            self.ribbon_result.ribbon.setVisible(visible)

    def _set_active_ribbon(self, key: str) -> None:
        if not getattr(self, "_toolbars_enabled", True):
            return
        if getattr(self.ctrl, "mode", "Idle") in ("CreatePoint", "CreateLine", "CreateSpline"):
            self.ctrl.cancel_model_action()
        self._active_ribbon = key
        categories = {
            "home": "home",
            "file": "home",
            "edit": "home",
            "model": "model",
            "sketch": "model",
            "boundary": "boundary",
            "analysis": "analysis",
            "view": "view",
            "background": "background",
            "help": "help",
        }
        category = self.ribbon_result.categories.get(categories.get(key, "home"))
        if category is not None and hasattr(self.ribbon_result.ribbon, "setCurrentCategory"):
            self.ribbon_result.ribbon.setCurrentCategory(category)

    def _activate_sketch_mode(self) -> None:
        self._set_active_ribbon("sketch")
        self._set_dock_visibility(active="sketch")

    def _activate_analysis_mode(self) -> None:
        self._set_active_ribbon("analysis")
        self._set_dock_visibility(active="analysis")

    def _set_dock_visibility(self, active: str) -> None:
        show_sketch = active == "sketch"
        show_analysis = active == "analysis"
        self.dock.setVisible(show_sketch)
        self.sim_dock.setVisible(show_analysis)
        if show_sketch:
            self._raise_dock(self.dock)
        if show_analysis:
            self._raise_dock(self.sim_dock)

    def _raise_dock(self, dock: QDockWidget) -> None:
        dock.show()
        dock.raise_()

    def _apply_action_icons(self) -> None:
        style = self.style()
        assign_default_icons(self._build_action_registry().actions, style, {
            "act_file_new": QStyle.StandardPixmap.SP_FileIcon,
            "act_file_open": QStyle.StandardPixmap.SP_DirOpenIcon,
            "act_file_save": QStyle.StandardPixmap.SP_DialogSaveButton,
            "act_file_save_as": QStyle.StandardPixmap.SP_DialogSaveButton,
            "act_file_exit": QStyle.StandardPixmap.SP_DialogCloseButton,
            "act_undo": QStyle.StandardPixmap.SP_ArrowBack,
            "act_redo": QStyle.StandardPixmap.SP_ArrowForward,
            "act_delete_selected": QStyle.StandardPixmap.SP_TrashIcon,
            "act_repeat_model": QStyle.StandardPixmap.SP_BrowserReload,
            "act_cancel_model": QStyle.StandardPixmap.SP_DialogCancelButton,
            "act_settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "act_create_point": QStyle.StandardPixmap.SP_DialogYesButton,
            "act_create_line": QStyle.StandardPixmap.SP_LineEditClearButton,
            "act_create_spline": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "act_pm": QStyle.StandardPixmap.SP_DialogYesButton,
            "act_dm": QStyle.StandardPixmap.SP_DialogApplyButton,
            "act_body_color": QStyle.StandardPixmap.SP_DriveDVDIcon,
            "act_splines": QStyle.StandardPixmap.SP_FileDialogInfoView,
            "act_load_arrows": QStyle.StandardPixmap.SP_ArrowUp,
            "act_bg_load": QStyle.StandardPixmap.SP_DialogOpenButton,
            "act_bg_visible": QStyle.StandardPixmap.SP_DialogYesButton,
            "act_bg_gray": QStyle.StandardPixmap.SP_DialogResetButton,
            "act_bg_opacity": QStyle.StandardPixmap.SP_DialogApplyButton,
            "act_bg_clear": QStyle.StandardPixmap.SP_LineEditClearButton,
            "act_grid_horizontal": QStyle.StandardPixmap.SP_ArrowRight,
            "act_grid_vertical": QStyle.StandardPixmap.SP_ArrowUp,
            "act_grid_settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "act_preset_show_all": QStyle.StandardPixmap.SP_DialogYesButton,
            "act_preset_points_only": QStyle.StandardPixmap.SP_DialogNoButton,
            "act_preset_links_only": QStyle.StandardPixmap.SP_DialogNoButton,
            "act_reset_view": QStyle.StandardPixmap.SP_BrowserStop,
            "act_fit_all": QStyle.StandardPixmap.SP_ArrowUp,
            "act_analysis_play": QStyle.StandardPixmap.SP_MediaPlay,
            "act_analysis_stop": QStyle.StandardPixmap.SP_MediaStop,
            "act_analysis_reset_pose": QStyle.StandardPixmap.SP_BrowserReload,
            "act_analysis_check": QStyle.StandardPixmap.SP_DialogApplyButton,
            "act_analysis_export": QStyle.StandardPixmap.SP_DialogSaveButton,
            "act_analysis_save_run": QStyle.StandardPixmap.SP_DialogSaveButton,
            "act_boundary_constraints": QStyle.StandardPixmap.SP_DialogApplyButton,
            "act_boundary_loads": QStyle.StandardPixmap.SP_ArrowUp,
            "act_boundary_add_force": QStyle.StandardPixmap.SP_ArrowUp,
            "act_boundary_add_torque": QStyle.StandardPixmap.SP_BrowserReload,
            "act_boundary_clear_loads": QStyle.StandardPixmap.SP_TrashIcon,
            "act_boundary_fix": QStyle.StandardPixmap.SP_DialogApplyButton,
            "act_help_manual": QStyle.StandardPixmap.SP_DialogHelpButton,
            "act_help_about": QStyle.StandardPixmap.SP_MessageBoxInformation,
        })

    def _build_analysis_solver_widget(self) -> None:
        self.analysis_solver_widget = QWidget(self)
        layout = QHBoxLayout(self.analysis_solver_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.lbl_analysis_solver = QLabel(self.analysis_solver_widget)
        self.combo_analysis_solver = QComboBox(self.analysis_solver_widget)
        layout.addWidget(self.lbl_analysis_solver)
        layout.addWidget(self.combo_analysis_solver)
        self.combo_analysis_solver.currentIndexChanged.connect(self._on_analysis_solver_combo_changed)
        if hasattr(self.sim_panel, "combo_solver"):
            self.sim_panel.combo_solver.currentIndexChanged.connect(self._sync_analysis_solver_combo_from_panel)
        self._refresh_analysis_solver_options()

    def _refresh_analysis_solver_options(self) -> None:
        if not hasattr(self, "combo_analysis_solver"):
            return
        current = self.sim_panel.get_solver_name() if hasattr(self.sim_panel, "get_solver_name") else "pbd"
        self.combo_analysis_solver.blockSignals(True)
        self.combo_analysis_solver.clear()
        if hasattr(self.sim_panel, "_solver_options"):
            for key, label in self.sim_panel._solver_options():
                self.combo_analysis_solver.addItem(label, key)
        if self.combo_analysis_solver.count() == 0:
            self.combo_analysis_solver.addItem("PBD", "pbd")
        index = self.combo_analysis_solver.findData(current)
        if index < 0:
            index = self.combo_analysis_solver.findData("pbd")
        if index >= 0:
            self.combo_analysis_solver.setCurrentIndex(index)
        self.combo_analysis_solver.blockSignals(False)
        if hasattr(self, "lbl_analysis_solver"):
            lang = getattr(self.ctrl, "ui_language", "en")
            self.lbl_analysis_solver.setText(tr(lang, "sim.solver"))

    def _on_analysis_solver_combo_changed(self) -> None:
        if not hasattr(self, "combo_analysis_solver") or not hasattr(self.sim_panel, "set_solver_name"):
            return
        name = self.combo_analysis_solver.currentData()
        if hasattr(self.sim_panel, "combo_solver"):
            self.sim_panel.combo_solver.blockSignals(True)
        self.sim_panel.set_solver_name(str(name))
        if hasattr(self.sim_panel, "combo_solver"):
            self.sim_panel.combo_solver.blockSignals(False)
        if hasattr(self.sim_panel, "_sync_simulation_settings_from_fields"):
            self.sim_panel._sync_simulation_settings_from_fields()

    def _sync_analysis_solver_combo_from_panel(self) -> None:
        if not hasattr(self, "combo_analysis_solver") or not hasattr(self.sim_panel, "get_solver_name"):
            return
        name = self.sim_panel.get_solver_name()
        self.combo_analysis_solver.blockSignals(True)
        index = self.combo_analysis_solver.findData(name)
        if index < 0:
            index = self.combo_analysis_solver.findData("pbd")
        if index >= 0:
            self.combo_analysis_solver.setCurrentIndex(index)
        self.combo_analysis_solver.blockSignals(False)

    def update_model_action_state(self) -> None:
        continuous_mode = getattr(self.ctrl, "_continuous_model_action", None)
        with QSignalBlocker(self.act_create_point):
            self.act_create_point.setChecked(continuous_mode == "CreatePoint")
        with QSignalBlocker(self.act_create_line):
            self.act_create_line.setChecked(continuous_mode == "CreateLine")
        with QSignalBlocker(self.act_create_spline):
            self.act_create_spline.setChecked(continuous_mode == "CreateSpline")

    def apply_language(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        self.act_file_new.setText(tr(lang, "action.new"))
        self.act_file_open.setText(tr(lang, "action.open"))
        self.act_file_save.setText(tr(lang, "action.save"))
        self.act_file_save_as.setText(tr(lang, "action.save_as"))
        self.act_file_exit.setText(tr(lang, "action.exit"))
        self.act_undo.setText(tr(lang, "action.undo"))
        self.act_redo.setText(tr(lang, "action.redo"))
        self.act_delete_selected.setText(tr(lang, "action.delete_selected"))
        self.act_cancel_model.setText(tr(lang, "action.cancel", "Cancel"))
        self.act_repeat_model.setText(tr(lang, "action.repeat_last_model_action"))
        self.act_settings.setText(tr(lang, "action.settings"))
        self.act_create_point.setText(tr(lang, "action.create_point"))
        self.act_create_line.setText(tr(lang, "action.create_line"))
        self.act_create_spline.setText(tr(lang, "action.create_spline"))
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
        self.act_grid_horizontal.setText(tr(lang, "action.show_horizontal_grid"))
        self.act_grid_vertical.setText(tr(lang, "action.show_vertical_grid"))
        self.act_grid_settings.setText(tr(lang, "action.grid_settings"))
        self.act_preset_show_all.setText(tr(lang, "action.preset_show_all"))
        self.act_preset_points_only.setText(tr(lang, "action.preset_points_only"))
        self.act_preset_links_only.setText(tr(lang, "action.preset_links_only"))
        self.act_reset_view.setText(tr(lang, "action.reset_view"))
        self.act_fit_all.setText(tr(lang, "action.fit_all"))
        self.act_analysis_play.setText(tr(lang, "sim.play"))
        self.act_analysis_stop.setText(tr(lang, "sim.stop"))
        self.act_analysis_reset_pose.setText(tr(lang, "sim.reset_pose"))
        self.act_analysis_check.setText(tr(lang, "analysis.check"))
        self.act_analysis_export.setText(tr(lang, "sim.export_csv"))
        self.act_analysis_save_run.setText(tr(lang, "sim.save_run"))
        self.act_boundary_constraints.setText(tr(lang, "action.boundary_constraints"))
        self.act_boundary_loads.setText(tr(lang, "action.boundary_loads"))
        self.act_boundary_add_force.setText(tr(lang, "action.boundary_add_force"))
        self.act_boundary_add_torque.setText(tr(lang, "action.boundary_add_torque"))
        self.act_boundary_clear_loads.setText(tr(lang, "action.boundary_clear_loads"))
        self.act_boundary_fix.setText(tr(lang, "action.boundary_fix"))
        self.act_help_manual.setText(tr(lang, "action.help_manual"))
        self.act_help_about.setText(tr(lang, "action.help_about"))
        self.dock.setWindowTitle(tr(lang, "dock.sketch"))
        self.sim_dock.setWindowTitle(tr(lang, "dock.analysis"))
        self.panel.apply_language()
        self.sim_panel.apply_language()
        self._refresh_analysis_solver_options()
        self._rebuild_ribbon()

    def _toggle_create_action(self, kind: str, checked: bool) -> None:
        if checked:
            if kind == "point":
                self.ctrl.begin_create_point()
            elif kind == "line":
                self.ctrl.begin_create_line()
            elif kind == "spline":
                self.ctrl.begin_create_spline()
        else:
            if getattr(self.ctrl, "mode", "Idle") in ("CreatePoint", "CreateLine", "CreateSpline"):
                self.ctrl.cancel_model_action()

    def show_constraints_tab(self) -> None:
        self._set_active_ribbon("boundary")
        self._set_dock_visibility(active="sketch")
        self.panel.tabs.setCurrentWidget(self.panel.constraints_tab)

    def show_loads_tab(self) -> None:
        self._set_active_ribbon("boundary")
        self._set_dock_visibility(active="analysis")
        self.sim_panel.tabs.setCurrentIndex(0)

    def create_point_at_view_center(self) -> None:
        self.ctrl.commit_drag_if_any()
        view_center = self.view.mapToScene(self.view.viewport().rect().center())
        self.ctrl.cmd_add_point(view_center.x(), view_center.y())

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

    def open_help_manual(self) -> None:
        from PyQt6.QtGui import QDesktopServices
        app_dir = Path(QCoreApplication.applicationDirPath())
        candidates = [
            app_dir / "help.pdf",
            Path.cwd() / "help.pdf",
            Path(__file__).resolve().parents[2] / "help.pdf",
        ]
        help_path = next((path for path in candidates if path.exists()), None)
        if help_path is None:
            QMessageBox.information(self, tr(self.ctrl.ui_language, "menu.help"), tr(self.ctrl.ui_language, "help.missing"))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_path)))

    def show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            tr(self.ctrl.ui_language, "action.help_about"),
            tr(self.ctrl.ui_language, "help.copyright"),
        )

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
    def _toggle_grid_horizontal(self, checked: bool):
        try:
            self.ctrl.set_grid_visibility(show_horizontal=bool(checked))
        except Exception:
            self.report_runtime_error("Grid Error", traceback.format_exc())
    def _toggle_grid_vertical(self, checked: bool):
        try:
            self.ctrl.set_grid_visibility(show_vertical=bool(checked))
        except Exception:
            self.report_runtime_error("Grid Error", traceback.format_exc())

    def open_grid_settings(self):
        dlg = GridSettingsDialog(self.ctrl, self)
        if dlg.exec():
            settings = dlg.settings()
            self.ctrl.set_grid_settings(**settings)

    def report_runtime_error(self, title: str, detail: str) -> None:
        QMessageBox.critical(self, title, detail)

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
            self.ctrl.cmd_delete_points(sorted(self.ctrl.selected_point_ids))
            return
        if self.ctrl.selected_link_id is not None:
            self.ctrl.cmd_delete_link(self.ctrl.selected_link_id); return
        if self.ctrl.selected_angle_id is not None:
            self.ctrl.cmd_delete_angle(self.ctrl.selected_angle_id); return
        if self.ctrl.selected_spline_id is not None:
            self.ctrl.cmd_delete_spline(self.ctrl.selected_spline_id); return
        if self.ctrl.selected_body_id is not None:
            self.ctrl.cmd_delete_body(self.ctrl.selected_body_id); return

    def confirm_unsaved_run(self) -> bool:
        sim_panel = getattr(self, "sim_panel", None)
        if not sim_panel or not sim_panel.has_unsaved_run():
            return True
        lang = getattr(self.ctrl, "ui_language", "en")
        reply = QMessageBox.question(
            self,
            tr(lang, "prompt.unsaved_run_title"),
            tr(lang, "prompt.unsaved_run_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _confirm_save_allowed(self) -> bool:
        sim_panel = getattr(self, "sim_panel", None)
        if sim_panel and sim_panel.is_running():
            lang = getattr(self.ctrl, "ui_language", "en")
            QMessageBox.information(
                self,
                tr(lang, "prompt.save_blocked_title"),
                tr(lang, "prompt.save_blocked_body"),
            )
            return False
        return True

    def _report_schema_issues(self, warnings: list[str], errors: list[str], context: str) -> bool:
        lang = getattr(self.ctrl, "ui_language", "en")
        if errors:
            detail = "\n".join(f"- {item}" for item in errors)
            QMessageBox.critical(
                self,
                tr(lang, "schema.errors_title").format(context=context),
                tr(lang, "schema.errors_body").format(context=context, details=detail),
            )
            return False
        if warnings:
            detail = "\n".join(f"- {item}" for item in warnings)
            QMessageBox.warning(
                self,
                tr(lang, "schema.warnings_title").format(context=context),
                tr(lang, "schema.warnings_body").format(context=context, details=detail),
            )
        return True

    def fix_selected_points(self) -> None:
        self.ctrl.commit_drag_if_any()
        pids = sorted(list(self.ctrl.selected_point_ids))
        if not pids and self.ctrl.selected_point_id is not None:
            pids = [self.ctrl.selected_point_id]
        if not pids:
            lang = getattr(self.ctrl, "ui_language", "en")
            QMessageBox.information(
                self,
                tr(lang, "prompt.fix_title"),
                tr(lang, "prompt.select_point_body"),
            )
            return
        for pid in pids:
            self.ctrl.cmd_set_point_fixed(pid, True)
        self.ctrl.update_graphics()

    def file_new(self, prompt_for_folder: bool = True):
        self.ctrl.commit_drag_if_any()
        if not self.confirm_unsaved_run():
            return
        if not self.ctrl.load_dict(
            self.ctrl.default_project_dict(force_new_uuid=True),
            action="start a new file",
        ):
            return
        self._sync_background_actions()
        self.ctrl.stack.clear()
        self.current_file = None
        self.project_dir = None
        if hasattr(self, "sim_panel"):
            self.sim_panel.reset_analysis_state()
        if prompt_for_folder:
            project_file = self._prompt_project_file("New Project")
            if project_file:
                self._set_project_paths(project_file)
        if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
            self.sim_panel.animation_tab.refresh_cases()

    def file_open(self):
        self.ctrl.commit_drag_if_any()
        if not self.confirm_unsaved_run():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Sketch", "", "Sketch JSON (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            warnings, errors = self.ctrl.validate_project_schema(raw)
            if not self._report_schema_issues(warnings, errors, "open"):
                return
            data = self.ctrl.merge_project_dict(raw)
            if not self.ctrl.load_dict(data, action="open a new file"):
                return
            self._sync_background_actions()
            self._set_project_paths(path)
            if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
                self.sim_panel.animation_tab.refresh_cases()
            self.view.fit_all()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def file_save(self):
        self.ctrl.commit_drag_if_any()
        if not self._confirm_save_allowed():
            return
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
        if not self._confirm_save_allowed():
            return
        project_file = self._prompt_project_file("Save Sketch As")
        if not project_file:
            return
        self._set_project_paths(project_file)
        self.file_save()
        if hasattr(self, "sim_panel") and hasattr(self.sim_panel, "animation_tab"):
            self.sim_panel.animation_tab.refresh_cases()

    def _prompt_project_file(self, title: str) -> Optional[str]:
        path, _ = QFileDialog.getSaveFileName(self, title, "", "Sketch JSON (*.json)")
        if not path:
            return None
        base_name = os.path.splitext(os.path.basename(path))[0] or "project"
        parent_dir = os.path.dirname(path) or os.getcwd()
        return os.path.join(parent_dir, f"{base_name}.json")

    def _derive_project_dir(self, project_file: str) -> str:
        base_name = os.path.splitext(os.path.basename(project_file))[0] or "project"
        parent_dir = os.path.dirname(project_file) or os.getcwd()
        if os.path.basename(parent_dir) == base_name:
            return parent_dir
        return os.path.join(parent_dir, base_name)

    def _set_project_paths(self, project_file: str) -> None:
        self.current_file = project_file
        self.project_dir = self._derive_project_dir(project_file)

    def _sync_background_actions(self) -> None:
        self.act_bg_visible.setChecked(bool(self.ctrl.background_image.get("visible", True)))
        self.act_bg_gray.setChecked(bool(self.ctrl.background_image.get("grayscale", False)))
        self.act_grid_horizontal.setChecked(bool(self.ctrl.grid_settings.get("show_horizontal", False)))
        self.act_grid_vertical.setChecked(bool(self.ctrl.grid_settings.get("show_vertical", False)))
        if self.project_dir:
            os.makedirs(self.project_dir, exist_ok=True)
