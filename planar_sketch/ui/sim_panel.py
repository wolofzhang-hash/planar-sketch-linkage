# -*- coding: utf-8 -*-
"""Simulation dock: driver/measurements, sweep, plot and export.

New in v2.6.6:
- Global Parameters tab + expression fields for Point X/Y, Length L, and Angle deg.

Previously (v2.4.19):
- Restored point right-click menus for Driver / Measurement (also available in v2.4.19).
- Reset pose to the sweep start pose
- Export full sweep CSV (time/input + all measurements)
"""

from __future__ import annotations

import csv
import math
import os
import tempfile
import time
import importlib.util
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QDialog, QComboBox, QSizePolicy, QMenu
)

from .analysis_tabs import AnimationTab
from .analysis.curves_tab import CurvesTab
from .analysis.optimization_tab import OptimizationTab
from .synthesis_tab import SynthesisTab
from .expression_builder import ExpressionBuilderDialog
from ..core.expression_registry import PARAMETER_FUNCTIONS
from .i18n import tr, get_ui_language
from .panel_common_i18n import panel_lang as _lang, panel_tr as _tr, panel_is_zh as _is_zh, panel_is_en as _is_en
from .table_context_menu import exec_table_context_menu
from .sim_panel_tables_mixin import SimulationPanelTablesMixin
from ..core.expression_service import eval_signal_expression
from ..core.headless_sim import simulate_case
from ..core.project_paths import ProjectPathService
from ..core.run_service import RunService

if TYPE_CHECKING:
    from ..core.controller import SketchController



class SimulationPanel(SimulationPanelTablesMixin, QWidget):
    def _report_persistence_error(self, title: str, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        win = getattr(self.ctrl, "win", None)
        try:
            if win is not None:
                win.statusBar().showMessage(f"{title}: {message}", 8000)
        except Exception:
            pass
        QMessageBox.critical(self, title, message)

    def __init__(self, ctrl: "SketchController"):
        super().__init__()
        self.ctrl = ctrl
        self._project_paths = ProjectPathService(ctrl)
        self._run_service = RunService(ctrl, self._project_paths)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._theta_deg = 0.0
        self._theta_end = 0.0
        self._theta_step = 1.0
        self._theta_step_cur = 1.0
        self._theta_step_min = 1e-4
        self._theta_step_max = 1.0
        self._theta_last_ok = 0.0
        self._frame = 0
        self._driver_sweep: Optional[List[Dict[str, float]]] = None
        self._driver_last_ok: List[float] = []
        self._driver_step_scale: float = 1.0
        self._driver_step_scale_max: float = 1.0
        self._sweep_steps_total: Optional[int] = None
        self._sweep_step_index: int = 0
        self._theta_start = 0.0

        self._records: List[Dict[str, Any]] = []
        self._pending_sim_start_capture = False
        self._run_context: Optional[Dict[str, Any]] = None
        self._run_start_snapshot: Optional[Dict[str, Any]] = None
        self._last_run_data: Optional[Dict[str, Any]] = None
        # The last case that has a persisted "current" run (enables "Save run").
        self._last_saved_case_id: Optional[str] = None
        self._last_used_solver: Optional[str] = None
        self._last_solver_fallback_from: Optional[str] = None
        self._last_solver_error: Optional[str] = None
        self._solver_error_log: List[str] = []

        # Isolated directory for blank/unsaved projects so we never touch cwd.
        # This directory is only used for listing/loading cases/runs and is
        # created lazily if needed.
        self._session_project_dir: Optional[str] = None

        # Performance knobs
        # - pose_points snapshots are expensive; record only when needed (e.g. Animation/Save Run).
        self._record_pose_points: bool = True
        # Throttle UI refresh during sweep to avoid event-queue backlog.
        self._ui_refresh_stride: int = 3
        self._ui_refresh_counter: int = 0

        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        # Driver
        row = QHBoxLayout()
        self.lbl_driver = QLabel()
        self.btn_clear_driver = QPushButton()
        row.addWidget(self.lbl_driver, 1)
        row.addWidget(self.btn_clear_driver)
        main_layout.addLayout(row)

        self.lbl_driver_sweep = QLabel()
        self.lbl_driver_sweep.setVisible(False)
        main_layout.addWidget(self.lbl_driver_sweep)

        self.table_drivers = QTableWidget(0, 4)
        self.table_drivers.setHorizontalHeaderLabels([])
        self.table_drivers.verticalHeader().setVisible(False)
        self.table_drivers.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.table_drivers.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_drivers.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_drivers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table_drivers)

        # Output
        out_row = QHBoxLayout()
        self.lbl_output = QLabel()
        self.btn_clear_output = QPushButton()
        out_row.addWidget(self.lbl_output, 1)
        out_row.addWidget(self.btn_clear_output)
        main_layout.addLayout(out_row)
        self.table_outputs = QTableWidget(0, 2)
        self.table_outputs.setHorizontalHeaderLabels([])
        self.table_outputs.verticalHeader().setVisible(False)
        self.table_outputs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_outputs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_outputs.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_outputs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table_outputs)

        # Sweep controls
        self.ed_step = QLineEdit("200")
        self.lbl_step = QLabel()

        # Solver backend
        solver_row = QHBoxLayout()
        self.lbl_solver = QLabel()
        self.combo_solver = QComboBox()
        self._init_solver_options()
        self.lbl_solver_used = QLabel()
        self.ed_nfev = QLineEdit("250")
        self.ed_nfev.setMaximumWidth(80)
        solver_row.addWidget(self.lbl_solver)
        solver_row.addWidget(self.combo_solver)
        solver_row.addWidget(self.lbl_solver_used)
        solver_row.addWidget(self.lbl_step)
        solver_row.addWidget(self.ed_step)
        self.lbl_max_nfev = QLabel()
        solver_row.addWidget(self.lbl_max_nfev)
        solver_row.addWidget(self.ed_nfev)
        self.chk_reset_before_run = QCheckBox()
        self.chk_reset_before_run.setChecked(True)
        solver_row.addWidget(self.chk_reset_before_run)
        self.input_fields = [self.ed_step, self.ed_nfev]
        solver_row.addStretch(1)
        main_layout.addLayout(solver_row)

        # Buttons
        btns = QHBoxLayout()
        self.btn_play = QPushButton()
        self.btn_stop = QPushButton()
        self.btn_reset_pose = QPushButton()
        self.btn_export = QPushButton()
        self.btn_check_analysis = QPushButton()
        self.btn_save_run = QPushButton()
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_reset_pose)
        btns.addWidget(self.btn_export)
        btns.addWidget(self.btn_check_analysis)
        btns.addWidget(self.btn_save_run)
        main_layout.addLayout(btns)

        main_layout.addStretch(1)

        measurements_tab = QWidget()
        measurements_layout = QVBoxLayout(measurements_tab)
        self.table_meas = QTableWidget(0, 3)
        self.table_meas.setHorizontalHeaderLabels([])
        self.table_meas.verticalHeader().setVisible(False)
        self.table_meas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_meas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_meas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_meas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        measurements_layout.addWidget(self.table_meas)
        self._measure_row_map: List[Dict[str, Any]] = []

        measurements_layout.addStretch(1)
        loads_tab = QWidget()
        loads_layout = QVBoxLayout(loads_tab)

        self.table_loads = QTableWidget(0, 8)
        self.table_loads.setHorizontalHeaderLabels([])
        self.table_loads.verticalHeader().setVisible(False)
        self.table_loads.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked
        )
        self.table_loads.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_loads.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.lbl_applied_loads = QLabel()
        loads_layout.addWidget(self.lbl_applied_loads)
        loads_layout.addWidget(self.table_loads)

        # Quasi-static summary (torques)
        qs_info = QHBoxLayout()
        self.lbl_qs_mode = QLabel()
        self.lbl_tau_in = QLabel()
        self.lbl_tau_out = QLabel()
        qs_info.addWidget(self.lbl_qs_mode)
        qs_info.addWidget(self.lbl_tau_in)
        qs_info.addWidget(self.lbl_tau_out)
        loads_layout.addLayout(qs_info)

        # Quasi-static joint loads (passive constraints only; actuator/closure torque reported separately)
        self.table_joint_loads = QTableWidget(0, 4)
        self.table_joint_loads.setHorizontalHeaderLabels([])
        self.table_joint_loads.verticalHeader().setVisible(False)
        self.table_joint_loads.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_joint_loads.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_joint_loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.lbl_joint_loads = QLabel()
        loads_layout.addWidget(self.lbl_joint_loads)
        loads_layout.addWidget(self.table_joint_loads)

        loads_layout.addStretch(1)

        friction_tab = QWidget()
        friction_layout = QVBoxLayout(friction_tab)
        self.lbl_friction = QLabel()
        friction_layout.addWidget(self.lbl_friction)
        self.table_friction = QTableWidget(0, 5)
        self.table_friction.setHorizontalHeaderLabels([])
        self.table_friction.verticalHeader().setVisible(False)
        self.table_friction.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked
        )
        self.table_friction.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_friction.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_friction.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        friction_layout.addWidget(self.table_friction)
        friction_layout.addStretch(1)
        friction_layout.addStretch(1)

        # ---- analysis tabs order ----
        # Keep most tabs in-place, but:
        # - Curves goes right after Measurements
        # - Synthesis goes right before Optimization
        self.simulation_tab = main_tab
        self.curves_tab = CurvesTab(self.ctrl)
        self.animation_tab = AnimationTab(self.ctrl, run_service=self._run_service, run_case_callback=self.run_case, on_active_case_changed=self._on_active_case_changed)
        self.synthesis_tab = SynthesisTab(self.ctrl, run_service=self._run_service)
        self.optimization_tab = OptimizationTab(self.ctrl, run_service=self._run_service)

        self.tabs.addTab(loads_tab, "")             # 0
        self.tabs.addTab(friction_tab, "")          # 1
        self.tabs.addTab(measurements_tab, "")      # 2
        self.tabs.addTab(self.curves_tab, "")       # 3
        self.tabs.addTab(self.simulation_tab, "")   # 4
        self.tabs.addTab(self.animation_tab, "")    # 5
        self.tabs.addTab(self.synthesis_tab, "")    # 6
        self.tabs.addTab(self.optimization_tab, "") # 7
        self.tabs.currentChanged.connect(self._on_tabs_changed)
        self.input_fields.extend(getattr(self.optimization_tab, "input_fields", []))

        # Signals
        self.btn_clear_driver.clicked.connect(self._clear_driver)
        self.btn_clear_output.clicked.connect(self._clear_output)
        self.btn_check_analysis.clicked.connect(self._run_analysis_check)
        self.btn_play.clicked.connect(self.play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_reset_pose.clicked.connect(self.reset_pose)
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_save_run.clicked.connect(self.save_last_run)

        self.table_drivers.cellChanged.connect(self._on_driver_table_changed)
        self.table_loads.cellChanged.connect(self._on_load_table_changed)
        self.table_friction.cellChanged.connect(self._on_friction_table_changed)
        self.ed_step.editingFinished.connect(self._on_sweep_field_changed)
        self.combo_solver.currentIndexChanged.connect(self._on_simulation_settings_changed)
        self.ed_nfev.editingFinished.connect(self._on_simulation_settings_changed)
        self.chk_reset_before_run.stateChanged.connect(self._on_simulation_settings_changed)
        self.apply_sweep_settings(self.ctrl.sweep_settings)
        self.apply_simulation_settings(self.ctrl.simulation_settings)

        self.apply_language()
        self.refresh_labels()
        self._refresh_run_buttons()

        # Explicit registration (no import-time side effects / monkey-patch install)
        from .table_context_menu import bind_sim_table_context_menus
        bind_sim_table_context_menus(self)

    def preferred_panel_width(self) -> int:
        """Preferred width for the analysis dock by current sub-tab."""
        base_by_idx = {
            0: 460,  # loads
            1: 450,  # friction
            2: 420,  # measurements
            3: 620,  # curves
            4: 500,  # simulation
            5: 520,  # animation
            6: 480,  # synthesis
            7: 760,  # optimization
        }
        try:
            idx = int(self.tabs.currentIndex())
        except Exception:
            return 500
        base = int(base_by_idx.get(idx, 500))
        try:
            page = self.tabs.widget(idx)
            extra = int(getattr(page, 'preferred_panel_width', lambda: 0)() or 0)
            if extra > 0:
                base = max(base, extra)
        except Exception:
            pass
        return base

    def _configure_panel_width_hints(self) -> None:
        """Phase B: make analysis controls readable without over-widening the dock."""
        try:
            self.tabs.setUsesScrollButtons(True)
        except Exception:
            pass
        for lbl_name in ('lbl_driver', 'lbl_output', 'lbl_driver_sweep', 'lbl_solver_used', 'lbl_qs_mode', 'lbl_tau_in', 'lbl_tau_out'):
            lbl = getattr(self, lbl_name, None)
            if isinstance(lbl, QLabel):
                lbl.setWordWrap(True)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for btn_name in ('btn_clear_driver','btn_clear_output','btn_play','btn_stop','btn_reset_pose','btn_export','btn_check_analysis','btn_save_run'):
            btn = getattr(self, btn_name, None)
            if isinstance(btn, QPushButton):
                btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if hasattr(self, 'combo_solver'):
            self.combo_solver.setMinimumWidth(130)
            self.combo_solver.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        if hasattr(self, 'ed_step'):
            self.ed_step.setMaximumWidth(90)
        if hasattr(self, 'ed_nfev'):
            self.ed_nfev.setMaximumWidth(90)

        def _table_policy(table, minw, interactive_cols=()):
            if not isinstance(table, QTableWidget):
                return
            table.setMinimumWidth(minw)
            hh = table.horizontalHeader()
            try:
                hh.setMinimumSectionSize(36)
                hh.setStretchLastSection(False)
            except Exception:
                pass
            for c in range(table.columnCount()):
                mode = QHeaderView.ResizeMode.Stretch
                if c in interactive_cols:
                    mode = QHeaderView.ResizeMode.Interactive
                try:
                    hh.setSectionResizeMode(c, mode)
                except Exception:
                    pass
            for c in interactive_cols:
                try:
                    hh.resizeSection(c, 90)
                except Exception:
                    pass

        _table_policy(self.table_drivers, 430, interactive_cols=(1,2,3))
        _table_policy(self.table_outputs, 380, interactive_cols=(1,))
        _table_policy(self.table_meas, 420, interactive_cols=(2,))
        _table_policy(self.table_loads, 520, interactive_cols=(2,3,4,5,6,7))
        _table_policy(self.table_joint_loads, 420, interactive_cols=(1,2,3))
        _table_policy(self.table_friction, 460, interactive_cols=(1,2,3,4))

    def apply_language(self) -> None:
        self.title.setText(_tr(self, "panel.analysis_title"))
        self.tabs.setTabText(0, _tr(self, "tab.loads"))
        self.tabs.setTabText(1, _tr(self, "tab.friction"))
        self.tabs.setTabText(2, _tr(self, "tab.measurements"))
        self.tabs.setTabText(3, _tr(self, "tab.curves"))
        self.tabs.setTabText(4, _tr(self, "tab.simulation"))
        self.tabs.setTabText(5, _tr(self, "tab.animation"))
        self.tabs.setTabText(6, _tr(self, "tab.synthesis"))
        self.tabs.setTabText(7, _tr(self, "tab.optimization"))
        self.lbl_solver.setText(_tr(self, "sim.solver"))
        self._refresh_solver_options()
        self._update_used_solver_label()
        self.lbl_step.setText(_tr(self, "sim.step_deg"))
        self.lbl_max_nfev.setText(_tr(self, "sim.max_nfev"))
        self.lbl_driver_sweep.setText(_tr(self, "sim.driver_sweep"))
        self.btn_clear_driver.setText(_tr(self, "sim.clear"))
        self.btn_clear_output.setText(_tr(self, "sim.clear"))
        self.btn_play.setText(_tr(self, "sim.play"))
        self.btn_stop.setText(_tr(self, "sim.stop"))
        self.btn_reset_pose.setText(_tr(self, "sim.reset_pose"))
        self.btn_export.setText(_tr(self, "sim.export_csv"))
        self.btn_save_run.setText(_tr(self, "sim.save_run"))
        self.btn_check_analysis.setText(_tr(self, "analysis.check"))
        self.lbl_applied_loads.setText(_tr(self, "sim.applied_loads"))
        self.lbl_joint_loads.setText(_tr(self, "sim.joint_loads"))
        self.lbl_friction.setText(_tr(self, "sim.friction_joints"))
        self.chk_reset_before_run.setText(_tr(self, "sim.reset_before_run"))
        self.table_meas.setHorizontalHeaderLabels([
            _tr(self, "sim.table.type"),
            _tr(self, "sim.table.measurement"),
            _tr(self, "sim.table.value"),
        ])
        self.table_loads.setHorizontalHeaderLabels([
            _tr(self, "sim.table.point"),
            _tr(self, "sim.table.type"),
            _tr(self, "sim.table.fx"),
            _tr(self, "sim.table.fy"),
            _tr(self, "sim.table.mz"),
            _tr(self, "sim.table.k"),
            _tr(self, "sim.table.load"),
            _tr(self, "sim.table.ref"),
        ])
        self.table_drivers.setHorizontalHeaderLabels([
            _tr(self, "sim.table.driver"),
            _tr(self, "sim.start"),
            _tr(self, "sim.end"),
            _tr(self, "sim.table.value"),
        ])
        self.table_outputs.setHorizontalHeaderLabels([
            _tr(self, "sim.table.output"),
            _tr(self, "sim.table.angle"),
        ])
        self.table_joint_loads.setHorizontalHeaderLabels([
            _tr(self, "sim.table.point"),
            _tr(self, "sim.table.fx"),
            _tr(self, "sim.table.fy"),
            _tr(self, "sim.table.mag"),
        ])
        self.table_friction.setHorizontalHeaderLabels([
            _tr(self, "sim.table.point"),
            _tr(self, "sim.table.mu"),
            _tr(self, "sim.table.diameter"),
            _tr(self, "sim.table.local_load"),
            _tr(self, "sim.table.friction_torque"),
        ])
        if hasattr(self, "animation_tab"):
            self.animation_tab.apply_language()
        if hasattr(self, "optimization_tab"):
            self.optimization_tab.apply_language()
        if hasattr(self, "curves_tab"):
            try:
                self.curves_tab.apply_language()
            except Exception:
                pass
        if hasattr(self, "synthesis_tab"):
            try:
                self.synthesis_tab.apply_language()
            except Exception:
                pass
        self._apply_compact_action_button_widths()
        self._configure_panel_width_hints()
        self.refresh_labels()

    def _apply_compact_action_button_widths(self) -> None:
        """Keep action buttons sized to text, not stretched to full row width."""
        buttons = [
        ]
        for btn in buttons:
            if btn is None:
                continue
            btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            try:
                btn.setMaximumWidth(max(80, btn.sizeHint().width() + 8))
            except Exception:
                pass

    def reset_analysis_state(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._records = []
        self._pending_sim_start_capture = False
        self._run_context = None
        self._run_start_snapshot = None
        self._last_run_data = None
        self._last_used_solver = None
        self._frame = 0
        self._driver_sweep = None
        self._driver_last_ok = []
        self._driver_step_scale = 1.0
        self._driver_step_scale_max = 1.0
        self._sweep_steps_total = None
        self._sweep_step_index = 0
        if hasattr(self, "animation_tab"):
            self.animation_tab.reset_state()
        if hasattr(self, "optimization_tab"):
            self.optimization_tab.reset_state()
        if hasattr(self, "synthesis_tab"):
            try:
                self.synthesis_tab.reset_for_new_project()
            except Exception:
                pass
        try:
            # Clear project-scoped curve/template customizations on 新建.
            if hasattr(self.ctrl, "clear_project_user_curves"):
                self.ctrl.clear_project_user_curves()
            elif hasattr(self.ctrl, "_user_measure_curves"):
                self.ctrl._user_measure_curves = {}
            if hasattr(self.ctrl, "_expression_builder_template_overrides"):
                self.ctrl._expression_builder_template_overrides = {}
        except Exception:
            pass
        self._refresh_run_buttons()
        self.refresh_labels()

    def _project_dir(self) -> str:
        return self._project_paths.project_dir()

    def _run_manager(self):
        return self._run_service.manager()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def has_unsaved_run(self) -> bool:
        # Runs are always written to "current" automatically; there is no unsaved run state.
        return False

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- selection helpers ----
    def _selected_two_points(self) -> Optional[tuple[int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 2:
            lang = _lang(self)
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(_tr(self, "status.select_two_points"))
            return None
        return pids[0], pids[1]

    def _selected_three_points(self) -> Optional[tuple[int, int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 3:
            lang = _lang(self)
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(_tr(self, "status.select_three_points"))
            return None
        return pids[0], pids[1], pids[2]

    def _selected_one_point(self) -> Optional[int]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 1:
            lang = _lang(self)
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(_tr(self, "status.select_one_point"))
            return None
        return pids[0]

    def _solver_options(self) -> List[tuple[str, str]]:
        return [
            ("pbd", _tr(self, "sim.solver.pbd")),
            ("scipy", _tr(self, "sim.solver.scipy")),
            ("exudyn", _tr(self, "sim.solver.exudyn")),
        ]

    def _exudyn_available(self) -> bool:
        return importlib.util.find_spec("exudyn") is not None

    def _init_solver_options(self) -> None:
        self.combo_solver.clear()
        exudyn_available = self._exudyn_available()
        for key, label in self._solver_options():
            if key == "exudyn" and not exudyn_available:
                label = f"{label} (not installed)"
            self.combo_solver.addItem(label, key)
            if key == "exudyn" and not exudyn_available:
                item = self.combo_solver.model().item(self.combo_solver.count() - 1)
                if item is not None:
                    item.setEnabled(False)
        if self.combo_solver.count() == 0:
            self.combo_solver.addItem("PBD", "pbd")

    def _refresh_solver_options(self) -> None:
        current = self.get_solver_name()
        self.combo_solver.blockSignals(True)
        self._init_solver_options()
        self.set_solver_name(current)
        self.combo_solver.blockSignals(False)

    def get_solver_name(self) -> str:
        name = self.combo_solver.currentData()
        if not name:
            return "pbd"
        return str(name)

    def set_solver_name(self, name: str) -> None:
        name = str(name or "").lower()
        if name == "exudyn" and not self._exudyn_available():
            name = "pbd"
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage("Exudyn is not installed; using PBD instead.")
        index = self.combo_solver.findData(name)
        if index < 0:
            index = self.combo_solver.findData("pbd")
        if index >= 0:
            self.combo_solver.setCurrentIndex(index)

    def _has_point_spline(self) -> bool:
        return any(
            ps.get("enabled", True)
            for ps in getattr(self.ctrl, "point_splines", {}).values()
        )

    def _effective_solver_name(self) -> str:
        solver_name = self.get_solver_name()
        if self._has_point_spline() and solver_name == "scipy":
            return "pbd"
        return solver_name

    def _solver_display_label(self, solver_name: str) -> str:
        label = _tr(self, f"sim.solver.{solver_name}")
        if label == f"sim.solver.{solver_name}":
            return solver_name
        return label

    def _mark_used_solver_unknown(self) -> None:
        self._last_used_solver = None
        self._last_solver_fallback_from = None
        self._update_used_solver_label()

    def _update_used_solver_label(self, solver_name: Optional[str] = None) -> None:
        if not hasattr(self, "lbl_solver_used"):
            return
        if solver_name is None:
            solver_name = self._last_used_solver
        else:
            self._last_used_solver = solver_name
        fallback_from = self._last_solver_fallback_from
        if solver_name is None:
            solver_name = "NA"
        display = self._solver_display_label(str(solver_name))
        if fallback_from:
            display_fallback = self._solver_display_label(str(fallback_from))
            display = f"{display} (fallback from {display_fallback})"
        self.lbl_solver_used.setText(_tr(self, "sim.solver.used").format(solver=display))

    def _set_used_solver(self, solver_name: str, fallback_from: Optional[str] = None) -> None:
        self._last_used_solver = solver_name
        self._last_solver_fallback_from = fallback_from
        self._update_used_solver_label()

    def _notify_solver_fallback(self, solver_name: str, msg: str) -> None:
        if not msg:
            msg = "unknown error"
        if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
            self.ctrl.win.statusBar().showMessage(
                f"{self._solver_display_label(solver_name)} failed ({msg}), fallback to PBD."
            )

    def apply_sweep_settings(self, settings: Dict[str, float]) -> None:
        step = settings.get("step", 200.0)
        try:
            step_val = int(round(float(step)))
        except Exception:
            step_val = 200
        step_val = max(step_val, 1)
        self.ed_step.setText(f"{step_val}")

    def get_simulation_settings(self) -> Dict[str, Any]:
        try:
            max_nfev = int(float(self.ed_nfev.text() or "250"))
        except Exception:
            max_nfev = 250
        if max_nfev <= 0:
            max_nfev = 250
        return {
            "solver": self.get_solver_name(),
            "max_nfev": max_nfev,
            "reset_before_run": bool(self.chk_reset_before_run.isChecked()),
        }

    def apply_simulation_settings(self, settings: Dict[str, Any]) -> None:
        solver_name = str(settings.get("solver") or ("scipy" if settings.get("use_scipy", True) else "pbd"))
        reset_before = bool(settings.get("reset_before_run", True))
        try:
            max_nfev = int(float(settings.get("max_nfev", 250)))
        except Exception:
            max_nfev = 250
        if max_nfev <= 0:
            max_nfev = 250
        self.set_solver_name(solver_name)
        self.ed_nfev.setText(str(max_nfev))
        self.chk_reset_before_run.setChecked(reset_before)
        self._sync_simulation_settings_from_fields()
        self._mark_used_solver_unknown()

    def _sync_simulation_settings_from_fields(self) -> None:
        if not hasattr(self.ctrl, "simulation_settings"):
            return
        self.ctrl.simulation_settings = self.get_simulation_settings()

    def _on_simulation_settings_changed(self) -> None:
        self._sync_simulation_settings_from_fields()
        self._mark_used_solver_unknown()

    def _sync_sweep_settings_from_fields(self) -> None:
        try:
            step = float(self.ed_step.text())
        except Exception:
            return
        step = int(round(abs(step)))
        if step <= 0:
            step = int(round(float(self.ctrl.sweep_settings.get("step", 200.0)) or 200.0))
            step = max(step, 1)
        self.ctrl.sweep_settings = {
            "start": self.ctrl.sweep_settings.get("start", 0.0),
            "end": self.ctrl.sweep_settings.get("end", 360.0),
            "step": step,
        }
        self.ed_step.setText(f"{step}")

    def _on_sweep_field_changed(self) -> None:
        self._sync_sweep_settings_from_fields()

    # ---- UI actions ----
    # ---- sweep ----
    def _start_numeric_playback(self, explicit_case_name: Optional[str] = None, explicit_case_spec: Optional[Dict[str, Any]] = None) -> None:
        # Numeric run must be independent from any replay payload that may have
        # temporarily moved the live model to a saved run pose.
        # Always record pose_points so replay depends only on saved run data,
        # never on the current live model / active case / current tab.
        self._record_pose_points = True
        try:
            anim = getattr(self, "animation_tab", None)
            if anim is not None and hasattr(anim, "release_replay_model_state"):
                anim.release_replay_model_state()
        except Exception:
            pass
        if hasattr(self, "chk_reset_before_run") and self.chk_reset_before_run.isChecked():
            if self.ctrl.reset_pose_to_sim_start():
                self.ctrl.update_graphics()
                if self.ctrl.panel:
                    self.ctrl.panel.defer_refresh_all(keep_selection=True)
        try:
            step = float(self.ed_step.text())
        except ValueError:
            QMessageBox.warning(self, _tr(self, "sweep.title"), _tr(self, "sweep.msg.step_numbers"))
            return
        step = int(round(abs(step)))
        if step <= 0:
            QMessageBox.warning(self, _tr(self, "sweep.title"), _tr(self, "sweep.msg.step_positive"))
            return
        active_drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
        start = self.ctrl.sweep_settings.get("start", 0.0)
        end = self.ctrl.sweep_settings.get("end", 360.0)
        if active_drivers:
            start = active_drivers[0].get("sweep_start", start)
            end = active_drivers[0].get("sweep_end", end)
        try:
            start = float(start)
        except Exception:
            start = 0.0
        try:
            end = float(end)
        except Exception:
            end = 360.0
        self.ctrl.sweep_settings = {"start": start, "end": end, "step": step}
        self.ed_step.setText(f"{step}")

        self.stop()
        self.ctrl.mark_sim_start_pose()
        self._pending_sim_start_capture = True
        self.ctrl.reset_trajectories()

        self._records = []
        self._frame = 0
        self._last_run_data = None
        self._last_solver_error = None
        self._solver_error_log = []
        self._run_start_snapshot = self.ctrl.snapshot_model()
        self._sweep_steps_total = int(step)
        self._sweep_step_index = 0
        self._theta_start = start
        has_non_angle_driver = any(d.get("type") != "angle" for d in active_drivers)
        use_driver_sweep = bool(active_drivers) and (len(active_drivers) > 1 or has_non_angle_driver)
        if use_driver_sweep:
            driver_sweep = []
            base_steps = []
            for drv in active_drivers:
                s = drv.get("sweep_start", start)
                e = drv.get("sweep_end", end)
                try:
                    s = float(s)
                except Exception:
                    s = start
                try:
                    e = float(e)
                except Exception:
                    e = end
                base_step = (e - s) / self._sweep_steps_total if self._sweep_steps_total else 0.0
                driver_sweep.append({"start": s, "end": e, "step": base_step})
                base_steps.append(abs(base_step))
            self._driver_sweep = driver_sweep
            self._driver_last_ok = [entry["start"] for entry in driver_sweep]
            self._driver_step_scale = 1.0
            self._theta_last_ok = start
            self._theta_deg = start
            self._theta_end = end
            max_step = max(base_steps) if base_steps else 0.0
            max_range = max(abs(entry["end"] - entry["start"]) for entry in driver_sweep) if driver_sweep else 0.0
            adaptive_max = max(max_step * 4.0, max_range / 60.0, max_step)
            if max_range > 0.0:
                adaptive_max = min(adaptive_max, max_range)
            self._theta_step = max_step
            self._theta_step_cur = max_step
            self._theta_step_max = adaptive_max
            self._theta_step_min = max(max_step / 128.0, 1e-4)
            self._driver_step_scale_max = adaptive_max / max_step if max_step else 1.0
        else:
            self._driver_sweep = None
            self._driver_last_ok = []
            self._driver_step_scale = 1.0
            self._theta_last_ok = start
            self._theta_deg = start
            self._theta_end = end
            base_step = (end - start) / self._sweep_steps_total if self._sweep_steps_total else 0.0
            sweep_range = abs(end - start)
            adaptive_max = max(abs(base_step) * 4.0, sweep_range / 60.0, abs(base_step))
            if sweep_range > 0.0:
                adaptive_max = min(adaptive_max, sweep_range)
            self._theta_step = base_step
            self._theta_step_cur = base_step
            self._theta_step_max = adaptive_max
            self._theta_step_min = max(abs(base_step) / 128.0, 1e-4)
            self._driver_step_scale_max = 1.0

        case_spec = dict(explicit_case_spec) if isinstance(explicit_case_spec, dict) and explicit_case_spec else self._build_case_spec()
        run_case_name = str(explicit_case_name) if explicit_case_name not in (None, "") else None
        self._run_context = {
            "started_utc": self._utc_now(),
            "start_time": time.time(),
            "case_spec": case_spec,
            "case_name": run_case_name,
        }
        self._refresh_run_buttons()

        self._on_tick()
        self._timer.start(15)

    def _try_play_saved_case_run(self) -> bool:
        try:
            manager = self._run_manager()
            active_case_name = manager.get_active_case() if manager else None
        except Exception:
            active_case_name = None
            manager = None
        if not active_case_name or manager is None:
            return False
        try:
            dirty = bool(self.ctrl.case_needs_rerun(active_case_name)) if hasattr(self.ctrl, "case_needs_rerun") else False
        except Exception:
            dirty = False
        runs = manager.list_runs(str(active_case_name))
        run = runs[0] if runs else None
        anim = getattr(self, "animation_tab", None)
        already_loaded = bool(anim is not None and getattr(anim, "_loaded_case_id", None) == str(active_case_name) and getattr(anim, "_frames", None))
        if run and not dirty:
            if already_loaded:
                if anim is not None and hasattr(anim, "play_replay"):
                    anim.play_replay()
                    return True
                return False
            ask = QMessageBox.question(
                self,
                _tr(self, "run.title"),
                _tr(self, "analysis.msg.load_run_for_play", default="Load saved run data for the current case and start replay?")
            )
            if ask == QMessageBox.StandardButton.Yes:
                if anim is not None and hasattr(anim, "_load_run_data_for_run") and hasattr(anim, "play_replay"):
                    anim._load_run_data_for_run(run, str(active_case_name))
                    anim.play_replay()
                    return True
            return False
        if run is None:
            msg = _tr(self, "analysis.msg.no_saved_run_run_now", default="This case has no saved run data. Run it now?")
        else:
            msg = _tr(self, "analysis.msg.model_changed_rerun", default="The model changed after the saved run. Re-run this case now?")
        ask = QMessageBox.question(self, _tr(self, "run.title"), msg)
        if ask == QMessageBox.StandardButton.Yes:
            self._start_numeric_playback()
            return True
        return True

    def play(self):
        if not self.ctrl.drivers and not self.ctrl.outputs:
            QMessageBox.information(self, _tr(self, "driver.title"), _tr(self, "driver.msg.set_driver_or_output"))
            return
        # Clean rule: when the Animation tab is the current context, the toolbar
        # Run button delegates to the animation table's explicit selection.
        # SimPanel no longer guesses a case by mixing selection/active/UI state.
        try:
            tabs = getattr(self, "tabs", None)
            current_tab = tabs.currentWidget() if tabs is not None else None
            anim = getattr(self, "animation_tab", None)
            if anim is not None and current_tab is anim and hasattr(anim, "run_selected_case"):
                if anim.run_selected_case(autoload_after_run=False):
                    return
        except Exception:
            pass
        # Numeric run must be independent from animation replay. Saved replay
        # data is handled only from the Animation tab's playback button.
        self._start_numeric_playback()

    def _restore_case_start_pose(self, case_name: str) -> bool:
        """Restore the saved *start pose* of a case before rerunning it.

        Root cause fixed here:
        different cases were sharing one global ``sim start pose`` from the most
        recent run. As a result, rerunning case "30" right after case "-40"
        would still start from the "-40" pose and produce the same branch.

        We now restore the selected case's own saved ``model.json`` point pose
        (runs/<case>/current/model.json) when available and topology matches.
        """
        try:
            manager = self._run_manager()
            runs = manager.list_runs(str(case_name)) if manager is not None else []
            run = runs[0] if runs else None
            if not run:
                return False
            path = str(run.get("path") or "")
            if not path:
                return False
            model_path = os.path.join(path, "model.json")
            if not os.path.exists(model_path):
                return False
            with open(model_path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
            point_rows = snapshot.get("points", []) if isinstance(snapshot, dict) else []
            pose = {}
            for item in point_rows:
                if not isinstance(item, dict):
                    continue
                pid = item.get("id")
                if pid is None:
                    continue
                try:
                    pose[int(pid)] = (float(item.get("x", 0.0)), float(item.get("y", 0.0)))
                except Exception:
                    continue
            if not pose:
                return False
            current_ids = set(getattr(self.ctrl, "points", {}).keys())
            if set(pose.keys()) != current_ids:
                return False
            self.ctrl.apply_points_snapshot(pose)
            self.ctrl.solve_constraints()
            self.ctrl.update_graphics()
            if getattr(self.ctrl, "panel", None):
                self.ctrl.panel.defer_refresh_all(keep_selection=True)
            # Very important: replace the shared global sim-start baseline with
            # this case's own restored start pose before the numeric run begins.
            self.ctrl.mark_sim_start_pose()
            return True
        except Exception as exc:
            return False

    def run_case(self, case_name: str, case_spec: Dict[str, Any]) -> None:
        """Run one saved case in isolation from live UI/run/replay state.

        Clean rule:
        - use the *current* model topology/geometry as the model snapshot,
        - use the selected case's stored spec as the only run spec,
        - generate/save frames headlessly,
        - do not let replay or the live simulation timer influence the result.
        """
        case_name = str(case_name)
        spec = dict(case_spec or {})
        manager = self._run_manager()
        if manager is not None:
            try:
                manager.set_active_case(case_name)
            except Exception:
                pass

        # A case rerun must not inherit any loaded replay or active timer state.
        try:
            anim = getattr(self, "animation_tab", None)
            if anim is not None and hasattr(anim, "release_replay_model_state"):
                anim.release_replay_model_state()
        except Exception:
            pass
        self.stop()

        # Use the current model as the geometry/topology source so ordinary model
        # edits rerun against the latest mechanism, while the case spec still
        # controls drivers/outputs/sweep independently.
        model_snapshot = self.ctrl.snapshot_model()
        started_utc = self._utc_now()
        start_time = time.time()
        try:
            frames, status, end_snapshot = simulate_case(model_snapshot, spec)
            success = bool((status or {}).get("success", False))
            reason = str((status or {}).get("reason", ""))
        except Exception as exc:
            frames = []
            end_snapshot = model_snapshot
            success = False
            reason = str(exc)
            status = {
                "success": False,
                "reason": reason,
                "solver_error": reason,
                "solver_error_log": [reason],
            }
        elapsed = max(0.0, time.time() - start_time)
        status = dict(status or {})
        status.setdefault("success", success)
        status.setdefault("reason", reason)
        status.setdefault("elapsed_sec", elapsed)
        status.setdefault("started_utc", started_utc)
        status.setdefault("finished_utc", self._utc_now())

        self._last_run_data = {
            "case_spec": spec,
            "start_snapshot": model_snapshot,
            "end_snapshot": end_snapshot if isinstance(end_snapshot, dict) else model_snapshot,
            "records": list(frames or []),
            "status": status,
        }
        self._last_saved_case_id = None
        self._refresh_run_buttons()

        try:
            if success and hasattr(self.ctrl, "mark_cases_clean_after_run"):
                self.ctrl.mark_cases_clean_after_run(case_name)
            if manager is not None:
                run_dir = self._run_service.save_case_run(
                    case_name,
                    spec,
                    self._last_run_data.get("start_snapshot", {}),
                    self._last_run_data.get("records", []),
                    self._last_run_data.get("status", {}),
                    end_snapshot=self._last_run_data.get("end_snapshot"),
                )
                self._run_service.save_last_run(
                    spec,
                    self._last_run_data.get("start_snapshot", {}),
                    self._last_run_data.get("records", []),
                    self._last_run_data.get("status", {}),
                    end_snapshot=self._last_run_data.get("end_snapshot"),
                )
        except Exception as exc:
            self._report_persistence_error(_tr(self, "save.failed"), exc)

        try:
            anim = getattr(self, "animation_tab", None)
            if anim is not None and hasattr(anim, "on_case_run_saved"):
                anim.on_case_run_saved(case_name)
        except Exception:
            pass

        if hasattr(self.ctrl, "win") and self.ctrl.win:
            msg = "Run finished" if success else f"Run failed: {reason or 'failed'}"
            self.ctrl.win.statusBar().showMessage(msg)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        if self._run_context is not None:
            self._complete_run(success=False, reason="stopped")

    def reset_pose(self):
        self.stop()
        ok = self.ctrl.reset_pose_to_sim_start()
        if not ok:
            QMessageBox.information(self, _tr(self, "reset.title"), _tr(self, "reset.msg.no_start_pose"))
        self.refresh_labels()
        self.ctrl.update_graphics()

    def _sweep_reached_end(self) -> bool:
        tol = max(float(getattr(self, "_theta_step_min", 1e-4)), 1e-6)
        if self._driver_sweep:
            for last_ok, entry in zip(self._driver_last_ok, self._driver_sweep):
                start = float(entry.get("start", last_ok))
                end = float(entry.get("end", last_ok))
                if abs(end - start) <= tol:
                    if abs(end - last_ok) > tol:
                        return False
                elif end > start:
                    if last_ok < end - tol:
                        return False
                else:
                    if last_ok > end + tol:
                        return False
            return True
        start = float(getattr(self, "_theta_start", 0.0))
        end = float(getattr(self, "_theta_end", 0.0))
        if abs(end - start) <= tol:
            return abs(self._theta_last_ok - end) <= tol
        if end > start:
            return self._theta_last_ok >= end - tol
        return self._theta_last_ok <= end + tol




    def _on_tabs_changed(self, idx: int) -> None:
        """Refresh lightweight UI only.

        Replay correctness must not depend on which tab happened to be open
        during the numeric run. We therefore keep per-frame pose recording
        enabled for all runs and only do UI refresh work here.
        """
        try:
            w = self.tabs.widget(idx)
            if w is self.animation_tab:
                try:
                    self.animation_tab.reset_to_first_frame()
                except Exception:
                    pass
            if w is getattr(self, "curves_tab", None):
                try:
                    self.curves_tab.refresh_curves()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            win = getattr(self.ctrl, "win", None)
            if win is not None and hasattr(win, "_sync_right_dock_width_for_current_context"):
                win._sync_right_dock_width_for_current_context()
        except Exception:
            pass
    def _on_tick(self):
        if self._sweep_reached_end():
            self._finalize_end_pose()
            self._complete_run(success=True, reason="completed")
            self.refresh_labels()
            return

        ok = True
        step_applied = False
        msg = ""
        has_point_spline = self._has_point_spline()
        solver_name = self.get_solver_name()
        if has_point_spline and solver_name in ("scipy",):
            solver_name = "pbd"
        actual_solver = solver_name
        iters = 200 if has_point_spline else 80
        base_step = self._theta_step
        step_target = self._theta_step_cur
        theta_target = self._theta_last_ok + step_target
        driver_targets: List[float] = []
        if self._driver_sweep:
            driver_targets = []
            desired_targets = []
            for last_ok, entry in zip(self._driver_last_ok, self._driver_sweep):
                start = float(entry.get("start", last_ok))
                end = float(entry.get("end", last_ok))
                base = float(entry.get("step", 0.0))
                desired = last_ok + base
                if end >= start:
                    desired = min(desired, end)
                else:
                    desired = max(desired, end)
                desired_targets.append(desired)
            for last_ok, desired, entry in zip(self._driver_last_ok, desired_targets, self._driver_sweep):
                scale = self._driver_step_scale
                start = float(entry.get("start", last_ok))
                end = float(entry.get("end", last_ok))
                target = last_ok + (desired - last_ok) * scale
                if end >= start:
                    target = min(target, end)
                else:
                    target = max(target, end)
                driver_targets.append(target)
            step_target = 0.0
            for last_ok, target in zip(self._driver_last_ok, driver_targets):
                step_target = max(step_target, abs(target - last_ok))
        else:
            if self._theta_end >= self._theta_start:
                theta_target = min(theta_target, self._theta_end)
            else:
                theta_target = max(theta_target, self._theta_end)
            step_target = theta_target - self._theta_last_ok
        tol = 1e-3
        hard_err_value = None
        while True:
            pose_before = self.ctrl.snapshot_points()
            has_non_angle_driver = any(d.get("type") != "angle" for d in self.ctrl._active_drivers())
            if solver_name == "scipy":
                try:
                    nfev = int(float(self.ed_nfev.text() or "250"))
                except Exception:
                    nfev = 250
                if self._driver_sweep:
                    if has_non_angle_driver:
                        self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                        ok, msg = True, ""
                    else:
                        ok, msg = self.ctrl.drive_to_multi_deg_scipy(driver_targets, max_nfev=nfev)
                else:
                    ok, msg = self.ctrl.drive_to_deg_scipy(theta_target, max_nfev=nfev)
                if not ok:
                    self.ctrl.apply_points_snapshot(pose_before)
                    # Fallback to PBD so the UI stays responsive
                    actual_solver = "pbd"
                    self._record_solver_error(solver_name, msg)
                    self._notify_solver_fallback(solver_name, msg)
                    if self._driver_sweep:
                        if has_non_angle_driver:
                            self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                        else:
                            self.ctrl.drive_to_multi_deg(driver_targets, iters=iters)
                    else:
                        self.ctrl.drive_to_deg(theta_target, iters=iters)
            elif solver_name == "exudyn":
                if self._driver_sweep:
                    if has_non_angle_driver:
                        self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                        ok, msg = True, ""
                    else:
                        ok, msg = self.ctrl.drive_to_multi_deg_exudyn(driver_targets, max_iters=iters)
                else:
                    ok, msg = self.ctrl.drive_to_deg_exudyn(theta_target, max_iters=iters)
                if not ok:
                    self.ctrl.apply_points_snapshot(pose_before)
                    actual_solver = "pbd"
                    self._record_solver_error(solver_name, msg)
                    self._notify_solver_fallback(solver_name, msg)
                    if self._driver_sweep:
                        if has_non_angle_driver:
                            self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                        else:
                            self.ctrl.drive_to_multi_deg(driver_targets, iters=iters)
                    else:
                        self.ctrl.drive_to_deg(theta_target, iters=iters)
            else:
                if self._driver_sweep:
                    if has_non_angle_driver:
                        self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                    else:
                        self.ctrl.drive_to_multi_deg(driver_targets, iters=iters)
                else:
                    self.ctrl.drive_to_deg(theta_target, iters=iters)

            # Feasibility check: do not "stretch" links across dead points.
            # If the requested step is infeasible, rollback and reduce the step.
            if hasattr(self.ctrl, "max_constraint_error"):
                max_err, detail = self.ctrl.max_constraint_error()
                hard_err = max(
                    detail.get("length", 0.0),
                    detail.get("angle", 0.0),
                    detail.get("coincide", 0.0),
                    detail.get("point_line", 0.0),
                    detail.get("point_spline", 0.0),
                )
                hard_err_value = hard_err
                if hard_err > tol:
                    # rollback to previous pose
                    self.ctrl.apply_points_snapshot(pose_before)
                    self.ctrl.solve_constraints(iters=iters)
                    self.ctrl.update_graphics()
                    if self.ctrl.panel:
                        self.ctrl.panel.defer_refresh_all()
                    ok = False
                    msg = f"infeasible step (hard_err={hard_err:.3g}, max_err={max_err:.3g})"
                    if abs(step_target) <= self._theta_step_min:
                        self._complete_run(success=False, reason=msg or "infeasible_step")
                        step_applied = False
                        break
                    step_target *= 0.5
                    if self._driver_sweep:
                        self._driver_step_scale *= 0.5
                        driver_targets = []
                        for last_ok, desired, entry in zip(self._driver_last_ok, desired_targets, self._driver_sweep):
                            start = float(entry.get("start", last_ok))
                            end = float(entry.get("end", last_ok))
                            target = last_ok + (desired - last_ok) * self._driver_step_scale
                            if end >= start:
                                target = min(target, end)
                            else:
                                target = max(target, end)
                            driver_targets.append(target)
                    else:
                        theta_target = self._theta_last_ok + step_target
                    continue
            step_applied = True
            break

        if self._pending_sim_start_capture:
            self.ctrl.update_sim_start_pose_snapshot()
            self._pending_sim_start_capture = False

        if step_applied:
            self.ctrl.append_trajectories()
        fallback_from = solver_name if actual_solver == "pbd" and solver_name != "pbd" else None
        self._set_used_solver(actual_solver, fallback_from=fallback_from)
        self._ui_refresh_counter += 1
        if self._ui_refresh_counter % max(1, self._ui_refresh_stride) == 0:
            self.refresh_labels()


        rec: Dict[str, Any] = {
            "time": self._frame,
            "solver": actual_solver,
            "success": ok,
            "input_deg": self.ctrl.get_input_angle_deg(),
            "output_deg": self.ctrl.get_output_angle_deg(),
            "driver_deg": list(self.ctrl.get_driver_angles_deg()),
        }
        # Fast replay payload (see AnimationTab._apply_frame).
        if self._record_pose_points:
            try:
                pts = self.ctrl.snapshot_points()
                rec["pose_points"] = [[int(pid), float(x), float(y)] for pid, (x, y) in pts.items()]
            except Exception:
                pass
        rec["hard_err"] = hard_err_value
        for nm, val, _unit in self.ctrl.get_measure_values():
            rec[nm] = val
        for nm, val in self.ctrl.get_load_measure_values():
            rec[nm] = val
        self._records.append(rec)

        self._frame += 1
        if step_applied:
            if self._driver_sweep:
                self._driver_last_ok = list(driver_targets)
                if self._driver_step_scale < 1.0:
                    self._driver_step_scale = min(1.0, self._driver_step_scale * 1.25)
                if hard_err_value is not None and ok and hard_err_value < tol * 0.25:
                    self._driver_step_scale = min(self._driver_step_scale_max, self._driver_step_scale * 1.25)
                self._theta_step_cur = math.copysign(
                    min(abs(base_step) * self._driver_step_scale, self._theta_step_max),
                    base_step if base_step else 1.0,
                )
            else:
                self._theta_last_ok = theta_target
                self._theta_deg = self._theta_last_ok + step_target
                self._theta_step_cur = step_target
                if abs(self._theta_step_cur) < abs(base_step):
                    grow = abs(self._theta_step_cur) * 1.25
                    grow = min(abs(base_step), grow)
                    self._theta_step_cur = math.copysign(grow, base_step)
                    self._theta_deg = self._theta_last_ok + self._theta_step_cur
                if hard_err_value is not None and ok and hard_err_value < tol * 0.25:
                    grow = min(abs(self._theta_step_cur) * 1.25, self._theta_step_max)
                    self._theta_step_cur = math.copysign(grow, base_step if base_step else step_target or 1.0)
                    self._theta_deg = self._theta_last_ok + self._theta_step_cur
            self._sweep_step_index += 1

    def _finalize_end_pose(self) -> None:
        has_point_spline = self._has_point_spline()
        solver_name = self.get_solver_name()
        if has_point_spline and solver_name == "scipy":
            solver_name = "pbd"
        actual_solver = solver_name
        iters = 200 if has_point_spline else 80
        if solver_name == "scipy":
            try:
                nfev = int(float(self.ed_nfev.text() or "250"))
            except Exception:
                nfev = 250
        else:
            nfev = None

        if self._driver_sweep:
            targets = [float(entry.get("end", last_ok)) for last_ok, entry in zip(self._driver_last_ok, self._driver_sweep)]
            has_non_angle_driver = any(d.get("type") != "angle" for d in self.ctrl._active_drivers())
            if solver_name == "scipy" and nfev is not None:
                if has_non_angle_driver:
                    self.ctrl.drive_to_multi_values(targets, iters=iters)
                else:
                    ok, _msg = self.ctrl.drive_to_multi_deg_scipy(targets, max_nfev=nfev)
                    if not ok:
                        actual_solver = "pbd"
                        self.ctrl.drive_to_multi_deg(targets, iters=iters)
            elif solver_name == "exudyn":
                if has_non_angle_driver:
                    self.ctrl.drive_to_multi_values(targets, iters=iters)
                else:
                    ok, _msg = self.ctrl.drive_to_multi_deg_exudyn(targets, max_iters=iters)
                    if not ok:
                        actual_solver = "pbd"
                        self.ctrl.drive_to_multi_deg(targets, iters=iters)
            else:
                if has_non_angle_driver:
                    self.ctrl.drive_to_multi_values(targets, iters=iters)
                else:
                    self.ctrl.drive_to_multi_deg(targets, iters=iters)
            self._driver_last_ok = list(targets)
        else:
            target = float(self._theta_end)
            if solver_name == "scipy" and nfev is not None:
                ok, _msg = self.ctrl.drive_to_deg_scipy(target, max_nfev=nfev)
                if not ok:
                    actual_solver = "pbd"
                    self.ctrl.drive_to_deg(target, iters=iters)
            elif solver_name == "exudyn":
                ok, _msg = self.ctrl.drive_to_deg_exudyn(target, max_iters=iters)
                if not ok:
                    actual_solver = "pbd"
                    self.ctrl.drive_to_deg(target, iters=iters)
            else:
                self.ctrl.drive_to_deg(target, iters=iters)
            self._theta_last_ok = target
            self._theta_deg = target
        self.ctrl.append_trajectories()
        fallback_from = solver_name if actual_solver == "pbd" and solver_name != "pbd" else None
        self._set_used_solver(actual_solver, fallback_from=fallback_from)

    def _build_case_spec(self) -> Dict[str, Any]:
        has_point_spline = any(
            ps.get("enabled", True)
            for ps in getattr(self.ctrl, "point_splines", {}).values()
        )
        try:
            max_nfev = int(float(self.ed_nfev.text() or "250"))
        except Exception:
            max_nfev = 250
        iters = 200 if has_point_spline else 80
        signals = ["input_deg", "output_deg", "hard_err", "success"]
        signals.extend([name for name, _val, _unit in self.ctrl.get_measure_values()])
        signals.extend([name for name, _val in self.ctrl.get_load_measure_values()])
        target_inputs = []
        for drv in self.ctrl.drivers:
            if not isinstance(drv, dict):
                continue
            try:
                target_inputs.append(float(drv.get("sweep_end", self.ctrl.sweep_settings.get("end", 360.0))))
            except Exception:
                target_inputs.append(float(self.ctrl.sweep_settings.get("end", 360.0)))
        return {
            "schema_version": "1.0",
            "target_input_deg": target_inputs[0] if target_inputs else float(self.ctrl.sweep_settings.get("end", 360.0)),
            "target_input_deg_list": target_inputs,
            "analysis_mode": "quasi_static",
            # Record per-frame point positions so the Animation tab can replay
            # smoothly without invoking the numeric solver on every frame.
            "record_pose": True,
            "driver": dict(self.ctrl.driver),
            "drivers": [dict(d) for d in self.ctrl.drivers],
            "output": dict(self.ctrl.output),
            "outputs": [dict(o) for o in self.ctrl.outputs],
            "sweep": {
                "start_deg": float(self.ctrl.sweep_settings.get("start", 0.0)),
                "end_deg": float(self.ctrl.sweep_settings.get("end", 360.0)),
                "step_count": int(self.ctrl.sweep_settings.get("step", 2.0)),
                "adaptive": True,
                "min_step_deg": float(self._theta_step_min),
                "max_step_deg": float(abs(self._theta_step_max)),
                "dtheta_min_deg": 0.05,
                "dtheta_max_deg": 2.0,
                "err_good": 1e-10,
                "err_ok": 1e-7,
                "grow": 1.35,
                "shrink": 0.5,
                "max_retries_per_step": 8,
            },
            "solver": {
                "name": self.get_solver_name(),
                "max_nfev": max_nfev,
                "pbd_iters": iters,
                "hard_err_tol": 1e-3,
                "treat_point_spline_as_soft": bool(has_point_spline),
            },
            "loads": list(self.ctrl.loads),
            "friction_joints": list(self.ctrl.friction_joints),
            "measurements": {
                "signals": signals,
                "measures": list(self.ctrl.measures),
                "load_measures": list(self.ctrl.load_measures),
            },
        }

    # ---- cases/runs integration ----
    def apply_case_spec(self, case_spec: Dict[str, Any]) -> None:
        """Apply a stored case spec to the current controller + UI.

        A *case* is just a definition of drivers/outputs/sweep/loads/measurements.
        It should not lock editing.
        """
        if not isinstance(case_spec, dict):
            return
        # Drivers / outputs / loads / friction / measurements
        try:
            drivers_list = case_spec.get("drivers")
            driver = case_spec.get("driver")
            if isinstance(drivers_list, list):
                self.ctrl.drivers = [self.ctrl._normalize_driver(d) for d in drivers_list if isinstance(d, dict)]
                self.ctrl._sync_primary_driver()
            elif isinstance(driver, dict):
                self.ctrl.drivers = [self.ctrl._normalize_driver(driver)]
                self.ctrl._sync_primary_driver()
        except Exception:
            pass
        try:
            outputs_list = case_spec.get("outputs")
            output = case_spec.get("output")
            if isinstance(outputs_list, list):
                self.ctrl.outputs = [self.ctrl._normalize_output(o) for o in outputs_list if isinstance(o, dict)]
                self.ctrl._sync_primary_output()
            elif isinstance(output, dict):
                self.ctrl.outputs = [self.ctrl._normalize_output(output)]
                self.ctrl._sync_primary_output()
        except Exception:
            pass
        try:
            loads = case_spec.get("loads")
            if isinstance(loads, list):
                self.ctrl.loads = [dict(ld) for ld in loads]
        except Exception:
            pass
        try:
            friction_joints = case_spec.get("friction_joints")
            if isinstance(friction_joints, list):
                self.ctrl.friction_joints = [dict(fj) for fj in friction_joints]
        except Exception:
            pass
        try:
            measurements = case_spec.get("measurements", {}) or {}
            measures = measurements.get("measures")
            if isinstance(measures, list):
                self.ctrl.measures = [dict(m) for m in measures]
            load_measures = measurements.get("load_measures")
            if isinstance(load_measures, list):
                self.ctrl.load_measures = [dict(m) for m in load_measures]
        except Exception:
            pass

        # Sweep
        try:
            sweep = case_spec.get("sweep", {}) or {}
            fallback_target = case_spec.get("target_input_deg", self.ctrl.sweep_settings.get("end", 360.0))
            start = float(sweep.get("start_deg", self.ctrl.sweep_settings.get("start", 0.0)))
            end = float(sweep.get("end_deg", fallback_target))
            step = int(float(sweep.get("step_count", self.ctrl.sweep_settings.get("step", 200))))
            step = max(1, step)
            self.ctrl.sweep_settings = {"start": start, "end": end, "step": step}
            if hasattr(self, "ed_step"):
                self.ed_step.setText(f"{step}")
        except Exception:
            pass

        # Solver (UI fields only)
        try:
            solver = case_spec.get("solver", {}) or {}
            name = str(solver.get("name", ""))
            if name:
                self.set_solver_name(name)
            if "max_nfev" in solver and hasattr(self, "ed_nfev"):
                self.ed_nfev.setText(str(int(float(solver.get("max_nfev") or 250))))
        except Exception:
            pass

        try:
            self._mark_used_solver_unknown()
        except Exception:
            pass
        try:
            self.refresh_labels()
        except Exception:
            pass
        try:
            self.ctrl.update_graphics()
        except Exception:
            pass

    def _complete_run(self, success: bool, reason: str) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if not self._run_context:
            return
        run_context = dict(self._run_context)
        start_time = run_context.get("start_time", time.time())
        elapsed = max(0.0, time.time() - float(start_time))
        status = {
            "success": bool(success),
            "elapsed_sec": elapsed,
            "reason": reason,
            "solver_error": self._last_solver_error,
            "solver_error_log": list(self._solver_error_log),
            "started_utc": run_context.get("started_utc"),
            "finished_utc": self._utc_now(),
        }
        case_spec = run_context.get("case_spec", {})
        end_snapshot = self.ctrl.snapshot_model()
        self._last_run_data = {
            "case_spec": case_spec,
            "start_snapshot": self._run_start_snapshot or end_snapshot,
            "end_snapshot": end_snapshot,
            "records": list(self._records),
            "status": status,
        }
        self._run_context = None
        explicit_case_name = run_context.get("case_name")
        manager = None
        active_case_name = None
        try:
            manager = self._run_manager()
            active_case_name = manager.get_active_case() if manager else None
        except Exception:
            manager = None
            active_case_name = None

        try:
            # Critical rule: a plain numeric Run must never overwrite a saved case
            # just because some case happens to be active in the UI. Only runs that
            # were explicitly started for a specific case may save back into that
            # case's current run directory.
            if bool(success) and explicit_case_name and hasattr(self.ctrl, "mark_cases_clean_after_run"):
                self.ctrl.mark_cases_clean_after_run(str(explicit_case_name))
            if bool(success) and explicit_case_name and manager is not None:
                run_dir = self._run_service.save_case_run(
                    str(explicit_case_name),
                    case_spec,
                    self._last_run_data.get("start_snapshot", {}),
                    self._last_run_data.get("records", []),
                    self._last_run_data.get("status", {}),
                    end_snapshot=self._last_run_data.get("end_snapshot"),
                )
                anim = getattr(self, "animation_tab", None)
                if anim is not None and hasattr(anim, "on_case_run_saved"):
                    anim.on_case_run_saved(str(explicit_case_name))
        except Exception as exc:
            self._report_persistence_error(_tr(self, "save.failed"), exc)

        # Persist an overwriteable "last run" snapshot WITHOUT creating a case.
        # Promoting the last run to a new Case is an explicit user action ("Save run").
        try:
            manager = self._run_manager()
            last_dir = self._run_service.save_last_run(
                case_spec,
                self._last_run_data.get("start_snapshot", {}),
                self._last_run_data.get("records", []),
                self._last_run_data.get("status", {}),
                end_snapshot=self._last_run_data.get("end_snapshot"),
            )
        except Exception as exc:
            self._report_persistence_error(_tr(self, "save.failed"), exc)
        self._last_saved_case_id = None

        self._refresh_run_buttons()
        # Last-run does not create a case; case list remains unchanged.
        if hasattr(self.ctrl, "win") and self.ctrl.win:
            if success:
                message = "Run finished"
            else:
                detail = reason or "failed"
                message = f"Run failed: {detail}"
            self.ctrl.win.statusBar().showMessage(message)

    def _refresh_run_buttons(self) -> None:
        # "Save run" promotes the last run into a brand-new Case.
        self.btn_save_run.setEnabled(bool(getattr(self, "_last_run_data", None)))

    def _record_solver_error(self, solver_name: str, msg: str) -> None:
        if not msg:
            return
        detail = f"{solver_name}: {msg}"
        self._last_solver_error = detail
        if detail not in self._solver_error_log:
            self._solver_error_log.append(detail)

    def _run_analysis_check(self) -> None:
        self.ctrl.commit_drag_if_any()
        self.ctrl.recompute_from_parameters()
        max_err, detail = self.ctrl.max_constraint_error()
        over, over_detail = self.ctrl.check_overconstraint()
        summary_lines = self._format_dof_summary()
        issues = []
        if over:
            issues.append(_tr(self, "analysis.issue.overconstrained").format(detail=over_detail))
        if max_err > 1e-6:
            issues.append(
                _tr(self, "analysis.issue.constraint_error").format(
                    value=max_err,
                    detail=" ".join(f"{k}={v:.4g}" for k, v in detail.items()),
                )
            )
        if not issues:
            issues.append(_tr(self, "analysis.issue.none"))
        message = (
            _tr(self, "analysis.check.summary_title")
            + "\n"
            + "\n".join(summary_lines)
            + "\n\n"
            + _tr(self, "analysis.check.issues_title")
            + "\n"
            + "\n".join(issues)
        )
        QMessageBox.information(self, _tr(self, "analysis.check"), message)

    def _format_dof_summary(self) -> List[str]:
        summaries = self.ctrl.constraint_dof_summary()
        if not summaries:
            return [_tr(self, "analysis.dof.no_points")]
        lines: List[str] = []
        for item in summaries:
            lines.append(
                _tr(self, "analysis.dof.component").format(
                    idx=item["component"],
                    dof=item["dof"],
                    total=item["total"],
                    fixed=item["fixed"],
                    links=item["links"],
                    angles=item["angles"],
                    coincide=item["coincide"],
                    line=item["point_lines"],
                    spline=item["point_splines"],
                    rigid=item["rigid_edges"],
                )
            )
        return lines

    def save_last_run(self) -> None:
        data = getattr(self, "_last_run_data", None)
        if not isinstance(data, dict) or not data:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.no_completed_run_to_save"))
            return
        manager = self._run_manager()
        case_spec = data.get("case_spec") or {}
        # Create a new Case unconditionally (multi-condition workflow).
        try:
            # Naming rule: case name == case id. Do not generate additional names.
            info = manager.create_case(case_spec)
            manager.set_active_case(str(info.name))
            self._run_service.save_case_run(
                str(info.name),
                case_spec,
                data.get("start_snapshot", {}),
                data.get("records", []),
                data.get("status", {}),
                end_snapshot=data.get("end_snapshot"),
            )
        except Exception as exc:
            self._report_persistence_error(_tr(self, "save.failed"), exc)
            return

        self._refresh_run_buttons()
        try:
            if hasattr(self, "animation_tab"):
                self.animation_tab.refresh_cases()
        except Exception:
            pass
        if hasattr(self.ctrl, "win") and self.ctrl.win:
            self.ctrl.win.statusBar().showMessage("Case saved")

    def open_last_run(self) -> None:
        manager = self._run_manager()
        path = manager.last_run_path()
        if not path:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.no_last_run"))
            return
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_active_case_changed(self) -> None:
        self.optimization_tab.refresh_active_case()
        # When switching active case, apply its stored case spec to the Simulation UI
        # so that re-run uses the case-specific sweep/input settings (multi-condition).
        try:
            manager = self._run_manager()
            active_id = manager.get_active_case() if manager else None
            if active_id:
                spec = manager.load_case_spec(active_id) or {}
                if isinstance(spec, dict) and spec:
                    self.apply_case_spec(spec)
        except Exception:
            pass
        # Keep Synthesis mapping in sync when cases change (without overwriting user edits).
        try:
            st = getattr(self, 'synthesis_tab', None)
            if st is not None and hasattr(st, 'sync_from_project'):
                st.sync_from_project(force=False)
        except Exception:
            pass
    # ---- export ----
    def export_csv(self):
        if not self._records:
            QMessageBox.information(self, _tr(self, "export.title"), _tr(self, "run.msg.no_sweep_run_first"))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Sweep CSV", "", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        # gather all columns that appeared
        cols = ["time", "input_deg"]
        extra = []
        for r in self._records:
            for k in r.keys():
                if k not in cols and k not in extra:
                    extra.append(k)
        cols.extend(extra)

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in self._records:
                    w.writerow([r.get(c) for c in cols])
        except Exception as e:
            QMessageBox.critical(self, _tr(self, "export.failed"), str(e))

