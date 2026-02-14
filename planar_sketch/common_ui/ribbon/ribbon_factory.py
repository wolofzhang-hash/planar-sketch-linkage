from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenuBar, QTabWidget, QToolButton, QVBoxLayout, QWidget

from .action_registry import ActionRegistry
from .icon_manager import RibbonIconConfig, ensure_large_button_icon
from .ribbon_spec import RibbonSpec
from .style import apply_compact_largeicon_style

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
        self.setMaximumHeight(106)
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


def _hide_panel_option_button(panel: object) -> None:
    option_getter = getattr(panel, "panelOptionButton", None)
    if not callable(option_getter):
        return
    option_btn = option_getter()
    if option_btn is None:
        return
    option_btn.hide()


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
    _ = icon_config or RibbonIconConfig()
    ribbon = _build_bar(mainwindow)
    result = RibbonBuildResult(ribbon=ribbon)

    for category_spec in spec.categories:
        category = ribbon.addCategory(category_spec.title)
        result.categories[category_spec.key] = category
        for panel_spec in category_spec.panels:
            panel = category.addPanel(panel_spec.title)
            _hide_panel_option_button(panel)
            for item in panel_spec.items:
                if item.kind == "widget":
                    panel.addWidget(registry.widget(item.key))
                    continue
                action = registry.action(item.key)
                text = item.text_override or action.text()
                btn = panel.addLargeButton(text, action.icon())
                if isinstance(btn, QToolButton):
                    ensure_large_button_icon(btn, action)
                    _sync_action_to_button(action, btn)
                    result.action_buttons.setdefault(item.key, []).append(btn)

    apply_compact_largeicon_style(ribbon)
    return result
