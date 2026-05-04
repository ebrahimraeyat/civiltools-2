"""
Create 25% shear wall file dialog.

Ported from civilTools/py_widget/shearwall/create_25percent_file.py.
Creates new ETABS file with 25% of shear wall stiffness for PMM check.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QFileDialog

from civiltools.commands.base import CommandResult
from civiltools.gui.busy_dialog import BusyDialog
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class Create25PercentDialog(QDialog):
    """Create ETABS file with 25% shear wall stiffness for PMM analysis."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "shearwall" / "create_25percent_file.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Create 25% File")
        self.resize(self.ui.size())
        set_dialog_icon(self, "create_25percent_file.svg")

        self._create_connections()

    def _create_connections(self):
        run_btn = getattr(self.ui, "create_file", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _browse(self):
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save 25% File", directory, "ETABS (*.EDB)")
        fn_edit = getattr(self.ui, "filename", None)
        if fn_edit and filename:
            fn_edit.setText(filename)

    def _run(self):
        # Prompt for file save location
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save 25% File", directory, "ETABS (*.EDB)")
        if not filename:
            return

        try:
            with BusyDialog(
                "Creating 25% Shear Wall File",
                status_text="ETABS is generating the reduced-stiffness model file…",
                parent=self,
                disable_widgets=[self.ui],
            ) as dlg:
                df = dlg.run(lambda: self._etabs.shearwall.create_25percent_file(filename))
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="25% Shear Wall",
            dataframe=df if df is not None else None,
            ok=True,
            summary=f"25% file created: {Path(filename).name}",
        )
        QMessageBox.information(self, "Done",
                                f"Created 25% shear wall file:\n{filename}")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
