from __future__ import annotations

from typing import Any, Dict, List


def serialize_user_curve_store(store: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(store, dict):
        return rows
    for key in sorted(store.keys(), key=lambda x: str(x)):
        curve = store.get(key)
        if not isinstance(curve, dict):
            continue
        row = dict(curve)
        row.setdefault("name", str(key))
        rows.append(row)
    return rows


def deserialize_user_curve_store(rows: Any) -> Dict[str, Dict[str, Any]]:
    store: Dict[str, Dict[str, Any]] = {}
    if not isinstance(rows, list):
        return store
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        store[name] = dict(row)
        store[name]["name"] = name
    return store
