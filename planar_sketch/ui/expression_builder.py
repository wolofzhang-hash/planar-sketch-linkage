# -*- coding: utf-8 -*-
"""Expression builder dialog."""

from __future__ import annotations


import json
from pathlib import Path


def _exprbuilder_global_templates_path() -> Path:
    base = Path.home() / ".planar_sketch"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "expression_builder_templates.json"


def load_global_expression_builder_template_overrides() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Load user-global template/function-help overrides for expression builder.
    Returns (template_groups, help_overrides). Missing/invalid file -> empty dicts.
    """
    path = _exprbuilder_global_templates_path()
    if not path.exists():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        groups = data.get('function_groups') or data.get('templates') or {}
        helps = data.get('function_help_overrides') or data.get('help_overrides') or {}
        norm_groups = {}
        if isinstance(groups, dict):
            for k, v in groups.items():
                if not isinstance(k, str):
                    continue
                if isinstance(v, (list, tuple)):
                    norm_groups[k] = [str(x) for x in v if str(x).strip()]
        norm_helps = {}
        if isinstance(helps, dict):
            for k, v in helps.items():
                if isinstance(k, str):
                    norm_helps[k] = str(v)
        return norm_groups, norm_helps
    except Exception:
        return {}, {}


def save_global_expression_builder_template_overrides(function_groups: Mapping[str, Iterable[str]] | None, function_help_overrides: Mapping[str, str] | None) -> bool:
    """Persist user-global template/function-help overrides. Returns success flag."""
    path = _exprbuilder_global_templates_path()
    try:
        groups_out = {}
        if isinstance(function_groups, Mapping):
            for k, v in function_groups.items():
                if not isinstance(k, str):
                    continue
                if isinstance(v, (list, tuple)):
                    groups_out[k] = [str(x) for x in v if str(x).strip()]
                else:
                    groups_out[k] = [str(x) for x in list(v)] if v is not None else []
        helps_out = {}
        if isinstance(function_help_overrides, Mapping):
            for k, v in function_help_overrides.items():
                if isinstance(k, str):
                    helps_out[k] = str(v)
        payload = {
            'version': 1,
            'function_groups': groups_out,
            'function_help_overrides': helps_out,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:
        return False

from collections.abc import Mapping, MutableMapping
from typing import Callable, Iterable, List, Optional

from ..core.expression_registry import PARAMETER_FUNCTIONS

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QGroupBox,
    QDialogButtonBox,
    QPushButton,
    QComboBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
)

from .i18n import tr, get_ui_language


class ExpressionBuilderDialog(QDialog):
    def __init__(
        self,
        parent,
        initial: str = "",
        tokens: Iterable[str] | Mapping[str, Iterable[str]] | None = None,
        functions: Iterable[str] | Mapping[str, Iterable[str]] | None = None,
        evaluator: Optional[Callable[[str], tuple[Optional[float], Optional[str]]]] = None,
        title: str = "Expression Builder",
        lang: str | None = None,
        function_help_overrides: Optional[Mapping[str, str]] = None,
        allow_edit_templates: bool = False,
    ) -> None:
        super().__init__(parent)
        self._lang = get_ui_language(getattr(parent, "ctrl", None) if parent else None, fallback="zh") if lang is None else lang
        if title == "Expression Builder":
            self.setWindowTitle(tr(self._lang, "dialog.expression_builder.title"))
        else:
            self.setWindowTitle(title)
        self._evaluator = evaluator
        self._token_groups_map: dict[str, list[str]] = {}
        self._function_groups_map: dict[str, list[str]] = {}
        self._func_help_label = None
        self._status_bar = None
        self._function_group_combo = None
        self._function_data_list = None
        # compatibility / editable template support (safe defaults)
        self._functions_src_ref = functions if isinstance(functions, MutableMapping) else None
        self._function_help_overrides_ref = function_help_overrides if isinstance(function_help_overrides, Mapping) else {}
        self._function_help_map: dict[str, str] = dict(function_help_overrides or {})
        self._allow_edit_templates = bool(allow_edit_templates)
        self._btn_tpl_add = None
        self._btn_tpl_edit = None
        self._btn_tpl_help = None
        self._btn_tpl_del = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(self._lang, "dialog.expression_builder.expression")))
        self.edit = QLineEdit(initial)
        layout.addWidget(self.edit)

        # New layout: no duplicated token list area. Keep only function/object-data panels.
        panels_row = QHBoxLayout()
        self._function_panel = self._build_function_panel(functions or [])
        if self._function_panel is not None:
            panels_row.addWidget(self._function_panel)
        self._object_data_box = self._build_object_data_panel(tokens)
        if self._object_data_box is not None:
            panels_row.addWidget(self._object_data_box)
        if panels_row.count() > 0:
            layout.addLayout(panels_row)

        self._status_bar = QStatusBar(self)
        self._status_bar.setSizeGripEnabled(False)
        self._status_bar.showMessage(tr(self._lang, "dialog.expression_builder.status_ready", "就绪"))
        layout.addWidget(self._status_bar)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        footer = QHBoxLayout()
        self._eval_button = QPushButton(tr(self._lang, "dialog.expression_builder.evaluate"))
        self._eval_label = QLabel(f"{tr(self._lang, 'dialog.expression_builder.value')} --")
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

        self.resize(980, 680)

    # ---- shared insert helpers -------------------------------------------------
    def _insert_text(self, text: str) -> None:
        def is_identifier_path(value: str) -> bool:
            if not value:
                return False
            parts = value.split(".")
            return all(part.isidentifier() for part in parts)

        operators = {"+", "-", "*", "/", "(", ")", ","}
        is_quoted_literal = (len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")))
        has_call_like_syntax = "(" in text or ")" in text
        if text and not is_identifier_path(text) and not text.endswith("(") and text not in operators and not is_quoted_literal and not has_call_like_syntax:
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            self.edit.insert(f'signal("{escaped}")')
        else:
            self.edit.insert(text)
        self.edit.setFocus()
        self._show_status(tr(self._lang, "dialog.expression_builder.status_inserted", "已插入"))

    def _show_status(self, text: str) -> None:
        if self._status_bar is not None:
            self._status_bar.showMessage(text)

    def _group_display_name(self, key: str) -> str:
        raw = str(key or '').strip()
        if not raw:
            return raw
        norm = raw.lower().replace(' ', '_').replace('-', '_')
        return tr(self._lang, f"dialog.expression_builder.group.{norm}", raw)

    def _combo_current_group_key(self, combo: QComboBox) -> str:
        if combo is None:
            return ''
        data = combo.currentData()
        return str(data) if data not in (None, '') else str(combo.currentText())

    # ---- function panel --------------------------------------------------------
    def _build_function_panel(self, functions_src) -> Optional[QGroupBox]:
        groups: dict[str, list[str]] = {}
        if isinstance(functions_src, Mapping):
            for k, vals in functions_src.items():
                key = str(k)
                items = [str(v) for v in (vals or []) if str(v).strip()]
                if items:
                    groups[key] = sorted(set(items))
        else:
            items = [str(v) for v in (functions_src or []) if str(v).strip()]
            if items:
                groups[tr(self._lang, "dialog.expression_builder.functions", "函数")] = sorted(set(items))
        if not groups:
            return None
        self._function_groups_map = groups

        box = QGroupBox(tr(self._lang, "dialog.expression_builder.functions", "函数"))
        root = QVBoxLayout(box)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr(self._lang, "dialog.expression_builder.func_group", "分类")))
        combo = QComboBox(box)
        for g in groups.keys():
            combo.addItem(self._group_display_name(g), g)
        top.addWidget(combo, 1)
        root.addLayout(top)

        lst = QListWidget(box)
        lst.itemDoubleClicked.connect(lambda item: self._insert_selected_object_data())
        lst.currentTextChanged.connect(self._on_function_selected)
        root.addWidget(lst, 1)

        btns = QHBoxLayout()
        btn_insert = QPushButton(tr(self._lang, "dialog.expression_builder.insert_function", "插入函数"), box)
        btn_insert.clicked.connect(self._insert_selected_function)
        btns.addWidget(btn_insert)

        self._btn_tpl_manage = QPushButton(tr(self._lang, "dialog.expression_builder.template_edit_short", "编辑模板"), box)
        self._btn_tpl_manage.clicked.connect(self._edit_templates_batch)
        btns.addWidget(self._btn_tpl_manage)

        self._btn_tpl_add = None
        self._btn_tpl_edit = None
        self._btn_tpl_help = None
        self._btn_tpl_del = None

        btns.addStretch(1)
        root.addLayout(btns)

        combo.currentIndexChanged.connect(self._refresh_function_list)
        combo.currentIndexChanged.connect(lambda *_: self._sync_template_buttons())
        lst.currentItemChanged.connect(lambda *_: self._sync_template_buttons())
        self._function_group_combo = combo
        self._function_data_list = lst
        self._func_help_label = None
        self._refresh_function_list()
        self._sync_template_buttons()
        return box

    def _refresh_function_list(self) -> None:
        if self._function_group_combo is None or self._function_data_list is None:
            return
        group = self._combo_current_group_key(self._function_group_combo)
        items = sorted({str(v) for v in self._function_groups_map.get(group, []) if str(v).strip()})
        self._function_data_list.clear()
        self._function_data_list.addItems(items)
        if items:
            self._function_data_list.setCurrentRow(0)

    def _selected_function_text(self) -> str:
        if self._function_data_list is None:
            return ""
        it = self._function_data_list.currentItem()
        return it.text() if it is not None else ""

    def _insert_selected_function(self) -> None:
        text = self._selected_function_text()
        if text:
            self._insert_text(text)

    def _on_function_selected(self, text: str) -> None:
        msg = self._function_help_message(text)
        self._show_status(msg)

    def _function_help_message(self, text: str) -> str:
        raw = (text or "").strip()
        key = raw[:-1] if raw.endswith("(") else raw
        helps = {
            # curve compare / analysis
            "curve_rms_err": tr(self._lang, "dialog.expression_builder.help.curve_rms_err", 'curve_rms_err("a","b"): 两条曲线差值的 RMS 误差（标量）'),
            "curve_max_abs_err": tr(self._lang, "dialog.expression_builder.help.curve_max_abs_err", 'curve_max_abs_err("a","b"): 两条曲线差值的最大绝对误差（标量）'),
            "curve_diff": tr(self._lang, "dialog.expression_builder.help.curve_diff", 'curve_diff("a","b"): 返回逐点差值序列 (a-b)'),
            "curve_abs_diff": tr(self._lang, "dialog.expression_builder.help.curve_abs_diff", 'curve_abs_diff("a","b"): 返回逐点绝对差值序列'),
            "curve_sq_diff": tr(self._lang, "dialog.expression_builder.help.curve_sq_diff", 'curve_sq_diff("a","b"): 返回逐点平方差序列'),
            "curve_value_at": tr(self._lang, "dialog.expression_builder.help.curve_value_at", 'curve_value_at("a", x): 对曲线 a 在 x 处插值取值（标量）'),
            "curve_monotonic_violation": tr(self._lang, "dialog.expression_builder.help.curve_monotonic_violation", 'curve_monotonic_violation("a"): 单调性违反量（越小越好，标量）'),
            # aggregates / math
            "rms": tr(self._lang, "dialog.expression_builder.help.rms", 'rms(seq): 序列均方根（标量）'),
            "mean": tr(self._lang, "dialog.expression_builder.help.mean", 'mean(seq): 序列平均值（标量）'),
            "max": tr(self._lang, "dialog.expression_builder.help.max", 'max(...): 最大值（标量）'),
            "min": tr(self._lang, "dialog.expression_builder.help.min", 'min(...): 最小值（标量）'),
            "first": tr(self._lang, "dialog.expression_builder.help.first", 'first(seq): 序列首个元素（标量）'),
            "last": tr(self._lang, "dialog.expression_builder.help.last", 'last(seq): 序列最后一个元素（标量）'),
            "abs": tr(self._lang, "dialog.expression_builder.help.abs", 'abs(x): 绝对值'),
            "floor": tr(self._lang, "dialog.expression_builder.help.floor", 'floor(x): 向下取整'),
            "ceil": tr(self._lang, "dialog.expression_builder.help.ceil", 'ceil(x): 向上取整'),
            "round": tr(self._lang, "dialog.expression_builder.help.round", 'round(x): 四舍五入'),
            "sqrt": tr(self._lang, "dialog.expression_builder.help.sqrt", 'sqrt(x): 平方根'),
            "sin": tr(self._lang, "dialog.expression_builder.help.sin", 'sin(x): 正弦'),
            "cos": tr(self._lang, "dialog.expression_builder.help.cos", 'cos(x): 余弦'),
            "tan": tr(self._lang, "dialog.expression_builder.help.tan", 'tan(x): 正切'),
            "asin": tr(self._lang, "dialog.expression_builder.help.asin", 'asin(x): 反正弦'),
            "acos": tr(self._lang, "dialog.expression_builder.help.acos", 'acos(x): 反余弦'),
            "atan": tr(self._lang, "dialog.expression_builder.help.atan", 'atan(x): 反正切'),
            "sinh": tr(self._lang, "dialog.expression_builder.help.sinh", 'sinh(x): 双曲正弦'),
            "cosh": tr(self._lang, "dialog.expression_builder.help.cosh", 'cosh(x): 双曲余弦'),
            "tanh": tr(self._lang, "dialog.expression_builder.help.tanh", 'tanh(x): 双曲正切'),
            "exp": tr(self._lang, "dialog.expression_builder.help.exp", 'exp(x): 指数 e^x'),
            "log": tr(self._lang, "dialog.expression_builder.help.log", 'log(x): 自然对数'),
            "log10": tr(self._lang, "dialog.expression_builder.help.log10", 'log10(x): 常用对数'),
            "pi": tr(self._lang, "dialog.expression_builder.help.pi", 'pi: 圆周率常量'),
            # object signal
            "signal": tr(self._lang, "dialog.expression_builder.help.signal", 'signal("name"): 按名称读取模型/仿真信号（如 signal("Link0.L")）'),
        }
        # explicit overrides (used by optimization/objective templates)
        if raw in self._function_help_map and str(self._function_help_map.get(raw, '')).strip():
            return str(self._function_help_map.get(raw))
        if key in self._function_help_map and str(self._function_help_map.get(key, '')).strip():
            return str(self._function_help_map.get(key))
        if key in helps:
            return helps[key]

        category = ""
        if self._function_group_combo is not None:
            category = (self._function_group_combo.currentText() or "").strip().lower()

        # Template expressions: explain as ready-made snippets
        if raw and (('(' in raw and ')' in raw) or ('+' in raw) or ('-' in raw) or ('*' in raw) or ('/' in raw)):
            return tr(self._lang, "dialog.expression_builder.help.template_expr_inline", '模板表达式：{raw}（可直接插入后再按需修改）').format(raw=raw)

        # Function-like fallback with category-aware hints (avoid blank/incomplete help)
        if raw.endswith('(') or key.isidentifier():
            if key.startswith('curve_'):
                return tr(self._lang, "dialog.expression_builder.help.fallback.curve_fn", '{raw}: 曲线函数。通常使用曲线名字符串作为参数，例如 "io_actual", "io_target"。').format(raw=raw)
            if 'curve' in category:
                return tr(self._lang, "dialog.expression_builder.help.fallback.curve_related", '{raw}: 曲线相关函数。参数通常为曲线名字符串或由曲线函数返回的序列。').format(raw=raw)
            if 'aggregate' in category or key in {'first','last','mean','rms','min','max'}:
                return tr(self._lang, "dialog.expression_builder.help.fallback.aggregate", '{raw}: 聚合函数。输入通常为序列（如 curve_diff(...) 的结果），输出标量。').format(raw=raw)
            if 'math' in category:
                return tr(self._lang, "dialog.expression_builder.help.fallback.math", '{raw}: 数学函数。输入/输出通常为标量。').format(raw=raw)
            if key in {'hard_err_mean','hard_err_max','valid_ratio','curve_err'}:
                return tr(self._lang, "dialog.expression_builder.help.fallback.opt_metric", '{raw}: 优化运行时统计量/中间量，请在优化表达式中使用。').format(raw=raw)
            return tr(self._lang, "dialog.expression_builder.help.fallback.generic_insertable", '{raw}: 可插入到表达式；参数请参考右侧对象数据列表和函数模板。').format(raw=raw)

        return tr(self._lang, "dialog.expression_builder.function_help_generic", "函数帮助：双击或点击“插入函数”插入到表达式。")

    def _current_function_group_name(self) -> str:
        return self._combo_current_group_key(self._function_group_combo) if self._function_group_combo is not None else ""

    def _is_templates_group(self) -> bool:
        return self._current_function_group_name().strip().lower() == "templates"

    def _sync_template_buttons(self) -> None:
        is_tpl = self._is_templates_group()
        if getattr(self, "_btn_tpl_manage", None) is not None:
            self._btn_tpl_manage.setVisible(is_tpl)
            self._btn_tpl_manage.setEnabled(is_tpl)

    def _edit_templates_batch(self) -> None:
        if not self._is_templates_group():
            return
        gname = self._current_function_group_name()
        items = list(self._function_groups_map.get(gname, []))
        dlg = QDialog(self)
        dlg.setWindowTitle(tr(self._lang, "dialog.expression_builder.template_edit", "编辑模板"))
        dlg.resize(900, 520)
        lay = QVBoxLayout(dlg)
        tip = QLabel(tr(self._lang, "dialog.expression_builder.template_batch_tip", "逐行编辑模板表达式与帮助；清空表达式行表示删除。"), dlg)
        lay.addWidget(tip)
        table = QTableWidget(len(items) + 3, 2, dlg)
        table.setHorizontalHeaderLabels([
            tr(self._lang, "dialog.expression_builder.template_expr", "模板表达式"),
            tr(self._lang, "dialog.expression_builder.template_help_text", "帮助说明"),
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        hov = self._function_help_overrides_ref if isinstance(self._function_help_overrides_ref, MutableMapping) else {}
        for r, expr in enumerate(items):
            table.setItem(r, 0, QTableWidgetItem(str(expr)))
            _help_seed = str(hov.get(expr, self._function_help_map.get(expr, ""))).strip()
            if not _help_seed:
                _help_seed = self._function_help_message(str(expr))
            table.setItem(r, 1, QTableWidgetItem(_help_seed))
        hdr = table.horizontalHeader()
        try:
            hdr.setStretchLastSection(True)
            hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        except Exception:
            pass
        lay.addWidget(table, 1)
        row_btns = QHBoxLayout()
        b_add = QPushButton(tr(self._lang, "dialog.expression_builder.template_add_short", "新增模板"), dlg)
        b_del = QPushButton(tr(self._lang, "dialog.expression_builder.template_delete_short", "删除选中"), dlg)
        row_btns.addWidget(b_add)
        row_btns.addWidget(b_del)
        row_btns.addStretch(1)
        lay.addLayout(row_btns)
        def _add_row():
            table.insertRow(table.rowCount())
        def _del_rows():
            rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
            for rr in rows:
                table.removeRow(rr)
        b_add.clicked.connect(_add_row)
        b_del.clicked.connect(_del_rows)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dlg)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        new_items: list[str] = []
        new_help: dict[str, str] = {}
        for r in range(table.rowCount()):
            eitem = table.item(r, 0)
            hitem = table.item(r, 1)
            expr = (eitem.text() if eitem else "").strip()
            help_txt = (hitem.text() if hitem else "").strip()
            if not expr:
                continue
            new_items.append(expr)
            if help_txt:
                new_help[expr] = help_txt
        self._replace_current_group_items(new_items)
        if isinstance(self._function_help_overrides_ref, MutableMapping):
            # clear old template overrides, then apply current rows
            for k in list(self._function_help_overrides_ref.keys()):
                if k in items and k not in new_help:
                    self._function_help_overrides_ref.pop(k, None)
            for k, v in new_help.items():
                self._function_help_overrides_ref[k] = v
        for k, v in new_help.items():
            self._function_help_map[k] = v
        self._show_status(tr(self._lang, "dialog.expression_builder.status_template_updated", "模板已更新"))

    def _replace_current_group_items(self, items: list[str]) -> None:
        g = self._current_function_group_name()
        if not g:
            return
        self._function_groups_map[g] = list(items)
        ref = self._functions_src_ref
        if isinstance(ref, MutableMapping):
            try:
                ref[g] = list(items)
            except Exception:
                pass
        self._refresh_function_list()

    def _build_object_data_panel(self, tokens_src) -> Optional[QGroupBox]:
        if not isinstance(tokens_src, Mapping):
            return None
        groups: dict[str, list[str]] = {}
        for k, vals in tokens_src.items():
            key = str(k)
            items = [str(v) for v in (vals or []) if str(v).strip()]
            if items:
                groups[key] = items
        if not groups:
            return None
        self._token_groups_map = groups

        box = QGroupBox(tr(self._lang, "dialog.expression_builder.object_data", "获取对象数据"))
        root = QVBoxLayout(box)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr(self._lang, "dialog.expression_builder.object_group", "分类")))
        combo = QComboBox(box)
        for g in groups.keys():
            combo.addItem(self._group_display_name(g), g)
        top.addWidget(combo, 1)
        root.addLayout(top)

        lst = QListWidget(box)
        lst.itemDoubleClicked.connect(lambda item: self._insert_selected_object_data())
        root.addWidget(lst, 1)

        btns = QHBoxLayout()
        btn_insert = QPushButton(tr(self._lang, "dialog.expression_builder.insert_object", "插入"), box)
        btn_insert.clicked.connect(self._insert_selected_object_data)
        btns.addWidget(btn_insert)
        btns.addStretch(1)
        root.addLayout(btns)

        combo.currentIndexChanged.connect(self._refresh_object_data_list)
        self._object_group_combo = combo
        self._object_data_list = lst
        self._refresh_object_data_list()
        return box

    def _refresh_object_data_list(self) -> None:
        if self._object_group_combo is None or self._object_data_list is None:
            return
        group = self._combo_current_group_key(self._object_group_combo)
        items = sorted({str(v) for v in self._token_groups_map.get(group, []) if str(v).strip()})
        self._object_data_list.clear()
        self._object_data_list.addItems(items)

    def _selected_object_data_text(self) -> str:
        if self._object_data_list is None:
            return ""
        it = self._object_data_list.currentItem()
        return it.text() if it is not None else ""

    def _insert_selected_object_data(self) -> None:
        text = self._selected_object_data_text()
        if text:
            self._insert_text(text)

    def _on_evaluate_clicked(self) -> None:
        if self._evaluator is None:
            return
        expr = self.edit.text()
        value, err = self._evaluator(expr)
        if err:
            self._eval_label.setText(f"Error: {err}")
            self._eval_label.setStyleSheet("color: #c0392b;")
            self._show_status(f"Error: {err}")
        else:
            self._eval_label.setText(f"Value: {value:.6g}" if value is not None else "Value: --")
            self._eval_label.setStyleSheet("")
            self._show_status(tr(self._lang, "dialog.expression_builder.status_eval_ok", "计算完成"))

    def expression(self) -> str:
        return self.edit.text()
