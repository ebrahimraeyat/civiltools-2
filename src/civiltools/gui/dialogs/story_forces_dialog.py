"""
Story shear force check dialog.

Ported from civilTools/py_widget/control/shear_story.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QDialogButtonBox

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class StoryForcesDialog(QDialog):
    """Show story shear forces with percentage distribution."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "shear_story.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Story Shear Forces")
        self.resize(self.ui.size())
        set_dialog_icon(self, "shear.svg")

        self._d = get_settings_from_etabs(self._etabs)
        self._populate()

        # Add OK/Cancel since the .ui has only list widgets
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._run)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _populate(self):
        d = self._d
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic(d)
            x_names = [ex, exn, exp]
            y_names = [ey, eyn, eyp]
        except Exception:
            x_names, y_names = ["EX"], ["EY"]

        for lw_name, names in [
            ("x_loadcase_list", x_names), ("y_loadcase_list", y_names),
        ]:
            lw = getattr(self.ui, lw_name, None)
            if lw is None:
                continue
            lw.clear()
            lw.addItems([n for n in names if n])
            for i in range(lw.count()):
                item = lw.item(i)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)

    def _get_checked(self, list_name):
        lw = getattr(self.ui, list_name, None)
        if lw is None:
            return []
        return [
            lw.item(i).text()
            for i in range(lw.count())
            if lw.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _run(self):
        x_cases = self._get_checked("x_loadcase_list")
        y_cases = self._get_checked("y_loadcase_list")

        try:
            df = self._etabs.get_story_forces_with_percentages(
                loadcases=x_cases + y_cases)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if df is None or df.empty:
            QMessageBox.information(self, "No Data", "No story force data returned.")
            return

        self._result = CommandResult(
            title="Story Shear Forces",
            dataframe=df,
            ok=True,
            summary="Story force percentage distribution computed.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
