# -*- coding: utf-8 -*-
"""Shared imports for SketchController modules."""

from __future__ import annotations

import json
import math
from typing import Dict, Any, Optional, List, Tuple, Callable

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QPainterPath, QColor, QImage, QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QMenu, QInputDialog, QGraphicsPixmapItem, QMessageBox

import numpy as np

from .commands import Command, CommandStack
from .geometry import clamp_angle_rad, angle_between, build_spline_samples, closest_point_on_samples
from .solver import ConstraintSolver
from .constraints_registry import ConstraintRegistry
from .parameters import ParameterRegistry
from .scipy_kinematics import SciPyKinematicSolver
from .exudyn_kinematics import ExudynKinematicSolver
from ..ui.items import (
    TextMarker,
    PointItem,
    LinkItem,
    AngleItem,
    CoincideItem,
    PointLineItem,
    SplineItem,
    PointSplineItem,
    TrajectoryItem,
    ForceArrowItem,
    TorqueArrowItem,
)
from ..ui.i18n import tr
from ..utils.constants import BODY_COLORS
