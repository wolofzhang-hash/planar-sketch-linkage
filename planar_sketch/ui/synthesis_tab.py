# -*- coding: utf-8 -*-
"""Synthesis / smart setup tab.

This tab is intended to:
- accept user I/O mapping requirements (input vs output target points)
- recommend/insert a starter topology (template)
- auto-generate: measurements, multiple cases, and an optimization preset

The current implementation focuses on a single-case curve shaping workflow:

- User provides target "input angle vs output angle" keypoints.
- System inserts a 4-bar starter topology (scaled by axis distance).
- A single sweep case is created (one case only).
- Optimization preset is generated using curve RMS and max-abs error.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from ..intel.synthesis_registry import list_supported_template_ids, template_display_label

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class _SynthesisPreviewPlotDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        self.fig = Figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas, 1)

    def apply_language(self, lang: str) -> None:
        self.setWindowTitle(tr(lang, "synth.preview_title", "Synthesis Curve Preview"))

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


from ..core.run_service import RunService
from .i18n import tr
from ..intel.templates import insert_template, list_user_templates


def _view_center(ctrl: Any) -> Tuple[float, float]:
    center_xy = (0.0, 0.0)
    try:
        win = getattr(ctrl, "win", None)
        view = getattr(win, "view", None) if win else None
        if view is not None:
            center = view.mapToScene(view.viewport().rect().center())
            center_xy = (float(center.x()), float(center.y()))
    except Exception:
        pass
    return center_xy


class SynthesisTab(QWidget):
    """A minimal end-to-end synthesis tab (v1).

    - Single-case sweep (input angle deg) curve shaping.
    - Output is an angle (deg).
    - Inserts a 4-bar starter template and creates one case + optimization preset.
    """

    def __init__(self, ctrl: Any, run_service: Optional[RunService] = None):
        super().__init__()
        self.ctrl = ctrl
        self._run_service = run_service or RunService(ctrl)
        self._plot_dialog: Optional[_SynthesisPreviewPlotDialog] = None
        # Whether the user has manually edited mapping points.
        # Used to avoid overwriting user input when we refresh from project cases.
        self._mapping_dirty: bool = False

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_requirement_group())
        layout.addWidget(self._build_mapping_group())
        layout.addWidget(self._build_optimization_group())

        self.btn_generate = QPushButton("")
        self.btn_to_opt = QPushButton("")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_generate)
        btn_row.addWidget(self.btn_to_opt)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_to_opt.clicked.connect(self._jump_to_optimization)

        self.combo_template.currentIndexChanged.connect(self._refresh_template_parameter_mode)
        self.apply_language()
        self._refresh_template_parameter_mode()
        self._load_mapping_from_project_or_default()

    def _project_dir(self) -> str:
        return self._run_service.project_dir()

    def _manager(self):
        return self._run_service.manager()

    # ---- UI ----
    def _build_requirement_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_req = group
        v = QVBoxLayout(group)

        row = QHBoxLayout()
        self.lbl_template = QLabel("")
        self.combo_template = QComboBox()
        # Populate from registry so adding new synthesis-supported templates
        # does not require modifying UI code.
        for tid in list_supported_template_ids():
            self.combo_template.addItem(template_display_label(tid, getattr(self, '_lang', 'en')) or tid, tid)
        # Allow user to confirm / switch topology, even if currently only one template exists.
        self.combo_template.setEnabled(True)
        row.addWidget(self.lbl_template)
        row.addWidget(self.combo_template)

        self.lbl_axis = QLabel("")
        self.ed_axis = QLineEdit("400")
        self.ed_axis.setMaximumWidth(110)
        row.addSpacing(16)
        row.addWidget(self.lbl_axis)
        row.addWidget(self.ed_axis)
        row.addStretch(1)
        v.addLayout(row)

        return group

    # ---- Public helpers (used by IntelligentDesignDialog handoff) ----
    def select_template_id(self, template_id: str) -> bool:
        """Select a template in the combo box.

        Returns True if the template was found/selected.
        """
        tid = str(template_id or '').strip()
        if not tid:
            return False
        try:
            i = self.combo_template.findData(tid)
            if i < 0:
                # Fall back to text match
                i = self.combo_template.findText(tid)
            if i < 0:
                return False
            self.combo_template.setCurrentIndex(i)
            return True
        except Exception:
            return False

    def _build_mapping_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_map = group
        v = QVBoxLayout(group)

        self.table_map = QTableWidget(0, 2)
        self.table_map.verticalHeader().setVisible(False)
        self.table_map.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table_map)

        btn_row = QHBoxLayout()
        self.btn_open_plot = QPushButton("")
        self.btn_add_row = QPushButton("")
        self.btn_del_row = QPushButton("")
        btn_row.addWidget(self.btn_add_row)
        btn_row.addWidget(self.btn_del_row)
        btn_row.addWidget(self.btn_open_plot)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.btn_add_row.clicked.connect(self._add_mapping_row)
        self.btn_del_row.clicked.connect(self._del_mapping_row)
        self.btn_open_plot.clicked.connect(self._open_preview_plot)
        self.table_map.itemChanged.connect(self._refresh_plot)
        self.table_map.itemChanged.connect(self._mark_mapping_dirty)
        return group

    def _mark_mapping_dirty(self, *_a) -> None:
        # itemChanged also fires during programmatic changes; those callers should
        # block signals (see _set_mapping_points).
        self._mapping_dirty = True

    def _build_optimization_group(self) -> QWidget:
        group = QGroupBox("")
        self.group_opt = group
        v = QVBoxLayout(group)

        row = QHBoxLayout()
        self.lbl_tol = QLabel("")
        self.ed_tol = QLineEdit("2.0")
        self.ed_tol.setMaximumWidth(80)
        row.addWidget(self.lbl_tol)
        row.addWidget(self.ed_tol)

        self.lbl_lower = QLabel("")
        self.ed_lower = QLineEdit("0.7")
        self.ed_lower.setMaximumWidth(80)
        row.addSpacing(12)
        row.addWidget(self.lbl_lower)
        row.addWidget(self.ed_lower)

        self.lbl_upper = QLabel("")
        self.ed_upper = QLineEdit("1.3")
        self.ed_upper.setMaximumWidth(80)
        row.addSpacing(12)
        row.addWidget(self.lbl_upper)
        row.addWidget(self.ed_upper)

        self.lbl_evals = QLabel("")
        self.ed_evals = QLineEdit("400")
        self.ed_evals.setMaximumWidth(90)
        row.addSpacing(12)
        row.addWidget(self.lbl_evals)
        row.addWidget(self.ed_evals)

        self.lbl_steps = QLabel("")
        self.ed_steps = QLineEdit("61")
        self.ed_steps.setMaximumWidth(90)
        row.addSpacing(12)
        row.addWidget(self.lbl_steps)
        row.addWidget(self.ed_steps)

        row.addStretch(1)
        v.addLayout(row)
        return group


    def _is_user_template_selected(self) -> bool:
        try:
            tid = str(self.combo_template.currentData() or self.combo_template.currentText() or '').strip()
            if not tid:
                return False
            for rec in list_user_templates() or []:
                if str((rec or {}).get('template_id') or '').strip() == tid:
                    return True
        except Exception:
            return False
        return False

    def _refresh_template_parameter_mode(self) -> None:
        is_user = self._is_user_template_selected()
        fields = [getattr(self, 'ed_lower', None), getattr(self, 'ed_upper', None), getattr(self, 'ed_evals', None), getattr(self, 'ed_steps', None)]
        for w in fields:
            if w is None:
                continue
            w.setEnabled(not is_user)
            if is_user:
                w.clear()
                w.setPlaceholderText('--')
            else:
                if not w.text().strip():
                    defaults = {id(getattr(self, 'ed_lower', None)):'0.7', id(getattr(self, 'ed_upper', None)):'1.3', id(getattr(self, 'ed_evals', None)):'400', id(getattr(self, 'ed_steps', None)):'61'}
                    dv = defaults.get(id(w))
                    if dv is not None:
                        w.setText(dv)

    def apply_language(self) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        self.group_req.setTitle(tr(lang, "synth.group.requirements"))
        self.group_map.setTitle(tr(lang, "synth.group.mapping"))
        self.group_opt.setTitle(tr(lang, "synth.group.optimization"))
        self.lbl_template.setText(tr(lang, "synth.template"))
        self.lbl_axis.setText(tr(lang, "synth.axis"))
        self.table_map.setHorizontalHeaderLabels([tr(lang, "synth.table.input"), tr(lang, "synth.table.target")])
        self.btn_add_row.setText("新增行" if lang == "zh" else "Add Row")
        self.btn_del_row.setText("删除行" if lang == "zh" else "Delete Row")
        self.btn_open_plot.setText("查看曲线图" if lang == "zh" else "Open Plot")
        if self._plot_dialog is not None:
            self._plot_dialog.apply_language(lang)
        self.lbl_tol.setText(tr(lang, "synth.tolerance"))
        self.lbl_lower.setText(tr(lang, "synth.lower_factor"))
        self.lbl_upper.setText(tr(lang, "synth.upper_factor"))
        self.lbl_evals.setText(tr(lang, "synth.evals"))
        self.lbl_steps.setText(tr(lang, "synth.steps"))
        self.btn_generate.setText(tr(lang, "synth.generate"))
        self.btn_to_opt.setText(tr(lang, "synth.goto_opt"))

        # Keep topology dropdown labels consistent with the Template Library.
        try:
            for i in range(self.combo_template.count()):
                tid = self.combo_template.itemData(i)
                self.combo_template.setItemText(i, template_display_label(tid, lang) or str(tid))
        except Exception:
            pass

        # Plot labels
        self._refresh_plot()

    # ---- mapping table ----
    def _add_mapping_row(self, inp: str = "", target: str = "") -> None:
        row = self.table_map.rowCount()
        self.table_map.insertRow(row)
        self.table_map.setItem(row, 0, QTableWidgetItem(str(inp)))
        self.table_map.setItem(row, 1, QTableWidgetItem(str(target)))

    def _del_mapping_row(self) -> None:
        row = self.table_map.currentRow()
        if row >= 0:
            self.table_map.removeRow(row)

    def _load_default_mapping(self) -> None:
        # A small, monotonic example mapping.
        self.table_map.setRowCount(0)
        for inp, out in [(0, 0), (30, 20), (60, 45), (90, 70)]:
            self._add_mapping_row(str(inp), str(out))
        self._refresh_plot()


    def _set_mapping_points(self, pts: List[Tuple[float, float]]) -> None:
        """Replace mapping table rows with the provided points."""
        try:
            self.table_map.blockSignals(True)
            self.table_map.setRowCount(0)
            for a, b in pts:
                self._add_mapping_row(str(a), str(b))
        finally:
            try:
                self.table_map.blockSignals(False)
            except Exception:
                pass
        # Programmatic sync should not be considered a user edit.
        self._mapping_dirty = False
        try:
            self._refresh_plot()
        except Exception:
            pass

    def sync_from_project(self, *, force: bool = False) -> None:
        """Refresh mapping points from the active project case.

        Parameters
        ----------
        force:
            If True, overwrite current table even if user edited it.
            This is appropriate when a new template is inserted.
        """
        if (not force) and self._mapping_dirty:
            return
        self._load_mapping_from_project_or_default()

    def _load_mapping_from_project_or_default(self) -> None:
        """Load mapping points from the latest single-case spec if present; otherwise use defaults.

        This avoids the confusing situation where a template is inserted (e.g. from Intelligent Design)
        but the Synthesis tab still shows the hard-coded demo mapping.
        """
        try:
            manager = self._manager()
            case_id = manager.get_active_case()
            spec = manager.load_case_spec(case_id) if case_id else {}
            pts = self._extract_mapping_from_case_spec(spec)
            if pts:
                self._set_mapping_points(pts)
                return
            # If active case doesn't include curve target, try by name.
            for c in manager.list_cases():
                if str(getattr(c, 'name', '') or '') == 'I/O Curve (single case)':
                    spec = manager.load_case_spec(c.name)
                    pts = self._extract_mapping_from_case_spec(spec)
                    if pts:
                        self._set_mapping_points(pts)
                        return
        except Exception:
            pass
        self._load_default_mapping()

    def _extract_mapping_from_case_spec(self, case_spec: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Extract (input_deg, target_output_deg) points from a case spec if available."""
        if not isinstance(case_spec, dict) or not case_spec:
            return []
        # Preferred: explicit curve_target points
        try:
            ct = case_spec.get('curve_target') or {}
            pts = ct.get('points') if isinstance(ct, dict) else None
            if isinstance(pts, list) and pts:
                out: List[Tuple[float, float]] = []
                for p in pts:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        try:
                            out.append((float(p[0]), float(p[1])))
                        except Exception:
                            continue
                return out
        except Exception:
            pass
        # Fallback: legacy io_map with OUT_i parameters
        try:
            iom = case_spec.get('io_map') or {}
            ins = iom.get('inputs_deg') if isinstance(iom, dict) else None
            outs = iom.get('out_params') if isinstance(iom, dict) else None
            if isinstance(ins, list) and isinstance(outs, list) and ins and outs and len(ins) == len(outs):
                params = getattr(getattr(self.ctrl, 'parameters', None), 'params', {}) or {}
                out: List[Tuple[float, float]] = []
                for a, pname in zip(ins, outs):
                    try:
                        b = float(params.get(str(pname), a))
                        out.append((float(a), b))
                    except Exception:
                        continue
                return out
        except Exception:
            pass
        return []

    def _ensure_plot_dialog(self) -> _SynthesisPreviewPlotDialog:
        if self._plot_dialog is None:
            self._plot_dialog = _SynthesisPreviewPlotDialog(self)
            self._plot_dialog.apply_language(getattr(self.ctrl, "ui_language", "en"))
        return self._plot_dialog

    def _open_preview_plot(self) -> None:
        self._refresh_plot()
        self._ensure_plot_dialog().show_and_raise()

    def _refresh_plot(self) -> None:
        pts = sorted(self._read_mapping_points(), key=lambda p: p[0])
        dlg = self._ensure_plot_dialog()
        dlg.ax.clear()
        lang = getattr(self.ctrl, "ui_language", "en")
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            dlg.ax.plot(xs, ys, marker="o")
            dlg.ax.set_xlabel(tr(lang, "synth.plot.x"))
            dlg.ax.set_ylabel(tr(lang, "synth.plot.y"))
        else:
            dlg.ax.text(0.5, 0.5, tr(lang, "synth.plot.empty"), ha="center", va="center")
            dlg.ax.set_xticks([])
            dlg.ax.set_yticks([])
        dlg.ax.grid(True, which="both")
        try:
            dlg.fig.tight_layout()
        except Exception:
            pass
        dlg.canvas.draw_idle()

    def reset_for_new_project(self) -> None:
        """Clear user-entered mapping/target curve points for a fresh project."""
        try:
            self.table_map.setRowCount(0)
        except Exception:
            pass
        try:
            self._refresh_plot()
        except Exception:
            pass

    def _read_mapping_points(self) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        for r in range(self.table_map.rowCount()):
            it_in = self.table_map.item(r, 0)
            it_out = self.table_map.item(r, 1)
            a = (it_in.text() if it_in else "").strip()
            b = (it_out.text() if it_out else "").strip()
            if not a or not b:
                continue
            try:
                pts.append((float(a), float(b)))
            except Exception:
                continue
        return pts

    # ---- actions ----
    def _jump_to_optimization(self) -> None:
        """Switch to the Optimization tab.

        If the user has edited mapping points but hasn't clicked "Generate & Configure",
        we generate/update the single-case + preset silently to avoid optimizing a stale
        short-sweep case.
        """
        try:
            # Best-effort: ensure preset/case are up-to-date before switching.
            # IMPORTANT: Intelligent-Design insertion may have created an auto IO-case
            # with a short sweep (e.g. 0~30 deg). Users can then edit the mapping table
            # to 0~90 deg without clicking "Generate & Configure".
            # If we don't detect this mismatch, optimization will run a stale short case
            # and can misleadingly report small objectives.
            mapping = self._read_mapping_points()
            if mapping:
                try:
                    manager = self._manager()
                    active_id = manager.get_active_case_id() if manager else None
                    spec = manager.load_case_spec(active_id) if (manager and active_id) else None
                    ct = (spec or {}).get("curve_target") if isinstance(spec, dict) else None
                    ok = isinstance(ct, dict) and ct.get("kind") == "io_angle" and isinstance(ct.get("points"), list) and ct.get("points")

                    def _norm_pts(pts):
                        out=[]
                        for p in pts or []:
                            if isinstance(p,(list,tuple)) and len(p)>=2:
                                try:
                                    out.append((float(p[0]), float(p[1])))
                                except Exception:
                                    pass
                        return sorted(out, key=lambda t: t[0])

                    mapping_norm = _norm_pts(mapping)
                    ct_norm = _norm_pts(ct.get("points") if isinstance(ct, dict) else None)

                    mismatch = False
                    if not ok:
                        mismatch = True
                    else:
                        if len(mapping_norm) != len(ct_norm):
                            mismatch = True
                        else:
                            for (a1,b1),(a2,b2) in zip(mapping_norm, ct_norm):
                                if abs(a1-a2) > 1e-9 or abs(b1-b2) > 1e-9:
                                    mismatch = True
                                    break

                    # Also ensure sweep covers the mapping domain.
                    try:
                        sw = (spec or {}).get('sweep') if isinstance(spec, dict) else None
                        if isinstance(sw, dict) and mapping_norm:
                            umin = min(p[0] for p in mapping_norm)
                            umax = max(p[0] for p in mapping_norm)
                            if float(sw.get('start_deg', umin) or umin) > umin + 1e-9:
                                mismatch = True
                            if float(sw.get('end_deg', umax) or umax) < umax - 1e-9:
                                mismatch = True
                    except Exception:
                        pass

                    if mismatch:
                        self._on_generate(quiet=True, jump=False)
                except Exception:
                    pass

            win = getattr(self.ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            if sim_panel is not None and hasattr(sim_panel, "tabs"):
                opt_tab = getattr(sim_panel, "optimization_tab", None)
                if opt_tab is not None:
                    sim_panel.tabs.setCurrentWidget(opt_tab)
        except Exception:
            pass

    def _on_generate(self, quiet: bool = False, jump: bool = True) -> None:
        lang = getattr(self.ctrl, "ui_language", "en")
        mapping = self._read_mapping_points()
        if not mapping:
            if not quiet:
                QMessageBox.information(self, tr(lang, "synth.title"), tr(lang, "synth.msg.no_points"))
            return

        # Use the currently selected topology / template.
        template_id = "4bar_door"
        try:
            tid = self.combo_template.currentData()
            if tid:
                template_id = str(tid)
        except Exception:
            pass

        # When there is no mechanism yet, we may need to insert a starter geometry.
        # For user "position synthesis" templates we map to a base starter topology.
        try:
            from ..intel.synthesis_registry import resolve_insert_template_id
            insert_id = resolve_insert_template_id(template_id) or template_id
        except Exception:
            insert_id = template_id

        # Parsing numeric settings
        def _f(text: str, default: float) -> float:
            try:
                return float(text or "")
            except Exception:
                return default

        def _i(text: str, default: int) -> int:
            try:
                return int(float(text or ""))
            except Exception:
                return default

        tol = _f(self.ed_tol.text(), 2.0)
        lower_factor = _f(self.ed_lower.text(), 0.7)
        upper_factor = _f(self.ed_upper.text(), 1.3)
        evals = max(10, _i(self.ed_evals.text(), 400))
        steps = max(5, _i(self.ed_steps.text(), 61))

        axis = _f(self.ed_axis.text(), 400.0)
        axis = max(1e-6, axis)
        scale = axis / 400.0

        # 1) Ensure we have a starter mechanism.
        # Keep this path deterministic and simple:
        # - If driver/output is not configured, insert a starter template.
        # - Do not try to reuse cached insert metadata or guess whether geometry exists.
        info: Dict[str, Any] = {}
        drv_spec = dict(getattr(self.ctrl, 'driver', {}) or {})
        out_spec = dict(getattr(self.ctrl, 'output', {}) or {})

        def _io_enabled(spec: Dict[str, Any]) -> bool:
            # Some older snapshots may omit 'enabled'. Treat pivot/tip as enabled.
            if spec.get('enabled') is False:
                return False
            if spec.get('enabled') is True:
                return True
            return (spec.get('pivot') is not None) and (spec.get('tip') is not None)

        have_io = _io_enabled(drv_spec) and _io_enabled(out_spec)

        if not have_io:
            info = insert_template(
                self.ctrl,
                insert_id,
                center_xy=_view_center(self.ctrl),
                scale=scale,
                open_angle_deg=None,
                auto_setup_io_cases=False,
                return_info=True,
            ) or {}

            if info:
                # For user templates, the inserted snapshot already contains driver/output.
                # Do NOT try to re-configure based on point ids (we don't have A/B/C/D info).
                if str(info.get('kind') or '') == 'user_override':
                    drv_spec = dict(getattr(self.ctrl, 'driver', {}) or {})
                    out_spec = dict(getattr(self.ctrl, 'output', {}) or {})
                    have_io = _io_enabled(drv_spec) and _io_enabled(out_spec)
                else:
                    drv_spec, out_spec = self._setup_driver_output_from_template(insert_id, info)
                    have_io = (
                        drv_spec is not None and out_spec is not None and
                        bool(drv_spec.get('enabled')) and bool(out_spec.get('enabled'))
                    )

        if not have_io:
            QMessageBox.warning(
                self,
                tr(lang, 'synth.title'),
                tr(lang, 'synth.msg.unsupported_template', 'Unable to auto-configure driver/output for template: {t}').format(t=template_id),
            )
            return

        # 3) Create params + ONE sweep case.
        manager = self._manager()
        for idx, (inp, target) in enumerate(sorted(mapping, key=lambda p: p[0]), start=1):
            try:
                self.ctrl.parameters.set_param(f"IN_{idx}", float(inp))
                self.ctrl.parameters.set_param(f"OUT_{idx}", float(target))
            except Exception:
                pass

        solver_name = "scipy"
        try:
            win = getattr(self.ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            if sim_panel is not None and hasattr(sim_panel, "get_solver_name"):
                solver_name = str(sim_panel.get_solver_name() or "scipy")
        except Exception:
            solver_name = "scipy"

        pts_sorted = sorted(mapping, key=lambda p: p[0])
        u_min = float(min(p[0] for p in pts_sorted))
        u_max = float(max(p[0] for p in pts_sorted))
        case_spec: Dict[str, Any] = {
            "schema_version": "1.0",
            "analysis_mode": "quasi_static",
            "name": "I/O Curve (single case)",
            "driver": dict(drv_spec),
            "drivers": [dict(drv_spec)],
            "output": dict(out_spec),
            "outputs": [dict(out_spec)],
            "solver": {
                "name": solver_name,
                "max_nfev": 250,
                "pbd_iters": 120,
                "hard_err_tol": 1e-3,
                "treat_point_spline_as_soft": False,
            },
            # The I/O curve points are specified as relative angles (deg) by default.
            # Use relative mode so that input=0 means the current pose, and the
            # recorded input/output match the user's curve domain.
            "angle_mode": "relative",
            "sweep": {"start_deg": u_min, "end_deg": u_max, "step_count": int(steps), "adaptive": False},
            "curve_target": {
                "kind": "io_angle",
                "input_key": "input_deg",
                "output_key": "output_deg",
                "points": [[float(a), float(b)] for a, b in pts_sorted],
            },
            "loads": list(getattr(self.ctrl, "loads", []) or []),
            "friction_joints": list(getattr(self.ctrl, "friction_joints", []) or []),
            "measurements": {
                "measures": list(getattr(self.ctrl, "measures", []) or []),
                "load_measures": list(getattr(self.ctrl, "load_measures", []) or []),
            },
        }
        # 3.5) Quick feasibility scan (prevents the default demo from looking 'broken')
        try:
            from ..core.headless_sim import simulate_case, build_signals
            from ..core.optimization import add_curve_target_signals
            snap0 = self.ctrl.snapshot_model()
            frames0, _sum0, _st0 = simulate_case(snap0, case_spec)
            sig0 = build_signals(frames0, snap0)
            add_curve_target_signals(sig0, case_spec)
            vr = float(sig0.get("valid_ratio", 1.0) or 0.0)
            ts = float(sig0.get("target_span", 0.0) or 0.0)
            os_ = float(sig0.get("output_span", 0.0) or 0.0)
            span_ratio = os_ / (ts + 1e-9) if ts > 0 else 1.0
            # If the initial geometry is too far from the target, widen bounds so that 400 evals can
            # actually find a matching family of linkages.
            if vr < 0.95 or span_ratio < 0.7:
                lower_factor = min(lower_factor, 0.4)
                upper_factor = max(upper_factor, 2.0)
                self.ed_lower.setText(f"{lower_factor:.3g}")
                self.ed_upper.setText(f"{upper_factor:.3g}")
        except Exception:
            pass

        info_case = manager.get_or_create_case(case_spec)
        if info_case is None:
            raise RuntimeError("Failed to create synthesis case")
        created_case_ids = [str(info_case.name)]
        manager.set_active_case(str(info_case.name))

        # 4) Optimization preset (single case)
        preset = self._build_opt_preset(created_case_ids, tol, lower_factor, upper_factor, evals)
        self._apply_preset_to_ui(preset)

        if not quiet:
            QMessageBox.information(self, tr(lang, "synth.title"), tr(lang, "synth.msg.done").format(n=len(created_case_ids)))
        if jump:
            self._jump_to_optimization()

    def auto_generate_or_update_single_case_from_template(
        self,
        template_id: str,
        info: Optional[Dict[str, Any]] = None,
        req: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Insert-template follow-up: configure driver/output and create/update one default case.

        This is intentionally lean and non-interactive so the intelligent-design path can
        hand off to a single deterministic case that later workflows (run/plot/opt) can reuse.
        """
        info = dict(info or {})
        tid = str(template_id or '').strip()
        if not tid:
            return {'ok': False, 'message': '模板ID为空'}

        # 1) Driver / output / measures setup (template-specific)
        drv_spec, out_spec = self._setup_driver_output_from_template(tid, info)
        if drv_spec is None or out_spec is None:
            # lightweight fallback for common aliases
            if tid.startswith('4bar'):
                drv_spec, out_spec = self._setup_driver_output_from_template('4bar_door', info)
            elif tid.startswith('6bar') or tid.startswith('sixbar'):
                # use the selected 6-bar id; do not fall back to 4-bar.
                drv_spec, out_spec = self._setup_driver_output_from_template(tid, info)
        if drv_spec is None or out_spec is None:
            return {'ok': False, 'message': f'未能自动配置驱动/输出（{tid}）'}

        # 2) Build a single default sweep case (relative angle, one case only)
        solver_name = 'scipy'
        try:
            win = getattr(self.ctrl, 'win', None)
            sim_panel = getattr(win, 'sim_panel', None) if win else None
            if sim_panel is not None and hasattr(sim_panel, 'get_solver_name'):
                solver_name = str(sim_panel.get_solver_name() or 'scipy')
        except Exception:
            solver_name = 'scipy'

        open_angle = 90.0
        try:
            if isinstance(req, dict):
                open_angle = float(req.get('open_angle_deg', open_angle) or open_angle)
        except Exception:
            pass

        # Default target mapping for the synthesis tab: monotonic 0→open_angle (users can edit later).
        try:
            oa = float(open_angle)
        except Exception:
            oa = 90.0
        oa = max(0.0, min(180.0, oa))
        inputs = [0.0, oa / 3.0, 2.0 * oa / 3.0, oa]
        params = getattr(getattr(self.ctrl, 'parameters', None), 'params', {}) or {}
        targets = []
        for idx, inp in enumerate(inputs, start=1):
            pname = f'OUT_{idx}'
            val = params.get(pname, inp)
            try:
                targets.append(float(val))
            except Exception:
                targets.append(float(inp))
        mapping_points = [(float(a), float(b)) for a, b in zip(inputs, targets)]
        # Ensure parameters exist so Optimization/Expressions can reference them if desired.
        try:
            for idx, (a, b) in enumerate(mapping_points, start=1):
                self.ctrl.parameters.set_param(f'IN_{idx}', float(a))
                self.ctrl.parameters.set_param(f'OUT_{idx}', float(b))
        except Exception:
            pass
        # Update the mapping table UI so users see the generated keypoints immediately.
        try:
            self._set_mapping_points(mapping_points)
        except Exception:
            pass

        case_name = 'I/O Curve (single case)'
        case_spec: Dict[str, Any] = {
            'schema_version': '1.0',
            'analysis_mode': 'quasi_static',
            'name': case_name,
            'driver': dict(drv_spec),
            'drivers': [dict(drv_spec)],
            'output': dict(out_spec),
            'outputs': [dict(out_spec)],
            'solver': {
                'name': solver_name,
                'max_nfev': 250,
                'pbd_iters': 120,
                'hard_err_tol': 1e-3,
                'treat_point_spline_as_soft': False,
            },
            'angle_mode': 'relative',
            'sweep': {'start_deg': 0.0, 'end_deg': float(open_angle), 'step_count': 61, 'adaptive': False},
            'curve_target': {
                'kind': 'io_angle',
                'input_key': 'input_deg',
                'output_key': 'output_deg',
                'points': [[float(a), float(b)] for a, b in mapping_points],
            },
            'loads': list(getattr(self.ctrl, 'loads', []) or []),
            'friction_joints': list(getattr(self.ctrl, 'friction_joints', []) or []),
            'measurements': {
                'measures': list(getattr(self.ctrl, 'measures', []) or []),
                'load_measures': list(getattr(self.ctrl, 'load_measures', []) or []),
            },
        }

        manager = self._manager()

        # Replace older auto single-case by name to keep the path deterministic and non-bloated.
        replaced = False
        try:
            for c in manager.list_cases():
                if str(getattr(c, 'name', '') or '') == case_name:
                    try:
                        manager.delete_case_runs(c.name)
                    except Exception:
                        pass
                    try:
                        manager.delete_case(c.name)
                    except Exception:
                        pass
                    replaced = True
                    break
        except Exception:
            pass

        info_case = manager.get_or_create_case(case_spec)
        manager.set_active_case(str(info_case.name))

        # Best effort: ask animation tab/case list UI to refresh so the new single case is visible immediately.
        try:
            win = getattr(self.ctrl, 'win', None)
            sp = getattr(win, 'sim_panel', None) if win else None
            if sp is not None and hasattr(sp, 'animation_tab'):
                at = getattr(sp, 'animation_tab')
                if hasattr(at, 'refresh_cases'):
                    at.refresh_cases()
                elif hasattr(at, '_refresh_cases'):
                    at._refresh_cases()
        except Exception:
            pass

        return {'ok': True, 'updated': replaced, 'case_name': str(info_case.name), 'template_name': case_name}

    def _setup_driver_output_from_template(
        self,
        template_id: str,
        info: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Configure ctrl driver/output based on inserted template info.

        Rules are intentionally lean but cover the common intelligent-design templates:
        - 4bar / 6bar: angle driver + angle output
        - slider_rail: angle driver + translation measure (output placeholder disabled)
        - cam: angle driver + (oscillating cam) angle output, else translation measure for translating follower
        """
        try:
            self.ctrl.clear_driver()
            self.ctrl.clear_output()
            self.ctrl.clear_measures()
        except Exception:
            pass

        template_id = (template_id or "").lower().strip()

        def _ret():
            return dict(getattr(self.ctrl, "driver", {}) or {}), dict(getattr(self.ctrl, "output", {}) or {})

        # 4-bar and 6-bar family: use A-B as input, D-C as output (same convention used by templates).
        if template_id in ("4bar", "4bar_door", "fourbar", "four_bar") or template_id.startswith('6bar') or template_id.startswith('sixbar'):
            A = info.get("A"); B = info.get("B"); C = info.get("C"); D = info.get("D")
            if A is None or B is None or C is None or D is None:
                return None, None
            try:
                self.ctrl.set_driver_angle(int(A), int(B))
                self.ctrl.set_output(int(D), int(C))
                self.ctrl.add_measure_angle(int(A), int(B))
                self.ctrl.add_measure_angle(int(D), int(C))
            except Exception:
                return None, None
            return _ret()

        # Slider / rail family: use crank angle as input; translation is captured as a measurement.
        if ('slider' in template_id) or ('rail' in template_id):
            A = info.get('A') if info.get('A') is not None else info.get('O')
            B = info.get('B')
            plid = info.get('plid') or info.get('pl1')
            if A is None or B is None:
                return None, None
            try:
                self.ctrl.set_driver_angle(int(A), int(B))
                self.ctrl.add_measure_angle(int(A), int(B))
                if plid is not None:
                    self.ctrl.add_measure_translation(int(plid))
                # No angular output for slider translation mapping; keep placeholder disabled so single-case path stays unified.
                self.ctrl.output = {'enabled': False, 'type': 'angle', 'pivot': int(A), 'tip': int(B), 'rad': 0.0}
            except Exception:
                return None, None
            return _ret()

        # Cam templates: always set cam rotation as driver. Output depends on follower type.
        if template_id.startswith('cam'):
            O = info.get('O'); T = info.get('T')
            if O is None or T is None:
                return None, None
            try:
                self.ctrl.set_driver_angle(int(O), int(T))
                self.ctrl.add_measure_angle(int(O), int(T))
                if info.get('F') is not None and info.get('P') is not None:
                    # Oscillating follower: output rocker angle F->P
                    self.ctrl.set_output(int(info['F']), int(info['P']))
                    self.ctrl.add_measure_angle(int(info['F']), int(info['P']))
                else:
                    # Translating follower: expose translation via pl1/plid measurement; output remains disabled placeholder.
                    plid = info.get('pl1') or info.get('plid')
                    if plid is not None:
                        self.ctrl.add_measure_translation(int(plid))
                    self.ctrl.output = {'enabled': False, 'type': 'angle', 'pivot': int(O), 'tip': int(T), 'rad': 0.0}
            except Exception:
                return None, None
            return _ret()

        return None, None

    def _build_opt_preset(
        self,
        case_ids: List[str],
        tol: float,
        lower_factor: float,
        upper_factor: float,
        evals: int,
    ) -> Dict[str, Any]:
        variables: List[Dict[str, Any]] = []
        for lid in sorted(getattr(self.ctrl, "links", {}).keys()):
            lk = self.ctrl.links.get(lid) or {}
            try:
                i = int(lk.get("i", -1))
                j = int(lk.get("j", -1))
            except Exception:
                continue
            if lk.get("ref", False):
                continue
            if bool(self.ctrl.points.get(i, {}).get("fixed", False)) and bool(self.ctrl.points.get(j, {}).get("fixed", False)):
                continue
            L = float(lk.get("L", 0.0) or 0.0)
            if L <= 1e-9:
                continue
            lo = lower_factor * L
            hi = upper_factor * L
            if hi < lo:
                lo, hi = hi, lo
            variables.append({"name": f"Link{lid}.L", "lower": lo, "upper": hi, "enabled": True, "case_id": None})

        constraints: List[Dict[str, Any]] = []
        for case_id in case_ids:
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "max(curve_abs_err)",
                    "comparator": "<=",
                    "limit": float(tol),
                }
            )
            # Feasibility / non-deadpoint guards (single-click usable defaults)
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "valid_ratio",
                    "comparator": ">=",
                    "limit": 0.95,
                }
            )
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "output_span / (target_span + 1e-9)",
                    "comparator": ">=",
                    "limit": 0.8,
                }
            )

        return {
            "schema_version": "1.0",
            "kind": "synthesis_io_curve_single_case",
            "variables": variables,
            "objectives": [
                {
                    "enabled": True,
                    "case_id": case_ids[0] if case_ids else None,
                    "direction": "min",
                    "expression": "rms(curve_err) + 1000*mean(hard_err) + 1000*(1-valid_ratio)",
                }
            ],
            "constraints": constraints,
            "run": {"evals": int(evals), "seed": ""},
        }

    def _apply_preset_to_ui(self, preset: Dict[str, Any]) -> None:
        # Persist preset to project (best effort)
        try:
            manager = self._manager()
            os.makedirs(manager.cases_dir, exist_ok=True)
            path = os.path.join(manager.cases_dir, "optimization_preset.json")
            import json

            with open(path, "w", encoding="utf-8") as fh:
                json.dump(preset, fh, indent=2, sort_keys=True)
        except Exception:
            pass

        # Apply to Optimization tab if present
        try:
            win = getattr(self.ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            opt_tab = getattr(sim_panel, "optimization_tab", None) if sim_panel else None
            if opt_tab is not None and hasattr(opt_tab, "apply_preset"):
                opt_tab.apply_preset(preset)
            anim_tab = getattr(sim_panel, "animation_tab", None) if sim_panel else None
            if anim_tab is not None and hasattr(anim_tab, "refresh_cases"):
                anim_tab.refresh_cases()
        except Exception:
            pass