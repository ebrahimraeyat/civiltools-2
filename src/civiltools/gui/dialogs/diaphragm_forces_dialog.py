"""
Diaphragm applied forces dialog — creates separate ETABS files per story.

Ported from civilTools/py_widget/control/diaphragm_applied_forces.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class DiaphragmForcesDialog(QDialog):
    """Create separate ETABS files with diaphragm applied forces."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "diaphragm_applied_forces.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Diaphragm Applied Forces")
        self.resize(self.ui.size())
        set_dialog_icon(self, "mass.svg")

        self._populate_stories()

        run_btn = getattr(self.ui, "create_pushbutton", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _populate_stories(self):
        from PySide6.QtCore import Qt
        lw = getattr(self.ui, "stories", None)
        if lw is None:
            return
        try:
            stories = self._etabs.story.get_sorted_story_name(
                reverse=False, include_base=False)
        except Exception:
            stories = []
        lw.clear()
        lw.addItems(stories)
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)

    def _run(self):
        from PySide6.QtCore import Qt
        lw = getattr(self.ui, "stories", None)
        stories = []
        if lw:
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    stories.append(item.text())

        if not stories:
            QMessageBox.warning(self, "No Stories", "Select at least one story.")
            return

        try:
            self._etabs.story.create_files_diaphragm_applied_forces(stories)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Diaphragm Forces",
            ok=True,
            summary=f"Created {len(stories)} diaphragm force files.",
        )
        QMessageBox.information(self, "Done",
                                f"Created {len(stories)} files for diaphragm forces.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
