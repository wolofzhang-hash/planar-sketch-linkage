# Cleanup Sprint v2.12.06

## Scope
- Language handling and table context menu framework cleanup (zh/en only)
- Remove historical patch leftovers for row buttons in sketch/analysis/sim tables
- Reduce translation call-site sprawl using module helpers

## This sprint
- Added `set_ui_language()` in `ui/i18n.py` as the explicit UI language setter
- Kept language normalization to `zh` / `en` only via `norm_lang()`
- Tightened `table_context_menu.py` exports to framework entry points (`build/exec/install*`)
- Consolidated `tabs.py`, `analysis_tabs.py`, `sim_panel.py` language access through `_lang(...)` / `_tr(...)`
- Added `_is_zh(...)` / `_is_en(...)` helpers to reduce scattered direct string comparisons
- Removed row add/delete buttons for sketch/sim/optimization tables and left right-click as the single entry for row actions

## Notes
- This package is intended as a cleanup milestone and should be validated by launching the app and checking right-click menus under both zh/en UI settings.
