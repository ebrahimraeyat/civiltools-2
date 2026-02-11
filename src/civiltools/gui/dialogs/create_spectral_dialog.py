"""
Create spectral response spectrum dialog.

Ported from civilTools/py_widget/define/create_spectral.py.
Generates .txt spectrum file from Building parameters.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QFileDialog,
)

from civiltools.etabs import config
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class CreateSpectralDialog(QDialog):
    """Generate spectral response spectrum .txt file."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "define" / "create_spectral.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Create Response Spectrum")
        self.resize(self.ui.size())
        set_dialog_icon(self, "spectral.svg")

        self._populate()
        self._create_connections()

    def _populate(self):
        d = config.get_settings_from_etabs(self._etabs)
        # Fill soil type, risk level if present
        for name, items in [
            ("soil_type", ["I", "II", "III", "IV"]),
            ("risk_level", ["خیلی زیاد", "زیاد", "متوسط", "کم"]),
        ]:
            combo = getattr(self.ui, name, None)
            if combo and combo.count() == 0:
                combo.addItems(items)
            if combo and name in d:
                idx = combo.findText(d[name])
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _create_connections(self):
        run_btn = getattr(self.ui, "create_pushbutton", None)
        if run_btn:
            run_btn.clicked.connect(self._run)
        cancel_btn = getattr(self.ui, "cancel_pushbutton", None)
        if cancel_btn:
            cancel_btn.clicked.connect(self.reject)

    def _browse(self):
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Spectrum File", directory, "Text (*.txt)")
        fn_edit = getattr(self.ui, "filename", None)
        if fn_edit and filename:
            fn_edit.setText(filename)

    def _run(self):
        # Prompt for file save location
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Spectrum File", directory, "Text (*.txt)")
        if not filename:
            return

        if not filename.endswith(".txt"):
            filename += ".txt"

        try:
            from civiltools.building import spectral
            soil_combo = getattr(self.ui, "soil_type", None)
            risk_combo = getattr(self.ui, "risk_level", None)
            soil_type = soil_combo.currentText() if soil_combo else "II"
            risk_level = risk_combo.currentText() if risk_combo else "زیاد"

            sotoh = {"خیلی زیاد": 0.35, "زیاد": 0.30, "متوسط": 0.25, "کم": 0.20}
            acc = sotoh.get(risk_level, 0.30)

            rf = spectral.ReflectionFactor(soilType=soil_type, acc=acc)
            import numpy as np
            x = np.arange(0, rf.endT, rf.dt)
            y = rf.BCurve()

            with open(filename, "w") as f:
                for xi, yi in zip(x, y):
                    f.write(f"{xi:.4f}\t{yi:.4f}\n")

        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Response Spectrum",
            ok=True,
            summary=f"Spectrum saved to {Path(filename).name}",
        )
        QMessageBox.information(self, "Done", f"Spectrum saved to:\n{filename}")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
