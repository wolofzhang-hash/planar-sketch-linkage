# -*- coding: utf-8 -*-
"""Optimization worker for random-search evaluation."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from .expression import evaluate_expression
from .parameters import ParameterRegistry
from .headless_sim import simulate_case


@dataclass
class DesignVariable:
    name: str
    lower: float
    upper: float
    enabled: bool = True


@dataclass
class ObjectiveSpec:
    expression: str
    direction: str
    enabled: bool = True


@dataclass
class ConstraintSpec:
    expression: str
    comparator: str
    limit: float
    enabled: bool = True


def _signals_from_frames(frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    signals: Dict[str, List[float]] = {}
    for rec in frames:
        for key, val in rec.items():
            if key in ("solver", "time"):
                continue
            if val is None:
                continue
            signals.setdefault(key, []).append(float(val))
    signals_map: Dict[str, Any] = dict(signals)

    for key, vals in list(signals.items()):
        if key.lower().startswith("load "):
            parts = key.replace("load ", "load.").replace(" ", ".")
            signals_map[parts] = vals
    return signals_map


def _recompute_snapshot_from_parameters(snapshot: Dict[str, Any]) -> None:
    registry = ParameterRegistry()
    registry.load_list(list(snapshot.get("parameters", []) or []))

    for p in snapshot.get("points", []) or []:
        for key_num, key_expr in (("x", "x_expr"), ("y", "y_expr")):
            expr = (p.get(key_expr) or "").strip()
            if not expr:
                continue
            val, err = registry.eval_expr(expr)
            if err is None and val is not None:
                p[key_num] = float(val)

    for l in snapshot.get("links", []) or []:
        if bool(l.get("ref", False)):
            continue
        expr = (l.get("L_expr") or "").strip()
        if not expr:
            continue
        val, err = registry.eval_expr(expr)
        if err is None and val is not None:
            l["L"] = float(val)

    for a in snapshot.get("angles", []) or []:
        expr = (a.get("deg_expr") or "").strip()
        if not expr:
            continue
        val, err = registry.eval_expr(expr)
        if err is None and val is not None:
            a["deg"] = float(val)


def _apply_design_vars(model_snapshot: Dict[str, Any], variables: Dict[str, float]) -> Dict[str, Any]:
    snapshot = copy.deepcopy(model_snapshot)
    point_vars: Dict[str, float] = {}
    link_vars: Dict[int, float] = {}
    param_vars: Dict[str, float] = {}

    for key, val in variables.items():
        if key.startswith("P") and "." in key:
            point_vars[key] = val
            continue
        if key.startswith("Param."):
            param_name = key[len("Param.") :]
            if param_name:
                param_vars[param_name] = val
            continue
        if key.startswith("Link") and key.endswith(".L"):
            lid_str = key[len("Link") : -len(".L")]
            try:
                lid = int(lid_str)
            except Exception:
                continue
            link_vars[lid] = float(val)

    if param_vars:
        params_list = list(snapshot.get("parameters", []) or [])
        existing = {str(p.get("name", "")): p for p in params_list if isinstance(p, dict)}
        for name, val in param_vars.items():
            if name in existing:
                existing[name]["value"] = float(val)
            else:
                params_list.append({"name": name, "value": float(val)})
        snapshot["parameters"] = params_list
        _recompute_snapshot_from_parameters(snapshot)

    points = snapshot.get("points", []) or []
    for p in points:
        pid = p.get("id")
        if pid is None:
            continue
        for axis in ("x", "y"):
            key = f"P{pid}.{axis}"
            if key in point_vars:
                p[axis] = float(point_vars[key])

    links = snapshot.get("links", []) or []
    for l in links:
        lid = l.get("id")
        if lid in link_vars:
            l["L"] = float(link_vars[lid])
    return snapshot


class OptimizationWorker(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        model_snapshot: Dict[str, Any],
        case_spec: Dict[str, Any],
        variables: List[DesignVariable],
        objectives: List[ObjectiveSpec],
        constraints: List[ConstraintSpec],
        evals: int,
        seed: Optional[int],
    ):
        super().__init__()
        self.model_snapshot = model_snapshot
        self.case_spec = case_spec
        self.variables = variables
        self.objectives = objectives
        self.constraints = constraints
        self.evals = max(1, int(evals))
        self.seed = seed
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            rng = random.Random(self.seed)
            best = {"score": float("inf"), "vars": {}, "objective": None, "constraints": None}
            for idx in range(self.evals):
                if self._stop:
                    break
                candidate = {}
                for var in self.variables:
                    if not var.enabled:
                        continue
                    candidate[var.name] = rng.uniform(var.lower, var.upper)

                snapshot = _apply_design_vars(self.model_snapshot, candidate)
                frames, summary, status = simulate_case(snapshot, self.case_spec)
                signals = _signals_from_frames(frames)

                obj_vals = []
                obj_score = 0.0
                for obj in self.objectives:
                    if not obj.enabled:
                        continue
                    val, err = evaluate_expression(obj.expression, signals)
                    if err:
                        val = 1e9
                    if obj.direction == "max":
                        val = -val
                    obj_vals.append(val)
                base_score = obj_vals[0] if obj_vals else 0.0

                violation = 0.0
                con_vals = []
                for con in self.constraints:
                    if not con.enabled:
                        continue
                    val, err = evaluate_expression(con.expression, signals)
                    if err:
                        violation += 1e6
                        con_vals.append(val)
                        continue
                    con_vals.append(val)
                    if con.comparator == "<=":
                        violation += max(0.0, val - con.limit)
                    else:
                        violation += max(0.0, con.limit - val)

                penalty = violation * 1e6
                obj_score = base_score + penalty

                if obj_score < best["score"]:
                    best = {
                        "score": obj_score,
                        "vars": candidate,
                        "objective": base_score,
                        "constraints": con_vals,
                        "summary": summary,
                        "status": status,
                    }

                self.progress.emit({"index": idx + 1, "best": best})

            self.finished.emit(best)
        except Exception as exc:
            self.failed.emit(str(exc))
