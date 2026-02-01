# -*- coding: utf-8 -*-
"""Settings dialog for display preferences."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def decimal_places(self) -> int:
        return int(self.spin_precision.value())
