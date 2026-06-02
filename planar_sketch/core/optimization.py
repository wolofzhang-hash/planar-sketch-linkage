# -*- coding: utf-8 -*-
"""Optimization worker for design optimization (DE or random-search)."""

from __future__ import annotations

import copy
import json
import os
import random

try:
    from scipy.optimize import differential_evolution
except Exception:  # pragma: no cover
    differential_evolution = None
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
    """Convert headless simulation frames into an expression-friendly signal map.

    Some records may include vector-valued signals (e.g. curve error arrays). Those
    must be kept as lists so expressions like rms(curve_err) / max(curve_abs_err)
    can be evaluated. Scalar signals are aggregated across frames as a list of
    floats.
    """

    signals: Dict[str, List[float]] = {}
    signals_map: Dict[str, Any] = {}

    for rec in frames:
        for key, val in rec.items():
            if key in ("solver", "time"):
                continue
            if val is None:
                continue

            # Vector-valued signals: keep as list (common for curve-related signals).
            if isinstance(val, (list, tuple)):
                try:
                    signals_map[key] = [float(x) for x in val]
                except Exception:
                    signals_map[key] = list(val)
                continue

            # Scalar signals: collect across frames.
            try:
                fval = float(val)
            except Exception:
                continue
            signals.setdefault(key, []).append(fval)

    # Scalar lists
    signals_map.update(dict(signals))

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


def _linear_interp(xs: List[float], ys: List[float], xq: float) -> float:
    if not xs:
        return 0.0
    if len(xs) == 1:
        return float(ys[0])
    if xq <= xs[0]:
        return float(ys[0])
    if xq >= xs[-1]:
        return float(ys[-1])
    # Find interval (xs assumed sorted)
    lo = 0
    hi = len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= xq:
            lo = mid
        else:
            hi = mid
    x0, x1 = xs[lo], xs[hi]
    y0, y1 = ys[lo], ys[hi]
    if abs(x1 - x0) < 1e-12:
        return float(y0)
    t = (xq - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))


def add_curve_target_signals(signals: Dict[str, Any], case_spec: Dict[str, Any]) -> None:
    """Augment signals with curve residuals when case_spec includes a curve_target.

    Adds:
      - curve_target: list[float]
      - curve_err: list[float] = output - target
      - curve_abs_err: list[float]
    """
    if not isinstance(case_spec, dict):
        return
    ct = case_spec.get("curve_target")
    if not isinstance(ct, dict):
        return
    pts = ct.get("points")
    if not isinstance(pts, list) or len(pts) < 1:
        return
    input_key = str(ct.get("input_key", "input_deg"))
    output_key = str(ct.get("output_key", "output_deg"))
    xs: List[float] = []
    ys: List[float] = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        try:
            xs.append(float(p[0]))
            ys.append(float(p[1]))
        except Exception:
            continue
    if not xs:
        return
    # sort points by x
    pairs = sorted(zip(xs, ys), key=lambda t: t[0])
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    inp = signals.get(input_key)
    out = signals.get(output_key)
    if not isinstance(inp, list) or not isinstance(out, list) or len(inp) != len(out) or len(inp) < 1:
        return

    # Units are enforced as degrees throughout the app.
    tgt: List[float] = []
    err: List[float] = []
    ab: List[float] = []

    # Success flags (1.0/0.0) may be present in frames.
    succ = signals.get("success")
    succ_list: List[float] = []
    if isinstance(succ, list) and len(succ) == len(inp):
        try:
            succ_list = [1.0 if float(v) >= 0.5 else 0.0 for v in succ]
        except Exception:
            succ_list = []

    # Spans (used for feasibility constraints)
    try:
        signals["target_span"] = float(max(ys) - min(ys)) if ys else 0.0
    except Exception:
        signals["target_span"] = 0.0
    try:
        signals["output_span"] = float(max(out) - min(out)) if out else 0.0
    except Exception:
        signals["output_span"] = 0.0

    if succ_list:
        signals["valid_ratio"] = float(sum(succ_list) / max(1, len(succ_list)))
    else:
        signals["valid_ratio"] = 1.0

    # Failure penalty: if a frame is not solved (success==0), penalize heavily so
    # the optimizer is forced into the feasible, continuous motion domain.
    # Strong penalty for invalid frames (solver failure, constraint violation,
    # branch flip, etc.). This must dominate typical curve errors so the search
    # is forced into the feasible continuous-motion region.
    failure_penalty = max(1000.0, 20.0 * float(signals.get("target_span", 0.0) or 0.0))

    for k, (u, y) in enumerate(zip(inp, out)):
        tu = _linear_interp(xs, ys, float(u))
        if succ_list and k < len(succ_list) and succ_list[k] < 0.5:
            e = float(failure_penalty)
        else:
            e = float(y) - tu
        tgt.append(tu)
        err.append(e)
        ab.append(abs(e))
    signals["curve_target"] = tgt
    signals["curve_err"] = err
    signals["curve_abs_err"] = ab

    # Named-curve measure aliases (v1): expression builder / optimization can compare
    # explicit curves like curve_rms_err("io_actual", "io_target") without reading UI.
    # x-grid is the current evaluation input sweep after case/simulation alignment.
    try:
        signals["curve__x__io_actual"] = [float(v) for v in inp]
        signals["curve__y__io_actual"] = [float(v) for v in out]
        signals["curve__x__io_target"] = [float(v) for v in inp]
        signals["curve__y__io_target"] = [float(v) for v in tgt]
        # Backward-friendly aliases for explicit-name syntax.
        signals["curve__x__io_ref"] = list(signals["curve__x__io_target"])
        signals["curve__y__io_ref"] = list(signals["curve__y__io_target"])
        signals.setdefault("curve__names", ["io_actual", "io_target", "io_ref"])
    except Exception:
        pass


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

            # Determine required cases (union of objective/constraint scopes).
            required_cases: set[str] = set()
            for obj in self.objectives:
                if obj.enabled:
                    required_cases.update(obj.case_ids or all_case_ids)
            for con in self.constraints:
                if con.enabled:
                    required_cases.update(con.case_ids or all_case_ids)
            if not required_cases:
                required_cases.update(all_case_ids)

            # Pre-scan feasibility for the current model as a baseline (helps explain failures).
            baseline_valid_ratio: Dict[str, float] = {}
            for case_id in sorted(required_cases):
                case_spec = self.case_specs.get(case_id)
                if not case_spec:
                    continue
                frames, _summary, _status = simulate_case(self.model_snapshot, case_spec)
                if frames:
                    ok = sum(1 for f in frames if f.get("success", False))
                    baseline_valid_ratio[case_id] = ok / float(len(frames))
                else:
                    baseline_valid_ratio[case_id] = 0.0

            best = {
                "score": float("inf"),
                "vars": {},
                "objective": None,
                "constraints": None,
                "violation": float("inf"),
                "summary": {},
                "status": {},
                "completed_evals": 0,
                "planned_evals": self.evals,
                "stopped": False,
                "baseline_valid_ratio": baseline_valid_ratio,
            }
            # Throttle UI progress updates to avoid flooding the event queue (which can
            # make the whole app feel laggy even after optimization completes).
            emit_stride = 1
            if self.evals >= 400:
                emit_stride = 10
            elif self.evals >= 200:
                emit_stride = 5
            elif self.evals >= 80:
                emit_stride = 2
            last_emit_eval = 0

            def evaluate_candidate(candidate: Dict[str, float], eval_index: int) -> float:
                """Return penalized objective score for a candidate. Lower is better."""
                nonlocal best
                apply_warnings: List[str] = []
                snapshot = _apply_design_vars(self.model_snapshot, candidate, apply_warnings)

                signals_by_case: Dict[str, Dict[str, Any]] = {}
                summaries: Dict[str, Any] = {}
                statuses: Dict[str, Any] = {}
                for case_id in required_cases:
                    case_spec = self.case_specs.get(case_id)
                    if not case_spec:
                        continue
                    frames, summary, status = simulate_case(snapshot, case_spec)
                    sig = build_signals(frames, snapshot)
                    try:
                        add_curve_target_signals(sig, case_spec)
                    except Exception:
                        pass
                    signals_by_case[case_id] = sig
                    summaries[case_id] = summary
                    statuses[case_id] = status

                objective_records: List[Dict[str, Any]] = []
                obj_vals: List[float] = []
                obj_display_vals: List[float] = []
                for obj in self.objectives:
                    if not obj.enabled:
                        continue
                    case_vals: List[float] = []
                    case_display_vals: List[float] = []
                    case_ids = obj.case_ids or all_case_ids
                    for case_id in case_ids:
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
                    avg_score = sum(case_vals) / float(len(case_vals)) if case_vals else None
                    avg_display = sum(case_display_vals) / float(len(case_display_vals)) if case_display_vals else None
                    if avg_score is not None:
                        obj_vals.append(avg_score)
                    if avg_display is not None:
                        obj_display_vals.append(avg_display)
                    objective_records.append({
                        "expression": obj.expression,
                        "direction": obj.direction,
                        "case_ids": list(case_ids),
                        "values": case_display_vals,
                        "value": avg_display,
                        "score": avg_score,
                    })

                base_score = obj_vals[0] if obj_vals else 0.0
                base_display = obj_display_vals[0] if obj_display_vals else 0.0

                violation = 0.0
                con_vals: List[float] = []
                constraint_records: List[Dict[str, Any]] = []
                for con in self.constraints:
                    if not con.enabled:
                        continue
                    case_values: List[float] = []
                    case_ids = con.case_ids or all_case_ids
                    for case_id in case_ids:
                        signals = signals_by_case.get(case_id)
                        if not signals:
                            continue
                        val, err = eval_signal_expression(con.expression, signals)
                        if err:
                            violation += 1e6
                            case_values.append(val)
                            continue
                        case_values.append(val)
                        if con.comparator == "<=":
                            violation += max(0.0, val - con.limit)
                        else:
                            violation += max(0.0, con.limit - val)
                    avg_val = sum(case_values) / float(len(case_values)) if case_values else None
                    if avg_val is not None:
                        con_vals.append(avg_val)
                    constraint_records.append({
                        "expression": con.expression,
                        "comparator": con.comparator,
                        "limit": con.limit,
                        "case_ids": list(case_ids),
                        "values": case_values,
                        "value": avg_val,
                    })

                penalty = violation * 1e6
                obj_score = float(base_score + penalty)

                new_best = False
                if obj_score < float(best.get("score", float("inf"))):
                    new_best = True
                    # Keep a compact copy of the best-case signals for UI plotting.
                    # This avoids re-simulating in the GUI (which can diverge due to
                    # solver tolerances / branch choices) and guarantees the plotted
                    # curve matches the objective score.
                    compact_signals: Dict[str, Any] = {}
                    try:
                        for _cid, _sig in (signals_by_case or {}).items():
                            if not isinstance(_sig, dict):
                                continue
                            xs = _sig.get("input_deg")
                            ys = _sig.get("output_deg")
                            tt = _sig.get("curve_target")
                            if isinstance(xs, list) and isinstance(ys, list):
                                compact_signals[_cid] = {
                                    "input_deg": xs,
                                    "output_deg": ys,
                                    "curve_target": tt if isinstance(tt, list) else None,
                                }
                    except Exception:
                        compact_signals = {}
                    best = {
                        "score": obj_score,
                        "vars": dict(candidate),
                        "objective": base_display,
                        "constraints": con_vals,
                        "violation": float(violation),
                        "summary": summaries,
                        "status": statuses,
                        "best_signals": compact_signals,
                        "completed_evals": int(eval_index),
                        "planned_evals": int(self.evals),
                        "stopped": False,
                        "baseline_valid_ratio": baseline_valid_ratio,
                    }

                status_list = []
                overall_success = True
                for cid in required_cases:
                    st = statuses.get(cid, {})
                    status_list.append({"case_id": cid, "status": st})
                    if st and not st.get("success", True):
                        overall_success = False

                log_record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "eval_index": int(eval_index),
                    "case_ids": sorted(required_cases),
                    "cases": status_list,
                    "design_vars": dict(candidate),
                    "objective_value": base_display,
                    "objectives": objective_records,
                    "objective_score": obj_score,
                    "penalty": float(penalty),
                    "constraint_violation": float(violation),
                    "constraints": constraint_records,
                    "solver_status": "success" if overall_success else "fail",
                }
                if apply_warnings:
                    log_record["warnings"] = apply_warnings
                logger.log(log_record)

                # UI progress
                # UI progress (throttled)
                try:
                    if new_best or (int(eval_index) - int(last_emit_eval) >= int(emit_stride)) or int(eval_index) >= int(self.evals):
                        last_emit_eval = int(eval_index)
                        self.progress.emit({"index": int(eval_index), "best": best, "planned": int(self.evals), "new_best": bool(new_best)})
                except Exception:
                    pass
                return obj_score

            # Use differential evolution by default when available (much more robust than pure random search).
            if differential_evolution is not None and any(v.enabled for v in self.variables):
                enabled_vars = [v for v in self.variables if v.enabled]
                bounds = [(float(v.lower), float(v.upper)) for v in enabled_vars]
                dim = max(1, len(bounds))
                popsize = 8
                # Ensure we respect the user's evaluation budget approximately.
                # nfev ~= (maxiter+1) * popsize * dim
                maxiter = max(1, int(self.evals / float(popsize * dim)) - 1)
                eval_counter = {"n": 0}

                def f(x):
                    if self._stop:
                        raise RuntimeError("stopped")
                    eval_counter["n"] += 1
                    cand = {enabled_vars[i].name: float(x[i]) for i in range(len(enabled_vars))}
                    return evaluate_candidate(cand, eval_counter["n"])

                try:
                    differential_evolution(
                        f,
                        bounds=bounds,
                        maxiter=maxiter,
                        popsize=popsize,
                        seed=self.seed,
                        polish=False,
                        disp=False,
                        updating='deferred',
                        workers=1,
                    )
                except RuntimeError as e:
                    # stop requested
                    if str(e) != 'stopped':
                        raise
                completed = int(min(eval_counter["n"], self.evals))
            else:
                # Fallback: random search (kept for environments without SciPy).
                completed = 0
                for idx in range(self.evals):
                    if self._stop:
                        break
                    completed = idx + 1
                    cand = {}
                    for var in self.variables:
                        if not var.enabled:
                            continue
                        cand[var.name] = rng.uniform(var.lower, var.upper)
                    evaluate_candidate(cand, completed)


            # Finalize convergence meta.
            best["completed_evals"] = int(completed)
            best["planned_evals"] = int(self.evals)
            best["stopped"] = bool(self._stop)
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