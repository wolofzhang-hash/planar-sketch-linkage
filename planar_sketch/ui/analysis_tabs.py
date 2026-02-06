# -*- coding: utf-8 -*-
"""Analysis tabs: Animation + Optimization."""

from __future__ import annotations

import ast
import csv
import importlib.util
import json
import math
import os
from typing import Any, Dict, List, Optional

import numpy as np
from PyQt6.QtCore import Qt, QUrl, QTimer, QCoreApplication
from PyQt6.QtGui import QDesktopServices, QImage
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
    QComboBox,
    QAbstractItemView,
    QMessageBox,
    QGroupBox,
    QLineEdit,
    QMenu,
    QDialog,
    QInputDialog,
    QFileDialog,
    QCheckBox,
)

from ..core.case_run_manager import CaseRunManager
from ..core.expression_service import eval_signal_expression
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
from .i18n import tr

class AnimationTab(QWidget):
    def __init__(self, ctrl: Any, on_active_case_changed=None):
        super().__init__()
        self.ctrl = ctrl
        self._on_active_case_changed = on_active_case_changed
        layout = QVBoxLayout(self)

        self.lbl_active = QLabel("")
        layout.addWidget(self.lbl_active)

        self.table_case_runs = QTableWidget(0, 3)
        self.table_case_runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_case_runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_case_runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_case_runs.verticalHeader().setVisible(False)
        self.table_case_runs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lbl_cases_runs = QLabel("")
        layout.addWidget(self.lbl_cases_runs)
        layout.addWidget(self.table_case_runs)

        action_row = QHBoxLayout()
        self.btn_set_active = QPushButton("")
        self.btn_load_run_data = QPushButton("")
        action_row.addWidget(self.btn_set_active)
        action_row.addWidget(self.btn_load_run_data)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        layout.addWidget(self._build_replay_group())

        self.btn_set_active.clicked.connect(self.set_active_case)
        self.btn_load_run_data.clicked.connect(self.load_run_data)
        self.table_case_runs.customContextMenuRequested.connect(self._open_case_run_context_menu)

        self._cases_cache: List[Any] = []
        self._row_cache: List[Dict[str, Any]] = []
        self._frames: List[Dict[str, Any]] = []
        self._frame_index = 0
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._advance_frame)
        self._plot_window: Optional[PlotWindow] = None
        self._loaded_case_id: Optional[str] = None
        self.apply_language()
        self.refresh_cases()

    def _project_dir(self) -> str:
        if getattr(self.ctrl, "win", None) and getattr(self.ctrl.win, "current_file", None):
            project_dir = getattr(self.ctrl.win, "project_dir", None)
            if project_dir:
                return project_dir
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _manager(self) -> CaseRunManager:
        project_uuid = getattr(self.ctrl, "project_uuid", "") if self.ctrl else ""
        return CaseRunManager(self._project_dir(), project_uuid=project_uuid)

    def _case_label_text(self) -> str:
        lang = getattr(self.ctrl, "ui_language", "en")
        cases = self._manager().list_cases()
        if not cases:
            return "--"
        return tr(lang, "analysis.all_cases")

    def _case_options(self) -> List[tuple[str, str]]:
        options: List[tuple[str, str]] = []
        for case in self._manager().list_cases():
            label = f"{case.name} ({case.case_id})"
            options.append((label, case.case_id))
        return options

    def _case_combo(self, parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        lang = getattr(self.ctrl, "ui_language", "en")
        combo.addItem(tr(lang, "analysis.all_cases"), None)
        for label, case_id in self._case_options():
            combo.addItem(label, case_id)
        return combo

    def _case_ids_from_combo(self, combo: Optional[QComboBox]) -> Optional[List[str]]:
        if not isinstance(combo, QComboBox):
            return None
        data = combo.currentData()
        if data is None:
            return None
        return [str(data)]

    def refresh_cases(self) -> None:
        manager = self._manager()
        cases = manager.list_cases()
        self._cases_cache = cases
        rows: List[Dict[str, Any]] = []
        for info in cases:
            runs = manager.list_runs(info.case_id)
            run_info = runs[0] if runs else None
            rows.append({"case": info, "run": run_info, "kind": "case"})
        self._row_cache = rows
        self.table_case_runs.setRowCount(len(rows))
        for row, payload in enumerate(rows):
            case_info = payload["case"]
            run_info = payload.get("run") or {}
            is_case_row = payload.get("kind") == "case"
            case_label = case_info.name
            items = [
                QTableWidgetItem(case_label),
                QTableWidgetItem(str(run_info.get("success", ""))),
                QTableWidgetItem(str(run_info.get("n_steps", ""))),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if is_case_row and col == 0:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table_case_runs.setItem(row, col, item)
        active = manager.get_active_case()
        self._set_active_label(active or "--")
        if active:
            self._select_case_row(active)
            run = next((item.get("run") for item in rows if item["case"].case_id == active), None)
            if run and self._loaded_case_id != active:
                self._load_run_data_for_run(run, active)
        if hasattr(self.ctrl, "win") and getattr(self.ctrl.win, "sim_panel", None):
            sim_panel = self.ctrl.win.sim_panel
            if hasattr(sim_panel, "optimization_tab"):
                sim_panel.optimization_tab.refresh_active_case()

    def apply_language(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self.table_case_runs.setHorizontalHeaderLabels(
            [
                tr(lang, "analysis.case"),
                tr(lang, "analysis.success"),
                tr(lang, "analysis.steps"),
            ]
        )
        self.lbl_cases_runs.setText(tr(lang, "analysis.cases"))
        self.btn_set_active.setText(tr(lang, "analysis.set_active_case"))
        self.btn_load_run_data.setText(tr(lang, "analysis.load_run_data"))
        self.group_replay.setTitle(tr(lang, "analysis.replay_plot"))
        self.btn_replay_play.setText(tr(lang, "analysis.play"))
        self.btn_replay_pause.setText(tr(lang, "analysis.pause"))
        self.btn_replay_stop.setText(tr(lang, "analysis.stop"))
        self.btn_plot_run.setText(tr(lang, "analysis.plot"))
        self.btn_capture_image.setText(tr(lang, "analysis.capture_image"))
        self.btn_record_gif.setText(tr(lang, "analysis.record_gif"))
        self._set_active_label(self._manager().get_active_case() or "--")
        self._set_frame_label(self._frame_index, len(self._frames))

    def reset_state(self) -> None:
        if self._frame_timer.isActive():
            self._frame_timer.stop()
        self._frames = []
        self._frame_index = 0
        self._loaded_case_id = None
        self.slider_frame.setRange(0, 0)
        self.slider_frame.setValue(0)
        self._set_frame_label(0, 0)
        if self._plot_window is not None:
            self._plot_window.close()
            self._plot_window = None

    def _set_active_label(self, case_id: str) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self.lbl_active.setText(tr(lang, "analysis.active_case").format(case=case_id))

    def _set_frame_label(self, index: int, total: int) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        if total <= 0:
            self.lbl_frame.setText(tr(lang, "analysis.frame").format(current="--"))
            return
        self.lbl_frame.setText(tr(lang, "analysis.frame").format(current=f"{index + 1}/{total}"))

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
        win = getattr(self.ctrl, "win", None)
        if win and hasattr(win, "confirm_unsaved_run"):
            if not win.confirm_unsaved_run():
                return
        path = os.path.join(run.get("path", ""), "model.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, "Run", "model.json not found.")
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.loads(fh.read())
            warnings, errors = self.ctrl.validate_project_schema(raw)
            if win and hasattr(win, "_report_schema_issues"):
                if not win._report_schema_issues(warnings, errors, "load"):
                    return
            elif errors:
                QMessageBox.critical(self, "Run", "\n".join(errors))
                return
            data = self.ctrl.merge_project_dict(raw)
            if not self.ctrl.load_dict(data, action="load a run snapshot"):
                return
            if self.ctrl.panel:
                self.ctrl.panel.defer_refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Run", f"Failed to load snapshot: {exc}")

    def set_active_case(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        if not self.confirm_stop_replay("switch cases"):
            return
        manager = self._manager()
        manager.set_active_case(case_id)
        self._set_active_label(case_id)
        if self._on_active_case_changed:
            self._on_active_case_changed()
        run = self._selected_run()
        if run:
            self._load_run_data_for_run(run, case_id)

    def _build_replay_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_replay = group
        layout = QVBoxLayout(group)

        controls = QHBoxLayout()
        self.btn_replay_play = QPushButton("")
        self.btn_replay_pause = QPushButton("")
        self.btn_replay_stop = QPushButton("")
        self.btn_plot_run = QPushButton("")
        self.btn_capture_image = QPushButton("")
        self.btn_record_gif = QPushButton("")
        controls.addWidget(self.btn_replay_play)
        controls.addWidget(self.btn_replay_pause)
        controls.addWidget(self.btn_replay_stop)
        controls.addWidget(self.btn_plot_run)
        controls.addWidget(self.btn_capture_image)
        controls.addWidget(self.btn_record_gif)
        controls.addStretch(1)
        layout.addLayout(controls)

        slider_row = QHBoxLayout()
        self.slider_frame = QSlider(Qt.Orientation.Horizontal)
        self.slider_frame.setRange(0, 0)
        self.lbl_frame = QLabel("")
        slider_row.addWidget(self.slider_frame, 1)
        slider_row.addWidget(self.lbl_frame)
        layout.addLayout(slider_row)

        self.btn_replay_play.clicked.connect(self.play_replay)
        self.btn_replay_pause.clicked.connect(self.pause_replay)
        self.btn_replay_stop.clicked.connect(self.stop_replay)
        self.slider_frame.valueChanged.connect(self._on_slider_changed)
        self.btn_plot_run.clicked.connect(self.open_plot_window)
        self.btn_capture_image.clicked.connect(self.capture_screenshot)
        self.btn_record_gif.clicked.connect(self.record_gif)
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

    def delete_case(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, "Case", "Select a case first.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete Case",
            f"Delete case {case_id} and all runs?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        manager = self._manager()
        if manager.delete_case(case_id):
            self.refresh_cases()
        else:
            QMessageBox.warning(self, "Case", "Failed to delete case.")

    def load_run_data(self) -> None:
        case_id = self._selected_case_id()
        run = self._selected_run()
        if not run:
            QMessageBox.information(self, "Run", "Select a run first.")
            return
        if not self.confirm_stop_replay("load run data"):
            return
        if case_id:
            manager = self._manager()
            manager.set_active_case(case_id)
            self._set_active_label(case_id)
            if self._on_active_case_changed:
                self._on_active_case_changed()
        self._load_run_data_for_run(run, case_id)

    def _load_run_data_for_run(self, run: Dict[str, Any], case_id: Optional[str]) -> None:
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
        if case_id:
            self._loaded_case_id = case_id

    def _select_case_row(self, case_id: str) -> None:
        for row, payload in enumerate(self._row_cache):
            if payload["case"].case_id == case_id:
                self.table_case_runs.selectRow(row)
                return

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
                stripped = val.strip()
                if (stripped.startswith("[") and stripped.endswith("]")) or (
                    stripped.startswith("{") and stripped.endswith("}")
                ):
                    parsed = None
                    try:
                        parsed = json.loads(stripped)
                    except Exception:
                        try:
                            parsed = ast.literal_eval(stripped)
                        except Exception:
                            parsed = None
                    if isinstance(parsed, (list, dict)):
                        out[key] = parsed
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
        self._plot_window.set_frame_index(self._frame_index)

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
        self._plot_window.set_frame_index(self._frame_index)
        self._plot_window.raise_()
        self._plot_window.activateWindow()

    def _view_widget(self):
        win = getattr(self.ctrl, "win", None)
        if win is None:
            return None
        return getattr(win, "view", None)

    def capture_screenshot(self) -> None:
        view = self._view_widget()
        if view is None:
            QMessageBox.warning(self, "Screenshot", "No view available to capture.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            "",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)",
        )
        if not path:
            return
        pixmap = view.grab()
        if not pixmap.save(path):
            QMessageBox.warning(self, "Screenshot", "Failed to save screenshot.")
            return
        QMessageBox.information(self, "Screenshot", "Screenshot saved.")

    def record_gif(self) -> None:
        if not self._frames:
            QMessageBox.information(self, "GIF", "Load run data first.")
            return
        if importlib.util.find_spec("imageio") is None:
            QMessageBox.warning(self, "GIF", "imageio is not available for GIF recording.")
            return
        view = self._view_widget()
        if view is None:
            QMessageBox.warning(self, "GIF", "No view available to capture.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save GIF",
            "",
            "GIF (*.gif)",
        )
        if not path:
            return
        if not path.lower().endswith(".gif"):
            path = f"{path}.gif"
        import imageio.v2 as imageio

        self.pause_replay()
        original_index = self._frame_index
        fps = 20
        with imageio.get_writer(path, mode="I", duration=1.0 / fps) as writer:
            for idx in range(len(self._frames)):
                self._apply_frame(idx)
                QCoreApplication.processEvents()
                image = view.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                ptr = image.bits()
                ptr.setsize(image.sizeInBytes())
                frame = np.frombuffer(ptr, np.uint8).reshape((image.height(), image.width(), 4))
                writer.append_data(frame)
        self.slider_frame.setValue(original_index)
        QMessageBox.information(self, "GIF", "GIF saved.")

    def _apply_frame(self, index: int) -> None:
        if not self._frames:
            return
        idx = max(0, min(index, len(self._frames) - 1))
        frame = self._frames[idx]
        driver_vals = frame.get("driver_deg")
        if isinstance(driver_vals, list) and driver_vals:
            try:
                self.ctrl.drive_to_multi_deg([float(val) for val in driver_vals], iters=80)
            except Exception:
                pass
        else:
            input_val = frame.get("input_deg")
            if input_val is not None:
                try:
                    self.ctrl.drive_to_deg(float(input_val))
                except Exception:
                    pass
        self._frame_index = idx
        self._set_frame_label(idx, len(self._frames))
        if self._plot_window is not None and self._plot_window.isVisible():
            self._plot_window.set_frame_index(idx)
            if self._frame_timer.isActive():
                self._plot_window.bring_to_front()

    def _advance_frame(self) -> None:
        if not self._frames:
            self._frame_timer.stop()
            return
        next_idx = self._frame_index + 1
        if next_idx >= len(self._frames):
            next_idx = 0
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

    def is_replay_active(self) -> bool:
        return self._frame_timer.isActive()

    def confirm_stop_replay(self, action: str) -> bool:
        if not self.is_replay_active():
            return True
        prompt = f"Animation is playing. Stop it to {action}?"
        confirm = QMessageBox.question(
            self,
            "Animation",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return False
        self.stop_replay()
        return True



    def _open_case_run_context_menu(self, pos) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        menu = QMenu(self)
        act_set_active = menu.addAction(tr(lang, "analysis.set_active_case"))
        menu.addSeparator()
        act_open_run = menu.addAction(tr(lang, "analysis.open_run_folder"))
        act_load_snapshot = menu.addAction(tr(lang, "analysis.load_run_snapshot"))
        menu.addSeparator()
        act_rename_case = menu.addAction(tr(lang, "analysis.rename_case"))
        act_rename_case_id = menu.addAction(tr(lang, "analysis.rename_case_id"))
        act_delete_case_results = menu.addAction(tr(lang, "analysis.delete_case_results"))
        act_delete_case = menu.addAction(tr(lang, "analysis.delete_case"))

        selected = menu.exec(self.table_case_runs.viewport().mapToGlobal(pos))
        if selected == act_set_active:
            self.set_active_case()
        elif selected == act_open_run:
            self.open_run_folder()
        elif selected == act_load_snapshot:
            self.load_run_snapshot()
        elif selected == act_rename_case:
            self.rename_case()
        elif selected == act_rename_case_id:
            self.rename_case_id()
        elif selected == act_delete_case_results:
            self.delete_case_results()
        elif selected == act_delete_case:
            self.delete_case()


class OptimizationTab(QWidget):
    def __init__(self, ctrl: Any):
        super().__init__()
        self.ctrl = ctrl
        self._worker: Optional[OptimizationWorker] = None
        self._best_vars: Dict[str, float] = {}
        self._best_var_names: List[str] = []
        self._progress_value = "--"

        layout = QVBoxLayout(self)
        self.lbl_active = QLabel("")
        layout.addWidget(self.lbl_active)

        layout.addWidget(self._build_variables_group())
        layout.addWidget(self._build_objectives_group())
        layout.addWidget(self._build_constraints_group())
        layout.addWidget(self._build_run_group())
        layout.addStretch(1)

        self.apply_language()
        self.refresh_case_label()
        self.ensure_defaults()

    def _build_variables_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_vars = group
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_var = QPushButton("")
        self.btn_del_var = QPushButton("")
        btn_row.addWidget(self.btn_add_var)
        btn_row.addWidget(self.btn_del_var)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_vars = QTableWidget(0, 7)
        self.table_vars.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_vars.verticalHeader().setVisible(False)
        self.table_vars.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_vars.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table_vars)

        self.btn_add_var.clicked.connect(lambda _checked=False: self.add_variable_row())
        self.btn_del_var.clicked.connect(self.remove_variable_row)
        return group

    def _build_objectives_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_obj = group
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_obj = QPushButton("")
        self.btn_del_obj = QPushButton("")
        btn_row.addWidget(self.btn_add_obj)
        btn_row.addWidget(self.btn_del_obj)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_obj = QTableWidget(0, 4)
        self.table_obj.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_obj.verticalHeader().setVisible(False)
        self.table_obj.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table_obj)

        self.btn_add_obj.clicked.connect(lambda _checked=False: self.add_objective_row())
        self.btn_del_obj.clicked.connect(self.remove_objective_row)
        self.table_obj.customContextMenuRequested.connect(self._open_objective_context_menu)
        return group

    def _build_constraints_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_con = group
        layout = QVBoxLayout(group)
        btn_row = QHBoxLayout()
        self.btn_add_con = QPushButton("")
        self.btn_del_con = QPushButton("")
        btn_row.addWidget(self.btn_add_con)
        btn_row.addWidget(self.btn_del_con)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table_con = QTableWidget(0, 5)
        self.table_con.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_con.verticalHeader().setVisible(False)
        self.table_con.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table_con)

        self.btn_add_con.clicked.connect(lambda _checked=False: self.add_constraint_row())
        self.btn_del_con.clicked.connect(self.remove_constraint_row)
        self.table_con.customContextMenuRequested.connect(self._open_constraint_context_menu)
        return group

    def _build_run_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_run = group
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        self.lbl_evals = QLabel("")
        row.addWidget(self.lbl_evals)
        self.ed_evals = QLineEdit("50")
        self.ed_evals.setMaximumWidth(80)
        row.addWidget(self.ed_evals)
        self.lbl_seed = QLabel("")
        row.addWidget(self.lbl_seed)
        self.ed_seed = QLineEdit("")
        self.ed_seed.setMaximumWidth(120)
        row.addWidget(self.ed_seed)
        self.input_fields = [self.ed_evals, self.ed_seed]
        row.addStretch(1)
        layout.addLayout(row)

        log_row = QHBoxLayout()
        self.chk_debug_log = QCheckBox("")
        log_row.addWidget(self.chk_debug_log)
        self.lbl_debug_log_path = QLabel("")
        log_row.addWidget(self.lbl_debug_log_path)
        self.ed_debug_log_path = QLineEdit("")
        log_row.addWidget(self.ed_debug_log_path)
        log_row.addStretch(1)
        layout.addLayout(log_row)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("")
        self.btn_stop = QPushButton("")
        self.btn_apply_best = QPushButton("")
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_apply_best)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.lbl_progress = QLabel("")
        layout.addWidget(self.lbl_progress)

        self.table_best = QTableWidget(0, 3)
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
            project_dir = getattr(self.ctrl.win, "project_dir", None)
            if project_dir:
                return project_dir
            return os.path.dirname(self.ctrl.win.current_file)
        return os.getcwd()

    def _manager(self) -> CaseRunManager:
        project_uuid = getattr(self.ctrl, "project_uuid", "") if self.ctrl else ""
        return CaseRunManager(self._project_dir(), project_uuid=project_uuid)

    def _case_label_text(self) -> str:
        lang = getattr(self.ctrl, "ui_language", "en")
        cases = self._manager().list_cases()
        if not cases:
            return "--"
        return tr(lang, "analysis.all_cases")

    def _case_options(self) -> List[tuple[str, str]]:
        options: List[tuple[str, str]] = []
        for case in self._manager().list_cases():
            label = f"{case.name} ({case.case_id})"
            options.append((label, case.case_id))
        return options

    def _case_combo(self, parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        lang = getattr(self.ctrl, "ui_language", "en")
        combo.addItem(tr(lang, "analysis.all_cases"), None)
        for label, case_id in self._case_options():
            combo.addItem(label, case_id)
        return combo

    def _refresh_case_combo_options(self, table: QTableWidget, column: int) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        options = self._case_options()
        for row in range(table.rowCount()):
            combo = table.cellWidget(row, column)
            if not isinstance(combo, QComboBox):
                continue
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr(lang, "analysis.all_cases"), None)
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
            self.table_best.setRowCount(1)
        self._refresh_best_objective_display()

    def apply_language(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self._set_cases_label(self._case_label_text())
        self.group_vars.setTitle(tr(lang, "analysis.design_variables"))
        self.group_obj.setTitle(tr(lang, "analysis.objectives"))
        self.group_con.setTitle(tr(lang, "analysis.constraints"))
        self.group_run.setTitle(tr(lang, "analysis.optimization_run"))
        self.btn_add_var.setText(tr(lang, "analysis.add"))
        self.btn_del_var.setText(tr(lang, "analysis.remove"))
        self.btn_add_obj.setText(tr(lang, "analysis.add"))
        self.btn_del_obj.setText(tr(lang, "analysis.remove"))
        self.btn_add_con.setText(tr(lang, "analysis.add"))
        self.btn_del_con.setText(tr(lang, "analysis.remove"))
        self.lbl_evals.setText(tr(lang, "analysis.evals"))
        self.lbl_seed.setText(tr(lang, "analysis.seed"))
        self.chk_debug_log.setText(tr(lang, "analysis.debug_log_enable"))
        self.lbl_debug_log_path.setText(tr(lang, "analysis.debug_log_path"))
        self.ed_debug_log_path.setPlaceholderText("logs/optimization_debug.log")
        self.btn_run.setText(tr(lang, "analysis.run"))
        self.btn_stop.setText(tr(lang, "analysis.stop"))
        self.btn_apply_best.setText(tr(lang, "analysis.apply_best"))
        self._set_progress_label(self._progress_value)
        self.table_vars.setHorizontalHeaderLabels(
            [
                tr(lang, "table.enabled"),
                tr(lang, "analysis.case"),
                tr(lang, "analysis.variable_type"),
                tr(lang, "analysis.variable_name"),
                tr(lang, "analysis.variable_current"),
                tr(lang, "analysis.variable_lower"),
                tr(lang, "analysis.variable_upper"),
            ]
        )
        self.table_obj.setHorizontalHeaderLabels(
            [
                tr(lang, "table.enabled"),
                tr(lang, "analysis.case"),
                tr(lang, "analysis.direction"),
                tr(lang, "analysis.expression"),
            ]
        )
        self.table_con.setHorizontalHeaderLabels(
            [
                tr(lang, "table.enabled"),
                tr(lang, "analysis.case"),
                tr(lang, "analysis.expression"),
                tr(lang, "analysis.comparator"),
                tr(lang, "analysis.limit"),
            ]
        )
        self._set_best_table_headers(self._best_var_names or self._collect_enabled_variable_names())

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
        lang = getattr(self.ctrl, "ui_language", "en")
        self.lbl_active.setText(tr(lang, "analysis.cases_label").format(cases=text))

    def _set_progress_label(self, value: str) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self._progress_value = value
        self.lbl_progress.setText(tr(lang, "analysis.progress").format(value=value))

    def ensure_defaults(self) -> None:
        if self.table_vars.rowCount() == 0:
            self.add_variable_row("P12.x")
            self.add_variable_row("P12.y")
        if self.table_obj.rowCount() == 0:
            self.add_objective_row(direction="min", expression="max(load.P9.Mag)")
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
            "seed": self.ed_seed.text(),
            "debug_log": {
                "enabled": bool(self.chk_debug_log.isChecked()),
                "path": self.ed_debug_log_path.text(),
            },
            "variables": variables,
            "objectives": objectives,
            "constraints": constraints,
        }

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        if not isinstance(settings, dict) or not settings:
            return
        self.table_vars.setRowCount(0)
        self.table_obj.setRowCount(0)
        self.table_con.setRowCount(0)

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
        if "seed" in settings:
            self.ed_seed.setText(str(settings.get("seed", "")))
        debug_log = settings.get("debug_log", {}) or {}
        self.chk_debug_log.setChecked(bool(debug_log.get("enabled", False)))
        self.ed_debug_log_path.setText(str(debug_log.get("path", "")))

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
        lang = getattr(self.ctrl, "ui_language", "en")
        self._best_var_names = list(var_names)
        headers = [tr(lang, "analysis.best_objective")] + self._best_var_names
        self.table_best.setColumnCount(len(headers))
        self.table_best.setHorizontalHeaderLabels(headers)

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

    def _optimization_functions(self) -> Dict[str, List[str]]:
        return {
            "Aggregates": ["max(", "min(", "mean(", "rms(", "abs(", "first(", "last("],
            "Operators": ["+", "-", "*", "/", "(", ")", ","],
        }

    def _optimization_token_groups(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        groups["Input/Output"] = ["input_deg", "output_deg"]

        measurements = [name for name, _val, _unit in self.ctrl.get_measure_values()]
        load_measures = [name for name, _val in self.ctrl.get_load_measure_values()]

        manager = self._manager()
        for info in manager.list_cases():
            case_spec = manager.load_case_spec(info.case_id) or {}
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
        if col != 3:
            return
        lang = getattr(self.ctrl, "ui_language", "en")
        menu = QMenu(self)
        act_builder = menu.addAction(tr(lang, "analysis.expression_builder"))
        selected = menu.exec(self.table_obj.viewport().mapToGlobal(pos))
        if selected == act_builder:
            self._open_expression_builder_for_objective(row)

    def _open_constraint_context_menu(self, pos) -> None:
        item = self.table_con.itemAt(pos)
        if not item:
            return
        row = item.row()
        col = item.column()
        if col != 2:
            return
        lang = getattr(self.ctrl, "ui_language", "en")
        menu = QMenu(self)
        act_builder = menu.addAction(tr(lang, "analysis.expression_builder"))
        selected = menu.exec(self.table_con.viewport().mapToGlobal(pos))
        if selected == act_builder:
            self._open_expression_builder_for_constraint(row)

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
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
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
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
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
                QMessageBox.warning(self, "Variables", "Bounds must be numeric.")
                return None
            if lower is None or upper is None:
                QMessageBox.warning(self, "Variables", f"Bounds required for {name}.")
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
                    QMessageBox.warning(self, "Constraints", "Constraint limits must be numeric.")
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

    def _collect_case_specs(self) -> Dict[str, Dict[str, Any]]:
        manager = self._manager()
        case_specs: Dict[str, Dict[str, Any]] = {}
        for info in manager.list_cases():
            spec = manager.load_case_spec(info.case_id)
            if spec:
                case_specs[info.case_id] = spec
        return case_specs

    def run_optimization(self) -> None:
        self.ensure_defaults()
        variables = self._collect_variables()
        if variables is None:
            return
        self._set_best_table_headers([var.name for var in variables if var.enabled])
        objectives = self._collect_objectives()
        constraints = self._collect_constraints()

        case_specs = self._collect_case_specs()
        if not case_specs:
            QMessageBox.warning(self, "Optimization", "No cases available.")
            return
        model_snapshot = self.ctrl.snapshot_model()

        try:
            evals = int(float(self.ed_evals.text() or "50"))
        except Exception:
            evals = 50
        seed_text = (self.ed_seed.text() or "").strip()
        seed = int(seed_text) if seed_text else None
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
            seed=seed,
            enable_debug_log=enable_debug_log,
            debug_log_path=debug_log_path,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_progress_label("0")
        self._worker.start()

    def stop_optimization(self) -> None:
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(True)

    def _on_progress(self, payload: Dict[str, Any]) -> None:
        idx = payload.get("index", 0)
        best = payload.get("best", {})
        self._set_progress_label(str(idx))
        if best and best.get("vars"):
            self._best_vars = dict(best.get("vars", {}))
            self._update_best_table(best)

    def _on_finished(self, payload: Dict[str, Any]) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if payload and payload.get("vars"):
            self._best_vars = dict(payload.get("vars", {}))
            self._update_best_table(payload)
        self._set_progress_label(tr(getattr(self.ctrl, "ui_language", "en"), "analysis.done"))

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
        for idx, key in enumerate(self._best_var_names, start=1):
            val = self._best_vars.get(key)
            item = QTableWidgetItem("--" if val is None else f"{val:.4f}")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_best.setItem(0, idx, item)

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
        obj_item = QTableWidgetItem("--" if obj_val is None else f"{obj_val:.4f}")
        obj_item.setFlags(obj_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table_best.setItem(0, 0, obj_item)

    def apply_best(self) -> None:
        if not self._best_vars:
            QMessageBox.information(self, "Optimization", "No best solution yet.")
            return
        for name, val in self._best_vars.items():
            if not name.startswith("P") or "." not in name:
                if name.startswith("Link") and name.endswith(".L"):
                    lid_str = name[len("Link") : -len(".L")]
                    try:
                        lid = int(lid_str)
                    except Exception:
                        continue
                    link = self.ctrl.links.get(lid)
                    if not link or link.get("ref", False):
                        continue
                    self.ctrl.cmd_set_link_length(lid, float(val))
                elif name.startswith("Param."):
                    param_name = name[len("Param.") :].strip()
                    if param_name:
                        self.ctrl.cmd_set_param(param_name, float(val))
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
        self._refresh_best_objective_display()
