"""Tests for automatic colored result-table persistence."""

from __future__ import annotations

import json

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from civiltools.commands.base import CommandResult
from civiltools.gui.main_window import MainWindow
from civiltools.gui.result_persistence import (
    persist_result_table,
    serialize_table_model,
)
from civiltools.gui.table_models import PandasModel
from civiltools.report.report_config import model_fingerprint


class ColoredModel(PandasModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.BackgroundRole and index.row() == 0 and index.column() == 1:
            return QColor("#ff557f")
        return super().data(index, role)


def test_serialize_table_model_preserves_values_and_colors():
    model = ColoredModel(pd.DataFrame({"Story": ["Level 1"], "Ratio": [0]}))

    data = serialize_table_model(model)

    assert data[0] == {"row": 0, "col": 0, "text": "Story", "color": ""}
    assert data[3] == {"row": 1, "col": 1, "text": "0", "color": "#ff557f"}


def test_persist_result_table_writes_json_and_manifest(tmp_path):
    model = PandasModel(pd.DataFrame({"Story": ["Level 1"]}))
    model_path = tmp_path / "Tower.edb"

    output_path = persist_result_table(model, model_path, "torsion", "Torsion Check")

    assert output_path == tmp_path / "Tower_table_results" / "torsion.json"
    assert json.loads(output_path.read_text(encoding="utf-8"))[1]["text"] == "Level 1"
    manifest = json.loads(
        (output_path.parent / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["torsion.json"]["display_name"]["en"] == "Torsion Check"
    assert manifest["torsion.json"]["schema_version"] == 1
    assert manifest["torsion.json"]["section_key"] == "torsion"
    assert manifest["torsion.json"]["model_fingerprint"] == model_fingerprint(model_path)


def test_main_window_persists_only_connected_etabs_results(monkeypatch):
    calls = []

    class Connection:
        is_connected = True
        model_path = "Tower.edb"

    class Command:
        command_id = "torsion"
        label = "Torsion Check"
        requires_etabs = True

    class Widget:
        _model = object()

    window = MainWindow.__new__(MainWindow)
    window._conn = Connection()
    monkeypatch.setattr(
        "civiltools.gui.main_window.persist_result_table",
        lambda *args: calls.append(args),
    )

    MainWindow._persist_result_table(
        window, Widget(), CommandResult(title="Torsion Check"), Command
    )

    assert calls == [(Widget._model, "Tower.edb", "torsion", "Torsion Check", {})]

    Connection.is_connected = False
    MainWindow._persist_result_table(
        window, Widget(), CommandResult(title="Torsion Check"), Command
    )
    assert len(calls) == 1
