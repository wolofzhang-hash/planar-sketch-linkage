# Planar Sketch Linkage

Interactive planar linkage sketcher with constraints, parameter expressions, simulation, optimization, and intelligent design helpers.

## Run from source

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-windows.txt
python run.py
```

macOS / Linux shell:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements-macos.txt
python run.py
```

`help.pdf` is optional. If it is not present, the Help command will show a missing-help message instead of opening a manual.

## Optional solver backend

The Exudyn solver is optional. Install it only when needed:

```bash
pip install -r requirements-optional.txt
```

## Package / build

Windows:

```powershell
.\packaging\build_windows.ps1
```

macOS:

```bash
./packaging/build_macos.sh
```

## Current UI / i18n status

- UI languages are **zh / en only**.
- UI text uses unified i18n helpers (`tr`, `_tr`, `_lang`).
- Table row actions are unified through **right-click context menus**.
- System locale is **not** used to override the software UI language setting.
- Create-mode toolbar/ribbon highlighting is driven by both one-shot modeling mode and continuous modeling mode.

## Features

- Sketch editing: Points / Lengths / Angles / Splines / Rigid Bodies / Constraints
- Constraint types: length, angle, coincide, point-on-line, rigid body grouping
- Parameter expressions on coordinates / lengths / angles and analysis fields
- Simulation panel: loads, friction, measurements, sweep, export, plots
- Optimization tab: variables / objectives / constraints with right-click row operations
- Intelligent design / synthesis related tools and preview windows

## Project structure

- `planar_sketch/` core application source
- `docs/` architecture, dev notes, changelog, cleanup notes
- `tests/` regression tests
- `packaging/` local PyInstaller build scripts
- `run.py` local entry point

## Docs

- `docs/ARCHITECTURE.md`
- `docs/DEV_GUIDE.md`
- `docs/SYNTHESIS.md`
- `docs/CHANGELOG.md`
- `docs/CLEANUP_SPRINT_v2.12.08.md`

## GitHub upload notes

Generated artifacts are intentionally excluded by `.gitignore`: CSV/SVG/GIF/ZIP/logs, caches, build output, local IDE files, and OS metadata such as `__MACOSX` / `._*`.
