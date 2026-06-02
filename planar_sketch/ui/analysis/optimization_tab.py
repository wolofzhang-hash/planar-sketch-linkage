"""OptimizationTab extracted from ui.analysis_tabs during refactor phase-3.
Refactor phase-4: make module self-contained and move plot dialog helper to optimization_widgets.
"""
from __future__ import annotations

import ast
import json
import math
import os
import tempfile
from typing import Any, Dict, List, Optional

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QAbstractItemView,
    QMessageBox,
    QGroupBox,
    QLineEdit,
    QMenu,
    QFileDialog,
    QCheckBox,
    QSizePolicy,
    QScrollArea,
    QFrame,
    QDialog,
)

from ...core.run_service import RunService
from ...core.commands import Command
from ...core.optimization import (
    OptimizationWorker,
    DesignVariable,
    ObjectiveSpec,
    ConstraintSpec,
    build_signals,
    model_variable_signals,
    add_curve_target_signals,
    _apply_design_vars,
)
from ..display_format import format_table_number
from ..expression_builder import (
    ExpressionBuilderDialog,
    load_global_expression_builder_template_overrides,
    save_global_expression_builder_template_overrides,
)
from ..i18n import tr, get_ui_language
from ..table_context_menu import bind_optimization_table_context_menus
from .optimization_widgets import _OptimizationPlotsDialog


def _lang(owner) -> str:
    ctrl = getattr(owner, "ctrl", owner)
    return get_ui_language(ctrl, fallback="zh")


def _tr(owner, key: str, **kwargs) -> str:
    return tr(_lang(owner), key, **kwargs)


def _is_zh(owner) -> bool:
    return _lang(owner) == "zh"


class OptimizationTab(QWidget):
    def __init__(self, ctrl: Any, run_service: Optional[RunService] = None):
        super().__init__()
        self.ctrl = ctrl
        self._run_service = run_service or RunService(ctrl)
        self._worker: Optional[OptimizationWorker] = None
        self._best_vars: Dict[str, float] = {}
        self._best_var_names: List[str] = []
        self._progress_value = "--"
        self._best_score_hist: List[float] = []
        self._best_obj_hist: List[float] = []
        # Whether the last completed optimization run satisfied constraints.
        self._last_run_feasible: bool = False
        self._planned_evals: int = 0
        self._convergence_text: str = ""
        # Detached plots dialog is lazily created, but the attribute must exist
        # before apply_language() runs during startup.
        self._plots_dialog: Optional[_OptimizationPlotsDialog] = None

        layout = QVBoxLayout(self)

        # --- Active case selector (top) ---
        # The tables below support per-row case selection, but users need an obvious way
        # to see/select the active case context. This combo also provides a sensible
        # default when adding new rows.
        self._active_case_id: Optional[str] = None
        self._last_finished_payload: Optional[Dict[str, Any]] = None
        case_row = QHBoxLayout()
        self.lbl_active = QLabel("")
        self.combo_active_case = QComboBox(self)
        self.combo_active_case.setMinimumWidth(280)
        case_row.addWidget(self.lbl_active)
        case_row.addWidget(self.combo_active_case)
        case_row.addStretch(1)
        layout.addLayout(case_row)

        # Make the long sections scrollable, while keeping the run controls
        # always visible (so the user doesn't need to resize the window just
        # to click "Run").
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_body = QWidget(self)
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(self._build_variables_group())
        scroll_layout.addWidget(self._build_objectives_group())
        scroll_layout.addWidget(self._build_constraints_group())
        scroll_layout.addStretch(1)
        self._scroll.setWidget(scroll_body)

        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._build_run_group())

        self.apply_language()
        self.refresh_case_label()
        self.ensure_defaults()

        self.combo_active_case.currentIndexChanged.connect(self._on_active_case_changed)

        bind_optimization_table_context_menus(self)

    def preferred_panel_width(self) -> int:
        # Optimization tables need materially more width in zh labels.
        return 860


    def _on_active_case_changed(self) -> None:
        data = self.combo_active_case.currentData()
        self._active_case_id = str(data) if data else None
        # If a result plot is already open/available, refresh it immediately when the
        # case selector changes so the target curve matches the selected case.
        try:
            if isinstance(self._last_finished_payload, dict) and self._last_finished_payload:
                self._update_curve_compare(self._last_finished_payload)
        except Exception:
            pass

    def _refresh_active_case_combo(self, preferred_case_id: Optional[str] = None) -> None:
        current = self.combo_active_case.currentData()
        self.combo_active_case.blockSignals(True)
        self.combo_active_case.clear()
        # Default option means: apply to all cases / no filtering
        self.combo_active_case.addItem(_tr(self, "analysis.all_cases"), None)
        options = self._case_options()
        for label, case_id in options:
            self.combo_active_case.addItem(label, case_id)

        # Selection priority:
        # 1) explicit preferred_case_id (used by intelligent synthesis preset/apply paths)
        # 2) previous selection (if still exists)
        # 3) newest case (first actual option)
        # 4) All cases
        selected_idx = -1
        if preferred_case_id is not None:
            selected_idx = self.combo_active_case.findData(str(preferred_case_id))
        if selected_idx < 0 and current is not None:
            selected_idx = self.combo_active_case.findData(current)
        if selected_idx < 0:
            selected_idx = 1 if options else 0
        self.combo_active_case.setCurrentIndex(selected_idx)
        self.combo_active_case.blockSignals(False)

        # Keep internal cache in sync even when signals are blocked during repopulation.
        data = self.combo_active_case.currentData()
        self._active_case_id = str(data) if data else None

    def _preferred_case_id_from_preset(self, preset: Dict[str, Any]) -> Optional[str]:
        try:
            for row in list(preset.get("objectives", []) or []):
                cid = row.get("case_id") if isinstance(row, dict) else None
                if cid:
                    return str(cid)
            for row in list(preset.get("constraints", []) or []):
                cid = row.get("case_id") if isinstance(row, dict) else None
                if cid:
                    return str(cid)
        except Exception:
            pass
        return None

    def apply_preset(self, preset: Dict[str, Any]) -> None:
        """Apply an optimization preset (typically generated by intelligent template insertion)."""
        try:
            variables = list(preset.get("variables", []) or [])
            objectives = list(preset.get("objectives", []) or [])
            constraints = list(preset.get("constraints", []) or [])

            # Ensure case lists reflect newly created/updated cases and prefer the preset case
            # so optimization plots/objective context follow the latest intelligent synthesis curve.
            preferred_case_id = self._preferred_case_id_from_preset(preset)
            self._set_cases_label(self._case_label_text())
            self._refresh_active_case_combo(preferred_case_id=preferred_case_id)

            # Clear existing rows
            self.table_vars.setRowCount(0)
            self.table_obj.setRowCount(0)
            self.table_con.setRowCount(0)

            # Variables
            for v in variables:
                name = str(v.get("name", "")).strip() or None
                self.add_variable_row(name=name)
                row = self.table_vars.rowCount() - 1
                enabled_item = self.table_vars.item(row, 0)
                if enabled_item:
                    enabled_item.setCheckState(Qt.CheckState.Checked if bool(v.get("enabled", True)) else Qt.CheckState.Unchecked)
                case_id = v.get("case_id")
                case_combo = self.table_vars.cellWidget(row, 1)
                if isinstance(case_combo, QComboBox) and case_id:
                    idx = case_combo.findData(str(case_id))
                    if idx >= 0:
                        case_combo.setCurrentIndex(idx)
                lower_item = self.table_vars.item(row, 5)
                upper_item = self.table_vars.item(row, 6)
                if lower_item is not None:
                    lower_item.setText(str(v.get("lower", "")))
                if upper_item is not None:
                    upper_item.setText(str(v.get("upper", "")))
                self._update_current_value(row)

            # Objectives
            for o in objectives:
                self.add_objective_row(direction=str(o.get("direction", "min")), expression=str(o.get("expression", "")))
                row = self.table_obj.rowCount() - 1
                enabled_item = self.table_obj.item(row, 0)
                if enabled_item:
                    enabled_item.setCheckState(Qt.CheckState.Checked if bool(o.get("enabled", True)) else Qt.CheckState.Unchecked)
                case_id = o.get("case_id")
                case_combo = self.table_obj.cellWidget(row, 1)
                if isinstance(case_combo, QComboBox) and case_id:
                    idx = case_combo.findData(str(case_id))
                    if idx >= 0:
                        case_combo.setCurrentIndex(idx)

            # Constraints
            for c in constraints:
                self.add_constraint_row(
                    expression=str(c.get("expression", "")),
                    comparator=str(c.get("comparator", "<=")),
                    limit=str(c.get("limit", "")),
                )
                row = self.table_con.rowCount() - 1
                enabled_item = self.table_con.item(row, 0)
                if enabled_item:
                    enabled_item.setCheckState(Qt.CheckState.Checked if bool(c.get("enabled", True)) else Qt.CheckState.Unchecked)
                case_id = c.get("case_id")
                case_combo = self.table_con.cellWidget(row, 1)
                if isinstance(case_combo, QComboBox) and case_id:
                    idx = case_combo.findData(str(case_id))
                    if idx >= 0:
                        case_combo.setCurrentIndex(idx)

            run_cfg = preset.get("run", {}) or {}
            if "evals" in run_cfg:
                self.ed_evals.setText(str(run_cfg.get("evals")))

            # Refresh best table headers based on enabled vars.
            self._set_best_table_headers(self._collect_enabled_variable_names())
            self._refresh_initial_row()
            self._refresh_best_objective_display()
        except Exception:
            return

    def _build_variables_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_vars = group
        layout = QVBoxLayout(group)
        self.table_vars = QTableWidget(0, 7)
        self.table_vars.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_vars.verticalHeader().setVisible(False)
        self.table_vars.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_vars.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_vars.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_vars.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_vars.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.table_vars)
        self.table_vars.customContextMenuRequested.connect(self._open_variable_context_menu)
        return group

    def _build_objectives_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_obj = group
        layout = QVBoxLayout(group)
        self.table_obj = QTableWidget(0, 4)
        self.table_obj.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_obj.verticalHeader().setVisible(False)
        self.table_obj.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_obj.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_obj.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.table_obj)

        self.table_obj.customContextMenuRequested.connect(self._open_objective_context_menu)
        return group

    def _build_constraints_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_con = group
        layout = QVBoxLayout(group)
        self.table_con = QTableWidget(0, 5)
        self.table_con.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_con.verticalHeader().setVisible(False)
        self.table_con.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_con.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_con.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.table_con)

        self.table_con.customContextMenuRequested.connect(self._open_constraint_context_menu)
        return group

    def _build_run_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_run = group
        layout = QVBoxLayout(group)

        self._run_toggle_bar = QWidget(group)
        toggle_run_row = QHBoxLayout(self._run_toggle_bar)
        toggle_run_row.setContentsMargins(0, 0, 0, 0)
        self.btn_toggle_run = QPushButton("")
        self.btn_toggle_run.setCheckable(True)
        self.btn_toggle_run.setChecked(False)
        self.btn_toggle_run.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        toggle_run_row.addWidget(self.btn_toggle_run)
        toggle_run_row.addStretch(1)
        layout.addWidget(self._run_toggle_bar)

        self._run_group_content = QWidget(group)
        content_layout = QVBoxLayout(self._run_group_content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self.lbl_evals = QLabel("")
        row.addWidget(self.lbl_evals)
        self.ed_evals = QLineEdit("50")
        self.ed_evals.setMaximumWidth(80)
        row.addWidget(self.ed_evals)
        self.chk_debug_log = QCheckBox("")
        self.lbl_debug_log_path = QLabel("")
        self.ed_debug_log_path = QLineEdit("")
        self.ed_debug_log_path.setReadOnly(True)
        row.addWidget(self.chk_debug_log)
        row.addWidget(self.lbl_debug_log_path)
        row.addWidget(self.ed_debug_log_path, 1)
        self.input_fields = [self.ed_evals]
        row.addStretch(1)
        content_layout.addLayout(row)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("")
        self.btn_stop = QPushButton("")
        # Styling hooks for the global theme (see common_ui/theme.py)
        self.btn_run.setProperty("primary", True)
        self.btn_stop.setProperty("danger", True)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        self.btn_apply_selected = QPushButton("")
        btn_row.addWidget(self.btn_apply_selected)
        self.btn_open_plots = QPushButton("")
        btn_row.addWidget(self.btn_open_plots)
        btn_row.addStretch(1)
        content_layout.addLayout(btn_row)

        self.lbl_statusbar = QLabel("")
        self.lbl_statusbar.setWordWrap(False)
        # Keep legacy attribute names for compatibility with existing methods.
        self.lbl_convergence = self.lbl_statusbar
        self.lbl_progress = self.lbl_statusbar
        content_layout.addWidget(self.lbl_statusbar)

        self._results_toggle_bar = QWidget(self._run_group_content)
        toggle_results_row = QHBoxLayout(self._results_toggle_bar)
        toggle_results_row.setContentsMargins(0, 0, 0, 0)
        self.btn_toggle_results = QPushButton("")
        self.btn_toggle_results.setCheckable(True)
        self.btn_toggle_results.setChecked(False)
        self.btn_toggle_results.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        toggle_results_row.addWidget(self.btn_toggle_results)
        toggle_results_row.addStretch(1)
        content_layout.addWidget(self._results_toggle_bar)

        self.table_best = QTableWidget(0, 3)
        self.table_best.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_best.verticalHeader().setVisible(True)
        self.table_best.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_best.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_best.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table_best.setMinimumHeight(72)
        self.table_best.setMaximumHeight(92)
        content_layout.addWidget(self.table_best)
        self.table_best.setVisible(False)
        layout.addWidget(self._run_group_content)

        self.btn_run.clicked.connect(self.run_optimization)
        self.btn_stop.clicked.connect(self.stop_optimization)
        self.btn_apply_selected.clicked.connect(self.apply_selected)
        self.btn_open_plots.clicked.connect(self.open_result_plots)
        self.btn_toggle_run.toggled.connect(self._on_toggle_run_group)
        self.btn_toggle_results.toggled.connect(self._on_toggle_results_table)
        self.chk_debug_log.toggled.connect(self._on_debug_log_toggled)
        self.btn_stop.setEnabled(False)
        self._on_debug_log_toggled(self.chk_debug_log.isChecked())
        self._on_toggle_run_group(self.btn_toggle_run.isChecked())
        return group

    def _project_dir(self) -> str:
        return self._run_service.project_dir()

    def _manager(self):
        return self._run_service.manager()

    def _case_label_text(self) -> str:
        cases = self._manager().list_cases()
        if not cases:
            return "--"
        return _tr(self, "analysis.all_cases")

    def _case_options(self) -> List[tuple[str, str]]:
        options: List[tuple[str, str]] = []
        for case in self._manager().list_cases():
            label = str(getattr(case, "label", case.name))
            options.append((label, str(case.name)))
        return options

    def _case_combo(self, parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItem(_tr(self, "analysis.all_cases"), None)
        for label, case_id in self._case_options():
            combo.addItem(label, case_id)
        return combo

    def _refresh_case_combo_options(self, table: QTableWidget, column: int) -> None:
        options = self._case_options()
        for row in range(table.rowCount()):
            combo = table.cellWidget(row, column)
            if not isinstance(combo, QComboBox):
                continue
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_tr(self, "analysis.all_cases"), None)
            for label, case_id in options:
                combo.addItem(label, case_id)
            if current_data is None:
                combo.setCurrentIndex(0)
            else:
                index = combo.findData(current_data)
                combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _case_ids_from_combo(self, combo: Optional[QComboBox]) -> Optional[List[str]]:
        if not isinstance(combo, QComboBox):
            return None
        data = combo.currentData()
        if data is None:
            return None
        return [str(data)]

    def refresh_case_label(self) -> None:
        self._set_cases_label(self._case_label_text())
        self._refresh_active_case_combo(preferred_case_id=None)

    def refresh_active_case(self) -> None:
        self.refresh_case_label()
        self._refresh_case_combo_options(self.table_vars, 1)
        self._refresh_case_combo_options(self.table_obj, 1)
        self._refresh_case_combo_options(self.table_con, 1)
        self.refresh_model_values()

    def refresh_model_values(self) -> None:
        for row in range(self.table_vars.rowCount()):
            self._update_current_value(row)
        if self.table_best.rowCount() == 0:
            self.table_best.setRowCount(2)
        self._refresh_best_objective_display()
        self._refresh_initial_row()

    def apply_language(self) -> None:
        lang = _lang(self)
        self._set_cases_label(self._case_label_text())
        self.group_vars.setTitle(_tr(self, "analysis.design_variables"))
        self.group_obj.setTitle(_tr(self, "analysis.objectives"))
        self.group_con.setTitle(_tr(self, "analysis.constraints"))
        self.group_run.setTitle("")
        self.lbl_evals.setText(_tr(self, "analysis.evals"))
        self.chk_debug_log.setText(_tr(self, "analysis.debug_log_enable"))
        self.lbl_debug_log_path.setText("")
        self.ed_debug_log_path.setPlaceholderText("logs/optimization_debug.log")
        self.btn_run.setText(_tr(self, "analysis.run"))
        self.btn_stop.setText(_tr(self, "analysis.stop"))
        self.btn_apply_selected.setText(_tr(self, "analysis.apply_selected"))
        self.btn_open_plots.setText("查看结果图" if _is_zh(self) else "Open Plots")
        self._update_results_toggle_text()
        self._update_run_toggle_text()
        if self._plots_dialog is not None:
            self._plots_dialog.apply_language(lang)
        self._set_progress_label(self._progress_value)
        self.table_vars.setHorizontalHeaderLabels(
            [
                _tr(self, "table.enabled"),
                _tr(self, "analysis.case"),
                _tr(self, "analysis.variable_type"),
                _tr(self, "analysis.variable_name"),
                _tr(self, "analysis.variable_current"),
                _tr(self, "analysis.variable_lower"),
                _tr(self, "analysis.variable_upper"),
            ]
        )
        self.table_obj.setHorizontalHeaderLabels(
            [
                _tr(self, "table.enabled"),
                _tr(self, "analysis.case"),
                _tr(self, "analysis.direction"),
                _tr(self, "analysis.expression"),
            ]
        )
        self.table_con.setHorizontalHeaderLabels(
            [
                _tr(self, "table.enabled"),
                _tr(self, "analysis.case"),
                _tr(self, "analysis.expression"),
                _tr(self, "analysis.comparator"),
                _tr(self, "analysis.limit"),
            ]
        )
        self._set_best_table_headers(self._best_var_names or self._collect_enabled_variable_names())
        self._configure_layout_width_hints()

    def _configure_layout_width_hints(self) -> None:
        try:
            self.combo_active_case.setMinimumWidth(360)
        except Exception:
            pass
        for t in (getattr(self, 'table_vars', None), getattr(self, 'table_obj', None), getattr(self, 'table_con', None), getattr(self, 'table_best', None)):
            if not isinstance(t, QTableWidget):
                continue
            t.setMinimumWidth(760)
            hh = t.horizontalHeader()
            try:
                hh.setMinimumSectionSize(36)
            except Exception:
                pass
        try:
            hh = self.table_vars.horizontalHeader()
            modes = {0: QHeaderView.ResizeMode.ResizeToContents, 1: QHeaderView.ResizeMode.Interactive, 2: QHeaderView.ResizeMode.ResizeToContents, 3: QHeaderView.ResizeMode.Stretch, 4: QHeaderView.ResizeMode.Interactive, 5: QHeaderView.ResizeMode.Interactive, 6: QHeaderView.ResizeMode.Interactive}
            for c,m in modes.items(): hh.setSectionResizeMode(c,m)
            for c,w in ((1,150),(4,120),(5,110),(6,110)): hh.resizeSection(c,w)
        except Exception:
            pass
        try:
            hh = self.table_obj.horizontalHeader()
            modes = {0: QHeaderView.ResizeMode.ResizeToContents, 1: QHeaderView.ResizeMode.Interactive, 2: QHeaderView.ResizeMode.ResizeToContents, 3: QHeaderView.ResizeMode.Stretch}
            for c,m in modes.items(): hh.setSectionResizeMode(c,m)
            hh.resizeSection(1, 150)
        except Exception:
            pass
        try:
            hh = self.table_con.horizontalHeader()
            modes = {0: QHeaderView.ResizeMode.ResizeToContents, 1: QHeaderView.ResizeMode.Interactive, 2: QHeaderView.ResizeMode.Stretch, 3: QHeaderView.ResizeMode.ResizeToContents, 4: QHeaderView.ResizeMode.Interactive}
            for c,m in modes.items(): hh.setSectionResizeMode(c,m)
            hh.resizeSection(1, 150); hh.resizeSection(4, 90)
        except Exception:
            pass

    def reset_state(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._best_vars = {}
        self._set_progress_label("--")
        self.table_vars.setRowCount(0)
        self.table_obj.setRowCount(0)
        self.table_con.setRowCount(0)
        self.table_best.setRowCount(0)

    def _set_cases_label(self, text: str) -> None:
        # Keep the top label simple; the combo box shows the selectable cases.
        self.lbl_active.setText(_tr(self, "analysis.case") + ":")

    def _set_progress_label(self, value: str) -> None:
        self._progress_value = value
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        progress_text = _tr(self, "analysis.progress").format(value=self._progress_value)
        conv = (self._convergence_text or "").strip()
        text = f"{progress_text}    |    {conv}" if conv else progress_text
        try:
            self.lbl_statusbar.setText(text)
        except Exception:
            pass

    def _on_toggle_results_table(self, checked: bool) -> None:
        self.table_best.setVisible(bool(checked))
        self._update_results_toggle_text()

    def _update_results_toggle_text(self) -> None:
        lang = _lang(self)
        checked = bool(getattr(self, 'btn_toggle_results', None) and self.btn_toggle_results.isChecked())
        if lang == 'zh':
            self.btn_toggle_results.setText(("收起结果表 ▲" if checked else "展开结果表 ▼"))
        else:
            self.btn_toggle_results.setText(("Hide Results ▲" if checked else "Show Results ▼"))
        try:
            self.btn_toggle_results.setMinimumWidth(180)
            self.btn_toggle_results.setMaximumWidth(220)
        except Exception:
            pass


    def _on_toggle_run_group(self, checked: bool) -> None:
        if hasattr(self, "_run_group_content") and self._run_group_content is not None:
            visible = bool(checked)
            self._run_group_content.setVisible(visible)
            try:
                self._run_group_content.setMaximumHeight(16777215 if visible else 0)
                self._run_group_content.setMinimumHeight(0)
                self._run_group_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred if visible else QSizePolicy.Policy.Fixed)
            except Exception:
                pass
        self._update_run_toggle_text()
        try:
            if hasattr(self, 'group_run') and self.group_run is not None:
                self.group_run.updateGeometry()
                self.group_run.adjustSize()
                self.group_run.update()
        except Exception:
            pass

    def _update_run_toggle_text(self) -> None:
        lang = _lang(self)
        checked = bool(getattr(self, "btn_toggle_run", None) and self.btn_toggle_run.isChecked())
        if _is_zh(self):
            self.btn_toggle_run.setText("收起优化运行 ▲" if checked else "展开优化运行 ▼")
        else:
            self.btn_toggle_run.setText("Hide Optimization Run ▲" if checked else "Show Optimization Run ▼")
        try:
            self.btn_toggle_run.setMinimumWidth(180)
            self.btn_toggle_run.setMaximumWidth(220)
            self.btn_toggle_run.setVisible(True)
        except Exception:
            pass

    def _on_debug_log_toggled(self, checked: bool) -> None:
        self.ed_debug_log_path.setReadOnly(not checked)
        if checked and not (self.ed_debug_log_path.text() or "").strip():
            self.ed_debug_log_path.setText(os.path.join(self._project_dir(), "logs", "optimization_debug.log"))

    def ensure_defaults(self) -> None:
        # Do not auto-insert dummy optimization rows. A preset (from intelligent synthesis)
        # or the user should define variables/objectives/constraints explicitly.
        self._set_best_table_headers(self._collect_enabled_variable_names())

    def export_settings(self) -> Dict[str, Any]:
        variables: List[Dict[str, Any]] = []
        for row in range(self.table_vars.rowCount()):
            enabled_item = self.table_vars.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_vars.cellWidget(row, 1)
            case_id = case_combo.currentData() if isinstance(case_combo, QComboBox) else None
            type_combo = self.table_vars.cellWidget(row, 2)
            var_type = type_combo.currentText() if isinstance(type_combo, QComboBox) else ""
            name_combo = self.table_vars.cellWidget(row, 3)
            name = name_combo.currentText() if isinstance(name_combo, QComboBox) else ""
            lower_item = self.table_vars.item(row, 5)
            upper_item = self.table_vars.item(row, 6)
            variables.append(
                {
                    "enabled": enabled,
                    "case_id": case_id,
                    "var_type": var_type,
                    "name": name,
                    "lower": lower_item.text() if lower_item else "",
                    "upper": upper_item.text() if upper_item else "",
                }
            )

        objectives: List[Dict[str, Any]] = []
        for row in range(self.table_obj.rowCount()):
            enabled_item = self.table_obj.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_obj.cellWidget(row, 1)
            case_id = case_combo.currentData() if isinstance(case_combo, QComboBox) else None
            direction_combo = self.table_obj.cellWidget(row, 2)
            direction = direction_combo.currentText() if isinstance(direction_combo, QComboBox) else "min"
            expr_item = self.table_obj.item(row, 3)
            objectives.append(
                {
                    "enabled": enabled,
                    "case_id": case_id,
                    "direction": direction,
                    "expression": expr_item.text() if expr_item else "",
                }
            )

        constraints: List[Dict[str, Any]] = []
        for row in range(self.table_con.rowCount()):
            enabled_item = self.table_con.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_con.cellWidget(row, 1)
            case_id = case_combo.currentData() if isinstance(case_combo, QComboBox) else None
            expr_item = self.table_con.item(row, 2)
            comparator_combo = self.table_con.cellWidget(row, 3)
            comparator = comparator_combo.currentText() if isinstance(comparator_combo, QComboBox) else "<="
            limit_item = self.table_con.item(row, 4)
            constraints.append(
                {
                    "enabled": enabled,
                    "case_id": case_id,
                    "expression": expr_item.text() if expr_item else "",
                    "comparator": comparator,
                    "limit": limit_item.text() if limit_item else "",
                }
            )

        return {
            "evals": self.ed_evals.text(),
            "debug_log": {
                "enabled": bool(self.chk_debug_log.isChecked()),
                "path": self.ed_debug_log_path.text(),
            },
            "variables": variables,
            "objectives": objectives,
            "constraints": constraints,
            "expression_builder": {
                "templates": list(getattr(self, "_opt_expr_templates", []) or []),
                "template_help": dict(getattr(self, "_opt_expr_template_help", {}) or {}),
            },
        }

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        if not isinstance(settings, dict) or not settings:
            return
        self.table_vars.setRowCount(0)
        self.table_obj.setRowCount(0)
        self.table_con.setRowCount(0)

        expr_builder = settings.get("expression_builder", {}) or {}
        tmpl_list = expr_builder.get("templates")
        if isinstance(tmpl_list, list):
            self._opt_expr_templates = [str(x) for x in tmpl_list if str(x).strip()]
        tmpl_help = expr_builder.get("template_help")
        if isinstance(tmpl_help, dict):
            self._opt_expr_template_help = {str(k): str(v) for k, v in tmpl_help.items() if str(k).strip()}

        for var in settings.get("variables", []) or []:
            name = var.get("name")
            self.add_variable_row(name)
            row = self.table_vars.rowCount() - 1
            enabled_item = self.table_vars.item(row, 0)
            if enabled_item:
                enabled_item.setCheckState(Qt.CheckState.Checked if var.get("enabled", True) else Qt.CheckState.Unchecked)
            self._set_case_combo_value(self.table_vars.cellWidget(row, 1), var.get("case_id"))
            type_combo = self.table_vars.cellWidget(row, 2)
            if isinstance(type_combo, QComboBox) and var.get("var_type"):
                type_combo.setCurrentText(str(var.get("var_type")))
                self._apply_variable_type(row, type_combo.currentText())
            name_combo = self.table_vars.cellWidget(row, 3)
            if isinstance(name_combo, QComboBox) and name:
                opts = [name_combo.itemText(i) for i in range(name_combo.count())]
                if name not in opts:
                    name_combo.addItem(name)
                name_combo.setCurrentText(name)
            lower_item = self.table_vars.item(row, 5)
            upper_item = self.table_vars.item(row, 6)
            if lower_item is not None:
                lower_item.setText(str(var.get("lower", "")))
            if upper_item is not None:
                upper_item.setText(str(var.get("upper", "")))
            self._update_current_value(row)

        for obj in settings.get("objectives", []) or []:
            self.add_objective_row(direction=str(obj.get("direction", "min")), expression=str(obj.get("expression", "")))
            row = self.table_obj.rowCount() - 1
            enabled_item = self.table_obj.item(row, 0)
            if enabled_item:
                enabled_item.setCheckState(Qt.CheckState.Checked if obj.get("enabled", True) else Qt.CheckState.Unchecked)
            self._set_case_combo_value(self.table_obj.cellWidget(row, 1), obj.get("case_id"))

        for con in settings.get("constraints", []) or []:
            self.add_constraint_row(
                expression=str(con.get("expression", "")),
                comparator=str(con.get("comparator", "<=")),
                limit=str(con.get("limit", "")),
            )
            row = self.table_con.rowCount() - 1
            enabled_item = self.table_con.item(row, 0)
            if enabled_item:
                enabled_item.setCheckState(Qt.CheckState.Checked if con.get("enabled", True) else Qt.CheckState.Unchecked)
            self._set_case_combo_value(self.table_con.cellWidget(row, 1), con.get("case_id"))

        if "evals" in settings:
            self.ed_evals.setText(str(settings.get("evals", "")))
        debug_log = settings.get("debug_log", {}) or {}
        self.chk_debug_log.setChecked(bool(debug_log.get("enabled", False)))
        self.ed_debug_log_path.setText(str(debug_log.get("path", "")))
        self._on_debug_log_toggled(self.chk_debug_log.isChecked())

        self._set_best_table_headers(self._collect_enabled_variable_names())
        self.refresh_model_values()

    def _set_case_combo_value(self, combo: Optional[QComboBox], case_id: Any) -> None:
        if not isinstance(combo, QComboBox):
            return
        combo.blockSignals(True)
        if case_id is None:
            combo.setCurrentIndex(0)
        else:
            idx = combo.findData(case_id)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _variable_type_options(self) -> List[str]:
        return ["Coordinate", "Length", "Parameter", "Constraint", "All"]

    def _variable_options_for_type(self, var_type: str) -> List[str]:
        coords = []
        for pid in sorted(self.ctrl.points.keys()):
            coords.append(f"P{pid}.x")
            coords.append(f"P{pid}.y")
        lengths = [f"Link{lid}.L" for lid in sorted(self.ctrl.links.keys())]
        params = [f"Param.{name}" for name in sorted(self.ctrl.parameters.params.keys())]
        offsets = [
            f"PointLine{plid}.s"
            for plid, pl in sorted(getattr(self.ctrl, "point_lines", {}).items(), key=lambda kv: kv[0])
            if "s" in pl
        ]
        if var_type == "Coordinate":
            return coords
        if var_type == "Length":
            return lengths
        if var_type == "Parameter":
            return params
        if var_type == "Constraint":
            return offsets
        return coords + lengths + params + offsets

    def _infer_variable_type(self, name: Optional[str]) -> str:
        if not name:
            return "Coordinate"
        if name.startswith("P") and "." in name:
            return "Coordinate"
        if name.startswith("Link") and name.endswith(".L"):
            return "Length"
        if name.startswith("Param."):
            return "Parameter"
        if name.startswith("PointLine") and name.endswith(".s"):
            return "Constraint"
        return "Coordinate"

    def _row_for_table_widget(self, table: QTableWidget, widget: Optional[QComboBox], columns: List[int]) -> int:
        if widget is None:
            return -1
        index = table.indexAt(widget.pos())
        if index.isValid():
            return index.row()
        for row in range(table.rowCount()):
            for col in columns:
                if table.cellWidget(row, col) is widget:
                    return row
        return -1

    def _collect_enabled_variable_names(self) -> List[str]:
        names: List[str] = []
        for row in range(self.table_vars.rowCount()):
            enabled_item = self.table_vars.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            if not enabled:
                continue
            combo = self.table_vars.cellWidget(row, 3)
            if not isinstance(combo, QComboBox):
                continue
            name = combo.currentText().strip()
            if name:
                names.append(name)
        return names

    def _set_best_table_headers(self, var_names: List[str]) -> None:
        self._best_var_names = list(var_names)
        headers = [_tr(self, "analysis.best_objective")] + self._best_var_names
        self.table_best.setColumnCount(len(headers))
        self.table_best.setHorizontalHeaderLabels(headers)
        self.table_best.setRowCount(2)
        self.table_best.setVerticalHeaderLabels([_tr(self, "analysis.initial_values"), _tr(self, "analysis.best_values")])

    def _on_variable_type_changed(self, var_type: str) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        row = self._row_for_table_widget(self.table_vars, combo, [2])
        if row < 0:
            return
        self._apply_variable_type(row, var_type)

    def _on_variable_name_changed(self) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        row = self._row_for_table_widget(self.table_vars, combo, [3])
        if row < 0:
            return
        self._update_current_value(row)

    def add_variable_row(self, name: Optional[str] = None) -> None:
        row = self.table_vars.rowCount()
        self.table_vars.insertRow(row)

        enabled_item = QTableWidgetItem()
        enabled_item.setCheckState(Qt.CheckState.Checked)
        self.table_vars.setItem(row, 0, enabled_item)

        case_combo = self._case_combo(self.table_vars)
        if getattr(self, "_active_case_id", None):
            idx = case_combo.findData(self._active_case_id)
            if idx >= 0:
                case_combo.setCurrentIndex(idx)
        self.table_vars.setCellWidget(row, 1, case_combo)

        type_combo = QComboBox(self.table_vars)
        type_combo.addItems(self._variable_type_options())
        type_combo.setCurrentText(self._infer_variable_type(name))
        type_combo.currentTextChanged.connect(self._on_variable_type_changed)
        self.table_vars.setCellWidget(row, 2, type_combo)

        combo = QComboBox(self.table_vars)
        opts = self._variable_options_for_type(type_combo.currentText())
        combo.addItems(opts)
        if name and name in opts:
            combo.setCurrentText(name)
        elif name:
            combo.addItem(name)
            combo.setCurrentText(name)
        combo.currentTextChanged.connect(self._on_variable_name_changed)
        self.table_vars.setCellWidget(row, 3, combo)

        current_item = QTableWidgetItem("--")
        current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_vars.setItem(row, 4, current_item)
        self.table_vars.setItem(row, 5, QTableWidgetItem(""))
        self.table_vars.setItem(row, 6, QTableWidgetItem(""))
        self._update_current_value(row)

    def remove_variable_row(self) -> None:
        row = self.table_vars.currentRow()
        if row >= 0:
            self.table_vars.removeRow(row)

    def _update_current_value(self, row: int) -> None:
        combo = self.table_vars.cellWidget(row, 3)
        if not isinstance(combo, QComboBox):
            return
        name = combo.currentText()
        current = self._get_variable_value(name)
        item = self.table_vars.item(row, 4)
        if item:
            item.setText(format_table_number(current))

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
            if name.startswith("PointLine") and name.endswith(".s"):
                plid_str = name[len("PointLine") : -len(".s")]
                try:
                    plid = int(plid_str)
                except Exception:
                    return None
                pl = getattr(self.ctrl, "point_lines", {}).get(plid)
                if not pl or "s" not in pl:
                    return None
                return float(pl.get("s", 0.0))
            return None
        pid_str, axis = name[1:].split(".", 1)
        try:
            pid = int(pid_str)
        except Exception:
            return None
        if pid not in self.ctrl.points:
            return None
        return float(self.ctrl.points[pid].get(axis, 0.0))

    def _apply_variable_type(self, row: int, var_type: str) -> None:
        combo = self.table_vars.cellWidget(row, 3)
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

        case_combo = self._case_combo(self.table_obj)
        if getattr(self, "_active_case_id", None):
            idx = case_combo.findData(self._active_case_id)
            if idx >= 0:
                case_combo.setCurrentIndex(idx)
        self.table_obj.setCellWidget(row, 1, case_combo)

        combo = QComboBox(self.table_obj)
        combo.addItems(["min", "max"])
        combo.setCurrentText(direction)
        self.table_obj.setCellWidget(row, 2, combo)
        self.table_obj.setItem(row, 3, QTableWidgetItem(expression))

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

        case_combo = self._case_combo(self.table_con)
        if getattr(self, "_active_case_id", None):
            idx = case_combo.findData(self._active_case_id)
            if idx >= 0:
                case_combo.setCurrentIndex(idx)
        self.table_con.setCellWidget(row, 1, case_combo)

        self.table_con.setItem(row, 2, QTableWidgetItem(expression))
        combo = QComboBox(self.table_con)
        combo.addItems(["<=", ">="])
        combo.setCurrentText(comparator)
        self.table_con.setCellWidget(row, 3, combo)
        self.table_con.setItem(row, 4, QTableWidgetItem(limit))

    def remove_constraint_row(self) -> None:
        row = self.table_con.currentRow()
        if row >= 0:
            self.table_con.removeRow(row)

    def insert_text_into_current_expression_cell(self, text: str) -> bool:
        text = str(text or '')
        if not text:
            return False
        # Objective expression column = 3
        row_o = self.table_obj.currentRow()
        col_o = self.table_obj.currentColumn()
        if row_o >= 0 and col_o == 3:
            it = self.table_obj.item(row_o, 3)
            if it is None:
                it = QTableWidgetItem('')
                self.table_obj.setItem(row_o, 3, it)
            it.setText((it.text() or '') + text)
            self.table_obj.setCurrentCell(row_o, 3)
            return True
        row_c = self.table_con.currentRow()
        col_c = self.table_con.currentColumn()
        if row_c >= 0 and col_c == 2:
            it = self.table_con.item(row_c, 2)
            if it is None:
                it = QTableWidgetItem('')
                self.table_con.setItem(row_c, 2, it)
            it.setText((it.text() or '') + text)
            self.table_con.setCurrentCell(row_c, 2)
            return True
        # fallback: if any selected row exists, prefer objective then constraint
        if row_o >= 0:
            self.table_obj.setCurrentCell(row_o, 3)
            return self.insert_text_into_current_expression_cell(text)
        if row_c >= 0:
            self.table_con.setCurrentCell(row_c, 2)
            return self.insert_text_into_current_expression_cell(text)
        return False

    def _optimization_functions(self) -> Dict[str, List[str]]:
        return {
            "Curve Compare": [
                "curve_rms_err(",
                "curve_max_abs_err(",
                "curve_diff(",
                "curve_abs_diff(",
                "curve_sq_diff(",
            ],
            "Curve Analysis": [
                "curve_value_at(",
                "curve_monotonic_violation(",
                "curve_max(",
                "curve_min(",
                "curve_mean(",
            ],
            "Aggregates": ["max(", "min(", "mean(", "rms(", "abs(", "first(", "last("],
            "Operators": ["+", "-", "*", "/", "(", ")", ","],
            "Templates": list(getattr(self, "_opt_expr_templates", [
                'curve_rms_err("io_actual","io_target") + 1000*hard_err_mean + 1000*(1-valid_ratio)',
                'curve_max_abs_err("io_actual","io_target")',
                'curve_value_at("io_actual",45)',
                'curve_monotonic_violation("io_actual")',
            ])),
        }

    def _optimization_token_groups(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        curve_names = []
        try:
            win = getattr(self.ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win is not None else None
            curves_tab = getattr(sim_panel, "curves_tab", None) if sim_panel is not None else None
            if curves_tab is not None and hasattr(curves_tab, "list_curve_names"):
                curve_names = [f'"{n}"' for n in (curves_tab.list_curve_names() or []) if str(n).strip()]
        except Exception:
            curve_names = []
        if not curve_names:
            curve_names = ['"io_actual"', '"io_target"']
        groups["Curves"] = curve_names
        groups["Input/Output"] = ["input_deg", "output_deg"]
        groups["Feasibility"] = ["valid_ratio", "output_span", "target_span"]

        measurements = [name for name, _val, _unit in self.ctrl.get_measure_values()]
        load_measures = [name for name, _val in self.ctrl.get_load_measure_values()]

        manager = self._manager()
        for info in manager.list_cases():
            case_spec = manager.load_case_spec(info.name) or {}
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

    def _open_variable_context_menu(self, pos) -> None:
        row = self.table_vars.rowAt(pos.y())
        if row >= 0:
            self.table_vars.selectRow(row)
        menu = QMenu(self)
        act_add = menu.addAction(_tr(self, "menu.add_row"))
        act_del = menu.addAction(_tr(self, "menu.delete_row"))
        selected = menu.exec(self.table_vars.viewport().mapToGlobal(pos))
        if selected == act_add:
            self.add_variable_row()
        elif selected == act_del:
            self.remove_variable_row()

    def _open_objective_context_menu(self, pos) -> None:
        row = self.table_obj.rowAt(pos.y())
        col = self.table_obj.columnAt(pos.x())
        if row >= 0:
            self.table_obj.selectRow(row)
        menu = QMenu(self)
        act_add = menu.addAction(_tr(self, "menu.add_row"))
        act_del = menu.addAction(_tr(self, "menu.delete_row"))
        act_builder = None
        if row >= 0 and col == 3:
            menu.addSeparator()
            act_builder = menu.addAction(_tr(self, "analysis.expression_builder"))
        selected = menu.exec(self.table_obj.viewport().mapToGlobal(pos))
        if selected == act_add:
            self.add_objective_row()
        elif selected == act_del:
            self.remove_objective_row()
        elif act_builder is not None and selected == act_builder:
            self._open_expression_builder_for_objective(row)

    def _open_constraint_context_menu(self, pos) -> None:
        row = self.table_con.rowAt(pos.y())
        col = self.table_con.columnAt(pos.x())
        if row >= 0:
            self.table_con.selectRow(row)
        menu = QMenu(self)
        act_add = menu.addAction(_tr(self, "menu.add_row"))
        act_del = menu.addAction(_tr(self, "menu.delete_row"))
        act_builder = None
        if row >= 0 and col == 2:
            menu.addSeparator()
            act_builder = menu.addAction(_tr(self, "analysis.expression_builder"))
        selected = menu.exec(self.table_con.viewport().mapToGlobal(pos))
        if selected == act_add:
            self.add_constraint_row()
        elif selected == act_del:
            self.remove_constraint_row()
        elif act_builder is not None and selected == act_builder:
            self._open_expression_builder_for_constraint(row)

    def _sync_expr_builder_template_state_from_dialog(self, dialog) -> None:
        """Persist template/help edits from expression builder back to optimization tab state and global defaults."""
        if dialog is None:
            return
        try:
            groups = getattr(dialog, "_function_groups_map", None)
            if isinstance(groups, dict):
                tpls = groups.get("Templates")
                if isinstance(tpls, (list, tuple)):
                    self._opt_expr_templates = [str(x) for x in tpls if str(x).strip()]
            hov = getattr(dialog, "_function_help_overrides_ref", None)
            if isinstance(hov, dict):
                self._opt_expr_template_help = {str(k): str(v) for k, v in hov.items() if str(k).strip()}
            save_global_expression_builder_template_overrides({"Templates": list(getattr(self, "_opt_expr_templates", []) or [])}, dict(getattr(self, "_opt_expr_template_help", {}) or {}))
        except Exception:
            pass

    def _open_expression_builder_for_objective(self, row: int) -> None:
        expr_item = self.table_obj.item(row, 3)
        current = expr_item.text() if expr_item else ""
        case_combo = self.table_obj.cellWidget(row, 1)
        case_ids = self._case_ids_from_combo(case_combo)
        dialog = ExpressionBuilderDialog(
            self,
            initial=current,
            tokens=self._optimization_token_groups(),
            functions=self._optimization_functions(),
            evaluator=lambda expr: self._evaluate_expression(expr, case_ids),
            function_help_overrides=getattr(self, "_opt_expr_template_help", None),
            allow_edit_templates=True,
        )
        _dlg_code = dialog.exec()
        self._sync_expr_builder_template_state_from_dialog(dialog)
        if _dlg_code == QDialog.DialogCode.Accepted:
            text = dialog.expression().strip()
            if expr_item:
                expr_item.setText(text)
            else:
                self.table_obj.setItem(row, 3, QTableWidgetItem(text))

    def _open_expression_builder_for_constraint(self, row: int) -> None:
        expr_item = self.table_con.item(row, 2)
        current = expr_item.text() if expr_item else ""
        case_combo = self.table_con.cellWidget(row, 1)
        case_ids = self._case_ids_from_combo(case_combo)
        dialog = ExpressionBuilderDialog(
            self,
            initial=current,
            tokens=self._optimization_token_groups(),
            functions=self._optimization_functions(),
            evaluator=lambda expr: self._evaluate_expression(expr, case_ids),
            function_help_overrides=getattr(self, "_opt_expr_template_help", None),
            allow_edit_templates=True,
        )
        _dlg_code = dialog.exec()
        self._sync_expr_builder_template_state_from_dialog(dialog)
        if _dlg_code == QDialog.DialogCode.Accepted:
            text = dialog.expression().strip()
            if expr_item:
                expr_item.setText(text)
            else:
                self.table_con.setItem(row, 2, QTableWidgetItem(text))

    def _evaluate_expression(self, expr: str, case_ids: Optional[List[str]] = None) -> tuple[Optional[float], Optional[str]]:
        case_specs = self._collect_case_specs()
        if not case_specs:
            return None, "No cases available"
        selected_case_ids = case_ids or list(case_specs.keys())
        if not selected_case_ids:
            return None, "No cases selected"
        model_snapshot = self.ctrl.snapshot_model()
        try:
            values = []
            for case_id in selected_case_ids:
                case_spec = case_specs.get(case_id)
                if not case_spec:
                    continue
                frames, _summary, _status = simulate_case(model_snapshot, case_spec)
                signals = build_signals(frames, model_snapshot)
                try:
                    add_curve_target_signals(signals, case_spec)
                except Exception:
                    pass
                val, err = eval_signal_expression(expr, signals)
                if err:
                    return None, err
                values.append(val)
            if not values:
                return None, "No case results"
            return float(sum(values)) / float(len(values)), None
        except Exception as exc:
            return None, str(exc)

    def _collect_variables(self) -> Optional[List[DesignVariable]]:
        variables: List[DesignVariable] = []
        for row in range(self.table_vars.rowCount()):
            enabled_item = self.table_vars.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_vars.cellWidget(row, 1)
            case_ids = self._case_ids_from_combo(case_combo)
            combo = self.table_vars.cellWidget(row, 3)
            name = combo.currentText() if isinstance(combo, QComboBox) else ""
            lower_item = self.table_vars.item(row, 5)
            upper_item = self.table_vars.item(row, 6)
            try:
                lower = float(lower_item.text()) if lower_item and lower_item.text().strip() else None
                upper = float(upper_item.text()) if upper_item and upper_item.text().strip() else None
            except Exception:
                QMessageBox.warning(self, _tr(self, "opt.variables.title"), _tr(self, "opt.variables.msg.bounds_numeric"))
                return None
            if lower is None or upper is None:
                QMessageBox.warning(self, _tr(self, "opt.variables.title"), _tr(self, "opt.variables.msg.bounds_required", name=name))
                return None
            variables.append(DesignVariable(name=name, lower=lower, upper=upper, enabled=enabled, case_ids=case_ids))
        return variables

    def _collect_objectives(self) -> List[ObjectiveSpec]:
        objs: List[ObjectiveSpec] = []
        for row in range(self.table_obj.rowCount()):
            enabled_item = self.table_obj.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_obj.cellWidget(row, 1)
            case_ids = self._case_ids_from_combo(case_combo)
            combo = self.table_obj.cellWidget(row, 2)
            direction = combo.currentText() if isinstance(combo, QComboBox) else "min"
            expr_item = self.table_obj.item(row, 3)
            expr = expr_item.text().strip() if expr_item else ""
            objs.append(ObjectiveSpec(expression=expr, direction=direction, enabled=enabled, case_ids=case_ids))
        return objs

    def _collect_constraints(self) -> List[ConstraintSpec]:
        cons: List[ConstraintSpec] = []
        for row in range(self.table_con.rowCount()):
            enabled_item = self.table_con.item(row, 0)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item else True
            case_combo = self.table_con.cellWidget(row, 1)
            case_ids = self._case_ids_from_combo(case_combo)
            expr_item = self.table_con.item(row, 2)
            expr = expr_item.text().strip() if expr_item else ""
            combo = self.table_con.cellWidget(row, 3)
            comparator = combo.currentText() if isinstance(combo, QComboBox) else "<="
            limit_item = self.table_con.item(row, 4)
            if limit_item is None or not limit_item.text().strip():
                limit = 0.0
            else:
                try:
                    limit = float(limit_item.text())
                except Exception:
                    QMessageBox.warning(self, _tr(self, "opt.constraints.title"), _tr(self, "opt.constraints.msg.limits_numeric"))
                    return []
            cons.append(
                ConstraintSpec(
                    expression=expr,
                    comparator=comparator,
                    limit=limit,
                    enabled=enabled,
                    case_ids=case_ids,
                )
            )
        return cons

    def _maybe_overlay_live_synthesis_curve(self, case_specs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Overlay optimization io-angle case(s) from ctrl live I/O curve provider at call time."""
        try:
            apply_live = getattr(self.ctrl, "apply_live_io_curve_target_to_case_spec", None)
            if not callable(apply_live):
                return case_specs
            target_case_ids = []
            try:
                cid = self.combo_active_case.currentData()
                if cid and str(cid) in case_specs:
                    target_case_ids = [str(cid)]
            except Exception:
                target_case_ids = []
            if not target_case_ids:
                for cid, spec in list(case_specs.items()):
                    ct = (spec or {}).get("curve_target") if isinstance(spec, dict) else None
                    if isinstance(ct, dict) and str(ct.get("kind", "io_angle")) == "io_angle":
                        target_case_ids.append(str(cid))
            if not target_case_ids:
                return case_specs
            out = dict(case_specs)
            for cid in target_case_ids:
                spec0 = case_specs.get(cid)
                if isinstance(spec0, dict):
                    out[cid] = apply_live(spec0)
            return out
        except Exception:
            return case_specs

    def _collect_case_specs(self) -> Dict[str, Dict[str, Any]]:
        manager = self._manager()
        case_specs: Dict[str, Dict[str, Any]] = {}
        for info in manager.list_cases():
            spec = manager.load_case_spec(info.name)
            if spec:
                case_specs[info.name] = spec
        return self._maybe_overlay_live_synthesis_curve(case_specs)

    def run_optimization(self) -> None:
        self.ensure_defaults()
        variables = self._collect_variables()
        if variables is None:
            return
        self._set_best_table_headers([var.name for var in variables if var.enabled])
        self._refresh_initial_row()
        self._refresh_best_objective_display()
        objectives = self._collect_objectives()
        constraints = self._collect_constraints()

        case_specs = self._collect_case_specs()
        if not case_specs:
            QMessageBox.warning(self, _tr(self, "tab.optimization"), _tr(self, "opt.msg.no_cases"))
            return

        # Sanity-check: ensure sweep range covers the target curve domain.
        # Otherwise the optimizer can appear to "win" by only fitting a short valid prefix.
        try:
            lang = _lang(self)
            adjusted: List[Tuple[str, float, float]] = []
            for cid, spec in list(case_specs.items()):
                if not isinstance(spec, dict):
                    continue
                ct = spec.get("curve_target")
                if not (isinstance(ct, dict) and ct.get("kind") == "io_angle"):
                    continue
                pts = ct.get("points")
                if not isinstance(pts, list) or not pts:
                    continue
                xs = []
                for p in pts:
                    try:
                        xs.append(float(p[0]))
                    except Exception:
                        continue
                if not xs:
                    continue
                tgt_min = float(min(xs))
                tgt_max = float(max(xs))
                sweep = spec.get("sweep") if isinstance(spec.get("sweep"), dict) else {}
                try:
                    end_deg = float((sweep or {}).get("end_deg", tgt_max))
                except Exception:
                    end_deg = tgt_max
                try:
                    start_deg = float((sweep or {}).get("start_deg", tgt_min))
                except Exception:
                    start_deg = tgt_min
                need_adjust = (end_deg + 1e-9) < tgt_max or (start_deg - 1e-9) > tgt_min
                if need_adjust:
                    # Patch in-memory spec used by the worker.
                    sweep2 = dict(sweep or {})
                    sweep2["start_deg"] = min(start_deg, tgt_min)
                    sweep2["end_deg"] = max(end_deg, tgt_max)
                    spec2 = dict(spec)
                    spec2["sweep"] = sweep2
                    case_specs[cid] = spec2
                    adjusted.append((str(cid), float(end_deg), float(sweep2["end_deg"])))
            if adjusted:
                if lang == "zh":
                    msg = "已自动调整扫角范围以覆盖目标关键点域：\n" + "\n".join(
                        [f"case {cid}: end {a:.3g} -> {b:.3g} (deg)" for cid, a, b in adjusted]
                    )
                else:
                    msg = "Adjusted sweep range to cover target keypoints:\n" + "\n".join(
                        [f"case {cid}: end {a:.3g} -> {b:.3g} (deg)" for cid, a, b in adjusted]
                    )
                QMessageBox.information(self, _tr(self, "tab.optimization"), msg)
        except Exception:
            pass

        model_snapshot = self.ctrl.snapshot_model()

        try:
            evals = int(float(self.ed_evals.text() or "50"))
        except Exception:
            evals = 50
        enable_debug_log = self.chk_debug_log.isChecked()
        debug_log_path = (self.ed_debug_log_path.text() or "").strip() or None
        if enable_debug_log and not debug_log_path:
            debug_log_path = os.path.join(self._project_dir(), "logs", "optimization_debug.log")

        self._worker = OptimizationWorker(
            model_snapshot=model_snapshot,
            case_specs=case_specs,
            variables=variables,
            objectives=objectives,
            constraints=constraints,
            evals=evals,
            seed=None,
            enable_debug_log=enable_debug_log,
            debug_log_path=debug_log_path,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        # reset convergence history
        self._best_score_hist = []
        self._best_obj_hist = []
        self._planned_evals = int(evals)
        self._last_finished_payload = None
        self._clear_viz()
        self._set_progress_label("0")
        self._worker.start()

    def stop_optimization(self) -> None:
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(True)

    def _on_progress(self, payload: Dict[str, Any]) -> None:
        idx = payload.get("index", 0)
        planned = payload.get("planned")
        if planned is not None:
            try:
                self._planned_evals = int(planned)
            except Exception:
                pass
        best = payload.get("best", {})
        new_best = bool(payload.get("new_best", False))
        self._set_progress_label(str(idx))
        # Only refresh the (heavier) tables when a new best solution is found.
        if new_best and best and best.get("vars"):
            self._best_vars = dict(best.get("vars", {}))
            self._update_best_table(best)
        self._update_convergence(best, current=int(idx))

    def _on_finished(self, payload: Dict[str, Any]) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if payload and payload.get("vars"):
            self._best_vars = dict(payload.get("vars", {}))
            self._update_best_table(payload)
        self._update_convergence(payload, current=int(payload.get("completed_evals", self._planned_evals) or 0), finished=True)
        self._last_finished_payload = dict(payload or {}) if isinstance(payload, dict) else None
        self._update_curve_compare(payload)
        self._set_progress_label(_tr(self, "analysis.done"))

        # Ensure worker thread is released to avoid UI lag after the run.
        try:
            if self._worker is not None:
                self._worker.quit()
                self._worker.wait(200)
                self._worker.deleteLater()
        except Exception:
            pass
        self._worker = None
    def _ensure_plots_dialog(self) -> _OptimizationPlotsDialog:
        if self._plots_dialog is None:
            self._plots_dialog = _OptimizationPlotsDialog(self)
            self._plots_dialog.apply_language(_lang(self))
        return self._plots_dialog

    def open_result_plots(self) -> None:
        dlg = self._ensure_plots_dialog()
        try:
            dlg.lbl_status.setText(self.lbl_statusbar.text())
        except Exception:
            pass
        dlg.show_and_raise()

    def _clear_viz(self) -> None:
        try:
            self._convergence_text = ""
            self._refresh_status_bar()
        except Exception:
            pass
        try:
            dlg = self._ensure_plots_dialog()
            dlg._ax_curve.clear()
            dlg._canvas_curve.draw_idle()
        except Exception:
            pass
        try:
            dlg = self._ensure_plots_dialog()
            dlg._ax_conv.clear()
            dlg._canvas_conv.draw_idle()
        except Exception:
            pass

    def _update_convergence(self, best_payload: Dict[str, Any], current: int = 0, finished: bool = False) -> None:
        # Track best objective over evals (for a simple convergence view).
        try:
            score = best_payload.get("score")
            obj = best_payload.get("objective")
            if isinstance(score, (int, float)):
                self._best_score_hist.append(float(score))
            if isinstance(obj, (int, float)):
                self._best_obj_hist.append(float(obj))
        except Exception:
            pass

        planned = self._planned_evals or int(best_payload.get("planned_evals", 0) or 0)
        completed = int(best_payload.get("completed_evals", current) or current)
        stopped = bool(best_payload.get("stopped", False))
        violation = best_payload.get("violation")
        feasible = (isinstance(violation, (int, float)) and float(violation) <= 1e-9)
        if finished and (not stopped):
            # Persist run status for other UI components (e.g., template saving).
            self._last_run_feasible = bool(feasible)
        lang = _lang(self)

        if _is_zh(self):
            status_text = f"进度: {completed}/{planned}" + ("（完成）" if finished and not stopped else ("（已停止）" if stopped else ""))
            if isinstance(best_payload.get("objective"), (int, float)):
                status_text += f"   最佳目标: {float(best_payload['objective']):.4g}"
            if isinstance(violation, (int, float)):
                status_text += f"   约束: {'可行' if feasible else '不满足'}"
        else:
            status_text = f"Progress: {completed}/{planned}" + (" (done)" if finished and not stopped else (" (stopped)" if stopped else ""))
            if isinstance(best_payload.get("objective"), (int, float)):
                status_text += f"   Best objective: {float(best_payload['objective']):.4g}"
            if isinstance(violation, (int, float)):
                status_text += f"   Constraints: {'feasible' if feasible else 'violated'}"
        self._convergence_text = status_text
        self._refresh_status_bar()
        try:
            self._ensure_plots_dialog().lbl_status.setText(status_text)
        except Exception:
            pass

        # Plot convergence (best objective vs eval index).
        try:
            dlg = self._ensure_plots_dialog()
            dlg._ax_conv.clear()
            ys = self._best_obj_hist if self._best_obj_hist else self._best_score_hist
            if ys:
                xs = list(range(1, len(ys) + 1))
                dlg._ax_conv.plot(xs, ys)
                dlg._ax_conv.set_xlabel("eval")
                dlg._ax_conv.set_ylabel("best" if not self._best_obj_hist else "best obj")
                dlg._ax_conv.grid(True)
            dlg._canvas_conv.draw_idle()
        except Exception:
            pass

    def _update_curve_compare(self, best_payload: Dict[str, Any]) -> None:
        """Plot best curve vs target curve if the active case has a curve_target."""
        try:
            case_specs = self._collect_case_specs()
            if not case_specs:
                return
            # Prefer the active-case selection; otherwise fall back to first case.
            active_case_id = self._active_case_id
            if not active_case_id or active_case_id not in case_specs:
                active_case_id = next(iter(case_specs.keys()))
            case_spec = dict(case_specs.get(active_case_id) or {})

            # Prefer the signals captured during the best evaluation (guaranteed to match the objective),
            # and only fall back to re-simulation when they are unavailable.
            x = y = t = None
            try:
                best_sigs = dict(best_payload.get("best_signals") or {})
                case_sig = best_sigs.get(active_case_id) or {}
                x = case_sig.get("input_deg")
                y = case_sig.get("output_deg")
                # Prefer the target curve captured during the best evaluation.
                # This guarantees the plotted curve matches the objective score used to pick "best".
                t = case_sig.get("curve_target")
            except Exception:
                pass

            if not (isinstance(x, list) and isinstance(y, list)):
                # Fallback: re-simulate from scratch using the best design vars.
                snapshot = self.ctrl.snapshot_model()
                vars_map = dict(best_payload.get("vars") or {})
                _apply_design_vars(snapshot, vars_map, [])
                frames, _summary, _status = simulate_case(snapshot, case_spec)
                sig = build_signals(frames, snapshot)
                add_curve_target_signals(sig, case_spec)
                x = sig.get("input_deg")
                y = sig.get("output_deg")
                t = sig.get("curve_target")

            # Ensure we have a target curve. (Some payloads may omit it to save space.)
            if isinstance(x, list) and isinstance(y, list) and not isinstance(t, list):
                try:
                    sig2 = {"input_deg": x, "output_deg": y}
                    add_curve_target_signals(sig2, case_spec)
                    t = sig2.get("curve_target")
                except Exception:
                    t = None

            if not (isinstance(x, list) and isinstance(y, list) and isinstance(t, list)):
                dlg = self._ensure_plots_dialog()
                dlg._ax_curve.clear()
                dlg._canvas_curve.draw_idle()
                return

            # Sort by x for a stable, monotonic plot.
            pairs = sorted(zip(x, y, t), key=lambda p: p[0])
            x = [p[0] for p in pairs]
            y = [p[1] for p in pairs]
            t = [p[2] for p in pairs]

            dlg = self._ensure_plots_dialog()
            dlg._ax_curve.clear()
            dlg._ax_curve.plot(x, t, label="target")
            dlg._ax_curve.plot(x, y, label="best")
            dlg._ax_curve.set_xlabel("input (deg)")
            dlg._ax_curve.set_ylabel("output")
            dlg._ax_curve.grid(True)
            dlg._ax_curve.legend(loc="best")
            dlg._canvas_curve.draw_idle()
        except Exception:
            # Visualization should never break the optimization workflow.
            return

    def _on_failed(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.warning(self, _tr(self, "tab.optimization"), _tr(self, "opt.msg.failed", msg=msg))

        # Ensure worker thread is released to avoid UI lag after the run.
        try:
            if self._worker is not None:
                self._worker.quit()
                self._worker.wait(200)
                self._worker.deleteLater()
        except Exception:
            pass
        self._worker = None
    def _update_best_table(self, payload: Dict[str, Any]) -> None:
        self.table_best.setRowCount(2)
        obj_val = payload.get("objective")
        obj_item = QTableWidgetItem(format_table_number(obj_val))
        obj_item.setFlags(obj_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_best.setItem(1, 0, obj_item)
        for idx, key in enumerate(self._best_var_names, start=1):
            val = self._best_vars.get(key)
            item = QTableWidgetItem(format_table_number(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_best.setItem(1, idx, item)

    def _refresh_best_objective_display(self) -> None:
        objectives = self._collect_objectives()
        obj_val: Optional[float] = None
        for obj in objectives:
            if not obj.enabled:
                continue
            obj_val, err = self._evaluate_expression(obj.expression, obj.case_ids)
            if err:
                obj_val = None
            break
        obj_item = QTableWidgetItem(format_table_number(obj_val))
        obj_item.setFlags(obj_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_best.setItem(0, 0, obj_item)

    def _refresh_initial_row(self) -> None:
        for idx, key in enumerate(self._best_var_names, start=1):
            val = self._get_variable_value(key)
            item = QTableWidgetItem(format_table_number(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_best.setItem(0, idx, item)

    def apply_selected(self) -> None:
        row = self.table_best.currentRow()
        if row < 0:
            QMessageBox.information(self, _tr(self, "tab.optimization"), _tr(self, "opt.msg.select_row_apply"))
            return
        if row == 0:
            selected_vars = {name: self._get_variable_value(name) for name in self._best_var_names}
        else:
            if not self._best_vars:
                QMessageBox.information(self, _tr(self, "tab.optimization"), _tr(self, "opt.msg.no_best_solution"))
                return
            selected_vars = dict(self._best_vars)
        # Apply all updates as a single command to avoid intermediate re-solves
        # that may jump the mechanism to a different assembly mode (e.g. 4-bar
        # crossing). Also solve with drive constraints disabled so outputs/
        # drivers won't "snap" the configuration to another branch.
        ctrl = self.ctrl
        model_before = ctrl.snapshot_model()

        link_updates: Dict[int, float] = {}
        param_updates: Dict[str, float] = {}
        point_updates: Dict[int, Dict[str, float]] = {}

        for name, val in selected_vars.items():
            if val is None:
                continue
            if not name.startswith("P") or "." not in name:
                if name.startswith("Link") and name.endswith(".L"):
                    lid_str = name[len("Link") : -len(".L")]
                    try:
                        lid = int(lid_str)
                    except Exception:
                        continue
                    link = ctrl.links.get(lid)
                    if not link or link.get("ref", False):
                        continue
                    link_updates[lid] = float(val)
                elif name.startswith("Param."):
                    param_name = name[len("Param.") :].strip()
                    if param_name:
                        param_updates[param_name] = float(val)
                continue

            pid_str, axis = name[1:].split(".", 1)
            try:
                pid = int(pid_str)
            except Exception:
                continue
            if pid not in ctrl.points:
                continue
            point_updates.setdefault(pid, {})[axis] = float(val)

        if not link_updates and not param_updates and not point_updates:
            return

        class ApplyOptResult(Command):
            name = "Apply Optimization Result"

            def do(self_):
                for lid, L in link_updates.items():
                    if lid in ctrl.links:
                        ctrl.links[lid]["L"] = float(L)
                for k, v in param_updates.items():
                    ctrl.params[str(k)] = float(v)
                for pid, axes in point_updates.items():
                    if pid not in ctrl.points:
                        continue
                    if "x" in axes:
                        ctrl.points[pid]["x"] = float(axes["x"])
                    if "y" in axes:
                        ctrl.points[pid]["y"] = float(axes["y"])
                ctrl.solve_constraints(use_drive_constraints=False)
                ctrl.update_graphics()
                if ctrl.panel:
                    ctrl.panel.defer_refresh_all(keep_selection=True)

            def undo(self_):
                ctrl.apply_model_snapshot(model_before)

        ctrl.stack.push(ApplyOptResult())
        self._refresh_best_objective_display()


__all__ = ["OptimizationTab"]
