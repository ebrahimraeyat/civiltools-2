"""GUI regression tests for report generation options."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QGroupBox, QLabel

from civiltools.gui.dialogs.report_dialog import ReportDialog
from civiltools.report.report_config import REFRESHABLE_SECTIONS


class _SapModel:
    @staticmethod
    def GetModelFilename() -> str:  # noqa: N802 - mirrors ETABS COM API
        return ""


class _Etabs:
    SapModel = _SapModel()


def test_report_dialog_shows_cache_live_controls(qtbot):
    dialog = ReportDialog(_Etabs())
    qtbot.addWidget(dialog)
    dialog.show()

    groups = {group.title(): group for group in dialog.findChildren(QGroupBox)}
    assert groups["Refresh Results from ETABS"].isVisible()
    assert not dialog.findChildren(QComboBox)

    hint_texts = {label.text() for label in dialog.findChildren(QLabel)}
    assert "Checked = Get from ETABS; unchecked = Using Last Results." in hint_texts

    refresh_checks = groups["Refresh Results from ETABS"].findChildren(QCheckBox)
    assert len(refresh_checks) == len(REFRESHABLE_SECTIONS)
    assert "100%-30% Column Check" in {check.text() for check in refresh_checks}

    dialog._set_refresh_checks(True)
    assert all(check.isChecked() for check in refresh_checks)
    dialog._set_refresh_checks(False)
    assert not any(check.isChecked() for check in refresh_checks)
