"""Regression tests for launching the current workspace source."""

from __future__ import annotations

from pathlib import Path


def test_run_batch_prioritizes_workspace_source():
    repo_root = Path(__file__).resolve().parents[1]
    launcher = (repo_root / "run.bat").read_text(encoding="utf-8")

    path_setup = 'set "PYTHONPATH=%~dp0src;%PYTHONPATH%"'
    app_start = "call conda run -n civiltools python -m civiltools"

    assert path_setup in launcher
    assert launcher.index(path_setup) < launcher.index(app_start)
    assert "Loaded package:" in launcher
