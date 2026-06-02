"""Registry for templates that are supported by SynthesisTab.

This module provides a single source of truth for whether a given template can
be continued in the Smart Synthesis workflow.

Design goals:
- No UI-specific logic here.
- Easy to extend: add new template ids or attach metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Dict, Optional, Iterable


@dataclass(frozen=True)
class SynthesisTemplateSpec:
    """Metadata for a template supported by synthesis.

    Notes
    -----
    Smart Synthesis distinguishes between:
    - The selection id shown in the SynthesisTab dropdown.
    - The starter insert template id used when there is no existing mechanism
      in the scene (driver/output not configured).

    For built-in templates these ids are typically the same. For user-defined
    "position synthesis" templates (e.g. sixbar_watt1_3pos) we map to a base
    starter topology (e.g. 6bar_watt1).
    """

    template_id: str
    # Optional human-friendly name override (UI may ignore this).
    name: Optional[str] = None
    # Template id used to insert starter geometry if no mechanism exists.
    insert_template_id: Optional[str] = None
    # Mechanism family hint (4bar/6bar/cam/...).
    family: Optional[str] = None


# Supported templates for Smart Synthesis.
# Extend this dict when new templates gain synthesis support.
SUPPORTED_TEMPLATES: Dict[str, SynthesisTemplateSpec] = {
    # Name is resolved from the intel library catalog so UI labels match
    # the template library dropdown (e.g. "Four-bar linkage (generic) [id]").
    "4bar_door": SynthesisTemplateSpec(template_id="4bar_door", name=None),
    "6bar_watt1": SynthesisTemplateSpec(template_id="6bar_watt1", name=None),
    "6bar_stephenson1": SynthesisTemplateSpec(template_id="6bar_stephenson1", name=None),
}


def resolve_insert_template_id(template_id: str | None) -> str:
    """Return the starter geometry template id for synthesis.

    This keeps the SynthesisTab deterministic:
    - Built-in synthesis templates insert themselves.
    - User "position synthesis" templates map to a base starter topology.
    - If no mapping is found, fall back to the selected id.
    """

    tid = str(template_id or "").strip()
    if not tid:
        return ""
    spec = SUPPORTED_TEMPLATES.get(tid)
    if spec is not None and spec.insert_template_id:
        return str(spec.insert_template_id)
    low = tid.lower()
    # Base 6-bar ids.
    if low.startswith("6bar_"):
        return tid
    # User naming conventions.
    if low.startswith("sixbar_") or low.startswith("6-bar"):
        if "watt1" in low:
            return "6bar_watt1"
        if "stephenson1" in low:
            return "6bar_stephenson1"
    if "watt1" in low:
        return "6bar_watt1"
    if "stephenson1" in low:
        return "6bar_stephenson1"
    if "4bar" in low or "fourbar" in low:
        return "4bar_door"
    return tid


def _builtin_template_name(template_id: str) -> str:
    """Return the catalog name for a built-in template id (best-effort)."""

    tid = str(template_id or "").strip()
    if not tid:
        return ""
    try:
        cat_path = Path(__file__).resolve().parent / "library" / "catalog.json"
        if not cat_path.exists():
            return ""
        cat = json.loads(cat_path.read_text(encoding="utf-8"))
        for c in list((cat or {}).get("concepts", []) or []):
            if str(c.get("template") or "").strip() == tid:
                return str(c.get("name") or "").strip()
    except Exception:
        return ""
    return ""


def can_continue_in_synthesis(template_id: str | None) -> bool:
    """Return True if the given template id can be continued in synthesis."""

    if not template_id:
        return False
    tid = str(template_id).strip()
    if tid in SUPPORTED_TEMPLATES:
        return True
    # user templates saved with synthesis profile
    try:
        from .templates import list_user_templates

        def _user_rec_supported(r: dict) -> bool:
            """Return True if this user template is compatible with synthesis.

            Smart Synthesis now supports both 4-bar and 6-bar starter pipelines.
            """

            fam = str(r.get('mechanism_family') or r.get('family') or '').strip().lower()
            concept = str(r.get('concept_id') or r.get('concept') or '').strip().lower()
            tid = str(r.get('template_id') or '').strip().lower()
            is_fourbar = fam in {'4-bar', '4bar', 'fourbar', 'four-bar'} or concept in {'4bar', 'fourbar'} or ('4bar' in tid)
            is_sixbar = fam in {'6-bar', '6bar', 'sixbar', 'six-bar'} or concept in {'6bar', 'sixbar'} or ('watt1' in tid) or ('stephenson1' in tid)
            return is_fourbar or is_sixbar

        for rec in list_user_templates():
            if not isinstance(rec, dict):
                continue
            if not rec.get('synthesis_enabled'):
                continue
            if str(rec.get('template_id') or '').strip() != tid:
                continue
            if _user_rec_supported(rec):
                return True
    except Exception:
        pass
    return False


def get_synthesis_template_spec(template_id: str) -> Optional[SynthesisTemplateSpec]:
    """Return template spec if supported, else None."""

    return SUPPORTED_TEMPLATES.get(template_id)


def list_supported_template_ids() -> list[str]:
    """Return supported template ids in a stable order.

    Includes built-in synthesis templates and user templates that were saved
    with a synthesis profile.
    """
    ids = set(SUPPORTED_TEMPLATES.keys())
    # Add user templates flagged as synthesis-enabled (and compatible with the
    # currently-supported synthesis pipelines).
    try:
        from .templates import list_user_templates  # lazy import
        for rec in list_user_templates():
            if not isinstance(rec, dict):
                continue
            if not rec.get('synthesis_enabled'):
                continue
            fam = str(rec.get('mechanism_family') or rec.get('family') or '').strip().lower()
            concept = str(rec.get('concept_id') or rec.get('concept') or '').strip().lower()
            tid_low = str(rec.get('template_id') or '').strip().lower()
            is_fourbar = fam in {'4-bar', '4bar', 'fourbar', 'four-bar'} or concept in {'4bar', 'fourbar'} or ('4bar' in tid_low)
            is_sixbar = fam in {'6-bar', '6bar', 'sixbar', 'six-bar'} or concept in {'6bar', 'sixbar'} or ('watt1' in tid_low) or ('stephenson1' in tid_low)
            if not (is_fourbar or is_sixbar):
                continue
            tid = str(rec.get('template_id') or '').strip()
            if tid:
                ids.add(tid)
    except Exception:
        pass
    return sorted(ids)


def template_display_name(template_id: str) -> str:
    """Return a human-friendly name for UI display."""

    tid = str(template_id or "").strip()
    if not tid:
        return ""
    spec = SUPPORTED_TEMPLATES.get(tid)
    if spec is None:
        # Try user template name.
        try:
            from .templates import list_user_templates
            for rec in list_user_templates():
                if str((rec or {}).get('template_id') or '').strip() == tid:
                    nm = str((rec or {}).get('name') or '').strip()
                    if nm:
                        return nm
        except Exception:
            pass
        return tid
    # Built-in templates: prefer catalog name if available.
    return str(spec.name or _builtin_template_name(tid) or spec.template_id)


def template_display_label(template_id: str, lang: str = "en") -> str:
    """UI label that matches the template library dropdown formatting."""

    tid = str(template_id or "").strip()
    if not tid:
        return ""
    base = template_display_name(tid) or tid
    # If this is a user template, prefix it similarly to the save dialog.
    try:
        from .templates import list_user_templates
        for rec in list_user_templates():
            if str((rec or {}).get("template_id") or "").strip() == tid:
                # Use the same key used by the save dialog.
                try:
                    from ..ui.i18n import tr
                    prefix = tr(lang, "intel.save.user_prefix", "(User)")
                except Exception:
                    prefix = "(User)"
                return f"{prefix} {str((rec or {}).get('name') or tid).strip()}  [{tid}]"
    except Exception:
        pass
    return f"{base}  [{tid}]"
