from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RibbonItemKind = Literal["action", "toggle", "widget"]


@dataclass(frozen=True)
class RibbonItemSpec:
    key: str
    kind: RibbonItemKind
    text_override: str | None = None


@dataclass(frozen=True)
class RibbonPanelSpec:
    title: str
    items: tuple[RibbonItemSpec, ...]


@dataclass(frozen=True)
class RibbonCategorySpec:
    title: str
    key: str
    panels: tuple[RibbonPanelSpec, ...]


@dataclass(frozen=True)
class RibbonSpec:
    categories: tuple[RibbonCategorySpec, ...] = field(default_factory=tuple)


def build_planar_ribbon_spec() -> RibbonSpec:
    return RibbonSpec(
        categories=(
            RibbonCategorySpec(
                title="Home",
                key="home",
                panels=(
                    RibbonPanelSpec("File", (
                        RibbonItemSpec("act_file_new", "action", "New"),
                        RibbonItemSpec("act_file_open", "action", "Open"),
                        RibbonItemSpec("act_file_save", "action", "Save"),
                        RibbonItemSpec("act_file_save_as", "action", "Save As"),
                    )),
                    RibbonPanelSpec("Edit", (
                        RibbonItemSpec("act_undo", "action", "Undo"),
                        RibbonItemSpec("act_redo", "action", "Redo"),
                        RibbonItemSpec("act_delete_selected", "action", "Delete"),
                        RibbonItemSpec("act_repeat_model", "action", "Repeat"),
                        RibbonItemSpec("act_cancel_model", "action", "Cancel"),
                    )),
                    RibbonPanelSpec("Settings", (
                        RibbonItemSpec("act_settings", "action", "Settings"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="Model",
                key="model",
                panels=(
                    RibbonPanelSpec("Create", (
                        RibbonItemSpec("act_create_point", "toggle", "Point"),
                        RibbonItemSpec("act_create_line", "toggle", "Line"),
                        RibbonItemSpec("act_create_spline", "toggle", "Spline"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="Boundary",
                key="boundary",
                panels=(
                    RibbonPanelSpec("Mode", (
                        RibbonItemSpec("act_boundary_constraints", "action", "Constraints"),
                        RibbonItemSpec("act_boundary_loads", "action", "Loads"),
                    )),
                    RibbonPanelSpec("Loads", (
                        RibbonItemSpec("act_boundary_add_force", "action", "Add Force"),
                        RibbonItemSpec("act_boundary_add_torque", "action", "Add Torque"),
                        RibbonItemSpec("act_boundary_clear_loads", "action", "Clear Loads"),
                    )),
                    RibbonPanelSpec("Fix", (
                        RibbonItemSpec("act_boundary_fix", "action", "Fix"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="Analysis",
                key="analysis",
                panels=(
                    RibbonPanelSpec("Run", (
                        RibbonItemSpec("act_analysis_play", "action", "Play"),
                        RibbonItemSpec("act_analysis_stop", "action", "Stop"),
                        RibbonItemSpec("act_analysis_reset_pose", "action", "ResetPose"),
                    )),
                    RibbonPanelSpec("Check", (
                        RibbonItemSpec("act_analysis_check", "action", "Check"),
                    )),
                    RibbonPanelSpec("Export", (
                        RibbonItemSpec("act_analysis_export", "action", "Export"),
                        RibbonItemSpec("act_analysis_save_run", "action", "Save Run"),
                    )),
                    RibbonPanelSpec("Solver", (
                        RibbonItemSpec("analysis_solver_widget", "widget", "Solver Combo"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="View",
                key="view",
                panels=(
                    RibbonPanelSpec("Display", (
                        RibbonItemSpec("act_pm", "toggle", "PM"),
                        RibbonItemSpec("act_dm", "toggle", "DM"),
                        RibbonItemSpec("act_body_color", "toggle", "Body Color"),
                        RibbonItemSpec("act_splines", "toggle", "Splines"),
                        RibbonItemSpec("act_load_arrows", "toggle", "Load Arrows"),
                    )),
                    RibbonPanelSpec("Presets", (
                        RibbonItemSpec("act_preset_show_all", "action", "Show All"),
                        RibbonItemSpec("act_preset_points_only", "action", "Points Only"),
                        RibbonItemSpec("act_preset_links_only", "action", "Links Only"),
                    )),
                    RibbonPanelSpec("Navigate", (
                        RibbonItemSpec("act_reset_view", "action", "Reset View"),
                        RibbonItemSpec("act_fit_all", "action", "Fit All"),
                    )),
                    RibbonPanelSpec("Grid", (
                        RibbonItemSpec("act_grid_horizontal", "toggle", "Grid H"),
                        RibbonItemSpec("act_grid_vertical", "toggle", "Grid V"),
                        RibbonItemSpec("act_grid_settings", "action", "Grid Settings"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="Background",
                key="background",
                panels=(
                    RibbonPanelSpec("Image", (
                        RibbonItemSpec("act_bg_load", "action", "Load"),
                        RibbonItemSpec("act_bg_visible", "toggle", "Visible"),
                        RibbonItemSpec("act_bg_gray", "toggle", "Gray"),
                        RibbonItemSpec("act_bg_opacity", "action", "Opacity"),
                        RibbonItemSpec("act_bg_clear", "action", "Clear"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title="Help",
                key="help",
                panels=(
                    RibbonPanelSpec("Support", (
                        RibbonItemSpec("act_help_manual", "action", "Manual"),
                        RibbonItemSpec("act_help_about", "action", "About"),
                    )),
                ),
            ),
        )
    )
