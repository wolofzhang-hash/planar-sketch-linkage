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
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog
)

from .analysis_tabs import AnimationTab, OptimizationTab
from ..core.case_run_manager import CaseRunManager

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
        self._theta_last_ok = 0.0
        self._frame = 0

        self._records: List[Dict[str, Any]] = []
        self._pending_sim_start_capture = False
        self._run_context: Optional[Dict[str, Any]] = None
        self._run_start_snapshot: Optional[Dict[str, Any]] = None
        self._last_run_data: Optional[Dict[str, Any]] = None

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        # Driver
        row = QHBoxLayout()
        self.lbl_driver = QLabel("Driver: (not set)")
        self.btn_clear_driver = QPushButton("Clear")
        row.addWidget(self.lbl_driver, 1)
        row.addWidget(self.btn_clear_driver)
        main_layout.addLayout(row)

        # Output
        out_row = QHBoxLayout()
        self.lbl_output = QLabel("Output: (not set)")
        self.btn_clear_output = QPushButton("Clear")
        out_row.addWidget(self.lbl_output, 1)
        out_row.addWidget(self.btn_clear_output)
        main_layout.addLayout(out_row)

        # Current
        self.lbl_angles = QLabel("Input: --")
        main_layout.addWidget(self.lbl_angles)

        # Sweep controls
        sweep = QHBoxLayout()
        self.ed_start = QLineEdit("0")
        self.ed_end = QLineEdit("360")
        self.ed_step = QLineEdit("2")
        sweep.addWidget(QLabel("Start°"))
        sweep.addWidget(self.ed_start)
        sweep.addWidget(QLabel("End°"))
        sweep.addWidget(self.ed_end)
        sweep.addWidget(QLabel("Step°"))
        sweep.addWidget(self.ed_step)
        main_layout.addLayout(sweep)

        # Solver backend
        solver_row = QHBoxLayout()
        self.chk_scipy = QCheckBox("Use SciPy (accurate)")
        self.chk_scipy.setChecked(True)
        self.ed_nfev = QLineEdit("250")
        self.ed_nfev.setMaximumWidth(80)
        solver_row.addWidget(self.chk_scipy)
        solver_row.addWidget(QLabel("MaxNfev"))
        solver_row.addWidget(self.ed_nfev)
        solver_row.addStretch(1)
        main_layout.addLayout(solver_row)

        # Buttons
        btns = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_stop = QPushButton("Stop")
        self.btn_reset_pose = QPushButton("Reset Pose")
        self.btn_export = QPushButton("Export CSV (full sweep)")
        self.btn_save_run = QPushButton("Save Run")
        self.btn_open_last_run = QPushButton("Open Last Run")
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_reset_pose)
        btns.addWidget(self.btn_export)
        btns.addWidget(self.btn_save_run)
        btns.addWidget(self.btn_open_last_run)
        main_layout.addLayout(btns)

        main_layout.addStretch(1)

        measurements_tab = QWidget()
        measurements_layout = QVBoxLayout(measurements_tab)
        self.table_meas = QTableWidget(0, 3)
        self.table_meas.setHorizontalHeaderLabels(["Type", "Measurement", "Value"])
        self.table_meas.verticalHeader().setVisible(False)
        self.table_meas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_meas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_meas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_meas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        measurements_layout.addWidget(self.table_meas)
        self._measure_row_map: List[Dict[str, Any]] = []

        meas_buttons = QHBoxLayout()
        self.btn_clear_meas = QPushButton("Clear")
        self.btn_delete_meas = QPushButton("Delete")
        meas_buttons.addWidget(self.btn_clear_meas)
        meas_buttons.addWidget(self.btn_delete_meas)
        measurements_layout.addLayout(meas_buttons)

        measurements_layout.addStretch(1)
        loads_tab = QWidget()
        loads_layout = QVBoxLayout(loads_tab)

        self.table_loads = QTableWidget(0, 5)
        self.table_loads.setHorizontalHeaderLabels(["Point", "Type", "Fx", "Fy", "Mz"])
        self.table_loads.verticalHeader().setVisible(False)
        self.table_loads.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_loads.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_loads.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        loads_layout.addWidget(QLabel("Applied Loads"))
        loads_layout.addWidget(self.table_loads)

        load_buttons = QHBoxLayout()
        self.btn_remove_load = QPushButton("Remove Selected")
        self.btn_clear_loads = QPushButton("Clear")
        load_buttons.addWidget(self.btn_remove_load)
        load_buttons.addWidget(self.btn_clear_loads)
        loads_layout.addLayout(load_buttons)

        # Quasi-static summary (torques)
        qs_info = QHBoxLayout()
        self.lbl_qs_mode = QLabel("Quasi-static: --")
        self.lbl_tau_in = QLabel("Input τ: --")
        self.lbl_tau_out = QLabel("Output τ: --")
        qs_info.addWidget(self.lbl_qs_mode)
        qs_info.addWidget(self.lbl_tau_in)
        qs_info.addWidget(self.lbl_tau_out)
        loads_layout.addLayout(qs_info)

        # Quasi-static joint loads (passive constraints only; actuator/closure torque reported separately)
        self.table_joint_loads = QTableWidget(0, 4)
        self.table_joint_loads.setHorizontalHeaderLabels(["Point", "Fx", "Fy", "Mag"])
        self.table_joint_loads.verticalHeader().setVisible(False)
        self.table_joint_loads.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_joint_loads.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_joint_loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        loads_layout.addWidget(QLabel("Joint Loads (Quasi-static)"))
        loads_layout.addWidget(self.table_joint_loads)

        loads_layout.addStretch(1)

        tabs.addTab(loads_tab, "Loads")
        tabs.addTab(measurements_tab, "Measurements")
        tabs.addTab(main_tab, "Simulation")
        self.animation_tab = AnimationTab(self.ctrl, on_active_case_changed=self._on_active_case_changed)
        self.optimization_tab = OptimizationTab(self.ctrl)
        tabs.addTab(self.animation_tab, "Animation")
        tabs.addTab(self.optimization_tab, "Optimization")

        # Signals
        self.btn_clear_driver.clicked.connect(self._clear_driver)
        self.btn_clear_output.clicked.connect(self._clear_output)
        self.btn_clear_meas.clicked.connect(self._clear_measures)
        self.btn_delete_meas.clicked.connect(self._delete_selected_measure)
        self.btn_remove_load.clicked.connect(self._remove_selected_load)
        self.btn_clear_loads.clicked.connect(self._clear_loads)
        self.btn_play.clicked.connect(self.play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_reset_pose.clicked.connect(self.reset_pose)
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_save_run.clicked.connect(self.save_last_run)
        self.btn_open_last_run.clicked.connect(self.open_last_run)

        self.ed_start.editingFinished.connect(self._on_sweep_field_changed)
        self.ed_end.editingFinished.connect(self._on_sweep_field_changed)
        self.ed_step.editingFinished.connect(self._on_sweep_field_changed)
        self.apply_sweep_settings(self.ctrl.sweep_settings)

        self.refresh_labels()
        self._refresh_run_buttons()

    def _project_dir(self) -> str:
        if getattr(self.ctrl, "win", None) and getattr(self.ctrl.win, "current_file", None):
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _run_manager(self) -> CaseRunManager:
        return CaseRunManager(self._project_dir())

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- selection helpers ----
    def _selected_two_points(self) -> Optional[tuple[int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 2:
            QMessageBox.information(self, "Selection", "Please select exactly 2 points (Ctrl+Click).")
            return None
        return pids[0], pids[1]

    def _selected_three_points(self) -> Optional[tuple[int, int, int]]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 3:
            QMessageBox.information(self, "Selection", "Please select exactly 3 points (Ctrl+Click).")
            return None
        return pids[0], pids[1], pids[2]

    def _selected_one_point(self) -> Optional[int]:
        pids = sorted(list(self.ctrl.selected_point_ids))
        if len(pids) != 1:
            QMessageBox.information(self, "Selection", "Please select exactly 1 point (Ctrl+Click).")
            return None
        return pids[0]

    def apply_sweep_settings(self, settings: Dict[str, float]) -> None:
        self.ed_start.setText(f"{float(settings.get('start', 0.0))}")
        self.ed_end.setText(f"{float(settings.get('end', 360.0))}")
        self.ed_step.setText(f"{float(settings.get('step', 2.0))}")

    def _sync_sweep_settings_from_fields(self) -> None:
        try:
            start = float(self.ed_start.text())
            end = float(self.ed_end.text())
            step = float(self.ed_step.text())
        except Exception:
            return
        step = abs(step)
        if step == 0:
            step = float(self.ctrl.sweep_settings.get("step", 2.0)) or 2.0
        self.ctrl.sweep_settings = {"start": start, "end": end, "step": step}
        self.ed_step.setText(f"{step}")

    def _on_sweep_field_changed(self) -> None:
        self._sync_sweep_settings_from_fields()

    # ---- UI actions ----
    def refresh_labels(self):
        d = self.ctrl.driver
        if d.get("enabled"):
            if d.get("type") == "joint" and d.get("i") is not None and d.get("j") is not None and d.get("k") is not None:
                self.lbl_driver.setText(f"Driver: joint P{d['i']}-P{d['j']}-P{d['k']}")
            elif d.get("pivot") is not None and d.get("tip") is not None:
                self.lbl_driver.setText(f"Driver: vector P{d['pivot']} -> P{d['tip']}")
            else:
                self.lbl_driver.setText("Driver: (invalid)")
        else:
            if self.ctrl.output.get("enabled"):
                self.lbl_driver.setText("Driver: (using Output)")
            else:
                self.lbl_driver.setText("Driver: (not set)")

        o = self.ctrl.output
        if o.get("enabled") and o.get("pivot") is not None and o.get("tip") is not None:
            self.lbl_output.setText(f"Output: vector P{o['pivot']} -> P{o['tip']}")
        else:
            self.lbl_output.setText("Output: (not set)")

        o = self.ctrl.output
        if o.get("enabled") and o.get("pivot") is not None and o.get("tip") is not None:
            self.lbl_output.setText(f"Output: vector P{o['pivot']} -> P{o['tip']}")
        else:
            self.lbl_output.setText("Output: (not set)")

        a_in = self.ctrl.get_input_angle_deg()
        a_out = self.ctrl.get_output_angle_deg()
        s_in = "--" if a_in is None else self.ctrl.format_number(a_in)
        s_out = "--" if a_out is None else self.ctrl.format_number(a_out)
        self.lbl_angles.setText(f"Input: {s_in}° | Output: {s_out}°")
        self._refresh_load_tables()
        if hasattr(self, "optimization_tab"):
            self.optimization_tab.refresh_active_case()

    def _set_driver_from_selection(self):
        pair = self._selected_two_points()
        if not pair:
            return
        pivot, tip = pair
        self.ctrl.set_driver(pivot, tip)
        self.refresh_labels()

    def _set_driver_joint_from_selection(self):
        tri = self._selected_three_points()
        if not tri:
            return
        i, j, k = tri
        self.ctrl.set_driver_joint(i, j, k)
        self.refresh_labels()

    def _clear_driver(self):
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

    def _add_measure_vector_from_selection(self):
        pair = self._selected_two_points()
        if not pair:
            return
        pivot, tip = pair
        self.ctrl.add_measure_vector(pivot, tip)
        self.refresh_labels()

    def _add_measure_joint_from_selection(self):
        tri = self._selected_three_points()
        if not tri:
            return
        i, j, k = tri
        self.ctrl.add_measure_joint(i, j, k)
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
        self.refresh_labels()

    def _refresh_measure_table(self):
        mv = self.ctrl.get_measure_values_deg()
        load_mv = self.ctrl.get_load_measure_values()
        self._measure_row_map = []
        total_rows = len(mv) + len(load_mv)
        self.table_meas.setRowCount(total_rows)
        row = 0
        for index, (nm, val) in enumerate(mv):
            type_item = QTableWidgetItem("Measurement")
            name_item = QTableWidgetItem(str(nm))
            value_item = QTableWidgetItem("--" if val is None else f"{self.ctrl.format_number(val)}°")
            for item in (type_item, name_item, value_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_meas.setItem(row, 0, type_item)
            self.table_meas.setItem(row, 1, name_item)
            self.table_meas.setItem(row, 2, value_item)
            self._measure_row_map.append({"kind": "measure", "index": index})
            row += 1
        for index, (nm, val) in enumerate(load_mv):
            type_item = QTableWidgetItem("Load")
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

    def _refresh_load_tables(self):
        loads = list(self.ctrl.loads)
        self.table_loads.setRowCount(len(loads))
        for row, ld in enumerate(loads):
            pid = ld.get("pid", "--")
            ltype = str(ld.get("type", "force"))
            fx = ld.get("fx", 0.0)
            fy = ld.get("fy", 0.0)
            mz = ld.get("mz", 0.0)
            items = [
                QTableWidgetItem(f"P{pid}" if isinstance(pid, int) else str(pid)),
                QTableWidgetItem(ltype),
                QTableWidgetItem(self.ctrl.format_number(fx)),
                QTableWidgetItem(self.ctrl.format_number(fy)),
                QTableWidgetItem(self.ctrl.format_number(mz)),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_loads.setItem(row, col, item)

        joint_loads, qs = self.ctrl.compute_quasistatic_report()

        mode = qs.get("mode", "--")
        self.lbl_qs_mode.setText(f"Quasi-static: {mode}")

        tau_in = qs.get("tau_input", None)
        tau_out = qs.get("tau_output", None)
        self.lbl_tau_in.setText("Input τ: --" if tau_in is None else f"Input τ: {self.ctrl.format_number(tau_in)}")
        self.lbl_tau_out.setText("Output τ: --" if tau_out is None else f"Output τ: {self.ctrl.format_number(tau_out)}")

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
    # ---- sweep ----
    def play(self):
        if not self.ctrl.driver.get("enabled") and not self.ctrl.output.get("enabled"):
            QMessageBox.information(self, "Driver", "Set a driver or output first.")
            return
        try:
            start = float(self.ed_start.text())
            end = float(self.ed_end.text())
            step = float(self.ed_step.text())
        except ValueError:
            QMessageBox.warning(self, "Sweep", "Start/End/Step must be numbers.")
            return
        step = abs(step)
        if step == 0:
            QMessageBox.warning(self, "Sweep", "Step must be greater than 0.")
            return
        if end < start:
            step = -step
        self.ctrl.sweep_settings = {"start": start, "end": end, "step": abs(step)}
        self.ed_step.setText(f"{abs(step)}")

        self.stop()
        self.ctrl.mark_sim_start_pose()
        self._pending_sim_start_capture = True
        self.ctrl.reset_trajectories()

        self._records = []
        self._frame = 0
        self._last_run_data = None
        self._run_start_snapshot = self.ctrl.snapshot_model()
        self._theta_last_ok = start
        self._theta_deg = start
        self._theta_end = end
        self._theta_step = step
        self._theta_step_cur = step
        self._theta_step_min = max(abs(step) / 128.0, 1e-4)

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
            QMessageBox.information(self, "Reset", "No start pose captured yet. Press Play once first.")
        self.refresh_labels()



    def _on_tick(self):
        # stop condition based on direction
        if ((self._theta_step_cur > 0 and self._theta_last_ok > self._theta_end)
                or (self._theta_step_cur < 0 and self._theta_last_ok < self._theta_end)):
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
        while True:
            pose_before = self.ctrl.snapshot_points()
            if hasattr(self, "chk_scipy") and self.chk_scipy.isChecked() and not has_point_spline:
                try:
                    nfev = int(float(self.ed_nfev.text() or "250"))
                except Exception:
                    nfev = 250
                ok, msg = self.ctrl.drive_to_deg_scipy(theta_target, max_nfev=nfev)
                if not ok:
                    # Fallback to PBD so the UI stays responsive
                    self.ctrl.drive_to_deg(theta_target, iters=iters)
            else:
                self.ctrl.drive_to_deg(theta_target, iters=iters)

            # Feasibility check: do not "stretch" links across dead points.
            # If the requested step is infeasible, rollback and reduce the step.
            tol = 1e-3
            if hasattr(self.ctrl, "max_constraint_error"):
                max_err, detail = self.ctrl.max_constraint_error()
                hard_err = max(
                    detail.get("length", 0.0),
                    detail.get("angle", 0.0),
                    detail.get("coincide", 0.0),
                    detail.get("point_line", 0.0),
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
                    theta_target = self._theta_last_ok + step_target
                    continue
            step_applied = True
            break

        if self._pending_sim_start_capture:
            self.ctrl.update_sim_start_pose_snapshot()
            self._pending_sim_start_capture = False

        if step_applied:
            self.ctrl.append_trajectories()
        self.refresh_labels()

        rec: Dict[str, Any] = {
            "time": self._frame,
            "solver": ("scipy" if (hasattr(self, "chk_scipy") and self.chk_scipy.isChecked()) else "pbd"),
            "success": ok,
            "input_deg": self.ctrl.get_input_angle_deg(),
            "output_deg": self.ctrl.get_output_angle_deg(),
        }
        try:
            _max_err, detail = self.ctrl.max_constraint_error()
            rec["hard_err"] = max(
                detail.get("length", 0.0),
                detail.get("angle", 0.0),
                detail.get("coincide", 0.0),
                detail.get("point_line", 0.0),
                detail.get("point_spline", 0.0),
            )
        except Exception:
            rec["hard_err"] = None
        for nm, val in self.ctrl.get_measure_values_deg():
            rec[nm] = val
        for nm, val in self.ctrl.get_load_measure_values():
            rec[nm] = val
        self._records.append(rec)

        self._frame += 1
        if step_applied:
            self._theta_last_ok = theta_target
            self._theta_deg = self._theta_last_ok + step_target
            self._theta_step_cur = step_target
            if abs(self._theta_step_cur) < abs(base_step):
                grow = abs(self._theta_step_cur) * 1.25
                grow = min(abs(base_step), grow)
                self._theta_step_cur = math.copysign(grow, base_step)
                self._theta_deg = self._theta_last_ok + self._theta_step_cur

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
        signals.extend([name for name, _val in self.ctrl.get_measure_values_deg()])
        signals.extend([name for name, _val in self.ctrl.get_load_measure_values()])
        return {
            "schema_version": "1.0",
            "analysis_mode": "quasi_static",
            "driver": dict(self.ctrl.driver),
            "output": dict(self.ctrl.output),
            "sweep": {
                "start_deg": float(self.ctrl.sweep_settings.get("start", 0.0)),
                "end_deg": float(self.ctrl.sweep_settings.get("end", 360.0)),
                "step_deg": float(self.ctrl.sweep_settings.get("step", 2.0)),
                "adaptive": False,
                "min_step_deg": float(self._theta_step_min),
                "max_step_deg": float(abs(self._theta_step)),
            },
            "solver": {
                "use_scipy": bool(self.chk_scipy.isChecked()),
                "max_nfev": max_nfev,
                "pbd_iters": iters,
                "hard_err_tol": 1e-3,
                "treat_point_spline_as_soft": bool(has_point_spline),
            },
            "loads": list(self.ctrl.loads),
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
            QMessageBox.information(self, "Export", "No sweep data yet. Run Play first.")
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
