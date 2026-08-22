"""GUI regression tests for unified report section source controls."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QSpinBox

from civiltools.config import Settings
from civiltools.gui.dialogs.report_dialog import (
    ReportDialog,
    table_json_provenance_warning,
    validate_table_json,
)
from civiltools.report.report_config import (
    DEFAULT_SECTION_ORDER,
    ModelReportSources,
    model_fingerprint,
)


class _SapModel:
    def __init__(self, model_path: str):
        self._model_path = model_path

    def GetModelFilename(self) -> str:  # noqa: N802 - mirrors ETABS COM API
        return self._model_path


class _Etabs:
    def __init__(self, model_path: str):
        self.SapModel = _SapModel(model_path)


def _section_item(dialog: ReportDialog, key: str):
    for index in range(dialog._sections.topLevelItemCount()):
        item = dialog._sections.topLevelItem(index)
        if item.data(1, Qt.ItemDataRole.UserRole) == key:
            return item
    raise AssertionError(f"Missing report section: {key}")


def test_report_dialog_uses_one_unified_section_table(qtbot, tmp_path):
    model_path = tmp_path / "building.EDB"
    settings = Settings(path=tmp_path / "settings.json")
    report = settings.get("report")
    drift = next(section for section in report["sections"] if section["key"] == "drift")
    drift["read_from_etabs"] = True
    settings.update({"report": report})

    dialog = ReportDialog(_Etabs(str(model_path)), settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    groups = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert "Refresh Results from ETABS" not in groups
    assert "Report Sections and Sources" in groups
    assert dialog.findChildren(QSpinBox) == []
    assert dialog._sections.topLevelItemCount() == len(DEFAULT_SECTION_ORDER)
    assert [_section_item(dialog, key).text(1) for key in DEFAULT_SECTION_ORDER]

    drift_item = _section_item(dialog, "drift")
    assert drift_item.checkState(2) == Qt.CheckState.Checked
    dialog._set_include_checks(False)
    assert all(
        dialog._sections.topLevelItem(index).checkState(0) == Qt.CheckState.Unchecked
        for index in range(dialog._sections.topLevelItemCount())
    )
    assert drift_item.checkState(2) == Qt.CheckState.Checked
    dialog._set_include_checks(True)
    assert drift_item.checkState(2) == Qt.CheckState.Checked


def test_model_report_sources_are_isolated_per_model(tmp_path):
    first_model = tmp_path / "first.EDB"
    second_model = tmp_path / "second.EDB"
    source_file = tmp_path / "drift.json"

    first = ModelReportSources(section_json_paths={"drift": str(source_file)})
    first.save_for_model(first_model)

    assert ModelReportSources.load_for_model(first_model).section_json_paths == {
        "drift": str(source_file)
    }
    assert ModelReportSources.load_for_model(second_model).section_json_paths == {}


def test_validate_table_json_accepts_civiltools_grid_and_rejects_other_json(tmp_path):
    valid = tmp_path / "drift.json"
    valid.write_text(
        json.dumps(
            [
                {"row": 0, "col": 0, "text": "Story", "color": ""},
                {"row": 1, "col": 0, "text": "Roof", "color": "#ffffff"},
            ]
        ),
        encoding="utf-8",
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"rows": []}), encoding="utf-8")

    assert validate_table_json(valid, "drift") is None
    assert validate_table_json(valid, "model_settings") is not None
    assert validate_table_json(invalid, "drift") is not None


def test_table_json_provenance_warns_for_other_model_and_legacy(tmp_path):
    result = tmp_path / "drift.json"
    result.write_text(
        json.dumps([{"row": 0, "col": 0, "text": "Story", "color": ""}]),
        encoding="utf-8",
    )
    current_model = tmp_path / "current.EDB"
    other_model = tmp_path / "other.EDB"

    assert "legacy" in table_json_provenance_warning(
        result, "drift", current_model
    ).lower()

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "drift.json": {
                    "schema_version": 1,
                    "section_key": "drift",
                    "model_fingerprint": model_fingerprint(other_model),
                }
            }
        ),
        encoding="utf-8",
    )
    assert "different ETABS model" in table_json_provenance_warning(
        result, "drift", current_model
    )


def test_report_dialog_keeps_global_choices_and_persists_model_paths(qtbot, tmp_path):
    model_path = tmp_path / "building.EDB"
    settings = Settings(path=tmp_path / "settings.json")
    source_file = tmp_path / "drift.json"
    source_file.write_text(
        json.dumps([{"row": 0, "col": 0, "text": "Story", "color": ""}]),
        encoding="utf-8",
    )
    dialog = ReportDialog(_Etabs(str(model_path)), settings=settings)
    qtbot.addWidget(dialog)
    original_report = settings.get("report")

    drift_item = _section_item(dialog, "drift")
    drift_item.setCheckState(0, Qt.CheckState.Unchecked)
    drift_item.setCheckState(2, Qt.CheckState.Unchecked)
    dialog._toc_check.setChecked(not dialog._toc_check.isChecked())
    dialog._fallback_check.setChecked(not dialog._fallback_check.isChecked())
    assert dialog._set_section_json_path("drift", source_file) is True
    assert drift_item.text(3) == "Saved JSON: drift"
    dialog._persist_model_sources()

    restored = Settings(path=tmp_path / "settings.json")
    assert restored.get("report") == original_report
    assert "section_json_paths" not in restored.get("report")
    assert ModelReportSources.load_for_model(model_path).section_json_paths == {
        "drift": str(source_file)
    }
