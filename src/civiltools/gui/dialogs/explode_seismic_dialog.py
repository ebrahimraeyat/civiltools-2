"""
Explode seismic load patterns dialog.

Ported from civilTools/py_widget/explode_seismic_load_patterns.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class ExplodeSeismicDialog(QDialog):
    """Expand seismic load patterns in ETABS model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "explode_seismic_load_patterns.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Explode Seismic Load Patterns")
        self.resize(self.ui.size())
        set_dialog_icon(self, "explode.svg")

        self._d = get_settings_from_etabs(self._etabs)
        self._populate()

        # Connect the replace buttons
        rx = getattr(self.ui, "replace_ex", None)
        if rx:
            rx.clicked.connect(lambda: self._run("x"))
        ry = getattr(self.ui, "replace_ey", None)
        if ry:
            ry.clicked.connect(lambda: self._run("y"))

    def _populate(self):
        d = self._d
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic(d)
        except Exception:
            return

        # Fill the labels showing current load pattern names
        for attr, val in [("ex", ex), ("epx", exp), ("enx", exn),
                          ("ey", ey), ("epy", eyp), ("eny", eyn)]:
            w = getattr(self.ui, attr, None)
            if w and val:
                w.setText(str(val))

    def _run(self, direction="x"):
        progressbar = getattr(self.ui, "progressbar", None)
        result_label = getattr(self.ui, "result_label", None)

        try:
            prefix = ""
            suffix = ""
            dp = getattr(self.ui, "drift_prefix", None)
            ds = getattr(self.ui, "drift_suffix", None)
            if dp:
                prefix = dp.text()
            if ds:
                suffix = ds.text()

            gen = self._etabs.database.expand_loads_by_direction(
                direction=direction, prefix=prefix, suffix=suffix)
            i = 0
            for msg in gen:
                i += 1
                if progressbar:
                    progressbar.setValue(min(i * 10, 100))
                if result_label:
                    result_label.setText(str(msg))
                QApplication.processEvents()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if progressbar:
            progressbar.setValue(100)

        self._result = CommandResult(
            title="Explode Seismic",
            ok=True,
            summary=f"Exploded seismic load patterns ({direction.upper()}).",
        )
        QMessageBox.information(self, "Done",
                                f"Exploded {direction.upper()} seismic load patterns.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
