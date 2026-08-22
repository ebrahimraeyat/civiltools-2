"""Persistence helpers for displayed command-result tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from civiltools.report.report_config import ResultManifest


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
    )
    return output_path


def _display_text(value: Any) -> str:
    return "" if value is None else str(value)
