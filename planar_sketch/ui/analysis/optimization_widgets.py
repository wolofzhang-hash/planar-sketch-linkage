"""Optimization-specific UI helper widgets."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout, QHBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from ..i18n import tr, get_ui_language


def _lang(owner) -> str:
    ctrl = getattr(owner, "ctrl", owner)
    return get_ui_language(ctrl, fallback="zh")


def _tr(owner, key: str, **kwargs) -> str:
    return tr(_lang(owner), key, **kwargs)


class _OptimizationPlotsDialog(QDialog):
    """Detached plots window for optimization results (curve + convergence)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        row = QHBoxLayout()
        self._fig_curve = Figure(figsize=(5, 3), dpi=100)
        self._ax_curve = self._fig_curve.add_subplot(111)
        self._canvas_curve = FigureCanvas(self._fig_curve)
        row.addWidget(self._canvas_curve, 2)
        self._fig_conv = Figure(figsize=(4, 3), dpi=100)
        self._ax_conv = self._fig_conv.add_subplot(111)
        self._canvas_conv = FigureCanvas(self._fig_conv)
        row.addWidget(self._canvas_conv, 1)
        layout.addLayout(row, 1)

    def apply_language(self, lang: str) -> None:
        self.setWindowTitle(_tr(self, "opt.plot_window_title"))

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
