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
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QDialog
)

from .analysis_tabs import AnimationTab, OptimizationTab
from .expression_builder import ExpressionBuilderDialog
from .i18n import tr
from ..core.case_run_manager import CaseRunManager
from ..core.expression_service import eval_signal_expression

if TYPE_CHECKING:
    from ..core.controller import SketchController


class SimulationPanel(QWidget):
    def __init__(self, ctrl: "SketchController"):
        super().__init__()
        self.ctrl = ctrl

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
        self.chk_scipy = QCheckBox()
        self.chk_scipy.setChecked(True)
        self.ed_nfev = QLineEdit("250")
        self.ed_nfev.setMaximumWidth(80)
        solver_row.addWidget(self.chk_scipy)
        solver_row.addWidget(self.lbl_step)
        solver_row.addWidget(self.ed_step)
        self.lbl_max_nfev = QLabel()
        solver_row.addWidget(self.lbl_max_nfev)
        solver_row.addWidget(self.ed_nfev)
        self.chk_reset_before_run = QCheckBox()
        self.chk_reset_before_run.setChecked(True)
        solver_row.addWidget(self.chk_reset_before_run)
        self.lbl_actual_solver = QLabel()
        solver_row.addWidget(self.lbl_actual_solver)
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
        self.btn_open_last_run = QPushButton()
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_reset_pose)
        btns.addWidget(self.btn_export)
        btns.addWidget(self.btn_check_analysis)
        btns.addWidget(self.btn_save_run)
        btns.addWidget(self.btn_open_last_run)
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

        meas_buttons = QHBoxLayout()
        self.btn_add_meas_expr = QPushButton()
        self.btn_clear_meas = QPushButton()
        self.btn_delete_meas = QPushButton()
        meas_buttons.addWidget(self.btn_add_meas_expr)
        meas_buttons.addWidget(self.btn_clear_meas)
        meas_buttons.addWidget(self.btn_delete_meas)
        measurements_layout.addLayout(meas_buttons)

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

        load_buttons = QHBoxLayout()
        self.btn_remove_load = QPushButton()
        self.btn_clear_loads = QPushButton()
        load_buttons.addWidget(self.btn_remove_load)
        load_buttons.addWidget(self.btn_clear_loads)
        loads_layout.addLayout(load_buttons)

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

        friction_buttons = QHBoxLayout()
        self.btn_add_friction = QPushButton()
        self.btn_remove_friction = QPushButton()
        self.btn_clear_friction = QPushButton()
        friction_buttons.addWidget(self.btn_add_friction)
        friction_buttons.addWidget(self.btn_remove_friction)
        friction_buttons.addWidget(self.btn_clear_friction)
        friction_layout.addLayout(friction_buttons)
        friction_layout.addStretch(1)

        self.tabs.addTab(loads_tab, "")
        self.tabs.addTab(friction_tab, "")
        self.tabs.addTab(measurements_tab, "")
        self.tabs.addTab(main_tab, "")
        self.animation_tab = AnimationTab(self.ctrl, on_active_case_changed=self._on_active_case_changed)
        self.optimization_tab = OptimizationTab(self.ctrl)
        self.tabs.addTab(self.animation_tab, "")
        self.tabs.addTab(self.optimization_tab, "")
        self.input_fields.extend(getattr(self.optimization_tab, "input_fields", []))

        # Signals
        self.btn_clear_driver.clicked.connect(self._clear_driver)
        self.btn_clear_output.clicked.connect(self._clear_output)
        self.btn_add_meas_expr.clicked.connect(self._add_expression_measurement)
        self.btn_clear_meas.clicked.connect(self._clear_measures)
        self.btn_delete_meas.clicked.connect(self._delete_selected_measure)
        self.btn_check_analysis.clicked.connect(self._run_analysis_check)
        self.btn_remove_load.clicked.connect(self._remove_selected_load)
        self.btn_clear_loads.clicked.connect(self._clear_loads)
        self.btn_add_friction.clicked.connect(self._add_friction_from_selection)
        self.btn_remove_friction.clicked.connect(self._remove_selected_friction)
        self.btn_clear_friction.clicked.connect(self._clear_friction)
        self.btn_play.clicked.connect(self.play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_reset_pose.clicked.connect(self.reset_pose)
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_save_run.clicked.connect(self.save_last_run)
        self.btn_open_last_run.clicked.connect(self.open_last_run)

        self.table_drivers.cellChanged.connect(self._on_driver_table_changed)
        self.table_loads.cellChanged.connect(self._on_load_table_changed)
        self.table_friction.cellChanged.connect(self._on_friction_table_changed)
        self.ed_step.editingFinished.connect(self._on_sweep_field_changed)
        self.chk_scipy.stateChanged.connect(self._on_simulation_settings_changed)
        self.ed_nfev.editingFinished.connect(self._on_simulation_settings_changed)
        self.chk_reset_before_run.stateChanged.connect(self._on_simulation_settings_changed)
        self.apply_sweep_settings(self.ctrl.sweep_settings)
        self.apply_simulation_settings(self.ctrl.simulation_settings)

        self.apply_language()
        self.refresh_labels()
        self._refresh_run_buttons()
        self._set_actual_solver("pbd")

    def apply_language(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self.title.setText(tr(lang, "panel.analysis_title"))
        self.tabs.setTabText(0, tr(lang, "tab.loads"))
        self.tabs.setTabText(1, tr(lang, "tab.friction"))
        self.tabs.setTabText(2, tr(lang, "tab.measurements"))
        self.tabs.setTabText(3, tr(lang, "tab.simulation"))
        self.tabs.setTabText(4, tr(lang, "tab.animation"))
        self.tabs.setTabText(5, tr(lang, "tab.optimization"))
        self.lbl_step.setText(tr(lang, "sim.step_deg"))
        self.lbl_max_nfev.setText(tr(lang, "sim.max_nfev"))
        self.chk_scipy.setText(tr(lang, "sim.use_scipy"))
        self.lbl_driver_sweep.setText(tr(lang, "sim.driver_sweep"))
        self.btn_clear_driver.setText(tr(lang, "sim.clear"))
        self.btn_clear_output.setText(tr(lang, "sim.clear"))
        self.btn_play.setText(tr(lang, "sim.play"))
        self.btn_stop.setText(tr(lang, "sim.stop"))
        self.btn_reset_pose.setText(tr(lang, "sim.reset_pose"))
        self.btn_export.setText(tr(lang, "sim.export_csv"))
        self.btn_save_run.setText(tr(lang, "sim.save_run"))
        self.btn_open_last_run.setText(tr(lang, "sim.open_last_run"))
        self.btn_check_analysis.setText(tr(lang, "analysis.check"))
        self.btn_add_meas_expr.setText(tr(lang, "sim.add_expression_measurement"))
        self.btn_clear_meas.setText(tr(lang, "sim.clear"))
        self.btn_delete_meas.setText(tr(lang, "sim.delete"))
        self.lbl_applied_loads.setText(tr(lang, "sim.applied_loads"))
        self.btn_remove_load.setText(tr(lang, "sim.remove_selected"))
        self.btn_clear_loads.setText(tr(lang, "sim.clear"))
        self.lbl_joint_loads.setText(tr(lang, "sim.joint_loads"))
        self.lbl_friction.setText(tr(lang, "sim.friction_joints"))
        self.btn_add_friction.setText(tr(lang, "button.add_selected"))
        self.btn_remove_friction.setText(tr(lang, "sim.remove_selected"))
        self.btn_clear_friction.setText(tr(lang, "sim.clear"))
        self.chk_reset_before_run.setText(tr(lang, "sim.reset_before_run"))
        self._set_actual_solver(getattr(self, "_actual_solver", "pbd"))
        self.table_meas.setHorizontalHeaderLabels([
            tr(lang, "sim.table.type"),
            tr(lang, "sim.table.measurement"),
            tr(lang, "sim.table.value"),
        ])
        self.table_loads.setHorizontalHeaderLabels([
            tr(lang, "sim.table.point"),
            tr(lang, "sim.table.type"),
            tr(lang, "sim.table.fx"),
            tr(lang, "sim.table.fy"),
            tr(lang, "sim.table.mz"),
            tr(lang, "sim.table.k"),
            tr(lang, "sim.table.load"),
            tr(lang, "sim.table.ref"),
        ])
        self.table_drivers.setHorizontalHeaderLabels([
            tr(lang, "sim.table.driver"),
            tr(lang, "sim.start"),
            tr(lang, "sim.end"),
            tr(lang, "sim.table.value"),
        ])
        self.table_outputs.setHorizontalHeaderLabels([
            tr(lang, "sim.table.output"),
            tr(lang, "sim.table.angle"),
        ])
        self.table_joint_loads.setHorizontalHeaderLabels([
            tr(lang, "sim.table.point"),
            tr(lang, "sim.table.fx"),
            tr(lang, "sim.table.fy"),
            tr(lang, "sim.table.mag"),
        ])
        self.table_friction.setHorizontalHeaderLabels([
            tr(lang, "sim.table.point"),
            tr(lang, "sim.table.mu"),
            tr(lang, "sim.table.diameter"),
            tr(lang, "sim.table.local_load"),
            tr(lang, "sim.table.friction_torque"),
        ])
        if hasattr(self, "animation_tab"):
            self.animation_tab.apply_language()
        if hasattr(self, "optimization_tab"):
            self.optimization_tab.apply_language()
        self.refresh_labels()

    def reset_analysis_state(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._records = []
        self._pending_sim_start_capture = False
        self._run_context = None
        self._run_start_snapshot = None
        self._last_run_data = None
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
        self._refresh_run_buttons()
        self.refresh_labels()

    def _project_dir(self) -> str:
        if getattr(self.ctrl, "win", None) and getattr(self.ctrl.win, "current_file", None):
            project_dir = getattr(self.ctrl.win, "project_dir", None)
            if project_dir:
                return project_dir
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _run_manager(self) -> CaseRunManager:
        project_uuid = getattr(self.ctrl, "project_uuid", "") if self.ctrl else ""
        return CaseRunManager(self._project_dir(), project_uuid=project_uuid)

    def is_running(self) -> bool:
        return self._timer.isActive()

    def has_unsaved_run(self) -> bool:
        return bool(self._last_run_data)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- selection helpers ----
    def _selected_two_points(self) -> Optional[tuple[int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 2:
            lang = getattr(self.ctrl, "ui_language", "en")
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(tr(lang, "status.select_two_points"))
            return None
        return pids[0], pids[1]

    def _selected_three_points(self) -> Optional[tuple[int, int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 3:
            lang = getattr(self.ctrl, "ui_language", "en")
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(tr(lang, "status.select_three_points"))
            return None
        return pids[0], pids[1], pids[2]

    def _selected_one_point(self) -> Optional[int]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 1:
            lang = getattr(self.ctrl, "ui_language", "en")
            if getattr(self.ctrl, "win", None) and self.ctrl.win.statusBar():
                self.ctrl.win.statusBar().showMessage(tr(lang, "status.select_one_point"))
            return None
        return pids[0]

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
            "use_scipy": bool(self.chk_scipy.isChecked()),
            "max_nfev": max_nfev,
            "reset_before_run": bool(self.chk_reset_before_run.isChecked()),
        }

    def apply_simulation_settings(self, settings: Dict[str, Any]) -> None:
        use_scipy = bool(settings.get("use_scipy", True))
        reset_before = bool(settings.get("reset_before_run", True))
        try:
            max_nfev = int(float(settings.get("max_nfev", 250)))
        except Exception:
            max_nfev = 250
        if max_nfev <= 0:
            max_nfev = 250
        self.chk_scipy.setChecked(use_scipy)
        self.ed_nfev.setText(str(max_nfev))
        self.chk_reset_before_run.setChecked(reset_before)
        self._sync_simulation_settings_from_fields()

    def _sync_simulation_settings_from_fields(self) -> None:
        if not hasattr(self.ctrl, "simulation_settings"):
            return
        self.ctrl.simulation_settings = self.get_simulation_settings()

    def _on_simulation_settings_changed(self) -> None:
        self._sync_simulation_settings_from_fields()

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

    def _set_actual_solver(self, solver: str) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        solver_key = "sim.solver.scipy" if solver == "scipy" else "sim.solver.pbd"
        self._actual_solver = solver
        self.lbl_actual_solver.setText(
            tr(lang, "sim.actual_solver").format(solver=tr(lang, solver_key))
        )

    # ---- UI actions ----
    def refresh_labels(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
        outputs = [o for o in self.ctrl.outputs if o.get("enabled")]
        if drivers:
            labels = []
            for d in drivers:
                if d.get("type") == "angle" and d.get("pivot") is not None and d.get("tip") is not None:
                    labels.append(tr(lang, "sim.driver_angle").format(pivot=d["pivot"], tip=d["tip"]))
                elif d.get("type") == "translation":
                    plid = d.get("plid")
                    pl = self.ctrl.point_lines.get(plid, None)
                    if pl:
                        labels.append(tr(lang, "sim.driver_translation").format(p=pl.get("p"), i=pl.get("i"), j=pl.get("j")))
                    else:
                        labels.append(tr(lang, "sim.driver_translation_invalid"))
                else:
                    labels.append(tr(lang, "sim.driver_invalid"))
            if len(labels) == 1:
                self.lbl_driver.setText(labels[0])
            else:
                self.lbl_driver.setText(tr(lang, "sim.driver_multi").format(drivers="; ".join(labels)))
        else:
            if outputs:
                self.lbl_driver.setText(tr(lang, "sim.driver_using_output"))
            else:
                self.lbl_driver.setText(tr(lang, "sim.driver_unset"))

        if outputs:
            labels = []
            for o in outputs:
                if o.get("pivot") is not None and o.get("tip") is not None:
                    labels.append(tr(lang, "sim.output_angle").format(pivot=o["pivot"], tip=o["tip"]))
                else:
                    labels.append(tr(lang, "sim.output_unset"))
            if len(labels) == 1:
                self.lbl_output.setText(labels[0])
            else:
                self.lbl_output.setText(tr(lang, "sim.output_multi").format(outputs="; ".join(labels)))
        else:
            self.lbl_output.setText(tr(lang, "sim.output_unset"))

        self._refresh_driver_table(drivers)
        self._refresh_output_table(outputs)
        self._refresh_load_tables()
        self._refresh_friction_table()
        if hasattr(self, "optimization_tab"):
            self.optimization_tab.refresh_active_case()
            self.optimization_tab.refresh_model_values()

    def _driver_label(self, driver: Dict[str, Any]) -> str:
        lang = getattr(self.ctrl, "ui_language", "en")
        if driver.get("type") == "angle" and driver.get("pivot") is not None and driver.get("tip") is not None:
            return tr(lang, "sim.driver_angle").format(pivot=driver["pivot"], tip=driver["tip"])
        if driver.get("type") == "translation":
            plid = driver.get("plid")
            pl = self.ctrl.point_lines.get(plid, None)
            if pl:
                return tr(lang, "sim.driver_translation").format(p=pl.get("p"), i=pl.get("i"), j=pl.get("j"))
            return tr(lang, "sim.driver_translation_invalid")
        return tr(lang, "sim.driver_invalid")

    def _refresh_driver_table(self, drivers: List[Dict[str, Any]]) -> None:
        values = self.ctrl.get_driver_display_values()
        self.table_drivers.blockSignals(True)
        try:
            self.table_drivers.setRowCount(len(drivers))
            for row, drv in enumerate(drivers):
                label = f"{row + 1}. {self._driver_label(drv)}"
                start_val = drv.get("sweep_start", self.ctrl.sweep_settings.get("start", 0.0))
                end_val = drv.get("sweep_end", self.ctrl.sweep_settings.get("end", 360.0))
                value_val, _unit = values[row] if row < len(values) else (None, "")
                items = [
                    QTableWidgetItem(label),
                    QTableWidgetItem(f"{float(start_val)}"),
                    QTableWidgetItem(f"{float(end_val)}"),
                    QTableWidgetItem("--" if value_val is None else self.ctrl.format_number(value_val)),
                ]
                items[0].setFlags(items[0].flags() & ~Qt.ItemFlag.ItemIsEditable)
                items[3].setFlags(items[3].flags())
                for col, item in enumerate(items):
                    self.table_drivers.setItem(row, col, item)
        finally:
            self.table_drivers.blockSignals(False)

    def _output_label(self, output: Dict[str, Any]) -> str:
        lang = getattr(self.ctrl, "ui_language", "en")
        if output.get("pivot") is not None and output.get("tip") is not None:
            return tr(lang, "sim.output_angle").format(pivot=output["pivot"], tip=output["tip"])
        return tr(lang, "sim.output_unset")

    def _refresh_output_table(self, outputs: List[Dict[str, Any]]) -> None:
        angles = self.ctrl.get_output_angles_deg()
        self.table_outputs.blockSignals(True)
        try:
            self.table_outputs.setRowCount(len(outputs))
            for row, out in enumerate(outputs):
                label = f"{row + 1}. {self._output_label(out)}"
                angle_val = angles[row] if row < len(angles) else None
                items = [
                    QTableWidgetItem(label),
                    QTableWidgetItem("--" if angle_val is None else self.ctrl.format_number(angle_val)),
                ]
                for item in items:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                for col, item in enumerate(items):
                    self.table_outputs.setItem(row, col, item)
        finally:
            self.table_outputs.blockSignals(False)

    def _on_driver_table_changed(self, row: int, col: int) -> None:
        active_drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
        if row < 0 or row >= len(active_drivers):
            return
        if col not in (1, 2, 3):
            return
        item = self.table_drivers.item(row, col)
        if item is None:
            return
        try:
            value = float(item.text())
        except Exception:
            if col == 3:
                QMessageBox.warning(self, "Sweep", "Angle must be numbers.")
            else:
                QMessageBox.warning(self, "Sweep", "Start/End must be numbers.")
            self._refresh_driver_table(active_drivers)
            return
        if col in (1, 2):
            key = "sweep_start" if col == 1 else "sweep_end"
            active_drivers[row][key] = value
            if len(active_drivers) == 1:
                self.ctrl.sweep_settings[key.replace("sweep_", "")] = value
            self.refresh_labels()
            return
        display_vals = [val if val is not None else 0.0 for val, _unit in self.ctrl.get_driver_display_values()]
        if row >= len(display_vals):
            self._refresh_driver_table(active_drivers)
            return
        display_vals[row] = value
        self.ctrl.drive_to_multi_values(display_vals, iters=80)
        self.refresh_labels()

    def _set_driver_from_selection(self):
        pair = self._selected_two_points()
        if not pair:
            return
        pivot, tip = pair
        self.ctrl.set_driver_angle(pivot, tip)
        self.refresh_labels()

    def _clear_driver(self):
        row = self.table_drivers.currentRow()
        if row >= 0:
            active_drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
            if row < len(active_drivers):
                target = active_drivers[row]
                for idx, drv in enumerate(self.ctrl.drivers):
                    if drv is target:
                        del self.ctrl.drivers[idx]
                        break
            self.ctrl._sync_primary_driver()
        else:
            self.ctrl.clear_driver()
        self.refresh_labels()

    def _set_output_from_selection(self):
        pair = self._selected_two_points()
        if not pair:
            return
        pivot, tip = pair
        self.ctrl.set_output(pivot, tip)
        self.refresh_labels()

    def _clear_output(self):
        self.ctrl.clear_output()
        self.refresh_labels()

    def _add_measure_angle_from_selection(self):
        pair = self._selected_two_points()
        if not pair:
            return
        pivot, tip = pair
        self.ctrl.add_measure_angle(pivot, tip)
        self.refresh_labels()

    def _add_measure_joint_from_selection(self):
        tri = self._selected_three_points()
        if not tri:
            return
        i, j, k = tri
        self.ctrl.add_measure_joint(i, j, k)
        self.refresh_labels()

    def _measurement_expression_functions(self) -> Dict[str, List[str]]:
        return {
            "Functions": ["max(", "min(", "mean(", "rms(", "abs(", "first(", "last("],
            "Operators": ["+", "-", "*", "/", "(", ")", ","],
        }

    def _measurement_expression_tokens(self) -> Dict[str, List[str]]:
        measurements = [name for name, _val, _unit in self.ctrl.get_measure_values()]
        load_measures = [name for name, _val in self.ctrl.get_load_measure_values()]
        groups: Dict[str, List[str]] = {}
        if measurements:
            groups["Measurements"] = sorted({str(item) for item in measurements if str(item).strip()})
        if load_measures:
            groups["Load Measurements"] = sorted({str(item) for item in load_measures if str(item).strip()})
        return groups

    def _measurement_expression_signals(self) -> Dict[str, float]:
        signals: Dict[str, float] = {}
        for nm, val, _unit in self.ctrl.get_measure_values():
            if nm and val is not None:
                signals[str(nm)] = float(val)
        for nm, val in self.ctrl.get_load_measure_values():
            if nm and val is not None:
                signals[str(nm)] = float(val)
        return signals

    def _add_expression_measurement(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        signals = self._measurement_expression_signals()
        token_groups = self._measurement_expression_tokens()
        tokens: Any = token_groups if token_groups else []
        dialog = ExpressionBuilderDialog(
            self,
            initial="",
            tokens=tokens,
            functions=self._measurement_expression_functions(),
            evaluator=lambda expr: eval_signal_expression(expr, signals),
            title=tr(lang, "analysis.expression_builder"),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expr = dialog.expression().strip()
        if not expr:
            return
        name, ok = QInputDialog.getText(
            self,
            tr(lang, "sim.measure_expression_title"),
            tr(lang, "sim.measure_expression_name"),
            text=expr,
        )
        if not ok or not name.strip():
            return
        unit, ok = QInputDialog.getText(
            self,
            tr(lang, "sim.measure_expression_title"),
            tr(lang, "sim.measure_expression_unit"),
            text="",
        )
        if not ok:
            return
        self.ctrl.add_measure_expression(name.strip(), expr, unit.strip())
        self.refresh_labels()

    def _clear_measures(self):
        self.ctrl.clear_measures()
        self.refresh_labels()

    def _delete_selected_measure(self):
        row = self.table_meas.currentRow()
        if row < 0:
            QMessageBox.information(self, "Measurements", "Select a measurement row to delete.")
            return
        if row >= len(self._measure_row_map):
            QMessageBox.information(self, "Measurements", "Select a measurement row to delete.")
            return
        row_info = self._measure_row_map[row]
        if row_info["kind"] == "measure":
            self.ctrl.remove_measure_at(row_info["index"])
        elif row_info["kind"] == "load":
            self.ctrl.remove_load_measure_at(row_info["index"])
        elif row_info["kind"] == "point_line":
            QMessageBox.information(self, "Measurements", "Point-on-line (s) measurements are tied to constraints.")
        self.refresh_labels()

    def _refresh_measure_table(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        all_measures = self.ctrl.get_measure_values()
        mv = [(nm, val, unit) for (nm, val, unit) in all_measures if unit == "deg"]
        mv_line = [(nm, val, unit) for (nm, val, unit) in all_measures if unit != "deg"]
        load_mv = self.ctrl.get_load_measure_values()
        self._measure_row_map = []
        total_rows = len(mv) + len(mv_line) + len(load_mv)
        self.table_meas.setRowCount(total_rows)
        row = 0
        for index, (nm, val, unit) in enumerate(mv):
            type_item = QTableWidgetItem(tr(lang, "sim.measurement"))
            name_item = QTableWidgetItem(str(nm))
            if val is None:
                value_text = "--"
            elif unit == "deg":
                value_text = f"{self.ctrl.format_number(val)}°"
            else:
                value_text = f"{self.ctrl.format_number(val)} {unit}"
            value_item = QTableWidgetItem(value_text)
            for item in (type_item, name_item, value_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_meas.setItem(row, 0, type_item)
            self.table_meas.setItem(row, 1, name_item)
            self.table_meas.setItem(row, 2, value_item)
            self._measure_row_map.append({"kind": "measure", "index": index})
            row += 1
        for index, (nm, val, unit) in enumerate(mv_line):
            type_item = QTableWidgetItem(tr(lang, "sim.measurement"))
            name_item = QTableWidgetItem(str(nm))
            value_item = QTableWidgetItem("--" if val is None else f"{self.ctrl.format_number(val)} {unit}")
            for item in (type_item, name_item, value_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_meas.setItem(row, 0, type_item)
            self.table_meas.setItem(row, 1, name_item)
            self.table_meas.setItem(row, 2, value_item)
            self._measure_row_map.append({"kind": "point_line", "index": index})
            row += 1
        for index, (nm, val) in enumerate(load_mv):
            type_item = QTableWidgetItem(tr(lang, "sim.load"))
            name_item = QTableWidgetItem(str(nm))
            value_item = QTableWidgetItem("--" if val is None else self.ctrl.format_number(val))
            for item in (type_item, name_item, value_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_meas.setItem(row, 0, type_item)
            self.table_meas.setItem(row, 1, name_item)
            self.table_meas.setItem(row, 2, value_item)
            self._measure_row_map.append({"kind": "load", "index": index})
            row += 1

    def _add_force_from_selection(self):
        pid = self._selected_one_point()
        if pid is None:
            return
        fx, ok = QInputDialog.getDouble(
            self,
            "Force X",
            "Fx",
            0.0,
            decimals=int(self.ctrl.display_precision),
        )
        if not ok:
            return
        fy, ok = QInputDialog.getDouble(
            self,
            "Force Y",
            "Fy",
            0.0,
            decimals=int(self.ctrl.display_precision),
        )
        if not ok:
            return
        self.ctrl.add_load_force(pid, fx, fy)
        self.refresh_labels()

    def _add_torque_from_selection(self):
        pid = self._selected_one_point()
        if pid is None:
            return
        mz, ok = QInputDialog.getDouble(
            self,
            "Torque",
            "Mz (out-of-plane)",
            0.0,
            decimals=int(self.ctrl.display_precision),
        )
        if not ok:
            return
        self.ctrl.add_load_torque(pid, mz)
        self.refresh_labels()

    def _clear_loads(self):
        self.ctrl.clear_loads()
        self.refresh_labels()

    def _remove_selected_load(self):
        row = self.table_loads.currentRow()
        if row < 0:
            QMessageBox.information(self, "Loads", "Select a load row to remove.")
            return
        self.ctrl.remove_load_at(row)
        self.refresh_labels()

    def _add_friction_from_selection(self):
        pid = self._selected_one_point()
        if pid is None:
            return
        self.ctrl.add_friction_joint(pid, 0.0, 0.0)
        self.refresh_labels()

    def _clear_friction(self):
        self.ctrl.clear_friction_joints()
        self.refresh_labels()

    def _remove_selected_friction(self):
        row = self.table_friction.currentRow()
        if row < 0:
            QMessageBox.information(self, "Friction", "Select a friction row to remove.")
            return
        self.ctrl.remove_friction_joint_at(row)
        self.refresh_labels()

    def _on_load_table_changed(self, row: int, col: int) -> None:
        if col not in (2, 3, 4, 5, 6, 7):
            return
        if row < 0 or row >= len(self.ctrl.loads):
            return
        item = self.table_loads.item(row, col)
        if item is None:
            return
        load = self.ctrl.loads[row]
        ltype = str(load.get("type", "force")).lower()
        if col in (2, 3, 4) and ltype in ("force", "torque"):
            key_map = {
                2: ("fx", "fx_expr"),
                3: ("fy", "fy_expr"),
                4: ("mz", "mz_expr"),
            }
            key_num, key_expr = key_map.get(col, ("", ""))
            if not key_num:
                return
            raw = item.text().strip()
            try:
                value = float(raw)
            except ValueError:
                if not raw:
                    self._refresh_load_tables()
                    return
                self.ctrl.loads[row][key_expr] = raw
                self.ctrl.recompute_from_parameters()
            else:
                self.ctrl.loads[row][key_num] = value
                self.ctrl.loads[row][key_expr] = ""
        elif col == 5 and ltype in ("spring", "torsion_spring"):
            raw = item.text().strip()
            try:
                value = float(raw)
            except ValueError:
                if not raw:
                    self._refresh_load_tables()
                    return
                self.ctrl.loads[row]["k_expr"] = raw
                self.ctrl.recompute_from_parameters()
            else:
                self.ctrl.loads[row]["k"] = value
                self.ctrl.loads[row]["k_expr"] = ""
        elif col == 6 and ltype in ("spring", "torsion_spring"):
            raw = item.text().strip()
            try:
                value = float(raw)
            except ValueError:
                if not raw:
                    self._refresh_load_tables()
                    return
                self.ctrl.loads[row]["load_expr"] = raw
                self.ctrl.recompute_from_parameters()
            else:
                self.ctrl.loads[row]["load"] = value
                self.ctrl.loads[row]["load_expr"] = ""
        elif col == 7 and ltype in ("spring", "torsion_spring"):
            try:
                raw = item.text().strip()
                if raw.lower().startswith("p"):
                    raw = raw[1:]
                value = int(raw)
            except ValueError:
                self._refresh_load_tables()
                return
            if value not in self.ctrl.points:
                self._refresh_load_tables()
                return
            self.ctrl.loads[row]["ref_pid"] = value
            if ltype == "torsion_spring":
                theta0 = self.ctrl.get_angle_rad(int(load.get("pid", -1)), value)
                if theta0 is not None:
                    self.ctrl.loads[row]["theta0"] = float(theta0)
        else:
            return
        self.refresh_labels()

    def _on_friction_table_changed(self, row: int, col: int) -> None:
        if col not in (1, 2):
            return
        if row < 0 or row >= len(self.ctrl.friction_joints):
            return
        item = self.table_friction.item(row, col)
        if item is None:
            return
        raw = item.text().strip()
        key_map = {
            1: ("mu", "mu_expr"),
            2: ("diameter", "diameter_expr"),
        }
        key_num, key_expr = key_map.get(col, ("", ""))
        if not key_num:
            return
        try:
            value = float(raw)
        except ValueError:
            if not raw:
                self._refresh_friction_table()
                return
            self.ctrl.friction_joints[row][key_expr] = raw
            self.ctrl.recompute_from_parameters()
        else:
            self.ctrl.friction_joints[row][key_num] = value
            self.ctrl.friction_joints[row][key_expr] = ""
        self.refresh_labels()

    def _refresh_load_tables(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        loads = list(self.ctrl.loads)
        self.table_loads.blockSignals(True)
        try:
            self.table_loads.setRowCount(len(loads))
            for row, ld in enumerate(loads):
                pid = ld.get("pid", "--")
                ltype = str(ld.get("type", "force"))
                fx, fy, mz = self.ctrl._resolve_load_components(ld)
                k = ld.get("k", "")
                preload = ld.get("load", "")
                ref_pid = ld.get("ref_pid", "")
                fx_expr = str(ld.get("fx_expr", "") or "")
                fy_expr = str(ld.get("fy_expr", "") or "")
                mz_expr = str(ld.get("mz_expr", "") or "")
                k_expr = str(ld.get("k_expr", "") or "")
                load_expr = str(ld.get("load_expr", "") or "")
                items = [
                    QTableWidgetItem(f"P{pid}" if isinstance(pid, int) else str(pid)),
                    QTableWidgetItem(ltype),
                    QTableWidgetItem(fx_expr if fx_expr else self.ctrl.format_number(fx)),
                    QTableWidgetItem(fy_expr if fy_expr else self.ctrl.format_number(fy)),
                    QTableWidgetItem(mz_expr if mz_expr else self.ctrl.format_number(mz)),
                    QTableWidgetItem(k_expr if k_expr else ("" if k == "" else self.ctrl.format_number(k))),
                    QTableWidgetItem(load_expr if load_expr else ("" if preload == "" else self.ctrl.format_number(preload))),
                    QTableWidgetItem("" if ref_pid == "" else f"P{ref_pid}"),
                ]
                for col, item in enumerate(items):
                    if col in (0, 1):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    elif ltype.lower() in ("force", "torque") and col in (5, 6, 7):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    elif ltype.lower() not in ("force", "torque") and col in (2, 3, 4):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table_loads.setItem(row, col, item)
        finally:
            self.table_loads.blockSignals(False)

        joint_loads, qs = self.ctrl.compute_quasistatic_report()

        mode = qs.get("mode", "--")
        self.lbl_qs_mode.setText(tr(lang, "sim.quasi_static").format(mode=mode))

        tau_in = qs.get("tau_input", None)
        tau_out = qs.get("tau_output", None)
        if tau_in is None:
            self.lbl_tau_in.setText(tr(lang, "sim.input_tau_none"))
        else:
            self.lbl_tau_in.setText(tr(lang, "sim.input_tau").format(value=self.ctrl.format_number(tau_in)))
        if tau_out is None:
            self.lbl_tau_out.setText(tr(lang, "sim.output_tau_none"))
        else:
            self.lbl_tau_out.setText(tr(lang, "sim.output_tau").format(value=self.ctrl.format_number(tau_out)))

        self.table_joint_loads.setRowCount(len(joint_loads))
        for row, jl in enumerate(joint_loads):
            items = [
                QTableWidgetItem(f"P{jl.get('pid')}"),
                QTableWidgetItem(self.ctrl.format_number(jl.get("fx", 0.0))),
                QTableWidgetItem(self.ctrl.format_number(jl.get("fy", 0.0))),
                QTableWidgetItem(self.ctrl.format_number(jl.get("mag", 0.0))),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_joint_loads.setItem(row, col, item)

        self._refresh_measure_table()

    def _refresh_friction_table(self) -> None:
        rows = self.ctrl.get_friction_table()
        self.table_friction.blockSignals(True)
        try:
            self.table_friction.setRowCount(len(rows))
            for row, entry in enumerate(rows):
                pid = entry.get("pid", "--")
                mu = entry.get("mu", 0.0)
                diameter = entry.get("diameter", 0.0)
                mu_expr = entry.get("mu_expr", "")
                diameter_expr = entry.get("diameter_expr", "")
                local_load = entry.get("local_load", None)
                torque = entry.get("torque", None)
                items = [
                    QTableWidgetItem(f"P{pid}" if isinstance(pid, int) else str(pid)),
                    QTableWidgetItem(mu_expr if mu_expr else self.ctrl.format_number(mu)),
                    QTableWidgetItem(diameter_expr if diameter_expr else self.ctrl.format_number(diameter)),
                    QTableWidgetItem("--" if local_load is None else self.ctrl.format_number(local_load)),
                    QTableWidgetItem("--" if torque is None else self.ctrl.format_number(torque)),
                ]
                for col, item in enumerate(items):
                    if col in (0, 3, 4):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table_friction.setItem(row, col, item)
        finally:
            self.table_friction.blockSignals(False)
    # ---- sweep ----
    def play(self):
        if not self.ctrl.drivers and not self.ctrl.outputs:
            QMessageBox.information(self, "Driver", "Set a driver or output first.")
            return
        if hasattr(self, "chk_reset_before_run") and self.chk_reset_before_run.isChecked():
            if self.ctrl.reset_pose_to_sim_start():
                self.ctrl.update_graphics()
                if self.ctrl.panel:
                    self.ctrl.panel.defer_refresh_all(keep_selection=True)
        try:
            step = float(self.ed_step.text())
        except ValueError:
            QMessageBox.warning(self, "Sweep", "Step must be numbers.")
            return
        step = int(round(abs(step)))
        if step <= 0:
            QMessageBox.warning(self, "Sweep", "Step must be greater than 0.")
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

        case_spec = self._build_case_spec()
        self._run_context = {
            "started_utc": self._utc_now(),
            "start_time": time.time(),
            "case_spec": case_spec,
        }
        self._refresh_run_buttons()

        # Do one immediate tick for responsiveness
        self._on_tick()
        self._timer.start(15)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        if self._run_context is not None:
            self._complete_run(success=False, reason="stopped")

    def reset_pose(self):
        self.stop()
        ok = self.ctrl.reset_pose_to_sim_start()
        if not ok:
            QMessageBox.information(self, "Reset", "No start pose captured yet. Press Run once first.")
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



    def _on_tick(self):
        if self._sweep_reached_end():
            self._finalize_end_pose()
            self._complete_run(success=True, reason="completed")
            self.refresh_labels()
            return

        ok = True
        step_applied = False
        msg = ""
        has_point_spline = any(
            ps.get("enabled", True)
            for ps in getattr(self.ctrl, "point_splines", {}).values()
        )
        iters = 200 if has_point_spline else 80
        base_step = self._theta_step
        step_target = self._theta_step_cur
        theta_target = self._theta_last_ok + step_target
        actual_solver = "pbd"
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
        while True:
            pose_before = self.ctrl.snapshot_points()
            has_non_angle_driver = any(d.get("type") != "angle" for d in self.ctrl._active_drivers())
            if hasattr(self, "chk_scipy") and self.chk_scipy.isChecked() and not has_point_spline:
                try:
                    nfev = int(float(self.ed_nfev.text() or "250"))
                except Exception:
                    nfev = 250
                if self._driver_sweep:
                    if has_non_angle_driver:
                        self.ctrl.drive_to_multi_values(driver_targets, iters=iters)
                        ok, msg = True, ""
                        actual_solver = "pbd"
                    else:
                        ok, msg = self.ctrl.drive_to_multi_deg_scipy(driver_targets, max_nfev=nfev)
                        actual_solver = "scipy" if ok else "pbd"
                else:
                    ok, msg = self.ctrl.drive_to_deg_scipy(theta_target, max_nfev=nfev)
                    actual_solver = "scipy" if ok else "pbd"
                if not ok:
                    self.ctrl.apply_points_snapshot(pose_before)
                    # Fallback to PBD so the UI stays responsive
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
        self._set_actual_solver(actual_solver)
        self.refresh_labels()

        hard_err_value = None
        try:
            _max_err, detail = self.ctrl.max_constraint_error()
            hard_err_value = max(
                detail.get("length", 0.0),
                detail.get("angle", 0.0),
                detail.get("coincide", 0.0),
                detail.get("point_line", 0.0),
                detail.get("point_spline", 0.0),
            )
        except Exception:
            hard_err_value = None

        rec: Dict[str, Any] = {
            "time": self._frame,
            "solver": actual_solver,
            "success": ok,
            "input_deg": self.ctrl.get_input_angle_deg(),
            "output_deg": self.ctrl.get_output_angle_deg(),
            "driver_deg": list(self.ctrl.get_driver_angles_deg()),
        }
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
        has_point_spline = any(
            ps.get("enabled", True)
            for ps in getattr(self.ctrl, "point_splines", {}).values()
        )
        iters = 200 if has_point_spline else 80
        if hasattr(self, "chk_scipy") and self.chk_scipy.isChecked() and not has_point_spline:
            try:
                nfev = int(float(self.ed_nfev.text() or "250"))
            except Exception:
                nfev = 250
        else:
            nfev = None

        if self._driver_sweep:
            targets = [float(entry.get("end", last_ok)) for last_ok, entry in zip(self._driver_last_ok, self._driver_sweep)]
            has_non_angle_driver = any(d.get("type") != "angle" for d in self.ctrl._active_drivers())
            if nfev is not None:
                if has_non_angle_driver:
                    self.ctrl.drive_to_multi_values(targets, iters=iters)
                else:
                    ok, _msg = self.ctrl.drive_to_multi_deg_scipy(targets, max_nfev=nfev)
                    if not ok:
                        self.ctrl.drive_to_multi_deg(targets, iters=iters)
            else:
                if has_non_angle_driver:
                    self.ctrl.drive_to_multi_values(targets, iters=iters)
                else:
                    self.ctrl.drive_to_multi_deg(targets, iters=iters)
            self._driver_last_ok = list(targets)
        else:
            target = float(self._theta_end)
            if nfev is not None:
                ok, _msg = self.ctrl.drive_to_deg_scipy(target, max_nfev=nfev)
                if not ok:
                    self.ctrl.drive_to_deg(target, iters=iters)
            else:
                self.ctrl.drive_to_deg(target, iters=iters)
            self._theta_last_ok = target
            self._theta_deg = target
        self.ctrl.append_trajectories()

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
        return {
            "schema_version": "1.0",
            "analysis_mode": "quasi_static",
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
            },
            "solver": {
                "use_scipy": bool(self.chk_scipy.isChecked()),
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

    def _complete_run(self, success: bool, reason: str) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if not self._run_context:
            return
        start_time = self._run_context.get("start_time", time.time())
        elapsed = max(0.0, time.time() - float(start_time))
        status = {
            "success": bool(success),
            "elapsed_sec": elapsed,
            "reason": reason,
            "started_utc": self._run_context.get("started_utc"),
            "finished_utc": self._utc_now(),
        }
        case_spec = self._run_context.get("case_spec", {})
        end_snapshot = self.ctrl.snapshot_model()
        self._last_run_data = {
            "case_spec": case_spec,
            "start_snapshot": self._run_start_snapshot or end_snapshot,
            "end_snapshot": end_snapshot,
            "records": list(self._records),
            "status": status,
        }
        self._run_context = None
        self._refresh_run_buttons()
        if hasattr(self.ctrl, "win") and self.ctrl.win:
            self.ctrl.win.statusBar().showMessage("Run finished (not saved)")

    def _refresh_run_buttons(self) -> None:
        manager = self._run_manager()
        self.btn_open_last_run.setEnabled(bool(manager.last_run_path()))
        self.btn_save_run.setEnabled(bool(self._last_run_data))

    def _run_analysis_check(self) -> None:
        self.ctrl.commit_drag_if_any()
        self.ctrl.recompute_from_parameters()
        max_err, detail = self.ctrl.max_constraint_error()
        over, over_detail = self.ctrl.check_overconstraint()
        summary_lines = self._format_dof_summary()
        issues = []
        lang = getattr(self.ctrl, "ui_language", "en")
        if over:
            issues.append(tr(lang, "analysis.issue.overconstrained").format(detail=over_detail))
        if max_err > 1e-6:
            issues.append(
                tr(lang, "analysis.issue.constraint_error").format(
                    value=max_err,
                    detail=" ".join(f"{k}={v:.4g}" for k, v in detail.items()),
                )
            )
        if not issues:
            issues.append(tr(lang, "analysis.issue.none"))
        message = (
            tr(lang, "analysis.check.summary_title")
            + "\n"
            + "\n".join(summary_lines)
            + "\n\n"
            + tr(lang, "analysis.check.issues_title")
            + "\n"
            + "\n".join(issues)
        )
        QMessageBox.information(self, tr(lang, "analysis.check"), message)

    def _format_dof_summary(self) -> List[str]:
        summaries = self.ctrl.constraint_dof_summary()
        lang = getattr(self.ctrl, "ui_language", "en")
        if not summaries:
            return [tr(lang, "analysis.dof.no_points")]
        lines: List[str] = []
        for item in summaries:
            lines.append(
                tr(lang, "analysis.dof.component").format(
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
        if not self._last_run_data:
            QMessageBox.information(self, "Run", "No completed run to save yet.")
            return
        manager = self._run_manager()
        payload = self._last_run_data
        manager.save_run(
            payload.get("case_spec", {}),
            payload.get("start_snapshot", {}),
            payload.get("records", []),
            payload.get("status", {}),
            end_snapshot=payload.get("end_snapshot"),
        )
        self._last_run_data = None
        self._refresh_run_buttons()
        if hasattr(self, "animation_tab"):
            self.animation_tab.refresh_cases()
        if hasattr(self.ctrl, "win") and self.ctrl.win:
            self.ctrl.win.statusBar().showMessage("Run saved")

    def open_last_run(self) -> None:
        manager = self._run_manager()
        path = manager.last_run_path()
        if not path:
            QMessageBox.information(self, "Run", "No last run available.")
            return
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_active_case_changed(self) -> None:
        self.optimization_tab.refresh_active_case()
    # ---- export ----
    def export_csv(self):
        if not self._records:
            QMessageBox.information(self, "Export", "No sweep data yet. Run first.")
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
            QMessageBox.critical(self, "Export failed", str(e))
