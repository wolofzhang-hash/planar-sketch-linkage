# -*- coding: utf-8 -*-
"""Centralized UI theme (QSS + palette).

Design goals:
- Professional, calm, consistent light theme
- Single place to tweak colors/spacing/fonts
- Easy to migrate: import and call apply_theme(app)

NOTE: Keep this module dependency-light; do not import application UI modules here.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeTokens:
    # Core surfaces
    bg: str = "#F6F7F9"
    panel: str = "#FFFFFF"
    panel_alt: str = "#FAFBFC"
    border: str = "#D7DCE3"

    # Text
    text: str = "#1F2328"
    text_muted: str = "#57606A"

    # Brand / accent
    accent: str = "#2563EB"  # calm blue
    accent_hover: str = "#1D4ED8"
    accent_pressed: str = "#1E40AF"

    # States
    danger: str = "#DC2626"
    warning: str = "#D97706"
    ok: str = "#16A34A"


def _build_palette(t: ThemeTokens) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.bg))
    pal.setColor(QPalette.ColorRole.Base, QColor(t.panel))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t.panel_alt))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(t.panel))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    return pal


def _default_font() -> QFont:
    # Prefer system UI fonts; include common Chinese fonts.
    # Qt will pick the first available.
    f = QFont()
    f.setFamilies([
        "Microsoft YaHei",
        "Segoe UI",
        "PingFang SC",
        "Noto Sans CJK SC",
        "SimHei",
        "Arial",
    ])
    f.setPointSize(10)
    return f


def _qss(t: ThemeTokens) -> str:
    # Keep QSS compact and predictable; avoid over-styling to preserve native behavior.
    return f"""
/* ---- Global ---- */
* {{
  font-family: 'Microsoft YaHei','Segoe UI','PingFang SC','Noto Sans CJK SC','SimHei','Arial';
  font-size: 10pt;
}}

QMainWindow, QWidget {{
  background: {t.bg};
  color: {t.text};
}}

/* ---- Menus ---- */
QMenuBar {{
  background: {t.panel};
  border-bottom: 1px solid {t.border};
}}
QMenuBar::item {{
  padding: 6px 10px;
  background: transparent;
}}
QMenuBar::item:selected {{
  background: {t.panel_alt};
  border-radius: 6px;
}}
QMenu {{
  background: {t.panel};
  border: 1px solid {t.border};
  padding: 6px;
}}
QMenu::item {{
  padding: 6px 22px;
  border-radius: 6px;
}}
QMenu::item:selected {{
  background: {t.panel_alt};
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
  border: 1px solid {t.border};
  background: {t.panel};
  top: -1px;
}}
QTabBar::tab {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-bottom: none;
  padding: 6px 12px;
  margin-right: 4px;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: {t.text_muted};
}}
QTabBar::tab:selected {{
  background: {t.panel_alt};
  color: {t.text};
}}
QTabBar::tab:hover {{
  background: {t.panel_alt};
}}

/* ---- Group boxes ---- */
QGroupBox {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-radius: 10px;
  margin-top: 14px;
}}
QGroupBox::title {{
  subcontrol-origin: margin;
  left: 10px;
  padding: 0 6px;
  color: {t.text_muted};
}}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-radius: 8px;
  padding: 6px 8px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
  border: 1px solid {t.accent};
}}

QComboBox {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-radius: 8px;
  padding: 6px 8px;
}}
QComboBox:focus {{
  border: 1px solid {t.accent};
}}

/* ---- Buttons ---- */
QPushButton {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-radius: 8px;
  padding: 6px 12px;
}}
QPushButton:hover {{
  background: {t.panel_alt};
}}
QPushButton:pressed {{
  background: #EEF2FF;
}}

QPushButton[primary="true"] {{
  background: {t.accent};
  border: 1px solid {t.accent};
  color: white;
}}
QPushButton[primary="true"]:hover {{
  background: {t.accent_hover};
  border: 1px solid {t.accent_hover};
}}
QPushButton[primary="true"]:pressed {{
  background: {t.accent_pressed};
  border: 1px solid {t.accent_pressed};
}}

QPushButton[danger="true"] {{
  background: {t.danger};
  border: 1px solid {t.danger};
  color: white;
}}
QPushButton[danger="true"]:hover {{
  background: #B91C1C;
  border: 1px solid #B91C1C;
}}
QPushButton[danger="true"]:pressed {{
  background: #991B1B;
  border: 1px solid #991B1B;
}}

/* ---- Tables ---- */
QHeaderView::section {{
  background: {t.panel_alt};
  color: {t.text_muted};
  padding: 6px 8px;
  border: 0px;
  border-bottom: 1px solid {t.border};
}}
QTableView, QTreeView {{
  background: {t.panel};
  border: 1px solid {t.border};
  border-radius: 10px;
  gridline-color: {t.border};
  selection-background-color: #DBEAFE;
  selection-color: {t.text};
}}

/* ---- Scrollbars (subtle) ---- */
QScrollBar:vertical {{
  background: transparent;
  width: 10px;
  margin: 2px;
}}
QScrollBar::handle:vertical {{
  background: #CBD5E1;
  border-radius: 5px;
  min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
  background: #94A3B8;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
  height: 0px;
}}

QScrollBar:horizontal {{
  background: transparent;
  height: 10px;
  margin: 2px;
}}
QScrollBar::handle:horizontal {{
  background: #CBD5E1;
  border-radius: 5px;
  min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
  background: #94A3B8;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
  width: 0px;
}}

/* ---- Status bar ---- */
QStatusBar {{
  background: {t.panel};
  border-top: 1px solid {t.border};
  color: {t.text_muted};
}}
"""


def apply_theme(app: QApplication, theme: str = "light") -> None:
    """Apply the global UI theme.

    Keep it idempotent: safe to call more than once.
    """
    # Consistent cross-platform look
    app.setStyle("Fusion")

    tokens = ThemeTokens()  # future: choose by `theme`
    app.setPalette(_build_palette(tokens))
    app.setFont(_default_font())
    app.setStyleSheet(_qss(tokens))

    # Better mouse-wheel / focus feel
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
