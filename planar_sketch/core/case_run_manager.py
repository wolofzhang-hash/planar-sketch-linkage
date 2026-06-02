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

from .run_models import RunRecord, ensure_case_spec_dict, ensure_frame_dicts
from ..version import CASE_SCHEMA_VERSION


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
    """A user-defined analysis scenario.

    ``name`` remains the stable internal case id for backward compatibility.
    ``display_name`` is the user-editable label shown in the UI.
    """

    name: str
    created_utc: str
    updated_utc: str
    case_hash: str
    display_name: str = ""

    @property
    def case_id(self) -> str:
        return self.name

    @property
    def label(self) -> str:
        return self.display_name or self.name


class CaseRunManager:
    def __init__(self, project_dir: str, project_uuid: Optional[str] = None):
        self.project_dir = project_dir
        self.project_uuid = str(project_uuid) if project_uuid else ""
        self.cases_dir = os.path.join(project_dir, "cases")
        self.runs_dir = os.path.join(project_dir, "runs")
        _ensure_dir(self.cases_dir)
        _ensure_dir(self.runs_dir)

    @staticmethod
    def _normalize_case_name(case_name: str) -> str:
        return str(case_name or "").strip()

    def _find_case_entry(self, case_name: str, *, index: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        case_name = self._normalize_case_name(case_name)
        if not case_name:
            return None
        payload = index if isinstance(index, dict) else self._load_index()
        for item in payload.get("cases", []):
            item_name = self._normalize_case_name(item.get("name") or item.get("case_id"))
            if item_name == case_name:
                return item
        return None

    def _require_case_entry(self, case_name: str, *, index: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry = self._find_case_entry(case_name, index=index)
        if entry is None:
            raise KeyError(f"Unknown case id: {case_name!r}")
        return entry

    def _index_path(self) -> str:
        return os.path.join(self.cases_dir, "index.json")

    def _load_index(self) -> Dict[str, Any]:
        payload = _read_json(self._index_path())
        if not payload:
            payload = {"cases": [], "hash_map": {}, "project_uuid": self.project_uuid}
        payload.setdefault("cases", [])
        payload.setdefault("hash_map", {})
        # NOTE:
        # Earlier versions treated a project_uuid mismatch as a hard reset of the case index.
        # That makes cases "disappear" after saving a new project (uuid changes from "" to a value),
        # which is confusing for users.
        # We now keep existing cases and simply update the stored uuid.
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        else:
            payload.setdefault("project_uuid", "")
        return payload

    def _save_index(self, payload: Dict[str, Any]) -> None:
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        _write_json(self._index_path(), payload)

    @staticmethod
    def _next_case_name(index: Dict[str, Any]) -> str:
        """Generate a new stable internal case id."""
        existing = {str(item.get("name", item.get("case_id", ""))).strip() for item in index.get("cases", [])}
        nums = []
        for value in existing:
            if value.startswith("case_") and value[5:].isdigit():
                nums.append(int(value[5:]))
            elif value.isdigit():
                nums.append(int(value))
        nxt = max(nums, default=0) + 1
        candidate = f"case_{nxt:03d}"
        while candidate in existing:
            nxt += 1
            candidate = f"case_{nxt:03d}"
        return candidate

    @staticmethod
    def _default_display_name(index: Dict[str, Any]) -> str:
        existing = {str(item.get("display_name", item.get("name", item.get("case_id", "")))).strip() for item in index.get("cases", [])}
        numeric = [int(x) for x in existing if x.isdigit()]
        nxt = max(numeric, default=0) + 1
        while str(nxt) in existing:
            nxt += 1
        return str(nxt)

    @staticmethod
    def _case_hash(case_spec: Dict[str, Any]) -> str:
        keys = {
            "driver": case_spec.get("driver"),
            "drivers": case_spec.get("drivers"),
            "output": case_spec.get("output"),
            "outputs": case_spec.get("outputs"),
            # IMPORTANT: include curve target + angle mode so that changing keypoints
            # does not silently overwrite/reuse a previous case.
            "angle_mode": case_spec.get("angle_mode"),
            "curve_target": case_spec.get("curve_target"),
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
        existing_name = hash_map.get(case_hash)
        now = _utc_now()
        if existing_name:
            for entry in index.get("cases", []):
                if (entry.get("name") or entry.get("case_id")) == existing_name:
                    entry["updated_utc"] = now
                    created = entry.get("created_utc", now)
                    display_name = str(entry.get("display_name") or entry.get("name") or entry.get("case_id") or existing_name)
                    info = CaseInfo(str(existing_name), created, now, case_hash, display_name=display_name)
                    self._save_index(index)
                    self._write_case_spec(info.name, case_spec, created, now, display_name=display_name)
                    return info

        # No matching case in the current index: create a fresh one.
        return self.create_case(case_spec)

    def create_case(self, case_spec: Dict[str, Any], display_name: Optional[str] = None) -> CaseInfo:
        """Create a brand-new case entry regardless of duplicates.

        Design intent:
        - A *Case* represents a user-saved scenario ("multi-condition") and should be
          created only from an explicit user action ("Save run as new case").
        - We still compute and store a case_hash for metadata, but we do not prevent
          multiple cases having the same hash.
        """
        index = self._load_index()
        now = _utc_now()
        case_name = self._next_case_name(index)
        case_hash = self._case_hash(case_spec)
        display_name = str(display_name or case_spec.get("display_name") or self._default_display_name(index)).strip()
        info = CaseInfo(str(case_name), now, now, case_hash, display_name=display_name or str(case_name))

        index.setdefault("cases", []).append(
            {
                "name": info.name,
                "display_name": info.display_name,
                "created_utc": now,
                "updated_utc": now,
                "case_hash": case_hash,
            }
        )
        # Keep hash_map pointing to the latest case for this hash (best-effort).
        # This does NOT deduplicate; it simply improves future "get_or_create" behavior.
        try:
            index.setdefault("hash_map", {})[case_hash] = info.name
        except Exception:
            pass
        self._save_index(index)
        self._write_case_spec(info.name, case_spec, now, now, display_name=info.display_name)
        return info

    def save_last_run(
        self,
        case_spec: Dict[str, Any],
        model_snapshot: Dict[str, Any],
        frames: List[Dict[str, Any]],
        status: Dict[str, Any],
        end_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist an overwriteable "last run" that is NOT an official case.

        Design intent:
        - Running without clicking "Save run" should not create a new Case.
        - The last run is stored in runs/_last/current and can be overwritten.
        - Users can promote the last run into a new Case via an explicit action.
        """
        case_spec = ensure_case_spec_dict(case_spec)
        frames = ensure_frame_dicts(frames)
        run_dir = os.path.join(self.runs_dir, "_last", "current")
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir)
        results_dir = os.path.join(run_dir, "results")
        _ensure_dir(results_dir)

        # Ensure the persisted spec contains project_uuid for validation.
        spec = dict(case_spec) if isinstance(case_spec, dict) else {}
        if self.project_uuid:
            spec.setdefault("project_uuid", self.project_uuid)
        _write_json(os.path.join(run_dir, "model.json"), model_snapshot)
        if end_snapshot is not None:
            _write_json(os.path.join(run_dir, "model_end.json"), end_snapshot)
        _write_json(os.path.join(run_dir, "case.json"), spec)

        frame_path = os.path.join(results_dir, "frames.csv")
        summary_path = os.path.join(results_dir, "summary.json")
        status_path = os.path.join(run_dir, "status.json")
        log_path = os.path.join(run_dir, "log.txt")

        fields = list(dict.fromkeys(key for rec in frames for key in rec.keys()))
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

    def _write_case_spec(self, case_name: str, case_spec: Dict[str, Any], created: str, updated: str, display_name: Optional[str] = None) -> None:
        payload = dict(case_spec)
        payload["schema_version"] = CASE_SCHEMA_VERSION
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        payload.pop("case_id", None)
        payload["name"] = str(case_name)
        if display_name is not None:
            payload["display_name"] = str(display_name)
        elif "display_name" not in payload:
            payload["display_name"] = str(case_name)
        payload["created_utc"] = created
        payload["updated_utc"] = updated
        path = os.path.join(self.cases_dir, f"{case_name}.case.json")
        _write_json(path, payload)

    def list_cases(self) -> List[CaseInfo]:
        index = self._load_index()
        cases = [
            CaseInfo(
                name=str(c.get("name", c.get("case_id", ""))),
                created_utc=str(c.get("created_utc", "")),
                updated_utc=str(c.get("updated_utc", "")),
                case_hash=str(c.get("case_hash", "")),
                display_name=str(c.get("display_name", c.get("name", c.get("case_id", "")))),
            )
            for c in index.get("cases", [])
        ]
        cases.sort(key=lambda c: c.updated_utc, reverse=True)
        return cases

    def rename_case(self, case_name: str, new_display_name: str) -> bool:
        """Rename a case label without changing its stable internal id/path."""
        case_name = self._normalize_case_name(case_name)
        new_display_name = str(new_display_name).strip()
        if not case_name or not new_display_name:
            return False
        index = self._load_index()
        entries = index.get("cases", [])
        for item in entries:
            item_name = self._normalize_case_name(item.get("name") or item.get("case_id"))
            item_label = str(item.get("display_name") or item.get("name") or item.get("case_id") or "").strip()
            if item_name != case_name and item_label == new_display_name:
                return False
        target = self._find_case_entry(case_name, index=index)
        if target is None:
            return False
        created = str(target.get("created_utc", _utc_now()))
        updated = _utc_now()
        target["display_name"] = new_display_name
        target["updated_utc"] = updated
        self._save_index(index)
        spec = self.load_case_spec(case_name)
        if spec:
            self._write_case_spec(case_name, spec, created, updated, display_name=new_display_name)
        return True

    def case_display_name(self, case_name: str) -> str:
        case_name = str(case_name).strip()
        for info in self.list_cases():
            if info.name == case_name:
                return info.label
        return case_name

    def delete_case_runs(self, case_name: str) -> bool:
        case_name = self._normalize_case_name(case_name)
        if not self._find_case_entry(case_name):
            return False
        runs_path = os.path.join(self.runs_dir, case_name)
        if os.path.isdir(runs_path):
            shutil.rmtree(runs_path)
        self._update_last_run_path(case_name, None)
        return True

    def delete_case(self, case_name: str) -> bool:
        case_name = self._normalize_case_name(case_name)
        index = self._load_index()
        entries = index.get("cases", [])
        entry = self._find_case_entry(case_name, index=index)
        if entry is None:
            return False

        # Remove persisted run data while the case is still known, so last_run.txt
        # is cleared when it points at this case.
        self.delete_case_runs(case_name)

        entries = [item for item in entries if (item.get("name") or item.get("case_id")) != case_name]
        index["cases"] = entries
        case_hash = entry.get("case_hash")
        hash_map = index.setdefault("hash_map", {})
        if case_hash and hash_map.get(case_hash) == case_name:
            replacement = None
            for item in reversed(entries):
                if item.get("case_hash") == case_hash:
                    replacement = item.get("name") or item.get("case_id")
                    break
            if replacement:
                hash_map[case_hash] = replacement
            else:
                hash_map.pop(case_hash, None)
        self._save_index(index)

        spec_path = os.path.join(self.cases_dir, f"{case_name}.case.json")
        if os.path.exists(spec_path):
            os.remove(spec_path)
        active = self.get_active_case()
        if active == case_name:
            active_path = os.path.join(self.cases_dir, "active_case.txt")
            try:
                os.remove(active_path)
            except Exception:
                with open(active_path, "w", encoding="utf-8") as fh:
                    fh.write("")
        return True

    def _update_last_run_path(self, old_case_name: str, new_case_name: Optional[str]) -> None:
        last_path = os.path.join(self.runs_dir, "last_run.txt")
        try:
            with open(last_path, "r", encoding="utf-8") as fh:
                current = fh.read().strip()
        except Exception:
            return
        if not current or f"{os.sep}{old_case_name}{os.sep}" not in current:
            return
        if new_case_name:
            updated = current.replace(f"{os.sep}{old_case_name}{os.sep}", f"{os.sep}{new_case_name}{os.sep}")
            with open(last_path, "w", encoding="utf-8") as fh:
                fh.write(updated)
        else:
            with open(last_path, "w", encoding="utf-8") as fh:
                fh.write("")

    def load_case_spec(self, case_name: str) -> Dict[str, Any]:
        case_name = self._normalize_case_name(case_name)
        if not self._find_case_entry(case_name):
            return {}
        path = os.path.join(self.cases_dir, f"{case_name}.case.json")
        return _read_json(path)

    def set_active_case(self, case_name: str) -> None:
        path = os.path.join(self.cases_dir, "active_case.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(case_name))

    def get_active_case(self) -> Optional[str]:
        path = os.path.join(self.cases_dir, "active_case.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read().strip() or None
        except Exception:
            return None

    def _run_dir(self, case_name: str, run_id: str) -> str:
        return os.path.join(self.runs_dir, case_name, run_id)

    def save_current_run(
        self,
        case_name: str,
        case_spec: Dict[str, Any],
        model_snapshot: Dict[str, Any],
        frames: List[Dict[str, Any]],
        status: Dict[str, Any],
        end_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Overwrite the single "current" run for a case.

        Design intent:
        - Running a case overwrites runs/<case_id>/current.
        - No new run folders are created automatically.
        - Users can explicitly archive a run via :meth:`archive_current_run`.
        """
        case_name = self._normalize_case_name(case_name)
        self._require_case_entry(case_name)
        case_spec = ensure_case_spec_dict(case_spec)
        frames = ensure_frame_dicts(frames)
        run_dir = self._run_dir(case_name, "current")
        # Only replace the current run, keep any archived runs.
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir)
        results_dir = os.path.join(run_dir, "results")
        _ensure_dir(results_dir)

        model_path = os.path.join(run_dir, "model.json")
        case_path = os.path.join(run_dir, "case.json")
        _write_json(model_path, model_snapshot)
        if end_snapshot is not None:
            end_path = os.path.join(run_dir, "model_end.json")
            _write_json(end_path, end_snapshot)
        # Persist the case spec actually used for the run.
        stored = self.load_case_spec(case_name)
        executed_spec = dict(case_spec)
        if self.project_uuid:
            executed_spec.setdefault("project_uuid", self.project_uuid)
        executed_spec.setdefault("schema_version", stored.get("schema_version") if isinstance(stored, dict) and stored.get("schema_version") else CASE_SCHEMA_VERSION)
        executed_spec["name"] = case_name
        if isinstance(stored, dict):
            executed_spec.setdefault("display_name", stored.get("display_name") or stored.get("name") or case_name)
            executed_spec.setdefault("created_utc", stored.get("created_utc", ""))
        _write_json(case_path, executed_spec)

        frame_path = os.path.join(results_dir, "frames.csv")
        summary_path = os.path.join(results_dir, "summary.json")
        status_path = os.path.join(run_dir, "status.json")
        log_path = os.path.join(run_dir, "log.txt")

        fields = list(dict.fromkeys(key for rec in frames for key in rec.keys()))

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

    def archive_current_run(self, case_name: str, run_id: Optional[str] = None) -> Optional[str]:
        """Archive the current run into a new run folder.

        This is only called from an explicit user action ("Save run").
        """
        case_name = self._normalize_case_name(case_name)
        self._require_case_entry(case_name)
        src = self._run_dir(case_name, "current")
        if not os.path.isdir(src):
            return None
        if not run_id:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dst = self._run_dir(case_name, run_id)
        if os.path.exists(dst):
            suffix = datetime.now(timezone.utc).strftime("_%f")
            dst = self._run_dir(case_name, run_id + suffix)
        _ensure_dir(os.path.dirname(dst))
        shutil.copytree(src, dst)
        return dst

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

    def list_runs(self, case_name: str) -> List[Dict[str, Any]]:
        case_name = self._normalize_case_name(case_name)
        if not self._find_case_entry(case_name):
            return []
        case_dir = os.path.join(self.runs_dir, case_name)
        if not os.path.isdir(case_dir):
            return []

        run_ids: List[str] = []
        for name in os.listdir(case_dir):
            full = os.path.join(case_dir, name)
            if os.path.isdir(full):
                run_ids.append(name)

        def _mtime(rid: str) -> float:
            try:
                return os.path.getmtime(os.path.join(case_dir, rid))
            except Exception:
                return 0.0

        run_ids.sort(key=_mtime, reverse=True)
        if "current" in run_ids:
            run_ids.remove("current")
            run_ids.insert(0, "current")

        runs: List[Dict[str, Any]] = []
        for rid in run_ids:
            run_dir = self._run_dir(case_name, rid)
            summary = _read_json(os.path.join(run_dir, "results", "summary.json"))
            status = _read_json(os.path.join(run_dir, "status.json"))
            runs.append(
                {
                    "run_id": rid,
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

    def list_run_records(self, case_name: str) -> List[RunRecord]:
        return [RunRecord.from_dict(item) for item in self.list_runs(case_name)]

    def last_run_path(self) -> Optional[str]:
        path = os.path.join(self.runs_dir, "last_run.txt")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
            if not val or not os.path.isdir(val):
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

    def latest_run_for_case(self, case_name: str) -> Optional[str]:
        runs = self.list_runs(case_name)
        if not runs:
            return None
        return runs[0].get("path")

    def load_latest_model_snapshot(self, case_name: str) -> Optional[Dict[str, Any]]:
        run_dir = self.latest_run_for_case(case_name)
        if not run_dir:
            return None
        return _read_json(os.path.join(run_dir, "model.json"))
