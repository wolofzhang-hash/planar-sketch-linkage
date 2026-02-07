# -*- coding: utf-8 -*-
"""Case/Run storage management for Analysis tabs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import numbers
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


@dataclass
class CaseInfo:
    case_id: str
    name: str
    created_utc: str
    updated_utc: str
    case_hash: str


class CaseRunManager:
    def __init__(self, project_dir: str, project_uuid: Optional[str] = None):
        self.project_dir = project_dir
        self.project_uuid = str(project_uuid) if project_uuid else ""
        self.cases_dir = os.path.join(project_dir, "cases")
        self.runs_dir = os.path.join(project_dir, "runs")
        _ensure_dir(self.cases_dir)
        _ensure_dir(self.runs_dir)

    def _index_path(self) -> str:
        return os.path.join(self.cases_dir, "index.json")

    def _load_index(self) -> Dict[str, Any]:
        payload = _read_json(self._index_path())
        if not payload:
            payload = {"cases": [], "hash_map": {}, "project_uuid": self.project_uuid}
        payload.setdefault("cases", [])
        payload.setdefault("hash_map", {})
        if self.project_uuid:
            stored_uuid = str(payload.get("project_uuid", "") or "")
            if stored_uuid and stored_uuid != self.project_uuid:
                payload = {"cases": [], "hash_map": {}, "project_uuid": self.project_uuid}
            else:
                payload["project_uuid"] = self.project_uuid
        else:
            payload.setdefault("project_uuid", "")
        return payload

    def _save_index(self, payload: Dict[str, Any]) -> None:
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        _write_json(self._index_path(), payload)

    @staticmethod
    def _next_case_id(index: Dict[str, Any]) -> str:
        existing_ids = {str(item.get("case_id", "")).strip() for item in index.get("cases", [])}
        numeric_ids = [int(cid) for cid in existing_ids if cid.isdigit()]
        next_id = max(numeric_ids, default=0) + 1
        while str(next_id) in existing_ids:
            next_id += 1
        return str(next_id)

    @staticmethod
    def _case_hash(case_spec: Dict[str, Any]) -> str:
        keys = {
            "driver": case_spec.get("driver"),
            "drivers": case_spec.get("drivers"),
            "output": case_spec.get("output"),
            "outputs": case_spec.get("outputs"),
            "sweep": case_spec.get("sweep"),
            "solver": case_spec.get("solver"),
            "loads": case_spec.get("loads"),
            "measurements": case_spec.get("measurements"),
        }
        raw = json.dumps(keys, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def get_or_create_case(self, case_spec: Dict[str, Any]) -> CaseInfo:
        index = self._load_index()
        case_hash = self._case_hash(case_spec)
        hash_map = index.get("hash_map", {})
        existing_id = hash_map.get(case_hash)
        now = _utc_now()
        if existing_id:
            for entry in index.get("cases", []):
                if entry.get("case_id") == existing_id:
                    entry["updated_utc"] = now
                    name = entry.get("name", str(existing_id))
                    created = entry.get("created_utc", now)
                    info = CaseInfo(existing_id, name, created, now, case_hash)
                    self._save_index(index)
                    self._write_case_spec(info.case_id, case_spec, created, now, name)
                    return info

        case_id = self._next_case_id(index)
        name = case_spec.get("name") or str(case_id)
        info = CaseInfo(case_id, name, now, now, case_hash)
        index["cases"].append(
            {
                "case_id": case_id,
                "name": name,
                "created_utc": now,
                "updated_utc": now,
                "case_hash": case_hash,
            }
        )
        index["hash_map"][case_hash] = case_id
        self._save_index(index)
        self._write_case_spec(case_id, case_spec, now, now, name)
        return info

    def _write_case_spec(self, case_id: str, case_spec: Dict[str, Any], created: str, updated: str, name: str) -> None:
        payload = dict(case_spec)
        payload["schema_version"] = payload.get("schema_version", "1.0")
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        payload["case_id"] = case_id
        payload["name"] = name
        payload["created_utc"] = created
        payload["updated_utc"] = updated
        path = os.path.join(self.cases_dir, f"{case_id}.case.json")
        _write_json(path, payload)

    def list_cases(self) -> List[CaseInfo]:
        index = self._load_index()
        cases = [
            CaseInfo(
                case_id=str(c.get("case_id", "")),
                name=str(c.get("name", "")),
                created_utc=str(c.get("created_utc", "")),
                updated_utc=str(c.get("updated_utc", "")),
                case_hash=str(c.get("case_hash", "")),
            )
            for c in index.get("cases", [])
        ]
        cases.sort(key=lambda c: c.updated_utc, reverse=True)
        return cases

    def update_case_name(self, case_id: str, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name:
            return False
        index = self._load_index()
        entry = None
        for item in index.get("cases", []):
            if item.get("case_id") == case_id:
                entry = item
                break
        if entry is None:
            return False
        now = _utc_now()
        entry["name"] = new_name
        entry["updated_utc"] = now
        self._save_index(index)
        spec = self.load_case_spec(case_id)
        if spec:
            created = spec.get("created_utc", entry.get("created_utc", now))
            self._write_case_spec(case_id, spec, created, now, new_name)
        return True

    def rename_case_id(self, case_id: str, new_case_id: str) -> bool:
        new_case_id = new_case_id.strip()
        if not new_case_id or new_case_id == case_id:
            return False
        index = self._load_index()
        for item in index.get("cases", []):
            if item.get("case_id") == new_case_id:
                return False
        entry = None
        for item in index.get("cases", []):
            if item.get("case_id") == case_id:
                entry = item
                break
        if entry is None:
            return False
        now = _utc_now()
        entry["case_id"] = new_case_id
        entry["updated_utc"] = now
        case_hash = entry.get("case_hash")
        if case_hash:
            index.setdefault("hash_map", {})[case_hash] = new_case_id
        self._save_index(index)

        old_path = os.path.join(self.cases_dir, f"{case_id}.case.json")
        new_path = os.path.join(self.cases_dir, f"{new_case_id}.case.json")
        spec = _read_json(old_path)
        if spec:
            created = spec.get("created_utc", entry.get("created_utc", now))
            name = spec.get("name", entry.get("name", str(new_case_id)))
            self._write_case_spec(new_case_id, spec, created, now, name)
        if os.path.exists(old_path):
            os.remove(old_path)

        old_runs = os.path.join(self.runs_dir, case_id)
        new_runs = os.path.join(self.runs_dir, new_case_id)
        if os.path.exists(old_runs) and not os.path.exists(new_runs):
            os.rename(old_runs, new_runs)

        active = self.get_active_case()
        if active == case_id:
            self.set_active_case(new_case_id)

        self._update_last_run_path(case_id, new_case_id)
        return True

    def delete_case_runs(self, case_id: str) -> bool:
        runs_path = os.path.join(self.runs_dir, case_id)
        if os.path.isdir(runs_path):
            shutil.rmtree(runs_path)
        self._update_last_run_path(case_id, None)
        return True

    def delete_case(self, case_id: str) -> bool:
        index = self._load_index()
        entries = index.get("cases", [])
        entry = next((item for item in entries if item.get("case_id") == case_id), None)
        if entry is None:
            return False
        entries = [item for item in entries if item.get("case_id") != case_id]
        index["cases"] = entries
        case_hash = entry.get("case_hash")
        if case_hash and index.get("hash_map", {}).get(case_hash) == case_id:
            index["hash_map"].pop(case_hash, None)
        self._save_index(index)
        spec_path = os.path.join(self.cases_dir, f"{case_id}.case.json")
        if os.path.exists(spec_path):
            os.remove(spec_path)
        self.delete_case_runs(case_id)
        active = self.get_active_case()
        if active == case_id:
            active_path = os.path.join(self.cases_dir, "active_case.txt")
            try:
                os.remove(active_path)
            except Exception:
                with open(active_path, "w", encoding="utf-8") as fh:
                    fh.write("")
        return True

    def _update_last_run_path(self, old_case_id: str, new_case_id: Optional[str]) -> None:
        last_path = os.path.join(self.runs_dir, "last_run.txt")
        try:
            with open(last_path, "r", encoding="utf-8") as fh:
                current = fh.read().strip()
        except Exception:
            return
        if not current or f"{os.sep}{old_case_id}{os.sep}" not in current:
            return
        if new_case_id:
            updated = current.replace(f"{os.sep}{old_case_id}{os.sep}", f"{os.sep}{new_case_id}{os.sep}")
            with open(last_path, "w", encoding="utf-8") as fh:
                fh.write(updated)
        else:
            with open(last_path, "w", encoding="utf-8") as fh:
                fh.write("")

    def load_case_spec(self, case_id: str) -> Dict[str, Any]:
        path = os.path.join(self.cases_dir, f"{case_id}.case.json")
        return _read_json(path)

    def set_active_case(self, case_id: str) -> None:
        path = os.path.join(self.cases_dir, "active_case.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(case_id))

    def get_active_case(self) -> Optional[str]:
        path = os.path.join(self.cases_dir, "active_case.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read().strip() or None
        except Exception:
            return None

    def _run_dir(self, case_id: str, run_id: str) -> str:
        return os.path.join(self.runs_dir, case_id, run_id)

    def save_run(
        self,
        case_spec: Dict[str, Any],
        model_snapshot: Dict[str, Any],
        frames: List[Dict[str, Any]],
        status: Dict[str, Any],
        end_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        case_info = self.get_or_create_case(case_spec)
        run_dir = self._run_dir(case_info.case_id, "current")
        case_runs_dir = os.path.join(self.runs_dir, case_info.case_id)
        if os.path.isdir(case_runs_dir):
            shutil.rmtree(case_runs_dir)
        results_dir = os.path.join(run_dir, "results")
        _ensure_dir(results_dir)

        model_path = os.path.join(run_dir, "model.json")
        case_path = os.path.join(run_dir, "case.json")
        _write_json(model_path, model_snapshot)
        if end_snapshot is not None:
            end_path = os.path.join(run_dir, "model_end.json")
            _write_json(end_path, end_snapshot)
        _write_json(case_path, self.load_case_spec(case_info.case_id))

        frame_path = os.path.join(results_dir, "frames.csv")
        summary_path = os.path.join(results_dir, "summary.json")
        status_path = os.path.join(run_dir, "status.json")
        log_path = os.path.join(run_dir, "log.txt")

        fields: List[str] = []
        for rec in frames:
            for key in rec.keys():
                if key not in fields:
                    fields.append(key)

        with open(frame_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(fields)
            for rec in frames:
                writer.writerow([rec.get(k) for k in fields])

        summary = self._build_summary(frames, status)
        _write_json(summary_path, summary)
        _write_json(status_path, status)
        with open(log_path, "w", encoding="utf-8") as fh:
            reason = status.get("reason", "ok")
            solver_error = status.get("solver_error")
            fh.write(str(reason))
            if solver_error:
                fh.write("\nsolver_error: ")
                fh.write(str(solver_error))

        with open(os.path.join(self.runs_dir, "last_run.txt"), "w", encoding="utf-8") as fh:
            fh.write(run_dir)

        return run_dir

    def _build_summary(self, frames: List[Dict[str, Any]], status: Dict[str, Any]) -> Dict[str, Any]:
        n_steps = len(frames)
        success_steps = [f for f in frames if f.get("success")]
        success_rate = float(len(success_steps)) / float(n_steps) if n_steps else 0.0
        max_hard_err = max((float(f.get("hard_err", 0.0) or 0.0) for f in frames), default=0.0)

        signals: Dict[str, Dict[str, float]] = {}
        for rec in frames:
            for key, val in rec.items():
                if key in ("time", "solver", "success"):
                    continue
                if val is None:
                    continue
                if not isinstance(val, numbers.Real):
                    continue
                val_f = float(val)
                signals.setdefault(key, {"min": val_f, "max": val_f, "sum": 0.0, "sum_sq": 0.0, "count": 0.0})
                signals[key]["min"] = min(signals[key]["min"], val_f)
                signals[key]["max"] = max(signals[key]["max"], val_f)
                signals[key]["sum"] += val_f
                signals[key]["sum_sq"] += val_f * val_f
                signals[key]["count"] += 1.0

        signal_stats = {}
        for key, st in signals.items():
            count = max(st.get("count", 0.0), 1.0)
            mean = st["sum"] / count
            rms = math.sqrt(st["sum_sq"] / count)
            signal_stats[key] = {
                "min": st["min"],
                "max": st["max"],
                "mean": mean,
                "rms": rms,
            }

        return {
            "success": bool(status.get("success", False)),
            "success_rate": success_rate,
            "n_steps": n_steps,
            "elapsed_sec": float(status.get("elapsed_sec", 0.0)),
            "max_hard_err": max_hard_err,
            "fail_reason_hist": status.get("fail_reason_hist", {}),
            "signals": signal_stats,
        }

    def list_runs(self, case_id: str) -> List[Dict[str, Any]]:
        run_dir = self._run_dir(case_id, "current")
        if not os.path.isdir(run_dir):
            return []
        summary = _read_json(os.path.join(run_dir, "results", "summary.json"))
        status = _read_json(os.path.join(run_dir, "status.json"))
        return [
            {
                "run_id": "current",
                "path": run_dir,
                "success": summary.get("success", status.get("success")),
                "n_steps": summary.get("n_steps"),
                "success_rate": summary.get("success_rate"),
                "max_hard_err": summary.get("max_hard_err"),
                "elapsed_sec": summary.get("elapsed_sec", status.get("elapsed_sec")),
                "updated_utc": status.get("finished_utc", ""),
            }
        ]

    def last_run_path(self) -> Optional[str]:
        path = os.path.join(self.runs_dir, "last_run.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
            if not val:
                return None
            if not self.project_uuid:
                return val
            case_spec = _read_json(os.path.join(val, "case.json"))
            stored_uuid = case_spec.get("project_uuid")
            if stored_uuid and stored_uuid != self.project_uuid:
                return None
            return val
        except Exception:
            return None

    def latest_run_for_case(self, case_id: str) -> Optional[str]:
        runs = self.list_runs(case_id)
        if not runs:
            return None
        return runs[0].get("path")

    def load_latest_model_snapshot(self, case_id: str) -> Optional[Dict[str, Any]]:
        run_dir = self.latest_run_for_case(case_id)
        if not run_dir:
            return None
        return _read_json(os.path.join(run_dir, "model.json"))
