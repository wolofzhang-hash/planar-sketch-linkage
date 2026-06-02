from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Mapping, Optional

from .run_models import ReplayBundle, ReplayFrame, RunRecord, ensure_run_record


class ReplayService:
    """Read-only helpers for persisted replay data."""

    @staticmethod
    def run_path(run: Optional[Mapping[str, Any] | RunRecord]) -> str:
        record = ensure_run_record(run)
        return record.path or ""

    @classmethod
    def frames_path(cls, run: Optional[Mapping[str, Any] | RunRecord]) -> str:
        path = cls.run_path(run)
        if not path:
            return ""
        return os.path.join(path, "results", "frames.csv")

    @classmethod
    def case_json_path(cls, run: Optional[Mapping[str, Any] | RunRecord]) -> str:
        path = cls.run_path(run)
        if not path:
            return ""
        return os.path.join(path, "case.json")

    @classmethod
    def model_json_path(cls, run: Optional[Mapping[str, Any] | RunRecord]) -> str:
        path = cls.run_path(run)
        if not path:
            return ""
        return os.path.join(path, "model.json")

    def validate_run(self, run: Optional[Mapping[str, Any] | RunRecord]) -> List[str]:
        record = ensure_run_record(run)
        errors: List[str] = []
        run_path = self.run_path(record)
        if not run_path:
            return ["missing run path"]
        if not os.path.isdir(run_path):
            return [f"run directory not found: {run_path}"]
        case_json = self.case_json_path(record)
        if not os.path.exists(case_json):
            errors.append(f"missing case.json: {case_json}")
        model_json = self.model_json_path(record)
        if not os.path.exists(model_json):
            errors.append(f"missing model.json: {model_json}")
        frames_path = self.frames_path(record)
        if not os.path.exists(frames_path):
            errors.append(f"missing frames.csv: {frames_path}")
        return errors

    def run_contains_pose_points(self, run: Optional[Mapping[str, Any] | RunRecord]) -> bool:
        frames_path = self.frames_path(run)
        if not frames_path or not os.path.exists(frames_path):
            return False
        try:
            with open(frames_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                first = next(reader, None)
            if not first:
                return False
            raw = first.get("pose_points")
            return raw not in (None, "", "[]")
        except Exception:
            return False

    def load_frame_rows(self, run: Optional[Mapping[str, Any] | RunRecord]) -> List[Dict[str, Any]]:
        errors = self.validate_run(run)
        if errors:
            raise FileNotFoundError("; ".join(errors))
        frames_path = self.frames_path(run)
        with open(frames_path, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def load_frames(self, run: Optional[Mapping[str, Any] | RunRecord]) -> List[ReplayFrame]:
        return [ReplayFrame.from_dict(row) for row in self.load_frame_rows(run)]

    def load_bundle(self, run: Optional[Mapping[str, Any] | RunRecord]) -> ReplayBundle:
        record = ensure_run_record(run)
        return ReplayBundle(run=record, frames=self.load_frames(record))
