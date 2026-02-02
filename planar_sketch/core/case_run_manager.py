# -*- coding: utf-8 -*-
"""Case/Run storage management for Analysis tabs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import uuid
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
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.cases_dir = os.path.join(project_dir, "cases")
        self.runs_dir = os.path.join(project_dir, "runs")
        _ensure_dir(self.cases_dir)
        _ensure_dir(self.runs_dir)

    def _index_path(self) -> str:
        return os.path.join(self.cases_dir, "index.json")

    def _load_index(self) -> Dict[str, Any]:
        payload = _read_json(self._index_path())
        if not payload:
            payload = {"cases": [], "hash_map": {}}
        payload.setdefault("cases", [])
        payload.setdefault("hash_map", {})
        return payload

    def _save_index(self, payload: Dict[str, Any]) -> None:
        _write_json(self._index_path(), payload)

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
                    name = entry.get("name", f"Case {existing_id}")
                    created = entry.get("created_utc", now)
                    info = CaseInfo(existing_id, name, created, now, case_hash)
                    self._save_index(index)
                    self._write_case_spec(info.case_id, case_spec, created, now, name)
                    return info

        case_id = case_hash[:12]
        name = case_spec.get("name") or f"Case {case_id}"
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
            name = spec.get("name", entry.get("name", f"Case {new_case_id}"))
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
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        run_dir = self._run_dir(case_info.case_id, run_id)
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
            fh.write(status.get("reason", "ok"))

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
                signals.setdefault(key, {"min": float(val), "max": float(val), "sum": 0.0, "sum_sq": 0.0, "count": 0.0})
                signals[key]["min"] = min(signals[key]["min"], float(val))
                signals[key]["max"] = max(signals[key]["max"], float(val))
                signals[key]["sum"] += float(val)
                signals[key]["sum_sq"] += float(val) * float(val)
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
        runs_path = os.path.join(self.runs_dir, case_id)
        if not os.path.isdir(runs_path):
            return []
        runs = []
        for run_id in sorted(os.listdir(runs_path), reverse=True):
            run_dir = os.path.join(runs_path, run_id)
            if not os.path.isdir(run_dir):
                continue
            summary = _read_json(os.path.join(run_dir, "results", "summary.json"))
            status = _read_json(os.path.join(run_dir, "status.json"))
            runs.append(
                {
                    "run_id": run_id,
                    "path": run_dir,
                    "success": summary.get("success", status.get("success")),
                    "n_steps": summary.get("n_steps"),
                    "success_rate": summary.get("success_rate"),
                    "max_hard_err": summary.get("max_hard_err"),
                    "elapsed_sec": summary.get("elapsed_sec", status.get("elapsed_sec")),
                    "updated_utc": status.get("finished_utc", ""),
                }
            )
        return runs

    def last_run_path(self) -> Optional[str]:
        path = os.path.join(self.runs_dir, "last_run.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
            return val or None
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
