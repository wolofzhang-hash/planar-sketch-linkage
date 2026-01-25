# -*- coding: utf-8 -*-
"""Right-side panel containing tabs for model editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, List

from PyQt6.QtCore import QTimer, QSignalBlocker, QItemSelectionModel
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel

from .tabs import ParametersTab, PointsTab, LinksTab, AnglesTab, BodiesTab, ConstraintsTab

if TYPE_CHECKING:
    from ..core.controller import SketchController


class SketchPanel(QWidget):
    def __init__(self, ctrl: SketchController):
        super().__init__()
        self.ctrl = ctrl
        self.ctrl.panel = self
        self.sync_guard = False
        layout = QVBoxLayout(self)
        title = QLabel("Sketch Parameters")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.points_tab = PointsTab(self)
        self.params_tab = ParametersTab(self)
        self.links_tab = LinksTab(self)
        self.angles_tab = AnglesTab(self)
        self.bodies_tab = BodiesTab(self)
        self.constraints_tab = ConstraintsTab(self)
        self.tabs.addTab(self.params_tab, "Parameters")
        self.tabs.addTab(self.points_tab, "Points")
        self.tabs.addTab(self.links_tab, "Lengths")
        self.tabs.addTab(self.angles_tab, "Angles")
        self.tabs.addTab(self.constraints_tab, "Constraints")
        self.tabs.addTab(self.bodies_tab, "Rigid Bodies")

    def defer_refresh_all(self, keep_selection=False):
        QTimer.singleShot(0, lambda: self.refresh_all(keep_selection=keep_selection))

    def refresh_all(self, keep_selection=False):
        self.params_tab.refresh(keep_selection=keep_selection)
        self.points_tab.refresh(keep_selection=keep_selection)
        self.links_tab.refresh(keep_selection=keep_selection)
        self.angles_tab.refresh(keep_selection=keep_selection)
        self.constraints_tab.refresh(keep_selection=keep_selection)
        self.bodies_tab.refresh(keep_selection=keep_selection)

    def refresh_fast(self):
        # Parameters rarely change during dragging; no fast-refresh needed.
        self.points_tab.refresh_fast()
        self.links_tab.refresh_fast()
        self.angles_tab.refresh_fast()
        self.constraints_tab.refresh_fast()

    def clear_points_selection_only(self):
        self.points_tab.table.clearSelection()
    def clear_links_selection_only(self):
        self.links_tab.table.clearSelection()
    def clear_angles_selection_only(self):
        self.angles_tab.table.clearSelection()
    def clear_constraints_selection_only(self):
        self.constraints_tab.table.clearSelection()

    def select_constraints_row(self, key: str):
        self.constraints_tab.select_key(key)

    def clear_bodies_selection_only(self):
        self.bodies_tab.table.clearSelection()

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
