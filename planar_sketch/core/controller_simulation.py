# -*- coding: utf-8 -*-
"""SketchController simulation, loads, trajectories, and measurements."""

from __future__ import annotations

from .controller_common import *


class ControllerSimulation:
    # -------------------- Linkage-style simulation API --------------------
    def set_driver_angle(self, pivot_pid: int, tip_pid: int):
        """Set the input driver as a world-angle direction (pivot -> tip)."""
        driver = self._normalize_driver({
            "enabled": True,
            "type": "angle",
            "pivot": int(pivot_pid),
            "tip": int(tip_pid),
            "sweep_start": self.sweep_settings.get("start", 0.0),
            "sweep_end": self.sweep_settings.get("end", 360.0),
        })
        ang = self.get_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            driver["rad"] = float(ang)
        self.drivers.insert(0, driver)
        self._sync_primary_driver()

    def set_driver_translation(self, plid: int):
        """Set a translational driver for a point-on-line (s) constraint."""
        if plid not in self.point_lines:
            return
        pl = self.point_lines[plid]
        base_s = self._point_line_current_s(pl)
        line_len = 0.0
        try:
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
            if i_id in self.points and j_id in self.points:
                pa = self.points[i_id]
                pb = self.points[j_id]
                line_len = math.hypot(float(pb["x"]) - float(pa["x"]), float(pb["y"]) - float(pa["y"]))
        except Exception:
            line_len = 0.0
        driver = self._normalize_driver({
            "enabled": True,
            "type": "translation",
            "plid": int(plid),
            "s_base": float(base_s),
            "value": 0.0,
            "sweep_start": 0.0,
            "sweep_end": float(line_len),
        })
        self.drivers.insert(0, driver)
        self._sync_primary_driver()

    def clear_driver(self):
        self.drivers = []
        self._sim_zero_driver_rad = []
        self._sync_primary_driver()

    def set_output(self, pivot_pid: int, tip_pid: int):
        """Set the output measurement angle (pivot -> tip)."""
        output = self._normalize_output({
            "enabled": True,
            "pivot": int(pivot_pid),
            "tip": int(tip_pid),
        })
        ang = self.get_angle_rad(int(pivot_pid), int(tip_pid))
        if ang is not None:
            output["rad"] = float(ang)
        self.outputs.insert(0, output)
        self._sync_primary_output()

    def clear_output(self):
        self.outputs = []
        self._sync_primary_output()

    # ---- Quasi-static loads ----
    def add_load_force(self, pid: int, fx: float, fy: float):
        self.loads.append({"type": "force", "pid": int(pid), "fx": float(fx), "fy": float(fy), "mz": 0.0})

    def add_load_torque(self, pid: int, mz: float):
        self.loads.append({"type": "torque", "pid": int(pid), "fx": 0.0, "fy": 0.0, "mz": float(mz)})

    def add_load_spring(self, pid: int, ref_pid: int, k: float, load: float = 0.0):
        self.loads.append({
            "type": "spring",
            "pid": int(pid),
            "ref_pid": int(ref_pid),
            "k": float(k),
            "load": float(load),
            "fx": 0.0,
            "fy": 0.0,
            "mz": 0.0,
        })

    def add_load_torsion_spring(self, pid: int, ref_pid: int, k: float, theta0: float, load: float = 0.0):
        self.loads.append({
            "type": "torsion_spring",
            "pid": int(pid),
            "ref_pid": int(ref_pid),
            "k": float(k),
            "theta0": float(theta0),
            "load": float(load),
            "fx": 0.0,
            "fy": 0.0,
            "mz": 0.0,
        })

    def remove_load_at(self, index: int):
        if 0 <= index < len(self.loads):
            del self.loads[index]

    def clear_loads(self):
        self.loads = []

    # ---- Joint friction ----
    def add_friction_joint(self, pid: int, mu: float = 0.0, diameter: float = 0.0):
        if pid not in self.points:
            return
        self.friction_joints.append({
            "pid": int(pid),
            "mu": float(mu),
            "diameter": float(diameter),
        })

    def remove_friction_joint_at(self, index: int):
        if 0 <= index < len(self.friction_joints):
            del self.friction_joints[index]

    def clear_friction_joints(self):
        self.friction_joints = []

    def get_friction_table(self, use_cached_loads: bool = True) -> List[Dict[str, Any]]:
        if use_cached_loads and self._last_joint_loads:
            joint_loads = list(self._last_joint_loads)
        else:
            joint_loads = self.compute_quasistatic_joint_loads()
        load_map = {
            int(jl.get("pid", -1)): float(jl.get("mag", 0.0))
            for jl in joint_loads
            if int(jl.get("pid", -1)) >= 0
        }
        rows: List[Dict[str, Any]] = []
        for item in self.friction_joints:
            pid = int(item.get("pid", -1))
            mu = float(item.get("mu", 0.0))
            diameter = float(item.get("diameter", 0.0))
            local_load = load_map.get(pid)
            torque = None if local_load is None else float(local_load) * mu * diameter
            rows.append({
                "pid": pid,
                "mu": mu,
                "diameter": diameter,
                "local_load": local_load,
                "torque": torque,
            })
        return rows

    def _prompt_add_force(self, pid: int):
        fx, ok = QInputDialog.getDouble(self.win, "Force X", f"P{pid} Fx", 0.0, decimals=4)
        if not ok:
            return
        fy, ok = QInputDialog.getDouble(self.win, "Force Y", f"P{pid} Fy", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_force(pid, fx, fy)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _prompt_add_torque(self, pid: int):
        mz, ok = QInputDialog.getDouble(self.win, "Torque", f"P{pid} Mz", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_torque(pid, mz)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _prompt_add_spring(self, pid: int, ref_pid: Optional[int] = None):
        if ref_pid is None:
            ref_pid, ok = QInputDialog.getInt(self.win, "Spring", "Direction point ID", 0)
            if not ok:
                return
        if int(ref_pid) not in self.points:
            QMessageBox.information(self.win, "Spring", f"Point P{ref_pid} not found.")
            return
        k, ok = QInputDialog.getDouble(self.win, "Spring", "k (force per length)", 0.0, decimals=4)
        if not ok:
            return
        load, ok = QInputDialog.getDouble(self.win, "Spring", "Load (force)", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_spring(pid, int(ref_pid), k, load)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _prompt_add_torsion_spring(self, pid: int, ref_pid: Optional[int] = None):
        if ref_pid is None:
            ref_pid, ok = QInputDialog.getInt(self.win, "Torsion Spring", "Reference point ID", 0)
            if not ok:
                return
        if int(ref_pid) not in self.points:
            QMessageBox.information(self.win, "Torsion Spring", f"Point P{ref_pid} not found.")
            return
        theta0 = self.get_angle_rad(int(pid), int(ref_pid))
        if theta0 is None:
            QMessageBox.information(self.win, "Torsion Spring", "Reference angle is not defined.")
            return
        k, ok = QInputDialog.getDouble(self.win, "Torsion Spring", "k (torque per rad)", 0.0, decimals=4)
        if not ok:
            return
        load, ok = QInputDialog.getDouble(self.win, "Torsion Spring", "Load (torque)", 0.0, decimals=4)
        if not ok:
            return
        self.add_load_torsion_spring(pid, int(ref_pid), k, float(theta0), load)
        if hasattr(self.win, "sim_panel") and self.win.sim_panel is not None:
            self.win.sim_panel.refresh_labels()

    def _build_quasistatic_constraints(self, point_ids: List[int]) -> List[Callable[[np.ndarray], float]]:
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        funcs: List[Callable[[np.ndarray], float]] = []

        def _xy(q: np.ndarray, pid: int) -> tuple[float, float]:
            idx = idx_map[pid]
            return float(q[2 * idx]), float(q[2 * idx + 1])

        # Fixed points (x, y lock)
        for pid in point_ids:
            p = self.points[pid]
            if not bool(p.get("fixed", False)):
                continue
            x0, y0 = float(p["x"]), float(p["y"])
            funcs.append(lambda q, pid=pid, x0=x0: _xy(q, pid)[0] - x0)
            funcs.append(lambda q, pid=pid, y0=y0: _xy(q, pid)[1] - y0)

        # Coincide constraints (point-point)
        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1))
            b = int(c.get("b", -1))
            if a not in idx_map or b not in idx_map:
                continue
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[0] - _xy(q, b)[0])
            funcs.append(lambda q, a=a, b=b: _xy(q, a)[1] - _xy(q, b)[1])

        # Point-on-line constraints
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

        # Point-on-spline constraints (distance to closest sampled point)
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

            def _pos(q: np.ndarray, p_id=p_id, cp_ids=cp_ids) -> float:
                px, py = _xy(q, p_id)
                samples = build_spline_samples(
                    [_xy(q, cid) for cid in cp_ids],
                    closed=bool(spline.get("closed", False)),
                )
                _, _, _, _, dist2 = closest_point_on_samples(px, py, samples)
                return math.sqrt(dist2)

            funcs.append(_pos)

        # Rigid body edges
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

        # Length constraints (links)
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

        # Angle constraints
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

        # Driver constraint (if enabled)
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
                fz = float(torque_map.get(pid, 0.0))
                mag = math.sqrt(fx * fx + fy * fy + fz * fz)
                out.append({"pid": pid, "fx": fx, "fy": fy, "fz": fz, "mag": mag})
            return out

        def eval_constraints(qvec: np.ndarray) -> np.ndarray:
            return np.array([fn(qvec) for fn in funcs], dtype=float)

        eps = 1e-6
        m = len(eval_constraints(q))
        J = np.zeros((m, ndof), dtype=float)
        for i in range(ndof):
            dq = np.zeros_like(q)
            dq[i] = eps
            fp = eval_constraints(q + dq)
            fm = eval_constraints(q - dq)
            J[:, i] = (fp - fm) / (2.0 * eps)

        if J.size == 0:
            reaction = np.zeros_like(f_ext)
        else:
            try:
                lam, *_ = np.linalg.lstsq(J.T, -f_ext, rcond=None)
                reaction = J.T @ lam
            except np.linalg.LinAlgError:
                reaction = np.zeros_like(f_ext)

        out: List[Dict[str, Any]] = []
        for idx, pid in enumerate(point_ids):
            fx = float(reaction[2 * idx])
            fy = float(reaction[2 * idx + 1])
            fz = float(torque_map.get(pid, 0.0))
            mag = math.sqrt(fx * fx + fy * fy + fz * fz)
            out.append({"pid": pid, "fx": fx, "fy": fy, "fz": fz, "mag": mag})
        return out

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

    # ---- Quasi-static loads ----
    def add_load_force(self, pid: int, fx: float, fy: float):
        self.loads.append({"type": "force", "pid": int(pid), "fx": float(fx), "fy": float(fy), "mz": 0.0})

    def add_load_torque(self, pid: int, mz: float):
        self.loads.append({"type": "torque", "pid": int(pid), "fx": 0.0, "fy": 0.0, "mz": float(mz)})

    def clear_loads(self):
        self.loads = []
    def _build_quasistatic_constraints(
        self,
        point_ids: List[int],
        *,
        include_driver: bool,
        include_output: bool,
    ) -> Tuple[List[Callable[[np.ndarray], float]], List[str], List[Dict[str, Any]]]:
        """Build constraint functions for quasi-static evaluation.

        Returns (funcs, roles, meta) where:
          - roles[i] in {"passive","actuator","output"} for funcs[i]
          - meta[i] provides small bits of info (e.g., type, pivot) for reporting torques.
        """
        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        funcs: List[Callable[[np.ndarray], float]] = []
        roles: List[str] = []
        meta: List[Dict[str, Any]] = []

        def _xy(q: np.ndarray, pid: int) -> tuple[float, float]:
            idx = idx_map[pid]
            return float(q[2 * idx]), float(q[2 * idx + 1])

        def _add(fn: Callable[[np.ndarray], float], role: str, info: Optional[Dict[str, Any]] = None):
            funcs.append(fn)
            roles.append(role)
            meta.append(info or {})

        # Fixed points (x, y lock)
        for pid in point_ids:
            p = self.points[pid]
            if not bool(p.get("fixed", False)):
                continue
            x0, y0 = float(p["x"]), float(p["y"])
            _add(lambda q, pid=pid, x0=x0: _xy(q, pid)[0] - x0, "passive", {"type": "fixed_x", "pid": pid})
            _add(lambda q, pid=pid, y0=y0: _xy(q, pid)[1] - y0, "passive", {"type": "fixed_y", "pid": pid})

        # Coincide constraints (point-point)
        for c in self.coincides.values():
            if not bool(c.get("enabled", True)):
                continue
            a = int(c.get("a", -1))
            b = int(c.get("b", -1))
            if a not in idx_map or b not in idx_map:
                continue
            _add(lambda q, a=a, b=b: _xy(q, a)[0] - _xy(q, b)[0], "passive", {"type": "coincide_x", "a": a, "b": b})
            _add(lambda q, a=a, b=b: _xy(q, a)[1] - _xy(q, b)[1], "passive", {"type": "coincide_y", "a": a, "b": b})

        # Point-on-line constraints
        for pl in self.point_lines.values():
            if not bool(pl.get("enabled", True)):
                continue
            p_id = int(pl.get("p", -1))
            i_id = int(pl.get("i", -1))
            j_id = int(pl.get("j", -1))
            if p_id not in idx_map or i_id not in idx_map or j_id not in idx_map:
                continue

            def _pol(q: np.ndarray, p_id=p_id, i_id=i_id, j_id=j_id) -> float:
                px, py = _xy(q, p_id)
                ax, ay = _xy(q, i_id)
                bx, by = _xy(q, j_id)
                abx, aby = bx - ax, by - ay
                denom = math.hypot(abx, aby)
                if denom < 1e-9:
                    return 0.0
                return ((px - ax) * (-aby) + (py - ay) * abx) / denom

            _add(_pol, "passive", {"type": "point_line", "p": p_id, "i": i_id, "j": j_id})
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

                _add(_pol_s, "passive", {"type": "point_line_s", "p": p_id, "i": i_id, "j": j_id})

        # Point-on-spline constraints (distance to closest sampled point)
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

            def _pos(q: np.ndarray, p_id=p_id, cp_ids=cp_ids) -> float:
                px, py = _xy(q, p_id)
                samples = build_spline_samples(
                    [_xy(q, cid) for cid in cp_ids],
                    closed=bool(spline.get("closed", False)),
                )
                _, _, _, _, dist2 = closest_point_on_samples(px, py, samples)
                return math.sqrt(dist2)

            _add(_pos, "passive", {"type": "point_spline", "p": p_id, "s": s_id})

        # Rigid body edges
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

            _add(_len, "passive", {"type": "rigid_edge", "i": i, "j": j})

        # Length constraints (links)
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

            _add(_len, "passive", {"type": "link_len", "i": i, "j": j})

        # Angle constraints
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

            _add(_ang, "passive", {"type": "angle", "i": i, "j": j, "k": k})

        # Closure / actuator constraints
        # Policy:
        #   - Kinematics uses self.driver (motion input).
        #   - Quasi-static closure uses output constraint if enabled; otherwise uses driver.
        #   - The closure constraint is NOT counted into "Joint Loads" (it is reported separately as a torque).
        if include_output:
            for out in self._active_outputs():
                piv = out.get("pivot")
                tip = out.get("tip")
                if piv in idx_map and tip in idx_map:
                    target = float(out.get("rad", 0.0))

                    def _out(q: np.ndarray, piv=piv, tip=tip, target=target) -> float:
                        px, py = _xy(q, int(piv))
                        tx, ty = _xy(q, int(tip))
                        dx, dy = tx - px, ty - py
                        if abs(dx) + abs(dy) < 1e-12:
                            return 0.0
                        return clamp_angle_rad(math.atan2(dy, dx) - target)

                    _add(_out, "output", {"type": "output_angle", "pivot": int(piv), "tip": int(tip)})
        elif include_driver:
            for drv in self._active_drivers():
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

                    _add(_drv, "actuator", {"type": "driver_angle", "pivot": int(piv), "tip": int(tip)})

        return funcs, roles, meta

    def compute_quasistatic_report(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Compute quasi-static joint loads and a small summary.

        - Motion input (driver) is used for kinematics.
        - If output is enabled, quasi-static closure uses output constraint (so driver will not
          appear as a huge 'constraint load' at the input joint).
        - The closure constraint torque is reported separately as input/output torque.
        """
        point_ids = sorted(list(self.points.keys()))
        if not point_ids:
            summary = {"mode": "none", "tau_input": None, "tau_output": None}
            self._last_quasistatic_summary = dict(summary)
            return [], summary

        idx_map = {pid: idx for idx, pid in enumerate(point_ids)}
        q = np.array([coord for pid in point_ids for coord in (self.points[pid]["x"], self.points[pid]["y"])], dtype=float)
        ndof = len(q)

        # External forces on translational DOFs
        f_ext = np.zeros(ndof, dtype=float)
        applied_force: Dict[int, Tuple[float, float]] = {pid: (0.0, 0.0) for pid in point_ids}

        # Collect applied torques and convert them to equivalent force couples
        applied_torque: Dict[int, float] = {pid: 0.0 for pid in point_ids}

        def _pick_torque_neighbor(pid: int, qvec: np.ndarray) -> Optional[int]:
            # Prefer link neighbors, then rigid edges. Choose the farthest neighbor
            # to reduce the required force magnitude for a given torque.
            neigh: List[int] = []
            for l in self.links.values():
                if l.get("ref", False):
                    continue
                i, j = int(l.get("i", -1)), int(l.get("j", -1))
                if i == pid and j in idx_map:
                    neigh.append(j)
                elif j == pid and i in idx_map:
                    neigh.append(i)
            if not neigh:
                for b in self.bodies.values():
                    for (i, j, _L) in b.get("rigid_edges", []):
                        if i == pid and j in idx_map:
                            neigh.append(int(j))
                        elif j == pid and i in idx_map:
                            neigh.append(int(i))
            if not neigh:
                return None
            i = idx_map[pid]
            xi, yi = float(qvec[2 * i]), float(qvec[2 * i + 1])
            best_nb = None
            best_r2 = -1.0
            for nb in neigh:
                j = idx_map[nb]
                dx = float(qvec[2 * j]) - xi
                dy = float(qvec[2 * j + 1]) - yi
                r2 = dx * dx + dy * dy
                if r2 > best_r2:
                    best_r2 = r2
                    best_nb = nb
            return best_nb

        # Apply loads
        for load in self.loads:
            pid = int(load.get("pid", -1))
            if pid not in idx_map:
                continue
            idx = idx_map[pid]
            fx, fy, mz = self._resolve_load_components(load, q, idx_map)
            f_ext[2 * idx] += fx
            f_ext[2 * idx + 1] += fy
            if abs(fx) > 0.0 or abs(fy) > 0.0:
                cur_fx, cur_fy = applied_force[pid]
                applied_force[pid] = (cur_fx + fx, cur_fy + fy)
            if abs(mz) > 0.0:
                applied_torque[pid] = applied_torque.get(pid, 0.0) + mz

        # Convert each applied torque into a force couple (net force = 0, net moment = Mz)
        for pid, mz in list(applied_torque.items()):
            if abs(mz) < 1e-12:
                continue
            nb = _pick_torque_neighbor(pid, q)
            if nb is None:
                # No neighbor => cannot form a couple; keep it only for display.
                continue
            i = idx_map[pid]
            j = idx_map[nb]
            xi, yi = float(q[2 * i]), float(q[2 * i + 1])
            xj, yj = float(q[2 * j]), float(q[2 * j + 1])
            rx, ry = (xj - xi), (yj - yi)
            r2 = rx * rx + ry * ry
            if r2 < 1e-12:
                continue
            # F such that r x F = mz  =>  F = (mz/r^2) * (-ry, rx)
            scale = float(mz) / r2
            Fx, Fy = (-ry * scale), (rx * scale)
            # Apply +F at neighbor, -F at pid
            f_ext[2 * j] += Fx
            f_ext[2 * j + 1] += Fy
            f_ext[2 * i] -= Fx
            f_ext[2 * i + 1] -= Fy

        # Build constraints for quasi-static
        use_output = bool(self._active_outputs())
        funcs, roles, meta = self._build_quasistatic_constraints(
            point_ids,
            include_driver=bool(self._active_drivers()) and (not use_output),
            include_output=use_output,
        )

        if not funcs:
            # No constraints -> reactions are just the negative external forces.
            joint_loads: List[Dict[str, Any]] = []
            for idx, pid in enumerate(point_ids):
                fx = -float(f_ext[2 * idx])
                fy = -float(f_ext[2 * idx + 1])
                mag = math.hypot(fx, fy)
                joint_loads.append({"pid": pid, "fx": fx, "fy": fy, "mag": mag})
            self._last_joint_loads = list(joint_loads)
            summary = {"mode": "none", "tau_input": None, "tau_output": None}
            self._last_quasistatic_summary = dict(summary)
            return joint_loads, summary

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

        summary: Dict[str, Any] = {"mode": "output" if use_output else ("driver" if self._active_drivers() else "none")}
        summary["tau_input"] = None
        summary["tau_output"] = None

        if J.size == 0:
            lam = np.zeros(m, dtype=float)
        else:
            try:
                lam, *_ = np.linalg.lstsq(J.T, -f_ext, rcond=None)
            except np.linalg.LinAlgError:
                lam = np.zeros(m, dtype=float)

        # Report closure torques (do NOT include in joint loads table)
        lam = np.asarray(lam, dtype=float)
        for k, role in enumerate(roles):
            if role == "actuator":
                # Driver torque (only used when output is disabled)
                summary["tau_input"] = float(lam[k]) if summary.get("tau_input") is None else float(summary["tau_input"]) + float(lam[k])
            elif role == "output":
                summary["tau_output"] = float(lam[k]) if summary.get("tau_output") is None else float(summary["tau_output"]) + float(lam[k])

        # Joint loads: use passive constraints for pin force, and include output closure for net balance.
        mask_passive = np.array([1.0 if r == "passive" else 0.0 for r in roles], dtype=float)
        mask_net = np.array(
            [1.0 if (r == "passive" or (use_output and r == "output")) else 0.0 for r in roles],
            dtype=float,
        )
        fixed_types = {"fixed_x", "fixed_y"}
        mask_fixed = np.array(
            [1.0 if meta[k].get("type") in fixed_types else 0.0 for k in range(len(roles))],
            dtype=float,
        )
        mask_nonrigid = np.array(
            [
                1.0
                if (roles[k] == "passive" and meta[k].get("type") not in {"rigid_edge", *fixed_types})
                else 0.0
                for k in range(len(roles))
            ],
            dtype=float,
        )
        lam_passive = lam * mask_passive
        lam_net = lam * mask_net
        lam_fixed = lam * mask_fixed
        lam_nonrigid = lam * mask_nonrigid
        reaction_passive = J.T @ lam_passive if J.size else np.zeros_like(f_ext)
        reaction_net = J.T @ lam_net if J.size else np.zeros_like(f_ext)
        reaction_fixed = J.T @ lam_fixed if J.size else np.zeros_like(f_ext)
        reaction_nonrigid = J.T @ lam_nonrigid if J.size else np.zeros_like(f_ext)

        link_reactions: Dict[int, Tuple[float, float, float]] = {}
        if J.size:
            for k, info in enumerate(meta):
                if info.get("type") != "link_len":
                    continue
                for end_key in ("i", "j"):
                    pid = int(info.get(end_key, -1))
                    if pid not in idx_map:
                        continue
                    idx = idx_map[pid]
                    fx_k = float(J[k, 2 * idx] * lam[k])
                    fy_k = float(J[k, 2 * idx + 1] * lam[k])
                    mag_k = math.hypot(fx_k, fy_k)
                    if mag_k <= 0.0:
                        continue
                    prev = link_reactions.get(pid)
                    if prev is None or mag_k > prev[2]:
                        link_reactions[pid] = (fx_k, fy_k, mag_k)

        spline_reactions: Dict[int, Tuple[float, float, float]] = {}
        if J.size:
            for k, info in enumerate(meta):
                if info.get("type") != "point_spline":
                    continue
                pid = int(info.get("p", -1))
                if pid not in idx_map:
                    continue
                idx = idx_map[pid]
                fx_k = float(J[k, 2 * idx] * lam[k])
                fy_k = float(J[k, 2 * idx + 1] * lam[k])
                mag_k = math.hypot(fx_k, fy_k)
                if mag_k <= 0.0:
                    continue
                prev = spline_reactions.get(pid)
                if prev is None or mag_k > prev[2]:
                    spline_reactions[pid] = (fx_k, fy_k, mag_k)

        joint_loads: List[Dict[str, Any]] = []
        for idx, pid in enumerate(point_ids):
            point = self.points[pid]
            if bool(point.get("fixed", False)):
                fx = float(reaction_fixed[2 * idx])
                fy = float(reaction_fixed[2 * idx + 1])
            elif pid in link_reactions:
                fx, fy, _mag = link_reactions[pid]
            elif pid in spline_reactions:
                fx, fy, _mag = spline_reactions[pid]
            else:
                applied_fx, applied_fy = applied_force.get(pid, (0.0, 0.0))
                if abs(applied_fx) > 0.0 or abs(applied_fy) > 0.0:
                    fx = float(reaction_net[2 * idx])
                    fy = float(reaction_net[2 * idx + 1])
                else:
                    fx = float(reaction_nonrigid[2 * idx])
                    fy = float(reaction_nonrigid[2 * idx + 1])
            mag = math.hypot(fx, fy)
            joint_loads.append({"pid": pid, "fx": fx, "fy": fy, "mag": mag})

        self._last_joint_loads = list(joint_loads)
        self._last_quasistatic_summary = dict(summary)
        return joint_loads, summary

    def compute_quasistatic_joint_loads(self) -> List[Dict[str, Any]]:
        # Backwards-compatible wrapper for UI code that expects just the table rows.
        joint_loads, _summary = self.compute_quasistatic_report()
        return joint_loads


    # ---- Trajectories ----
    def set_show_trajectories(self, enabled: bool, reset: bool = False):
        self.show_trajectories = bool(enabled)
        if reset:
            self.reset_trajectories()
        self.update_graphics()

    def reset_trajectories(self):
        for pid, p in self.points.items():
            titem = p.get("traj_item")
            if titem is not None:
                titem.reset_path(p["x"], p["y"])

    def append_trajectories(self):
        if not self.show_trajectories or self._drag_active:
            return
        for pid, p in self.points.items():
            if not bool(p.get("traj", False)):
                continue
            titem = p.get("traj_item")
            if titem is not None:
                titem.add_point(p["x"], p["y"])

    # ---- Measurements ----
    def add_measure_angle(self, pivot_pid: int, tip_pid: int):
        name = f"ang P{int(pivot_pid)}->P{int(tip_pid)}"
        self.measures.append({"type": "angle", "pivot": int(pivot_pid), "tip": int(tip_pid), "name": name})

    def add_measure_joint(self, i_pid: int, j_pid: int, k_pid: int):
        name = f"ang P{int(i_pid)}-P{int(j_pid)}-P{int(k_pid)}"
        self.measures.append({"type": "joint", "i": int(i_pid), "j": int(j_pid), "k": int(k_pid), "name": name})

    def add_measure_translation(self, plid: int):
        if plid not in self.point_lines:
            return
        for m in self.measures:
            if str(m.get("type", "")).lower() == "translation" and int(m.get("plid", -1)) == int(plid):
                return
        pl = self.point_lines[plid]
        name = str(pl.get("name", "")) or self._point_line_offset_name(pl)
        self.measures.append({"type": "translation", "plid": int(plid), "name": name})

    def clear_measures(self):
        self.measures = []
        self.load_measures = []

    def remove_measure_at(self, index: int):
        if index < 0 or index >= len(self.measures):
            return
        self.measures.pop(index)

    def add_load_measure_joint(self, pid: int, component: str):
        component = component.lower()
        label = {"fx": "Fx", "fy": "Fy", "mag": "Mag"}.get(component, component)
        name = f"load P{int(pid)} {label}"
        self.load_measures.append({"type": "joint_load", "pid": int(pid), "component": component, "name": name})

    def clear_load_measures(self):
        self.load_measures = []

    def remove_load_measure_at(self, index: int):
        if index < 0 or index >= len(self.load_measures):
            return
        self.load_measures.pop(index)

    def get_measure_values(self) -> List[tuple[str, Optional[float], str]]:
        """Return measurement values with units.

        If a sweep has started (Play), angle values are reported relative to the Play-start pose
        (i.e., value==0 at the starting pose).
        """
        out: List[tuple[str, Optional[float], str]] = []
        for m in self.measures:
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
                    out.append((nm, None, "mm"))
                else:
                    nm = str(nm) or str(pl.get("name", "")) or self._point_line_offset_name(pl)
                    sval = float(self._point_line_current_s(pl))
                    if nm in self._sim_zero_meas_len:
                        out.append((nm, sval - float(self._sim_zero_meas_len[nm]), "mm"))
                    else:
                        out.append((nm, sval, "mm"))
                continue

            if abs_deg is None:
                out.append((nm, None, "deg"))
                continue

            if nm in self._sim_zero_meas_deg:
                out.append((nm, self._rel_deg(abs_deg, float(self._sim_zero_meas_deg[nm])), "deg"))
            else:
                out.append((nm, abs_deg, "deg"))
        return out

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

    # ---- Angles ----
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

    # ---- Relative-zero helpers (for simulation) ----
    @staticmethod
    def _rel_deg(abs_deg: float, base_deg: float) -> float:
        """Return relative angle in [0, 360) degrees."""
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

    def _get_output_angle_abs_rad_for(self, output: Dict[str, Any]) -> Optional[float]:
        if not output or not output.get("enabled"):
            return None
        piv = output.get("pivot")
        tip = output.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_angle_rad(int(piv), int(tip))

    def _get_driver_angle_abs_rad(self, driver: Dict[str, Any]) -> Optional[float]:
        if not driver or not driver.get("enabled"):
            return None
        if driver.get("type") != "angle":
            return None
        piv = driver.get("pivot")
        tip = driver.get("tip")
        if piv is None or tip is None:
            return None
        return self.get_angle_rad(int(piv), int(tip))

    def get_input_angle_deg(self) -> Optional[float]:
        """Current input angle in degrees.

        When a sweep has started (Play), 0° is defined as the pose at Play-start.
        """
        ang = self._get_input_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_input_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_input_rad)
        return self._rel_deg(abs_deg, base_deg)

    def get_driver_angles_deg(self) -> List[Optional[float]]:
        """Current driver angles in degrees (relative to Play-start if available)."""
        result: List[Optional[float]] = []
        drivers = self._active_drivers()
        for idx, drv in enumerate(drivers):
            ang = self._get_driver_angle_abs_rad(drv)
            if ang is None:
                result.append(None)
                continue
            abs_deg = math.degrees(ang)
            base_rad: Optional[float] = None
            if self._sim_zero_driver_rad and idx < len(self._sim_zero_driver_rad):
                base_rad = self._sim_zero_driver_rad[idx]
            elif idx == 0 and self._sim_zero_input_rad is not None:
                base_rad = self._sim_zero_input_rad
            if base_rad is None:
                result.append(abs_deg)
            else:
                result.append(self._rel_deg(abs_deg, math.degrees(base_rad)))
        return result

    def get_driver_display_values(self) -> List[tuple[Optional[float], str]]:
        """Return driver values for display (value, unit)."""
        out: List[tuple[Optional[float], str]] = []
        drivers = self._active_drivers()
        for idx, drv in enumerate(drivers):
            dtype = str(drv.get("type", "angle"))
            if dtype == "angle":
                ang = self._get_driver_angle_abs_rad(drv)
                if ang is None:
                    out.append((None, "deg"))
                    continue
                abs_deg = math.degrees(ang)
                base_rad: Optional[float] = None
                if self._sim_zero_driver_rad and idx < len(self._sim_zero_driver_rad):
                    base_rad = self._sim_zero_driver_rad[idx]
                elif idx == 0 and self._sim_zero_input_rad is not None:
                    base_rad = self._sim_zero_input_rad
                if base_rad is None:
                    out.append((abs_deg, "deg"))
                else:
                    out.append((self._rel_deg(abs_deg, math.degrees(base_rad)), "deg"))
                continue
            if dtype == "translation":
                plid = drv.get("plid")
                pl = self.point_lines.get(plid) if plid in self.point_lines else None
                if pl is None:
                    base_s = float(drv.get("s_base", 0.0) or 0.0)
                    out.append((base_s + float(drv.get("value", 0.0) or 0.0), "mm"))
                else:
                    out.append((float(pl.get("s", self._point_line_current_s(pl)) or 0.0), "mm"))
                continue
            out.append((None, ""))
        return out

    def get_output_angle_deg(self) -> Optional[float]:
        """Current output angle in degrees (relative to Play-start if available)."""
        ang = self._get_output_angle_abs_rad()
        if ang is None:
            return None
        abs_deg = math.degrees(ang)
        if self._sim_zero_output_rad is None:
            return abs_deg
        base_deg = math.degrees(self._sim_zero_output_rad)
        return self._rel_deg(abs_deg, base_deg)

    def get_output_angles_deg(self) -> List[Optional[float]]:
        """Current output angles in degrees (relative to Play-start for the primary)."""
        result: List[Optional[float]] = []
        outputs = [o for o in self.outputs if o.get("enabled")]
        for idx, out in enumerate(outputs):
            ang = self._get_output_angle_abs_rad_for(out)
            if ang is None:
                result.append(None)
                continue
            abs_deg = math.degrees(ang)
            if idx == 0 and self._sim_zero_output_rad is not None:
                result.append(self._rel_deg(abs_deg, math.degrees(self._sim_zero_output_rad)))
            else:
                result.append(abs_deg)
        return result

    def drive_to_deg(self, deg: float, iters: int = 80):
        """Drive the mechanism to a *relative* input angle (deg) and solve constraints.

        If Play has started, 0° corresponds to the Play-start pose.
        """
        if not self._active_drivers() and not self._active_outputs():
            return

        # Target = (Play-start absolute angle) + delta
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
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()

    def drive_to_multi_deg(self, deg_list: List[float], iters: int = 80):
        """Drive multiple active drivers to relative angles (deg) and solve constraints."""
        active_drivers = self._active_drivers()
        if not active_drivers:
            return
        for idx, drv in enumerate(active_drivers):
            if idx >= len(deg_list):
                break
            base_rad = None
            if idx < len(self._sim_zero_driver_rad):
                base_rad = self._sim_zero_driver_rad[idx]
            if base_rad is None:
                base_rad = self._get_driver_angle_abs_rad(drv)
            target = math.radians(float(deg_list[idx]))
            if base_rad is not None:
                target = float(base_rad) + target
            drv["rad"] = float(target)
        self._sync_primary_driver()
        self.solve_constraints(iters=iters)
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()

    def drive_to_multi_values(self, values: List[float], iters: int = 80):
        """Drive multiple active drivers to target values (deg or mm) and solve constraints."""
        active_drivers = self._active_drivers()
        if not active_drivers:
            return
        for idx, drv in enumerate(active_drivers):
            if idx >= len(values):
                break
            dtype = str(drv.get("type", "angle"))
            if dtype == "angle":
                target_deg = float(values[idx])
                base_rad: Optional[float] = None
                if idx < len(self._sim_zero_driver_rad) and self._sim_zero_driver_rad[idx] is not None:
                    base_rad = self._sim_zero_driver_rad[idx]
                elif idx == 0 and self._sim_zero_input_rad is not None:
                    base_rad = self._sim_zero_input_rad
                if base_rad is None:
                    drv["rad"] = math.radians(target_deg)
                else:
                    drv["rad"] = float(base_rad) + math.radians(target_deg)
            elif dtype == "translation":
                target_s = float(values[idx])
                plid = drv.get("plid")
                pl = self.point_lines.get(plid) if plid in self.point_lines else None
                if pl is None:
                    base_s = float(drv.get("s_base", 0.0) or 0.0)
                else:
                    base_s = float(drv.get("s_base", self._point_line_current_s(pl)) or 0.0)
                    pl["s"] = target_s
                drv["value"] = target_s - base_s
        self._sync_primary_driver()
        self.solve_constraints(iters=iters)
        self.update_graphics()
        self.append_trajectories()
        if self.panel:
            self.panel.defer_refresh_all()

    # ---- Pose snapshots ----
    def capture_initial_pose_if_needed(self):
        if self._pose_initial is None:
            self._pose_initial = self.snapshot_points()

    def mark_sim_start_pose(self):
        """Capture pose + set the 'relative zero' for input/output/measures."""
        self._pose_last_sim_start = self.snapshot_points()
        self.capture_initial_pose_if_needed()

        # Set relative-zero angles based on the current pose.
        self._sim_zero_input_rad = self._get_input_angle_abs_rad()
        self._sim_zero_output_rad = self._get_output_angle_abs_rad()
        self._sim_zero_driver_rad = []
        for drv in self._active_drivers():
            self._sim_zero_driver_rad.append(self._get_driver_angle_abs_rad(drv))
        if self._sim_zero_output_rad is not None and self.outputs:
            self.outputs[0]["rad"] = float(self._sim_zero_output_rad)
            self._sync_primary_output()

        self._sim_zero_meas_deg = {}
        self._sim_zero_meas_len = {}
        for (nm, val, unit) in self.get_measure_values():
            # At this moment get_measure_values returns ABS (since _sim_zero_meas_deg is cleared)
            if val is None:
                continue
            if unit == "deg":
                self._sim_zero_meas_deg[str(nm)] = float(val)
            elif unit == "mm":
                self._sim_zero_meas_len[str(nm)] = float(val)

    def update_sim_start_pose_snapshot(self):
        """Update the stored sweep start pose without touching the relative-zero angles."""
        self._pose_last_sim_start = self.snapshot_points()
        self.capture_initial_pose_if_needed()

    def reset_pose_to_sim_start(self) -> bool:
        if not self._pose_last_sim_start:
            return False
        self.apply_points_snapshot(self._pose_last_sim_start)
        if self.drivers and self._sim_zero_input_rad is not None:
            self.drivers[0]["rad"] = float(self._sim_zero_input_rad)
            self._sync_primary_driver()
        if self._sim_zero_driver_rad:
            for idx, drv in enumerate(self._active_drivers()):
                if idx >= len(self._sim_zero_driver_rad):
                    break
                if self._sim_zero_driver_rad[idx] is not None:
                    drv["rad"] = float(self._sim_zero_driver_rad[idx])
        if self.outputs and self._sim_zero_output_rad is not None:
            self.outputs[0]["rad"] = float(self._sim_zero_output_rad)
            self._sync_primary_output()
        self.solve_constraints()
        self.update_graphics()
        if self.panel:
            self.panel.defer_refresh_all(keep_selection=True)
        return True

    def reset_pose_to_initial(self) -> bool:
        if not self._pose_initial:
            return False
        self.apply_points_snapshot(self._pose_initial)
        self.solve_constraints()
        self.update_graphics()
        if self.panel:
            self.panel.defer_refresh_all(keep_selection=True)
        return True
