from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
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


def build_planar_ribbon_spec(translate: Callable[[str, str], str] | None = None) -> RibbonSpec:
    def t(key: str, default: str) -> str:
        if translate is None:
            return default
        return translate(key, default)

    return RibbonSpec(
        categories=(
            RibbonCategorySpec(
                title=t("ribbon.category.home", "Home"),
                key="home",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.file", "File"), (
                        RibbonItemSpec("act_file_new", "action"),
                        RibbonItemSpec("act_file_open", "action"),
                        RibbonItemSpec("act_file_save", "action"),
                        RibbonItemSpec("act_file_save_as", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.edit", "Edit"), (
                        RibbonItemSpec("act_undo", "action"),
                        RibbonItemSpec("act_redo", "action"),
                        RibbonItemSpec("act_delete_selected", "action"),
                        RibbonItemSpec("act_repeat_model", "action"),
                        RibbonItemSpec("act_cancel_model", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.settings", "Settings"), (
                        RibbonItemSpec("act_settings", "action"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.sketch", "Model"),
                key="model",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.create", "Create"), (
                        RibbonItemSpec("act_create_point", "toggle"),
                        RibbonItemSpec("act_create_line", "toggle"),
                        RibbonItemSpec("act_create_spline", "toggle"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.boundary", "Boundary"),
                key="boundary",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.mode", "Mode"), (
                        RibbonItemSpec("act_boundary_constraints", "action"),
                        RibbonItemSpec("act_boundary_loads", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.loads", "Loads"), (
                        RibbonItemSpec("act_boundary_add_force", "action"),
                        RibbonItemSpec("act_boundary_add_torque", "action"),
                        RibbonItemSpec("act_boundary_clear_loads", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.fix", "Fix"), (
                        RibbonItemSpec("act_boundary_fix", "action"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.analysis", "Analysis"),
                key="analysis",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.run", "Run"), (
                        RibbonItemSpec("act_analysis_play", "action"),
                        RibbonItemSpec("act_analysis_stop", "action"),
                        RibbonItemSpec("act_analysis_reset_pose", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.check", "Check"), (
                        RibbonItemSpec("act_analysis_check", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.export", "Export"), (
                        RibbonItemSpec("act_analysis_export", "action"),
                        RibbonItemSpec("act_analysis_save_run", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.solver", "Solver"), (
                        RibbonItemSpec("analysis_solver_widget", "widget"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.view", "View"),
                key="view",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.display", "Display"), (
                        RibbonItemSpec("act_pm", "toggle"),
                        RibbonItemSpec("act_dm", "toggle"),
                        RibbonItemSpec("act_body_color", "toggle"),
                        RibbonItemSpec("act_splines", "toggle"),
                        RibbonItemSpec("act_load_arrows", "toggle"),
                    )),
                    RibbonPanelSpec(t("menu.presets", "Presets"), (
                        RibbonItemSpec("act_preset_show_all", "action"),
                        RibbonItemSpec("act_preset_points_only", "action"),
                        RibbonItemSpec("act_preset_links_only", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.navigate", "Navigate"), (
                        RibbonItemSpec("act_reset_view", "action"),
                        RibbonItemSpec("act_fit_all", "action"),
                    )),
                    RibbonPanelSpec(t("ribbon.panel.grid", "Grid"), (
                        RibbonItemSpec("act_grid_horizontal", "toggle"),
                        RibbonItemSpec("act_grid_vertical", "toggle"),
                        RibbonItemSpec("act_grid_settings", "action"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.background_image", "Background"),
                key="background",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.image", "Image"), (
                        RibbonItemSpec("act_bg_load", "action"),
                        RibbonItemSpec("act_bg_visible", "toggle"),
                        RibbonItemSpec("act_bg_gray", "toggle"),
                        RibbonItemSpec("act_bg_opacity", "action"),
                        RibbonItemSpec("act_bg_clear", "action"),
                    )),
                ),
            ),
            RibbonCategorySpec(
                title=t("menu.help", "Help"),
                key="help",
                panels=(
                    RibbonPanelSpec(t("ribbon.panel.support", "Support"), (
                        RibbonItemSpec("act_help_manual", "action"),
                        RibbonItemSpec("act_help_about", "action"),
                    )),
                ),
            ),
        )
    )
