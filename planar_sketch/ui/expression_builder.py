# -*- coding: utf-8 -*-
"""Expression builder dialog."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, Iterable, List, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QGroupBox,
    QDialogButtonBox,
    QTabWidget,
    QPushButton,
)


class ExpressionBuilderDialog(QDialog):
    def __init__(
        self,
        parent,
        initial: str = "",
        tokens: Iterable[str] | Mapping[str, Iterable[str]] | None = None,
        functions: Iterable[str] | Mapping[str, Iterable[str]] | None = None,
        evaluator: Optional[Callable[[str], tuple[Optional[float], Optional[str]]]] = None,
        title: str = "Expression Builder",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._evaluator = evaluator

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Expression"))
        self.edit = QLineEdit(initial)
        layout.addWidget(self.edit)

        lists_row = QHBoxLayout()
        self._tokens_list = self._build_list_box("Tokens", tokens or [])
        self._functions_list = self._build_list_box("Functions", functions or [])
        lists_row.addWidget(self._tokens_list["box"])
        lists_row.addWidget(self._functions_list["box"])
        layout.addLayout(lists_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        footer = QHBoxLayout()
        self._eval_button = QPushButton("Evaluate")
        self._eval_label = QLabel("Value: --")
        self._eval_label.setMinimumWidth(220)
        self._eval_button.clicked.connect(self._on_evaluate_clicked)
        if self._evaluator is None:
            self._eval_button.setVisible(False)
            self._eval_label.setVisible(False)
        footer.addWidget(self._eval_button)
        footer.addWidget(self._eval_label)
        footer.addStretch(1)
        footer.addWidget(buttons)
        layout.addLayout(footer)

    def _build_list_box(self, title: str, items: Iterable[str] | Mapping[str, Iterable[str]]):
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        list_widgets: List[QListWidget] = []
        if isinstance(items, Mapping):
            tabs = QTabWidget()
            for group_name, group_items in items.items():
                list_widget = QListWidget()
                sorted_items: List[str] = sorted(str(it) for it in group_items if str(it))
                list_widget.addItems(sorted_items)
                list_widget.itemDoubleClicked.connect(lambda item: self._insert_text(item.text()))
                tabs.addTab(list_widget, str(group_name))
                list_widgets.append(list_widget)
            box_layout.addWidget(tabs)
        else:
            list_widget = QListWidget()
            sorted_items: List[str] = sorted(str(it) for it in items if str(it))
            list_widget.addItems(sorted_items)
            list_widget.itemDoubleClicked.connect(lambda item: self._insert_text(item.text()))
            box_layout.addWidget(list_widget)
            list_widgets.append(list_widget)
        return {"box": box, "lists": list_widgets}

    def _insert_text(self, text: str) -> None:
        def is_identifier_path(value: str) -> bool:
            if not value:
                return False
            parts = value.split(".")
            return all(part.isidentifier() for part in parts)

        operators = {"+", "-", "*", "/", "(", ")", ","}
        if text and not is_identifier_path(text) and not text.endswith("(") and text not in operators:
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            self.edit.insert(f'signal("{escaped}")')
        else:
            self.edit.insert(text)
        self.edit.setFocus()

    def _on_evaluate_clicked(self) -> None:
        if self._evaluator is None:
            return
        expr = self.edit.text()
        value, err = self._evaluator(expr)
        if err:
            self._eval_label.setText(f"Error: {err}")
            self._eval_label.setStyleSheet("color: #c0392b;")
        else:
            self._eval_label.setText(f"Value: {value:.6g}" if value is not None else "Value: --")
            self._eval_label.setStyleSheet("")

    def expression(self) -> str:
        return self.edit.text()
