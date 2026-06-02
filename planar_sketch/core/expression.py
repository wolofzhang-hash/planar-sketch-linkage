# -*- coding: utf-8 -*-
"""Safe expression evaluation for optimization objectives/constraints.

Supports scalar signals and named-curve helper functions such as:
    curve_rms_err("io_actual", "io_target")
    curve_max_abs_err("io_actual", "io_target")
    curve_value_at("io_actual", 45)
    curve_monotonic_violation("io_actual")

Named curves are provided through signals using aliases:
    curve__x__<name>, curve__y__<name>
"""

from __future__ import annotations

import ast
import math
from typing import Any, Dict, Iterable, List, Tuple


class ExpressionError(ValueError):
    pass


def _mean(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if not vals:
        raise ExpressionError("mean() requires at least one value")
    return sum(vals) / float(len(vals))


def _rms(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if not vals:
        raise ExpressionError("rms() requires at least one value")
    return math.sqrt(sum(v * v for v in vals) / float(len(vals)))


def _first(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if not vals:
        raise ExpressionError("first() requires at least one value")
    return float(vals[0])


def _last(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if not vals:
        raise ExpressionError("last() requires at least one value")
    return float(vals[-1])


def _linear_interp(xs: List[float], ys: List[float], xq: float) -> float:
    if not xs or not ys or len(xs) != len(ys):
        raise ExpressionError("Invalid curve data")
    if len(xs) == 1:
        return float(ys[0])
    if xq <= xs[0]:
        return float(ys[0])
    if xq >= xs[-1]:
        return float(ys[-1])
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= xq:
            lo = mid
        else:
            hi = mid
    x0, x1 = float(xs[lo]), float(xs[hi])
    y0, y1 = float(ys[lo]), float(ys[hi])
    if abs(x1 - x0) < 1e-12:
        return y0
    t = (float(xq) - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))


def _ensure_float_list(v: Any, *, name: str) -> List[float]:
    if not isinstance(v, (list, tuple)):
        raise ExpressionError(f"{name} is not a numeric array")
    out: List[float] = []
    for it in v:
        try:
            out.append(float(it))
        except Exception as ex:
            raise ExpressionError(f"{name} contains non-numeric value") from ex
    return out


def _get_named_curve(signals: Dict[str, Any], curve_name: str) -> Tuple[List[float], List[float]]:
    name = str(curve_name or "").strip()
    if not name:
        raise ExpressionError("Curve name is empty")

    # v1 explicit aliases: curve__x__<name>, curve__y__<name>
    x_key = f"curve__x__{name}"
    y_key = f"curve__y__{name}"
    if x_key in signals and y_key in signals:
        xs = _ensure_float_list(signals[x_key], name=x_key)
        ys = _ensure_float_list(signals[y_key], name=y_key)
        if len(xs) != len(ys) or len(xs) < 1:
            raise ExpressionError(f"Invalid curve lengths for {name}")
        return xs, ys

    # Fallbacks for legacy names.
    if name in ("io_actual", "curve_actual"):
        xs = _ensure_float_list(signals.get("input_deg"), name="input_deg")
        ys = _ensure_float_list(signals.get("output_deg"), name="output_deg")
        if len(xs) != len(ys):
            raise ExpressionError("input_deg/output_deg length mismatch")
        return xs, ys
    if name in ("io_target", "curve_target"):
        xs = _ensure_float_list(signals.get("input_deg"), name="input_deg")
        ys = _ensure_float_list(signals.get("curve_target"), name="curve_target")
        if len(xs) != len(ys):
            raise ExpressionError("input_deg/curve_target length mismatch")
        return xs, ys

    # Generic y-only fallback: signal array + common x axis.
    if name in signals and isinstance(signals.get(name), (list, tuple)):
        ys = _ensure_float_list(signals.get(name), name=name)
        x_guess = None
        for k in ("input_deg", "time", "s"):
            if isinstance(signals.get(k), (list, tuple)) and len(signals[k]) == len(ys):
                x_guess = _ensure_float_list(signals[k], name=k)
                break
        if x_guess is None:
            x_guess = [float(i) for i in range(len(ys))]
        return x_guess, ys

    raise ExpressionError(f"Unknown curve: {name}")


def _curve_align_diff(signals: Dict[str, Any], a_name: str, b_name: str) -> List[float]:
    ax, ay = _get_named_curve(signals, a_name)
    bx, by = _get_named_curve(signals, b_name)
    if len(ax) < 1 or len(bx) < 1:
        raise ExpressionError("Empty curve")
    # intersection_interp_on_a_grid (v1)
    lo = max(min(ax), min(bx))
    hi = min(max(ax), max(bx))
    grid_idx = [i for i, xv in enumerate(ax) if lo <= xv <= hi]
    if not grid_idx:
        raise ExpressionError("Curve domains do not overlap")
    dif: List[float] = []
    for i in grid_idx:
        xv = float(ax[i])
        av = float(ay[i])
        bv = _linear_interp(bx, by, xv)
        dif.append(av - bv)
    if len(dif) < 1:
        raise ExpressionError("Curve comparison has no samples")
    return dif


def _curve_value_at(signals: Dict[str, Any], name: str, xq: float) -> float:
    xs, ys = _get_named_curve(signals, name)
    return _linear_interp(xs, ys, float(xq))


def _curve_monotonic_violation(signals: Dict[str, Any], name: str) -> float:
    _xs, ys = _get_named_curve(signals, name)
    if len(ys) < 2:
        return 0.0
    vio = 0.0
    prev = float(ys[0])
    for y in ys[1:]:
        y = float(y)
        dy = y - prev
        if dy < 0.0:
            vio += -dy
        prev = y
    return float(vio)


_ALLOWED_SIMPLE_FUNCS = {
    "max": max,
    "min": min,
    "mean": _mean,
    "rms": _rms,
    "abs": abs,
    "first": _first,
    "last": _last,
}


CURVE_FUNC_NAMES = {
    "curve_diff",
    "curve_abs_diff",
    "curve_sq_diff",
    "curve_rms_err",
    "curve_max_abs_err",
    "curve_mae",
    "curve_value_at",
    "curve_monotonic_violation",
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
        result = self.visit(tree.body)
        if isinstance(result, (list, tuple)):
            raise ExpressionError("Use aggregate functions for signal arrays")
        if isinstance(result, str):
            raise ExpressionError("Expression must evaluate to a number")
        return float(result)

    def _ensure_scalar(self, v: Any) -> float:
        if isinstance(v, list):
            raise ExpressionError("Use aggregate functions for signal arrays")
        if isinstance(v, str):
            raise ExpressionError("String value cannot be used in arithmetic")
        return float(v)

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self._ensure_scalar(self.visit(node.left))
        right = self._ensure_scalar(self.visit(node.right))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise ExpressionError("Unsupported operator")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        val = self._ensure_scalar(self.visit(node.operand))
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ExpressionError("Unsupported unary operator")

    def _dispatch_curve_func(self, name: str, args: List[Any]) -> Any:
        # Backward-compatible no-arg forms map to io_actual/io_target.
        if name in ("curve_rms_err", "curve_max_abs_err", "curve_mae", "curve_diff", "curve_abs_diff", "curve_sq_diff") and len(args) == 0:
            args = ["io_actual", "io_target"]

        if name in ("curve_diff", "curve_abs_diff", "curve_sq_diff", "curve_rms_err", "curve_max_abs_err", "curve_mae"):
            if len(args) != 2 or not all(isinstance(a, str) for a in args):
                raise ExpressionError(f"{name}() expects two curve names")
            dif = _curve_align_diff(self.signals, args[0], args[1])
            if name == "curve_diff":
                return dif
            if name == "curve_abs_diff":
                return [abs(v) for v in dif]
            if name == "curve_sq_diff":
                return [v * v for v in dif]
            if name == "curve_rms_err":
                return _rms(dif)
            if name == "curve_max_abs_err":
                return max(abs(v) for v in dif) if dif else 0.0
            if name == "curve_mae":
                return _mean(abs(v) for v in dif)

        if name == "curve_value_at":
            if len(args) != 2 or not isinstance(args[0], str):
                raise ExpressionError("curve_value_at() expects (curve_name, x)")
            return _curve_value_at(self.signals, args[0], self._ensure_scalar(args[1]))

        if name == "curve_monotonic_violation":
            if len(args) != 1 or not isinstance(args[0], str):
                raise ExpressionError("curve_monotonic_violation() expects one curve name")
            return _curve_monotonic_violation(self.signals, args[0])

        raise ExpressionError(f"Function not allowed: {name}")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("Only simple function calls are allowed")
        name = node.func.id
        if name == "signal":
            if len(node.args) != 1:
                raise ExpressionError("signal() expects one argument")
            key_node = node.args[0]
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                key = key_node.value
            elif isinstance(key_node, ast.Name):
                key = key_node.id
            elif isinstance(key_node, ast.Attribute):
                key = _attr_to_path(key_node)
            else:
                raise ExpressionError("signal() expects a string or signal name")
            if key not in self.signals:
                raise ExpressionError(f"Unknown signal: {key}")
            return self.signals[key]

        if name in CURVE_FUNC_NAMES:
            args = [self.visit(a) for a in node.args]
            return self._dispatch_curve_func(name, args)

        if name not in _ALLOWED_SIMPLE_FUNCS:
            raise ExpressionError(f"Function not allowed: {name}")
        if len(node.args) != 1:
            raise ExpressionError(f"{name}() expects one argument")
        arg = self.visit(node.args[0])
        func = _ALLOWED_SIMPLE_FUNCS[name]
        if isinstance(arg, list):
            return float(func(arg))
        if isinstance(arg, str):
            raise ExpressionError(f"{name}() does not accept string arguments")
        if name in ("mean", "rms", "max", "min", "first", "last"):
            return float(func([float(arg)]))
        return float(func(float(arg)))

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

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node.value, str):
            return node.value
        raise ExpressionError("Only numeric and string constants are allowed")

    def generic_visit(self, node: ast.AST) -> float:
        raise ExpressionError(f"Unsupported expression: {type(node).__name__}")


def eval_signal_expression(expr: str, signals: Dict[str, Any]) -> Tuple[float, str | None]:
    expr = (expr or "").strip()
    if not expr:
        return 0.0, "Empty expression"
    evaluator = ExpressionEvaluator(signals)
    try:
        return evaluator.evaluate(expr), None
    except ExpressionError as exc:
        return 0.0, str(exc)


def evaluate_expression(expr: str, signals: Dict[str, Any]) -> Tuple[float, str | None]:
    return eval_signal_expression(expr, signals)
