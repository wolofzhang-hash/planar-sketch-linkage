# -*- coding: utf-8 -*-
"""Dialog for grid settings."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QDoubleSpinBox,
)

from .i18n import tr


class GridSettingsDialog(QDialog):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.lang = getattr(self.ctrl, "ui_language", "en")
        self.setWindowTitle(tr(self.lang, "grid.title"))

        settings = getattr(self.ctrl, "grid_settings", {}) or {}
        center = settings.get("center", (0.0, 0.0))

        layout = QFormLayout(self)

        self.spin_spacing_x = QDoubleSpinBox(self)
        self.spin_spacing_x.setRange(0.1, 100000.0)
        self.spin_spacing_x.setDecimals(2)
        self.spin_spacing_x.setValue(float(settings.get("spacing_x", 100.0)))
        layout.addRow(tr(self.lang, "grid.spacing_x"), self.spin_spacing_x)

        self.spin_spacing_y = QDoubleSpinBox(self)
        self.spin_spacing_y.setRange(0.1, 100000.0)
        self.spin_spacing_y.setDecimals(2)
        self.spin_spacing_y.setValue(float(settings.get("spacing_y", 100.0)))
        layout.addRow(tr(self.lang, "grid.spacing_y"), self.spin_spacing_y)

        self.spin_range_x = QDoubleSpinBox(self)
        self.spin_range_x.setRange(0.0, 1000000.0)
        self.spin_range_x.setDecimals(2)
        self.spin_range_x.setValue(float(settings.get("range_x", 2000.0)))
        layout.addRow(tr(self.lang, "grid.range_x"), self.spin_range_x)

        self.spin_range_y = QDoubleSpinBox(self)
        self.spin_range_y.setRange(0.0, 1000000.0)
        self.spin_range_y.setDecimals(2)
        self.spin_range_y.setValue(float(settings.get("range_y", 2000.0)))
        layout.addRow(tr(self.lang, "grid.range_y"), self.spin_range_y)

        self.spin_center_x = QDoubleSpinBox(self)
        self.spin_center_x.setRange(-1000000.0, 1000000.0)
        self.spin_center_x.setDecimals(2)
        self.spin_center_x.setValue(float(center[0] if len(center) > 0 else 0.0))
        layout.addRow(tr(self.lang, "grid.center_x"), self.spin_center_x)

        self.spin_center_y = QDoubleSpinBox(self)
        self.spin_center_y.setRange(-1000000.0, 1000000.0)
        self.spin_center_y.setDecimals(2)
        self.spin_center_y.setValue(float(center[1] if len(center) > 1 else 0.0))
        layout.addRow(tr(self.lang, "grid.center_y"), self.spin_center_y)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def settings(self) -> dict:
        return {
            "spacing_x": float(self.spin_spacing_x.value()),
            "spacing_y": float(self.spin_spacing_y.value()),
            "range_x": float(self.spin_range_x.value()),
            "range_y": float(self.spin_range_y.value()),
            "center_x": float(self.spin_center_x.value()),
            "center_y": float(self.spin_center_y.value()),
        }
