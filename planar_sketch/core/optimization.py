# -*- coding: utf-8 -*-
"""Optimization worker for random-search evaluation."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from .expression import evaluate_expression
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


def _apply_design_vars(model_snapshot: Dict[str, Any], variables: Dict[str, float]) -> Dict[str, Any]:
    snapshot = copy.deepcopy(model_snapshot)
    points = snapshot.get("points", []) or []
    for p in points:
        pid = p.get("id")
        if pid is None:
            continue
        for axis in ("x", "y"):
            key = f"P{pid}.{axis}"
            if key in variables:
                p[axis] = float(variables[key])
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
