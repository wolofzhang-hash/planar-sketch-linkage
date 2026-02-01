# -*- coding: utf-8 -*-
"""Expression builder dialog."""

from __future__ import annotations

from typing import Iterable, List

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QGroupBox,
    QDialogButtonBox,
)


class ExpressionBuilderDialog(QDialog):
    def __init__(
        self,
        parent,
        initial: str = "",
        tokens: Iterable[str] | None = None,
        functions: Iterable[str] | None = None,
        title: str = "Expression Builder",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

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

        self._tokens_list["list"].itemDoubleClicked.connect(lambda item: self._insert_text(item.text()))
        self._functions_list["list"].itemDoubleClicked.connect(lambda item: self._insert_text(item.text()))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_list_box(self, title: str, items: Iterable[str]):
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        list_widget = QListWidget()
        sorted_items: List[str] = sorted(str(it) for it in items)
        list_widget.addItems(sorted_items)
        box_layout.addWidget(list_widget)
        return {"box": box, "list": list_widget}

    def _insert_text(self, text: str) -> None:
        self.edit.insert(text)
        self.edit.setFocus()

    def expression(self) -> str:
        return self.edit.text()
