"""
Assigns dialog — end-length offsets, diaphragm assignments, etc.

Ported from civilTools/py_widget/assign/assigns.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class AssignsDialog(QDialog):
    """Apply frame/area assignments: offsets, diaphragm, etc."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "assign" / "assigns.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Assignments")
        self.resize(self.ui.size())
        set_dialog_icon(self, "assigns.svg")

        self._create_connections()

    def _create_connections(self):
        """Connect each set/check pushbutton to its action."""
        pairs = [
            ("set_end_length_offset_pushbutton", self._set_end_length_offsets),
            ("set_diaphragm_pushbutton", self._set_diaphragm),
            ("set_earthquake_pushbutton", self._set_earthquake),
            ("set_property_modifiers_pushbutton", self._set_property_modifiers),
        ]
        for name, slot in pairs:
            btn = getattr(self.ui, name, None)
            if btn:
                btn.clicked.connect(slot)

        close_btn = getattr(self.ui, "close_button", None)
        if close_btn:
            close_btn.clicked.connect(self.accept)

    def _set_end_length_offsets(self):
        try:
            sp = getattr(self.ui, "end_length_offset_spinbox", None)
            ratio = sp.value() if sp else 0.5
            self._etabs.frame_obj.set_end_length_offsets(ratio)
            QMessageBox.information(self, "Done", f"End-length offsets set (ratio={ratio}).")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _set_diaphragm(self):
        try:
            combo = getattr(self.ui, "diaphragm_combobox", None)
            name = combo.currentText() if combo else ""
            self._etabs.diaphragm.assign_diaphragm(name)
            QMessageBox.information(self, "Done", "Diaphragm assigned.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _set_earthquake(self):
        try:
            self._etabs.load_patterns.select_all_load_patterns()
            QMessageBox.information(self, "Done", "Earthquake assignment applied.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _set_property_modifiers(self):
        try:
            self._etabs.frame_obj.set_frame_property_modifiers()
            QMessageBox.information(self, "Done", "Property modifiers applied.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    @property
    def result(self) -> CommandResult | None:
        return self._result
