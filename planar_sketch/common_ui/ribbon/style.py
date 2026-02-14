from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenuBar, QToolButton


def apply_compact_largeicon_style(ribbonbar: QMenuBar) -> None:
    if hasattr(ribbonbar, "setRibbonHeight"):
        ribbonbar.setRibbonHeight(78)

    if hasattr(ribbonbar, "applicationOptionButton"):
        app_btn = ribbonbar.applicationOptionButton()
        if app_btn is not None:
            app_btn.hide()

    def _hide_ribbon_button_content() -> None:
        for button in ribbonbar.findChildren(QToolButton):
            button.setIcon(QIcon())
            button.setText("")
            button.setToolTip("")

    _hide_ribbon_button_content()
    QTimer.singleShot(0, _hide_ribbon_button_content)
