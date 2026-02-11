"""
Offset beam dialog — apply offset to selected frames.

Ported from civilTools/py_widget/tools/offset.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QDialogButtonBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class OffsetDialog(QDialog):
    """Apply offset to selected frames in ETABS."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "tools" / "offset.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Offset Frame")
        self.resize(self.ui.size())
        set_dialog_icon(self, "offset.svg")

        # Add OK/Cancel since the .ui has no buttons
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._run)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _run(self):
        sp = getattr(self.ui, "distance", None)
        offset = sp.value() if sp else 0.0
        neg = getattr(self.ui, "negative", None)
        if neg and neg.isChecked():
            offset = -offset

        try:
            self._etabs.frame_obj.offset_frame(offset)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Offset",
            ok=True,
            summary=f"Applied offset {offset} to selected frames.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
