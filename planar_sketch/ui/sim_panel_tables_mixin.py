# -*- coding: utf-8 -*-
"""Table/measurement/load handlers extracted from ``SimulationPanel``.

Boundary/dependencies (provided by host ``SimulationPanel``):
- ``ctrl`` controller with simulation/query APIs
- UI widgets referenced here (labels/tables/buttons)
- host callbacks like ``_update_used_solver_label()`` and ``optimization_tab`` refresh hooks
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QTableWidgetItem

from ..core.expression_registry import PARAMETER_FUNCTIONS
from .panel_common_i18n import panel_lang as _lang, panel_tr as _tr



class SimulationPanelTablesMixin:
    """Mixin for SimulationPanel table refresh/edit flows."""

    def refresh_labels(self):
            drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
            outputs = [o for o in self.ctrl.outputs if o.get("enabled")]
            if drivers:
                labels = []
                for d in drivers:
                    if d.get("type") == "angle" and d.get("pivot") is not None and d.get("tip") is not None:
                        labels.append(_tr(self, "sim.driver_angle").format(pivot=d["pivot"], tip=d["tip"]))
                    elif d.get("type") == "translation":
                        plid = d.get("plid")
                        pl = self.ctrl.point_lines.get(plid, None)
                        if pl:
                            labels.append(_tr(self, "sim.driver_translation").format(p=pl.get("p"), i=pl.get("i"), j=pl.get("j")))
                        else:
                            labels.append(_tr(self, "sim.driver_translation_invalid"))
                    else:
                        labels.append(_tr(self, "sim.driver_invalid"))
                if len(labels) == 1:
                    self.lbl_driver.setText(labels[0])
                else:
                    self.lbl_driver.setText(_tr(self, "sim.driver_multi").format(drivers="; ".join(labels)))
            else:
                if outputs:
                    self.lbl_driver.setText(_tr(self, "sim.driver_using_output"))
                else:
                    self.lbl_driver.setText(_tr(self, "sim.driver_unset"))

            if outputs:
                labels = []
                for o in outputs:
                    if o.get("pivot") is not None and o.get("tip") is not None:
                        labels.append(_tr(self, "sim.output_angle").format(pivot=o["pivot"], tip=o["tip"]))
                    else:
                        labels.append(_tr(self, "sim.output_unset"))
                if len(labels) == 1:
                    self.lbl_output.setText(labels[0])
                else:
                    self.lbl_output.setText(_tr(self, "sim.output_multi").format(outputs="; ".join(labels)))
            else:
                self.lbl_output.setText(_tr(self, "sim.output_unset"))

            self._refresh_driver_table(drivers)
            self._refresh_output_table(outputs)
            self._refresh_load_tables()
            self._refresh_friction_table()
            self._update_used_solver_label()
            if hasattr(self, "optimization_tab"):
                self.optimization_tab.refresh_active_case()
                self.optimization_tab.refresh_model_values()

    def _driver_label(self, driver: Dict[str, Any]) -> str:
            if driver.get("type") == "angle" and driver.get("pivot") is not None and driver.get("tip") is not None:
                return _tr(self, "sim.driver_angle").format(pivot=driver["pivot"], tip=driver["tip"])
            if driver.get("type") == "translation":
                plid = driver.get("plid")
                pl = self.ctrl.point_lines.get(plid, None)
                if pl:
                    return _tr(self, "sim.driver_translation").format(p=pl.get("p"), i=pl.get("i"), j=pl.get("j"))
                return _tr(self, "sim.driver_translation_invalid")
            return _tr(self, "sim.driver_invalid")

    def _refresh_driver_table(self, drivers: List[Dict[str, Any]]) -> None:
            values = self.ctrl.get_driver_display_values()
            self.table_drivers.blockSignals(True)
            try:
                self.table_drivers.setRowCount(len(drivers))
                for row, drv in enumerate(drivers):
                    label = f"{row + 1}. {self._driver_label(drv)}"
                    start_val = drv.get("sweep_start", self.ctrl.sweep_settings.get("start", 0.0))
                    end_val = drv.get("sweep_end", self.ctrl.sweep_settings.get("end", 360.0))
                    value_val, _unit = values[row] if row < len(values) else (None, "")
                    items = [
                        QTableWidgetItem(label),
                        QTableWidgetItem(f"{float(start_val)}"),
                        QTableWidgetItem(f"{float(end_val)}"),
                        QTableWidgetItem("--" if value_val is None else self.ctrl.format_number(value_val)),
                    ]
                    items[0].setFlags(items[0].flags() & ~Qt.ItemFlag.ItemIsEditable)
                    items[3].setFlags(items[3].flags())
                    for col, item in enumerate(items):
                        self.table_drivers.setItem(row, col, item)
            finally:
                self.table_drivers.blockSignals(False)

    def _output_label(self, output: Dict[str, Any]) -> str:
            if output.get("pivot") is not None and output.get("tip") is not None:
                return _tr(self, "sim.output_angle").format(pivot=output["pivot"], tip=output["tip"])
            return _tr(self, "sim.output_unset")

    def _refresh_output_table(self, outputs: List[Dict[str, Any]]) -> None:
            angles = self.ctrl.get_output_angles_deg()
            self.table_outputs.blockSignals(True)
            try:
                self.table_outputs.setRowCount(len(outputs))
                for row, out in enumerate(outputs):
                    label = f"{row + 1}. {self._output_label(out)}"
                    angle_val = angles[row] if row < len(angles) else None
                    items = [
                        QTableWidgetItem(label),
                        QTableWidgetItem("--" if angle_val is None else self.ctrl.format_number(angle_val)),
                    ]
                    for item in items:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    for col, item in enumerate(items):
                        self.table_outputs.setItem(row, col, item)
            finally:
                self.table_outputs.blockSignals(False)

    def _on_driver_table_changed(self, row: int, col: int) -> None:
            active_drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
            if row < 0 or row >= len(active_drivers):
                return
            if col not in (1, 2, 3):
                return
            item = self.table_drivers.item(row, col)
            if item is None:
                return
            try:
                value = float(item.text())
            except Exception:
                if col == 3:
                    QMessageBox.warning(self, _tr(self, "sweep.title"), _tr(self, "sweep.msg.angle_must_be_numbers"))
                else:
                    QMessageBox.warning(self, _tr(self, "sweep.title"), _tr(self, "sweep.msg.start_end_numbers"))
                self._refresh_driver_table(active_drivers)
                return
            if col in (1, 2):
                key = "sweep_start" if col == 1 else "sweep_end"
                active_drivers[row][key] = value
                if len(active_drivers) == 1:
                    self.ctrl.sweep_settings[key.replace("sweep_", "")] = value
                self.refresh_labels()
                return
            display_vals = [val if val is not None else 0.0 for val, _unit in self.ctrl.get_driver_display_values()]
            if row >= len(display_vals):
                self._refresh_driver_table(active_drivers)
                return
            display_vals[row] = value
            self.ctrl.drive_to_multi_values(display_vals, iters=80)
            self.refresh_labels()

    def _clear_driver(self):
            row = self.table_drivers.currentRow()
            if row >= 0:
                active_drivers = [d for d in self.ctrl.drivers if d.get("enabled")]
                if row < len(active_drivers):
                    target = active_drivers[row]
                    for idx, drv in enumerate(self.ctrl.drivers):
                        if drv is target:
                            del self.ctrl.drivers[idx]
                            break
                self.ctrl._sync_primary_driver()
            else:
                self.ctrl.clear_driver()
            self.refresh_labels()

    def _clear_output(self):
            self.ctrl.clear_output()
            self.refresh_labels()

    def _measurement_expression_functions(self) -> Dict[str, List[str]]:
            return {
                "Functions": ["max(", "min(", "mean(", "rms(", "abs(", "first(", "last("],
                "Operators": ["+", "-", "*", "/", "(", ")", ","],
            }

    def _measurement_expression_tokens(self) -> Dict[str, List[str]]:
            measurements = [name for name, _val, _unit in self.ctrl.get_measure_values()]
            load_measures = [name for name, _val in self.ctrl.get_load_measure_values()]
            groups: Dict[str, List[str]] = {}
            if measurements:
                groups["Measurements"] = sorted({str(item) for item in measurements if str(item).strip()})
            if load_measures:
                groups["Load Measurements"] = sorted({str(item) for item in load_measures if str(item).strip()})
            return groups

    def _measurement_expression_signals(self) -> Dict[str, float]:
            signals: Dict[str, float] = {}
            for nm, val, _unit in self.ctrl.get_measure_values():
                if nm and val is not None:
                    signals[str(nm)] = float(val)
            for nm, val in self.ctrl.get_load_measure_values():
                if nm and val is not None:
                    signals[str(nm)] = float(val)
            return signals

    def _delete_selected_measure(self):
            row = self.table_meas.currentRow()
            if row < 0:
                QMessageBox.information(self, _tr(self, "measurements.title"), _tr(self, "measurements.msg.select_row_delete"))
                return
            if row >= len(self._measure_row_map):
                QMessageBox.information(self, _tr(self, "measurements.title"), _tr(self, "measurements.msg.select_row_delete"))
                return
            row_info = self._measure_row_map[row]
            if row_info["kind"] == "measure":
                self.ctrl.remove_measure_at(row_info["index"])
            elif row_info["kind"] == "load":
                self.ctrl.remove_load_measure_at(row_info["index"])
            elif row_info["kind"] == "point_line":
                QMessageBox.information(self, _tr(self, "measurements.title"), _tr(self, "measurements.msg.point_on_line_tied"))
            self.refresh_labels()

    def _refresh_measure_table(self):
            all_measures = self.ctrl.get_measure_values()
            mv = [(nm, val, unit) for (nm, val, unit) in all_measures if unit == "deg"]
            mv_line = [(nm, val, unit) for (nm, val, unit) in all_measures if unit != "deg"]
            load_mv = self.ctrl.get_load_measure_values()
            self._measure_row_map = []
            total_rows = len(mv) + len(mv_line) + len(load_mv)
            self.table_meas.setRowCount(total_rows)
            row = 0
            for index, (nm, val, unit) in enumerate(mv):
                type_item = QTableWidgetItem(_tr(self, "sim.measurement"))
                name_item = QTableWidgetItem(str(nm))
                if val is None:
                    value_text = "--"
                elif unit == "deg":
                    value_text = f"{self.ctrl.format_number(val)}°"
                else:
                    value_text = f"{self.ctrl.format_number(val)} {unit}"
                value_item = QTableWidgetItem(value_text)
                for item in (type_item, name_item, value_item):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_meas.setItem(row, 0, type_item)
                self.table_meas.setItem(row, 1, name_item)
                self.table_meas.setItem(row, 2, value_item)
                self._measure_row_map.append({"kind": "measure", "index": index})
                row += 1
            for index, (nm, val, unit) in enumerate(mv_line):
                type_item = QTableWidgetItem(_tr(self, "sim.measurement"))
                name_item = QTableWidgetItem(str(nm))
                value_item = QTableWidgetItem("--" if val is None else f"{self.ctrl.format_number(val)} {unit}")
                for item in (type_item, name_item, value_item):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_meas.setItem(row, 0, type_item)
                self.table_meas.setItem(row, 1, name_item)
                self.table_meas.setItem(row, 2, value_item)
                self._measure_row_map.append({"kind": "point_line", "index": index})
                row += 1
            for index, (nm, val) in enumerate(load_mv):
                type_item = QTableWidgetItem(_tr(self, "sim.load"))
                name_item = QTableWidgetItem(str(nm))
                value_item = QTableWidgetItem("--" if val is None else self.ctrl.format_number(val))
                for item in (type_item, name_item, value_item):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_meas.setItem(row, 0, type_item)
                self.table_meas.setItem(row, 1, name_item)
                self.table_meas.setItem(row, 2, value_item)
                self._measure_row_map.append({"kind": "load", "index": index})
                row += 1

    def _add_force_from_selection(self):
            pid = self._selected_one_point()
            if pid is None:
                return
            fx, ok = QInputDialog.getDouble(
                self,
                "Force X",
                "Fx",
                0.0,
                decimals=int(self.ctrl.display_precision),
            )
            if not ok:
                return
            fy, ok = QInputDialog.getDouble(
                self,
                "Force Y",
                "Fy",
                0.0,
                decimals=int(self.ctrl.display_precision),
            )
            if not ok:
                return
            self.ctrl.add_load_force(pid, fx, fy)
            self.refresh_labels()

    def _add_torque_from_selection(self):
            pid = self._selected_one_point()
            if pid is None:
                return
            mz, ok = QInputDialog.getDouble(
                self,
                "Torque",
                "Mz (out-of-plane)",
                0.0,
                decimals=int(self.ctrl.display_precision),
            )
            if not ok:
                return
            self.ctrl.add_load_torque(pid, mz)
            self.refresh_labels()

    def _clear_loads(self):
            self.ctrl.clear_loads()
            self.refresh_labels()

    def _remove_selected_load(self):
            row = self.table_loads.currentRow()
            if row < 0:
                QMessageBox.information(self, _tr(self, "loads.title"), _tr(self, "loads.msg.select_row_remove"))
                return
            self.ctrl.remove_load_at(row)
            self.refresh_labels()

    def _add_friction_from_selection(self):
            pid = self._selected_one_point()
            if pid is None:
                return
            self.ctrl.add_friction_joint(pid, 0.0, 0.0)
            self.refresh_labels()

    def _remove_selected_friction(self):
            row = self.table_friction.currentRow()
            if row < 0:
                QMessageBox.information(self, _tr(self, "friction.title"), _tr(self, "friction.msg.select_row_remove"))
                return
            self.ctrl.remove_friction_joint_at(row)
            self.refresh_labels()

    def _on_load_table_changed(self, row: int, col: int) -> None:
            if col not in (2, 3, 4, 5, 6, 7):
                return
            if row < 0 or row >= len(self.ctrl.loads):
                return
            item = self.table_loads.item(row, col)
            if item is None:
                return
            load = self.ctrl.loads[row]
            ltype = str(load.get("type", "force")).lower()
            if col in (2, 3, 4) and ltype in ("force", "torque"):
                key_map = {
                    2: ("fx", "fx_expr"),
                    3: ("fy", "fy_expr"),
                    4: ("mz", "mz_expr"),
                }
                key_num, key_expr = key_map.get(col, ("", ""))
                if not key_num:
                    return
                raw = item.text().strip()
                try:
                    value = float(raw)
                except ValueError:
                    if not raw:
                        self._refresh_load_tables()
                        return
                    self.ctrl.loads[row][key_expr] = raw
                    self.ctrl.recompute_from_parameters()
                else:
                    self.ctrl.loads[row][key_num] = value
                    self.ctrl.loads[row][key_expr] = ""
            elif col == 5 and ltype in ("spring", "torsion_spring"):
                raw = item.text().strip()
                try:
                    value = float(raw)
                except ValueError:
                    if not raw:
                        self._refresh_load_tables()
                        return
                    self.ctrl.loads[row]["k_expr"] = raw
                    self.ctrl.recompute_from_parameters()
                else:
                    self.ctrl.loads[row]["k"] = value
                    self.ctrl.loads[row]["k_expr"] = ""
            elif col == 6 and ltype in ("spring", "torsion_spring"):
                raw = item.text().strip()
                try:
                    value = float(raw)
                except ValueError:
                    if not raw:
                        self._refresh_load_tables()
                        return
                    self.ctrl.loads[row]["load_expr"] = raw
                    self.ctrl.recompute_from_parameters()
                else:
                    self.ctrl.loads[row]["load"] = value
                    self.ctrl.loads[row]["load_expr"] = ""
            elif col == 7 and ltype in ("spring", "torsion_spring"):
                try:
                    raw = item.text().strip()
                    if raw.lower().startswith("p"):
                        raw = raw[1:]
                    value = int(raw)
                except ValueError:
                    self._refresh_load_tables()
                    return
                if value not in self.ctrl.points:
                    self._refresh_load_tables()
                    return
                self.ctrl.loads[row]["ref_pid"] = value
                if ltype == "torsion_spring":
                    theta0 = self.ctrl.get_angle_rad(int(load.get("pid", -1)), value)
                    if theta0 is not None:
                        self.ctrl.loads[row]["theta0"] = float(theta0)
            else:
                return
            self.refresh_labels()

    def _on_friction_table_changed(self, row: int, col: int) -> None:
            if col not in (1, 2):
                return
            if row < 0 or row >= len(self.ctrl.friction_joints):
                return
            item = self.table_friction.item(row, col)
            if item is None:
                return
            raw = item.text().strip()
            key_map = {
                1: ("mu", "mu_expr"),
                2: ("diameter", "diameter_expr"),
            }
            key_num, key_expr = key_map.get(col, ("", ""))
            if not key_num:
                return
            try:
                value = float(raw)
            except ValueError:
                if not raw:
                    self._refresh_friction_table()
                    return
                self.ctrl.friction_joints[row][key_expr] = raw
                self.ctrl.recompute_from_parameters()
            else:
                self.ctrl.friction_joints[row][key_num] = value
                self.ctrl.friction_joints[row][key_expr] = ""
            self.refresh_labels()

    def _refresh_load_tables(self):
            loads = list(self.ctrl.loads)
            self.table_loads.blockSignals(True)
            try:
                self.table_loads.setRowCount(len(loads))
                for row, ld in enumerate(loads):
                    pid = ld.get("pid", "--")
                    ltype = str(ld.get("type", "force"))
                    fx, fy, mz = self.ctrl._resolve_load_components(ld)
                    k = ld.get("k", "")
                    preload = ld.get("load", "")
                    ref_pid = ld.get("ref_pid", "")
                    fx_expr = str(ld.get("fx_expr", "") or "")
                    fy_expr = str(ld.get("fy_expr", "") or "")
                    mz_expr = str(ld.get("mz_expr", "") or "")
                    k_expr = str(ld.get("k_expr", "") or "")
                    load_expr = str(ld.get("load_expr", "") or "")
                    items = [
                        QTableWidgetItem(f"P{pid}" if isinstance(pid, int) else str(pid)),
                        QTableWidgetItem(ltype),
                        QTableWidgetItem(fx_expr if fx_expr else self.ctrl.format_number(fx)),
                        QTableWidgetItem(fy_expr if fy_expr else self.ctrl.format_number(fy)),
                        QTableWidgetItem(mz_expr if mz_expr else self.ctrl.format_number(mz)),
                        QTableWidgetItem(k_expr if k_expr else ("" if k == "" else self.ctrl.format_number(k))),
                        QTableWidgetItem(load_expr if load_expr else ("" if preload == "" else self.ctrl.format_number(preload))),
                        QTableWidgetItem("" if ref_pid == "" else f"P{ref_pid}"),
                    ]
                    for col, item in enumerate(items):
                        if col in (0, 1):
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        elif ltype.lower() in ("force", "torque") and col in (5, 6, 7):
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        elif ltype.lower() not in ("force", "torque") and col in (2, 3, 4):
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.table_loads.setItem(row, col, item)
            finally:
                self.table_loads.blockSignals(False)

            joint_loads, qs = self.ctrl.compute_quasistatic_report()

            mode = qs.get("mode", "--")
            self.lbl_qs_mode.setText(_tr(self, "sim.quasi_static").format(mode=mode))

            tau_in = qs.get("tau_input", None)
            tau_out = qs.get("tau_output", None)
            if tau_in is None:
                self.lbl_tau_in.setText(_tr(self, "sim.input_tau_none"))
            else:
                self.lbl_tau_in.setText(_tr(self, "sim.input_tau").format(value=self.ctrl.format_number(tau_in)))
            if tau_out is None:
                self.lbl_tau_out.setText(_tr(self, "sim.output_tau_none"))
            else:
                self.lbl_tau_out.setText(_tr(self, "sim.output_tau").format(value=self.ctrl.format_number(tau_out)))

            self.table_joint_loads.setRowCount(len(joint_loads))
            for row, jl in enumerate(joint_loads):
                items = [
                    QTableWidgetItem(f"P{jl.get('pid')}"),
                    QTableWidgetItem(self.ctrl.format_number(jl.get("fx", 0.0))),
                    QTableWidgetItem(self.ctrl.format_number(jl.get("fy", 0.0))),
                    QTableWidgetItem(self.ctrl.format_number(jl.get("mag", 0.0))),
                ]
                for col, item in enumerate(items):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table_joint_loads.setItem(row, col, item)

            self._refresh_measure_table()

    def _refresh_friction_table(self) -> None:
            rows = self.ctrl.get_friction_table()
            self.table_friction.blockSignals(True)
            try:
                self.table_friction.setRowCount(len(rows))
                for row, entry in enumerate(rows):
                    pid = entry.get("pid", "--")
                    mu = entry.get("mu", 0.0)
                    diameter = entry.get("diameter", 0.0)
                    mu_expr = entry.get("mu_expr", "")
                    diameter_expr = entry.get("diameter_expr", "")
                    local_load = entry.get("local_load", None)
                    torque = entry.get("torque", None)
                    items = [
                        QTableWidgetItem(f"P{pid}" if isinstance(pid, int) else str(pid)),
                        QTableWidgetItem(mu_expr if mu_expr else self.ctrl.format_number(mu)),
                        QTableWidgetItem(diameter_expr if diameter_expr else self.ctrl.format_number(diameter)),
                        QTableWidgetItem("--" if local_load is None else self.ctrl.format_number(local_load)),
                        QTableWidgetItem("--" if torque is None else self.ctrl.format_number(torque)),
                    ]
                    for col, item in enumerate(items):
                        if col in (0, 3, 4):
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.table_friction.setItem(row, col, item)
            finally:
                self.table_friction.blockSignals(False)

