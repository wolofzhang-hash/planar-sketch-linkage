from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QStyle, QToolButton


_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_FALLBACK_ICON_PATH = _ASSETS_DIR / "fallback_action.svg"
_APP_ICON_PATH = _ASSETS_DIR / "app_icon.svg"


def _fallback_icon() -> QIcon:
    if _FALLBACK_ICON_PATH.exists():
        return QIcon(str(_FALLBACK_ICON_PATH))
    if _APP_ICON_PATH.exists():
        return QIcon(str(_APP_ICON_PATH))
    return QIcon()


def assign_default_icons(actions: dict[str, QAction], style: QStyle, standard_pixmaps: dict[str, QStyle.StandardPixmap]) -> None:
    fallback = _fallback_icon()
    for key, action in actions.items():
        if action.icon().isNull() and key in standard_pixmaps:
            action.setIcon(style.standardIcon(standard_pixmaps[key]))
        if action.icon().isNull() and not fallback.isNull():
            action.setIcon(fallback)


def ensure_large_button_icon(button: QToolButton, action: QAction) -> None:
    if button.icon().isNull():
        button.setIcon(action.icon() if not action.icon().isNull() else _fallback_icon())
