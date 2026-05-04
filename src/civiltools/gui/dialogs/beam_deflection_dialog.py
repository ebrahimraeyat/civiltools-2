"""
Beam deflection control dialog.

Ported from civilTools/py_widget/control/control_deflection_of_beams.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication

from civiltools.commands.base import CommandResult
from civiltools.gui.busy_dialog import BusyDialog
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class BeamDeflectionDialog(QDialog):
    """Check beam deflection limits per design code."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "control_deflection_of_beams.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Beam Deflection Control")
        self.resize(self.ui.size())
        set_dialog_icon(self, "deflection.svg")

        self._create_connections()

    def _create_connections(self):
        run_btn = getattr(self.ui, "check_button", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        try:
            with BusyDialog(
                "Beam Deflection Control",
                status_text="ETABS is reading beam design output and checking deflection limits…",
                parent=self,
                disable_widgets=[self.ui],
            ) as dlg:
                df = dlg.run(lambda: self._etabs.design.get_deflection_of_beams())
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if df is None or df.empty:
            QMessageBox.information(self, "No Data", "No deflection data returned.")
            return

        n_fail = 0
        if "Result" in df.columns:
            n_fail = (df["Result"] == False).sum()

        self._result = CommandResult(
            title="Beam Deflection",
            dataframe=df,
            ok=n_fail == 0,
            summary=f"{n_fail} beams exceed deflection limit" if n_fail else "All beams OK",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
