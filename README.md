# civilTools Standalone

Standalone structural engineering application for seismic analysis, design checks, report generation, and 3D visualization.

## Tech Stack

- **Python 3.12+**
- **PySide6** — Qt 6 GUI framework
- **pythonocc-core 7.9** — OpenCASCADE 3D kernel (install via conda)
- **ETABS API** — comtypes COM automation
- **fpdf2 + python-docx** — report generation (PDF / DOCX)
- **markdown-it-py** — help system authoring

## Setup (development)

```bash
# 1. Create conda environment with OCC
conda create -n civiltools python=3.12 pythonocc-core=7.9 -c conda-forge -y
conda activate civiltools

# 2. Install the package in editable mode
pip install -e ".[dev]"

# 3. Run
civiltools
# or
python -m civiltools
```

## Build

### Development build (PyInstaller)
```bash
python build/build_pyinstaller.py
```

### Release build (Nuitka — source-protected)
```bash
python build/build_nuitka.py
```

## Project Structure

```
G:\civiltools\
├── pyproject.toml
├── build/                  # Build & packaging scripts
├── resources/              # Icons, fonts, templates
├── src/civiltools/
│   ├── core/               # Pure computation (no GUI)
│   │   ├── model.py        # In-memory building model
│   │   ├── building/       # Seismic calculations (Standard 2800)
│   │   ├── etabs/          # ETABS COM API wrappers
│   │   └── sections/       # Section property analysis
│   ├── viewer/             # PythonOCC 3D visualization
│   ├── gui/                # PySide6 dialogs, panels, main window
│   ├── report/             # PDF + DOCX report generation
│   ├── licensing/          # Trial + serial key licensing
│   ├── help/               # Context-sensitive help system
│   └── io/                 # Import/export (DXF, IFC, ETABS)
└── tests/
```

## Licensing

- **30-day free trial** from first launch
- After trial: requires a hardware-locked serial key
- Serial keys bound to machine fingerprint (CPU + disk + hostname)
- Nuitka builds provide source code protection for release builds
