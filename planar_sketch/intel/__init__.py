"""Intelligent design helpers (rule-based recommender + templates).

This package is intentionally lightweight so it can evolve into:

1) Rule-based recommendation (explainable)
2) Case retrieval / knowledge-base driven recommendation
3) Dimensional synthesis / optimization

For now, it provides:

- Requirement: a small schema for user intent
- recommend(): returns ranked mechanism concepts + rationale
- insert_template(): creates a starter mechanism on the canvas
"""

from .requirements import Requirement
from .recommender import recommend
from .templates import insert_template, save_current_model_as_template, list_user_templates, delete_user_template, _user_template_preview_path

__all__ = ["Requirement", "recommend", "insert_template", "save_current_model_as_template", "list_user_templates", "delete_user_template", "_user_template_preview_path"]
