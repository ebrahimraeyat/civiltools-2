"""Tests for selected report-check refreshes."""

from __future__ import annotations

import json

import pandas as pd

from civiltools.commands.base import CommandResult
from civiltools.commands.columns_100_30 import Columns10030Command
from civiltools.report import refresh
from civiltools.report.report_config import ReportConfig


def test_refresh_report_results_uses_saved_and_explicit_parameters(monkeypatch, tmp_path):
    calls = []

    class FakeCommand:
        label = "Fake Check"

        @classmethod
        def execute(cls, etabs, params):
            calls.append(params)
            return CommandResult(
                title=cls.label,
                dataframe=pd.DataFrame({"Story": ["Level 1"], "Result": [True]}),
            )

    class SapModel:
        @staticmethod
        def get_model_filename():
            return str(tmp_path / "Tower.edb")

    SapModel.GetModelFilename = staticmethod(SapModel.get_model_filename)

    class Etabs:
        pass

    Etabs.SapModel = SapModel()

    results_dir = tmp_path / "Tower_table_results"
    results_dir.mkdir()
    (results_dir / "refresh_params.json").write_text(
        json.dumps({"fake": {"mode": "saved"}}),
        encoding="utf-8",
    )
    monkeypatch.setitem(refresh._SECTION_COMMANDS, "fake", (FakeCommand, "fake"))

    config = ReportConfig(
        refresh_sections=["fake"],
        refresh_params={"fake": {"mode": "explicit"}},
    )
    refresh.refresh_report_results(Etabs(), config)

    assert calls == [{"mode": "explicit"}]
    output = results_dir / "fake.json"
    assert json.loads(output.read_text(encoding="utf-8"))[2]["text"] == "Level 1"
    manifest = json.loads((results_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fake.json"]["display_name"]["en"] == "Fake Check"


def test_columns_100_30_command_reports_required_columns(monkeypatch):
    frame = pd.DataFrame({"UniqueName": ["C1", "C2"], "Result": [True, False]})
    monkeypatch.setattr(
        "civiltools.commands.columns_100_30.run_columns_100_30",
        lambda etabs, params: frame,
    )

    result = Columns10030Command.execute(object(), {"structure_type": "Concrete"})

    assert result.ok is False
    assert result.headers == ["UniqueName", "Result"]
    assert result.summary == "1 columns require 100-30 combination"
