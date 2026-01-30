from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterable

# A small, explicit registry for constraints.
# Stage-1 goal: unify existing Length/Angle/Coincide constraints under one manager,
# without changing project behavior.

@dataclass
class ConstraintRow:
    key: str
    typ: str
    entities: str
    enabled: bool
    state: str


class ConstraintRegistry:
    """Unified view + IO for constraints (Length/Angle/Coincide/PointOnLine/PointOnSpline).

    This is intentionally thin in Stage-1: it wraps the controller's existing
    dict storage (links / angles / coincides) and provides a single API surface
    for UI + serialization. Later stages can migrate to class-based constraints
    while keeping this API stable.
    """
    def __init__(self, ctrl: Any):
        self.ctrl = ctrl

    # ---------- unified listing ----------
    def iter_rows(self) -> Iterable[ConstraintRow]:
        # Length constraints (Links)
        for lid, l in sorted(self.ctrl.links.items(), key=lambda kv: kv[0]):
            key = f"L{lid}"
            typ = "Length"
            ent = f"P{l['i']}-P{l['j']}"
            enabled = not bool(l.get("ref", False))
            state = "(measured)" if not enabled else ("OVER" if l.get("over", False) else "OK")
            yield ConstraintRow(key, typ, ent, enabled, state)

        # Angle constraints
        for aid, a in sorted(self.ctrl.angles.items(), key=lambda kv: kv[0]):
            key = f"A{aid}"
            typ = "Angle"
            ent = f"P{a['i']}-P{a['j']}-P{a['k']}"
            enabled = bool(a.get("enabled", True))
            state = "OVER" if a.get("over", False) else "OK"
            yield ConstraintRow(key, typ, ent, enabled, state)

        # Coincide constraints
        for cid, c in sorted(self.ctrl.coincides.items(), key=lambda kv: kv[0]):
            key = f"C{cid}"
            typ = "Coincide"
            ent = f"P{c['a']}==P{c['b']}"
            enabled = bool(c.get("enabled", True))
            state = "OVER" if c.get("over", False) else "OK"
            yield ConstraintRow(key, typ, ent, enabled, state)

        # Point-on-line constraints
        for plid, pl in sorted(getattr(self.ctrl, "point_lines", {}).items(), key=lambda kv: kv[0]):
            key = f"P{plid}"
            typ = "PointOnLine"
            ent = f"P{pl['p']} on (P{pl['i']}-P{pl['j']})"
            enabled = bool(pl.get("enabled", True))
            state = "OVER" if pl.get("over", False) else "OK"
            yield ConstraintRow(key, typ, ent, enabled, state)

        # Point-on-spline constraints
        for psid, ps in sorted(getattr(self.ctrl, "point_splines", {}).items(), key=lambda kv: kv[0]):
            key = f"S{psid}"
            typ = "PointOnSpline"
            ent = f"P{ps['p']} on S{ps['s']}"
            enabled = bool(ps.get("enabled", True))
            state = "OVER" if ps.get("over", False) else "OK"
            yield ConstraintRow(key, typ, ent, enabled, state)


    # ---------- unified actions ----------
    @staticmethod
    def parse_key(key: str) -> Tuple[Optional[str], Optional[int]]:
        if not key:
            return None, None
        k = key.strip()
        if len(k) < 2:
            return None, None
        kind = k[0].upper()
        try:
            cid = int(k[1:])
        except Exception:
            return None, None
        return kind, cid

    def delete_by_key(self, key: str) -> None:
        kind, cid = self.parse_key(key)
        if kind == "L" and cid in self.ctrl.links:
            self.ctrl.cmd_delete_link(cid)
        elif kind == "A" and cid in self.ctrl.angles:
            self.ctrl.cmd_delete_angle(cid)
        elif kind == "C" and cid in self.ctrl.coincides:
            self.ctrl.cmd_delete_coincide(cid)
        elif kind == "P" and cid in getattr(self.ctrl, "point_lines", {}):
            self.ctrl.cmd_delete_point_line(cid)
        elif kind == "S" and cid in getattr(self.ctrl, "point_splines", {}):
            self.ctrl.cmd_delete_point_spline(cid)

    def toggle_by_key(self, key: str) -> None:
        kind, cid = self.parse_key(key)
        if kind == "L" and cid in self.ctrl.links:
            self.ctrl.cmd_set_link_reference(cid, not self.ctrl.links[cid].get("ref", False))
        elif kind == "A" and cid in self.ctrl.angles:
            self.ctrl.cmd_set_angle_enabled(cid, not self.ctrl.angles[cid].get("enabled", True))
        elif kind == "C" and cid in self.ctrl.coincides:
            self.ctrl.cmd_set_coincide_enabled(cid, not self.ctrl.coincides[cid].get("enabled", True))
        elif kind == "P" and cid in getattr(self.ctrl, "point_lines", {}):
            self.ctrl.cmd_set_point_line_enabled(cid, not self.ctrl.point_lines[cid].get("enabled", True))
        elif kind == "S" and cid in getattr(self.ctrl, "point_splines", {}):
            self.ctrl.cmd_set_point_spline_enabled(cid, not self.ctrl.point_splines[cid].get("enabled", True))

    # ---------- serialization ----------
    def to_list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for lid, l in sorted(self.ctrl.links.items(), key=lambda kv: kv[0]):
            out.append({
                "type": "length",
                "id": int(lid),
                "i": int(l["i"]),
                "j": int(l["j"]),
                "value": float(l["L"]),
                "hidden": bool(l.get("hidden", False)),
                "enabled": (not bool(l.get("ref", False))),
            })
        for aid, a in sorted(self.ctrl.angles.items(), key=lambda kv: kv[0]):
            out.append({
                "type": "angle",
                "id": int(aid),
                "i": int(a["i"]),
                "j": int(a["j"]),
                "k": int(a["k"]),
                "value": float(a.get("deg", 0.0)),
                "hidden": bool(a.get("hidden", False)),
                "enabled": bool(a.get("enabled", True)),
            })
        for cid, c in sorted(self.ctrl.coincides.items(), key=lambda kv: kv[0]):
            out.append({
                "type": "coincide",
                "id": int(cid),
                "a": int(c["a"]),
                "b": int(c["b"]),
                "hidden": bool(c.get("hidden", False)),
                "enabled": bool(c.get("enabled", True)),
            })
        for plid, pl in sorted(getattr(self.ctrl, "point_lines", {}).items(), key=lambda kv: kv[0]):
            out.append({
                "type": "point_line",
                "id": int(plid),
                "p": int(pl.get("p", -1)),
                "i": int(pl.get("i", -1)),
                "j": int(pl.get("j", -1)),
                "hidden": bool(pl.get("hidden", False)),
                "enabled": bool(pl.get("enabled", True)),
            })
        for psid, ps in sorted(getattr(self.ctrl, "point_splines", {}).items(), key=lambda kv: kv[0]):
            out.append({
                "type": "point_spline",
                "id": int(psid),
                "p": int(ps.get("p", -1)),
                "s": int(ps.get("s", -1)),
                "hidden": bool(ps.get("hidden", False)),
                "enabled": bool(ps.get("enabled", True)),
            })
        return out

    @staticmethod
    def split_constraints(constraints: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        links: List[Dict[str, Any]] = []
        angles: List[Dict[str, Any]] = []
        splines: List[Dict[str, Any]] = []
        coincides: List[Dict[str, Any]] = []
        point_lines: List[Dict[str, Any]] = []
        point_splines: List[Dict[str, Any]] = []
        for c in constraints or []:
            t = str(c.get("type", "")).lower()
            if t == "length":
                links.append({
                    "id": int(c.get("id", -1)),
                    "i": int(c.get("i", -1)),
                    "j": int(c.get("j", -1)),
                    "L": float(c.get("value", 1.0)),
                    "hidden": bool(c.get("hidden", False)),
                    "ref": (not bool(c.get("enabled", True))),
                })
            elif t == "angle":
                angles.append({
                    "id": int(c.get("id", -1)),
                    "i": int(c.get("i", -1)),
                    "j": int(c.get("j", -1)),
                    "k": int(c.get("k", -1)),
                    "deg": float(c.get("value", 0.0)),
                    "hidden": bool(c.get("hidden", False)),
                    "enabled": bool(c.get("enabled", True)),
                })
            elif t == "coincide":
                coincides.append({
                    "id": int(c.get("id", -1)),
                    "a": int(c.get("a", -1)),
                    "b": int(c.get("b", -1)),
                    "hidden": bool(c.get("hidden", False)),
                    "enabled": bool(c.get("enabled", True)),
                })
            elif t in ("point_line", "pointonline", "point_line_constraint"):
                point_lines.append({
                    "id": int(c.get("id", -1)),
                    "p": int(c.get("p", -1)),
                    "i": int(c.get("i", -1)),
                    "j": int(c.get("j", -1)),
                    "hidden": bool(c.get("hidden", False)),
                    "enabled": bool(c.get("enabled", True)),
                })
            elif t in ("point_spline", "pointonspline", "point_spline_constraint"):
                point_splines.append({
                    "id": int(c.get("id", -1)),
                    "p": int(c.get("p", -1)),
                    "s": int(c.get("s", -1)),
                    "hidden": bool(c.get("hidden", False)),
                    "enabled": bool(c.get("enabled", True)),
                })
        return links, angles, splines, coincides, point_lines, point_splines
