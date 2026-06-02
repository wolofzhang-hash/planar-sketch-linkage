# -*- coding: utf-8 -*-
"""Shared simulation query/load helper methods for controller and headless models.

Boundary/dependencies (provided by host class):
- geometry/state containers: ``points``, ``load_measures``
- simulation APIs: ``compute_quasistatic_joint_loads()``, ``_primary_driver()``, ``_primary_output()``
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from .geometry import angle_between


class SimulationQueryLoadMixin:
    """Extracted mixin; host supplies state and methods."""

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

    @staticmethod
    def _rel_deg(abs_deg: float, base_deg: float) -> float:
            return (abs_deg - base_deg) % 360.0

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

