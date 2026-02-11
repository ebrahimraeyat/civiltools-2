"""
Assign modifiers dialog — beam/column/slab property modifiers.

Ported from civilTools/py_widget/assign/assign_modifiers.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class AssignModifiersDialog(QDialog):
    """Assign frame/area property modifiers to selected objects."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "assign" / "assign_modifiers.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Assign Property Modifiers")
        self.resize(self.ui.size())
        set_dialog_icon(self, "assign_modifiers.svg")

        run_btn = getattr(self.ui, "apply_to_etabs_button", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        actions = []
        try:
            # Beam modifiers — read checkbox/spinbox pairs: beam_area, beam_as2, etc.
            beam_mods = self._read_checked_modifiers("beam_")
            if beam_mods:
                self._etabs.frame_obj.assign_frame_modifiers(
                    frame_type="beam", modifiers=beam_mods)
                actions.append("Beam modifiers")

            # Column modifiers
            col_mods = self._read_checked_modifiers("column_")
            if col_mods:
                self._etabs.frame_obj.assign_frame_modifiers(
                    frame_type="column", modifiers=col_mods)
                actions.append("Column modifiers")

            # Slab modifiers
            slab_mods = self._read_checked_modifiers("slabs_")
            if slab_mods:
                self._etabs.area.assign_slab_modifiers(modifiers=slab_mods)
                actions.append("Slab modifiers")

        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        summary = ", ".join(actions) if actions else "No modifiers applied"
        self._result = CommandResult(
            title="Property Modifiers",
            ok=True,
            summary=summary,
        )
        QMessageBox.information(self, "Done", summary)
        self.accept()

    def _read_checked_modifiers(self, prefix: str) -> dict[str, float] | None:
        """Read checkbox/spinbox pairs with given prefix from .ui.

        The .ui has widgets like beam_area_checkbox + beam_area_spinbox,
        beam_i22_checkbox + beam_i22_spinbox, etc.
        Returns dict of {property: value} for checked items, or None if no checkbox checked.
        """
        suffixes = ["area", "as2", "as3", "torsion", "i22", "i33", "mass", "weight"]
        result = {}
        any_checked = False
        for s in suffixes:
            cb = getattr(self.ui, f"{prefix}{s}_checkbox", None)
            sp = getattr(self.ui, f"{prefix}{s}_spinbox", None)
            if cb and cb.isChecked():
                any_checked = True
                result[s] = sp.value() if sp else 1.0
            elif sp:
                result[s] = sp.value()
        return result if any_checked else None

    @property
    def result(self) -> CommandResult | None:
        return self._result
