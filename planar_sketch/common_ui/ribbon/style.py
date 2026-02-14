from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QMenuBar, QToolButton


def apply_compact_largeicon_style(ribbonbar: QMenuBar) -> None:
    if hasattr(ribbonbar, "setRibbonHeight"):
        ribbonbar.setRibbonHeight(78)

    if hasattr(ribbonbar, "applicationOptionButton"):
        app_btn = ribbonbar.applicationOptionButton()
        if app_btn is not None:
            app_btn.hide()

    def _restore_ribbon_button_content() -> None:
        for button in ribbonbar.findChildren(QToolButton):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            if not button.toolTip() and button.text():
                button.setToolTip(button.text())

    _restore_ribbon_button_content()
    QTimer.singleShot(0, _restore_ribbon_button_content)
