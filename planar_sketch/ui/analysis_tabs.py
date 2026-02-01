# -*- coding: utf-8 -*-
"""Analysis tabs: Animation + Optimization."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QGroupBox,
    QLineEdit,
    QComboBox,
)

from ..core.case_run_manager import CaseRunManager
from ..core.optimization import (
    OptimizationWorker,
    DesignVariable,
    ObjectiveSpec,
    ConstraintSpec,
)


class AnimationTab(QWidget):
    def __init__(self, ctrl: Any, on_active_case_changed=None):
        super().__init__()
        self.ctrl = ctrl
        self._on_active_case_changed = on_active_case_changed
        layout = QVBoxLayout(self)

        self.lbl_active = QLabel("Active Case: --")
        layout.addWidget(self.lbl_active)

        self.table_cases = QTableWidget(0, 4)
        self.table_cases.setHorizontalHeaderLabels(["Name", "Case ID", "Updated", "Created"])
        self.table_cases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_cases.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_cases.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_cases.verticalHeader().setVisible(False)
        layout.addWidget(QLabel("Cases"))
        layout.addWidget(self.table_cases)

        self.table_runs = QTableWidget(0, 6)
        self.table_runs.setHorizontalHeaderLabels(["Run ID", "Success", "Steps", "Success Rate", "Max Hard Err", "Time"])
        self.table_runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_runs.verticalHeader().setVisible(False)
        layout.addWidget(QLabel("Runs"))
        layout.addWidget(self.table_runs)

        btn_row = QHBoxLayout()
        self.btn_open_run = QPushButton("Open Run Folder")
        self.btn_load_snapshot = QPushButton("Load Run Snapshot")
        self.btn_set_active = QPushButton("Set Active Case")
        btn_row.addWidget(self.btn_open_run)
        btn_row.addWidget(self.btn_load_snapshot)
        btn_row.addWidget(self.btn_set_active)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_cases.itemSelectionChanged.connect(self.refresh_runs)
        self.btn_open_run.clicked.connect(self.open_run_folder)
        self.btn_load_snapshot.clicked.connect(self.load_run_snapshot)
        self.btn_set_active.clicked.connect(self.set_active_case)

        self._cases_cache: List[Any] = []
        self._runs_cache: List[Dict[str, Any]] = []
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
        self.table_cases.setRowCount(len(cases))
        for row, info in enumerate(cases):
            items = [
                QTableWidgetItem(info.name),
                QTableWidgetItem(info.case_id),
                QTableWidgetItem(info.updated_utc),
                QTableWidgetItem(info.created_utc),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_cases.setItem(row, col, item)
        active = manager.get_active_case()
        self.lbl_active.setText(f"Active Case: {active or '--'}")
        self.refresh_runs()

    def _selected_case_id(self) -> Optional[str]:
        row = self.table_cases.currentRow()
        if row < 0 or row >= len(self._cases_cache):
            return None
        return self._cases_cache[row].case_id

    def refresh_runs(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            self.table_runs.setRowCount(0)
            return
        manager = self._manager()
        runs = manager.list_runs(case_id)
        self._runs_cache = runs
        self.table_runs.setRowCount(len(runs))
        for row, info in enumerate(runs):
            items = [
                QTableWidgetItem(str(info.get("run_id", ""))),
                QTableWidgetItem(str(info.get("success", ""))),
                QTableWidgetItem(str(info.get("n_steps", ""))),
                QTableWidgetItem(str(info.get("success_rate", ""))),
                QTableWidgetItem(str(info.get("max_hard_err", ""))),
                QTableWidgetItem(str(info.get("updated_utc", ""))),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_runs.setItem(row, col, item)

    def _selected_run(self) -> Optional[Dict[str, Any]]:
        row = self.table_runs.currentRow()
        if row < 0 or row >= len(self._runs_cache):
            return None
        return self._runs_cache[row]

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

        self.table_vars = QTableWidget(0, 5)
        self.table_vars.setHorizontalHeaderLabels(["Enabled", "Variable", "Current", "Lower", "Upper"])
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
        layout.addWidget(self.table_obj)

        self.btn_add_obj.clicked.connect(lambda _checked=False: self.add_objective_row())
        self.btn_del_obj.clicked.connect(self.remove_objective_row)
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
        layout.addWidget(self.table_con)

        self.btn_add_con.clicked.connect(lambda _checked=False: self.add_constraint_row())
        self.btn_del_con.clicked.connect(self.remove_constraint_row)
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

    def _variable_options(self) -> List[str]:
        opts = []
        for pid in sorted(self.ctrl.points.keys()):
            opts.append(f"P{pid}.x")
            opts.append(f"P{pid}.y")
        return opts

    def add_variable_row(self, name: Optional[str] = None) -> None:
        row = self.table_vars.rowCount()
        self.table_vars.insertRow(row)

        enabled_item = QTableWidgetItem()
        enabled_item.setCheckState(Qt.CheckState.Checked)
        self.table_vars.setItem(row, 0, enabled_item)

        combo = QComboBox(self.table_vars)
        opts = self._variable_options()
        combo.addItems(opts)
        if name and name in opts:
            combo.setCurrentText(name)
        elif name:
            combo.addItem(name)
            combo.setCurrentText(name)
        combo.currentTextChanged.connect(lambda _t, r=row: self._update_current_value(r))
        self.table_vars.setCellWidget(row, 1, combo)

        current_item = QTableWidgetItem("--")
        current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_vars.setItem(row, 2, current_item)
        self.table_vars.setItem(row, 3, QTableWidgetItem(""))
        self.table_vars.setItem(row, 4, QTableWidgetItem(""))
        self._update_current_value(row)

    def remove_variable_row(self) -> None:
        row = self.table_vars.currentRow()
        if row >= 0:
            self.table_vars.removeRow(row)

    def _update_current_value(self, row: int) -> None:
        combo = self.table_vars.cellWidget(row, 1)
        if not isinstance(combo, QComboBox):
            return
        name = combo.currentText()
        current = self._get_variable_value(name)
        item = self.table_vars.item(row, 2)
        if item:
            item.setText("--" if current is None else f"{current:.4f}")

    def _get_variable_value(self, name: str) -> Optional[float]:
        name = name.strip()
        if not name.startswith("P") or "." not in name:
            return None
        pid_str, axis = name[1:].split(".", 1)
        try:
            pid = int(pid_str)
        except Exception:
            return None
        if pid not in self.ctrl.points:
            return None
        return float(self.ctrl.points[pid].get(axis, 0.0))

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

    def _collect_variables(self) -> Optional[List[DesignVariable]]:
        variables: List[DesignVariable] = []
        for row in range(self.table_vars.rowCount()):
            enabled_item = self.table_vars.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            combo = self.table_vars.cellWidget(row, 1)
            name = combo.currentText() if isinstance(combo, QComboBox) else ""
            lower_item = self.table_vars.item(row, 3)
            upper_item = self.table_vars.item(row, 4)
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
