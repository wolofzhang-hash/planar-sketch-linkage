from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QMenuBar, QTabBar, QToolButton

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

    tab_font = QFont()
    tab_font.setPointSize(_TAB_FONT_SIZE)
    for tabbar in ribbonbar.findChildren(QTabBar):
        tabbar.setFont(tab_font)
        tabbar.setMinimumHeight(22)
        tabbar.setMaximumHeight(24)

    button_font = QFont()
    button_font.setPointSize(_BUTTON_FONT_SIZE)
    for button in ribbonbar.findChildren(QToolButton):
        button.setIconSize(_ICON_SIZE)
        button.setFont(button_font)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

    ribbonbar.setMinimumHeight(92)
    ribbonbar.setMaximumHeight(106)
