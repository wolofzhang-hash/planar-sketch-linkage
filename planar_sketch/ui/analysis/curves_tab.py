# -*- coding: utf-8 -*-
"""Curves tab extracted from analysis_tabs.py (Phase-2 true migration)."""

from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QLineEdit, QMenu, QDialog, QInputDialog, QFileDialog,
)

from ..plot_window import PlotWindow
from ..i18n import tr, get_ui_language


def _lang(owner) -> str:
    ctrl = getattr(owner, "ctrl", owner)
    return get_ui_language(ctrl, fallback="zh")


def _tr(owner, key: str, default: Optional[str] = None, **kwargs) -> str:
    return tr(_lang(owner), key, default, **kwargs)


class _CurveEditDialog(QDialog):
    def __init__(self, parent, title: str, curve: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 420)
        self._curve = dict(curve or {})
        lay = QVBoxLayout(self)

        form1 = QHBoxLayout()
        self.ed_name = QLineEdit(str(self._curve.get("name") or ""))
        self.ed_x_name = QLineEdit(str(self._curve.get("x_name") or "input_deg"))
        self.ed_y_name = QLineEdit(str(self._curve.get("y_name") or "output_deg"))
        form1.addWidget(QLabel("Name"))
        form1.addWidget(self.ed_name, 2)
        form1.addWidget(QLabel("X"))
        form1.addWidget(self.ed_x_name, 1)
        form1.addWidget(QLabel("Y"))
        form1.addWidget(self.ed_y_name, 1)
        lay.addLayout(form1)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["X", "Y"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self.btn_add_row = QPushButton("+")
        self.btn_del_row = QPushButton("-")
        btns.addWidget(self.btn_add_row)
        btns.addWidget(self.btn_del_row)
        btns.addStretch(1)
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        lay.addLayout(btns)

        xs = list(self._curve.get('x') or [])
        ys = list(self._curve.get('y') or [])
        n = max(len(xs), len(ys), 2)
        for i in range(n):
            self._insert_row(xs[i] if i < len(xs) else '', ys[i] if i < len(ys) else '')

        self.btn_add_row.clicked.connect(lambda: self._insert_row('', ''))
        self.btn_del_row.clicked.connect(self._remove_row)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _insert_row(self, x, y):
        r = self.table.rowCount(); self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(str(x)))
        self.table.setItem(r, 1, QTableWidgetItem(str(y)))

    def _remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def curve_data(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        name = self.ed_name.text().strip()
        if not name:
            return None, "Curve name is required"
        x_name = self.ed_x_name.text().strip() or 'x'
        y_name = self.ed_y_name.text().strip() or 'y'
        xs=[]; ys=[]
        for r in range(self.table.rowCount()):
            xi = self.table.item(r,0); yi = self.table.item(r,1)
            xt = (xi.text() if xi else '').strip(); yt = (yi.text() if yi else '').strip()
            if not xt and not yt:
                continue
            try:
                xv = float(xt); yv = float(yt)
            except Exception:
                return None, f"Invalid numeric value at row {r+1}"
            xs.append(xv); ys.append(yv)
        if len(xs) < 2:
            return None, "At least 2 points are required"
        pairs = sorted(zip(xs, ys), key=lambda t: t[0])
        xs = [float(a) for a,_ in pairs]
        ys = [float(b) for _,b in pairs]
        return {
            'name': name, 'x': xs, 'y': ys, 'x_name': x_name, 'y_name': y_name,
            'x_unit': '', 'y_unit': '', 'source_type': 'user',
        }, None

class CurvesTab(QWidget):
    """Named curve (measure) registry view for optimization/builder."""

    def __init__(self, ctrl: Any):
        super().__init__()
        self.ctrl = ctrl
        self._rows: List[Dict[str, Any]] = []
        layout = QVBoxLayout(self)
        self.lbl_intro = QLabel('')
        self.lbl_intro.setWordWrap(True)
        layout.addWidget(self.lbl_intro)

        self.table_curves = QTableWidget(0, 5)
        self.table_curves.verticalHeader().setVisible(False)
        self.table_curves.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_curves.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_curves.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_curves.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_curves)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton('')
        self.btn_add_curve = QPushButton('')
        self.btn_edit_curve = QPushButton('')
        self.btn_show_curve = QPushButton('')
        self.btn_import_csv = QPushButton('')
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_add_curve)
        btn_row.addWidget(self.btn_edit_curve)
        btn_row.addWidget(self.btn_show_curve)
        btn_row.addWidget(self.btn_import_csv)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.lbl_detail = QLabel('')
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.lbl_detail)
        layout.addStretch(1)

        self.table_curves.itemSelectionChanged.connect(self._update_detail_panel)
        self.table_curves.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_curves.customContextMenuRequested.connect(self._open_curve_context_menu)
        self.btn_refresh.clicked.connect(self.refresh_curves)
        self.btn_add_curve.clicked.connect(self.add_curve)
        self.btn_edit_curve.clicked.connect(self.edit_selected_curve)
        self.btn_show_curve.clicked.connect(self.show_selected_curve)
        self.btn_import_csv.clicked.connect(self.import_curve_csv)
        self._curve_plot_windows = []

        self.apply_language()
        self.refresh_curves()

    def preferred_panel_width(self) -> int:
        return 620

    def apply_language(self) -> None:
        lang = _lang(self)
        self.lbl_intro.setText(tr(lang, 'curves.intro', 'Named curves used by optimization expressions (measures / targets / simulation outputs).'))
        self.table_curves.setHorizontalHeaderLabels([
            tr(lang, 'curves.col.name', 'Name'),
            tr(lang, 'curves.col.source', 'Source'),
            tr(lang, 'curves.col.axes', 'Axes'),
            tr(lang, 'curves.col.points', 'Points'),
            tr(lang, 'curves.col.status', 'Status'),
        ])
        self.btn_refresh.setText(tr(lang, 'curves.refresh', 'Refresh'))
        self.btn_add_curve.setText(tr(lang, 'curves.add', 'Add Curve'))
        self.btn_edit_curve.setText(tr(lang, 'curves.edit', 'Edit Curve'))
        self.btn_show_curve.setText(tr(lang, 'curves.show', 'Show Curve'))
        self.btn_import_csv.setText(tr(lang, 'curves.import_csv', 'Import CSV'))
        if not self._rows:
            self.lbl_detail.setText(tr(lang, 'curves.detail.empty', 'Select a curve to view details.'))

    def list_curve_names(self) -> List[str]:
        self.refresh_curves(silent=True)
        return [str(r.get('name')) for r in self._rows if str(r.get('name') or '').strip()]

    def copy_selected_curve_name(self) -> None:
        row = self.table_curves.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        name = str(self._rows[row].get('name') or '')
        if not name:
            return
        app = QCoreApplication.instance()
        if app is not None and app.clipboard() is not None:
            app.clipboard().setText(name)

    def refresh_curves(self, silent: bool = False) -> None:
        rows = self._build_curve_rows()
        self._rows = rows
        self.table_curves.setRowCount(0)
        for r in rows:
            row = self.table_curves.rowCount()
            self.table_curves.insertRow(row)
            for c, key in enumerate(('name','source','axes','points_text','status')):
                self.table_curves.setItem(row, c, QTableWidgetItem(str(r.get(key, ''))))
        if rows and self.table_curves.currentRow() < 0:
            self.table_curves.selectRow(0)
        if not rows and not silent:
            self._update_detail_panel()
        else:
            self._update_detail_panel()

    def _user_curve_store(self) -> Dict[str, Dict[str, Any]]:
        store = getattr(self.ctrl, '_user_measure_curves', None)
        if not isinstance(store, dict):
            store = {}
            setattr(self.ctrl, '_user_measure_curves', store)
        return store

    def _selected_row_dict(self) -> Optional[Dict[str, Any]]:
        row = self.table_curves.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def add_curve(self) -> None:
        dlg = _CurveEditDialog(self, _tr(self, 'curves.add', default='Add Curve'))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        curve, err = dlg.curve_data()
        if err:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), err); return
        store = self._user_curve_store()
        name = str(curve['name'])
        if name in store or name in {'io_target','io_actual'}:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.name_exists', default='Curve name already exists.'))
            return
        store[name] = curve
        self.refresh_curves()
        self._select_curve_name(name)

    def edit_selected_curve(self) -> None:
        r = self._selected_row_dict()
        if not r:
            return
        if not bool(r.get('_user_editable')):
            QMessageBox.information(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.readonly', default='This curve is system-provided and read-only.'))
            return
        store = self._user_curve_store()
        name0 = str(r.get('name') or '')
        curve0 = dict(store.get(name0) or {})
        dlg = _CurveEditDialog(self, _tr(self, 'curves.edit', default='Edit Curve'), curve0)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        curve, err = dlg.curve_data()
        if err:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), err); return
        name1 = str(curve['name'])
        if name1 != name0 and (name1 in store or name1 in {'io_target','io_actual'}):
            QMessageBox.warning(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.name_exists', default='Curve name already exists.'))
            return
        if name1 != name0:
            store.pop(name0, None)
        store[name1] = curve
        self.refresh_curves()
        self._select_curve_name(name1)

    def show_selected_curve(self) -> None:
        r = self._selected_row_dict()
        if not r:
            return
        xs = list(r.get('_x') or [])
        ys = list(r.get('_y') or [])
        if not xs or not ys:
            QMessageBox.information(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.no_data', default='No curve data to display.'))
            return
        xk = str(r.get('_x_name') or 'x')
        yk = str(r.get('name') or (r.get('_y_name') or 'y'))
        recs = [{xk: float(x), yk: float(y)} for x, y in zip(xs, ys)]
        try:
            w = PlotWindow(recs, ctrl=self.ctrl)
            # set X to xk and Y to yk if present
            idx = w.cb_x.findData(xk)
            if idx >= 0: w.cb_x.setCurrentIndex(idx)
            for i in range(w.lst_y.count()):
                it = w.lst_y.item(i)
                k = it.data(Qt.ItemDataRole.UserRole)
                it.setCheckState(Qt.CheckState.Checked if str(k) == yk else Qt.CheckState.Unchecked)
            w.plot()
            w.setWindowTitle(f"{_tr(self, 'curves.show', default='Show Curve')}: {r.get('name','')}")
            w.show()
            self._curve_plot_windows.append(w)
        except Exception as exc:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), str(exc))

    def import_curve_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _tr(self, 'curves.import_csv', default='Import CSV'), '', 'CSV Files (*.csv);;All Files (*)')
        if not path:
            return
        xs=[]; ys=[]
        try:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or len(row) < 2:
                        continue
                    try:
                        x = float(str(row[0]).strip()); y = float(str(row[1]).strip())
                    except Exception:
                        continue
                    xs.append(x); ys.append(y)
        except Exception as exc:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), str(exc)); return
        if len(xs) < 2:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.import_need_2pts', default='CSV must contain at least 2 numeric rows (x,y).'))
            return
        base = os.path.splitext(os.path.basename(path))[0]
        name = base or 'imported_curve'
        store = self._user_curve_store()
        i = 1; cand = name
        while cand in store or cand in {'io_target','io_actual'}:
            i += 1; cand = f"{name}_{i}"
        pairs = sorted(zip(xs, ys), key=lambda t: t[0])
        store[cand] = {'name': cand, 'x': [float(a) for a,_ in pairs], 'y': [float(b) for _,b in pairs], 'x_name': 'input_deg', 'y_name': 'output_deg', 'source_type': 'imported'}
        self.refresh_curves()
        self._select_curve_name(cand)

    def _delete_selected_curve(self) -> None:
        r = self._selected_row_dict()
        if not r or not bool(r.get('_user_editable')):
            return
        name = str(r.get('name') or '')
        if QMessageBox.question(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.confirm_delete', default='Delete curve: {name}?').format(name=name)) != QMessageBox.StandardButton.Yes:
            return
        self._user_curve_store().pop(name, None)
        self.refresh_curves()

    def _rename_selected_curve(self) -> None:
        r = self._selected_row_dict()
        if not r or not bool(r.get('_user_editable')):
            return
        old = str(r.get('name') or '')
        new, ok = QInputDialog.getText(self, _tr(self, 'curves.rename', default='Rename Curve'), _tr(self, 'curves.col.name', default='Name'), text=old)
        if not ok:
            return
        new = str(new).strip()
        if not new or new == old:
            return
        store = self._user_curve_store()
        if new in store or new in {'io_target','io_actual'}:
            QMessageBox.warning(self, _tr(self, 'tab.curves'), _tr(self, 'curves.msg.name_exists', default='Curve name already exists.'))
            return
        data = dict(store.get(old) or {})
        if not data:
            return
        data['name'] = new
        store.pop(old, None); store[new] = data
        self.refresh_curves(); self._select_curve_name(new)

    def _send_selected_curve_name_to_expression(self) -> None:
        r = self._selected_row_dict()
        if not r:
            return
        text = f'"{str(r.get("name") or "")}"'
        ok = False
        try:
            win = getattr(self.ctrl, 'win', None)
            sim = getattr(win, 'sim_panel', None) if win is not None else None
            opt = getattr(sim, 'optimization_tab', None) if sim is not None else None
            inserter = getattr(opt, 'insert_text_into_current_expression_cell', None)
            if callable(inserter):
                ok = bool(inserter(text))
        except Exception:
            ok = False
        if not ok:
            self.copy_selected_curve_name()

    def _select_curve_name(self, name: str) -> None:
        for i, r in enumerate(self._rows):
            if str(r.get('name') or '') == str(name):
                self.table_curves.selectRow(i)
                return

    def _open_curve_context_menu(self, pos) -> None:
        row = self.table_curves.rowAt(pos.y())
        if row >= 0:
            self.table_curves.selectRow(row)
        r = self._selected_row_dict()
        menu = QMenu(self)
        act_add = menu.addAction(_tr(self, 'curves.add', default='Add Curve'))
        act_import = menu.addAction(_tr(self, 'curves.import_csv', default='Import CSV'))
        menu.addSeparator()
        act_show = menu.addAction(_tr(self, 'curves.show', default='Show Curve'))
        act_send = menu.addAction(_tr(self, 'curves.send_to_expr', default='Send to Expression'))
        act_edit = act_rename = act_del = None
        if r and bool(r.get('_user_editable')):
            menu.addSeparator()
            act_edit = menu.addAction(_tr(self, 'curves.edit', default='Edit Curve'))
            act_rename = menu.addAction(_tr(self, 'curves.rename', default='Rename Curve'))
            act_del = menu.addAction(_tr(self, 'menu.delete_row', default='Delete'))
        picked = menu.exec(self.table_curves.viewport().mapToGlobal(pos))
        if picked == act_add: self.add_curve()
        elif picked == act_import: self.import_curve_csv()
        elif picked == act_show: self.show_selected_curve()
        elif picked == act_send: self._send_selected_curve_name_to_expression()
        elif act_edit is not None and picked == act_edit: self.edit_selected_curve()
        elif act_rename is not None and picked == act_rename: self._rename_selected_curve()
        elif act_del is not None and picked == act_del: self._delete_selected_curve()

    def _build_curve_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen = set()

        def _append(name: str, source: str, x, y, x_name='x', y_name='y', status='ok', note=''):
            if not name:
                return
            key = str(name)
            if key in seen:
                return
            seen.add(key)
            xs = list(x or [])
            ys = list(y or [])
            n = min(len(xs), len(ys))
            if n <= 0:
                points_text = '0'
            else:
                points_text = str(n)
            rows.append({
                'name': key, 'source': source, 'axes': f"{x_name} -> {y_name}",
                'points_text': points_text, 'status': status,
                '_x': xs[:n], '_y': ys[:n], '_note': note, '_x_name': x_name, '_y_name': y_name, '_user_editable': False,
            })

        # Live target from intelligent synthesis (no cache)
        get_live = getattr(self.ctrl, 'get_live_io_curve_target', None)
        if callable(get_live):
            try:
                live = get_live()
            except Exception:
                live = None
            if isinstance(live, dict):
                pts = [p for p in (live.get('points') or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
                if pts:
                    xs = [float(p[0]) for p in pts]
                    ys = [float(p[1]) for p in pts]
                else:
                    xs = [float(v) for v in (live.get('x') or live.get('xs') or [])]
                    ys = [float(v) for v in (live.get('y') or live.get('ys') or [])]
                _append(
                    'io_target',
                    tr(_lang(self), 'curves.source.live_target', 'Live Target'),
                    xs, ys,
                    str(live.get('input_key', 'input_deg')),
                    str(live.get('output_key', 'output_deg')),
                    status='live',
                    note=tr(_lang(self), 'curves.note.live', 'Read from intelligent synthesis on demand.'),
                )

        # Best actual from optimization last result (if available)
        try:
            win = getattr(self.ctrl, 'win', None)
            sim_panel = getattr(win, 'sim_panel', None) if win is not None else None
            opt = getattr(sim_panel, 'optimization_tab', None) if sim_panel is not None else None
            payload = getattr(opt, '_last_finished_payload', None) if opt is not None else None
            best_sigs = dict(payload.get('best_signals') or {}) if isinstance(payload, dict) else {}
        except Exception:
            best_sigs = {}
        if best_sigs:
            xs = list(best_sigs.get('input_deg') or [])
            ys = list(best_sigs.get('output_deg') or [])
            if xs and ys:
                _append(
                    'io_actual',
                    tr(_lang(self), 'curves.source.best_actual', 'Best Result'),
                    xs, ys, 'input_deg', 'output_deg',
                    status='snapshot',
                    note=tr(_lang(self), 'curves.note.snapshot', 'Best optimization result snapshot.'),
                )

        # User curves (editable/imported)
        try:
            for uname, c in sorted((self._user_curve_store() or {}).items()):
                if not isinstance(c, dict):
                    continue
                _append(
                    str(c.get('name') or uname),
                    tr(_lang(self), 'curves.source.user', 'User Curve') if str(c.get('source_type') or 'user') != 'imported' else tr(_lang(self), 'curves.source.imported', 'Imported CSV'),
                    list(c.get('x') or []), list(c.get('y') or []),
                    str(c.get('x_name') or 'x'), str(c.get('y_name') or 'y'),
                    status='user',
                    note=tr(_lang(self), 'curves.note.user', 'User-managed curve.'),
                )
                if rows:
                    rows[-1]['_user_editable'] = True
        except Exception:
            pass

        # Do not inject missing built-in placeholders (io_target/io_actual).
        # They should appear only when real data exists; otherwise users think a new project
        # still contains leftover curves. Function builder can still discover names via its own
        # object-data provider and template examples.
        return rows

    def _update_detail_panel(self) -> None:
        row = self.table_curves.currentRow()
        lang = _lang(self)
        if row < 0 or row >= len(self._rows):
            self.lbl_detail.setText(tr(lang, 'curves.detail.empty', 'Select a curve to view details.'))
            return
        r = self._rows[row]
        xs = list(r.get('_x') or [])
        ys = list(r.get('_y') or [])
        lines = [
            f"{tr(lang, 'curves.col.name', 'Name')}: {r.get('name','')}",
            f"{tr(lang, 'curves.col.source', 'Source')}: {r.get('source','')}",
            f"{tr(lang, 'curves.col.axes', 'Axes')}: {r.get('axes','')}",
            f"{tr(lang, 'curves.col.points', 'Points')}: {r.get('points_text','0')}",
            f"{tr(lang, 'curves.col.status', 'Status')}: {r.get('status','')}",
        ]
        if xs and ys:
            try:
                lines.append(f"{tr(lang, 'curves.detail.x_range', 'x range')}: [{min(xs):.6g}, {max(xs):.6g}]")
                lines.append(f"{tr(lang, 'curves.detail.y_range', 'y range')}: [{min(ys):.6g}, {max(ys):.6g}]")
            except Exception:
                pass
        self.lbl_detail.setText('\n'.join(lines))


__all__ = ["CurvesTab"]
