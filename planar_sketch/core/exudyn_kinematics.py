# -*- coding: utf-8 -*-
"""Exudyn kinematic/quasi-static solver backend.

This module provides a thin integration layer for Exudyn. It currently
initializes an Exudyn system to ensure the runtime is available, then
uses the existing constraint solver as a fallback to keep the UI responsive.

The API is designed to be extended with full Exudyn-based constraint and
load handling (hinges, trajectories, springs, friction, etc.).
"""

from __future__ import annotations

from typing import Any, Tuple
import importlib
import importlib.util


def _load_exudyn():
    spec = importlib.util.find_spec("exudyn")
    if spec is None:
        raise RuntimeError(
            "Exudyn is required for the Exudyn solver. "
            "Please install exudyn (e.g. pip install exudyn)."
        )
    return importlib.import_module("exudyn")


class ExudynKinematicSolver:
    """Integration stub for Exudyn-based solvers."""

    @staticmethod
    def solve(ctrl: Any, max_iters: int = 80) -> Tuple[bool, str]:
        """Solve the current sketch using Exudyn integration.

        If Exudyn is available, this will initialize an Exudyn system and
        then fall back to the internal constraint solver as a temporary
        implementation until full Exudyn modeling is added.
        """
        exu = _load_exudyn()
        try:
            sc = exu.SystemContainer()
            sc.AddSystem()
        except Exception as exc:
            return False, f"Exudyn initialization failed: {exc}"

        # Temporary fallback: rely on existing constraint solver to keep the
        # application functional while Exudyn models are expanded.
        if hasattr(ctrl, "solve_constraints"):
            try:
                ctrl.solve_constraints(iters=max_iters)
            except Exception as exc:
                return False, f"Fallback solve failed: {exc}"
        return True, "Exudyn initialized; fallback solver applied"
