from __future__ import annotations

import math
import os
import json
from pathlib import Path
from typing import Iterable, Tuple, Optional, Dict, Any, List

from ..core.commands import Command
from ..core.case_run_manager import CaseRunManager


def _user_template_root() -> Path:
    root = Path.home() / ".planar_sketch" / "intel_templates"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _user_template_path(template_id: str) -> Path:
    tid = (template_id or "").strip().lower()
    safe = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in tid) or "custom_template"
    return _user_template_root() / f"{safe}.json"




def _user_template_preview_dir() -> Path:
    d = _user_template_root() / "previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_template_preview_path(template_id: str) -> Path:
    tid = (template_id or "").strip().lower()
    safe = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in tid) or "custom_template"
    return _user_template_preview_dir() / f"{safe}.png"


def _user_template_index_path() -> Path:
    return _user_template_root() / "index.json"


def _load_user_template_index() -> Dict[str, Any]:
    p = _user_template_index_path()
    if not p.exists():
        return {"version": 1, "templates": []}
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(d, dict):
            raise ValueError
        d.setdefault('version', 1)
        d.setdefault('templates', [])
        if not isinstance(d.get('templates'), list):
            d['templates'] = []
        return d
    except Exception:
        return {"version": 1, "templates": []}


def _save_user_template_index(data: Dict[str, Any]) -> None:
    _user_template_index_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def list_user_templates() -> List[Dict[str, Any]]:
    """Return user templates from index.

    The index can contain stale entries (e.g. the user deleted the JSON file).
    We filter missing templates here so UI lists don't show ghost records.
    """
    idx = _load_user_template_index()
    out: List[Dict[str, Any]] = []
    for rec in idx.get('templates', []) or []:
        if not isinstance(rec, dict):
            continue
        tid = str(rec.get('template_id') or '').strip().lower()
        if not tid:
            continue
        jpath = str(rec.get('json_path') or '').strip()
        p = Path(jpath) if jpath else _user_template_path(tid)
        try:
            if not p.exists():
                continue
        except Exception:
            continue
        out.append(dict(rec))
    return out




def delete_user_template(template_id: str, *, remove_preview: bool = True) -> dict:
    """Delete a user template JSON (and optional preview image).

    Returns summary dict. Raises FileNotFoundError if missing.
    """
    tid = str(template_id or '').strip()
    if not tid:
        raise ValueError('template_id is required')
    # Use refactored helper path builder
    tpath = _user_template_path(tid)
    if not tpath.exists():
        raise FileNotFoundError(f'user template not found: {tid}')
    preview_candidates = []
    try:
        data = json.loads(tpath.read_text(encoding='utf-8'))
        pth = str((data or {}).get('preview_image_path') or '').strip()
        if pth:
            preview_candidates.append(Path(pth))
    except Exception:
        pass
    preview_candidates.append(_user_template_preview_path(tid))
    tpath.unlink()

    # Keep index.json in sync (prevents deleted templates from still showing up).
    try:
        idx = _load_user_template_index()
        rows = idx.get('templates', []) or []
        new_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = str(r.get('template_id') or '').strip().lower()
            if rid == tid.lower():
                continue
            new_rows.append(r)
        idx['templates'] = new_rows
        _save_user_template_index(idx)
    except Exception:
        pass
    removed_preview = []
    if remove_preview:
        seen=set()
        for pp in preview_candidates:
            try:
                rp = str(pp.resolve())
            except Exception:
                rp = str(pp)
            if rp in seen:
                continue
            seen.add(rp)
            try:
                if pp.exists() and pp.is_file():
                    pp.unlink()
                    removed_preview.append(str(pp))
            except Exception:
                pass
    return {'ok': True, 'template_id': tid, 'json_path': str(tpath), 'removed_preview': removed_preview}
def save_current_model_as_template(
    ctrl,
    template_id: str,
    *,
    mode: str = "override",
    name: Optional[str] = None,
    family: Optional[str] = None,
    tags: Optional[List[str]] = None,
    description: Optional[str] = None,
    concept_id: Optional[str] = None,
    base_template_id: Optional[str] = None,
    preview_image_path: Optional[str] = None,
    synthesis_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Save current sketch as a user template or override and record metadata/index."""
    tid = (template_id or "").strip().lower()
    if not tid:
        raise ValueError("template_id is empty")
    data = ctrl.to_dict()
    meta = dict(data.get("intel_user_template", {}) or {})
    meta.update({
        "template_id": tid,
        "saved_from": "intelligent_design",
        "schema": "intel_user_template_v2",
        "mode": (mode or 'override'),
        "name": (name or tid),
        "family": family or meta.get('family') or '',
        "tags": list(tags or []),
        "description": description or '',
        "concept_id": concept_id or '',
        "base_template_id": (base_template_id or ''),
    })
    if isinstance(synthesis_profile, dict) and synthesis_profile:
        # Mark this template as synthesis-capable and persist the profile.
        meta['synthesis_enabled'] = True
        meta['synthesis_profile'] = dict(synthesis_profile)
    else:
        meta.pop('synthesis_enabled', None)
        meta.pop('synthesis_profile', None)
    if preview_image_path:
        meta['preview_image_path'] = str(preview_image_path)
    data["intel_user_template"] = meta
    path = _user_template_path(tid)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    idx = _load_user_template_index()
    rows = idx.get('templates', []) or []
    # preserve existing row to keep numbering/order stable on override
    existing = None
    new_rows = []
    for r in rows:
        if isinstance(r, dict) and str(r.get('template_id','')).strip().lower() == tid:
            existing = dict(r)
        else:
            new_rows.append(r)
    rows = new_rows
    max_order = 0
    for r in rows:
        try:
            max_order = max(max_order, int((r or {}).get('display_order') or 0))
        except Exception:
            pass
    if not preview_image_path and existing and str((existing or {}).get('preview_image_path') or '').strip():
        preview_image_path = str(existing.get('preview_image_path') or '')
    row = {
        'template_id': tid,
        'name': str(name or tid),
        'family': str(family or ''),
        'tags': list(tags or []),
        'description': str(description or ''),
        'concept_id': str(concept_id or ''),
        'base_template_id': str(base_template_id or ''),
        'source': 'override' if (mode or 'override') == 'override' else 'user',
        'json_path': str(path),
        'preview_image_path': str(preview_image_path or ''),
        'synthesis_enabled': bool(meta.get('synthesis_enabled', False)),
        'display_order': int((existing or {}).get('display_order') or (max_order + 1)),
    }
    rows.append(row)
    idx['templates'] = rows
    _save_user_template_index(idx)
    return str(path)


def _load_user_template_data(template_id: str):
    path = _user_template_path(template_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def insert_template(
    ctrl,
    template_id: str,
    center_xy: Tuple[float, float] = (0.0, 0.0),
    scale: float = 1.0,
    open_angle_deg: Optional[float] = None,
    auto_setup_io_cases: bool = True,
    solve_after_insert: bool = True,
    return_info: bool = False,
) -> Optional[Dict[str, Any]]:
    """Insert a starter mechanism onto the canvas.

    Notes
    -----
    - This uses a single undo step by snapshotting the model.
    - The inserted mechanisms are *templates* (good starting layouts), not
      optimized solutions.
    """

    if not getattr(ctrl, "_confirm_stop_replay", lambda _a: True)("insert a template"):
        return {} if return_info else None

    template_id = (template_id or "").strip().lower()

    # User override template: saved from manual editing workflow.
    user_tpl = _load_user_template_data(template_id)
    if isinstance(user_tpl, dict):
        ok = bool(getattr(ctrl, "load_dict")(user_tpl, clear_undo=False, action=f"insert template {template_id}"))
        if return_info:
            return {"template_id": template_id, "kind": "user_override", "ok": ok}
        return None

    cx, cy = float(center_xy[0]), float(center_xy[1])
    s = max(0.1, float(scale))

    before = ctrl.snapshot_model()

    def add_point(x: float, y: float, fixed: bool = False, hidden: bool = False) -> int:
        pid = int(getattr(ctrl, "_next_pid"))
        ctrl._next_pid = pid + 1
        ctrl._create_point(pid, float(x), float(y), fixed=bool(fixed), hidden=bool(hidden), traj_enabled=False)
        return pid

    def add_link(i: int, j: int, hidden: bool = False) -> int:
        lid = int(getattr(ctrl, "_next_lid"))
        ctrl._next_lid = lid + 1
        pi, pj = ctrl.points[i], ctrl.points[j]
        L = math.hypot(float(pj["x"]) - float(pi["x"]), float(pj["y"]) - float(pi["y"]))
        ctrl._create_link(lid, i, j, L=L, hidden=bool(hidden))
        return lid

    def add_point_line(p: int, i: int, j: int, hidden: bool = False) -> int:
        plid = int(getattr(ctrl, "_next_plid"))
        ctrl._next_plid = plid + 1
        ctrl._create_point_line(plid, p=p, i=i, j=j, hidden=bool(hidden), enabled=True)
        return plid

    def add_spline(point_ids: List[int], hidden: bool = False, closed: bool = False) -> int:
        sid = int(getattr(ctrl, "_next_sid"))
        ctrl._next_sid = sid + 1
        ctrl._create_spline(sid, list(point_ids), hidden=bool(hidden), closed=bool(closed))
        return sid

    def add_point_spline_dist(p: int, s_id: int, dist: float, hidden: bool = False) -> int:
        pdid = int(getattr(ctrl, "_next_pdid"))
        ctrl._next_pdid = pdid + 1
        ctrl._create_point_spline_dist(pdid, p=int(p), s=int(s_id), dist=float(dist), hidden=bool(hidden), enabled=True, hint_seg=-1)
        return pdid

    def add_point_spline(p: int, s_id: int, hidden: bool = False) -> int:
        psid = int(getattr(ctrl, "_next_psid"))
        ctrl._next_psid = psid + 1
        ctrl._create_point_spline(psid, p=int(p), s=int(s_id), hidden=bool(hidden), enabled=True)
        return psid

    def add_body(name: str, point_ids: List[int], hidden: bool = False, color_name: str = "Blue") -> int:
        bid = int(getattr(ctrl, "_next_bid"))
        ctrl._next_bid = bid + 1
        ctrl._create_body(bid, name=str(name), point_ids=list(point_ids), hidden=bool(hidden), color_name=str(color_name))
        return bid

    def _project_dir() -> str:
        """Return the directory used for cases/runs.

        IMPORTANT: Do **not** fall back to ``os.getcwd()``.
        Using the process working directory causes stale `cases/` and `runs/` from
        previous sessions to be picked up.
        """
        try:
            win = getattr(ctrl, "win", None)
            if win is not None:
                project_dir = getattr(win, "project_dir", None)
                if project_dir:
                    return str(project_dir)
                current_file = getattr(win, "current_file", None)
                if current_file:
                    return os.path.dirname(str(current_file))
                import tempfile

                scratch = getattr(win, "project_dir", None)
                if not scratch:
                    scratch = tempfile.mkdtemp(prefix="planar_sketch_session_")
                    try:
                        setattr(win, "project_dir", scratch)
                    except Exception:
                        pass
                return str(scratch)
        except Exception:
            pass
        import tempfile

        return tempfile.mkdtemp(prefix="planar_sketch_session_")

    def _auto_setup_door_io(A: int, B: int, C: int, D: int) -> None:
        """Best-effort auto setup for door I/O mapping + cases + optimization preset."""
        if not auto_setup_io_cases:
            return

        # 1) Configure driver/output on the live model.
        try:
            ctrl.clear_driver()
            ctrl.clear_output()
            ctrl.set_driver_angle(A, B)  # input: crank AB
            ctrl.set_output(D, C)        # output: rocker DC
            # Helpful default measures.
            ctrl.add_measure_angle(A, B)
            ctrl.add_measure_angle(D, C)
        except Exception:
            pass

        # 2) Create mapping cases: input_deg -> target output_deg.
        # IMPORTANT: Keep this consistent with SynthesisTab single-case workflow.
        # We store an explicit curve_target so the Synthesis tab can immediately
        # display keypoints even if it was already created earlier.
        angle = float(open_angle_deg) if open_angle_deg is not None else 90.0
        angle = max(0.0, min(180.0, angle))
        inputs = [0.0, angle / 3.0, 2.0 * angle / 3.0, angle]

        # Targets are parameters so users can tweak quickly without rewriting expressions.
        # Also store IN_i for symmetry and easier expression authoring.
        out_param_names: List[str] = []
        mapping_points: List[Tuple[float, float]] = []
        for idx, inp in enumerate(inputs, start=1):
            try:
                ctrl.parameters.set_param(f"IN_{idx}", float(inp))
            except Exception:
                pass
            pname = f"OUT_{idx}"
            out_param_names.append(pname)
            try:
                ctrl.parameters.set_param(pname, float(inp))
            except Exception:
                pass
            mapping_points.append((float(inp), float(inp)))

        manager = CaseRunManager(_project_dir(), project_uuid=getattr(ctrl, "project_uuid", "") or "")

        # Single-case workflow (matches Synthesis tab):
        # - One sweep case from 0 -> open_angle
        # - Explicit curve_target points so UI can show them without extra steps
        # - OUT_1..OUT_4 params remain for user tuning and optimization expressions
        case_spec: Dict[str, Any] = {
            "schema_version": "1.0",
            "analysis_mode": "quasi_static",
            "kind": "io_curve",
            "name": "I/O Curve (single case)",
            "driver": {"enabled": True, "type": "angle", "pivot": int(A), "tip": int(B), "rad": 0.0},
            "drivers": [{"enabled": True, "type": "angle", "pivot": int(A), "tip": int(B), "rad": 0.0}],
            "output": {"enabled": True, "pivot": int(D), "tip": int(C), "rad": 0.0},
            "outputs": [{"enabled": True, "pivot": int(D), "tip": int(C), "rad": 0.0}],
            "solver": {"name": "scipy", "max_nfev": 250, "pbd_iters": 120, "hard_err_tol": 1e-3, "treat_point_spline_as_soft": False},
            "angle_mode": "relative",
            "sweep": {"start_deg": 0.0, "end_deg": float(angle), "step_count": 61, "adaptive": False},
            "curve_target": {
                "kind": "io_angle",
                "input_key": "input_deg",
                "output_key": "output_deg",
                "points": [[float(a), float(b)] for a, b in mapping_points],
            },
            "loads": list(getattr(ctrl, "loads", []) or []),
            "friction_joints": list(getattr(ctrl, "friction_joints", []) or []),
            "measurements": {
                "measures": list(getattr(ctrl, "measures", []) or []),
                "load_measures": list(getattr(ctrl, "load_measures", []) or []),
            },
            "io_map": {
                "inputs_deg": list(inputs),
                "out_params": list(out_param_names),
            },
        }

        info = manager.get_or_create_case(case_spec)
        manager.set_active_case(info.name)
        created_case_names: List[str] = [info.name]

        # Best effort: if Synthesis tab already exists, refresh its mapping points.
        try:
            win = getattr(ctrl, 'win', None)
            sp = getattr(win, 'sim_panel', None) if win else None
            st = getattr(sp, 'synthesis_tab', None) if sp else None
            if st is not None:
                if hasattr(st, 'sync_from_project'):
                    st.sync_from_project(force=True)
                elif hasattr(st, '_load_mapping_from_project_or_default'):
                    st._load_mapping_from_project_or_default()
        except Exception:
            pass
        # 3) Build an Optimization preset consistent with the Synthesis tab.
        # IMPORTANT: the objective must reflect curve-fit quality (curve_err),
        # otherwise optimization can report a tiny score while the I/O curve is
        # obviously wrong.
        tol = 2.0
        variables: List[Dict[str, Any]] = []
        for lid in sorted(getattr(ctrl, "links", {}).keys()):
            lk = ctrl.links.get(lid) or {}
            try:
                i = int(lk.get("i", -1))
                j = int(lk.get("j", -1))
            except Exception:
                continue
            if lk.get("ref", False):
                continue
            if bool(ctrl.points.get(i, {}).get("fixed", False)) and bool(ctrl.points.get(j, {}).get("fixed", False)):
                continue
            L = float(lk.get("L", 0.0) or 0.0)
            if L <= 1e-9:
                continue
            variables.append({"name": f"Link{lid}.L", "lower": 0.7 * L, "upper": 1.3 * L, "enabled": True, "case_id": None})

        # Constraints (match Synthesis tab single-case preset)
        constraints: List[Dict[str, Any]] = []
        for case_id in created_case_names:
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "max(curve_abs_err)",
                    "comparator": "<=",
                    "limit": float(tol),
                }
            )
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "valid_ratio",
                    "comparator": ">=",
                    "limit": 0.95,
                }
            )
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": "output_span / (target_span + 1e-9)",
                    "comparator": ">=",
                    "limit": 0.8,
                }
            )

        preset: Dict[str, Any] = {
            "schema_version": "1.0",
            "kind": "synthesis_io_curve_single_case",
            "variables": variables,
            "objectives": [
                {
                    "enabled": True,
                    "case_id": created_case_names[0] if created_case_names else None,
                    "direction": "min",
                    "expression": "rms(curve_err) + 1000*mean(hard_err) + 1000*(1-valid_ratio)",
                }
            ],
            "constraints": constraints,
            "run": {"evals": 400, "seed": ""},
        }

        # Persist preset for the project (optional, best effort).
        try:
            os.makedirs(manager.cases_dir, exist_ok=True)
            preset_path = os.path.join(manager.cases_dir, "optimization_preset.json")
            import json

            with open(preset_path, "w", encoding="utf-8") as fh:
                json.dump(preset, fh, indent=2, sort_keys=True)
        except Exception:
            pass

        # Apply to Optimization tab if present.
        try:
            win = getattr(ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            opt_tab = getattr(sim_panel, "optimization_tab", None) if sim_panel else None
            if opt_tab is not None and hasattr(opt_tab, "apply_preset"):
                opt_tab.apply_preset(preset)
                anim_tab = getattr(sim_panel, "animation_tab", None)
                if anim_tab is not None and hasattr(anim_tab, "refresh_cases"):
                    anim_tab.refresh_cases()
        except Exception:
            pass

    def _auto_setup_slider_io(A: int, B: int, plid: int, slider_pid: int) -> None:
        """Best-effort auto setup for slider-crank I/O mapping + cases + optimization preset.

        - Driver: crank angle A->B
        - Output signal: translation measure 's' for the point-on-line (plid) constraint
        """
        if not auto_setup_io_cases:
            return

        # 1) Configure driver + a translation measurement on the slider point.
        measure_name = ""
        try:
            ctrl.clear_driver()
            ctrl.clear_output()
            ctrl.set_driver_angle(A, B)
            ctrl.add_measure_translation(plid)
            pl = ctrl.point_lines.get(int(plid), {})
            measure_name = str(pl.get("name", "")) or ctrl._point_line_offset_name(pl)
        except Exception:
            pass
        if not measure_name:
            measure_name = f"s P{int(slider_pid)} on rail"

        # 2) Create mapping cases: input_deg -> target translation (s) [same unit as sketch length].
        angle = float(open_angle_deg) if open_angle_deg is not None else 90.0
        angle = max(0.0, min(180.0, angle))
        inputs = [0.0, angle / 3.0, 2.0 * angle / 3.0, angle]

        out_param_names: List[str] = []
        # Initialize parameters with the current slider value (fallback: use input angle as dummy).
        base_val = 0.0
        try:
            # Attempt a quick read by sampling current measure value from the live model.
            vals = {nm: val for nm, val, _u in ctrl.get_measure_values()}
            base_val = float(vals.get(measure_name, 0.0))
        except Exception:
            base_val = 0.0
        for idx, _inp in enumerate(inputs, start=1):
            pname = f"SLIDE_{idx}"
            out_param_names.append(pname)
            try:
                ctrl.parameters.set_param(pname, float(base_val))
            except Exception:
                pass

        manager = CaseRunManager(_project_dir(), project_uuid=getattr(ctrl, "project_uuid", "") or "")
        created_case_names: List[str] = []
        for inp in inputs:
            case_spec: Dict[str, Any] = {
                "schema_version": "1.0",
                "analysis_mode": "quasi_static",
                "name": f"Slider map @{inp:.1f}deg",
                "driver": {"enabled": True, "type": "angle", "pivot": int(A), "tip": int(B), "rad": 0.0},
                "output": {"enabled": False, "pivot": int(A), "tip": int(B), "rad": 0.0},
                "solver": {"name": "scipy", "max_nfev": 250, "pbd_iters": 120},
                "sweep": {"start_deg": float(inp), "end_deg": float(inp), "step_count": 1, "adaptive": False},
                "measurements": {
                    "measures": list(getattr(ctrl, "measures", []) or []),
                    "load_measures": list(getattr(ctrl, "load_measures", []) or []),
                },
            }
            info = manager.get_or_create_case(case_spec)
            created_case_names.append(info.name)

        if created_case_names:
            manager.set_active_case(created_case_names[0])

        # 3) Build an Optimization preset (length variables + constraints on the translation measure).
        tol = 2.0  # length unit tolerance (e.g., mm if sketch is in mm)
        variables: List[Dict[str, Any]] = []
        for lid in sorted(getattr(ctrl, "links", {}).keys()):
            lk = ctrl.links.get(lid) or {}
            try:
                i = int(lk.get("i", -1))
                j = int(lk.get("j", -1))
            except Exception:
                continue
            if lk.get("ref", False):
                continue
            if bool(ctrl.points.get(i, {}).get("fixed", False)) and bool(ctrl.points.get(j, {}).get("fixed", False)):
                continue
            L = float(lk.get("L", 0.0) or 0.0)
            if L <= 1e-9:
                continue
            variables.append({"name": f"Link{lid}.L", "lower": 0.7 * L, "upper": 1.3 * L, "enabled": True, "case_id": None})

        constraints: List[Dict[str, Any]] = []
        safe_measure = measure_name.replace('"', '\"')
        for idx, case_id in enumerate(created_case_names, start=1):
            pname = out_param_names[idx - 1] if idx - 1 < len(out_param_names) else f"SLIDE_{idx}"
            constraints.append(
                {
                    "enabled": True,
                    "case_id": str(case_id),
                    "expression": f"abs(first(\"{safe_measure}\") - Param.{pname})",
                    "comparator": "<=",
                    "limit": tol,
                }
            )

        preset: Dict[str, Any] = {
            "schema_version": "1.0",
            "kind": "slider_io_mapping",
            "variables": variables,
            "objectives": [{"enabled": True, "case_id": None, "direction": "min", "expression": "mean(hard_err)"}],
            "constraints": constraints,
            "run": {"evals": 400, "seed": ""},
        }

        # Persist preset (best effort).
        try:
            os.makedirs(manager.cases_dir, exist_ok=True)
            preset_path = os.path.join(manager.cases_dir, "optimization_preset.json")
            import json

            with open(preset_path, "w", encoding="utf-8") as fh:
                json.dump(preset, fh, indent=2, sort_keys=True)
        except Exception:
            pass

        # Apply to Optimization tab if present.
        try:
            win = getattr(ctrl, "win", None)
            sim_panel = getattr(win, "sim_panel", None) if win else None
            opt_tab = getattr(sim_panel, "optimization_tab", None) if sim_panel else None
            if opt_tab is not None and hasattr(opt_tab, "apply_preset"):
                opt_tab.apply_preset(preset)
                anim_tab = getattr(sim_panel, "animation_tab", None)
                if anim_tab is not None and hasattr(anim_tab, "refresh_cases"):
                    anim_tab.refresh_cases()
        except Exception:
            pass

    info: Dict[str, Any] = {}

    def do_insert() -> None:
        inserted_pts: list[int] = []

        if template_id in ("4bar", "4bar_door", "fourbar", "four_bar"):
            # A simple crank-rocker-ish layout (good as a door/hatch starter).
            # Ground pivots: A, D (fixed)
            A = add_point(cx - 200 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 200 * s, cy, fixed=True); inserted_pts.append(D)
            # Moving joints
            B = add_point(cx - 120 * s, cy + 120 * s); inserted_pts.append(B)
            C = add_point(cx + 120 * s, cy + 80 * s); inserted_pts.append(C)

            info.update({"A": A, "B": B, "C": C, "D": D})

            # Links
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            # Optional ground visual (hidden by default)
            add_link(A, D, hidden=True)

            _auto_setup_door_io(A, B, C, D)

        elif template_id in ("4bar_crank_rocker", "crank_rocker"):
            # Crank-rocker: one link can rotate continuously, the opposite link oscillates.
            A = add_point(cx - 220 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 180 * s, cy - 20 * s, fixed=True); inserted_pts.append(D)
            B = add_point(cx - 80 * s, cy + 140 * s); inserted_pts.append(B)
            C = add_point(cx + 120 * s, cy + 80 * s); inserted_pts.append(C)
            info.update({"A": A, "B": B, "C": C, "D": D})
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)
            _auto_setup_door_io(A, B, C, D)

        elif template_id in ("4bar_double_rocker", "double_rocker"):
            # Double-rocker: both grounded links oscillate (good for compact hinges).
            A = add_point(cx - 200 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 200 * s, cy, fixed=True); inserted_pts.append(D)
            B = add_point(cx - 80 * s, cy + 140 * s); inserted_pts.append(B)
            C = add_point(cx + 60 * s, cy + 150 * s); inserted_pts.append(C)
            info.update({"A": A, "B": B, "C": C, "D": D})
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)
            _auto_setup_door_io(A, B, C, D)

        elif template_id in ("4bar_toggle", "toggle"):
            # Toggle / clamp starter: near-collinear at one extreme (users can tune).
            A = add_point(cx - 220 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 220 * s, cy, fixed=True); inserted_pts.append(D)
            B = add_point(cx - 40 * s, cy + 40 * s); inserted_pts.append(B)
            C = add_point(cx + 40 * s, cy + 20 * s); inserted_pts.append(C)
            info.update({"A": A, "B": B, "C": C, "D": D})
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)
            _auto_setup_door_io(A, B, C, D)

        elif template_id in ("slider", "slider_crank", "slider-crank", "crank_slider"):
            # Slider-crank with a fixed rail (point-on-line constraint).
            A = add_point(cx - 160 * s, cy, fixed=True); inserted_pts.append(A)
            B = add_point(cx - 60 * s, cy + 90 * s); inserted_pts.append(B)
            # Rail endpoints (fixed)
            R1 = add_point(cx - 260 * s, cy - 160 * s, fixed=True, hidden=True); inserted_pts.append(R1)
            R2 = add_point(cx + 260 * s, cy - 160 * s, fixed=True, hidden=True); inserted_pts.append(R2)
            # Slider point on rail
            C = add_point(cx + 60 * s, cy - 160 * s, fixed=False); inserted_pts.append(C)
            plid = add_point_line(p=C, i=R1, j=R2, hidden=True)

            info.update({"A": A, "B": B, "C": C, "R1": R1, "R2": R2, "plid": plid})

            add_link(A, B)
            add_link(B, C)

            _auto_setup_slider_io(A, B, plid, C)

        elif template_id in ("offset_slider_crank", "slider_crank_offset"):
            # Offset slider-crank: rail is offset from crank pivot.
            A = add_point(cx - 160 * s, cy + 60 * s, fixed=True); inserted_pts.append(A)
            B = add_point(cx - 40 * s, cy + 160 * s); inserted_pts.append(B)
            R1 = add_point(cx - 260 * s, cy - 160 * s, fixed=True, hidden=True); inserted_pts.append(R1)
            R2 = add_point(cx + 260 * s, cy - 160 * s, fixed=True, hidden=True); inserted_pts.append(R2)
            C = add_point(cx + 80 * s, cy - 160 * s, fixed=False); inserted_pts.append(C)
            plid = add_point_line(p=C, i=R1, j=R2, hidden=True)
            info.update({"A": A, "B": B, "C": C, "R1": R1, "R2": R2, "plid": plid})
            add_link(A, B)
            add_link(B, C)
            _auto_setup_slider_io(A, B, plid, C)

        elif template_id in ("dual_slider", "two_rail"):
            # Dual-slider: one slider on horizontal rail, one on vertical rail, linked together.
            O = add_point(cx - 180 * s, cy + 120 * s, fixed=True); inserted_pts.append(O)
            # Horizontal rail
            H1 = add_point(cx - 320 * s, cy, fixed=True, hidden=True); inserted_pts.append(H1)
            H2 = add_point(cx + 320 * s, cy, fixed=True, hidden=True); inserted_pts.append(H2)
            S1 = add_point(cx - 60 * s, cy, fixed=False); inserted_pts.append(S1)
            pl1 = add_point_line(p=S1, i=H1, j=H2, hidden=True)
            # Vertical rail
            V1 = add_point(cx + 160 * s, cy - 260 * s, fixed=True, hidden=True); inserted_pts.append(V1)
            V2 = add_point(cx + 160 * s, cy + 260 * s, fixed=True, hidden=True); inserted_pts.append(V2)
            S2 = add_point(cx + 160 * s, cy + 40 * s, fixed=False); inserted_pts.append(S2)
            pl2 = add_point_line(p=S2, i=V1, j=V2, hidden=True)
            # Links
            B = add_point(cx - 80 * s, cy + 80 * s); inserted_pts.append(B)
            add_link(O, B)
            add_link(B, S1)
            add_link(S1, S2)
            info.update({"O": O, "B": B, "S1": S1, "S2": S2, "pl1": pl1, "pl2": pl2})
            # Basic IO: use O->B as driver, measure translation of S1.
            _auto_setup_slider_io(O, B, pl1, S1)

        elif template_id in ("cam_roller_translating", "cam_translating", "cam_disk_slider"):
            # Cam + translating roller follower (rebuilt to use explicit bodies like user examples).
            roller_R = 18.0 * s

            # --- Cam body (B0): center O + driver tip T + closed spline points ---
            O = add_point(cx - 140 * s, cy, fixed=True); inserted_pts.append(O)
            T = add_point(cx - 60 * s, cy + 10 * s); inserted_pts.append(T)
            cam_pts: List[int] = []
            for k in range(10):
                th = 2.0 * math.pi * k / 10.0
                bump = 1.0 + 0.22 * math.exp(-((th - 0.15) ** 2) / (2.0 * (0.45 ** 2)))
                rr = 88.0 * s * bump
                pid = add_point(cx - 140 * s + rr * math.cos(th), cy + rr * math.sin(th), fixed=False)
                inserted_pts.append(pid); cam_pts.append(pid)
            sid = add_spline(cam_pts, hidden=False, closed=True)
            cam_bid = add_body("B0", [O, T] + cam_pts, hidden=False, color_name="Green")
            add_link(O, T, hidden=True)  # explicit driver radius for SciPy robustness

            # --- Slider/follower body (B1): two guide points + roller center ---
            rail_y = cy - 180 * s
            R1 = add_point(cx - 360 * s, rail_y, fixed=True, hidden=True); inserted_pts.append(R1)
            R2 = add_point(cx + 360 * s, rail_y, fixed=True, hidden=True); inserted_pts.append(R2)
            G1 = add_point(cx + 85 * s, rail_y); inserted_pts.append(G1)
            # Keep both guide points on the same rail line (horizontal) to avoid immediate inconsistency.
            G2 = add_point(cx + 147 * s, rail_y); inserted_pts.append(G2)
            P = add_point(cx + 85 * s, rail_y + 62 * s); inserted_pts.append(P)
            pl1 = add_point_line(p=G1, i=R1, j=R2, hidden=False)
            pl2 = add_point_line(p=G2, i=R1, j=R2, hidden=False)
            f_bid = add_body("B1", [G1, G2, P], hidden=False, color_name="Blue")

            # Keep follower geometry visible with links (not hidden) so pivots/arms are understandable.
            add_link(G1, G2, hidden=False)
            add_link(G1, P, hidden=False)
            add_link(G2, P, hidden=True)  # close triangle so SciPy remains rigid even if body constraints are bypassed

            # Contact: point-spline distance for roller, and optional point-on-spline if R=0 later.
            pdid = add_point_spline_dist(P, sid, dist=roller_R, hidden=False)

            info.update({
                "O": O, "T": T, "cam_spline": sid, "cam_pts": cam_pts, "cam_bid": cam_bid,
                "R1": R1, "R2": R2, "G1": G1, "G2": G2, "P": P, "pl1": pl1, "pl2": pl2,
                "follower_bid": f_bid, "pdid": pdid, "roller_R": roller_R
            })

            try:
                ctrl.clear_driver()
                ctrl.set_driver_angle(O, T)
            except Exception:
                pass

        elif template_id in ("cam_roller_oscillating", "cam_oscillating", "cam_disk_rocker"):
            # Cam + oscillating roller follower (body-based layout, closer to camdemo.json semantics).
            roller_R = 16.0 * s

            # Cam body B0
            O = add_point(cx - 120 * s, cy, fixed=True); inserted_pts.append(O)
            T = add_point(cx - 45 * s, cy + 15 * s); inserted_pts.append(T)
            cam_pts: List[int] = []
            for k in range(10):
                th = 2.0 * math.pi * k / 10.0
                bump = 1.0 + 0.20 * math.exp(-((th - 0.35) ** 2) / (2.0 * (0.50 ** 2)))
                rr = 84.0 * s * bump
                pid = add_point(cx - 120 * s + rr * math.cos(th), cy + rr * math.sin(th), fixed=False)
                inserted_pts.append(pid); cam_pts.append(pid)
            sid = add_spline(cam_pts, hidden=False, closed=True)
            cam_bid = add_body("B0", [O, T] + cam_pts, hidden=False, color_name="Green")
            add_link(O, T, hidden=True)  # explicit driver radius for SciPy robustness

            # Oscillating follower body B1: fixed pivot F, roller center P, aux point Q
            F = add_point(cx + 170 * s, cy - 30 * s, fixed=True); inserted_pts.append(F)
            P = add_point(cx + 65 * s, cy + 30 * s); inserted_pts.append(P)
            Q = add_point(cx + 210 * s, cy + 80 * s); inserted_pts.append(Q)
            f_bid = add_body("B1", [F, P, Q], hidden=False, color_name="Blue")
            add_link(F, P, hidden=False)
            add_link(F, Q, hidden=False)
            add_link(P, Q, hidden=True)  # close triangle; prevents follower collapsing to a line under under-constrained solves

            pdid = add_point_spline_dist(P, sid, dist=roller_R, hidden=False)

            info.update({
                "O": O, "T": T, "cam_spline": sid, "cam_pts": cam_pts, "cam_bid": cam_bid,
                "F": F, "P": P, "Q": Q, "follower_bid": f_bid, "pdid": pdid, "roller_R": roller_R
            })

            try:
                ctrl.clear_driver()
                ctrl.set_driver_angle(O, T)
            except Exception:
                pass

        elif template_id in ("6bar_watt1", "watt1"):
            # A practical 6-link (incl. ground) starter with two 4-bar loops sharing a joint.
            # Ground pivots: A, D, E (fixed)
            A = add_point(cx - 260 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 220 * s, cy - 40 * s, fixed=True); inserted_pts.append(D)
            E = add_point(cx + 80 * s, cy - 220 * s, fixed=True); inserted_pts.append(E)
            # Shared joint between loops
            C = add_point(cx + 80 * s, cy + 140 * s); inserted_pts.append(C)
            B = add_point(cx - 120 * s, cy + 160 * s); inserted_pts.append(B)
            F = add_point(cx + 160 * s, cy - 120 * s); inserted_pts.append(F)

            info.update({"A": A, "B": B, "C": C, "D": D, "E": E, "F": F})
            # Loop 1: A-B-C-D
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)
            # Loop 2: D-C-F-E (shares joint C)
            add_link(C, F)
            add_link(F, E)
            add_link(D, E, hidden=True)

            # Door-style IO: drive A->B, output D<-C
            _auto_setup_door_io(A, B, C, D)

        elif template_id in ("6bar_stephenson1", "stephenson1"):
            # A Stephenson-like starter: two loops share a central joint.
            A = add_point(cx - 260 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 220 * s, cy - 40 * s, fixed=True); inserted_pts.append(D)
            E = add_point(cx + 120 * s, cy - 220 * s, fixed=True); inserted_pts.append(E)
            C = add_point(cx - 40 * s, cy + 160 * s); inserted_pts.append(C)
            B = add_point(cx - 140 * s, cy + 40 * s); inserted_pts.append(B)
            F = add_point(cx + 80 * s, cy + 140 * s); inserted_pts.append(F)

            info.update({"A": A, "B": B, "C": C, "D": D, "E": E, "F": F})
            # Loop 1: A-B-C-D
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)
            # Loop 2: A-C-F-E (shares A and C)
            add_link(A, C, hidden=True)
            add_link(C, F)
            add_link(F, E)
            add_link(A, E, hidden=True)

            _auto_setup_door_io(A, B, C, D)


        else:
            # Unknown template: fallback to 4-bar
            A = add_point(cx - 200 * s, cy, fixed=True); inserted_pts.append(A)
            D = add_point(cx + 200 * s, cy, fixed=True); inserted_pts.append(D)
            B = add_point(cx - 120 * s, cy + 120 * s); inserted_pts.append(B)
            C = add_point(cx + 120 * s, cy + 80 * s); inserted_pts.append(C)
            add_link(A, B)
            add_link(B, C)
            add_link(C, D)
            add_link(A, D, hidden=True)

        # NOTE: Do not keep a persistent "last insert" cache on the controller.
        # It tends to create surprising behavior across projects and increases complexity.

        # Selection + refresh
        try:
            ctrl.selected_point_ids = set(inserted_pts)
            ctrl.selected_point_id = inserted_pts[-1] if inserted_pts else None
        except Exception:
            pass

        if solve_after_insert:
            ctrl.solve_constraints()
        ctrl.update_graphics()
        if getattr(ctrl, "panel", None):
            ctrl.panel.defer_refresh_all(keep_selection=True)
        ctrl.update_status()

    def undo_insert() -> None:
        ctrl.apply_model_snapshot(before)

    ctrl.stack.push(Command(do=do_insert, undo=undo_insert, desc=f"Insert template: {template_id}"))
    return info if return_info else None
