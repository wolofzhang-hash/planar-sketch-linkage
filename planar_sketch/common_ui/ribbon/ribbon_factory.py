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
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(2)

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
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(4)

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
        self.setMinimumHeight(82)
        self.setMaximumHeight(88)
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




def apply_compact_ribbon_style(ribbonbar: QMenuBar) -> None:
    tab_font = QFont()
    tab_font.setPointSize(12)
    for tabbar in ribbonbar.findChildren(QTabBar):
        tabbar.setFont(tab_font)
        tabbar.setMinimumHeight(20)

    button_font = QFont()
    button_font.setPointSize(9)
    for button in ribbonbar.findChildren(QToolButton):
        button.setIconSize(QSize(22, 22))
        button.setFont(button_font)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

    label_font = QFont()
    label_font.setPointSize(8)
    for label in ribbonbar.findChildren(QLabel):
        label.setFont(label_font)
        label.setContentsMargins(0, 0, 0, 0)

    # Hide the default application button (usually shown as "PyQtRibbon") so
    # the tab row starts cleanly from the first tab.
    for button in ribbonbar.findChildren(QToolButton):
        if button.text().strip() == "PyQtRibbon":
            button.hide()

    ribbonbar.setMaximumHeight(84)

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
    apply_ribbon_qss(ribbon)
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

    apply_compact_ribbon_style(ribbon)
    return result
