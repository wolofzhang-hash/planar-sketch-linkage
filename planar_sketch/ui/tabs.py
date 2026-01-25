# -*- coding: utf-8 -*-
"""Dock tabs for editing points/links/angles/bodies."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, List

from PyQt6.QtCore import Qt, QSignalBlocker, QItemSelectionModel, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QLabel, QMessageBox, QPushButton, QLineEdit, QComboBox
)

from ..utils.constants import BODY_COLORS, PURPLE, GRAY
from ..core.geometry import parse_id_list

if TYPE_CHECKING:
    from ..core.controller import SketchController


class ParametersTab(QWidget):
    """Global parameter table.

    Parameters can be referenced by expression fields, e.g.
    - Point X: `a*2`
    - Length L: `b + 10`
    - Angle deg: `45 + t`
    """

    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel
        self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Param")
        self.btn_del = QPushButton("Delete")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Name", "Value"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add_param)
        self.btn_del.clicked.connect(self._delete_selected)
        self.table.itemChanged.connect(self._on_item_changed)

    def _add_param(self):
        # Generate a unique default name.
        base = "a"
        existing = set(self.ctrl.parameters.params.keys())
        if base not in existing:
            name = base
        else:
            k = 1
            while True:
                name = f"a{k}"
                if name not in existing:
                    break
                k += 1
        self.ctrl.cmd_set_param(name, 0.0)

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        name_item = self.table.item(row, 0)
        if not name_item:
            return
        name = name_item.text().strip()
        if not name:
            return
        self.ctrl.cmd_delete_param(name)

    def refresh(self, keep_selection=False):
        with QSignalBlocker(self.table):
            items = sorted(self.ctrl.parameters.params.items(), key=lambda kv: kv[0])
            self.table.setRowCount(len(items))
            for r, (name, val) in enumerate(items):
                self.table.setItem(r, 0, QTableWidgetItem(str(name)))
                self.table.setItem(r, 1, QTableWidgetItem(f"{float(val):.6g}"))
        # Keep selection is best-effort
        if keep_selection and self.table.rowCount() > 0 and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        name_item = self.table.item(row, 0)
        val_item = self.table.item(row, 1)
        if not name_item or not val_item:
            return

        old_names = sorted(self.ctrl.parameters.params.keys())
        # Current row name/value
        name = name_item.text().strip()
        val_text = val_item.text().strip()
        if not name:
            return
        try:
            val = float(val_text)
        except Exception:
            QMessageBox.warning(self, "Invalid value", f"Parameter value must be numeric: {val_text!r}")
            self.panel.defer_refresh_all(keep_selection=True)
            return

        # Decide whether this row corresponds to an existing name.
        # Heuristic: if the edited row index is within sorted existing keys and the previous text was that key.
        # If not, just set (creates/overwrites).
        if name in self.ctrl.parameters.params:
            self.ctrl.cmd_set_param(name, val)
        else:
            # If likely rename: find nearest existing row mapping
            if row < len(old_names):
                old = old_names[row]
                if old in self.ctrl.parameters.params:
                    try:
                        self.ctrl.cmd_rename_param(old, name)
                        self.ctrl.cmd_set_param(name, val)
                        return
                    except Exception:
                        pass
            self.ctrl.cmd_set_param(name, val)

class PointsTab(QWidget):
    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel; self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Point")
        self.btn_del = QPushButton("Delete")
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "X", "Y", "Fixed", "Hidden", "Body"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table)
        self.btn_add.clicked.connect(lambda: self.ctrl.cmd_add_point(0.0, 0.0))
        self.btn_del.clicked.connect(self._delete_selected)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

    def _delete_selected(self):
        ids = self.panel.selected_points_from_table(include_hidden=True)
        for pid in sorted(ids, reverse=True):
            self.ctrl.cmd_delete_point(pid)

    def refresh(self, keep_selection=False):
        with QSignalBlocker(self.table):
            pts = sorted(self.ctrl.points.items(), key=lambda kv: kv[0])
            self.table.setRowCount(len(pts))
            for r, (pid, p) in enumerate(pts):
                id_item = QTableWidgetItem(str(pid)); id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, id_item)
                x_expr = (p.get("x_expr") or "").strip()
                y_expr = (p.get("y_expr") or "").strip()
                x_item = QTableWidgetItem(x_expr if x_expr else f"{p['x']:.6g}")
                y_item = QTableWidgetItem(y_expr if y_expr else f"{p['y']:.6g}")
                if p.get("x_expr_error"):
                    x_item.setForeground(PURPLE)
                if p.get("y_expr_error"):
                    y_item.setForeground(PURPLE)
                self.table.setItem(r, 1, x_item)
                self.table.setItem(r, 2, y_item)
                self.table.setItem(r, 3, QTableWidgetItem("1" if p.get("fixed", False) else "0"))
                self.table.setItem(r, 4, QTableWidgetItem("1" if p.get("hidden", False) else "0"))
                bid = self.ctrl.point_body(pid)
                self.table.setItem(r, 5, QTableWidgetItem("" if bid is None else str(bid)))
                self.table.item(r, 5).setFlags(self.table.item(r, 5).flags() & ~Qt.ItemFlag.ItemIsEditable)
        if keep_selection:
            self.panel.select_points_multi(sorted(self.ctrl.selected_point_ids))

    def refresh_fast(self):
        with QSignalBlocker(self.table):
            for r in range(self.table.rowCount()):
                pid_item = self.table.item(r, 0)
                if not pid_item: continue
                pid = int(pid_item.text())
                if pid not in self.ctrl.points: continue
                p = self.ctrl.points[pid]
                # Don't overwrite expression text during dragging/fast updates.
                if not (p.get("x_expr") or "").strip():
                    self.table.item(r, 1).setText(f"{p['x']:.6g}")
                if not (p.get("y_expr") or "").strip():
                    self.table.item(r, 2).setText(f"{p['y']:.6g}")

    def _on_selection_changed(self):
        if self.panel.sync_guard: return
        ids = self.panel.selected_points_from_table(include_hidden=False)
        self.ctrl.commit_drag_if_any()
        self.panel.sync_guard = True
        try:
            for pid in list(self.ctrl.selected_point_ids):
                if pid in self.ctrl.points:
                    self.ctrl.points[pid]["item"].setSelected(False)
            self.ctrl.selected_point_ids = set(ids)
            for pid in ids:
                if pid in self.ctrl.points:
                    self.ctrl.points[pid]["item"].setSelected(True)
            self.ctrl.selected_point_id = ids[-1] if ids else None
            self.ctrl.selected_link_id = None; self.ctrl.selected_angle_id = None; self.ctrl.selected_body_id = None
            self.ctrl._clear_scene_link_selection(); self.ctrl._clear_scene_angle_selection()
            self.ctrl.update_graphics()
            self.panel.clear_links_selection_only(); self.panel.clear_angles_selection_only(); self.panel.clear_bodies_selection_only()
            self.ctrl.update_status()
        finally:
            self.panel.sync_guard = False

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        pid_item = self.table.item(row, 0)
        if not pid_item: return
        pid = int(pid_item.text())
        if pid not in self.ctrl.points: return
        try:
            x_text = (self.table.item(row, 1).text() if self.table.item(row, 1) else "").strip()
            y_text = (self.table.item(row, 2).text() if self.table.item(row, 2) else "").strip()
            fixed = (self.table.item(row, 3).text().strip() not in ("0", "", "false", "False", "no", "No"))
            hidden = (self.table.item(row, 4).text().strip() not in ("0", "", "false", "False", "no", "No"))
        except Exception as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            self.panel.defer_refresh_all(keep_selection=True); return
        def apply():
            self.ctrl.commit_drag_if_any()
            self.ctrl.cmd_set_point_expr(pid, x_text, y_text)
            self.ctrl.cmd_set_point_fixed(pid, fixed)
            self.ctrl.cmd_set_point_hidden(pid, hidden)
            self.panel.defer_refresh_all(keep_selection=True)
        QTimer.singleShot(0, apply)

class LinksTab(QWidget):
    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel; self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Length (from 2 selected points)")
        self.btn_del = QPushButton("Delete")
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "i", "j", "L", "Hidden", "State"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        layout.addWidget(self.table)
        self.btn_add.clicked.connect(self._add_link_from_points)
        self.btn_del.clicked.connect(self._delete_selected)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

    def _add_link_from_points(self):
        ids = self.panel.selected_points_from_table(include_hidden=False)
        if len(ids) < 2:
            QMessageBox.information(self, "Need 2 points", "Select two points then click Add Length.")
            return
        self.ctrl.cmd_add_link(ids[0], ids[1])

    def _delete_selected(self):
        lid = self.panel.selected_link_from_table()
        if lid is None: return
        self.ctrl.cmd_delete_link(lid)

    def refresh(self, keep_selection=False):
        with QSignalBlocker(self.table):
            lks = sorted(self.ctrl.links.items(), key=lambda kv: kv[0])
            self.table.setRowCount(len(lks))
            for r, (lid, l) in enumerate(lks):
                id_item = QTableWidgetItem(str(lid)); id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, id_item)
                i_item = QTableWidgetItem(str(l["i"])); i_item.setFlags(i_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                j_item = QTableWidgetItem(str(l["j"])); j_item.setFlags(j_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 1, i_item); self.table.setItem(r, 2, j_item)
                # L: constraint value (or measured value when in Reference)
                if l.get("ref", False):
                    i, j = int(l.get("i")), int(l.get("j"))
                    if i in self.ctrl.points and j in self.ctrl.points:
                        p1, p2 = self.ctrl.points[i], self.ctrl.points[j]
                        curL = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                    else:
                        curL = float(l.get("L", 0.0))
                    L_item = QTableWidgetItem(f"{curL:.6g}")
                    L_item.setFlags(L_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(r, 3, L_item)
                else:
                    L_expr = (l.get("L_expr") or "").strip()
                    L_item = QTableWidgetItem(L_expr if L_expr else f"{l['L']:.6g}")
                    if l.get("L_expr_error"):
                        L_item.setForeground(PURPLE)
                    self.table.setItem(r, 3, L_item)
                self.table.setItem(r, 4, QTableWidgetItem("1" if l.get("hidden", False) else "0"))
                st = "Reference" if l.get("ref", False) else ("OVER" if l.get("over", False) else "OK")
                st_item = QTableWidgetItem(st); st_item.setFlags(st_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if l.get("ref", False): st_item.setForeground(GRAY)
                elif l.get("over", False): st_item.setForeground(PURPLE)
                self.table.setItem(r, 5, st_item)
        if keep_selection and self.ctrl.selected_link_id is not None:
            self.panel.select_link(self.ctrl.selected_link_id)

    def refresh_fast(self):
        with QSignalBlocker(self.table):
            for r in range(self.table.rowCount()):
                lid_item = self.table.item(r, 0)
                if not lid_item: continue
                lid = int(lid_item.text())
                if lid not in self.ctrl.links: continue
                l = self.ctrl.links[lid]
                self.table.item(r, 5).setText("Reference" if l.get("ref", False) else ("OVER" if l.get("over", False) else "OK"))

    def _on_selection_changed(self):
        if self.panel.sync_guard: return
        lid = self.panel.selected_link_from_table()
        self.ctrl.commit_drag_if_any()
        if lid is None: return
        self.panel.sync_guard = True
        try:
            self.ctrl.select_link_single(lid)
        finally:
            self.panel.sync_guard = False

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        lid_item = self.table.item(row, 0)
        if not lid_item: return
        lid = int(lid_item.text())
        if lid not in self.ctrl.links: return
        try:
            L_text = (self.table.item(row, 3).text() if self.table.item(row, 3) else "").strip()
            hidden = (self.table.item(row, 4).text().strip() not in ("0", "", "false", "False", "no", "No"))
        except Exception as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            self.panel.defer_refresh_all(keep_selection=True); return
        def apply():
            self.ctrl.commit_drag_if_any()
            if self.ctrl.links.get(lid, {}).get("ref", False):
                # Reference rows are read-only for L.
                pass
            else:
                self.ctrl.cmd_set_link_expr(lid, L_text)
            self.ctrl.cmd_set_link_hidden(lid, hidden)
            self.panel.defer_refresh_all(keep_selection=True)
        QTimer.singleShot(0, apply)

class AnglesTab(QWidget):
    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel; self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Angle (from 3 selected points, middle is vertex)")
        self.btn_del = QPushButton("Delete")
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "i", "j(vertex)", "k", "deg", "Hidden", "State"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        layout.addWidget(self.table)
        self.btn_add.clicked.connect(self._add_angle_from_points)
        self.btn_del.clicked.connect(self._delete_selected)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

    def _add_angle_from_points(self):
        ids = self.panel.selected_points_from_table(include_hidden=False)
        if len(ids) < 3:
            QMessageBox.information(self, "Need 3 points", "Select 3 points (2nd is vertex).")
            return
        i, j, k = ids[0], ids[1], ids[2]
        pi, pj, pk = self.ctrl.points[i], self.ctrl.points[j], self.ctrl.points[k]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        deg = math.degrees(angle_between(v1x, v1y, v2x, v2y))
        self.ctrl.cmd_add_angle(i, j, k, deg)

    def _delete_selected(self):
        aid = self.panel.selected_angle_from_table()
        if aid is None: return
        self.ctrl.cmd_delete_angle(aid)

    def refresh(self, keep_selection=False):
        with QSignalBlocker(self.table):
            angs = sorted(self.ctrl.angles.items(), key=lambda kv: kv[0])
            self.table.setRowCount(len(angs))
            for r, (aid, a) in enumerate(angs):
                id_item = QTableWidgetItem(str(aid)); id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, id_item)
                for c, key in enumerate(["i", "j", "k"], start=1):
                    it = QTableWidgetItem(str(a[key])); it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(r, c, it)
                deg_expr = (a.get("deg_expr") or "").strip()
                deg_item = QTableWidgetItem(deg_expr if deg_expr else f"{a['deg']:.6g}")
                if a.get("deg_expr_error"):
                    deg_item.setForeground(PURPLE)
                self.table.setItem(r, 4, deg_item)
                self.table.setItem(r, 5, QTableWidgetItem("1" if a.get("hidden", False) else "0"))
                st = "OVER" if a.get("over", False) else "OK"
                st_item = QTableWidgetItem(st); st_item.setFlags(st_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if a.get("over", False): st_item.setForeground(PURPLE)
                self.table.setItem(r, 6, st_item)
        if keep_selection and self.ctrl.selected_angle_id is not None:
            self.panel.select_angle(self.ctrl.selected_angle_id)

    def refresh_fast(self):
        with QSignalBlocker(self.table):
            for r in range(self.table.rowCount()):
                aid_item = self.table.item(r, 0)
                if not aid_item: continue
                aid = int(aid_item.text())
                if aid not in self.ctrl.angles: continue
                a = self.ctrl.angles[aid]
                # Don't overwrite expression text during fast updates.
                if not (a.get("deg_expr") or "").strip():
                    self.table.item(r, 4).setText(f"{a['deg']:.6g}")
                self.table.item(r, 6).setText("OVER" if a.get("over", False) else "OK")

    def _on_selection_changed(self):
        if self.panel.sync_guard: return
        aid = self.panel.selected_angle_from_table()
        self.ctrl.commit_drag_if_any()
        if aid is None: return
        self.panel.sync_guard = True
        try:
            self.ctrl.select_angle_single(aid)
        finally:
            self.panel.sync_guard = False

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        aid_item = self.table.item(row, 0)
        if not aid_item: return
        aid = int(aid_item.text())
        if aid not in self.ctrl.angles: return
        try:
            deg_text = (self.table.item(row, 4).text() if self.table.item(row, 4) else "").strip()
            hidden = (self.table.item(row, 5).text().strip() not in ("0", "", "false", "False", "no", "No"))
        except Exception as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            self.panel.defer_refresh_all(keep_selection=True); return
        def apply():
            self.ctrl.commit_drag_if_any()
            self.ctrl.cmd_set_angle_expr(aid, deg_text)
            self.ctrl.cmd_set_angle_hidden(aid, hidden)
            self.panel.defer_refresh_all(keep_selection=True)
        QTimer.singleShot(0, apply)



class ConstraintsTab(QWidget):
    """Unified constraint manager (Length/Angle/Coincide)."""
    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel; self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.btn_toggle = QPushButton("Enable/Disable")
        self.btn_delete = QPushButton("Delete")
        btn_row.addWidget(self.btn_toggle)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Key", "Type", "Entities", "Enabled", "State"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_toggle.clicked.connect(self._toggle_selected)

    def _selected_key(self) -> Optional[str]:
        sel = self.table.selectedItems()
        if not sel:
            return None
        it = self.table.item(sel[0].row(), 0)
        return it.text() if it else None

    def _parse_key(self, key: str):
        if not key:
            return None, None
        k = key.strip()
        if len(k) < 2:
            return None, None
        kind = k[0].upper()
        try:
            cid = int(k[1:])
        except Exception:
            return None, None
        return kind, cid

    def refresh(self, keep_selection=False):
        keep_key = self._selected_key() if keep_selection else None
        rows = []
        for row in self.ctrl.constraint_registry.iter_rows():
            rows.append((row.key, row.typ, row.entities, "1" if row.enabled else "0", row.state))

        with QSignalBlocker(self.table):
            self.table.setRowCount(len(rows))
            for r, (key, typ, ent, enabled, state) in enumerate(rows):
                self.table.setItem(r, 0, QTableWidgetItem(key))
                self.table.setItem(r, 1, QTableWidgetItem(typ))
                self.table.setItem(r, 2, QTableWidgetItem(ent))
                self.table.setItem(r, 3, QTableWidgetItem(enabled))
                st_item = QTableWidgetItem(state)
                if state in ("Reference",):
                    st_item.setForeground(GRAY)
                elif state in ("OVER",):
                    st_item.setForeground(PURPLE)
                self.table.setItem(r, 4, st_item)

        if keep_key:
            self.select_key(keep_key)

    def refresh_fast(self):
        self.refresh(keep_selection=True)

    def select_key(self, key: str):
        with QSignalBlocker(self.table):
            self.table.clearSelection()
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 0)
                if it and it.text() == key:
                    self.table.selectRow(r)
                    return

    def _on_selection_changed(self):
        if self.panel.sync_guard:
            return
        key = self._selected_key()
        if not key:
            return
        kind, cid = self._parse_key(key)
        if kind == "L":
            if cid in self.ctrl.links:
                self.ctrl.select_link_single(cid)
        elif kind == "A":
            if cid in self.ctrl.angles:
                self.ctrl.select_angle_single(cid)
        elif kind == "C":
            if cid in self.ctrl.coincides:
                self.ctrl.select_coincide_single(cid)
        elif kind == "P":
            if cid in getattr(self.ctrl, "point_lines", {}):
                self.ctrl.select_point_line_single(cid)

    def _delete_selected(self):
        key = self._selected_key()
        if not key:
            return
        self.ctrl.constraint_registry.delete_by_key(key)

    def _toggle_selected(self):
        key = self._selected_key()
        if not key:
            return
        self.ctrl.constraint_registry.toggle_by_key(key)

class BodiesTab(QWidget):
    def __init__(self, panel: "SketchPanel"):
        super().__init__()
        self.panel = panel; self.ctrl = panel.ctrl
        layout = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.btn_make = QPushButton("Make Body (from selected points)")
        self.btn_del = QPushButton("Delete Body")
        btn_row.addWidget(self.btn_make); btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Point IDs:"))
        self.edit_ids = QLineEdit()
        self.edit_ids.setPlaceholderText("e.g. 0,1,2")
        self.btn_set = QPushButton("Set Members")
        self.btn_add = QPushButton("Add IDs")
        self.btn_rm = QPushButton("Remove IDs")
        row2.addWidget(self.edit_ids, 1)
        row2.addWidget(self.btn_set); row2.addWidget(self.btn_add); row2.addWidget(self.btn_rm)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_add_sel = QPushButton("Add selected points")
        self.btn_rm_sel = QPushButton("Remove selected points")
        row3.addWidget(self.btn_add_sel); row3.addWidget(self.btn_rm_sel)
        row3.addStretch(1)
        layout.addLayout(row3)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Points", "Color", "Hidden", "RigidEdges"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        layout.addWidget(self.table)

        self.btn_make.clicked.connect(self._make_body)
        self.btn_del.clicked.connect(self._del_body)
        self.btn_set.clicked.connect(self._set_members_from_text)
        self.btn_add.clicked.connect(self._add_members_from_text)
        self.btn_rm.clicked.connect(self._rm_members_from_text)
        self.btn_add_sel.clicked.connect(self._add_sel_pts)
        self.btn_rm_sel.clicked.connect(self._rm_sel_pts)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

    def _make_body(self):
        ids = self.panel.selected_points_from_table(include_hidden=False)
        if len(ids) < 2:
            QMessageBox.information(self, "Need >=2 points", "Select at least 2 visible points then Make Body.")
            return
        self.ctrl.cmd_add_body_from_points(ids)

    def _add_sel_pts(self):
        bid = self.panel.selected_body_from_table()
        if bid is None:
            QMessageBox.information(self, "Select body", "Select a body first.")
            return
        ids = self.panel.selected_points_from_table(include_hidden=False)
        if not ids: return
        cur = list(self.ctrl.bodies[bid].get("points", []))
        for pid in ids:
            if pid not in cur:
                cur.append(pid)
        self.ctrl.cmd_body_set_members(bid, cur)

    def _rm_sel_pts(self):
        bid = self.panel.selected_body_from_table()
        if bid is None:
            QMessageBox.information(self, "Select body", "Select a body first.")
            return
        ids = set(self.panel.selected_points_from_table(include_hidden=True))
        if not ids: return
        cur = [pid for pid in self.ctrl.bodies[bid].get("points", []) if pid not in ids]
        self.ctrl.cmd_body_set_members(bid, cur)

    def _set_members_from_text(self):
        bid = self.panel.selected_body_from_table()
        if bid is None:
            QMessageBox.information(self, "Select body", "Select a body first.")
            return
        ids = parse_id_list(self.edit_ids.text())
        if not ids:
            QMessageBox.information(self, "No IDs", "Enter point IDs like 0,1,2.")
            return
        self.ctrl.cmd_body_set_members(bid, ids)

    def _add_members_from_text(self):
        bid = self.panel.selected_body_from_table()
        if bid is None:
            QMessageBox.information(self, "Select body", "Select a body first.")
            return
        ids = parse_id_list(self.edit_ids.text())
        if not ids: return
        cur = list(self.ctrl.bodies[bid].get("points", []))
        for pid in ids:
            if pid not in cur:
                cur.append(pid)
        self.ctrl.cmd_body_set_members(bid, cur)

    def _rm_members_from_text(self):
        bid = self.panel.selected_body_from_table()
        if bid is None:
            QMessageBox.information(self, "Select body", "Select a body first.")
            return
        ids = set(parse_id_list(self.edit_ids.text()))
        if not ids: return
        cur = [pid for pid in self.ctrl.bodies[bid].get("points", []) if pid not in ids]
        self.ctrl.cmd_body_set_members(bid, cur)

    def _del_body(self):
        bid = self.panel.selected_body_from_table()
        if bid is None: return
        self.ctrl.cmd_delete_body(bid)

    def refresh(self, keep_selection=False):
        with QSignalBlocker(self.table):
            bods = sorted(self.ctrl.bodies.items(), key=lambda kv: kv[0])
            self.table.setRowCount(len(bods))
            for r, (bid, b) in enumerate(bods):
                id_item = QTableWidgetItem(str(bid)); id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, id_item)
                self.table.setItem(r, 1, QTableWidgetItem(b.get("name", f"B{bid}")))
                pts = ",".join(str(x) for x in b.get("points", []))
                pts_item = QTableWidgetItem(pts); pts_item.setFlags(pts_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 2, pts_item)

                cb = QComboBox()
                for cname in BODY_COLORS.keys():
                    cb.addItem(cname)
                cur = b.get("color_name", "Blue")
                cb.setCurrentText(cur if cur in BODY_COLORS else "Blue")
                cb.currentTextChanged.connect(lambda val, bid_=bid: self.ctrl.cmd_set_body_color(bid_, val))
                self.table.setCellWidget(r, 3, cb)

                self.table.setItem(r, 4, QTableWidgetItem("1" if b.get("hidden", False) else "0"))
                re_cnt = len(b.get("rigid_edges", []))
                re_item = QTableWidgetItem(str(re_cnt)); re_item.setFlags(re_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 5, re_item)
        if keep_selection and self.ctrl.selected_body_id is not None:
            self.panel.select_body(self.ctrl.selected_body_id)

    def _on_selection_changed(self):
        if self.panel.sync_guard: return
        bid = self.panel.selected_body_from_table()
        if bid is None: return
        self.ctrl.commit_drag_if_any()
        self.panel.sync_guard = True
        try:
            self.ctrl.select_body_single(bid)
        finally:
            self.panel.sync_guard = False

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        bid_item = self.table.item(row, 0)
        if not bid_item: return
        bid = int(bid_item.text())
        if bid not in self.ctrl.bodies: return
        try:
            name = self.table.item(row, 1).text()
            hidden = (self.table.item(row, 4).text().strip() not in ("0", "", "false", "False", "no", "No"))
        except Exception as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            self.panel.defer_refresh_all(keep_selection=True); return
        def apply():
            model_before = self.ctrl.snapshot_model()
            ctrl = self.ctrl
            class EditBodyMeta(Command):
                name = "Edit Body"
                def do(self_):
                    ctrl.bodies[bid]["name"] = name
                    ctrl.bodies[bid]["hidden"] = hidden
                    ctrl.update_graphics()
                    self.panel.defer_refresh_all(keep_selection=True)
                def undo(self_):
                    ctrl.apply_model_snapshot(model_before)
            ctrl.stack.push(EditBodyMeta())
        QTimer.singleShot(0, apply)