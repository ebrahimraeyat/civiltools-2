# civilTools — Agent Guide

Standalone structural engineering desktop app (seismic analysis, design checks, report generation, 3D visualization). Python 3.12 + PySide6 GUI, driving ETABS via COM automation.

See [README.md](README.md) for install/build details. Don't duplicate that here.

## Environment & commands

- **Package manager is pixi** (conda-based). `pythonocc-core` is conda-only — **never `pip install` it**.
- Run app: `pixi run start` (or `python -m civiltools`).
- Tests: `pixi run test` (or `pytest`). Config in [pytest.ini](pytest.ini); `qt_api = pyside6`, tests live in [tests/](tests).
- Lint/format: `ruff` — `line-length = 100`, target `py312`, rules `E,F,W,I,N,UP` (see [pyproject.toml](pyproject.toml)).
- Builds: `pixi run build-pyinstaller` (dev) or `pixi run build-nuitka` (source-protected release).
- `etabs-api` is an **external dependency** (git/local at `G:\etabs_api\src`), not part of this repo. ETABS commands need a *running* ETABS instance to execute.

## Architecture

`src/civiltools/` packages, by responsibility:

- `core/` — pure computation, **no GUI imports** (building model, seismic per Standard 2800, sections).
- `commands/` — structural check/action commands (the heart of the app). See pattern below.
- `gui/` — PySide6 dialogs, panels, `main_window.py`, table models, OCC widgets.
- `etabs/` — COM connection wrapper. `EtabsConnection` ([src/civiltools/etabs/connection.py](src/civiltools/etabs/connection.py)) wraps `etabs_obj.EtabsModel` from the external `etabs_api`.
- `viewer/` — PythonOCC (OpenCASCADE) 3D visualization.
- `report/` — PDF (fpdf2) + DOCX (python-docx) + matplotlib plan renderers.
- `building/`, `dxf/`, `wind/`, `db/` — domain helpers (live loads, DWG/DXF read, wind, CSV data).
- `licensing/` — trial + hardware-locked serial keys.

**Entry flow:** [`__main__.py`](src/civiltools/__main__.py) runs the license check *before* heavy imports, then [`app.py`](src/civiltools/app.py) builds `QApplication` + `MainWindow`. Keep GUI/ETABS imports lazy in startup paths.

## Adding a command (most common task)

Commands are auto-registered. To add one ([example](src/civiltools/commands/torsion.py)):

1. Subclass `BaseCommand` ([commands/base.py](src/civiltools/commands/base.py)) and decorate with `@register`.
2. Set class attrs: `command_id`, `label`, `menu_path` (e.g. `"Control"`), `tooltip`, optional `table_model`, `dialog_class`, and `requires_etabs = False` for standalone (e.g. AutoCAD-only) commands.
3. Implement `execute(cls, etabs, params) -> CommandResult` — catch exceptions and return `CommandResult(ok=False, error=...)` rather than raising.
4. Add the module to the import list in [commands/__init__.py](src/civiltools/commands/__init__.py) so it registers on load.
5. Optionally declare user inputs via `parameters()` returning `CommandParam` objects.

`CommandResult` carries `title`, `headers`, `rows`, optional `dataframe`, `summary`, `ok`, `error` — rendered as a table tab in the GUI.

## Conventions

- `from __future__ import annotations` at the top of modules; PEP 604 unions (`X | None`).
- Module docstrings describe purpose and original-source porting notes; keep that style.
- Keep `core/` free of Qt/COM imports so it stays unit-testable headless.
- Note: the directory tree in [README.md](README.md) is partly aspirational — trust the actual `src/civiltools/` layout above.
