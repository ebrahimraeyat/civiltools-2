"""Tests for selected report-check refreshes."""

from __future__ import annotations

import json

import pandas as pd

from civiltools.commands.base import CommandResult
from civiltools.commands.columns_100_30 import Columns10030Command
from civiltools.report import refresh
from civiltools.report.data_extractor import ReportData, _extract_drift
from civiltools.report.report_config import ReportConfig
from civiltools.report.report_generator import _resolve_section_sources


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


class _SapModel:
    def __init__(self, model_path: str = "", connected: bool = True):
        self._model_path = model_path
        self._connected = connected

    def GetModelFilename(self) -> str:  # noqa: N802 - mirrors ETABS COM API
        if not self._connected:
            raise RuntimeError("ETABS disconnected")
        return self._model_path


class _Etabs:
    def __init__(self, model_path: str = "", connected: bool = True):
        self.SapModel = _SapModel(model_path, connected)


def test_source_policy_uses_explicit_json_without_refresh(tmp_path):
    source = tmp_path / "chosen.json"
    source.write_text("[]", encoding="utf-8")
    config = ReportConfig(
        section_order=["drift"],
        refresh_sections=["drift"],
        section_sources={"drift": "json"},
        section_json_paths={"drift": str(source)},
    )

    _resolve_section_sources(_Etabs(str(tmp_path / "model.EDB")), config)

    assert config.section_sources["drift"] == "json"
    assert config.refresh_sections == []
    assert config.disabled_sections == []


def test_source_policy_falls_back_to_etabs_when_json_is_missing(tmp_path):
    config = ReportConfig(
        section_order=["drift"],
        section_sources={"drift": "json"},
        section_json_paths={"drift": str(tmp_path / "missing.json")},
        fallback_to_etabs_if_missing=True,
    )

    _resolve_section_sources(_Etabs(str(tmp_path / "model.EDB")), config)

    assert config.section_sources["drift"] == "etabs"
    assert config.refresh_sections == ["drift"]


def test_source_policy_skips_missing_json_when_fallback_is_disabled(tmp_path):
    config = ReportConfig(
        section_order=["drift"],
        section_sources={"drift": "json"},
        fallback_to_etabs_if_missing=False,
    )

    _resolve_section_sources(_Etabs(str(tmp_path / "model.EDB")), config)

    assert config.section_sources["drift"] == "unavailable"
    assert config.disabled_sections == ["drift"]
    assert config.refresh_sections == []


def test_source_policy_uses_json_if_etabs_disconnects(tmp_path):
    source = tmp_path / "drift.json"
    source.write_text("[]", encoding="utf-8")
    config = ReportConfig(
        section_order=["drift"],
        refresh_sections=["drift"],
        section_sources={"drift": "etabs"},
        section_json_paths={"drift": str(source)},
    )

    _resolve_section_sources(_Etabs(connected=False), config)

    assert config.section_sources["drift"] == "json"
    assert config.refresh_sections == []
    assert config.disabled_sections == []


def test_explicit_drift_json_precedes_automatic_model_cache(tmp_path):
    results_dir = tmp_path / "model_table_results"
    results_dir.mkdir()
    cached = results_dir / "drift.json"
    explicit = tmp_path / "selected.json"

    def write_grid(path, value):
        path.write_text(
            json.dumps(
                [
                    {"row": 0, "col": 0, "text": "Story", "color": ""},
                    {"row": 1, "col": 0, "text": value, "color": ""},
                ]
            ),
            encoding="utf-8",
        )

    write_grid(cached, "Cached")
    write_grid(explicit, "Explicit")
    data = ReportData(model_dir=tmp_path, model_stem="model")

    class NoLiveEtabs:
        @staticmethod
        def get_drifts(*args, **kwargs):
            raise AssertionError("Live ETABS should not be read")

    _extract_drift(NoLiveEtabs(), None, data, explicit)

    assert data.drift_data.iloc[0, 0] == "Explicit"
