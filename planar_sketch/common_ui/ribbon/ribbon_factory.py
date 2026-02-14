from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QToolButton
from pyqtribbon import RibbonBar

from .action_registry import ActionRegistry
from .icon_manager import ensure_large_button_icon
from .ribbon_spec import RibbonSpec
from .style import apply_ribbon_style


@dataclass
class RibbonBuildResult:
    ribbon: RibbonBar
    categories: dict[str, object] = field(default_factory=dict)
    action_buttons: dict[str, list[QToolButton]] = field(default_factory=dict)


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


def build(mainwindow, spec: RibbonSpec, registry: ActionRegistry) -> RibbonBuildResult:
    ribbon = RibbonBar(mainwindow)
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

    apply_ribbon_style(ribbon)
    return result
