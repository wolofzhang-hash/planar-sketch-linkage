# -*- coding: utf-8 -*-
"""Simulation dock: driver/measurements, sweep, plot and export.

New in v2.6.6:
- Global Parameters tab + expression fields for Point X/Y, Length L, and Angle deg.

Previously (v2.4.19):
- Restored point right-click menus for Driver / Measurement (also available in v2.4.19).
- Reset pose to the sweep start pose
- Plot window with custom X/Y (X can be time or any measurement; Y supports multiple series)
- Export SVG/CSV from the plot window; export full sweep CSV (time/input + all measurements)
"""

from __future__ import annotations

import csv
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView
)

from .plot_window import PlotWindow

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
        self._frame = 0

        self._records: List[Dict[str, Any]] = []
        self._plot_window: Optional[PlotWindow] = None
        self._pending_sim_start_capture = False

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        # Driver
        row = QHBoxLayout()
        self.lbl_driver = QLabel("Driver: (not set)")
        self.btn_set_driver_vec = QPushButton("Set Vector Driver (2 pts)")
        self.btn_set_driver_joint = QPushButton("Set Joint Driver (3 pts)")
        self.btn_clear_driver = QPushButton("Clear")
        row.addWidget(self.lbl_driver, 1)
        row.addWidget(self.btn_set_driver_vec)
        row.addWidget(self.btn_set_driver_joint)
        row.addWidget(self.btn_clear_driver)
        main_layout.addLayout(row)

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
        self.chk_traj = QCheckBox("Show Trajectory")
        self.chk_traj.setChecked(True)
        solver_row.addWidget(self.chk_traj)
        solver_row.addStretch(1)
        main_layout.addLayout(solver_row)

        # Buttons
        btns = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_stop = QPushButton("Stop")
        self.btn_reset_pose = QPushButton("Reset Pose")
        self.btn_plot = QPushButton("Plot...")
        self.btn_export = QPushButton("Export CSV (full sweep)")
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_reset_pose)
        btns.addWidget(self.btn_plot)
        btns.addWidget(self.btn_export)
        main_layout.addLayout(btns)

        main_layout.addStretch(1)
        tabs.addTab(main_tab, "Simulation")

        measurements_tab = QWidget()
        measurements_layout = QVBoxLayout(measurements_tab)
        self.table_meas = QTableWidget(0, 2)
        self.table_meas.setHorizontalHeaderLabels(["Measurement", "Value (deg)"])
        self.table_meas.verticalHeader().setVisible(False)
        self.table_meas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_meas.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_meas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        measurements_layout.addWidget(self.table_meas)

        meas_buttons = QHBoxLayout()
        self.btn_add_meas_vec = QPushButton("Add Vector Measure (2 pts)")
        self.btn_add_meas_joint = QPushButton("Add Joint Measure (3 pts)")
        self.btn_clear_meas = QPushButton("Clear")
        meas_buttons.addWidget(self.btn_add_meas_vec)
        meas_buttons.addWidget(self.btn_add_meas_joint)
        meas_buttons.addWidget(self.btn_clear_meas)
        measurements_layout.addLayout(meas_buttons)
        measurements_layout.addStretch(1)
        tabs.addTab(measurements_tab, "Measurements")

        # Signals
        self.btn_set_driver_vec.clicked.connect(self._set_driver_from_selection)
        self.btn_set_driver_joint.clicked.connect(self._set_driver_joint_from_selection)
        self.btn_clear_driver.clicked.connect(self._clear_driver)
        self.btn_add_meas_vec.clicked.connect(self._add_measure_vector_from_selection)
        self.btn_add_meas_joint.clicked.connect(self._add_measure_joint_from_selection)
        self.btn_clear_meas.clicked.connect(self._clear_measures)
        self.btn_play.clicked.connect(self.play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_reset_pose.clicked.connect(self.reset_pose)
        self.btn_plot.clicked.connect(self.open_plot)
        self.btn_export.clicked.connect(self.export_csv)

        self.refresh_labels()

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
            self.lbl_driver.setText("Driver: (not set)")

        a_in = self.ctrl.get_input_angle_deg()
        s_in = "--" if a_in is None else f"{a_in:.3f}°"
        self.lbl_angles.setText(f"Input: {s_in}")
        self._refresh_measure_table()

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

    def _refresh_measure_table(self):
        mv = self.ctrl.get_measure_values_deg()
        self.table_meas.setRowCount(len(mv))
        for row, (nm, val) in enumerate(mv):
            name_item = QTableWidgetItem(str(nm))
            value_item = QTableWidgetItem("--" if val is None else f"{val:.3f}°")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_meas.setItem(row, 0, name_item)
            self.table_meas.setItem(row, 1, value_item)

    # ---- sweep ----
    def play(self):
        if not self.ctrl.driver.get("enabled"):
            QMessageBox.information(self, "Driver", "Set a driver first.")
            return
        try:
            start = float(self.ed_start.text())
            end = float(self.ed_end.text())
            step = float(self.ed_step.text())
        except ValueError:
            QMessageBox.warning(self, "Sweep", "Start/End/Step must be numbers.")
            return
        if step == 0:
            QMessageBox.warning(self, "Sweep", "Step must be non-zero.")
            return

        self.stop()
        self.ctrl.mark_sim_start_pose()
        self._pending_sim_start_capture = True
        self.ctrl.set_show_trajectories(self.chk_traj.isChecked(), reset=True)

        self._records = []
        self._frame = 0
        self._theta_deg = start
        self._theta_end = end
        self._theta_step = step

        # Do one immediate tick for responsiveness
        self._on_tick()
        self._timer.start(15)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def reset_pose(self):
        self.stop()
        ok = self.ctrl.reset_pose_to_sim_start()
        if not ok:
            QMessageBox.information(self, "Reset", "No start pose captured yet. Press Play once first.")
        self.refresh_labels()



    def _on_tick(self):
        pose_before = self.ctrl.snapshot_points()

        # stop condition based on direction
        if (self._theta_step > 0 and self._theta_deg > self._theta_end) or (self._theta_step < 0 and self._theta_deg < self._theta_end):
            self.stop()
            self.refresh_labels()
            return

        ok = True
        step_applied = True
        msg = ""
        if hasattr(self, "chk_scipy") and self.chk_scipy.isChecked():
            try:
                nfev = int(float(self.ed_nfev.text() or "250"))
            except Exception:
                nfev = 250
            ok, msg = self.ctrl.drive_to_deg_scipy(self._theta_deg, max_nfev=nfev)
            if not ok:
                # Fallback to PBD so the UI stays responsive
                self.ctrl.drive_to_deg(self._theta_deg, iters=80)
        else:
            self.ctrl.drive_to_deg(self._theta_deg, iters=80)

        # Feasibility check: do not "stretch" links across dead points.
        # If the requested step is infeasible, rollback and stop.
        tol = 1e-3
        if hasattr(self.ctrl, "max_constraint_error"):
            max_err, _detail = self.ctrl.max_constraint_error()
            if max_err > tol:
                # rollback to previous pose
                self.ctrl.apply_points_snapshot(pose_before)
                self.ctrl.solve_constraints(iters=80)
                self.ctrl.update_graphics()
                if self.ctrl.panel:
                    self.ctrl.panel.defer_refresh_all()
                ok = False
                msg = f"infeasible step (max_err={max_err:.3g})"
                step_applied = False
                self.stop()

        if self._pending_sim_start_capture:
            self.ctrl.update_sim_start_pose_snapshot()
            self._pending_sim_start_capture = False

        if step_applied:
            self.ctrl.append_trajectories()
        self.refresh_labels()

        rec: Dict[str, Any] = {
            "time": self._frame,
            "solver": ("scipy" if (hasattr(self, "chk_scipy") and self.chk_scipy.isChecked()) else "pbd"),
            "ok": ok,
            "input_deg": self.ctrl.get_input_angle_deg(),
        }
        for nm, val in self.ctrl.get_measure_values_deg():
            rec[nm] = val
        self._records.append(rec)

        self._frame += 1
        self._theta_deg += self._theta_step
    # ---- plot/export ----
    def open_plot(self):
        if not self._records:
            QMessageBox.information(self, "Plot", "No sweep data yet. Run Play first.")
            return
        # Reuse existing window if present.
        if self._plot_window is None:
            self._plot_window = PlotWindow(self._records)
        else:
            # update records reference and refresh options
            self._plot_window._records = self._records
            self._plot_window._populate_axes_options()
        self._plot_window.show()
        self._plot_window.raise_()
        self._plot_window.activateWindow()

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
