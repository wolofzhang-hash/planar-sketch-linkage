$ErrorActionPreference = "Stop"
python -m pip install -U pip
pip install -r requirements-windows.txt
python -m PyInstaller --noconfirm --clean --windowed --name PlanarSketch `
  --icon planar_sketch/assets/app_icon.svg `
  --add-data "planar_sketch/assets;planar_sketch/assets" `
  --add-data "planar_sketch/ui/locales;planar_sketch/ui/locales" `
  --add-data "planar_sketch/intel/library;planar_sketch/intel/library" `
  --add-data "docs;docs" `
  run.py
