# -*- coding: utf-8 -*-
"""SketchController initialization."""

from __future__ import annotations

from .controller_common import (
    Dict,
    Any,
    Optional,
    List,
    Tuple,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QPointF,
    QImage,
    CommandStack,
    ConstraintRegistry,
    ParameterRegistry,
)


class ControllerCore:
    def __init__(self, scene: QGraphicsScene, win: "MainWindow"):
        self.scene = scene
        self.win = win
        # Global parameters used by expression fields (x_expr / L_expr / deg_expr / ...)
        self.parameters = ParameterRegistry()
        self.points: Dict[int, Dict[str, Any]] = {}
        self.links: Dict[int, Dict[str, Any]] = {}
        self.angles: Dict[int, Dict[str, Any]] = {}
        self.splines: Dict[int, Dict[str, Any]] = {}
        self.bodies: Dict[int, Dict[str, Any]] = {}
        self.coincides: Dict[int, Dict[str, Any]] = {}
        # Point-on-line constraints: {id: {p,i,j,hidden,enabled,over}}
        self.point_lines: Dict[int, Dict[str, Any]] = {}
        # Point-on-spline constraints: {id: {p,s,hidden,enabled,over}}
        self.point_splines: Dict[int, Dict[str, Any]] = {}

        # Parameters + expressions
        self.constraint_registry = ConstraintRegistry(self)
        self._next_pid = 0
        self._next_lid = 0
        self._next_aid = 0
        self._next_sid = 0
        self._next_bid = 0
        self._next_cid = 0
        self._next_plid = 0
        self._next_psid = 0
        self.selected_point_ids: set = set()
        self.selected_point_id: Optional[int] = None
        self.selected_link_id: Optional[int] = None
        self.selected_angle_id: Optional[int] = None
        self.selected_spline_id: Optional[int] = None
        self.selected_body_id: Optional[int] = None
        self.selected_coincide_id: Optional[int] = None
        self.selected_point_line_id: Optional[int] = None
        self.selected_point_spline_id: Optional[int] = None

        self.show_point_markers = True
        self.show_dim_markers = True

        self.show_points_geometry = True
        self.show_links_geometry = True
        self.show_angles_geometry = True
        self.show_splines_geometry = True
        self.show_body_coloring = True
        self.show_trajectories = False
        self.show_load_arrows = True
        self.display_precision = 1
        self.load_arrow_width = 1.6
        self.torque_arrow_width = 1.6
        self.ui_language = "en"
        self.project_uuid: str = ""

        self.background_image: Dict[str, Any] = {
            "path": None,
            "visible": True,
            "opacity": 0.6,
            "grayscale": False,
            "scale": 1.0,
            "pos": (0.0, 0.0),
        }
        self._background_item: Optional[QGraphicsPixmapItem] = None
        self._background_image_original: Optional[QImage] = None
        self._background_pick_points: List[QPointF] = []
        self.grid_settings: Dict[str, Any] = {
            "show_horizontal": True,
            "show_vertical": True,
            "spacing_x": 100.0,
            "spacing_y": 100.0,
            "range_x": 2000.0,
            "range_y": 2000.0,
            "center": (0.0, 0.0),
        }
        self._grid_item: Optional[GridItem] = None

        self.mode = "Idle"
        self._line_sel: List[int] = []
        self._co_master: Optional[int] = None
        self._pol_master: Optional[int] = None
        self._pol_line_sel: List[int] = []
        self._pos_master: Optional[int] = None
        self.panel: Optional["SketchPanel"] = None
        self.stack = CommandStack(on_change=self.win.update_undo_redo_actions)
        self._drag_active = False
        self._drag_pid: Optional[int] = None
        self._drag_before: Optional[Dict[int, Tuple[float, float]]] = None
        self._last_model_action: Optional[str] = None
        self._continuous_model_action: Optional[str] = None
        self._last_scene_pos: Optional[Tuple[float, float]] = None
        self._last_point_pos: Optional[Tuple[float, float]] = None
        self._graphics_update_in_progress = False
        self._graphics_update_pending = False
        self._graphics_update_scheduled = False
        self._graphics_update_last = 0.0
        self._graphics_update_min_interval = 1.0 / 60.0

        # --- Linkage-style simulation configuration ---
        # Driver: world-angle of a pivot->tip direction.
        # type: "angle"
        self.driver: Dict[str, Any] = self._default_driver()
        # Multiple drivers (primary driver is drivers[0] when present)
        self.drivers: List[Dict[str, Any]] = []
        # Output: measured angle of (pivot -> tip) relative to world +X.
        self.output: Dict[str, Any] = self._default_output()
        # Multiple outputs (primary output is outputs[0] when present)
        self.outputs: List[Dict[str, Any]] = []
        # Extra measurements: a list of {type,name,...} items.
        self.measures: List[Dict[str, Any]] = []
        # Load measurements: a list of {type,name,...} items.
        self.load_measures: List[Dict[str, Any]] = []
        # Joint friction definitions: list of {pid, mu, diameter}
        self.friction_joints: List[Dict[str, Any]] = []
        # Quasi-static loads: list of {type,pid,fx,fy,mz,ref_pid,k,theta0}
        self.loads: List[Dict[str, Any]] = []
        # Display items for load arrows.
        self._load_arrow_items: List[ForceArrowItem] = []
        self._torque_arrow_items: List[TorqueArrowItem] = []
        self._friction_torque_arrow_items: List[TorqueArrowItem] = []
        self._last_joint_loads: List[Dict[str, Any]] = []
        self._last_quasistatic_summary: Dict[str, Any] = {}
        # Pose snapshots for "reset to initial".
        self._pose_initial: Optional[Dict[int, Tuple[float, float]]] = None
        self._pose_last_sim_start: Optional[Dict[int, Tuple[float, float]]] = None

        # Simulation "relative zero" (0° == pose at Play-start)
        self._sim_zero_input_rad: Optional[float] = None
        self._sim_zero_output_rad: Optional[float] = None
        self._sim_zero_driver_rad: List[Optional[float]] = []
        self._sim_zero_meas_deg: Dict[str, float] = {}
        self._sim_zero_meas_len: Dict[str, float] = {}
        self.sweep_settings: Dict[str, float] = {"start": 0.0, "end": 360.0, "step": 200.0}
        self.simulation_settings: Dict[str, Any] = {
            "solver": "scipy",
            "max_nfev": 250,
            "reset_before_run": True,
        }
        self.optimization_settings: Dict[str, Any] = {
            "evals": 50,
            "seed": "",
            "debug_log": {"enabled": False, "path": ""},
            "variables": [],
            "objectives": [],
            "constraints": [],
        }
