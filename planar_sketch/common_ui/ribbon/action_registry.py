from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget


@dataclass
class ActionRegistry:
    actions: dict[str, QAction] = field(default_factory=dict)
    widgets: dict[str, Callable[[], QWidget]] = field(default_factory=dict)

    def action(self, key: str) -> QAction:
        return self.actions[key]

    def widget(self, key: str) -> QWidget:
        return self.widgets[key]()
