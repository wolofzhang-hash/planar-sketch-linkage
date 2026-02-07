# -*- coding: utf-8 -*-
"""Headless simulation utilities for optimization and run evaluation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .constraints_registry import ConstraintRegistry
from .expression_service import eval_signal_expression
from .geometry import angle_between, clamp_angle_rad, build_spline_samples, closest_point_on_samples
from .solver import ConstraintSolver
from .scipy_kinematics import SciPyKinematicSolver
from .exudyn_kinematics import ExudynKinematicSolver


@dataclass
class SweepSettings:
    start: float
    end: float
    step: float


class HeadlessModel:
    def __init__(self, snapshot: Dict[str, Any], case_spec: Dict[str, Any]):
        self.points: Dict[int, Dict[str, Any]] = {}
        self.links: Dict[int, Dict[str, Any]] = {}
        self.angles: Dict[int, Dict[str, Any]] = {}
        self.splines: Dict[int, Dict[str, Any]] = {}
        self.bodies: Dict[int, Dict[str, Any]] = {}
        self.coincides: Dict[int, Dict[str, Any]] = {}
        self.point_lines: Dict[int, Dict[str, Any]] = {}
        self.point_splines: Dict[int, Dict[str, Any]] = {}

        self.driver: Dict[str, Any] = self._default_driver()
        self.drivers: List[Dict[str, Any]] = []
        self.output: Dict[str, Any] = self._default_output()
        self.outputs: List[Dict[str, Any]] = []
        self.measures: List[Dict[str, Any]] = []
        self.loads: List[Dict[str, Any]] = []
        self.load_measures: List[Dict[str, Any]] = []
        self.friction_joints: List[Dict[str, Any]] = []

        self._sim_zero_input_rad: Optional[float] = None
        self._sim_zero_output_rad: Optional[float] = None
        self._sim_zero_meas_deg: Dict[str, float] = {}
        self._sim_zero_meas_len: Dict[str, float] = {}

        self._load_snapshot(snapshot)
        self._apply_case_spec(case_spec)
        self.mark_sim_start_pose()

    @staticmethod
    def _default_driver() -> Dict[str, Any]:
        return {
            "enabled": False,
            "type": "angle",
            "pivot": None,
            "tip": None,
            "rad": 0.0,
            "plid": None,
            "s_base": 0.0,
            "value": 0.0,
        }

    @staticmethod
    def _default_output() -> Dict[str, Any]:
        return {"enabled": False, "pivot": None, "tip": None, "rad": 0.0}

    @staticmethod
    def _normalize_driver(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "enabled": bool(data.get("enabled", True)),
            "type": str(data.get("type", "angle")),
            "pivot": data.get("pivot"),
            "tip": data.get("tip"),
            "rad": float(data.get("rad", 0.0) or 0.0),
            "plid": data.get("plid"),
            "s_base": float(data.get("s_base", 0.0) or 0.0),
            "value": float(data.get("value", 0.0) or 0.0),
        }

    @staticmethod
    def _normalize_output(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "enabled": bool(data.get("enabled", True)),
            "pivot": data.get("pivot"),
            "tip": data.get("tip"),
            "rad": float(data.get("rad", 0.0) or 0.0),
        }

    def _active_drivers(self) -> List[Dict[str, Any]]:
        return [d for d in self.drivers if d.get("enabled", False)]

    def _active_outputs(self) -> List[Dict[str, Any]]:
        return [o for o in self.outputs if o.get("enabled", False)]

    def _sync_primary_driver(self) -> None:
        if self.drivers:
            self.driver = dict(self.drivers[0])
        else:
            self.driver = self._default_driver()

    def _sync_primary_output(self) -> None:
        if self.outputs:
            self.output = dict(self.outputs[0])
        else:
            self.output = self._default_output()

    def _primary_driver(self) -> Optional[Dict[str, Any]]:
        return self.drivers[0] if self.drivers else None

    def _primary_output(self) -> Optional[Dict[str, Any]]:
        return self.outputs[0] if self.outputs else None

    def _load_snapshot(self, data: Dict[str, Any]) -> None:
        self.points = {
            int(p["id"]): {
                "x": float(p.get("x", 0.0)),
                "y": float(p.get("y", 0.0)),
                "fixed": bool(p.get("fixed", False)),
                "hidden": bool(p.get("hidden", False)),
            }
            for p in data.get("points", []) or []
        }

        constraints = data.get("constraints", None)
        if constraints:
            lks, angs, spls, coincs, pls, pss = ConstraintRegistry.split_constraints(constraints)
        else:
            lks = data.get("links", []) or []
            angs = data.get("angles", []) or []
            spls = data.get("splines", []) or []
            coincs = data.get("coincides", []) or []
            pls = data.get("point_lines", []) or []
            pss = data.get("point_splines", []) or []

        self.links = {
            int(l["id"]): {
                "i": int(l.get("i", -1)),
                "j": int(l.get("j", -1)),
                "L": float(l.get("L", 0.0)),
                "ref": bool(l.get("ref", False)),
                "over": False,
            }
            for l in lks
        }
        self.angles = {
            int(a["id"]): {
                "i": int(a.get("i", -1)),
                "j": int(a.get("j", -1)),
                "k": int(a.get("k", -1)),
                "deg": float(a.get("deg", 0.0)),
                "rad": math.radians(float(a.get("deg", 0.0))),
                "enabled": bool(a.get("enabled", True)),
                "over": False,
            }
            for a in angs
        }
        self.splines = {
            int(s.get("id", -1)): {
                "points": list(s.get("points", [])),
                "hidden": bool(s.get("hidden", False)),
                "closed": bool(s.get("closed", False)),
            }
            for s in spls
        }
        self.coincides = {
            int(c["id"]): {
                "a": int(c.get("a", -1)),
                "b": int(c.get("b", -1)),
                "enabled": bool(c.get("enabled", True)),
                "over": False,
            }
            for c in coincs
        }
        point_lines: Dict[int, Dict[str, Any]] = {}
        for pl in pls:
            plid = int(pl.get("id", -1))
            entry = {
                "p": int(pl.get("p", -1)),
                "i": int(pl.get("i", -1)),
                "j": int(pl.get("j", -1)),
                "enabled": bool(pl.get("enabled", True)),
                "over": False,
            }
            if "s" in pl or "s_expr" in pl:
                entry["s"] = float(pl.get("s", 0.0))
                entry["s_expr"] = str(pl.get("s_expr", ""))
                if pl.get("name"):
                    entry["name"] = str(pl.get("name", ""))
            point_lines[plid] = entry
        self.point_lines = point_lines
        self.point_splines = {
            int(ps["id"]): {
                "p": int(ps.get("p", -1)),
                "s": int(ps.get("s", -1)),
                "enabled": bool(ps.get("enabled", True)),
                "over": False,
            }
            for ps in pss
        }

        self.bodies = {
            int(b.get("id", -1)): {
                "rigid_edges": list(b.get("rigid_edges", [])),
            }
            for b in data.get("bodies", []) or []
        }

        driver = data.get("driver", {}) or {}
        output = data.get("output", {}) or {}
        drivers_list = data.get("drivers", None)
        outputs_list = data.get("outputs", None)
        self.drivers = []
        if isinstance(drivers_list, list) and drivers_list:
            for drv in drivers_list:
                if isinstance(drv, dict):
                    normalized = self._normalize_driver(drv)
                    if "rad" not in drv:
                        normalized["_needs_rad"] = True
                    self.drivers.append(normalized)
        elif isinstance(driver, dict):
            legacy_driver = self._normalize_driver(driver)
            if legacy_driver.get("enabled"):
                if "rad" not in driver:
                    legacy_driver["_needs_rad"] = True
                self.drivers.append(legacy_driver)

        for drv in self.drivers:
            if not drv.pop("_needs_rad", False):
                continue
            if drv.get("type") != "angle":
                continue
            piv = drv.get("pivot")
            tip = drv.get("tip")
            if piv is not None and tip is not None:
                ang = self.get_angle_rad(int(piv), int(tip))
                if ang is not None:
                    drv["rad"] = float(ang)
        self._sync_primary_driver()

        self.outputs = []
        if isinstance(outputs_list, list) and outputs_list:
            for out in outputs_list:
                if isinstance(out, dict):
                    normalized = self._normalize_output(out)
                    if "rad" not in out:
                        normalized["_needs_rad"] = True
                    self.outputs.append(normalized)
        elif isinstance(output, dict):
            legacy_output = self._normalize_output(output)
            if legacy_output.get("enabled"):
                if "rad" not in output:
                    legacy_output["_needs_rad"] = True
                self.outputs.append(legacy_output)

        for out in self.outputs:
            if not out.pop("_needs_rad", False):
                continue
            piv = out.get("pivot")
            tip = out.get("tip")
            if piv is not None and tip is not None:
                ang = self.get_angle_rad(int(piv), int(tip))
                if ang is not None:
                    out["rad"] = float(ang)
        self._sync_primary_output()
        self.measures = list(data.get("measures", []) or [])
        self.loads = list(data.get("loads", []) or [])
        self.load_measures = list(data.get("load_measures", []) or [])
        self.friction_joints = list(data.get("friction_joints", []) or [])

    def _point_line_current_s(self, pl: Dict[str, Any]) -> float:
        try:
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
        except Exception:
            return 0.0
        if p_id not in self.points or i_id not in self.points or j_id not in self.points:
            return 0.0
        pp = self.points[p_id]
        pa = self.points[i_id]
        pb = self.points[j_id]
        ax, ay = float(pa["x"]), float(pa["y"])
        bx, by = float(pb["x"]), float(pb["y"])
        px, py = float(pp["x"]), float(pp["y"])
        abx, aby = bx - ax, by - ay
        ab_len = math.hypot(abx, aby)
        if ab_len < 1e-12:
            return 0.0
        ux, uy = abx / ab_len, aby / ab_len
        return (px - ax) * ux + (py - ay) * uy

    def _apply_case_spec(self, case_spec: Dict[str, Any]) -> None:
        driver = case_spec.get("driver")
        drivers_list = case_spec.get("drivers")
        output = case_spec.get("output")
        outputs_list = case_spec.get("outputs")
        if isinstance(drivers_list, list):
            self.drivers = [self._normalize_driver(d) for d in drivers_list if isinstance(d, dict)]
            self._sync_primary_driver()
        elif isinstance(driver, dict):
            self.drivers = [self._normalize_driver(driver)]
            self._sync_primary_driver()
        if isinstance(outputs_list, list):
            self.outputs = [self._normalize_output(o) for o in outputs_list if isinstance(o, dict)]
            self._sync_primary_output()
        elif isinstance(output, dict):
            self.outputs = [self._normalize_output(output)]
            self._sync_primary_output()
        loads = case_spec.get("loads")
        if isinstance(loads, list):
            self.loads = [dict(ld) for ld in loads]
        friction_joints = case_spec.get("friction_joints")
        if isinstance(friction_joints, list):
            self.friction_joints = [dict(fj) for fj in friction_joints]
        measurements = case_spec.get("measurements", {}) or {}
        measures = measurements.get("measures")
        if isinstance(measures, list):
            self.measures = [dict(m) for m in measures]
        load_measures = measurements.get("load_measures")
        if isinstance(load_measures, list):
            self.load_measures = [dict(m) for m in load_measures]

    def mark_sim_start_pose(self) -> None:
        self._sim_zero_input_rad = self._get_input_angle_abs_rad()
        self._sim_zero_output_rad = self._get_output_angle_abs_rad()
        self._sim_zero_meas_deg = {}
        self._sim_zero_meas_len = {}
        for name, val, unit in self.get_measure_values(abs_values=True):
            if val is None:
                continue
            if unit == "deg":
                self._sim_zero_meas_deg[name] = float(val)
            elif unit == "mm":
                self._sim_zero_meas_len[name] = float(val)

    @staticmethod
    def _rel_deg(abs_deg: float, base_deg: float) -> float:
        return (abs_deg - base_deg) % 360.0

    def get_angle_rad(self, pivot_pid: int, tip_pid: int) -> Optional[float]:
        if pivot_pid not in self.points or tip_pid not in self.points:
            return None
        p = self.points[pivot_pid]
        q = self.points[tip_pid]
        dx = q["x"] - p["x"]
        dy = q["y"] - p["y"]
        if abs(dx) + abs(dy) < 1e-12:
            return None
        return math.atan2(dy, dx)

    def get_joint_angle_rad(self, i_pid: int, j_pid: int, k_pid: int) -> Optional[float]:
        if i_pid not in self.points or j_pid not in self.points or k_pid not in self.points:
            return None
        pi, pj, pk = self.points[i_pid], self.points[j_pid], self.points[k_pid]
        v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
        v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
        if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
            return None
        return angle_between(v1x, v1y, v2x, v2y)

    def _point_line_offset_name(self, pl: Dict[str, Any]) -> str:
        try:
            p = int(pl.get("p", -1))
            i = int(pl.get("i", -1))
            j = int(pl.get("j", -1))
        except Exception:
            return "point line s"
        return f"s P{p} on (P{i}-P{j})"

    def _get_input_angle_abs_rad(self) -> Optional[float]:
        primary = self._primary_driver()
        if not primary or not primary.get("enabled"):
            return None
        if primary.get("type") != "angle":
            return None
        piv = primary.get("pivot")
        tip = primary.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_angle_rad(int(piv), int(tip))

    def _get_output_angle_abs_rad(self) -> Optional[float]:
        primary = self._primary_output()
        if not primary or not primary.get("enabled"):
            return None
        piv = primary.get("pivot")
        tip = primary.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_angle_rad(int(piv), int(tip))

    def get_input_angle_deg(self) -> Optional[float]:
        ang = self._get_input_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_input_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_input_rad)
        return self._rel_deg(abs_deg, base_deg)

    def get_output_angle_deg(self) -> Optional[float]:
        ang = self._get_output_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_output_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_output_rad)
        return self._rel_deg(abs_deg, base_deg)

    def get_measure_values(self, abs_values: bool = False) -> List[tuple[str, Optional[float], str]]:
        out: List[tuple[str, Optional[float], str]] = []
        base_values: Dict[int, tuple[str, Optional[float], str]] = {}
        signals: Dict[str, float] = {}

        for idx, m in enumerate(self.measures):
            nm = str(m.get("name", ""))
            mtype = str(m.get("type", "")).lower()
            abs_deg: Optional[float] = None
            if mtype == "angle":
                ang = self.get_angle_rad(int(m.get("pivot")), int(m.get("tip")))
                abs_deg = None if ang is None else math.degrees(ang)
            elif mtype == "joint":
                ang = self.get_joint_angle_rad(int(m.get("i")), int(m.get("j")), int(m.get("k")))
                abs_deg = None if ang is None else math.degrees(ang)
            elif mtype == "translation":
                try:
                    plid = int(m.get("plid", -1))
                except (TypeError, ValueError):
                    plid = -1
                pl = self.point_lines.get(plid)
                if pl is None:
                    base_values[idx] = (nm, None, "mm")
                    continue
                nm = str(nm) or self._point_line_offset_name(pl)
                try:
                    sval = float(pl.get("s", 0.0))
                except (TypeError, ValueError):
                    sval = None
                if sval is not None and (not abs_values) and nm in self._sim_zero_meas_len:
                    base_values[idx] = (nm, sval - float(self._sim_zero_meas_len[nm]), "mm")
                else:
                    base_values[idx] = (nm, sval, "mm")
                if nm and base_values[idx][1] is not None:
                    signals[nm] = float(base_values[idx][1])
                continue
            elif mtype == "expression":
                continue
            else:
                continue

            if abs_deg is None:
                base_values[idx] = (nm, None, "deg")
            elif abs_values:
                base_values[idx] = (nm, abs_deg, "deg")
            elif nm in self._sim_zero_meas_deg:
                base_values[idx] = (nm, self._rel_deg(abs_deg, float(self._sim_zero_meas_deg[nm])), "deg")
            else:
                base_values[idx] = (nm, abs_deg, "deg")
            if nm and base_values[idx][1] is not None:
                signals[nm] = float(base_values[idx][1])

        for nm, val in self.get_load_measure_values():
            if nm and val is not None:
                signals[str(nm)] = float(val)

        for idx, m in enumerate(self.measures):
            if idx in base_values:
                out.append(base_values[idx])
                continue
            mtype = str(m.get("type", "")).lower()
            if mtype != "expression":
                continue
            nm = str(m.get("name", ""))
            expr = str(m.get("expr", ""))
            unit = str(m.get("unit", ""))
            val, err = eval_signal_expression(expr, signals)
            if err:
                out.append((nm, None, unit))
            else:
                out.append((nm, float(val), unit))
                if nm:
                    signals[nm] = float(val)
        return out

    def _build_quasistatic_constraints(self, point_ids: List[int]) -> List[Any]:
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        funcs: List[Any] = []

        def _xy(q: np.ndarray, pid: int) -> tuple[float, float]:
            idx = idx_map[pid]
            return float(q[2 * idx]), float(q[2 * idx + 1])

        for pid in point_ids:
            p = self.points[pid]
            if not bool(p.get("fixed", False)):
                continue
            x0, y0 = float(p["x"]), float(p["y"])
            funcs.append(lambda q, pid=pid, x0=x0: _xy(q, pid)[0] - x0)
            funcs.append(lambda q, pid=pid, y0=y0: _xy(q, pid)[1] - y0)

        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1))
            b = int(c.get("b", -1))
            if a not in idx_map or b not in idx_map:
                continue
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[0] - _xy(q, b)[0])
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[1] - _xy(q, b)[1])

        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
            if p_id not in idx_map or i_id not in idx_map or j_id not in idx_map:
                continue
            if "s" in pl:
                s_val = float(pl.get("s", 0.0))

                def _polx(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id, s_val=s_val) -> float:
                    px, _py = _xy(q, p_id)
                    ax, ay = _xy(q, i_id)
                    bx, by = _xy(q, j_id)
                    abx, aby = bx - ax, by - ay
                    denom = math.hypot(abx, aby)
                    if denom < 1e-9:
                        return 0.0
                    ux, uy = abx / denom, aby / denom
                    target_x = ax + ux * s_val
                    return px - target_x

                def _poly(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id, s_val=s_val) -> float:
                    _px, py = _xy(q, p_id)
                    ax, ay = _xy(q, i_id)
                    bx, by = _xy(q, j_id)
                    abx, aby = bx - ax, by - ay
                    denom = math.hypot(abx, aby)
                    if denom < 1e-9:
                        return 0.0
                    ux, uy = abx / denom, aby / denom
                    target_y = ay + uy * s_val
                    return py - target_y

                funcs.append(_polx)
                funcs.append(_poly)
            else:
                def _pol(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id) -> float:
                    px, py = _xy(q, p_id)
                    ax, ay = _xy(q, i_id)
                    bx, by = _xy(q, j_id)
                    abx, aby = bx - ax, by - ay
                    denom = math.hypot(abx, aby)
                    if denom < 1e-9:
                        return 0.0
                    return ((px - ax) * (-aby) + (py - ay) * abx) / denom

            funcs.append(_pol)
            if "s" in pl:
                s_target = float(pl.get("s", 0.0))

                def _pol_s(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id, s_target=s_target) -> float:
                    px, py = _xy(q, p_id)
                    ax, ay = _xy(q, i_id)
                    bx, by = _xy(q, j_id)
                    abx, aby = bx - ax, by - ay
                    denom = math.hypot(abx, aby)
                    if denom < 1e-9:
                        return 0.0
                    ux, uy = abx / denom, aby / denom
                    return (px - ax) * ux + (py - ay) * uy - s_target

                funcs.append(_pol_s)

        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = int(ps.get("p", -1))
            s_id = int(ps.get("s", -1))
            if p_id not in idx_map or s_id not in self.splines:
                continue
            spline = self.splines[s_id]
            cp_ids = [pid for pid in spline.get("points", []) if pid in idx_map]
            if len(cp_ids) < 2:
                continue

            def _pos(q: np.ndarray, p_id=p_id, cp_ids=cp_ids, spline=spline) -> float:
                px, py = _xy(q, p_id)
                samples = build_spline_samples(
                    [_xy(q, cid) for cid in cp_ids],
                    closed=bool(spline.get("closed", False)),
                )
                _, _, _, _, dist2 = closest_point_on_samples(px, py, samples)
                return math.sqrt(dist2)

            funcs.append(_pos)

        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))
        for (i, j, L) in body_edges:
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=L) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            funcs.append(_len)

        for l in self.links.values():
            if l.get("ref", False):
                continue
            i, j = int(l.get("i", -1)), int(l.get("j", -1))
            if i not in idx_map or j not in idx_map:
                continue

            def _len(q: np.ndarray, i=i, j=j, L=l["L"]) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                return math.hypot(xj - xi, yj - yi) - float(L)

            funcs.append(_len)

        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i, j, k = int(a.get("i", -1)), int(a.get("j", -1)), int(a.get("k", -1))
            if i not in idx_map or j not in idx_map or k not in idx_map:
                continue
            target = float(a.get("rad", 0.0))

            def _ang(q: np.ndarray, i=i, j=j, k=k, target=target) -> float:
                xi, yi = _xy(q, i)
                xj, yj = _xy(q, j)
                xk, yk = _xy(q, k)
                v1x, v1y = xi - xj, yi - yj
                v2x, v2y = xk - xj, yk - yj
                if math.hypot(v1x, v1y) < 1e-12 or math.hypot(v2x, v2y) < 1e-12:
                    return 0.0
                cur = angle_between(v1x, v1y, v2x, v2y)
                return clamp_angle_rad(cur - target)

            funcs.append(_ang)

        active_drivers = self._active_drivers()
        active_outputs = self._active_outputs()
        if active_drivers:
            for drv in active_drivers:
                if drv.get("type") != "angle":
                    continue
                piv = drv.get("pivot")
                tip = drv.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(drv.get("rad", 0.0))

                    def _drv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    funcs.append(_drv)
        elif active_outputs:
            for out in active_outputs:
                piv = out.get("pivot")
                tip = out.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(out.get("rad", 0.0))

                    def _odrv(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    funcs.append(_odrv)

        return funcs

    def compute_quasistatic_joint_loads(self) -> List[Dict[str, Any]]:
        point_ids = sorted(list(self.points.keys()))
        if not point_ids:
            return []
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        q = np.array([coord for pid in point_ids for coord in (self.points[pid]["x"], self.points[pid]["y"])], dtype=float)
        ndof = len(q)
        f_ext = np.zeros(ndof, dtype=float)
        torque_map: Dict[int, float] = {pid: 0.0 for pid in point_ids}
        for load in self.loads:
            pid = int(load.get("pid", -1))
            if pid not in self.points:
                continue
            idx = idx_map[pid]
            fx, fy, mz = self._resolve_load_components(load, q, idx_map)
            f_ext[2 * idx] += fx
            f_ext[2 * idx + 1] += fy
            if abs(mz) > 0.0:
                torque_map[pid] = torque_map.get(pid, 0.0) + float(mz)

        funcs = self._build_quasistatic_constraints(point_ids)
        if not funcs:
            out = []
            for idx, pid in enumerate(point_ids):
                fx = -float(f_ext[2 * idx])
                fy = -float(f_ext[2 * idx + 1])
                out.append({"pid": pid, "fx": fx, "fy": fy, "mag": math.hypot(fx, fy)})
            return out

        def eval_constraints(qvec: np.ndarray) -> np.ndarray:
            return np.array([fn(qvec) for fn in funcs], dtype=float)

        eps = 1e-6
        c0 = eval_constraints(q)
        m = int(c0.size)
        J = np.zeros((m, ndof), dtype=float)
        for i in range(ndof):
            dq = np.zeros_like(q)
            dq[i] = eps
            fp = eval_constraints(q + dq)
            fm = eval_constraints(q - dq)
            J[:, i] = (fp - fm) / (2.0 * eps)

        if J.size == 0:
            lam = np.zeros(m, dtype=float)
        else:
            try:
                lam, *_ = np.linalg.lstsq(J.T, -f_ext, rcond=None)
            except np.linalg.LinAlgError:
                lam = np.zeros(m, dtype=float)

        joint_loads: List[Dict[str, Any]] = []
        lam = np.asarray(lam, dtype=float)
        for idx, pid in enumerate(point_ids):
            fx = -float(f_ext[2 * idx])
            fy = -float(f_ext[2 * idx + 1])
            mag = math.hypot(fx, fy)
            joint_loads.append({"pid": pid, "fx": fx, "fy": fy, "mag": mag})
        return joint_loads

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        return (angle + math.pi) % (2.0 * math.pi) - math.pi

    def _resolve_load_components(
        self,
        load: Dict[str, Any],
        qvec: Optional[np.ndarray] = None,
        idx_map: Optional[Dict[int, int]] = None,
    ) -> tuple[float, float, float]:
        ltype = str(load.get("type", "force")).lower()
        if ltype == "spring":
            pid = int(load.get("pid", -1))
            ref_pid = int(load.get("ref_pid", -1))
            k = float(load.get("k", 0.0))
            preload = float(load.get("load", 0.0))
            if pid not in self.points or ref_pid not in self.points:
                return 0.0, 0.0, 0.0
            if qvec is not None and idx_map is not None and pid in idx_map and ref_pid in idx_map:
                i = idx_map[pid]
                j = idx_map[ref_pid]
                dx = float(qvec[2 * j]) - float(qvec[2 * i])
                dy = float(qvec[2 * j + 1]) - float(qvec[2 * i + 1])
            else:
                dx = float(self.points[ref_pid]["x"]) - float(self.points[pid]["x"])
                dy = float(self.points[ref_pid]["y"]) - float(self.points[pid]["y"])
            fx = k * dx
            fy = k * dy
            if abs(dx) + abs(dy) > 1e-12 and abs(preload) > 0.0:
                norm = math.hypot(dx, dy)
                fx += preload * dx / norm
                fy += preload * dy / norm
            return fx, fy, 0.0
        if ltype == "torsion_spring":
            pid = int(load.get("pid", -1))
            ref_pid = int(load.get("ref_pid", -1))
            k = float(load.get("k", 0.0))
            theta0 = float(load.get("theta0", 0.0))
            preload = float(load.get("load", 0.0))
            if pid not in self.points or ref_pid not in self.points:
                return 0.0, 0.0, 0.0
            if qvec is not None and idx_map is not None and pid in idx_map and ref_pid in idx_map:
                i = idx_map[pid]
                j = idx_map[ref_pid]
                dx = float(qvec[2 * j]) - float(qvec[2 * i])
                dy = float(qvec[2 * j + 1]) - float(qvec[2 * i + 1])
            else:
                dx = float(self.points[ref_pid]["x"]) - float(self.points[pid]["x"])
                dy = float(self.points[ref_pid]["y"]) - float(self.points[pid]["y"])
            if abs(dx) + abs(dy) < 1e-12:
                return 0.0, 0.0, 0.0
            theta = math.atan2(dy, dx)
            delta = self._wrap_angle(theta - theta0)
            return 0.0, 0.0, k * delta + preload
        fx = float(load.get("fx", 0.0))
        fy = float(load.get("fy", 0.0))
        mz = float(load.get("mz", 0.0))
        return fx, fy, mz

    def get_load_measure_values(self) -> List[tuple[str, Optional[float]]]:
        out: List[tuple[str, Optional[float]]] = []
        if not self.load_measures:
            return out
        load_map: Dict[int, Dict[str, float]] = {}
        for jl in self.compute_quasistatic_joint_loads():
            pid = int(jl.get("pid", -1))
            if pid < 0:
                continue
            load_map[pid] = {
                "fx": float(jl.get("fx", 0.0)),
                "fy": float(jl.get("fy", 0.0)),
                "mag": float(jl.get("mag", 0.0)),
            }
        for m in self.load_measures:
            nm = str(m.get("name", ""))
            pid = int(m.get("pid", -1))
            comp = str(m.get("component", "mag")).lower()
            val = None
            if pid in load_map and comp in load_map[pid]:
                val = float(load_map[pid][comp])
            out.append((nm, val))
        return out

    def drive_to_deg(self, deg: float, iters: int = 80) -> None:
        if not self._active_drivers() and not self._active_outputs():
            return
        primary_driver = self._primary_driver()
        primary_output = self._primary_output()
        if primary_driver and primary_driver.get("enabled"):
            if self._sim_zero_input_rad is not None:
                target = float(self._sim_zero_input_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_driver["rad"] = float(target)
            self.drivers[0] = primary_driver
            self._sync_primary_driver()
        elif primary_output and primary_output.get("enabled"):
            if self._sim_zero_output_rad is not None:
                target = float(self._sim_zero_output_rad) + math.radians(float(deg))
            else:
                target = math.radians(float(deg))
            primary_output["rad"] = float(target)
            self.outputs[0] = primary_output
            self._sync_primary_output()
        self.solve_constraints(iters=iters)

    def solve_constraints(self, iters: int = 60) -> None:
        for l in self.links.values():
            l["over"] = False
        for a in self.angles.values():
            a["over"] = False
        for c in self.coincides.values():
            c["over"] = False
        for pl in self.point_lines.values():
            pl["over"] = False
        for ps in self.point_splines.values():
            ps["over"] = False

        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))

        driven_pids: set[int] = set()
        active_drivers = self._active_drivers()
        active_outputs = self._active_outputs()
        drive_sources: List[Dict[str, Any]] = []
        if active_drivers:
            for drv in active_drivers:
                entry = dict(drv)
                entry["mode"] = "driver"
                drive_sources.append(entry)
        elif active_outputs:
            for out in active_outputs:
                entry = {
                    "mode": "output",
                    "type": "angle",
                    "pivot": out.get("pivot"),
                    "tip": out.get("tip"),
                    "rad": out.get("rad", 0.0),
                }
                drive_sources.append(entry)

        for drv in drive_sources:
            if str(drv.get("type", "angle")) == "translation":
                plid = drv.get("plid")
                if plid in self.point_lines:
                    p_id = self.point_lines[plid].get("p")
                    if p_id is not None:
                        driven_pids.add(int(p_id))
                continue
            tip = drv.get("tip")
            if tip is not None:
                driven_pids.add(int(tip))

        driver_length_pairs: set[frozenset[int]] = set()
        for drv in drive_sources:
            piv = drv.get("pivot")
            tip = drv.get("tip")
            if piv is not None and tip is not None:
                driver_length_pairs.add(frozenset({int(piv), int(tip)}))

        translation_targets: Dict[int, float] = {}
        for drv in drive_sources:
            if str(drv.get("type", "angle")) != "translation":
                continue
            plid = drv.get("plid")
            if plid not in self.point_lines:
                continue
            pl = self.point_lines[plid]
            base_s = float(drv.get("s_base", self._point_line_current_s(pl)) or 0.0)
            offset = float(drv.get("value", 0.0) or 0.0)
            translation_targets[int(plid)] = base_s + offset

        for _ in range(int(iters)):
            for drv in drive_sources:
                if str(drv.get("type", "angle")) == "translation":
                    continue
                piv = drv.get("pivot")
                tip = drv.get("tip")
                if piv is None or tip is None:
                    continue
                piv = int(piv); tip = int(tip)
                if piv in self.points and tip in self.points:
                    piv_pt = self.points[piv]
                    tip_pt = self.points[tip]
                    lock_piv = bool(piv_pt.get("fixed", False))
                    lock_tip = bool(tip_pt.get("fixed", False))
                    ConstraintSolver.enforce_driver_angle(
                        piv_pt,
                        tip_pt,
                        float(drv.get("rad", 0.0)),
                        lock_piv,
                        lock_tip=lock_tip,
                    )

            for plid, target_s in translation_targets.items():
                pl = self.point_lines.get(plid)
                if not pl or not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1))
                i_id = int(pl.get("i", -1))
                j_id = int(pl.get("j", -1))
                if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                    continue
                pp = self.points[p_id]
                pa = self.points[i_id]
                pb = self.points[j_id]
                lock_p = bool(pp.get("fixed", False))
                lock_a = bool(pa.get("fixed", False))
                lock_b = bool(pb.get("fixed", False))
                ConstraintSolver.solve_point_on_line_offset(
                    pp,
                    pa,
                    pb,
                    float(target_s),
                    lock_p,
                    lock_a,
                    lock_b,
                    tol=1e-6,
                )

            for c in self.coincides.values():
                if not bool(c.get("enabled", True)):
                    continue
                a = int(c.get("a", -1))
                b = int(c.get("b", -1))
                if a not in self.points or b not in self.points:
                    continue
                pa = self.points[a]
                pb = self.points[b]
                ax, ay = float(pa["x"]), float(pa["y"])
                bx, by = float(pb["x"]), float(pb["y"])
                lock_a = bool(pa.get("fixed", False))
                lock_b = bool(pb.get("fixed", False))
                if lock_a and lock_b:
                    if (ax - bx) * (ax - bx) + (ay - by) * (ay - by) > 1e-6:
                        c["over"] = True
                    continue
                if lock_a and not lock_b:
                    pb["x"], pb["y"] = ax, ay
                elif lock_b and not lock_a:
                    pa["x"], pa["y"] = bx, by
                else:
                    mx = 0.5 * (ax + bx)
                    my = 0.5 * (ay + by)
                    pa["x"], pa["y"] = mx, my
                    pb["x"], pb["y"] = mx, my

            for plid, pl in self.point_lines.items():
                if not bool(pl.get("enabled", True)):
                    continue
                p_id = int(pl.get("p", -1))
                i_id = int(pl.get("i", -1))
                j_id = int(pl.get("j", -1))
                if p_id not in self.points or i_id not in self.points or j_id not in self.points:
                    continue
                pp = self.points[p_id]
                pa = self.points[i_id]
                pb = self.points[j_id]
                lock_p = bool(pp.get("fixed", False)) or (p_id in driven_pids)
                lock_a = bool(pa.get("fixed", False)) or (i_id in driven_pids)
                lock_b = bool(pb.get("fixed", False)) or (j_id in driven_pids)
                if plid in translation_targets:
                    ok = ConstraintSolver.solve_point_on_line_offset(
                        pp,
                        pa,
                        pb,
                        float(translation_targets[plid]),
                        lock_p,
                        lock_a,
                        lock_b,
                        tol=1e-6,
                    )
                elif "s" in pl:
                    ok = ConstraintSolver.solve_point_on_line_offset(
                        pp,
                        pa,
                        pb,
                        float(pl.get("s", 0.0)),
                        lock_p,
                        lock_a,
                        lock_b,
                        tol=1e-6,
                    )
                else:
                    ok = ConstraintSolver.solve_point_on_line(pp, pa, pb, lock_p, lock_a, lock_b, tol=1e-6)
                if not ok:
                    pl["over"] = True

            for ps in self.point_splines.values():
                if not bool(ps.get("enabled", True)):
                    continue
                p_id = int(ps.get("p", -1))
                s_id = int(ps.get("s", -1))
                if p_id not in self.points or s_id not in self.splines:
                    continue
                spline = self.splines[s_id]
                cp_ids = [pid for pid in spline.get("points", []) if pid in self.points]
                if len(cp_ids) < 2:
                    continue
                pp = self.points[p_id]
                cps = [self.points[cid] for cid in cp_ids]
                lock_p = bool(pp.get("fixed", False)) or (p_id in driven_pids)
                lock_controls = []
                for cid in cp_ids:
                    lock_controls.append(bool(self.points[cid].get("fixed", False)) or (cid in driven_pids))
                ok = ConstraintSolver.solve_point_on_spline(
                    pp,
                    cps,
                    lock_p,
                    lock_controls,
                    tol=1e-6,
                    closed=bool(spline.get("closed", False)),
                )
                if not ok:
                    ps["over"] = True

            for (i, j, L) in body_edges:
                if i not in self.points or j not in self.points:
                    continue
                p1, p2 = self.points[i], self.points[j]
                pair = frozenset({i, j})
                allow_move_driven = (pair in driver_length_pairs)
                lock1 = bool(p1.get("fixed", False)) or ((i in driven_pids) and (not allow_move_driven))
                lock2 = bool(p2.get("fixed", False)) or ((j in driven_pids) and (not allow_move_driven))
                ConstraintSolver.solve_length(p1, p2, float(L), lock1, lock2, tol=1e-6)

            for l in self.links.values():
                if l.get("ref", False):
                    continue
                i, j = l["i"], l["j"]
                if i not in self.points or j not in self.points:
                    continue
                p1, p2 = self.points[i], self.points[j]
                pair = frozenset({i, j})
                allow_move_driven = (pair in driver_length_pairs)
                lock1 = bool(p1.get("fixed", False)) or ((i in driven_pids) and (not allow_move_driven))
                lock2 = bool(p2.get("fixed", False)) or ((j in driven_pids) and (not allow_move_driven))
                ok = ConstraintSolver.solve_length(p1, p2, float(l["L"]), lock1, lock2, tol=1e-6)
                if not ok:
                    l["over"] = True

            for a in self.angles.values():
                if not a.get("enabled", True):
                    continue
                i, j, k = a["i"], a["j"], a["k"]
                if i not in self.points or j not in self.points or k not in self.points:
                    continue
                pi, pj, pk = self.points[i], self.points[j], self.points[k]
                lock_i = bool(pi.get("fixed", False)) or (i in driven_pids)
                lock_j = bool(pj.get("fixed", False)) or (j in driven_pids)
                lock_k = bool(pk.get("fixed", False)) or (k in driven_pids)
                ok = ConstraintSolver.solve_angle(pi, pj, pk, float(a["rad"]), lock_i, lock_j, lock_k, tol=1e-5)
                if not ok:
                    a["over"] = True

    def solve_constraints_scipy(self, max_nfev: int = 200) -> tuple[bool, str]:
        try:
            ok, msg, _cost = SciPyKinematicSolver.solve(self, max_nfev=max_nfev)
            return ok, msg
        except Exception as exc:
            return False, str(exc)

    def solve_constraints_exudyn(self, max_iters: int = 80) -> tuple[bool, str]:
        try:
            ok, msg = ExudynKinematicSolver.solve(self, max_iters=max_iters)
            return ok, msg
        except Exception as exc:
            return False, str(exc)

    def _check_over_flags_only(self) -> None:
        return

    def max_constraint_error(self) -> Tuple[float, Dict[str, float]]:
        max_len = 0.0
        max_ang = 0.0
        max_coin = 0.0
        max_pl = 0.0
        max_ps = 0.0

        body_edges: List[Tuple[int, int, float]] = []
        for b in self.bodies.values():
            body_edges.extend(b.get("rigid_edges", []))
        for (i, j, L) in body_edges:
            if i in self.points and j in self.points:
                p1, p2 = self.points[i], self.points[j]
                d = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                max_len = max(max_len, abs(d - float(L)))

        for l in self.links.values():
            if bool(l.get("ref", False)):
                continue
            i, j = int(l.get("i", -1)), int(l.get("j", -1))
            if i in self.points and j in self.points:
                p1, p2 = self.points[i], self.points[j]
                d = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                max_len = max(max_len, abs(d - float(l.get("L", 0.0))))

        for a in self.angles.values():
            if not bool(a.get("enabled", True)):
                continue
            i, j, k = int(a.get("i", -1)), int(a.get("j", -1)), int(a.get("k", -1))
            if i in self.points and j in self.points and k in self.points:
                pi, pj, pk = self.points[i], self.points[j], self.points[k]
                v1x, v1y = pi["x"] - pj["x"], pi["y"] - pj["y"]
                v2x, v2y = pk["x"] - pj["x"], pk["y"] - pj["y"]
                if math.hypot(v1x, v1y) > 1e-12 and math.hypot(v2x, v2y) > 1e-12:
                    cur = angle_between(v1x, v1y, v2x, v2y)
                    err = abs(clamp_angle_rad(cur - float(a.get("rad", 0.0))))
                    max_ang = max(max_ang, err)

        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a_id, b_id = int(c.get("a", -1)), int(c.get("b", -1))
            if a_id in self.points and b_id in self.points:
                pa, pb = self.points[a_id], self.points[b_id]
                max_coin = max(max_coin, math.hypot(pa["x"] - pb["x"], pa["y"] - pb["y"]))

        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id, i_id, j_id = int(pl.get("p", -1)), int(pl.get("i", -1)), int(pl.get("j", -1))
            if p_id in self.points and i_id in self.points and j_id in self.points:
                pp, pa, pb = self.points[p_id], self.points[i_id], self.points[j_id]
                ax, ay = float(pa["x"]), float(pa["y"])
                bx, by = float(pb["x"]), float(pb["y"])
                px, py = float(pp["x"]), float(pp["y"])
                abx, aby = bx - ax, by - ay
                denom = math.hypot(abx, aby)
                if denom > 1e-12:
                    if "s" in pl:
                        ux, uy = abx / denom, aby / denom
                        target_x = ax + ux * float(pl.get("s", 0.0))
                        target_y = ay + uy * float(pl.get("s", 0.0))
                        dist = math.hypot(px - target_x, py - target_y)
                    else:
                        dist = abs((px - ax) * (-aby) + (py - ay) * abx) / denom
                    max_pl = max(max_pl, dist)

        for ps in self.point_splines.values():
            if not bool(ps.get("enabled", True)):
                continue
            p_id = int(ps.get("p", -1))
            s_id = int(ps.get("s", -1))
            if p_id not in self.points or s_id not in self.splines:
                continue
            cp_ids = [pid for pid in self.splines[s_id].get("points", []) if pid in self.points]
            if len(cp_ids) < 2:
                continue
            pts = [(self.points[cid]["x"], self.points[cid]["y"]) for cid in cp_ids]
            samples = build_spline_samples(pts, samples_per_segment=16, closed=bool(self.splines[s_id].get("closed", False)))
            if len(samples) < 2:
                continue
            px, py = float(self.points[p_id]["x"]), float(self.points[p_id]["y"])
            _cx, _cy, _seg_idx, _t_seg, dist2 = closest_point_on_samples(px, py, samples)
            max_ps = max(max_ps, math.sqrt(dist2))

        max_err = max(max_len, max_ang, max_coin, max_pl, max_ps)
        return max_err, {
            "length": max_len,
            "angle": max_ang,
            "coincide": max_coin,
            "point_line": max_pl,
            "point_spline": max_ps,
        }


def simulate_case(
    model_snapshot: Dict[str, Any],
    case_spec: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    model = HeadlessModel(model_snapshot, case_spec)

    sweep = case_spec.get("sweep", {}) or {}
    start = float(sweep.get("start_deg", sweep.get("start", 0.0)))
    end = float(sweep.get("end_deg", sweep.get("end", 0.0)))
    step_count = sweep.get("step_count", None)
    if step_count is None:
        step = float(sweep.get("step_deg", sweep.get("step", 1.0)))
        step = abs(step) if step != 0 else 1.0
        if end < start:
            step = -step
        step_count = None
    else:
        step = None
        try:
            step_count = int(round(float(step_count)))
        except Exception:
            step_count = 1
        step_count = max(step_count, 1)

    solver = case_spec.get("solver", {}) or {}
    solver_name = str(solver.get("name") or ("scipy" if solver.get("use_scipy", False) else "pbd")).lower()
    if solver_name not in ("pbd", "scipy", "exudyn"):
        solver_name = "pbd"
    max_nfev = int(solver.get("max_nfev", 200))
    pbd_iters = int(solver.get("pbd_iters", 80))
    hard_err_tol = float(solver.get("hard_err_tol", 1e-3))
    treat_point_spline_as_soft = bool(solver.get("treat_point_spline_as_soft", False))

    if solver_name == "scipy":
        ok, _msg = model.solve_constraints_scipy(max_nfev=max_nfev)
        if not ok:
            model.solve_constraints(iters=pbd_iters)
    elif solver_name == "exudyn":
        ok, _msg = model.solve_constraints_exudyn(max_iters=pbd_iters)
        if not ok:
            model.solve_constraints(iters=pbd_iters)
    else:
        model.solve_constraints(iters=pbd_iters)
    model.mark_sim_start_pose()

    frames: List[Dict[str, Any]] = []
    reason = ""
    success = True
    solver_error = ""

    degrees: List[float] = []
    if step_count is None:
        cur = start
        if step > 0:
            while cur <= end + 1e-9:
                degrees.append(cur)
                cur += step
        else:
            while cur >= end - 1e-9:
                degrees.append(cur)
                cur += step
    else:
        for idx in range(step_count):
            progress = (idx + 1) / float(step_count)
            degrees.append(start + (end - start) * progress)

    for frame_idx, deg in enumerate(degrees):
        ok = True
        msg = ""
        if solver_name == "scipy":
            model.drive_to_deg(deg, iters=0)
            ok, msg = model.solve_constraints_scipy(max_nfev=max_nfev)
            if not ok:
                if msg and not solver_error:
                    solver_error = f"scipy: {msg}"
                model.solve_constraints(iters=pbd_iters)
        elif solver_name == "exudyn":
            model.drive_to_deg(deg, iters=0)
            ok, msg = model.solve_constraints_exudyn(max_iters=pbd_iters)
            if not ok:
                if msg and not solver_error:
                    solver_error = f"exudyn: {msg}"
                model.solve_constraints(iters=pbd_iters)
        else:
            model.drive_to_deg(deg, iters=pbd_iters)

        max_err, detail = model.max_constraint_error()
        hard_err = max(detail.get("length", 0.0), detail.get("angle", 0.0), detail.get("coincide", 0.0), detail.get("point_line", 0.0))
        if not treat_point_spline_as_soft:
            hard_err = max(hard_err, detail.get("point_spline", 0.0))

        step_success = bool(ok) and hard_err <= hard_err_tol
        if not step_success:
            success = False
            if not reason:
                reason = msg or "constraint_error"

        rec: Dict[str, Any] = {
            "time": frame_idx,
            "solver": solver_name,
            "success": step_success,
            "input_deg": model.get_input_angle_deg(),
            "output_deg": model.get_output_angle_deg(),
            "hard_err": hard_err,
        }
        for nm, val, _unit in model.get_measure_values():
            rec[nm] = val
        for nm, val in model.get_load_measure_values():
            rec[nm] = val
        frames.append(rec)

    status = {
        "success": success,
        "reason": reason or ("ok" if success else "failed"),
        "solver_error": solver_error or None,
    }
    summary = {
        "success": success,
        "success_rate": (sum(1 for f in frames if f.get("success")) / float(len(frames))) if frames else 0.0,
        "n_steps": len(frames),
        "max_hard_err": max((f.get("hard_err", 0.0) or 0.0) for f in frames) if frames else 0.0,
    }
    return frames, summary, status
