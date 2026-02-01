# -*- coding: utf-8 -*-
"""Settings dialog for display preferences."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
)


class SettingsDialog(QDialog):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setWindowTitle("Settings")

        layout = QFormLayout(self)
        self.spin_precision = QSpinBox(self)
        self.spin_precision.setRange(0, 6)
        self.spin_precision.setValue(int(getattr(self.ctrl, "display_precision", 3)))
        layout.addRow("Decimal places", self.spin_precision)

        self.spin_load_arrow = QDoubleSpinBox(self)
        self.spin_load_arrow.setRange(0.2, 6.0)
        self.spin_load_arrow.setSingleStep(0.1)
        self.spin_load_arrow.setValue(float(getattr(self.ctrl, "load_arrow_width", 1.6)))
        layout.addRow("Load arrow thickness", self.spin_load_arrow)

        self.spin_torque_arrow = QDoubleSpinBox(self)
        self.spin_torque_arrow.setRange(0.2, 6.0)
        self.spin_torque_arrow.setSingleStep(0.1)
        self.spin_torque_arrow.setValue(float(getattr(self.ctrl, "torque_arrow_width", 1.6)))
        layout.addRow("Torque arrow thickness", self.spin_torque_arrow)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def decimal_places(self) -> int:
        return int(self.spin_precision.value())

    def load_arrow_width(self) -> float:
        return float(self.spin_load_arrow.value())

    def torque_arrow_width(self) -> float:
        return float(self.spin_torque_arrow.value())
