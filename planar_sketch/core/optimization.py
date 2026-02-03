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
    case_ids: Optional[List[str]] = None


@dataclass
class ObjectiveSpec:
    expression: str
    direction: str
    enabled: bool = True
    case_ids: Optional[List[str]] = None


@dataclass
class ConstraintSpec:
    expression: str
    comparator: str
    limit: float
    enabled: bool = True
    case_ids: Optional[List[str]] = None


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


def model_variable_signals(snapshot: Dict[str, Any]) -> Dict[str, float]:
    signals: Dict[str, float] = {}
    for point in snapshot.get("points", []) or []:
        pid = point.get("id")
        if pid is None:
            continue
        signals[f"P{pid}.x"] = float(point.get("x", 0.0))
        signals[f"P{pid}.y"] = float(point.get("y", 0.0))
    for link in snapshot.get("links", []) or []:
        lid = link.get("id")
        if lid is None:
            continue
        signals[f"Link{lid}.L"] = float(link.get("L", 0.0))
    for param in snapshot.get("parameters", []) or []:
        name = str(param.get("name", "")).strip()
        if not name:
            continue
        signals[f"Param.{name}"] = float(param.get("value", 0.0))
    return signals


def build_signals(frames: List[Dict[str, Any]], snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signals = _signals_from_frames(frames)
    if snapshot:
        signals.update(model_variable_signals(snapshot))
    return signals


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
        case_specs: Dict[str, Dict[str, Any]],
        variables: List[DesignVariable],
        objectives: List[ObjectiveSpec],
        constraints: List[ConstraintSpec],
        evals: int,
        seed: Optional[int],
    ):
        super().__init__()
        self.model_snapshot = model_snapshot
        self.case_specs = case_specs
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
            all_case_ids = list(self.case_specs.keys())
            if not all_case_ids:
                self.failed.emit("No cases available.")
                return
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
                required_cases: set[str] = set()
                for obj in self.objectives:
                    if not obj.enabled:
                        continue
                    required_cases.update(obj.case_ids or all_case_ids)
                for con in self.constraints:
                    if not con.enabled:
                        continue
                    required_cases.update(con.case_ids or all_case_ids)
                if not required_cases:
                    required_cases.update(all_case_ids)

                signals_by_case: Dict[str, Dict[str, Any]] = {}
                summaries: Dict[str, Any] = {}
                statuses: Dict[str, Any] = {}
                for case_id in required_cases:
                    case_spec = self.case_specs.get(case_id)
                    if not case_spec:
                        continue
                    frames, summary, status = simulate_case(snapshot, case_spec)
                    signals_by_case[case_id] = build_signals(frames, snapshot)
                    summaries[case_id] = summary
                    statuses[case_id] = status

                obj_vals = []
                obj_score = 0.0
                for obj in self.objectives:
                    if not obj.enabled:
                        continue
                    case_vals = []
                    for case_id in obj.case_ids or all_case_ids:
                        signals = signals_by_case.get(case_id)
                        if not signals:
                            continue
                        val, err = evaluate_expression(obj.expression, signals)
                        if err:
                            val = 1e9
                        if obj.direction == "max":
                            val = -val
                        case_vals.append(val)
                    if case_vals:
                        obj_vals.append(sum(case_vals) / float(len(case_vals)))
                base_score = obj_vals[0] if obj_vals else 0.0

                violation = 0.0
                con_vals = []
                for con in self.constraints:
                    if not con.enabled:
                        continue
                    for case_id in con.case_ids or all_case_ids:
                        signals = signals_by_case.get(case_id)
                        if not signals:
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
                        "summary": summaries,
                        "status": statuses,
                    }

                self.progress.emit({"index": idx + 1, "best": best})

            self.finished.emit(best)
        except Exception as exc:
            self.failed.emit(str(exc))
