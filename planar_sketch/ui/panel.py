# -*- coding: utf-8 -*-
"""Right-side panel containing tabs for model editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, List

from PyQt6.QtCore import QTimer, QSignalBlocker, QItemSelectionModel
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel, QAbstractItemView

from .tabs import ParametersTab, PointsTab, LinksTab, AnglesTab, SplinesTab, BodiesTab, ConstraintsTab
from .i18n import tr

if TYPE_CHECKING:
    from ..core.controller import SketchController


class SketchPanel(QWidget):
    def __init__(self, ctrl: SketchController):
        super().__init__()
        self.ctrl = ctrl
        self.ctrl.panel = self
        self.sync_guard = False
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.points_tab = PointsTab(self)
        self.params_tab = ParametersTab(self)
        self.links_tab = LinksTab(self)
        self.angles_tab = AnglesTab(self)
        self.splines_tab = SplinesTab(self)
        self.bodies_tab = BodiesTab(self)
        self.constraints_tab = ConstraintsTab(self)
        self.tabs.addTab(self.params_tab, "")
        self.tabs.addTab(self.points_tab, "")
        self.tabs.addTab(self.links_tab, "")
        self.tabs.addTab(self.angles_tab, "")
        self.tabs.addTab(self.splines_tab, "")
        self.tabs.addTab(self.constraints_tab, "")
        self.tabs.addTab(self.bodies_tab, "")
        self.apply_language()

    def apply_language(self):
        lang = getattr(self.ctrl, "ui_language", "en")
        self.title.setText(tr(lang, "panel.title"))
        self.tabs.setTabText(0, tr(lang, "tab.parameters"))
        self.tabs.setTabText(1, tr(lang, "tab.points"))
        self.tabs.setTabText(2, tr(lang, "tab.lengths"))
        self.tabs.setTabText(3, tr(lang, "tab.angles"))
        self.tabs.setTabText(4, tr(lang, "tab.splines"))
        self.tabs.setTabText(5, tr(lang, "tab.constraints"))
        self.tabs.setTabText(6, tr(lang, "tab.bodies"))
        self.params_tab.apply_language()
        self.points_tab.apply_language()
        self.links_tab.apply_language()
        self.angles_tab.apply_language()
        self.splines_tab.apply_language()
        self.constraints_tab.apply_language()
        self.bodies_tab.apply_language()

    def defer_refresh_all(self, keep_selection=False):
        QTimer.singleShot(0, lambda: self.refresh_all(keep_selection=keep_selection))

    def refresh_all(self, keep_selection=False):
        self.params_tab.refresh(keep_selection=keep_selection)
        self.points_tab.refresh(keep_selection=keep_selection)
        self.links_tab.refresh(keep_selection=keep_selection)
        self.angles_tab.refresh(keep_selection=keep_selection)
        self.splines_tab.refresh(keep_selection=keep_selection)
        self.constraints_tab.refresh(keep_selection=keep_selection)
        self.bodies_tab.refresh(keep_selection=keep_selection)

    def refresh_fast(self):
        # Parameters rarely change during dragging; no fast-refresh needed.
        self.points_tab.refresh_fast()
        self.links_tab.refresh_fast()
        self.angles_tab.refresh_fast()
        self.splines_tab.refresh_fast()
        self.constraints_tab.refresh_fast()

    def clear_points_selection_only(self):
        self.points_tab.table.clearSelection()
    def clear_links_selection_only(self):
        self.links_tab.table.clearSelection()
    def clear_angles_selection_only(self):
        self.angles_tab.table.clearSelection()
    def clear_constraints_selection_only(self):
        self.constraints_tab.table.clearSelection()
    def clear_splines_selection_only(self):
        self.splines_tab.table.clearSelection()

    def select_constraints_row(self, key: str):
        self.constraints_tab.select_key(key)

    def _scroll_table_selection(self, table):
        sel = table.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        table.setCurrentCell(row, 0)
        item = table.item(row, 0)
        if item is not None:
            table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def focus_point(self, pid: int):
        self.tabs.setCurrentWidget(self.points_tab)
        self.select_points_multi([pid])
        self._scroll_table_selection(self.points_tab.table)

    def focus_link(self, lid: int):
        self.tabs.setCurrentWidget(self.links_tab)
        self.select_link(lid)
        self._scroll_table_selection(self.links_tab.table)

    def focus_angle(self, aid: int):
        self.tabs.setCurrentWidget(self.angles_tab)
        self.select_angle(aid)
        self._scroll_table_selection(self.angles_tab.table)

    def focus_spline(self, sid: int):
        self.tabs.setCurrentWidget(self.splines_tab)
        self.select_spline(sid)
        self._scroll_table_selection(self.splines_tab.table)

    def focus_body(self, bid: int):
        self.tabs.setCurrentWidget(self.bodies_tab)
        self.select_body(bid)
        self._scroll_table_selection(self.bodies_tab.table)

    def focus_constraint_key(self, key: str):
        self.tabs.setCurrentWidget(self.constraints_tab)
        self.select_constraints_row(key)
        self._scroll_table_selection(self.constraints_tab.table)

    def clear_bodies_selection_only(self):
        self.bodies_tab.table.clearSelection()

    def select_spline(self, sid: int):
        t = self.splines_tab.table
        with QSignalBlocker(t):
            t.clearSelection()
            for r in range(t.rowCount()):
                it = t.item(r, 0)
                if it and int(it.text()) == sid:
                    t.selectRow(r); return

    def selected_spline_from_table(self) -> Optional[int]:
        t = self.splines_tab.table
        sel = t.selectedItems()
        if not sel:
            return None
        try:
            return int(t.item(sel[0].row(), 0).text())
        except Exception:
            return None

    def selected_points_from_table(self, include_hidden: bool) -> List[int]:
        t = self.points_tab.table
        rows = sorted(set(i.row() for i in t.selectedItems()))
        ids: List[int] = []
        for r in rows:
            it = t.item(r, 0)
            if not it: continue
            try:
                pid = int(it.text())
                if pid in self.ctrl.points:
                    if include_hidden:
                        ids.append(pid)
                    else:
                        if not self.ctrl.is_point_effectively_hidden(pid):
                            ids.append(pid)
            except Exception:
                pass
        return ids

    def select_points_multi(self, pids: List[int]):
        t = self.points_tab.table
        with QSignalBlocker(t):
            sm = t.selectionModel()
            if sm:
                sm.clearSelection()
                want = set(pids)
                for r in range(t.rowCount()):
                    it = t.item(r, 0)
                    if not it: continue
                    if int(it.text()) in want:
                        idx = t.model().index(r, 0)
                        sm.select(idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    def select_link(self, lid: int):
        t = self.links_tab.table
        with QSignalBlocker(t):
            t.clearSelection()
            for r in range(t.rowCount()):
                it = t.item(r, 0)
                if it and int(it.text()) == lid:
                    t.selectRow(r); return

    def select_angle(self, aid: int):
        t = self.angles_tab.table
        with QSignalBlocker(t):
            t.clearSelection()
            for r in range(t.rowCount()):
                it = t.item(r, 0)
                if it and int(it.text()) == aid:
                    t.selectRow(r); return

    def select_body(self, bid: int):
        t = self.bodies_tab.table
        with QSignalBlocker(t):
            t.clearSelection()
            for r in range(t.rowCount()):
                it = t.item(r, 0)
                if it and int(it.text()) == bid:
                    t.selectRow(r); return

    def selected_link_from_table(self) -> Optional[int]:
        t = self.links_tab.table
        sel = t.selectedItems()
        if not sel: return None
        try: return int(t.item(sel[0].row(), 0).text())
        except Exception: return None

    def selected_angle_from_table(self) -> Optional[int]:
        t = self.angles_tab.table
        sel = t.selectedItems()
        if not sel: return None
        try: return int(t.item(sel[0].row(), 0).text())
        except Exception: return None

    def selected_body_from_table(self) -> Optional[int]:
        t = self.bodies_tab.table
        sel = t.selectedItems()
        if not sel: return None
        try: return int(t.item(sel[0].row(), 0).text())
        except Exception: return None
