# -*- coding: utf-8 -*-
"""Analysis tabs: Animation + Optimization."""

from __future__ import annotations

import csv
import json
import math
import os
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QGroupBox,
    QLineEdit,
    QMenu,
    QDialog,
    QInputDialog,
)

from ..core.case_run_manager import CaseRunManager
from ..core.expression import evaluate_expression
from ..core.headless_sim import simulate_case
from ..core.optimization import (
    OptimizationWorker,
    DesignVariable,
    ObjectiveSpec,
    ConstraintSpec,
    build_signals,
    model_variable_signals,
)
from .expression_builder import ExpressionBuilderDialog
from .plot_window import PlotWindow

class AnimationTab(QWidget):
    def __init__(self, ctrl: Any, on_active_case_changed=None):
        super().__init__()
        self.ctrl = ctrl
        self._on_active_case_changed = on_active_case_changed
        layout = QVBoxLayout(self)

        self.lbl_active = QLabel("Active Case: --")
        layout.addWidget(self.lbl_active)

        self.table_case_runs = QTableWidget(0, 5)
        self.table_case_runs.setHorizontalHeaderLabels(["Case Name", "Case ID", "Run ID", "Success", "Steps"])
        self.table_case_runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_case_runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_case_runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_case_runs.verticalHeader().setVisible(False)
        layout.addWidget(QLabel("Cases + Runs"))
        layout.addWidget(self.table_case_runs)

        case_btn_row = QHBoxLayout()
        self.btn_rename_case = QPushButton("Rename Case")
        self.btn_rename_case_id = QPushButton("Rename Case ID")
        self.btn_delete_case_results = QPushButton("Delete Case Results")
        case_btn_row.addWidget(self.btn_rename_case)
        case_btn_row.addWidget(self.btn_rename_case_id)
        case_btn_row.addWidget(self.btn_delete_case_results)
        case_btn_row.addStretch(1)
        layout.addLayout(case_btn_row)

        btn_row = QHBoxLayout()
        self.btn_open_run = QPushButton("Open Run Folder")
        self.btn_load_snapshot = QPushButton("Load Run Snapshot")
        self.btn_set_active = QPushButton("Set Active Case")
        self.btn_load_run_data = QPushButton("Load Run Data")
        btn_row.addWidget(self.btn_open_run)
        btn_row.addWidget(self.btn_load_snapshot)
        btn_row.addWidget(self.btn_set_active)
        btn_row.addWidget(self.btn_load_run_data)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addWidget(self._build_replay_group())

        self.btn_open_run.clicked.connect(self.open_run_folder)
        self.btn_load_snapshot.clicked.connect(self.load_run_snapshot)
        self.btn_set_active.clicked.connect(self.set_active_case)
        self.btn_load_run_data.clicked.connect(self.load_run_data)
        self.btn_rename_case.clicked.connect(self.rename_case)
        self.btn_rename_case_id.clicked.connect(self.rename_case_id)
        self.btn_delete_case_results.clicked.connect(self.delete_case_results)

        self._cases_cache: List[Any] = []
        self._row_cache: List[Dict[str, Any]] = []
        self._frames: List[Dict[str, Any]] = []
        self._frame_index = 0
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._advance_frame)
        self._plot_window: Optional[PlotWindow] = None
        self.refresh_cases()

    def _project_dir(self) -> str:
        if getattr(self.ctrl, "win", None) and getattr(self.ctrl.win, "current_file", None):
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _manager(self) -> CaseRunManager:
        return CaseRunManager(self._project_dir())

    def refresh_cases(self) -> None:
        manager = self._manager()
        cases = manager.list_cases()
        self._cases_cache = cases
        rows: List[Dict[str, Any]] = []
        for info in cases:
            runs = manager.list_runs(info.case_id)
            if not runs:
                rows.append({"case": info, "run": None})
                continue
            for run in runs:
                rows.append({"case": info, "run": run})
        self._row_cache = rows
        self.table_case_runs.setRowCount(len(rows))
        for row, payload in enumerate(rows):
            case_info = payload["case"]
            run_info = payload.get("run") or {}
            items = [
                QTableWidgetItem(case_info.name),
                QTableWidgetItem(case_info.case_id),
                QTableWidgetItem(str(run_info.get("run_id", ""))),
                QTableWidgetItem(str(run_info.get("success", ""))),
                QTableWidgetItem(str(run_info.get("n_steps", ""))),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_case_runs.setItem(row, col, item)
        active = manager.get_active_case()
        self.lbl_active.setText(f"Active Case: {active or '--'}")

    def _selected_case_id(self) -> Optional[str]:
        row = self.table_case_runs.currentRow()
        if row < 0 or row >= len(self._row_cache):
            return None
        return self._row_cache[row]["case"].case_id

    def _selected_run(self) -> Optional[Dict[str, Any]]:
        row = self.table_case_runs.currentRow()
        if row < 0 or row >= len(self._row_cache):
            return None
        return self._row_cache[row].get("run")

    def open_run_folder(self) -> None:
        run = self._selected_run()
        if not run:
            QMessageBox.information(self, "Run", "Select a run first.")
            return
        path = run.get("path")
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def load_run_snapshot(self) -> None:
        run = self._selected_run()
        if not run:
            QMessageBox.information(self, "Run", "Select a run first.")
            return
        path = os.path.join(run.get("path", ""), "model.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, "Run", "model.json not found.")
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = fh.read()
            self.ctrl.load_dict(json.loads(data))
            if self.ctrl.panel:
                self.ctrl.panel.defer_refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Run", f"Failed to load snapshot: {exc}")

    def set_active_case(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        manager = self._manager()
        manager.set_active_case(case_id)
        self.lbl_active.setText(f"Active Case: {case_id}")
        if self._on_active_case_changed:
            self._on_active_case_changed()

    def _build_replay_group(self) -> QWidget:
        group = QGroupBox("Replay + Plot")
        layout = QVBoxLayout(group)

        controls = QHBoxLayout()
        self.btn_replay_play = QPushButton("Play")
        self.btn_replay_pause = QPushButton("Pause")
        self.btn_replay_stop = QPushButton("Stop")
        self.btn_replay_restart = QPushButton("Replay")
        self.btn_plot_run = QPushButton("Plot...")
        controls.addWidget(self.btn_replay_play)
        controls.addWidget(self.btn_replay_pause)
        controls.addWidget(self.btn_replay_stop)
        controls.addWidget(self.btn_replay_restart)
        controls.addWidget(self.btn_plot_run)
        controls.addStretch(1)
        layout.addLayout(controls)

        slider_row = QHBoxLayout()
        self.slider_frame = QSlider(Qt.Orientation.Horizontal)
        self.slider_frame.setRange(0, 0)
        self.lbl_frame = QLabel("Frame: --")
        slider_row.addWidget(self.slider_frame, 1)
        slider_row.addWidget(self.lbl_frame)
        layout.addLayout(slider_row)

        self.btn_replay_play.clicked.connect(self.play_replay)
        self.btn_replay_pause.clicked.connect(self.pause_replay)
        self.btn_replay_stop.clicked.connect(self.stop_replay)
        self.btn_replay_restart.clicked.connect(self.restart_replay)
        self.slider_frame.valueChanged.connect(self._on_slider_changed)
        self.btn_plot_run.clicked.connect(self.open_plot_window)
        return group

    def rename_case(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        manager = self._manager()
        new_name, ok = QInputDialog.getText(self, "Rename Case", "New case name:")
        if not ok:
            return
        if manager.update_case_name(case_id, new_name):
            self.refresh_cases()
        else:
            QMessageBox.warning(self, "Case", "Failed to rename case.")

    def rename_case_id(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        manager = self._manager()
        new_id, ok = QInputDialog.getText(self, "Rename Case ID", "New case ID:")
        if not ok:
            return
        if manager.rename_case_id(case_id, new_id):
            self.refresh_cases()
        else:
            QMessageBox.warning(self, "Case", "Failed to rename case ID.")

    def delete_case_results(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete Results",
            f"Delete all runs for case {case_id}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        manager = self._manager()
        manager.delete_case_runs(case_id)
        self.refresh_cases()

    def load_run_data(self) -> None:
        run = self._selected_run()
        if not run:
            QMessageBox.information(self, "Run", "Select a run first.")
            return
        path = run.get("path")
        if not path:
            return
        frames_path = os.path.join(path, "results", "frames.csv")
        if not os.path.exists(frames_path):
            QMessageBox.warning(self, "Run", "frames.csv not found.")
            return
        model_path = os.path.join(path, "model.json")
        if not os.path.exists(model_path):
            QMessageBox.warning(self, "Run", "model.json not found.")
            return
        try:
            with open(frames_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                self._frames = [self._coerce_frame_row(row) for row in reader]
        except Exception as exc:
            QMessageBox.critical(self, "Run", f"Failed to load frames: {exc}")
            return
        try:
            with open(model_path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
            self.ctrl.apply_model_snapshot(snapshot)
            self.ctrl.mark_sim_start_pose()
            if self.ctrl.panel:
                self.ctrl.panel.defer_refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Run", f"Failed to load model snapshot: {exc}")
            return
        self._frame_index = 0
        self.slider_frame.setRange(0, max(0, len(self._frames) - 1))
        self.slider_frame.setValue(0)
        self._apply_frame(0)
        self._refresh_plot_window()

    def _coerce_frame_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, val in row.items():
            if val is None or val == "":
                out[key] = None
                continue
            if isinstance(val, str):
                lower = val.strip().lower()
                if lower in ("true", "false"):
                    out[key] = lower == "true"
                    continue
                try:
                    out[key] = float(val)
                    continue
                except ValueError:
                    out[key] = val
                    continue
            out[key] = val
        return out

    def _refresh_plot_window(self) -> None:
        if self._plot_window is None:
            return
        self._plot_window._records = self._frames
        self._plot_window._populate_axes_options()

    def open_plot_window(self) -> None:
        if not self._frames:
            QMessageBox.information(self, "Plot", "No run data loaded.")
            return
        if self._plot_window is None:
            self._plot_window = PlotWindow(self._frames)
        else:
            self._plot_window._records = self._frames
            self._plot_window._populate_axes_options()
        self._plot_window.show()
        self._plot_window.raise_()
        self._plot_window.activateWindow()

    def _apply_frame(self, index: int) -> None:
        if not self._frames:
            return
        idx = max(0, min(index, len(self._frames) - 1))
        frame = self._frames[idx]
        input_val = frame.get("input_deg")
        if input_val is not None:
            try:
                self.ctrl.drive_to_deg(float(input_val))
            except Exception:
                pass
        self._frame_index = idx
        self.lbl_frame.setText(f"Frame: {idx + 1}/{len(self._frames)}")

    def _advance_frame(self) -> None:
        if not self._frames:
            self._frame_timer.stop()
            return
        next_idx = self._frame_index + 1
        if next_idx >= len(self._frames):
            self._frame_timer.stop()
            return
        self.slider_frame.setValue(next_idx)

    def _on_slider_changed(self, value: int) -> None:
        self._apply_frame(value)

    def play_replay(self) -> None:
        if not self._frames:
            QMessageBox.information(self, "Replay", "Load run data first.")
            return
        if self._frame_index >= len(self._frames) - 1:
            self.slider_frame.setValue(0)
        self._frame_timer.start(50)

    def pause_replay(self) -> None:
        if self._frame_timer.isActive():
            self._frame_timer.stop()

    def stop_replay(self) -> None:
        if self._frame_timer.isActive():
            self._frame_timer.stop()
        self.slider_frame.setValue(0)

    def restart_replay(self) -> None:
        if not self._frames:
            return
        self.slider_frame.setValue(0)
        self._frame_timer.start(50)


class OptimizationTab(QWidget):
    def __init__(self, ctrl: Any):
        super().__init__()
        self.ctrl = ctrl
        self._worker: Optional[OptimizationWorker] = None
        self._best_vars: Dict[str, float] = {}

        layout = QVBoxLayout(self)
        self.lbl_active = QLabel("Active Case: --")
        layout.addWidget(self.lbl_active)

        layout.addWidget(self._build_variables_group())
        layout.addWidget(self._build_objectives_group())
        layout.addWidget(self._build_constraints_group())
        layout.addWidget(self._build_run_group())
        layout.addStretch(1)

        self.refresh_active_case()
        self.ensure_defaults()

    def _build_variables_group(self) -> QWidget:
        group = QGroupBox("Design Variables")
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_var = QPushButton("Add")
        self.btn_del_var = QPushButton("Remove")
        btn_row.addWidget(self.btn_add_var)
        btn_row.addWidget(self.btn_del_var)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_vars = QTableWidget(0, 6)
        self.table_vars.setHorizontalHeaderLabels(["Enabled", "Type", "Variable", "Current", "Lower", "Upper"])
        self.table_vars.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_vars.verticalHeader().setVisible(False)
        self.table_vars.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_vars.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table_vars)

        self.btn_add_var.clicked.connect(lambda _checked=False: self.add_variable_row())
        self.btn_del_var.clicked.connect(self.remove_variable_row)
        return group

    def _build_objectives_group(self) -> QWidget:
        group = QGroupBox("Objectives")
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_obj = QPushButton("Add")
        self.btn_del_obj = QPushButton("Remove")
        btn_row.addWidget(self.btn_add_obj)
        btn_row.addWidget(self.btn_del_obj)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_obj = QTableWidget(0, 3)
        self.table_obj.setHorizontalHeaderLabels(["Enabled", "Direction", "Expression"])
        self.table_obj.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_obj.verticalHeader().setVisible(False)
        self.table_obj.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table_obj)

        self.btn_add_obj.clicked.connect(lambda _checked=False: self.add_objective_row())
        self.btn_del_obj.clicked.connect(self.remove_objective_row)
        self.table_obj.customContextMenuRequested.connect(self._open_objective_context_menu)
        return group

    def _build_constraints_group(self) -> QWidget:
        group = QGroupBox("Constraints")
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_con = QPushButton("Add")
        self.btn_del_con = QPushButton("Remove")
        btn_row.addWidget(self.btn_add_con)
        btn_row.addWidget(self.btn_del_con)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_con = QTableWidget(0, 4)
        self.table_con.setHorizontalHeaderLabels(["Enabled", "Expression", "Comparator", "Limit"])
        self.table_con.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_con.verticalHeader().setVisible(False)
        self.table_con.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table_con)

        self.btn_add_con.clicked.connect(lambda _checked=False: self.add_constraint_row())
        self.btn_del_con.clicked.connect(self.remove_constraint_row)
        self.table_con.customContextMenuRequested.connect(self._open_constraint_context_menu)
        return group

    def _build_run_group(self) -> QWidget:
        group = QGroupBox("Optimization Run")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Evals"))
        self.ed_evals = QLineEdit("50")
        self.ed_evals.setMaximumWidth(80)
        row.addWidget(self.ed_evals)
        row.addWidget(QLabel("Seed"))
        self.ed_seed = QLineEdit("")
        self.ed_seed.setMaximumWidth(120)
        row.addWidget(self.ed_seed)
        row.addStretch(1)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_stop = QPushButton("Stop")
        self.btn_apply_best = QPushButton("Apply Best to Model")
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_apply_best)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.lbl_progress = QLabel("Progress: --")
        layout.addWidget(self.lbl_progress)

        self.table_best = QTableWidget(0, 3)
        self.table_best.setHorizontalHeaderLabels(["Best Objective", "P12.x", "P12.y"])
        self.table_best.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_best.verticalHeader().setVisible(False)
        layout.addWidget(self.table_best)

        self.btn_run.clicked.connect(self.run_optimization)
        self.btn_stop.clicked.connect(self.stop_optimization)
        self.btn_apply_best.clicked.connect(self.apply_best)
        self.btn_stop.setEnabled(False)
        return group

    def _project_dir(self) -> str:
        if getattr(self.ctrl, "win", None) and getattr(self.ctrl.win, "current_file", None):
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _manager(self) -> CaseRunManager:
        return CaseRunManager(self._project_dir())

    def refresh_active_case(self) -> None:
        active = self._manager().get_active_case()
        self.lbl_active.setText(f"Active Case: {active or '--'}")

    def ensure_defaults(self) -> None:
        if self.table_vars.rowCount() == 0:
            self.add_variable_row("P12.x")
            self.add_variable_row("P12.y")
        if self.table_obj.rowCount() == 0:
            self.add_objective_row(direction="min", expression="max(load.P9.Mag)")

    def _variable_type_options(self) -> List[str]:
        return ["Coordinate", "Length", "Parameter", "All"]

    def _variable_options_for_type(self, var_type: str) -> List[str]:
        coords = []
        for pid in sorted(self.ctrl.points.keys()):
            coords.append(f"P{pid}.x")
            coords.append(f"P{pid}.y")
        lengths = [f"Link{lid}.L" for lid in sorted(self.ctrl.links.keys())]
        params = [f"Param.{name}" for name in sorted(self.ctrl.parameters.params.keys())]
        if var_type == "Coordinate":
            return coords
        if var_type == "Length":
            return lengths
        if var_type == "Parameter":
            return params
        return coords + lengths + params

    def _infer_variable_type(self, name: Optional[str]) -> str:
        if not name:
            return "Coordinate"
        if name.startswith("P") and "." in name:
            return "Coordinate"
        if name.startswith("Link") and name.endswith(".L"):
            return "Length"
        if name.startswith("Param."):
            return "Parameter"
        return "Coordinate"

    def add_variable_row(self, name: Optional[str] = None) -> None:
        row = self.table_vars.rowCount()
        self.table_vars.insertRow(row)

        enabled_item = QTableWidgetItem()
        enabled_item.setCheckState(Qt.CheckState.Checked)
        self.table_vars.setItem(row, 0, enabled_item)

        type_combo = QComboBox(self.table_vars)
        type_combo.addItems(self._variable_type_options())
        type_combo.setCurrentText(self._infer_variable_type(name))
        type_combo.currentTextChanged.connect(lambda t, r=row: self._on_variable_type_changed(r, t))
        self.table_vars.setCellWidget(row, 1, type_combo)

        combo = QComboBox(self.table_vars)
        opts = self._variable_options_for_type(type_combo.currentText())
        combo.addItems(opts)
        if name and name in opts:
            combo.setCurrentText(name)
        elif name:
            combo.addItem(name)
            combo.setCurrentText(name)
        combo.currentTextChanged.connect(lambda _t, r=row: self._update_current_value(r))
        self.table_vars.setCellWidget(row, 2, combo)

        current_item = QTableWidgetItem("--")
        current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_vars.setItem(row, 3, current_item)
        self.table_vars.setItem(row, 4, QTableWidgetItem(""))
        self.table_vars.setItem(row, 5, QTableWidgetItem(""))
        self._update_current_value(row)

    def remove_variable_row(self) -> None:
        row = self.table_vars.currentRow()
        if row >= 0:
            self.table_vars.removeRow(row)

    def _update_current_value(self, row: int) -> None:
        combo = self.table_vars.cellWidget(row, 2)
        if not isinstance(combo, QComboBox):
            return
        name = combo.currentText()
        current = self._get_variable_value(name)
        item = self.table_vars.item(row, 3)
        if item:
            item.setText("--" if current is None else f"{current:.4f}")

    def _get_variable_value(self, name: str) -> Optional[float]:
        name = name.strip()
        if not name.startswith("P") or "." not in name:
            if name.startswith("Param."):
                param = name[len("Param.") :]
                if param in self.ctrl.parameters.params:
                    return float(self.ctrl.parameters.params.get(param, 0.0))
            if name.startswith("Link") and name.endswith(".L"):
                lid_str = name[len("Link") : -len(".L")]
                try:
                    lid = int(lid_str)
                except Exception:
                    return None
                link = self.ctrl.links.get(lid)
                if not link:
                    return None
                if link.get("ref", False):
                    i = int(link.get("i", -1))
                    j = int(link.get("j", -1))
                    if i in self.ctrl.points and j in self.ctrl.points:
                        p1 = self.ctrl.points[i]
                        p2 = self.ctrl.points[j]
                        return math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                return float(link.get("L", 0.0))
            return None
        pid_str, axis = name[1:].split(".", 1)
        try:
            pid = int(pid_str)
        except Exception:
            return None
        if pid not in self.ctrl.points:
            return None
        return float(self.ctrl.points[pid].get(axis, 0.0))

    def _on_variable_type_changed(self, row: int, var_type: str) -> None:
        combo = self.table_vars.cellWidget(row, 2)
        if not isinstance(combo, QComboBox):
            return
        current = combo.currentText()
        opts = self._variable_options_for_type(var_type)
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(opts)
        if current in opts:
            combo.setCurrentText(current)
        elif opts:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
        self._update_current_value(row)

    def add_objective_row(self, direction: str = "min", expression: str = "") -> None:
        row = self.table_obj.rowCount()
        self.table_obj.insertRow(row)
        enabled_item = QTableWidgetItem()
        enabled_item.setCheckState(Qt.CheckState.Checked)
        self.table_obj.setItem(row, 0, enabled_item)
        combo = QComboBox(self.table_obj)
        combo.addItems(["min", "max"])
        combo.setCurrentText(direction)
        self.table_obj.setCellWidget(row, 1, combo)
        self.table_obj.setItem(row, 2, QTableWidgetItem(expression))

    def remove_objective_row(self) -> None:
        row = self.table_obj.currentRow()
        if row >= 0:
            self.table_obj.removeRow(row)

    def add_constraint_row(self, expression: str = "", comparator: str = "<=", limit: str = "") -> None:
        row = self.table_con.rowCount()
        self.table_con.insertRow(row)
        enabled_item = QTableWidgetItem()
        enabled_item.setCheckState(Qt.CheckState.Checked)
        self.table_con.setItem(row, 0, enabled_item)
        self.table_con.setItem(row, 1, QTableWidgetItem(expression))
        combo = QComboBox(self.table_con)
        combo.addItems(["<=", ">="])
        combo.setCurrentText(comparator)
        self.table_con.setCellWidget(row, 2, combo)
        self.table_con.setItem(row, 3, QTableWidgetItem(limit))

    def remove_constraint_row(self) -> None:
        row = self.table_con.currentRow()
        if row >= 0:
            self.table_con.removeRow(row)

    def _optimization_functions(self) -> Dict[str, List[str]]:
        return {
            "Aggregates": ["max(", "min(", "mean(", "rms(", "abs(", "first(", "last("],
            "Operators": ["+", "-", "*", "/", "(", ")", ","],
        }

    def _optimization_token_groups(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        groups["Input/Output"] = ["input_deg", "output_deg"]
        groups["Status"] = ["hard_err", "success"]

        measurements = [name for name, _val in self.ctrl.get_measure_values_deg()]
        load_measures = [name for name, _val in self.ctrl.get_load_measure_values()]

        manager = self._manager()
        case_id = manager.get_active_case()
        if case_id:
            case_spec = manager.load_case_spec(case_id) or {}
            measurements.extend(case_spec.get("measurements", {}).get("signals", []))

        if measurements:
            groups["Measurements"] = measurements
        if load_measures:
            groups["Load Measurements"] = load_measures

        snapshot = self.ctrl.snapshot_model()
        model_vars = sorted(model_variable_signals(snapshot).keys())
        if model_vars:
            groups["Model Variables"] = model_vars

        cleaned: Dict[str, List[str]] = {}
        for name, items in groups.items():
            filtered = sorted({str(item) for item in items if str(item).strip()})
            if filtered:
                cleaned[name] = filtered
        return cleaned

    def _open_objective_context_menu(self, pos) -> None:
        item = self.table_obj.itemAt(pos)
        if not item:
            return
        row = item.row()
        col = item.column()
        if col != 2:
            return
        menu = QMenu(self)
        act_builder = menu.addAction("Expression Builder...")
        selected = menu.exec(self.table_obj.viewport().mapToGlobal(pos))
        if selected == act_builder:
            self._open_expression_builder_for_objective(row)

    def _open_constraint_context_menu(self, pos) -> None:
        item = self.table_con.itemAt(pos)
        if not item:
            return
        row = item.row()
        col = item.column()
        if col != 1:
            return
        menu = QMenu(self)
        act_builder = menu.addAction("Expression Builder...")
        selected = menu.exec(self.table_con.viewport().mapToGlobal(pos))
        if selected == act_builder:
            self._open_expression_builder_for_constraint(row)

    def _open_expression_builder_for_objective(self, row: int) -> None:
        expr_item = self.table_obj.item(row, 2)
        current = expr_item.text() if expr_item else ""
        dialog = ExpressionBuilderDialog(
            self,
            initial=current,
            tokens=self._optimization_token_groups(),
            functions=self._optimization_functions(),
            evaluator=self._evaluate_expression,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.expression().strip()
            if expr_item:
                expr_item.setText(text)
            else:
                self.table_obj.setItem(row, 2, QTableWidgetItem(text))

    def _open_expression_builder_for_constraint(self, row: int) -> None:
        expr_item = self.table_con.item(row, 1)
        current = expr_item.text() if expr_item else ""
        dialog = ExpressionBuilderDialog(
            self,
            initial=current,
            tokens=self._optimization_token_groups(),
            functions=self._optimization_functions(),
            evaluator=self._evaluate_expression,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.expression().strip()
            if expr_item:
                expr_item.setText(text)
            else:
                self.table_con.setItem(row, 1, QTableWidgetItem(text))

    def _evaluate_expression(self, expr: str) -> tuple[Optional[float], Optional[str]]:
        manager = self._manager()
        case_id = manager.get_active_case()
        if not case_id:
            return None, "Select an active case first"
        case_spec = manager.load_case_spec(case_id)
        if not case_spec:
            return None, "Active case spec not found"

        model_snapshot = manager.load_latest_model_snapshot(case_id)
        if model_snapshot is None:
            model_snapshot = self.ctrl.snapshot_model()

        frames, _summary, _status = simulate_case(model_snapshot, case_spec)
        signals = build_signals(frames, model_snapshot)
        return evaluate_expression(expr, signals)

    def _collect_variables(self) -> Optional[List[DesignVariable]]:
        variables: List[DesignVariable] = []
        for row in range(self.table_vars.rowCount()):
            enabled_item = self.table_vars.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            combo = self.table_vars.cellWidget(row, 2)
            name = combo.currentText() if isinstance(combo, QComboBox) else ""
            lower_item = self.table_vars.item(row, 4)
            upper_item = self.table_vars.item(row, 5)
            try:
                lower = float(lower_item.text()) if lower_item and lower_item.text().strip() else None
                upper = float(upper_item.text()) if upper_item and upper_item.text().strip() else None
            except Exception:
                QMessageBox.warning(self, "Variables", "Bounds must be numeric.")
                return None
            if lower is None or upper is None:
                QMessageBox.warning(self, "Variables", f"Bounds required for {name}.")
                return None
            variables.append(DesignVariable(name=name, lower=lower, upper=upper, enabled=enabled))
        return variables

    def _collect_objectives(self) -> List[ObjectiveSpec]:
        objs: List[ObjectiveSpec] = []
        for row in range(self.table_obj.rowCount()):
            enabled_item = self.table_obj.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            combo = self.table_obj.cellWidget(row, 1)
            direction = combo.currentText() if isinstance(combo, QComboBox) else "min"
            expr_item = self.table_obj.item(row, 2)
            expr = expr_item.text().strip() if expr_item else ""
            objs.append(ObjectiveSpec(expression=expr, direction=direction, enabled=enabled))
        return objs

    def _collect_constraints(self) -> List[ConstraintSpec]:
        cons: List[ConstraintSpec] = []
        for row in range(self.table_con.rowCount()):
            enabled_item = self.table_con.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            expr_item = self.table_con.item(row, 1)
            expr = expr_item.text().strip() if expr_item else ""
            combo = self.table_con.cellWidget(row, 2)
            comparator = combo.currentText() if isinstance(combo, QComboBox) else "<="
            limit_item = self.table_con.item(row, 3)
            if limit_item is None or not limit_item.text().strip():
                limit = 0.0
            else:
                try:
                    limit = float(limit_item.text())
                except Exception:
                    QMessageBox.warning(self, "Constraints", "Constraint limits must be numeric.")
                    return []
            cons.append(ConstraintSpec(expression=expr, comparator=comparator, limit=limit, enabled=enabled))
        return cons

    def run_optimization(self) -> None:
        self.ensure_defaults()
        variables = self._collect_variables()
        if variables is None:
            return
        objectives = self._collect_objectives()
        constraints = self._collect_constraints()

        manager = self._manager()
        case_id = manager.get_active_case()
        if not case_id:
            QMessageBox.warning(self, "Optimization", "Select an active case first.")
            return
        case_spec = manager.load_case_spec(case_id)
        if not case_spec:
            QMessageBox.warning(self, "Optimization", "Active case spec not found.")
            return

        model_snapshot = manager.load_latest_model_snapshot(case_id)
        if model_snapshot is None:
            model_snapshot = self.ctrl.snapshot_model()

        try:
            evals = int(float(self.ed_evals.text() or "50"))
        except Exception:
            evals = 50
        seed_text = (self.ed_seed.text() or "").strip()
        seed = int(seed_text) if seed_text else None

        self._worker = OptimizationWorker(
            model_snapshot=model_snapshot,
            case_spec=case_spec,
            variables=variables,
            objectives=objectives,
            constraints=constraints,
            evals=evals,
            seed=seed,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_progress.setText("Progress: 0")
        self._worker.start()

    def stop_optimization(self) -> None:
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(True)

    def _on_progress(self, payload: Dict[str, Any]) -> None:
        idx = payload.get("index", 0)
        best = payload.get("best", {})
        self.lbl_progress.setText(f"Progress: {idx}")
        if best and best.get("vars"):
            self._best_vars = dict(best.get("vars", {}))
            self._update_best_table(best)

    def _on_finished(self, payload: Dict[str, Any]) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if payload and payload.get("vars"):
            self._best_vars = dict(payload.get("vars", {}))
            self._update_best_table(payload)
        self.lbl_progress.setText("Progress: done")

    def _on_failed(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.warning(self, "Optimization", f"Failed: {msg}")

    def _update_best_table(self, payload: Dict[str, Any]) -> None:
        self.table_best.setRowCount(1)
        obj_val = payload.get("objective")
        obj_item = QTableWidgetItem("--" if obj_val is None else f"{obj_val:.4f}")
        obj_item.setFlags(obj_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_best.setItem(0, 0, obj_item)
        for idx, key in enumerate(["P12.x", "P12.y"], start=1):
            val = self._best_vars.get(key)
            item = QTableWidgetItem("--" if val is None else f"{val:.4f}")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_best.setItem(0, idx, item)

    def apply_best(self) -> None:
        if not self._best_vars:
            QMessageBox.information(self, "Optimization", "No best solution yet.")
            return
        for name, val in self._best_vars.items():
            if not name.startswith("P") or "." not in name:
                continue
            pid_str, axis = name[1:].split(".", 1)
            try:
                pid = int(pid_str)
            except Exception:
                continue
            if pid not in self.ctrl.points:
                continue
            point = self.ctrl.points[pid]
            x = point.get("x")
            y = point.get("y")
            if axis == "x":
                x = float(val)
            elif axis == "y":
                y = float(val)
            else:
                continue
            self.ctrl.cmd_move_point_by_table(pid, float(x), float(y))
        if self.ctrl.panel:
            self.ctrl.panel.defer_refresh_all()
