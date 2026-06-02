from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .case_run_manager import CaseRunManager
from .project_paths import ProjectPathService
from .run_models import CaseSpec, ReplayFrame, RunRecord, ensure_case_spec_dict, ensure_frame_dicts


class RunService:
    """Thin boundary around CaseRunManager for run/case persistence.

    Stage 3 note:
    - keep backward-compatible dict helpers for existing UI code
    - expose dataclass-based accessors so future refactors stop passing raw dicts
    """

    def __init__(self, ctrl: Any, project_paths: Optional[ProjectPathService] = None):
        self.ctrl = ctrl
        self.project_paths = project_paths or ProjectPathService(ctrl)

    def project_dir(self) -> str:
        return self.project_paths.project_dir()

    def manager(self) -> CaseRunManager:
        project_uuid = getattr(self.ctrl, "project_uuid", "") if self.ctrl else ""
        return CaseRunManager(self.project_dir(), project_uuid=project_uuid)

    def list_cases(self):
        return self.manager().list_cases()

    def list_runs(self, case_name: str) -> List[Dict[str, Any]]:
        return self.manager().list_runs(str(case_name))

    def list_run_records(self, case_name: str) -> List[RunRecord]:
        return [RunRecord.from_dict(item) for item in self.list_runs(case_name)]

    def load_case_spec(self, case_name: str) -> Dict[str, Any]:
        return self.manager().load_case_spec(str(case_name)) or {}

    def load_case(self, case_name: str) -> CaseSpec:
        return CaseSpec.from_dict(self.load_case_spec(case_name))

    def set_active_case(self, case_name: str) -> None:
        self.manager().set_active_case(str(case_name))

    def get_active_case(self) -> Optional[str]:
        return self.manager().get_active_case()

    def save_case_run(
        self,
        case_name: str,
        case_spec: CaseSpec | Mapping[str, Any],
        start_snapshot: Dict[str, Any],
        records: Sequence[ReplayFrame | Mapping[str, Any]],
        status: Dict[str, Any],
        *,
        end_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.manager().save_current_run(
            str(case_name),
            ensure_case_spec_dict(case_spec),
            start_snapshot,
            ensure_frame_dicts(records),
            status,
            end_snapshot=end_snapshot,
        )

    def save_last_run(
        self,
        case_spec: CaseSpec | Mapping[str, Any],
        start_snapshot: Dict[str, Any],
        records: Sequence[ReplayFrame | Mapping[str, Any]],
        status: Dict[str, Any],
        *,
        end_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.manager().save_last_run(
            ensure_case_spec_dict(case_spec),
            start_snapshot,
            ensure_frame_dicts(records),
            status,
            end_snapshot=end_snapshot,
        )
