from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QLabel, QMenuBar, QTabBar, QTabWidget, QToolButton, QVBoxLayout, QWidget

from .action_registry import ActionRegistry
from .icon_manager import RibbonIconConfig, apply_ribbon_qss, ensure_large_button_icon, style_large_button
from .ribbon_spec import RibbonSpec

try:
    from pyqtribbon import RibbonBar as _RibbonBar
except Exception:
    _RibbonBar = None


class _CompatPanel(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(1)

    def addLargeButton(self, text: str, icon):
        btn = QToolButton(self)
        btn.setText(text)
        btn.setIcon(icon)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._layout.addWidget(btn)
        return btn

    def addWidget(self, widget: QWidget):
        self._layout.addWidget(widget)
        return widget


class _CompatCategory(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(1)

    def addPanel(self, title: str):
        panel = _CompatPanel(title, self)
        self._layout.addWidget(panel)
        return panel


class _CompatRibbonBar(QMenuBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self.setNativeMenuBar(False)
        self.setMinimumHeight(92)
        self.setMaximumHeight(100)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self._tabs)

    def addCategory(self, title: str):
        category = _CompatCategory(title, self)
        self._tabs.addTab(category, title)
        return category

    def setCurrentCategory(self, category):
        idx = self._tabs.indexOf(category)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)


@dataclass
class RibbonBuildResult:
    ribbon: QMenuBar
    categories: dict[str, object] = field(default_factory=dict)
    action_buttons: dict[str, list[QToolButton]] = field(default_factory=dict)


def _build_bar(parent) -> QMenuBar:
    if _RibbonBar is not None:
        return _RibbonBar(parent)
    return _CompatRibbonBar(parent)




def _hide_or_soften_brand_block(ribbonbar: QMenuBar) -> None:
    brand_widgets: list[QWidget] = []

    for label in ribbonbar.findChildren(QLabel):
        if "pyqtribbon" in label.text().strip().lower():
            brand_widgets.append(label)

    for button in ribbonbar.findChildren(QToolButton):
        if "pyqtribbon" in button.text().strip().lower():
            brand_widgets.append(button)

    hidden = False
    for widget in brand_widgets:
        widget.setVisible(False)
        parent = widget.parentWidget()
        if parent is not None:
            parent.setMaximumWidth(0)
            parent.setMinimumWidth(0)
        hidden = True

    if not hidden:
        for label in ribbonbar.findChildren(QLabel):
            text = label.text().strip()
            if not text:
                continue
            if text.lower() in {"ribbon", "application"}:
                label.setStyleSheet("font-size: 7px; color: #9a9a9a; padding: 0px; margin: 0px;")


def apply_ribbon_style(ribbonbar: QMenuBar) -> None:
    apply_ribbon_qss(ribbonbar)

    tab_font = QFont()
    tab_font.setPointSize(12)
    for tabbar in ribbonbar.findChildren(QTabBar):
        tabbar.setFont(tab_font)
        tabbar.setMinimumHeight(24)
        tabbar.setMaximumHeight(26)

    button_font = QFont()
    button_font.setPointSize(10)
    for button in ribbonbar.findChildren(QToolButton):
        button.setIconSize(QSize(24, 24))
        button.setFont(button_font)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

    label_font = QFont()
    label_font.setPointSize(8)
    for label in ribbonbar.findChildren(QLabel):
        label.setFont(label_font)
        label.setContentsMargins(0, 0, 0, 0)

    _hide_or_soften_brand_block(ribbonbar)
    ribbonbar.setMinimumHeight(92)
    ribbonbar.setMaximumHeight(100)

def _sync_action_to_button(action: QAction, btn: QToolButton) -> None:
    btn.setEnabled(action.isEnabled())
    btn.setCheckable(action.isCheckable())
    btn.setChecked(action.isChecked())
    btn.clicked.connect(action.trigger)
    action.changed.connect(lambda a=action, b=btn: _apply_action_state(a, b))


def _apply_action_state(action: QAction, btn: QToolButton) -> None:
    btn.setEnabled(action.isEnabled())
    if btn.isCheckable() != action.isCheckable():
        btn.setCheckable(action.isCheckable())
    if action.isCheckable():
        btn.setChecked(action.isChecked())


def build(mainwindow, spec: RibbonSpec, registry: ActionRegistry, icon_config: RibbonIconConfig | None = None) -> RibbonBuildResult:
    icon_config = icon_config or RibbonIconConfig()
    ribbon = _build_bar(mainwindow)
    result = RibbonBuildResult(ribbon=ribbon)

    for category_spec in spec.categories:
        category = ribbon.addCategory(category_spec.title)
        result.categories[category_spec.key] = category
        for panel_spec in category_spec.panels:
            panel = category.addPanel(panel_spec.title)
            for item in panel_spec.items:
                if item.kind == "widget":
                    panel.addWidget(registry.widget(item.key))
                    continue
                action = registry.action(item.key)
                text = item.text_override or action.text()
                btn = panel.addLargeButton(text, action.icon())
                if isinstance(btn, QToolButton):
                    style_large_button(btn, icon_config)
                    ensure_large_button_icon(btn, action)
                    _sync_action_to_button(action, btn)
                    result.action_buttons.setdefault(item.key, []).append(btn)

    apply_ribbon_style(ribbon)
    return result
