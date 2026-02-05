# -*- coding: utf-8 -*-
"""Model + controller logic entrypoint."""

from __future__ import annotations

from .controller_core import ControllerCore
from .controller_model import ControllerModel
from .controller_selection import ControllerSelection
from .controller_simulation import ControllerSimulation


class SketchController(ControllerCore, ControllerModel, ControllerSelection, ControllerSimulation):
    """Public SketchController entrypoint."""
    pass
