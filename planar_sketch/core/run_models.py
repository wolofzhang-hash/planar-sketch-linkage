from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from ..version import CASE_SCHEMA_VERSION


@dataclass
class DriverSpec:
    enabled: bool = False
    type: str = ""
    pivot: Optional[int] = None
    tip: Optional[int] = None
    rad: Optional[float] = None
    plid: Optional[int] = None
    s_base: float = 0.0
    value: float = 0.0
    sweep_start: float = 0.0
    sweep_end: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DriverSpec":
        d = dict(data or {})
        return cls(
            enabled=bool(d.get("enabled", False)),
            type=str(d.get("type", "") or ""),
            pivot=d.get("pivot"),
            tip=d.get("tip"),
            rad=d.get("rad"),
            plid=d.get("plid"),
            s_base=float(d.get("s_base", 0.0) or 0.0),
            value=float(d.get("value", 0.0) or 0.0),
            sweep_start=float(d.get("sweep_start", 0.0) or 0.0),
            sweep_end=float(d.get("sweep_end", 0.0) or 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OutputSpec:
    enabled: bool = False
    pivot: Optional[int] = None
    tip: Optional[int] = None
    rad: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "OutputSpec":
        d = dict(data or {})
        return cls(
            enabled=bool(d.get("enabled", False)),
            pivot=d.get("pivot"),
            tip=d.get("tip"),
            rad=d.get("rad"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SweepSpec:
    start_deg: float = 0.0
    end_deg: float = 0.0
    step_count: int = 0
    adaptive: bool = True
    min_step_deg: float = 0.0
    max_step_deg: float = 0.0
    dtheta_min_deg: float = 0.0
    dtheta_max_deg: float = 0.0
    err_good: float = 0.0
    err_ok: float = 0.0
    grow: float = 0.0
    shrink: float = 0.0
    max_retries_per_step: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SweepSpec":
        d = dict(data or {})
        def _f(name: str, default: float = 0.0) -> float:
            return float(d.get(name, default) or default)
        return cls(
            start_deg=_f("start_deg"),
            end_deg=_f("end_deg"),
            step_count=int(d.get("step_count", 0) or 0),
            adaptive=bool(d.get("adaptive", True)),
            min_step_deg=_f("min_step_deg"),
            max_step_deg=_f("max_step_deg"),
            dtheta_min_deg=_f("dtheta_min_deg"),
            dtheta_max_deg=_f("dtheta_max_deg"),
            err_good=_f("err_good"),
            err_ok=_f("err_ok"),
            grow=_f("grow"),
            shrink=_f("shrink"),
            max_retries_per_step=int(d.get("max_retries_per_step", 0) or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CaseSpec:
    schema_version: str = CASE_SCHEMA_VERSION
    name: Optional[str] = None
    display_name: Optional[str] = None
    created_utc: str = ""
    updated_utc: str = ""
    project_uuid: str = ""
    target_input_deg: Optional[float] = None
    target_input_deg_list: List[float] = field(default_factory=list)
    analysis_mode: str = ""
    record_pose: bool = False
    angle_mode: Optional[str] = None
    curve_target: Any = None
    driver: DriverSpec = field(default_factory=DriverSpec)
    drivers: List[DriverSpec] = field(default_factory=list)
    output: OutputSpec = field(default_factory=OutputSpec)
    outputs: List[OutputSpec] = field(default_factory=list)
    sweep: SweepSpec = field(default_factory=SweepSpec)
    solver: Dict[str, Any] = field(default_factory=dict)
    loads: List[Dict[str, Any]] = field(default_factory=list)
    friction_joints: List[Dict[str, Any]] = field(default_factory=list)
    measurements: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CaseSpec":
        d = dict(data or {})
        known = {
            "schema_version", "name", "display_name", "created_utc", "updated_utc", "project_uuid",
            "target_input_deg", "target_input_deg_list", "analysis_mode", "record_pose",
            "angle_mode", "curve_target", "driver", "drivers", "output", "outputs",
            "sweep", "solver", "loads", "friction_joints", "measurements",
        }
        drivers_src = d.get("drivers") or ([] if not d.get("driver") else [d.get("driver")])
        outputs_src = d.get("outputs") or ([] if not d.get("output") else [d.get("output")])
        target_list = d.get("target_input_deg_list")
        if not isinstance(target_list, list):
            target = d.get("target_input_deg")
            target_list = [] if target is None else [target]
        return cls(
            schema_version=str(d.get("schema_version", CASE_SCHEMA_VERSION) or CASE_SCHEMA_VERSION),
            name=(None if d.get("name") in (None, "") else str(d.get("name"))),
            display_name=(None if d.get("display_name") in (None, "") else str(d.get("display_name"))),
            created_utc=str(d.get("created_utc", "") or ""),
            updated_utc=str(d.get("updated_utc", "") or ""),
            project_uuid=str(d.get("project_uuid", "") or ""),
            target_input_deg=(None if d.get("target_input_deg") is None else float(d.get("target_input_deg"))),
            target_input_deg_list=[float(x) for x in target_list],
            analysis_mode=str(d.get("analysis_mode", "") or ""),
            record_pose=bool(d.get("record_pose", False)),
            angle_mode=d.get("angle_mode"),
            curve_target=d.get("curve_target"),
            driver=DriverSpec.from_dict(d.get("driver")),
            drivers=[DriverSpec.from_dict(x) for x in drivers_src],
            output=OutputSpec.from_dict(d.get("output")),
            outputs=[OutputSpec.from_dict(x) for x in outputs_src],
            sweep=SweepSpec.from_dict(d.get("sweep")),
            solver=dict(d.get("solver") or {}),
            loads=list(d.get("loads") or []),
            friction_joints=list(d.get("friction_joints") or []),
            measurements=dict(d.get("measurements") or {}),
            extra={k: v for k, v in d.items() if k not in known},
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(self.extra)
        payload.update({
            "schema_version": self.schema_version,
            "target_input_deg": self.target_input_deg,
            "target_input_deg_list": list(self.target_input_deg_list),
            "analysis_mode": self.analysis_mode,
            "record_pose": self.record_pose,
            "driver": self.driver.to_dict(),
            "drivers": [x.to_dict() for x in self.drivers],
            "output": self.output.to_dict(),
            "outputs": [x.to_dict() for x in self.outputs],
            "sweep": self.sweep.to_dict(),
            "solver": dict(self.solver),
            "loads": list(self.loads),
            "friction_joints": list(self.friction_joints),
            "measurements": dict(self.measurements),
        })
        if self.name is not None:
            payload["name"] = self.name
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        if self.created_utc:
            payload["created_utc"] = self.created_utc
        if self.updated_utc:
            payload["updated_utc"] = self.updated_utc
        if self.project_uuid:
            payload["project_uuid"] = self.project_uuid
        if self.angle_mode is not None:
            payload["angle_mode"] = self.angle_mode
        if self.curve_target is not None:
            payload["curve_target"] = self.curve_target
        return payload


@dataclass
class ReplayFrame:
    values: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ReplayFrame":
        return cls(dict(data or {}))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.values)


@dataclass
class RunRecord:
    run_id: str
    path: str
    success: Optional[bool] = None
    n_steps: Optional[int] = None
    success_rate: Optional[float] = None
    max_hard_err: Optional[float] = None
    elapsed_sec: Optional[float] = None
    updated_utc: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "RunRecord":
        d = dict(data or {})
        return cls(
            run_id=str(d.get("run_id", "") or ""),
            path=str(d.get("path", "") or ""),
            success=d.get("success"),
            n_steps=d.get("n_steps"),
            success_rate=d.get("success_rate"),
            max_hard_err=d.get("max_hard_err"),
            elapsed_sec=d.get("elapsed_sec"),
            updated_utc=str(d.get("updated_utc", "") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayBundle:
    run: RunRecord
    frames: List[ReplayFrame] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run": self.run.to_dict(),
            "frames": [f.to_dict() for f in self.frames],
        }


def ensure_case_spec_dict(case_spec: CaseSpec | Mapping[str, Any] | None) -> Dict[str, Any]:
    if isinstance(case_spec, CaseSpec):
        return case_spec.to_dict()
    return dict(case_spec or {})


def ensure_frame_dicts(frames: Sequence[ReplayFrame | Mapping[str, Any]] | None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for frame in frames or []:
        if isinstance(frame, ReplayFrame):
            out.append(frame.to_dict())
        else:
            out.append(dict(frame))
    return out


def ensure_run_record(run: RunRecord | Mapping[str, Any] | None) -> RunRecord:
    if isinstance(run, RunRecord):
        return run
    return RunRecord.from_dict(run)
