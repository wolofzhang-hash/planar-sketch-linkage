# -*- coding: utf-8 -*-
"""Plot window for sweep/measurement data.

Features:
- Choose X axis: Time / Input / Output / any measurement
- Choose one or multiple Y series (Output + measurements)
- Render in a separate window
- Export SVG and CSV

This module intentionally stays lightweight: it plots the most recently collected sweep
in the Simulation panel.
"""

from __future__ import annotations

import csv
from typing import Dict, List, Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QComboBox, QListWidget,
    QListWidgetItem
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class PlotWindow(QMainWindow):
    def __init__(self, records: List[Dict[str, Any]]):
        super().__init__()
        self.setWindowTitle("Plot")
        self.resize(1000, 650)

        self._records: List[Dict[str, Any]] = records or []
        self._last_x_key: Optional[str] = None
        self._last_y_keys: List[str] = []

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("X:"))
        self.cb_x = QComboBox()
        ctrl.addWidget(self.cb_x, 1)

        ctrl.addWidget(QLabel("Y:"))
        self.lst_y = QListWidget()
        self.lst_y.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.lst_y.setMaximumHeight(130)
        ctrl.addWidget(self.lst_y, 2)

        btn_col = QVBoxLayout()
        self.btn_plot = QPushButton("Plot")
        self.btn_export_svg = QPushButton("Export SVG")
        self.btn_export_csv = QPushButton("Export CSV")
        btn_col.addWidget(self.btn_plot)
        btn_col.addWidget(self.btn_export_svg)
        btn_col.addWidget(self.btn_export_csv)
        btn_col.addStretch(1)
        ctrl.addLayout(btn_col)

        layout.addLayout(ctrl)

        # Matplotlib canvas
        self.fig = Figure(figsize=(6, 4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas, 1)

        self.btn_plot.clicked.connect(self.plot)
        self.btn_export_svg.clicked.connect(self.export_svg)
        self.btn_export_csv.clicked.connect(self.export_csv)

        self._populate_axes_options()

    def _populate_axes_options(self):
        self.cb_x.clear()
        self.lst_y.clear()

        if not self._records:
            self.cb_x.addItem("(no data)", None)
            return

        # Collect keys present in records.
        keys = set()
        for r in self._records:
            keys.update(r.keys())

        def is_numeric_key(key: str) -> bool:
            saw_value = False
            for r in self._records:
                v = r.get(key)
                if v is None:
                    continue
                if isinstance(v, bool):
                    return False
                try:
                    float(v)
                except (TypeError, ValueError):
                    return False
                saw_value = True
            return saw_value

        # Preferred ordering
        x_candidates = []
        for k in ["input_deg", "time", "output_deg"]:
            if k in keys:
                x_candidates.append(k)

        # Measurements: anything else numeric-like
        meas = sorted(
            [k for k in keys if k not in {"time", "input_deg", "output_deg"} and is_numeric_key(k)]
        )
        x_candidates.extend(meas)

        def label_for(k: str) -> str:
            if k == "time":
                return "Time"
            if k == "input_deg":
                return "Input (deg)"
            if k == "output_deg":
                return "Output (deg)"
            return str(k)

        for k in x_candidates:
            self.cb_x.addItem(label_for(k), k)

        # Y list: measurements (allow multi), optionally include output
        y_candidates = []
        y_candidates.extend(meas)
        if "output_deg" in keys:
            y_candidates.append("output_deg")
        default_y = meas[0] if meas else ("output_deg" if "output_deg" in keys else None)

        for k in y_candidates:
            it = QListWidgetItem(label_for(k))
            it.setData(Qt.ItemDataRole.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if default_y and k == default_y else Qt.CheckState.Unchecked)
            self.lst_y.addItem(it)

        if "input_deg" in keys:
            idx = self.cb_x.findData("input_deg")
            if idx >= 0:
                self.cb_x.setCurrentIndex(idx)

    def _selected_y_keys(self) -> List[str]:
        ys: List[str] = []
        for i in range(self.lst_y.count()):
            it = self.lst_y.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                k = it.data(Qt.ItemDataRole.UserRole)
                if k:
                    ys.append(str(k))
        return ys

    def _get_series(self, key: str) -> List[float]:
        out: List[float] = []
        for r in self._records:
            v = r.get(key)
            if v is None or isinstance(v, bool):
                out.append(float("nan"))
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(float("nan"))
        return out

    def plot(self):
        if not self._records:
            QMessageBox.information(self, "Plot", "No sweep data yet. Run Play in the Simulation panel first.")
            return

        x_key = self.cb_x.currentData()
        if not x_key:
            return
        y_keys = self._selected_y_keys()
        if not y_keys:
            QMessageBox.information(self, "Plot", "Please check at least one Y series.")
            return

        self._last_x_key = str(x_key)
        self._last_y_keys = [str(k) for k in y_keys]

        x = self._get_series(self._last_x_key)

        self.ax.clear()
        for k in self._last_y_keys:
            y = self._get_series(k)
            self.ax.plot(x, y, label=k)
        self.ax.set_xlabel(self.cb_x.currentText())
        self.ax.set_ylabel("Value")
        if len(self._last_y_keys) > 1:
            self.ax.legend()
        self.ax.grid(True)
        self.canvas.draw_idle()

    def export_svg(self):
        if not self._records:
            QMessageBox.information(self, "Export", "No data to export.")
            return
        if self._last_x_key is None:
            self.plot()
        path, _ = QFileDialog.getSaveFileName(self, "Export SVG", "", "SVG (*.svg)")
        if not path:
            return
        if not path.lower().endswith(".svg"):
            path += ".svg"
        try:
            self.fig.savefig(path, format="svg")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def export_csv(self):
        if not self._records:
            QMessageBox.information(self, "Export", "No data to export.")
            return
        if self._last_x_key is None:
            self.plot()
        if self._last_x_key is None:
            return
        if not self._last_y_keys:
            QMessageBox.information(self, "Export", "No Y series selected.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                header = [self._last_x_key] + self._last_y_keys
                w.writerow(header)
                for r in self._records:
                    row = [r.get(self._last_x_key)]
                    for k in self._last_y_keys:
                        row.append(r.get(k))
                    w.writerow(row)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
