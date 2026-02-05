# -*- coding: utf-8 -*-
"""Parameter system + safe expression evaluation.

This module provides a small, explicit "parameter registry" that supports
assigning expressions (strings) to numeric fields in the sketch.

Implementation notes
--------------------
- We avoid Python ``eval``. Instead we use SymPy to parse and evaluate.
- Only a conservative set of functions/constants are exposed.
- Unknown symbols cause evaluation errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple

from .expression_service import eval_param_expression


def _is_valid_param_name(name: str) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(ch.isalnum() or ch == "_" for ch in name)


@dataclass
class ParameterRegistry:
    """A simple parameter store with expression evaluation."""

    params: Dict[str, float] = field(default_factory=dict)

    def set_param(self, name: str, value: float):
        if not _is_valid_param_name(name):
            raise ValueError(f"Invalid parameter name: {name!r}")
        self.params[str(name).strip()] = float(value)

    def delete_param(self, name: str):
        self.params.pop(name, None)

    def rename_param(self, old: str, new: str):
        if old not in self.params:
            return
        if not _is_valid_param_name(new):
            raise ValueError(f"Invalid parameter name: {new!r}")
        v = self.params.pop(old)
        self.params[str(new).strip()] = float(v)

    def to_list(self) -> list[dict[str, Any]]:
        return [{"name": k, "value": float(v)} for k, v in sorted(self.params.items(), key=lambda kv: kv[0])]

    def load_list(self, items: list[dict[str, Any]]):
        self.params.clear()
        for it in items or []:
            try:
                name = str(it.get("name", "")).strip()
                val = float(it.get("value", 0.0))
                if _is_valid_param_name(name):
                    self.params[name] = val
            except Exception:
                continue

    def eval_expr(self, expr: str) -> Tuple[Optional[float], Optional[str]]:
        """Evaluate an expression string.

        Returns (value, error_message). If evaluation fails, value is None.
        """
        return eval_param_expression(expr, self.params)
