# -*- coding: utf-8 -*-
"""Safe expression evaluation for optimization objectives/constraints."""

from __future__ import annotations

import ast
import math
from typing import Any, Dict, Iterable, Tuple


class ExpressionError(ValueError):
    pass


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        raise ExpressionError("mean() requires at least one value")
    return sum(vals) / float(len(vals))


def _rms(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        raise ExpressionError("rms() requires at least one value")
    return math.sqrt(sum(v * v for v in vals) / float(len(vals)))


def _first(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        raise ExpressionError("first() requires at least one value")
    return float(vals[0])


def _last(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        raise ExpressionError("last() requires at least one value")
    return float(vals[-1])


_ALLOWED_FUNCS = {
    "max": max,
    "min": min,
    "mean": _mean,
    "rms": _rms,
    "abs": abs,
    "first": _first,
    "last": _last,
}


def _attr_to_path(node: ast.AST) -> str:
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        raise ExpressionError("Invalid attribute reference")
    return ".".join(reversed(parts))


class ExpressionEvaluator(ast.NodeVisitor):
    def __init__(self, signals: Dict[str, Any]):
        self.signals = signals

    def evaluate(self, expr: str) -> float:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"Parse error: {exc}") from exc
        return self.visit(tree.body)

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(left, list) or isinstance(right, list):
            raise ExpressionError("Use aggregate functions for signal arrays")
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        raise ExpressionError("Unsupported operator")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        val = self.visit(node.operand)
        if isinstance(val, list):
            raise ExpressionError("Use aggregate functions for signal arrays")
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ExpressionError("Unsupported unary operator")

    def visit_Call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("Only simple function calls are allowed")
        name = node.func.id
        if name not in _ALLOWED_FUNCS:
            raise ExpressionError(f"Function not allowed: {name}")
        if len(node.args) != 1:
            raise ExpressionError(f"{name}() expects one argument")
        arg = self.visit(node.args[0])
        func = _ALLOWED_FUNCS[name]
        if isinstance(arg, list):
            return float(func(arg))
        if name in ("mean", "rms", "max", "min", "first", "last"):
            return float(func([arg]))
        return float(func(arg))

    def visit_Name(self, node: ast.Name) -> Any:
        key = node.id
        if key not in self.signals:
            raise ExpressionError(f"Unknown signal: {key}")
        return self.signals[key]

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        key = _attr_to_path(node)
        if key not in self.signals:
            raise ExpressionError(f"Unknown signal: {key}")
        return self.signals[key]

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ExpressionError("Only numeric constants are allowed")

    def generic_visit(self, node: ast.AST) -> float:
        raise ExpressionError(f"Unsupported expression: {type(node).__name__}")


def evaluate_expression(expr: str, signals: Dict[str, Any]) -> Tuple[float, str | None]:
    expr = (expr or "").strip()
    if not expr:
        return 0.0, "Empty expression"
    evaluator = ExpressionEvaluator(signals)
    try:
        return evaluator.evaluate(expr), None
    except ExpressionError as exc:
        return 0.0, str(exc)
