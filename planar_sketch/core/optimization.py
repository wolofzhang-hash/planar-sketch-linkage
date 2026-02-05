# -*- coding: utf-8 -*-
"""Optimization worker for random-search evaluation."""

from __future__ import annotations

import copy
import json
import os
import random
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from .expression_service import eval_signal_expression
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
    for pl in snapshot.get("point_lines", []) or []:
        plid = pl.get("id")
        if plid is None:
            continue
        if "s" in pl:
            signals[f"PointLine{plid}.s"] = float(pl.get("s", 0.0))
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

    for pl in snapshot.get("point_lines", []) or []:
        expr = (pl.get("s_expr") or "").strip()
        if not expr:
            continue
        val, err = registry.eval_expr(expr)
        if err is None and val is not None:
            pl["s"] = float(val)


def _update_link_constraints(
    snapshot: Dict[str, Any],
    link_id: int,
    new_length: float,
    warnings: Optional[List[str]] = None,
) -> None:
    constraints = snapshot.get("constraints")
    if not isinstance(constraints, list):
        return

    matched = False
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        c_type = str(constraint.get("type", "")).lower()
        if c_type not in ("length", "link_length", "link"):
            continue
        target_id = constraint.get("id", constraint.get("link_id"))
        try:
            target_id = int(target_id)
        except Exception:
            continue
        if target_id != link_id:
            continue
        if constraint.get("enabled", True) is False:
            continue
        constraint["value"] = float(new_length)
        matched = True

    if not matched and warnings is not None:
        warnings.append(f"length constraint not found for Link{link_id}.L")


def _apply_design_vars(
    model_snapshot: Dict[str, Any],
    variables: Dict[str, float],
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    snapshot = copy.deepcopy(model_snapshot)
    point_vars: Dict[str, float] = {}
    link_vars: Dict[int, float] = {}
    line_vars: Dict[int, float] = {}
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
            continue
        if key.startswith("PointLine") and key.endswith(".s"):
            plid_str = key[len("PointLine") : -len(".s")]
            try:
                plid = int(plid_str)
            except Exception:
                continue
            line_vars[plid] = float(val)

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
            if l.get("ref", False):
                continue
            l["L"] = float(link_vars[lid])
    for lid, new_length in link_vars.items():
        _update_link_constraints(snapshot, lid, new_length, warnings)
    if line_vars:
        for pl in snapshot.get("point_lines", []) or []:
            plid = pl.get("id")
            if plid in line_vars:
                pl["s"] = float(line_vars[plid])
    return snapshot


class _OptimizationDebugLogger:
    def __init__(self, enabled: bool, log_path: Optional[str]) -> None:
        self.enabled = bool(enabled)
        self.log_path = log_path
        self._handle = None
        if not self.enabled:
            return
        if not self.log_path:
            self.log_path = os.path.join(os.getcwd(), "logs", "optimization_debug.log")
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        self._handle = open(self.log_path, "a", encoding="utf-8")

    def log(self, payload: Dict[str, Any]) -> None:
        if not self._handle:
            return
        try:
            self._handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._handle.flush()
        except Exception:
            self.enabled = False
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None

    def close(self) -> None:
        if self._handle:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None


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
        enable_debug_log: bool = False,
        debug_log_path: Optional[str] = None,
    ):
        super().__init__()
        self.model_snapshot = model_snapshot
        self.case_specs = case_specs
        self.variables = variables
        self.objectives = objectives
        self.constraints = constraints
        self.evals = max(1, int(evals))
        self.seed = seed
        self.enable_debug_log = enable_debug_log
        self.debug_log_path = debug_log_path
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        logger = _OptimizationDebugLogger(self.enable_debug_log, self.debug_log_path)
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

                apply_warnings: List[str] = []
                snapshot = _apply_design_vars(self.model_snapshot, candidate, apply_warnings)
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
                obj_display_vals = []
                obj_score = 0.0
                for obj in self.objectives:
                    if not obj.enabled:
                        continue
                    case_vals = []
                    case_display_vals = []
                    for case_id in obj.case_ids or all_case_ids:
                        signals = signals_by_case.get(case_id)
                        if not signals:
                            continue
                        val, err = eval_signal_expression(obj.expression, signals)
                        if err:
                            val = 1e9
                            score_val = 1e9
                        else:
                            score_val = -val if obj.direction == "max" else val
                        case_vals.append(score_val)
                        case_display_vals.append(val)
                    if case_vals:
                        obj_vals.append(sum(case_vals) / float(len(case_vals)))
                    if case_display_vals:
                        obj_display_vals.append(sum(case_display_vals) / float(len(case_display_vals)))
                base_score = obj_vals[0] if obj_vals else 0.0
                base_display = obj_display_vals[0] if obj_display_vals else 0.0

                violation = 0.0
                con_vals = []
                for con in self.constraints:
                    if not con.enabled:
                        continue
                    for case_id in con.case_ids or all_case_ids:
                        signals = signals_by_case.get(case_id)
                        if not signals:
                            continue
                        val, err = eval_signal_expression(con.expression, signals)
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
                        "objective": base_display,
                        "constraints": con_vals,
                        "summary": summaries,
                        "status": statuses,
                    }

                status_list = []
                overall_success = True
                for case_id in required_cases:
                    status = statuses.get(case_id, {})
                    status_list.append({"case_id": case_id, "status": status})
                    if status and not status.get("success", True):
                        overall_success = False
                log_record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "eval_index": idx + 1,
                    "case_ids": sorted(required_cases),
                    "cases": status_list,
                    "design_vars": candidate,
                    "objective_value": base_display,
                    "objective_score": obj_score,
                    "penalty": penalty,
                    "constraint_violation": violation,
                    "solver_status": "success" if overall_success else "fail",
                }
                if apply_warnings:
                    log_record["warnings"] = apply_warnings
                logger.log(log_record)
                self.progress.emit({"index": idx + 1, "best": best})

            self.finished.emit(best)
        except Exception as exc:
            logger.log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "eval_index": None,
                    "design_vars": None,
                    "objective_value": None,
                    "solver_status": "fail",
                    "error": str(exc).splitlines()[0] if str(exc) else "unknown_error",
                }
            )
            self.failed.emit(str(exc))
        finally:
            logger.close()
