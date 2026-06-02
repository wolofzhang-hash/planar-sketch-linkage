# -*- coding: utf-8 -*-
"""Analysis tabs: Animation + Optimization."""

from __future__ import annotations

import ast
import csv
import importlib.util
import json
import math
import os
import tempfile
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
    QSizePolicy,
    QScrollArea,
    QFrame,
)

from ...core.replay_service import ReplayService
from ...core.run_service import RunService
from ..plot_window import PlotWindow
from ..i18n import tr, get_ui_language


def _lang(owner) -> str:
    ctrl = getattr(owner, "ctrl", owner)
    return get_ui_language(ctrl, fallback="zh")

def _tr(owner, key: str, **kwargs) -> str:
    return tr(_lang(owner), key, **kwargs)


def _is_zh(owner) -> bool:
    return _lang(owner) == 'zh'


def _is_en(owner) -> bool:
    return _lang(owner) == 'en'





class AnimationTab(QWidget):
    def __init__(self, ctrl: Any, run_service: Optional[RunService] = None, run_case_callback=None, on_active_case_changed=None):
        super().__init__()
        self.ctrl = ctrl
        self._run_service = run_service or RunService(ctrl)
        self._replay_service = ReplayService()
        self._run_case_callback = run_case_callback
        self._plots_dialog: Optional[_OptimizationPlotsDialog] = None
        self._on_active_case_changed = on_active_case_changed

        # State (keep explicit to avoid AttributeError crashes on startup)
        self._plot_window: Optional[PlotWindow] = None
        self._loaded_case_id: Optional[str] = None
        self._replay_reset_snapshot: Dict[int, Any] = {}
        self._live_pose_before_replay: Dict[int, Any] = {}
        self._pending_autoload_case_id: Optional[str] = None
        self._selected_case_id: Optional[str] = None

        # Use a scroll area so the bottom replay/plot controls are always reachable
        # even when the Analysis dock is short.
        outer = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)

        content = QWidget()
        self._scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

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
        action_row.addWidget(self.btn_set_active)

        # Tools: Plot / Screenshot / GIF
        self.btn_plot = QPushButton("")
        self.btn_capture = QPushButton("")
        self.btn_gif = QPushButton("")
        action_row.addWidget(self.btn_plot)
        action_row.addWidget(self.btn_capture)
        action_row.addWidget(self.btn_gif)

        action_row.addStretch(1)
        layout.addLayout(action_row)

        layout.addWidget(self._build_replay_group())

        self.btn_set_active.clicked.connect(self.set_active_case)
        self.btn_plot.clicked.connect(self.open_plot)
        self.btn_capture.clicked.connect(self.capture_screenshot)
        self.btn_gif.clicked.connect(self.record_gif)
        self.table_case_runs.customContextMenuRequested.connect(self._open_case_run_context_menu)

        # Case selection should not require the user to manually pick a "run".
        # Each case has at most one persisted run (runs/<case_name>/current).
        self.table_case_runs.itemSelectionChanged.connect(self._on_case_selected)

        self._cases_cache: List[Any] = []
        self._row_cache: List[Dict[str, Any]] = []
        self._session_project_dir = ""
        self._frames: List[Dict[str, Any]] = []
        self._frame_index = 0
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame_tick)

    def preferred_panel_width(self) -> int:
        return 520

    def _on_frame_tick(self) -> None:
        """Timer tick handler for replay."""
        self._advance_frame()

    def _clear_loaded_replay(self, *, restore_live_pose: bool = False) -> None:
        """Forget any loaded replay payload and optionally restore the live model pose."""
        try:
            if self._frame_timer.isActive():
                self._frame_timer.stop()
        except Exception:
            pass
        if restore_live_pose and isinstance(self._live_pose_before_replay, dict) and self._live_pose_before_replay:
            try:
                self.ctrl.apply_points_snapshot(self._live_pose_before_replay)
                self.ctrl.update_graphics()
                if getattr(self.ctrl, "panel", None):
                    self.ctrl.panel.defer_refresh_all(keep_selection=True)
            except Exception:
                pass
        self._frames = []
        self._frame_index = 0
        self._loaded_case_id = None
        self._pending_autoload_case_id = None
        self._replay_reset_snapshot = {}
        self._live_pose_before_replay = {}
        try:
            self.slider_frame.blockSignals(True)
            self.slider_frame.setRange(0, 0)
            self.slider_frame.setValue(0)
            self.slider_frame.blockSignals(False)
        except Exception:
            pass
        self._set_frame_label(0, 0)

    def _on_case_selected(self) -> None:
        """Remember the user's explicit table selection without side effects."""
        case_name = self._selected_case_name_from_view()
        self._selected_case_id = case_name
        if case_name and self._pending_autoload_case_id and self._pending_autoload_case_id != case_name:
            self._pending_autoload_case_id = None
        # A loaded replay belongs to exactly one case. Once the user selects a
        # different case, do not keep replaying the previous case silently.
        if case_name and self._loaded_case_id and str(case_name) != str(self._loaded_case_id):
            self._clear_loaded_replay(restore_live_pose=True)

    def on_case_run_saved(self, case_name: str) -> None:
        """Callback from SimPanel when a case run is saved/updated.

        We keep runs minimal: each case overwrites runs/<case_name>/current.
        After a run finishes, if this case is currently active (or the user
        requested an autoload), we immediately load its latest frames so replay
        works without extra clicks.
        """
        if not case_name:
            return

        # Autoload only for an explicit replay request. A plain numeric Run
        # must not snap the replay UI back to frame 0 just because the case has
        # a saved run.
        autoload_requested = (self._pending_autoload_case_id == case_name)
        if autoload_requested:
            self._pending_autoload_case_id = None
        else:
            try:
                self.refresh_cases()
            except Exception:
                pass
            return

        try:
            self.refresh_cases()
            manager = self._run_service.manager()
            runs = self._run_service.list_runs(case_name)
            if runs:
                # Do not prompt to stop replay here; we are refreshing the current result.
                self.stop_replay()
                self._load_run_data_for_run(runs[0], case_name)
        except Exception:
            pass


    def _run_case_now(self, case_name: str, autoload_after_run: bool = False) -> None:
        """Run the selected case using its stored case spec."""
        spec = self._run_service.load_case_spec(case_name) or {}
        if self._run_case_callback is None:
            QMessageBox.warning(self, _tr(self, "run.title"), _tr(self, "run.msg.sim_panel_missing"))
            return
        try:
            self._run_service.set_active_case(case_name)
            self._set_active_label(case_name)
        except Exception:
            pass
        self._pending_autoload_case_id = case_name if autoload_after_run else None
        try:
            self._run_case_callback(case_name, spec)
        except Exception as exc:
            QMessageBox.critical(self, _tr(self, "run.title"), _tr(self, "run.msg.start_failed", exc=exc))

    def _run_contains_pose_points(self, run: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(run, dict):
            return False
        return self._replay_service.run_contains_pose_points(run)

    def _resolve_run_for_case(self, case_name: str, prompt_to_run: bool = True) -> Optional[Dict[str, Any]]:
        """Return a run dict for case_name, prompting to run if needed."""
        runs = self._run_service.list_runs(case_name)
        run = runs[0] if runs else None
        dirty = False
        try:
            dirty = bool(self.ctrl.case_needs_rerun(case_name)) if hasattr(self.ctrl, "case_needs_rerun") else False
        except Exception:
            dirty = False

        if run and not dirty:
            if self._run_contains_pose_points(run):
                return run
            # Old runs without pose_points cannot be replayed independently;
            # make the user rerun once so replay becomes case-isolated.
            dirty = True
        if not prompt_to_run:
            return None

        if run is None:
            msg = "This case has no saved run yet. Run this case now?"
        else:
            msg = "Model has changed since the last run. Re-run this case now?"
        confirm = QMessageBox.question(self, _tr(self, "run.title"), msg)
        if confirm == QMessageBox.StandardButton.Yes:
            self._run_case_now(case_name, autoload_after_run=True)
        return None

    def _project_dir(self) -> str:
        return self._run_service.project_dir()

    def _manager(self):
        return self._run_service.manager()

    def _case_label_text(self) -> str:
        cases = self._run_service.list_cases()
        if not cases:
            return "--"
        return _tr(self, "analysis.all_cases")

    def _case_options(self) -> List[tuple[str, str]]:
        options: List[tuple[str, str]] = []
        for case in self._run_service.list_cases():
            label = str(getattr(case, "label", case.name))
            options.append((label, str(case.name)))
        return options

    def _case_combo(self, parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItem(_tr(self, "analysis.all_cases"), None)
        for label, case_name in self._case_options():
            combo.addItem(label, case_name)
        return combo

    def _case_ids_from_combo(self, combo: Optional[QComboBox]) -> Optional[List[str]]:
        if not isinstance(combo, QComboBox):
            return None
        data = combo.currentData()
        if data is None:
            return None
        return [str(data)]

    def refresh_cases(self) -> None:
        """Refresh case table in a *display-only* way.

        Important design rule for template insertion and model editing: cases are
        part of the model, but refreshing the UI must not trigger analysis work.
        Therefore this method intentionally avoids scanning run folders for every
        case and avoids auto-loading run data. Run information is loaded only on
        explicit user actions (e.g. clicking "Load run data" or running).
        """
        manager = self._run_service.manager()
        # Preserve the user's explicit table selection across refreshes. Do not
        # silently jump back to the active case, otherwise the top-level Run can
        # appear to rerun the wrong case right after another case was saved.
        preferred_case = self._selected_case_id or self._selected_case_name_from_view()
        cases = manager.list_cases()
        self._cases_cache = cases
        rows: List[Dict[str, Any]] = []
        for info in cases:
            # Lazy UI refresh: do not enumerate runs here. This keeps template
            # insertion/editing responsive when many cases exist.
            rows.append({"case": info, "run": None, "kind": "case"})
        self._row_cache = rows
        self.table_case_runs.setRowCount(len(rows))
        for row, payload in enumerate(rows):
            case_info = payload["case"]
            is_case_row = payload.get("kind") == "case"
            case_label = str(getattr(case_info, "label", case_info.name))
            # Column 2 re-used as case state in lazy mode (instead of eager run summary).
            ctrl = getattr(self, "ctrl", None)
            dirty = False
            try:
                dirty = bool(ctrl.case_needs_rerun(case_label)) if ctrl is not None and hasattr(ctrl, "case_needs_rerun") else False
            except Exception:
                dirty = False
            status_text = _tr(self, "analysis.status.rerun_needed") if dirty else _tr(self, "analysis.status.ready")
            items = [
                QTableWidgetItem(case_label),
                QTableWidgetItem(status_text),
                QTableWidgetItem(""),
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
        if preferred_case:
            self._select_case_row(preferred_case)
        elif active:
            self._select_case_row(active)
        # Keep optimization UI in sync with case list, but do not force any
        # case/run evaluation here.
        if hasattr(self.ctrl, "win") and getattr(self.ctrl.win, "sim_panel", None):
            sim_panel = self.ctrl.win.sim_panel
            if hasattr(sim_panel, "optimization_tab"):
                sim_panel.optimization_tab.refresh_case_label()

    def apply_language(self) -> None:
        self.table_case_runs.setHorizontalHeaderLabels(
            [
                _tr(self, "analysis.case"),
                _tr(self, "table.state"),
                _tr(self, "table.info"),
            ]
        )
        self.lbl_cases_runs.setText(_tr(self, "analysis.cases"))
        self.btn_set_active.setText(_tr(self, "analysis.set_active_case"))
        self.btn_plot.setText(_tr(self, "analysis.plot"))
        self.btn_capture.setText(_tr(self, "analysis.capture_image"))
        self.btn_gif.setText(_tr(self, "analysis.record_gif"))
        self.group_replay.setTitle(_tr(self, "analysis.replay_plot"))
        self.btn_replay_play.setText(_tr(self, "analysis.play"))
        self.btn_replay_pause.setText(_tr(self, "analysis.pause"))
        self.btn_replay_stop.setText(_tr(self, "analysis.stop"))
        self._set_active_label(self._manager().get_active_case() or "--")
        self._set_frame_label(self._frame_index, len(self._frames))

    def reset_to_first_frame(self) -> None:
        """Reset replay UI to the first frame.

        This is used when switching into the Animation tab to avoid confusing
        initial poses (e.g. cross branch) after re-runs.
        """
        try:
            self.pause_replay()
        except Exception:
            pass
        try:
            self._frame_index = 0
        except Exception:
            pass
        try:
            self.slider_frame.blockSignals(True)
            self.slider_frame.setValue(0)
        finally:
            try:
                self.slider_frame.blockSignals(False)
            except Exception:
                pass
        try:
            self._apply_frame(0)
        except Exception:
            pass

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
        # Mixed column policy: narrow control columns fixed-ish, expression/name columns stretch.
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
        self._clear_loaded_replay()
        if self._plot_window is not None:
            self._plot_window.close()
            self._plot_window = None

    def _set_active_label(self, case_name: str) -> None:
        label = self._manager().case_display_name(case_name) if case_name not in (None, "--") else case_name
        self.lbl_active.setText(_tr(self, "analysis.active_case").format(case=label))

    def _set_frame_label(self, index: int, total: int) -> None:
        if total <= 0:
            self.lbl_frame.setText(_tr(self, "analysis.frame").format(current="--"))
            return
        self.lbl_frame.setText(_tr(self, "analysis.frame").format(current=f"{index + 1}/{total}"))

    def _selected_case_name_from_view(self) -> Optional[str]:
        """Read the currently selected case row directly from the table view."""
        row = -1
        try:
            sm = self.table_case_runs.selectionModel()
            if sm is not None:
                rows = sm.selectedRows()
                if rows:
                    row = rows[0].row()
        except Exception:
            row = -1
        if row < 0:
            try:
                row = self.table_case_runs.currentRow()
            except Exception:
                row = -1
        if row < 0 or row >= len(self._row_cache):
            try:
                item = self.table_case_runs.currentItem()
                if item is not None:
                    row = item.row()
            except Exception:
                row = -1
        if row < 0 or row >= len(self._row_cache):
            return None
        try:
            return str(self._row_cache[row]["case"].name)
        except Exception:
            return None

    def _selected_case_name(self) -> Optional[str]:
        case_name = self._selected_case_name_from_view()
        if case_name:
            self._selected_case_id = case_name
            return case_name
        if self._selected_case_id:
            for payload in self._row_cache:
                try:
                    if str(payload["case"].name) == str(self._selected_case_id):
                        return str(self._selected_case_id)
                except Exception:
                    continue
        return None

    def selected_case_name(self) -> Optional[str]:
        """Public accessor used by SimPanel to rerun the currently selected case.

        Keeping this as a tiny wrapper avoids more cross-widget coupling.
        """
        return self._selected_case_name()

    def run_selected_case(self, *, autoload_after_run: bool = False) -> bool:
        """Run exactly the case the user selected in the animation table."""
        case_name = self._selected_case_name()
        if not case_name:
            return False
        self._run_case_now(str(case_name), autoload_after_run=autoload_after_run)
        return True

    def selected_case_spec(self) -> Optional[Dict[str, Any]]:
        """Return the stored spec of the currently selected case, if any."""
        case_name = self._selected_case_name()
        if not case_name:
            return None
        try:
            spec = self._manager().load_case_spec(str(case_name)) or {}
        except Exception:
            spec = {}
        return dict(spec) if isinstance(spec, dict) and spec else None


    def _selected_run(self) -> Optional[Dict[str, Any]]:
        row = self.table_case_runs.currentRow()
        if row < 0 or row >= len(self._row_cache):
            return None
        return self._row_cache[row].get("run")

    def open_run_folder(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.select_case_first"))
            return
        run = self._resolve_run_for_case(case_name, prompt_to_run=False)
        if not run:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.no_saved_run_for_case"))
            return
        path = run.get("path")
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def load_run_snapshot(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.select_case_first"))
            return
        run = self._resolve_run_for_case(case_name, prompt_to_run=False)
        if not run:
            QMessageBox.information(self, _tr(self, "run.title"), _tr(self, "run.msg.no_saved_run_for_case"))
            return
        win = getattr(self.ctrl, "win", None)
        if win and hasattr(win, "confirm_unsaved_run"):
            if not win.confirm_unsaved_run():
                return
        path = os.path.join(run.get("path", ""), "model.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, _tr(self, "run.title"), _tr(self, "run.msg.model_json_not_found"))
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.loads(fh.read())
            warnings, errors = self.ctrl.validate_project_schema(raw)
            if win and hasattr(win, "_report_schema_issues"):
                if not win._report_schema_issues(warnings, errors, "load"):
                    return
            elif errors:
                QMessageBox.critical(self, _tr(self, "run.title"), "\n".join(errors))
                return
            data = self.ctrl.merge_project_dict(raw)
            if not self.ctrl.load_dict(data, action="load a run snapshot"):
                return
            if self.ctrl.panel:
                self.ctrl.panel.defer_refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, _tr(self, "run.title"), _tr(self, "run.msg.load_snapshot_failed", exc=exc))

    def set_active_case(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "case.title"), _tr(self, "run.msg.select_case_first"))
            return
        if not self.confirm_stop_replay("switch cases"):
            return
        manager = self._run_service.manager()
        manager.set_active_case(case_name)
        self._set_active_label(case_name)
        if self._on_active_case_changed:
            self._on_active_case_changed()
        # Case switching only changes the active case definition.
        # It must not auto-load old run data or prompt for re-run repeatedly.
        self.refresh_cases()

    def _build_replay_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_replay = group
        layout = QVBoxLayout(group)

        controls = QHBoxLayout()
        self.btn_replay_play = QPushButton("")
        self.btn_replay_pause = QPushButton("")
        self.btn_replay_stop = QPushButton("")
        controls.addWidget(self.btn_replay_play)
        controls.addWidget(self.btn_replay_pause)
        controls.addWidget(self.btn_replay_stop)
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
        return group

    def rename_case(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "case.title"), _tr(self, "run.msg.select_case_first"))
            return
        manager = self._run_service.manager()
        current_label = manager.case_display_name(case_name)
        new_id, ok = QInputDialog.getText(
            self,
            _tr(self, "analysis.rename_case"),
            _tr(self, "analysis.rename_case_label", default="Display name:"),
            text=current_label,
        )
        if not ok:
            return
        if manager.rename_case(case_name, new_id):
            self.refresh_cases()
        else:
            QMessageBox.warning(self, _tr(self, "case.title"), _tr(self, "case.msg.rename_case_failed"))

    def delete_case_results(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "case.title"), _tr(self, "run.msg.select_case_first"))
            return
        confirm = QMessageBox.question(
            self,
            "Delete Results",
            f"Delete all runs for case {case_name}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        manager = self._run_service.manager()
        manager.delete_case_runs(case_name)
        if self._loaded_case_id and str(self._loaded_case_id) == str(case_name):
            self._clear_loaded_replay(restore_live_pose=True)
        self.refresh_cases()

    def delete_case(self) -> None:
        case_name = self._selected_case_name()
        if not case_name:
            QMessageBox.information(self, _tr(self, "case.title"), _tr(self, "run.msg.select_case_first"))
            return
        confirm = QMessageBox.question(
            self,
            "Delete Case",
            f"Delete case {case_name} and all runs?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        manager = self._run_service.manager()
        if manager.delete_case(case_name):
            if self._loaded_case_id and str(self._loaded_case_id) == str(case_name):
                self._clear_loaded_replay(restore_live_pose=True)
            self.refresh_cases()
        else:
            QMessageBox.warning(self, _tr(self, "case.title"), _tr(self, "case.msg.delete_failed"))

    def _load_run_data_for_run(self, run: Dict[str, Any], case_name: Optional[str]) -> None:
        # Replay is read-only: it must depend only on saved pose_points and must
        # never re-solve against the current live model/case state.
        current_live_pose = {}
        try:
            current_live_pose = self.ctrl.snapshot_points()
        except Exception:
            current_live_pose = {}
        self._clear_loaded_replay(restore_live_pose=False)
        path = run.get("path")
        if not path:
            return
        validation_errors = self._replay_service.validate_run(run)
        if validation_errors:
            QMessageBox.warning(self, _tr(self, "run.title"), "\n".join(validation_errors))
            return
        try:
            frames = [self._coerce_frame_row(row) for row in self._replay_service.load_frame_rows(run)]
        except Exception as exc:
            QMessageBox.critical(self, _tr(self, "run.title"), _tr(self, "run.msg.load_frames_failed", exc=exc))
            return
        if not frames or not any(isinstance(f.get("pose_points"), list) and f.get("pose_points") for f in frames):
            QMessageBox.information(
                self,
                _tr(self, "run.title"),
                "This saved run does not contain replay poses yet. Please re-run this case once.",
            )
            return
        self._live_pose_before_replay = dict(current_live_pose) if isinstance(current_live_pose, dict) else {}
        self._replay_reset_snapshot = None
        self._frames = frames
        self._frame_index = 0
        self.slider_frame.setRange(0, max(0, len(self._frames) - 1))
        self.slider_frame.setValue(0)
        self._apply_frame(0)
        self._refresh_plot_window()
        if case_name:
            self._loaded_case_id = case_name

    def _select_case_row(self, case_name: str) -> None:
        self._selected_case_id = str(case_name) if case_name else None
        for row, payload in enumerate(self._row_cache):
            if payload["case"].name == case_name:
                self.table_case_runs.selectRow(row)
                try:
                    self.table_case_runs.setCurrentCell(row, 0)
                except Exception:
                    pass
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
    def open_plot(self) -> None:
        """UI handler for the Plot button.

        Kept deliberately minimal: plotting is only available when frames are loaded.
        """
        self.open_plot_window()

    def open_plot_window(self) -> None:
        if not self._frames:
            QMessageBox.information(self, _tr(self, "plot.title"), _tr(self, "run.msg.no_run_data_loaded"))
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
            QMessageBox.warning(self, _tr(self, "screenshot.title"), _tr(self, "screenshot.msg.no_view"))
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
            QMessageBox.warning(self, _tr(self, "screenshot.title"), _tr(self, "screenshot.msg.save_failed"))
            return
        QMessageBox.information(self, _tr(self, "screenshot.title"), _tr(self, "screenshot.msg.saved"))

    def record_gif(self) -> None:
        if not self._frames:
            QMessageBox.information(self, _tr(self, "gif.title"), _tr(self, "gif.msg.run_case_first"))
            return
        if importlib.util.find_spec("imageio") is None:
            QMessageBox.warning(self, _tr(self, "gif.title"), _tr(self, "gif.msg.imageio_missing"))
            return
        view = self._view_widget()
        if view is None:
            QMessageBox.warning(self, _tr(self, "gif.title"), _tr(self, "screenshot.msg.no_view"))
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
        QMessageBox.information(self, _tr(self, "gif.title"), _tr(self, "gif.msg.saved"))

    def _apply_frame(self, index: int) -> None:
        if not self._frames:
            return
        idx = max(0, min(index, len(self._frames) - 1))
        frame = self._frames[idx]
        # Fast path: if the run data recorded point coordinates, apply them
        # directly. This avoids calling the numeric solver on every frame
        # and makes replay/animation much smoother for 4-bar and larger models.
        pose = frame.get("pose_points")
        if isinstance(pose, list) and pose:
            try:
                snap = {int(pid): (float(x), float(y)) for pid, x, y in pose if pid is not None}
                self.ctrl.apply_points_snapshot(snap)
                self.ctrl.update_graphics()
                if getattr(self.ctrl, "panel", None):
                    self.ctrl.panel.defer_refresh_all()
            except Exception:
                pose = None

        if pose is not None:
            # Pose applied; skip re-solving.
            self._frame_index = idx
            self._set_frame_label(idx, len(self._frames))
            if self._plot_window is not None and self._plot_window.isVisible():
                self._plot_window.set_frame_index(idx)
                if self._frame_timer.isActive():
                    self._plot_window.bring_to_front()
            return

        # Replay requires saved pose_points. Do not re-solve against the current
        # live model; that would couple different cases through current UI state.
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
            # Stop at the end and restore the start pose to avoid switching
            # to the other assembly branch on wrap-around.
            self.stop_replay()
            return
        self.slider_frame.setValue(next_idx)

    def _on_slider_changed(self, value: int) -> None:
        self._apply_frame(value)

    def release_replay_model_state(self) -> None:
        """Detach replay from the live model before a numeric run/edit."""
        self._clear_loaded_replay(restore_live_pose=True)

    def play_replay(self) -> None:
        selected_case = self._selected_case_name()
        if self._frames and self._loaded_case_id and selected_case and str(selected_case) != str(self._loaded_case_id):
            # Loaded replay data belongs to another case; never keep replaying it
            # when the user has selected a different case.
            self._clear_loaded_replay()
        if not self._frames:
            case_name = self._selected_case_name()
            if case_name:
                run = self._resolve_run_for_case(case_name, prompt_to_run=False)
                if run:
                    ask = QMessageBox.question(
                        self,
                        _tr(self, "run.title"),
                        _tr(
                            self,
                            "analysis.msg.load_run_for_play",
                            default="Load saved run data for the current case and start replay?",
                        ),
                    )
                    if ask == QMessageBox.StandardButton.Yes:
                        self._load_run_data_for_run(run, case_name)
                        if self._frames:
                            self._frame_timer.start(50)
                        return
                elif self.ctrl.case_needs_rerun(case_name) if hasattr(self.ctrl, "case_needs_rerun") else False:
                    ask = QMessageBox.question(
                        self,
                        _tr(self, "run.title"),
                        _tr(
                            self,
                            "analysis.msg.model_changed_rerun",
                            default="The model changed after the saved run. Re-run this case now?",
                        ),
                    )
                    if ask == QMessageBox.StandardButton.Yes:
                        self._run_case_now(case_name, autoload_after_run=True)
                    return
            QMessageBox.information(self, _tr(self, "replay.title"), _tr(self, "replay.msg.load_run_data_first"))
            return
        if self._frame_index >= len(self._frames) - 1:
            self.slider_frame.setValue(0)
        self._frame_timer.start(50)

    def pause_replay(self) -> None:
        if self._frame_timer.isActive():
            self._frame_timer.stop()

    def stop_replay(self) -> None:
        """Stop replay and fully restore the pre-replay live model pose.

        Replay must be read-only. Once the user stops playback (or playback
        reaches the end), the live model should go back to the exact pose it had
        before any saved run frames were loaded/applied. Keeping the loaded run's
        frame-0 pose in the live model is what lets replay leak into later run /
        save operations.
        """
        try:
            if self._frame_timer.isActive():
                self._frame_timer.stop()
        except Exception:
            pass
        restore_pose = dict(self._live_pose_before_replay) if isinstance(self._live_pose_before_replay, dict) else {}
        # Forget the loaded replay payload completely; the next Play action may
        # explicitly load again from disk, but replay must not keep owning the
        # live model state after Stop/end.
        self._clear_loaded_replay(restore_live_pose=False)
        if restore_pose:
            try:
                self.ctrl.apply_points_snapshot(restore_pose)
                self.ctrl.update_graphics()
                if getattr(self.ctrl, "panel", None):
                    self.ctrl.panel.defer_refresh_all(keep_selection=True)
            except Exception:
                pass
        self._frame_index = 0
        self._set_frame_label(0, 0)

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
        menu = QMenu(self)
        act_set_active = menu.addAction(_tr(self, "analysis.set_active_case"))
        menu.addSeparator()
        act_open_run = menu.addAction(_tr(self, "analysis.open_run_folder"))
        act_load_snapshot = menu.addAction(_tr(self, "analysis.load_run_snapshot"))
        menu.addSeparator()
        act_rename_case = menu.addAction(_tr(self, "analysis.rename_case"))
        act_delete_case_results = menu.addAction(_tr(self, "analysis.delete_case_results"))
        act_delete_case = menu.addAction(_tr(self, "analysis.delete_case"))

        selected = menu.exec(self.table_case_runs.viewport().mapToGlobal(pos))
        if selected == act_set_active:
            self.set_active_case()
        elif selected == act_open_run:
            self.open_run_folder()
        elif selected == act_load_snapshot:
            self.load_run_snapshot()
        elif selected == act_rename_case:
            self.rename_case()
        elif selected == act_delete_case_results:
            self.delete_case_results()
        elif selected == act_delete_case:
            self.delete_case()

from .optimization_widgets import _OptimizationPlotsDialog
