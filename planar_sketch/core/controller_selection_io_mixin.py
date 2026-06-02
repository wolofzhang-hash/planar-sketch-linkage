# -*- coding: utf-8 -*-
"""Project serialization/schema IO methods extracted from ControllerSelection.

Boundary/dependencies (provided by host class):
- scene/state containers (points/links/angles/...) and registries
- command/build helpers used during load/merge
- optional UI references are accessed defensively (``win``, ``panel``)
"""

from __future__ import annotations

import uuid

from .controller_common import *
from .user_curve_store import deserialize_user_curve_store, serialize_user_curve_store
from ..version import PROJECT_SCHEMA_VERSION


class ControllerSelectionIOMixin:
    """Extracted mixin; host supplies state and methods."""

    def clear_project_user_curves(self) -> None:
            self._user_measure_curves = {}

    def _serialize_user_curve_store(self) -> list[Dict[str, Any]]:
            store = getattr(self, "_user_measure_curves", {}) or {}
            return serialize_user_curve_store(store)

    def _deserialize_user_curve_store(self, rows: Any) -> Dict[str, Dict[str, Any]]:
            return deserialize_user_curve_store(rows)

    def _serialize_load(self, ld: Dict[str, Any]) -> Dict[str, Any]:
            ltype = str(ld.get("type", "force") or "force").lower()
            out: Dict[str, Any] = {
                "type": ltype,
                "pid": int(ld.get("pid", -1)),
                "fx": float(ld.get("fx", 0.0) or 0.0),
                "fy": float(ld.get("fy", 0.0) or 0.0),
                "mz": float(ld.get("mz", 0.0) or 0.0),
                "fx_expr": str(ld.get("fx_expr", "") or ""),
                "fy_expr": str(ld.get("fy_expr", "") or ""),
                "mz_expr": str(ld.get("mz_expr", "") or ""),
            }
            if ltype in {"spring", "torsion_spring"}:
                out.update({
                    "ref_pid": int(ld.get("ref_pid", -1)),
                    "k": float(ld.get("k", 0.0) or 0.0),
                    "load": float(ld.get("load", 0.0) or 0.0),
                    "k_expr": str(ld.get("k_expr", "") or ""),
                    "load_expr": str(ld.get("load_expr", "") or ""),
                })
            if ltype == "torsion_spring":
                out["theta0"] = float(ld.get("theta0", 0.0) or 0.0)
            return out

    def _load_float(self, data: Dict[str, Any], key: str, default: float = 0.0) -> float:
            try:
                return float(data.get(key, default) or default)
            except Exception:
                return default

    def to_dict(self) -> Dict[str, Any]:
            payload = self.default_project_dict(project_uuid=self._ensure_project_uuid())
            simulation_settings = dict(getattr(self, "simulation_settings", {}) or {})
            optimization_settings = dict(getattr(self, "optimization_settings", {}) or {})
            measurement_settings = {
                "measures": list(self.measures),
                "load_measures": list(self.load_measures),
            }
            win = getattr(self, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            if sim_panel is not None:
                if hasattr(sim_panel, "get_simulation_settings"):
                    simulation_settings = sim_panel.get_simulation_settings()
                opt_tab = getattr(sim_panel, "optimization_tab", None)
                if opt_tab is not None and hasattr(opt_tab, "export_settings"):
                    optimization_settings = opt_tab.export_settings()
            if simulation_settings:
                self.simulation_settings = dict(simulation_settings)
            if optimization_settings:
                self.optimization_settings = dict(optimization_settings)
            payload.update(
                {
                    "display_precision": int(getattr(self, "display_precision", 3)),
                    "load_arrow_width": float(getattr(self, "load_arrow_width", 1.6)),
                    "torque_arrow_width": float(getattr(self, "torque_arrow_width", 1.6)),
                    "parameters": self.parameters.to_list(),
                    "background_image": {
                        "path": self.background_image.get("path"),
                        "visible": bool(self.background_image.get("visible", True)),
                        "opacity": float(self.background_image.get("opacity", 0.6)),
                        "grayscale": bool(self.background_image.get("grayscale", False)),
                        "scale": float(self.background_image.get("scale", 1.0)),
                        "pos": list(self.background_image.get("pos", (0.0, 0.0))),
                    },
                    "grid_settings": {
                        "show_horizontal": bool(self.grid_settings.get("show_horizontal", False)),
                        "show_vertical": bool(self.grid_settings.get("show_vertical", False)),
                        "spacing_x": float(self.grid_settings.get("spacing_x", 100.0)),
                        "spacing_y": float(self.grid_settings.get("spacing_y", 100.0)),
                        "range_x": float(self.grid_settings.get("range_x", 2000.0)),
                        "range_y": float(self.grid_settings.get("range_y", 2000.0)),
                        "center": list(self.grid_settings.get("center", (0.0, 0.0))),
                    },
                    "points": [
                        {
                            "id": pid,
                            "x": p["x"], "y": p["y"],
                            "x_expr": (p.get("x_expr") or ""),
                            "y_expr": (p.get("y_expr") or ""),
                            "fixed": bool(p.get("fixed", False)),
                            "hidden": bool(p.get("hidden", False)),
                            "traj": bool(p.get("traj", False)),
                        }
                        for pid, p in sorted(self.points.items(), key=lambda kv: kv[0])
                    ],
                    "constraints": self.constraint_registry.to_list(),
                    "links": [
                        {
                            "id": lid, "i": l["i"], "j": l["j"],
                            "L": l["L"],
                            "L_expr": (l.get("L_expr") or ""),
                            "hidden": bool(l.get("hidden", False)),
                            "ref": bool(l.get("ref", False)),
                        }
                        for lid, l in sorted(self.links.items(), key=lambda kv: kv[0])
                    ],
                    "angles": [
                        {
                            "id": aid, "i": a["i"], "j": a["j"], "k": a["k"],
                            "deg": a["deg"],
                            "deg_expr": (a.get("deg_expr") or ""),
                            "hidden": bool(a.get("hidden", False)),
                            "enabled": bool(a.get("enabled", True)),
                        }
                        for aid, a in sorted(self.angles.items(), key=lambda kv: kv[0])
                    ],
                    "splines": [
                        {
                            "id": sid,
                            "points": list(s.get("points", [])),
                            "hidden": bool(s.get("hidden", False)),
                            "closed": bool(s.get("closed", False)),
                        }
                        for sid, s in sorted(self.splines.items(), key=lambda kv: kv[0])
                    ],
                    "coincides": [
                        {"id": cid, "a": c["a"], "b": c["b"], "hidden": bool(c.get("hidden", False)), "enabled": bool(c.get("enabled", True))}
                        for cid, c in sorted(self.coincides.items(), key=lambda kv: kv[0])
                    ],
                    "point_lines": [
                        {
                            "id": plid,
                            "p": pl.get("p"),
                            "i": pl.get("i"),
                            "j": pl.get("j"),
                            "hidden": bool(pl.get("hidden", False)),
                            "enabled": bool(pl.get("enabled", True)),
                            **({"s": float(pl.get("s", 0.0))} if "s" in pl else {}),
                            **({"s_expr": str(pl.get("s_expr", ""))} if pl.get("s_expr") else {}),
                            **({"name": str(pl.get("name", ""))} if pl.get("name") else {}),
                        }
                        for plid, pl in sorted(self.point_lines.items(), key=lambda kv: kv[0])
                    ],
                    "point_splines": [
                        {"id": psid, "p": ps.get("p"), "s": ps.get("s"),
                         "hidden": bool(ps.get("hidden", False)), "enabled": bool(ps.get("enabled", True))}
                        for psid, ps in sorted(self.point_splines.items(), key=lambda kv: kv[0])
                    ],
                    "bodies": [
                        {"id": bid, "name": b.get("name", f"B{bid}"), "points": list(b.get("points", [])),
                         "hidden": bool(b.get("hidden", False)), "color_name": b.get("color_name", "Blue"),
                         "rigid_edges": list(b.get("rigid_edges", []))}
                        for bid, b in sorted(self.bodies.items(), key=lambda kv: kv[0])
                    ],
                    "driver": {
                        "enabled": bool(self.driver.get("enabled", False)),
                        "type": str(self.driver.get("type", "angle")),
                        "pivot": self.driver.get("pivot"),
                        "tip": self.driver.get("tip"),
                        "rad": float(self.driver.get("rad", 0.0)),
                        "plid": self.driver.get("plid"),
                        "s_base": self.driver.get("s_base"),
                        "value": self.driver.get("value"),
                        "sweep_start": self.driver.get("sweep_start"),
                        "sweep_end": self.driver.get("sweep_end"),
                    },
                    "drivers": [
                        {
                            "enabled": bool(d.get("enabled", False)),
                            "type": str(d.get("type", "angle")),
                            "pivot": d.get("pivot"),
                            "tip": d.get("tip"),
                            "rad": float(d.get("rad", 0.0)),
                            "plid": d.get("plid"),
                            "s_base": d.get("s_base"),
                            "value": d.get("value"),
                            "sweep_start": d.get("sweep_start"),
                            "sweep_end": d.get("sweep_end"),
                        }
                        for d in self.drivers
                    ],
                    "output": {
                        "enabled": bool(self.output.get("enabled", False)),
                        "pivot": self.output.get("pivot"),
                        "tip": self.output.get("tip"),
                        "rad": float(self.output.get("rad", 0.0)),
                    },
                    "outputs": [
                        {
                            "enabled": bool(o.get("enabled", False)),
                            "pivot": o.get("pivot"),
                            "tip": o.get("tip"),
                            "rad": float(o.get("rad", 0.0)),
                        }
                        for o in self.outputs
                    ],
                    "measures": [
                        {
                            "type": str(m.get("type", "")),
                            "name": str(m.get("name", "")),
                            "pivot": m.get("pivot"),
                            "tip": m.get("tip"),
                            "i": m.get("i"),
                            "j": m.get("j"),
                            "k": m.get("k"),
                        }
                        for m in self.measures
                    ],
                    "loads": [self._serialize_load(ld) for ld in self.loads],
                    "load_measures": [
                        {
                            "type": str(lm.get("type", "joint_load")),
                            "pid": int(lm.get("pid", -1)),
                            "component": str(lm.get("component", "mag")),
                            "name": str(lm.get("name", "")),
                        }
                        for lm in self.load_measures
                    ],
                    "friction_joints": [
                        {
                            "pid": int(fj.get("pid", -1)),
                            "mu": float(fj.get("mu", 0.0)),
                            "diameter": float(fj.get("diameter", 0.0)),
                            "mu_expr": str(fj.get("mu_expr", "") or ""),
                            "diameter_expr": str(fj.get("diameter_expr", "") or ""),
                        }
                        for fj in self.friction_joints
                    ],
                    "sweep": {
                        "start": float(self.sweep_settings.get("start", 0.0)),
                        "end": float(self.sweep_settings.get("end", 360.0)),
                        "step": float(self.sweep_settings.get("step", 200.0)),
                    },
                    "measurement_settings": measurement_settings,
                    "simulation_settings": simulation_settings,
                    "optimization_settings": optimization_settings,
                    "user_measure_curves": self._serialize_user_curve_store(),
                }
            )
            return payload

    def _ensure_project_uuid(self, candidate: Optional[str] = None) -> str:
            if candidate and isinstance(candidate, str) and candidate.strip():
                self.project_uuid = candidate.strip()
            if not getattr(self, "project_uuid", ""):
                self.project_uuid = str(uuid.uuid4())
            return self.project_uuid

    def default_project_dict(self, project_uuid: Optional[str] = None, force_new_uuid: bool = False) -> Dict[str, Any]:
            if force_new_uuid:
                uuid_val = str(uuid.uuid4())
                self.project_uuid = uuid_val
            else:
                uuid_val = self._ensure_project_uuid(project_uuid)
            return {
                "version": PROJECT_SCHEMA_VERSION,
                "project_uuid": uuid_val,
                "display_precision": int(getattr(self, "display_precision", 3)),
                "load_arrow_width": float(getattr(self, "load_arrow_width", 1.6)),
                "torque_arrow_width": float(getattr(self, "torque_arrow_width", 1.6)),
                "parameters": [],
                "background_image": {
                    "path": None,
                    "visible": True,
                    "opacity": 0.6,
                    "grayscale": False,
                    "scale": 1.0,
                    "pos": [0.0, 0.0],
                },
                "grid_settings": {
                    "show_horizontal": False,
                    "show_vertical": False,
                    "spacing_x": 100.0,
                    "spacing_y": 100.0,
                    "range_x": 2000.0,
                    "range_y": 2000.0,
                    "center": [0.0, 0.0],
                },
                "points": [],
                "constraints": [],
                "links": [],
                "angles": [],
                "splines": [],
                "coincides": [],
                "point_lines": [],
                "point_splines": [],
                "bodies": [],
                "driver": dict(self._default_driver()),
                "drivers": [],
                "output": dict(self._default_output()),
                "outputs": [],
                "measures": [],
                "loads": [],
                "load_measures": [],
                "friction_joints": [],
                "sweep": {
                    "start": float(self.sweep_settings.get("start", 0.0)),
                    "end": float(self.sweep_settings.get("end", 360.0)),
                    "step": float(self.sweep_settings.get("step", 200.0)),
                },
                "measurement_settings": {
                    "measures": [],
                    "load_measures": [],
                },
                "simulation_settings": dict(getattr(self, "simulation_settings", {}) or {}),
                "optimization_settings": dict(getattr(self, "optimization_settings", {}) or {}),
                "user_measure_curves": [],
            }

    def merge_project_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
            has_uuid = isinstance(data, dict) and str(data.get("project_uuid", "")).strip()
            base = self.default_project_dict(
                project_uuid=(data.get("project_uuid") if has_uuid else None),
                force_new_uuid=not has_uuid,
            )
            if not isinstance(data, dict):
                return base
            for key, val in data.items():
                if key in (
                    "background_image",
                    "grid_settings",
                    "driver",
                    "output",
                    "sweep",
                    "measurement_settings",
                    "simulation_settings",
                    "optimization_settings",
                ) and isinstance(val, dict):
                    base[key] = {**base.get(key, {}), **val}
                else:
                    base[key] = val
            return base

    def validate_project_schema(self, data: Any) -> tuple[list[str], list[str]]:
            warnings: list[str] = []
            errors: list[str] = []
            if not isinstance(data, dict):
                errors.append("Project data must be a JSON object.")
                return warnings, errors
            schema_keys = {
                "version",
                "project_uuid",
                "display_precision",
                "load_arrow_width",
                "torque_arrow_width",
                "parameters",
                "background_image",
                "grid_settings",
                "points",
                "constraints",
                "links",
                "angles",
                "splines",
                "coincides",
                "point_lines",
                "point_splines",
                "bodies",
                "driver",
                "drivers",
                "output",
                "outputs",
                "measures",
                "loads",
                "load_measures",
                "friction_joints",
                "sweep",
                "measurement_settings",
                "simulation_settings",
                "optimization_settings",
                "user_measure_curves",
            }
            for key in sorted(schema_keys):
                if key not in data:
                    warnings.append(f"Missing key: {key}")
            list_keys = [
                "points",
                "constraints",
                "links",
                "angles",
                "splines",
                "coincides",
                "point_lines",
                "point_splines",
                "bodies",
                "parameters",
                "drivers",
                "outputs",
                "measures",
                "loads",
                "load_measures",
                "friction_joints",
                "user_measure_curves",
            ]
            dict_keys = [
                "background_image",
                "grid_settings",
                "driver",
                "output",
                "sweep",
                "measurement_settings",
                "simulation_settings",
                "optimization_settings",
            ]
            for key in list_keys:
                if key in data and not isinstance(data.get(key), list):
                    errors.append(f"Key '{key}' should be a list.")
            for key in dict_keys:
                if key in data and not isinstance(data.get(key), dict):
                    errors.append(f"Key '{key}' should be an object.")
            if "project_uuid" in data and not isinstance(data.get("project_uuid"), str):
                errors.append("Key 'project_uuid' should be a string.")
            return warnings, errors

    def load_dict(self, data: Dict[str, Any], clear_undo: bool = True, action: str = "load a new model") -> bool:
            if not self._confirm_stop_replay(action):
                return False
            if isinstance(data, dict):
                self._ensure_project_uuid(data.get("project_uuid"))
            else:
                self._ensure_project_uuid()
            if hasattr(self.win, "sim_panel"):
                self.win.sim_panel.stop()
                if hasattr(self.win.sim_panel, "animation_tab"):
                    self.win.sim_panel.animation_tab.stop_replay()
            self._drag_active = False
            self._drag_pid = None
            self._drag_before = None
            # (No intelligent-design insertion cache is kept.)
            background_info = data.get("background_image") or data.get("background") or {}
            self.background_image = {
                "path": None,
                "visible": True,
                "opacity": 0.6,
                "grayscale": False,
                "scale": 1.0,
                "pos": (0.0, 0.0),
            }
            if isinstance(background_info, dict):
                self.background_image["path"] = background_info.get("path")
                self.background_image["visible"] = bool(background_info.get("visible", True))
                self.background_image["opacity"] = float(background_info.get("opacity", 0.6))
                self.background_image["grayscale"] = bool(background_info.get("grayscale", False))
                self.background_image["scale"] = float(background_info.get("scale", 1.0))
                pos = background_info.get("pos", (0.0, 0.0))
                try:
                    self.background_image["pos"] = (float(pos[0]), float(pos[1]))
                except Exception:
                    self.background_image["pos"] = (0.0, 0.0)
            grid_info = data.get("grid_settings") or {}
            self.grid_settings = {
                "show_horizontal": False,
                "show_vertical": False,
                "spacing_x": 100.0,
                "spacing_y": 100.0,
                "range_x": 2000.0,
                "range_y": 2000.0,
                "center": (0.0, 0.0),
            }
            if isinstance(grid_info, dict):
                self.grid_settings["show_horizontal"] = bool(grid_info.get("show_horizontal", False))
                self.grid_settings["show_vertical"] = bool(grid_info.get("show_vertical", False))
                self.grid_settings["spacing_x"] = max(0.1, float(grid_info.get("spacing_x", 100.0)))
                self.grid_settings["spacing_y"] = max(0.1, float(grid_info.get("spacing_y", 100.0)))
                self.grid_settings["range_x"] = max(0.0, float(grid_info.get("range_x", 2000.0)))
                self.grid_settings["range_y"] = max(0.0, float(grid_info.get("range_y", 2000.0)))
                center = grid_info.get("center", (0.0, 0.0))
                try:
                    self.grid_settings["center"] = (float(center[0]), float(center[1]))
                except Exception:
                    self.grid_settings["center"] = (0.0, 0.0)
            sweep_info = data.get("sweep", {}) or {}
            try:
                sweep_start = float(sweep_info.get("start", self.sweep_settings.get("start", 0.0)))
            except Exception:
                sweep_start = self.sweep_settings.get("start", 0.0)
            try:
                sweep_end = float(sweep_info.get("end", self.sweep_settings.get("end", 360.0)))
            except Exception:
                sweep_end = self.sweep_settings.get("end", 360.0)
            try:
                sweep_step = float(sweep_info.get("step", self.sweep_settings.get("step", 200.0)))
            except Exception:
                sweep_step = self.sweep_settings.get("step", 200.0)
            sweep_step = abs(sweep_step)
            if sweep_step == 0:
                sweep_step = float(self.sweep_settings.get("step", 200.0)) or 200.0
            self.sweep_settings = {"start": sweep_start, "end": sweep_end, "step": sweep_step}
            if hasattr(self.win, "sim_panel"):
                self.win.sim_panel.apply_sweep_settings(self.sweep_settings)
            raw_sim_settings = data.get("simulation_settings", {}) or {}
            try:
                max_nfev = int(float(raw_sim_settings.get("max_nfev", 250)))
            except Exception:
                max_nfev = 250
            solver_name = str(raw_sim_settings.get("solver") or ("scipy" if raw_sim_settings.get("use_scipy", True) else "pbd"))
            self.simulation_settings = {
                "solver": solver_name,
                "max_nfev": max_nfev,
                "reset_before_run": bool(raw_sim_settings.get("reset_before_run", True)),
            }
            raw_opt_settings = data.get("optimization_settings", {}) or {}
            self.optimization_settings = dict(raw_opt_settings) if isinstance(raw_opt_settings, dict) else {}
            self.scene.blockSignals(True)
            try:
                self.scene.clear()
                self.points.clear(); self.links.clear(); self.angles.clear(); self.splines.clear(); self.bodies.clear(); self.coincides.clear(); self.point_lines.clear(); self.point_splines.clear(); self.point_spline_dists.clear()
                self._background_item = None
                self._background_image_original = None
                self._grid_item = None
            finally:
                self.scene.blockSignals(False)
            self._load_arrow_items = []
            self._torque_arrow_items = []
            self._friction_torque_arrow_items = []
            self._last_joint_loads = []
            # Load parameters early so expression fields can be evaluated during/after construction.
            self.parameters.load_list(list(data.get("parameters", []) or []))
            self.selected_point_ids.clear()
            self.selected_point_id = None; self.selected_link_id = None; self.selected_angle_id = None; self.selected_spline_id = None; self.selected_body_id = None; self.selected_coincide_id = None; self.selected_point_line_id = None; self.selected_point_spline_id = None; self.selected_point_spline_dist_id = None
            pts = data.get("points", [])
            # Unified constraints list (Stage-1). If present, it overrides legacy links/angles/coincides.
            constraints_list = data.get("constraints", None)
            if constraints_list:
                from .constraints_registry import ConstraintRegistry as _CR
                lks, angs, spls, coincs, pls, pss, pds = _CR.split_constraints(constraints_list)
            else:
                lks = data.get("links", [])
                angs = data.get("angles", [])
                spls = data.get("splines", [])
                coincs = data.get("coincides", [])
                pls = data.get("point_lines", [])
                pss = data.get("point_splines", [])
                pds = data.get("point_spline_dists", [])
            if constraints_list:
                spls = data.get("splines", [])
                legacy_point_lines = data.get("point_lines", []) or []
                legacy_point_splines = data.get("point_splines", []) or []
                legacy_point_spline_dists = data.get("point_spline_dists", []) or []
                existing_plids = {int(pl.get("id", -1)) for pl in (pls or [])}
                existing_psids = {int(ps.get("id", -1)) for ps in (pss or [])}
                existing_pdids = {int(pd.get("id", -1)) for pd in (pds or [])}
                for pl in legacy_point_lines:
                    try:
                        plid = int(pl.get("id", -1))
                    except Exception:
                        continue
                    if plid in existing_plids:
                        continue
                    pls = list(pls or []) + [pl]
                    existing_plids.add(plid)
                for ps in legacy_point_splines:
                    try:
                        psid = int(ps.get("id", -1))
                    except Exception:
                        continue
                    if psid in existing_psids:
                        continue
                    pss = list(pss or []) + [ps]
                    existing_psids.add(psid)
                for pd in legacy_point_spline_dists:
                    try:
                        pdid = int(pd.get("id", -1))
                    except Exception:
                        continue
                    if pdid in existing_pdids:
                        continue
                    pds = list(pds or []) + [pd]
                    existing_pdids.add(pdid)
            bods = data.get("bodies", [])
            driver = data.get("driver", {}) or {}
            output = data.get("output", {}) or {}
            drivers_list = data.get("drivers", None)
            outputs_list = data.get("outputs", None)
            measurement_settings = data.get("measurement_settings", {}) or {}
            measures = measurement_settings.get("measures", data.get("measures", []) or []) or []
            self.display_precision = int(data.get("display_precision", getattr(self, "display_precision", 3)))
            self.load_arrow_width = float(data.get("load_arrow_width", getattr(self, "load_arrow_width", 1.6)))
            self.torque_arrow_width = float(data.get("torque_arrow_width", getattr(self, "torque_arrow_width", 1.6)))
            loads = data.get("loads", []) or []
            load_measures = measurement_settings.get("load_measures", data.get("load_measures", []) or []) or []
            friction_joints = data.get("friction_joints", []) or []
            self._user_measure_curves = self._deserialize_user_curve_store(data.get("user_measure_curves", []) or [])
            bg_path = self.background_image.get("path")
            if bg_path:
                image = QImage(bg_path)
                if not image.isNull():
                    self._background_image_original = image
                    self._ensure_background_item()
                    self._apply_background_pixmap()
                    scale = float(self.background_image.get("scale", 1.0))
                    pos = self.background_image.get("pos", (0.0, 0.0))
                    if self._background_item is not None:
                        self._background_item.setScale(scale)
                        self._background_item.setPos(float(pos[0]), float(pos[1]))
                    self.set_background_visible(bool(self.background_image.get("visible", True)))
                    self.set_background_opacity(float(self.background_image.get("opacity", 0.6)))
                    self.set_background_grayscale(bool(self.background_image.get("grayscale", False)))
                else:
                    self.background_image["path"] = None
                    self._background_image_original = None
            max_pid = -1
            any_traj_enabled = False
            for p in pts:
                pid = int(p["id"]); max_pid = max(max_pid, pid)
                self._create_point(
                    pid,
                    float(p.get("x", 0.0)),
                    float(p.get("y", 0.0)),
                    bool(p.get("fixed", False)),
                    bool(p.get("hidden", False)),
                    traj_enabled=bool(p.get("traj", False)),
                )
                any_traj_enabled = any_traj_enabled or bool(p.get("traj", False))
                if pid in self.points:
                    self.points[pid]["x_expr"] = str(p.get("x_expr", "") or "")
                    self.points[pid]["y_expr"] = str(p.get("y_expr", "") or "")
            if any_traj_enabled:
                self.show_trajectories = True
            max_lid = -1
            for l in lks:
                lid = int(l["id"]); max_lid = max(max_lid, lid)
                self._create_link(lid, int(l.get("i")), int(l.get("j")), float(l.get("L", 1.0)),
                                  bool(l.get("hidden", False)))
                self.links[lid]["ref"] = bool(l.get("ref", False))
                self.links[lid]["L_expr"] = str(l.get("L_expr", "") or "")
            max_aid = -1
            for a in angs:
                aid = int(a["id"]); max_aid = max(max_aid, aid)
                self._create_angle(aid, int(a.get("i")), int(a.get("j")), int(a.get("k")),
                                   float(a.get("deg", 0.0)), bool(a.get("hidden", False)))
                if aid in self.angles:
                    self.angles[aid]["deg_expr"] = str(a.get("deg_expr", "") or "")
            max_sid = -1
            for s in spls:
                sid = int(s.get("id", -1)); max_sid = max(max_sid, sid)
                pts = list(s.get("points", []))
                self._create_spline(sid, pts, bool(s.get("hidden", False)), closed=bool(s.get("closed", False)))
            max_bid = -1
            for b in bods:
                bid = int(b["id"]); max_bid = max(max_bid, bid)
                self._create_body(bid, b.get("name", f"B{bid}"), list(b.get("points", [])),
                                  bool(b.get("hidden", False)), color_name=b.get("color_name", "Blue"))
                if "rigid_edges" in b and b["rigid_edges"]:
                    self.bodies[bid]["rigid_edges"] = [tuple(x) for x in b["rigid_edges"]]

            self.drivers = []
            if isinstance(drivers_list, list) and drivers_list:
                for drv in drivers_list:
                    if not isinstance(drv, dict):
                        continue
                    normalized = self._normalize_driver(drv)
                    if "rad" not in drv:
                        normalized["_needs_rad"] = True
                    self.drivers.append(normalized)
            elif isinstance(driver, dict) and driver:
                legacy_driver = self._normalize_driver(driver)
                if legacy_driver.get("enabled"):
                    if "rad" not in driver:
                        legacy_driver["_needs_rad"] = True
                    self.drivers.append(legacy_driver)

            for drv in self.drivers:
                if not drv.pop("_needs_rad", False):
                    continue
                dtype = str(drv.get("type", "angle"))
                if dtype != "angle":
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
                    if not isinstance(out, dict):
                        continue
                    normalized = self._normalize_output(out)
                    if "rad" not in out:
                        normalized["_needs_rad"] = True
                    self.outputs.append(normalized)
            elif isinstance(output, dict) and output:
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
            self.measures = []
            for m in measures:
                mtype = str(m.get("type", "")).lower()
                name = str(m.get("name", ""))
                if mtype == "angle":
                    pivot = m.get("pivot")
                    tip = m.get("tip")
                    if pivot is None or tip is None:
                        continue
                    if int(pivot) in self.points and int(tip) in self.points:
                        self.measures.append({
                            "type": "angle",
                            "pivot": int(pivot),
                            "tip": int(tip),
                            "name": name or f"ang P{int(pivot)}->P{int(tip)}",
                        })
                elif mtype == "joint":
                    i = m.get("i")
                    j = m.get("j")
                    k = m.get("k")
                    if i is None or j is None or k is None:
                        continue
                    if int(i) in self.points and int(j) in self.points and int(k) in self.points:
                        self.measures.append({
                            "type": "joint",
                            "i": int(i),
                            "j": int(j),
                            "k": int(k),
                            "name": name or f"ang P{int(i)}-P{int(j)}-P{int(k)}",
                        })
            self.loads = []
            for ld in loads:
                pid = int(ld.get("pid", -1))
                if pid not in self.points:
                    continue
                ltype = str(ld.get("type", "force")).lower()
                fx = self._load_float(ld, "fx", 0.0)
                fy = self._load_float(ld, "fy", 0.0)
                mz = self._load_float(ld, "mz", 0.0)
                fx_expr = str(ld.get("fx_expr", "") or "")
                fy_expr = str(ld.get("fy_expr", "") or "")
                mz_expr = str(ld.get("mz_expr", "") or "")
                k_expr = str(ld.get("k_expr", "") or "")
                load_expr = str(ld.get("load_expr", "") or "")
                if ltype == "torque":
                    self.add_load_torque(pid, mz)
                    self.loads[-1].update({
                        "fx": fx,
                        "fy": fy,
                        "fx_expr": fx_expr,
                        "fy_expr": fy_expr,
                        "mz_expr": mz_expr,
                    })
                elif ltype == "spring":
                    ref_pid = int(ld.get("ref_pid", -1))
                    k = self._load_float(ld, "k", 0.0)
                    preload = self._load_float(ld, "load", 0.0)
                    if ref_pid in self.points:
                        self.add_load_spring(pid, ref_pid, k, preload)
                        self.loads[-1].update({
                            "k_expr": k_expr,
                            "load_expr": load_expr,
                            "theta0": theta0,
                        })
                elif ltype == "torsion_spring":
                    ref_pid = int(ld.get("ref_pid", -1))
                    k = self._load_float(ld, "k", 0.0)
                    theta0 = self._load_float(ld, "theta0", 0.0)
                    preload = self._load_float(ld, "load", 0.0)
                    if ref_pid in self.points:
                        self.add_load_torsion_spring(pid, ref_pid, k, theta0, preload)
                        self.loads[-1].update({
                            "k_expr": k_expr,
                            "load_expr": load_expr,
                        })
                else:
                    self.add_load_force(pid, fx, fy)
                    self.loads[-1].update({
                        "mz": mz,
                        "fx_expr": fx_expr,
                        "fy_expr": fy_expr,
                        "mz_expr": mz_expr,
                    })

            self.load_measures = []
            for lm in load_measures:
                pid = int(lm.get("pid", -1))
                if pid not in self.points:
                    continue
                comp = str(lm.get("component", "mag"))
                name = str(lm.get("name", "")) or f"load P{pid} {comp}"
                self.load_measures.append({
                    "type": str(lm.get("type", "joint_load")),
                    "pid": int(pid),
                    "component": comp,
                    "name": name,
                })

            self.friction_joints = []
            for fj in friction_joints:
                try:
                    pid = int(fj.get("pid", -1))
                except Exception:
                    continue
                if pid not in self.points:
                    continue
                try:
                    mu = float(fj.get("mu", 0.0))
                except Exception:
                    mu = 0.0
                try:
                    diameter = float(fj.get("diameter", 0.0))
                except Exception:
                    diameter = 0.0
                mu_expr = str(fj.get("mu_expr", "") or "")
                diameter_expr = str(fj.get("diameter_expr", "") or "")
                self.friction_joints.append({
                    "pid": pid,
                    "mu": mu,
                    "diameter": diameter,
                    "mu_expr": mu_expr,
                    "diameter_expr": diameter_expr,
                })
        
            # --- Coincide constraints ---
            coincs = coincs or []
            max_cid = -1
            for c in coincs:
                try:
                    cid = int(c.get("id"))
                    a = int(c.get("a")); b = int(c.get("b"))
                except Exception:
                    continue
                max_cid = max(max_cid, cid)
                if a in self.points and b in self.points:
                    self._create_coincide(
                        cid, a, b,
                        hidden=bool(c.get("hidden", False)),
                        enabled=bool(c.get("enabled", True)),
                    )
            self._next_cid = max(max_cid + 1, 0)

            # --- Point-on-line constraints ---
            pls = pls or []
            max_plid = -1
            for pl in pls:
                try:
                    plid = int(pl.get("id"))
                    p = int(pl.get("p")); i = int(pl.get("i")); j = int(pl.get("j"))
                except Exception:
                    continue
                max_plid = max(max_plid, plid)
                if p in self.points and i in self.points and j in self.points and i != j and p != i and p != j:
                    s_expr = str(pl.get("s_expr", ""))
                    name = str(pl.get("name", ""))
                    s_val = None
                    if "s" in pl or s_expr:
                        try:
                            s_val = float(pl.get("s", 0.0))
                        except Exception:
                            s_val = 0.0
                    self._create_point_line(
                        plid, p, i, j,
                        hidden=bool(pl.get("hidden", False)),
                        enabled=bool(pl.get("enabled", True)),
                        s=s_val,
                        s_expr=s_expr,
                        name=name,
                    )
            self._next_plid = max(max_plid + 1, 0)

            # --- Point-on-spline constraints ---
            pss = pss or []
            max_psid = -1
            for ps in pss:
                try:
                    psid = int(ps.get("id"))
                    p = int(ps.get("p")); s = int(ps.get("s"))
                except Exception:
                    continue
                max_psid = max(max_psid, psid)
                if p in self.points and s in self.splines:
                    self._create_point_spline(
                        psid, p, s,
                        hidden=bool(ps.get("hidden", False)),
                        enabled=bool(ps.get("enabled", True)),
                    )
            self._next_psid = max(max_psid + 1, 0)

            # --- Point-to-spline distance constraints ---
            pds = pds or []
            max_pdid = -1
            for pd in pds:
                try:
                    pdid = int(pd.get("id"))
                    p = int(pd.get("p")); s = int(pd.get("s"))
                    dist = float(pd.get("dist", pd.get("r", 0.0)))
                except Exception:
                    continue
                max_pdid = max(max_pdid, pdid)
                if p in self.points and s in self.splines:
                    self._create_point_spline_dist(
                        pdid, p, s, dist,
                        hidden=bool(pd.get("hidden", False)),
                        enabled=bool(pd.get("enabled", True)),
                        hint_seg=int(pd.get("hint_seg", -1)),
                    )
            self._next_pdid = max(max_pdid + 1, 0)

            self._next_pid = max(max_pid + 1, 0)
            self._next_lid = max(max_lid + 1, 0)
            self._next_aid = max(max_aid + 1, 0)
            self._next_sid = max(max_sid + 1, 0)
            self._next_bid = max(max_bid + 1, 0)
            self.mode = "Idle"; self._line_sel = []; self._co_master = None; self._pol_master = None; self._pol_line_sel = []; self._pos_master = None
            if hasattr(self.win, "sim_panel"):
                self.win.sim_panel.apply_simulation_settings(self.simulation_settings)
                opt_tab = getattr(self.win.sim_panel, "optimization_tab", None)
                if opt_tab is not None and hasattr(opt_tab, "apply_settings"):
                    opt_tab.apply_settings(self.optimization_settings)
                curves_tab = getattr(self.win.sim_panel, "curves_tab", None)
                if curves_tab is not None and hasattr(curves_tab, "refresh_curves"):
                    curves_tab.refresh_curves(silent=True)
            self._refresh_grid_item()
            self.solve_constraints(); self.update_graphics()
            if self.panel: self.panel.defer_refresh_all()
            if clear_undo: self.stack.clear()
            self.update_status()
            return True

