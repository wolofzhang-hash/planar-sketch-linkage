# -*- coding: utf-8 -*-
"""Shared expression evaluation helpers.

This module centralizes expression evaluation so parameter and signal expressions
use consistent parsing/error handling while preserving their existing behavior.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import sympy as sp

from .expression import eval_signal_expression as eval_signal_expression_impl


_ALLOWED_PARAM_FUNCS: Dict[str, Any] = {
    # Basic math
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "min": sp.Min,
    "max": sp.Max,
    "pi": sp.pi,
    "E": sp.E,
}


def eval_param_expression(expr: str, params: Dict[str, float]) -> Tuple[Optional[float], Optional[str]]:
    """Evaluate a parameter expression string using SymPy.

    Returns (value, error_message). If evaluation fails, value is None.
    """
    expr = (expr or "").strip()
    if not expr:
        return None, "Empty expression"

    locals_map: Dict[str, Any] = dict(_ALLOWED_PARAM_FUNCS)
    for name in params.keys():
        locals_map[name] = sp.Symbol(name)

    try:
        parsed = sp.sympify(expr, locals=locals_map)
    except Exception as ex:
        return None, f"Parse error: {ex}"

    free = {str(s) for s in getattr(parsed, "free_symbols", set())}
    unknown = sorted([s for s in free if s not in params])
    if unknown:
        return None, f"Unknown symbol(s): {', '.join(unknown)}"

    try:
        subs = {sp.Symbol(k): float(v) for k, v in params.items()}
        val = float(parsed.evalf(subs=subs))
        if val != val:  # NaN
            return None, "Expression evaluated to NaN"
        return val, None
    except Exception as ex:
        return None, f"Eval error: {ex}"


def eval_signal_expression(expr: str, signals: Dict[str, Any]) -> Tuple[float, Optional[str]]:
    """Evaluate signal expressions (optimization/analysis)."""
    return eval_signal_expression_impl(expr, signals)
