from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QMenuBar, QToolButton, QWidget

_ICON_SIZE = QSize(28, 28)
_TAB_FONT_SIZE = 11
_BUTTON_FONT_SIZE = 9


def _load_qss() -> str:
    qss_path = Path(__file__).with_name("ribbon_style.qss")
    if not qss_path.exists():
        return ""
    return qss_path.read_text(encoding="utf-8")


def apply_compact_largeicon_style(ribbonbar: QMenuBar) -> None:
    qss = _load_qss()
    if qss:
        ribbonbar.setStyleSheet(qss)

    if hasattr(ribbonbar, "setRibbonHeight"):
        ribbonbar.setRibbonHeight(105)

    if hasattr(ribbonbar, "applicationOptionButton"):
        app_btn = ribbonbar.applicationOptionButton()
        if app_btn is not None:
            app_btn.hide()

    if hasattr(ribbonbar, "applicationButton"):
        app_btn = ribbonbar.applicationButton()
        if app_btn is not None:
            app_btn.hide()

    for button in ribbonbar.findChildren(QToolButton):
        if "pyqtribbon" in button.text().lower():
            button.hide()

    def _apply_tab_style() -> None:
        tabbar_getter = getattr(ribbonbar, "tabBar", None)
        if not callable(tabbar_getter):
            return
        tabbar = tabbar_getter()
        if tabbar is None:
            return
        tab_font = QFont()
        tab_font.setPointSize(_TAB_FONT_SIZE)
        tabbar.setFont(tab_font)
        tabbar.setMinimumHeight(22)
        tabbar.setMaximumHeight(24)

    def _apply_icon_and_button_style() -> None:
        button_font = QFont()
        button_font.setPointSize(_BUTTON_FONT_SIZE)
        for child in ribbonbar.findChildren(QWidget):
            if isinstance(child, QToolButton):
                child.setIconSize(_ICON_SIZE)
                child.setFont(button_font)
                child.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

    _apply_tab_style()
    _apply_icon_and_button_style()
    QTimer.singleShot(0, lambda: (_apply_tab_style(), _apply_icon_and_button_style()))
