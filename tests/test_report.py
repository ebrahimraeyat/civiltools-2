"""
Tests for the report module.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from docx import Document

from civiltools.report.data_extractor import ReportData
from civiltools.report.docx_report import _section_columns_100_30
from civiltools.report.latex_str import (
    earthquake_c_with_values,
    earthquake_formula,
    full_earthquake_calculation,
)
from civiltools.report.report_config import ReportConfig
from civiltools.report.report_generator import ReportGenerator
from civiltools.report.strings import S, get_all_strings, get_string


class TestStrings:
    def test_get_persian(self):
        assert get_string("DEAD", "fa") == "بار مرده"

    def test_get_english(self):
        assert get_string("DEAD", "en") == "Dead Load"

    def test_unknown_key(self):
        assert get_string("NONEXISTENT") == "NONEXISTENT"

    def test_accessor(self):
        assert S.EX["fa"] == "بار زلزله در جهت X"
        assert S.EX["en"] == "Earthquake Load in X Direction"

    def test_all_strings(self):
        all_fa = get_all_strings("fa")
        assert isinstance(all_fa, dict)
        assert len(all_fa) > 50


class TestReportConfig:
    def test_defaults(self):
        config = ReportConfig()
        assert config.language == "fa"
        assert config.output_format == "docx"
        assert config.is_rtl

    def test_active_sections(self):
        config = ReportConfig(disabled_sections=["drift"])
        assert "drift" not in config.active_sections
        assert "project_info" in config.active_sections

    def test_serialization(self):
        config = ReportConfig(language="en", output_format="pdf")
        d = config.to_dict()
        restored = ReportConfig.from_dict(d)
        assert restored.language == "en"
        assert restored.output_format == "pdf"

    def test_save_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        config = ReportConfig(language="both")
        config.save(path)
        loaded = ReportConfig.load(path)
        assert loaded.language == "both"
        path.unlink()


class TestReportGenerator:
    def test_generates_docx_only(self, monkeypatch, tmp_path):
        data = ReportData(project_name="Test Building")
        written_paths = []

        monkeypatch.setattr(
            "civiltools.report.report_generator.extract_report_data",
            lambda *args, **kwargs: data,
        )

        def write_docx(report_data, config, output_path):
            written_paths.append((report_data, config, output_path))
            Path(output_path).write_bytes(b"docx")

        monkeypatch.setattr(
            "civiltools.report.docx_report.create_docx_report",
            write_docx,
        )

        generator = ReportGenerator(
            etabs=object(),
            config=ReportConfig(output_format="docx"),
            output_dir=tmp_path,
        )
        docx_path, pdf_path = generator.generate()

        assert Path(docx_path) == tmp_path / "Test_Building_report.docx"
        assert pdf_path == ""
        assert written_paths == [(data, generator.config, Path(docx_path))]


def test_100_30_section_contains_clause_text_and_result():
    data = ReportData(
        columns_100_30_data=pd.DataFrame({"UniqueName": ["C1"], "Result": [False]})
    )
    doc = Document()

    _section_columns_100_30(doc, data, "en")

    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Clause 4-1-3" in text
    assert "100%-30%" in text
    assert "1 column(s) require" in text


class TestLatexStr:
    def test_generic_formula(self):
        assert "C" in earthquake_formula
        assert "\\frac" in earthquake_formula

    def test_c_with_values(self):
        result = earthquake_c_with_values(0.3, 2.5, 1.0, 7.0, 0.1071)
        assert "0.3" in result
        assert "7.0" in result

    def test_full_calculation(self):
        params = {
            "A": 0.3, "I": 1.0, "Rx": 7.0, "Ry": 7.0,
            "Tx": 0.5, "Tx_an": 0.6, "Tx_design": 0.5,
            "B1x": 2.5, "Nx": 1.0, "Bx": 2.5, "Kx": 1.0, "Cx": 0.1071,
            "alpha": 0.07, "beta": 0.75, "H": 10.0,
            "soil_type": "III", "T0": 0.15, "Ts": 0.70,
            "S": 1.75, "S0": 1.75, "risk_level": 3,
        }
        steps = full_earthquake_calculation(params, "x")
        assert len(steps) == 10
        assert all(isinstance(s, tuple) and len(s) == 2 for s in steps)
