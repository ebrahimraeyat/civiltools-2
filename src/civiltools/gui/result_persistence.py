"""Persistence helpers for displayed command-result tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from civiltools.report.report_config import ResultManifest, model_fingerprint


def serialize_table_model(model: Any) -> list[dict[str, Any]]:
    """Serialize a Qt table model using the legacy colored grid format."""
    data: list[dict[str, Any]] = []
    column_count = model.columnCount()
    for column in range(column_count):
        header = model.headerData(
            column,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.DisplayRole,
        )
        data.append({"row": 0, "col": column, "text": _display_text(header), "color": ""})

    for row in range(model.rowCount()):
        for column in range(column_count):
            index = model.index(row, column)
            value = model.data(index, Qt.ItemDataRole.DisplayRole)
            background = model.data(index, Qt.ItemDataRole.BackgroundRole)
            color = background.name() if isinstance(background, QColor) else ""
            data.append({
                "row": row + 1,
                "col": column,
                "text": _display_text(value),
                "color": color,
            })
    return data


def save_table_model(model: Any, filepath: str | Path) -> Path:
    """Write a table model to JSON and return the resulting path."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(serialize_table_model(model), indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def persist_result_table(
    model: Any,
    model_path: str | Path,
    command_id: str,
    display_name: str,
    params: dict[str, Any] | None = None,
) -> Path:
    """Save an ETABS command result and update its report manifest."""
    source = Path(model_path)
    results_dir = source.parent / f"{source.stem}_table_results"
    filename = f"{command_id}.json"
    output_path = save_table_model(model, results_dir / filename)

    manifest = ResultManifest(results_dir)
    manifest.register_table(
        filename,
        {"en": display_name, "fa": display_name},
        category="checks",
        section_key=command_id,
        source_model_fingerprint=model_fingerprint(source),
    )
    if params:
        save_refresh_params(results_dir, command_id, params)
    return output_path


def save_refresh_params(
    results_dir: str | Path,
    command_id: str,
    params: dict[str, Any],
) -> Path:
    """Save JSON-safe command inputs for later report refreshes."""
    directory = Path(results_dir)
    path = directory / "refresh_params.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            pass
    existing[command_id] = _json_safe(params)
    path.write_text(
        json.dumps(existing, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_refresh_params(model_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load saved command inputs for the model associated with *model_path*."""
    source = Path(model_path)
    path = source.parent / f"{source.stem}_table_results" / "refresh_params.json"
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _display_text(value: Any) -> str:
    return "" if value is None else str(value)
