from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .requirements import Requirement


@dataclass(frozen=True)
class Recommendation:
    concept_id: str
    concept_name: str
    score: float
    why: list[str]
    template: str | None = None


def _load_catalog() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "library" / "catalog.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Fallback: in case the file is missing in a user deployment.
        return {
            "concepts": [
                {
                    "id": "4bar",
                    "name": "Four-bar linkage",
                    "tags": ["general", "door", "function", "path"],
                    "template": "4bar_door",
                }
            ]
        }


def recommend(req: Requirement, top_k: int = 3) -> List[Recommendation]:
    """Rule-based, explainable recommendation.

    This intentionally starts simple. Later you can replace the scoring with:
    - case retrieval (knowledge base)
    - optimization-based synthesis
    - ML-based generation
    while keeping the same output structure.
    """

    cat = _load_catalog()
    concepts: List[Dict[str, Any]] = list(cat.get("concepts", []))

    # NOTE: Do not include user-saved templates in recommendations.
    # Users can access them via the Template Library.

    # Optional: family filter ("any" keeps all).
    fam = (getattr(req, "mechanism_family", "any") or "any").lower().strip()
    filtered = []
    if fam and fam != "any":
        for c in concepts:
            cfam = str(c.get("family", "") or "").lower().strip()
            if cfam == fam:
                filtered.append(c)
        # If the requested family is empty in catalog, fall back to all.
        if not filtered:
            filtered = concepts
    else:
        filtered = concepts

    recs: List[Recommendation] = []
    for c in filtered:
        tags = set(map(str.lower, c.get("tags", [])))
        score = 0.0
        why: List[str] = []

        cfam = str(c.get("family", "") or "").lower().strip()
        if fam and fam != "any":
            if cfam == fam:
                score += 3.0
                why.append(f"Matches mechanism family: {fam}.")

        task = (req.task or "").lower().strip()

        # Task match
        if task and task in tags:
            score += 5.0
            why.append(f"Matches task: {task}.")
        elif task == "door" and "hinge" in tags:
            score += 4.0
            why.append("Common in hinge/door packaging.")
        elif task == "path" and ("path" in tags or "guidance" in tags):
            score += 4.0
            why.append("Good for path / guidance.")

        # Preferences
        if req.prefer_fewer_links:
            if cfam in ("4bar", "slider_rail") and c.get("id") in ("4bar", "slider_crank", "4bar_crank_rocker", "4bar_double_rocker"):
                score += 2.0
                why.append("Fewer links (simpler, faster sizing).")
            else:
                score -= 1.0
        if req.prefer_compact and "compact" in tags:
            score += 1.5
            why.append("Compact packaging.")

        # Door opening angle hint
        if task == "door" and req.open_angle_deg is not None:
            ang = float(req.open_angle_deg)
            if 70 <= ang <= 130 and c.get("id") in ("4bar", "6bar_watt1"):
                score += 1.0
                why.append("Typical hatch opening angle range.")
            if ang > 130 and c.get("id") in ("6bar_watt1", "6bar_stephenson1"):
                score += 0.5
                why.append("Large opening may benefit from 6-bar flexibility.")

        # Default explanation
        if not why:
            why.append("General-purpose option.")

        recs.append(
            Recommendation(
                concept_id=str(c.get("id", "")),
                concept_name=str(c.get("name", c.get("id", ""))),
                score=float(score),
                why=why,
                template=c.get("template"),
            )
        )

    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[: max(1, int(top_k))]
