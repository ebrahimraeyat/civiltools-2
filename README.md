# civilTools Standalone

Standalone structural engineering application for seismic analysis, design checks, report generation, and 3D visualization.

## Tech Stack

- **Python 3.12+**
- **PySide6** — Qt 6 GUI framework
- **pythonocc-core 7.9** — OpenCASCADE 3D kernel (conda-forge)
- **ETABS API** — comtypes COM automation
- **fpdf2 + python-docx** — report generation (PDF / DOCX)
- **markdown-it-py** — help system authoring

## Quick Install (Recommended)

You do **not** need Python or Anaconda installed — everything is handled automatically.

### Option A — One-click installer (easiest)

1. Download **`setup_civiltools.vbs`** from the [Releases](https://github.com/ebrahimraeyat/civiltools/releases) page
2. Double-click the file
3. A dialog appears — type a path or click **Browse...** to choose an install folder
4. Click **Install** → a terminal window opens and installs everything automatically (Git, Miniconda, Python, pythonocc-core, all dependencies)
5. The application launches when setup is complete

> This single file can be shared via email or USB — no other software needs to be installed beforehand.

### Option B — Clone + double-click

If you already have **Git** installed:

```powershell
git clone --depth=1 https://github.com/ebrahimraeyat/civiltools-2.git
```

Then open the `civiltools` folder and **double-click `install.bat`**. It will:
- Install **Git** (if missing)
- Install **Miniconda** (if missing)
- Create a conda environment named `civiltools` (Python 3.12 + `pythonocc-core`)
- Install all dependencies with `pip`
- Launch the application

### Running after installation

**Double-click `run.bat`** to start the application.

---

## Updating

**Double-click `update.bat`** to pull the latest code and launch.

Alternatively, in a terminal:

```powershell
git pull
conda activate civiltools
python -m civiltools
```

---

## Manual Setup (Advanced)

<details>
<summary>Click to expand step-by-step manual instructions</summary>

### Using conda

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

</details>

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
