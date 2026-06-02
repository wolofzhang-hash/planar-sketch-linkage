# Patch Notes - Round 2

This round focuses on stability, replay validation, case-id safety, and test coverage.

## Changes

- Added strict internal case-id validation in `CaseRunManager`
  - case operations now require the stable internal id (for example `case_001`)
  - display names are no longer accidentally accepted by persistence APIs
  - `save_current_run()` now raises `KeyError` for unknown case ids instead of silently creating inconsistent run folders
  - `delete_case_runs()` now returns `False` when called with a non-existent case id

- Added replay/run validation in `ReplayService`
  - validates presence of `case.json`, `model.json`, and `results/frames.csv`
  - `load_frame_rows()` now fails with a clear error if the saved run is incomplete
  - Animation replay now shows validation errors before attempting to load frames

- Improved persistence error handling in `SimulationPanel`
  - `save_last_run()` now reports the real persistence exception instead of showing a misleading generic warning

- Extracted user-curve serialization helpers into a Qt-free module
  - new file: `planar_sketch/core/user_curve_store.py`
  - keeps project user-curve persistence logic testable without importing PyQt

## Tests added

- user curve store round-trip and invalid-row filtering
- case operations require internal case id, not display name
- replay validation reports missing saved files

## Validation

- `python -m py_compile ...` passed
- `PYTHONPATH=. pytest -q` passed
- total tests: **15 passed**
