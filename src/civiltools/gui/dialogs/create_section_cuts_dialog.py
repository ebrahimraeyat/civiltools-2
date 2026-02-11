"""
Create section cuts dialog.

Ported from civilTools/py_widget/define/create_section_cuts.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class CreateSectionCutsDialog(QDialog):
    """Create section cuts in ETABS model for force extraction."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "define" / "create_section_cuts.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Create Section Cuts")
        self.resize(self.ui.size())
        set_dialog_icon(self, "cut.svg")

        run_btn = getattr(self.ui, "accept_pushbutton", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        try:
            n = self._etabs.database.create_section_cuts()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Section Cuts",
            ok=True,
            summary=f"Created {n} section cuts." if isinstance(n, int) else "Section cuts created.",
        )
        QMessageBox.information(self, "Done", "Section cuts created in ETABS.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
