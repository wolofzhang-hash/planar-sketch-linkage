# -*- coding: utf-8 -*-
"""Settings dialog for display preferences."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
)

from .i18n import tr


class SettingsDialog(QDialog):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.lang = getattr(self.ctrl, "ui_language", "en")
        self.setWindowTitle(tr(self.lang, "settings.title"))

        layout = QFormLayout(self)
        self.spin_precision = QSpinBox(self)
        self.spin_precision.setRange(0, 6)
        self.spin_precision.setValue(int(getattr(self.ctrl, "display_precision", 3)))
        layout.addRow(tr(self.lang, "settings.decimal_places"), self.spin_precision)

        self.spin_load_arrow = QDoubleSpinBox(self)
        self.spin_load_arrow.setRange(0.2, 6.0)
        self.spin_load_arrow.setSingleStep(0.1)
        self.spin_load_arrow.setValue(float(getattr(self.ctrl, "load_arrow_width", 1.6)))
        layout.addRow(tr(self.lang, "settings.load_arrow"), self.spin_load_arrow)

        self.spin_torque_arrow = QDoubleSpinBox(self)
        self.spin_torque_arrow.setRange(0.2, 6.0)
        self.spin_torque_arrow.setSingleStep(0.1)
        self.spin_torque_arrow.setValue(float(getattr(self.ctrl, "torque_arrow_width", 1.6)))
        layout.addRow(tr(self.lang, "settings.torque_arrow"), self.spin_torque_arrow)

        self.combo_language = QComboBox(self)
        self.combo_language.addItem(tr(self.lang, "language.english"), "en")
        self.combo_language.addItem(tr(self.lang, "language.chinese"), "zh")
        current_language = getattr(self.ctrl, "ui_language", "en")
        index = self.combo_language.findData(current_language)
        if index >= 0:
            self.combo_language.setCurrentIndex(index)
        layout.addRow(tr(self.lang, "settings.language"), self.combo_language)

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

    def language(self) -> str:
        return str(self.combo_language.currentData() or "en")
