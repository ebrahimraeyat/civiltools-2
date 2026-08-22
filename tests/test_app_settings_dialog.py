"""GUI tests for application-wide settings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from civiltools.config import Settings
from civiltools.gui.dialogs.app_settings_dialog import AppSettingsDialog, RtlTextDelegate
from civiltools.gui.main_window import MainWindow


def _section_item(dialog: AppSettingsDialog, key: str):
    for index in range(dialog._sections.topLevelItemCount()):
        item = dialog._sections.topLevelItem(index)
        if item.data(1, Qt.ItemDataRole.UserRole) == key:
            return item
    raise AssertionError(f"Missing section row: {key}")


def test_settings_dialog_saves_general_and_report_preferences(qtbot, tmp_path):
    settings = Settings(path=tmp_path / "settings.json")
    dialog = AppSettingsDialog(settings)
    qtbot.addWidget(dialog)

    assert dialog._tabs.count() == 2
    assert isinstance(dialog._sections.itemDelegateForColumn(2), RtlTextDelegate)
    assert dialog._workers_spin.minimum() == 1
    assert dialog._workers_spin.maximum() == 16

    drift = _section_item(dialog, "drift")
    drift.setText(1, "Drift Results")
    drift.setText(2, "نتایج دریفت")
    drift.setCheckState(0, Qt.CheckState.Unchecked)
    drift.setCheckState(3, Qt.CheckState.Checked)
    dialog._appearance_combo.setCurrentIndex(dialog._appearance_combo.findData(True))
    dialog._language_combo.setCurrentIndex(dialog._language_combo.findData("en"))
    dialog._workers_spin.setValue(7)
    dialog._apply()

    restored = Settings(path=tmp_path / "settings.json")
    report = restored.get("report")
    saved_drift = next(section for section in report["sections"] if section["key"] == "drift")
    assert saved_drift["title_en"] == "Drift Results"
    assert saved_drift["title_fa"] == "نتایج دریفت"
    assert saved_drift["included"] is False
    assert saved_drift["read_from_etabs"] is True
    assert report["workers"] == 7
    assert restored.get("dark_theme") is True
    assert restored.get("language") == "en"


def test_settings_dialog_cancel_does_not_persist_edits(qtbot, tmp_path):
    settings = Settings(path=tmp_path / "settings.json")
    original_title = settings.get("report")["sections"][0]["title_en"]
    dialog = AppSettingsDialog(settings)
    qtbot.addWidget(dialog)

    dialog._sections.topLevelItem(0).setText(1, "Unsaved")
    dialog.reject()

    restored = Settings(path=tmp_path / "settings.json")
    assert restored.get("report")["sections"][0]["title_en"] == original_title


def test_help_menu_contains_application_settings(qtbot, tmp_path):
    window = MainWindow(settings=Settings(path=tmp_path / "settings.json"))
    qtbot.addWidget(window)

    settings_actions = [
        action
        for action in window.findChildren(QAction)
        if action.text().replace("&", "") == "Settings..."
    ]
    assert len(settings_actions) == 1
    assert settings_actions[0].shortcut().toString() == "Ctrl+,"
    assert settings_actions[0].menu() is None
