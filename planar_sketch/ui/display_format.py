from __future__ import annotations

import math
from typing import Optional


def format_table_number(value: Optional[float], *, digits: int = 2, empty: str = "--") -> str:
    if value is None:
        return empty
    try:
        v = float(value)
    except Exception:
        return empty
    if not math.isfinite(v):
        return empty
    abs_v = abs(v)
    if abs_v >= 1000 or (abs_v > 0 and abs_v < 0.01):
        return f"{v:.{digits}g}"
    return f"{v:.{digits}f}"
