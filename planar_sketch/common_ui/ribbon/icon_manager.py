from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QStyle, QToolButton, QWidget


@dataclass(frozen=True)
class RibbonIconConfig:
    icon_size: QSize = QSize(28, 28)


_FALLBACK_ICON_PATH = Path(__file__).resolve().parents[1] / "assets" / "fallback_action.svg"


def _fallback_icon() -> QIcon:
    if _FALLBACK_ICON_PATH.exists():
        return QIcon(str(_FALLBACK_ICON_PATH))
    return QIcon()


def assign_default_icons(actions: dict[str, QAction], style: QStyle, standard_pixmaps: dict[str, QStyle.StandardPixmap]) -> None:
    fallback = _fallback_icon()
    for key, action in actions.items():
        if action.icon().isNull() and key in standard_pixmaps:
            action.setIcon(style.standardIcon(standard_pixmaps[key]))
        if action.icon().isNull() and not fallback.isNull():
            action.setIcon(fallback)


def style_large_button(button: QToolButton, config: RibbonIconConfig) -> None:
    button.setIconSize(config.icon_size)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)


def ensure_large_button_icon(button: QToolButton, action: QAction) -> None:
    if button.icon().isNull():
        button.setIcon(action.icon() if not action.icon().isNull() else _fallback_icon())


def apply_ribbon_qss(target: QWidget) -> None:
    qss_path = Path(__file__).with_name("ribbon_style.qss")
    if qss_path.exists():
        existing = target.styleSheet() or ""
        target.setStyleSheet(f"{existing}\n{qss_path.read_text(encoding='utf-8')}")
