# Intelligent Design (Beta)

This project now includes an **Intelligent Design** entry to help users go from **requirements → mechanism concept recommendation → starter template insertion**.

## Where to find it
- Ribbon: **Model** tab → **Intelligent** panel → **Intelligent Design...**

## What it does (current Beta)
1. Collects a minimal requirement:
   - Task: Door/Hatch, Path generation, Function generation, Rigid body guidance
   - Mechanism family: Any / Cam / 4-bar / 6-bar / Slider-Rail
   - Opening angle (deg)
   - Preferences: fewer links, compact
2. Produces Top-3 **explainable** recommendations (rule-based scoring)
3. Inserts a **starter template** to the canvas (single undo step)

## Built-in templates (currently)
- `4bar_door`: a 4-bar starter layout suitable for door/hatch opening studies
- `slider_crank`: slider-crank starter layout with point-on-line (rail) constraint

Additional templates:
- `4bar_crank_rocker`, `4bar_double_rocker`, `4bar_toggle`
- `offset_slider_crank`, `dual_slider`
- `6bar_watt1`, `6bar_stephenson1`

> Note: 6-bar concepts are listed but templates are not yet built-in.

## Code structure
- `planar_sketch/intel/requirements.py` : requirement schema
- `planar_sketch/intel/recommender.py` : rule-based recommender + rationale
- `planar_sketch/intel/templates.py` : template insertion (single undo)
- `planar_sketch/intel/library/catalog.json` : concept library (expandable; now includes cam/4bar/6bar/slider-rail families)
- `planar_sketch/ui/intel_dialog.py` : the UI dialog

## Next recommended upgrades
- Add door-specific templates (Watt I / Stephenson / hidden hinge patterns)
- Add collision/keep-out envelope constraints
- Add dimensional synthesis (least_squares / evolutionary optimization)
- Add a knowledge base (cases + tags + retrieval)
