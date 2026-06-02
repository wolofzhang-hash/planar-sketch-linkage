# Patch Notes - Round 3

This round fixes confirmed defects from the v2.12.73 patched round2 review while avoiding broad rewrites or compatibility shims.

## Changes

- Fixed `CaseRunManager.delete_case()` cleanup order.
  - removes `runs/<case_id>/` before the case is removed from the index
  - clears `runs/last_run.txt` when it points at the deleted case
  - preserves `hash_map` by remapping duplicate-hash cases to an existing remaining case

- Hardened `last_run_path()`.
  - stale or missing run directories now return `None` instead of a dead path

- Removed unconditional `[PS-DEBUG ...]` stdout output from production code.
  - affected `case_run_manager.py`, `sim_panel.py`, and `animation_tab.py`

- Removed headless simulation's accidental PyQt dependency path.
  - `sim_common_queries.py` now imports `angle_between` from `core.geometry`
  - verified `planar_sketch.core.headless_sim` imports without loading `PyQt6`

- Preserved spline definitions in headless snapshot loading when unified `constraints` are present.
  - avoids losing `data["splines"]` through the currently empty `split_constraints()` spline slot

- Fixed ribbon fallback icon lookup.
  - corrected asset directory resolution
  - falls back to existing `assets/app_icon.svg` if no dedicated `fallback_action.svg` exists

- Aligned case schema defaults with `CASE_SCHEMA_VERSION`.
  - `CaseSpec` now uses the centralized version constant for new/default specs
  - persisted case specs are written with the current case schema version

- Cleaned small UI/i18n inconsistencies.
  - `Rename Case` dialog title and label now use i18n
  - wording now refers to display label/name rather than internal case ID

- Cleaned packaging artifacts.
  - removed `__pycache__` and `.pyc` files from the delivery zip
  - added a root `.gitignore` to match the README packaging note

## Tests added

- deleting a case removes its current run and clears `last_run_path()`
- missing `last_run.txt` target returns `None`
- deleting the latest duplicate-hash case remaps to the remaining case
- default `CaseSpec` schema matches `CASE_SCHEMA_VERSION`

## Validation

- `python -m compileall -q planar_sketch tests` passed
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests` passed
- total tests: **19 passed**
