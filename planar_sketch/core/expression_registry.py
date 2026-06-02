from __future__ import annotations

from typing import Any, Dict, List

import sympy as sp

PARAMETER_ALLOWED_FUNCTIONS: Dict[str, Any] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "exp": sp.exp,
    "log": sp.log,
    "log10": lambda x: sp.log(x, 10),
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "floor": sp.floor,
    "ceil": sp.ceiling,
    "round": lambda x: sp.Integer(sp.floor(x + sp.Rational(1, 2))),
    "min": sp.Min,
    "max": sp.Max,
    "pi": sp.pi,
    "E": sp.E,
}

PARAMETER_FUNCTIONS: List[str] = [
    "sin(", "cos(", "tan(", "asin(", "acos(", "atan(",
    "sinh(", "cosh(", "tanh(",
    "exp(", "log(", "log10(", "sqrt(",
    "abs(", "floor(", "ceil(", "round(",
    "min(", "max(", "pi", "E",
]
