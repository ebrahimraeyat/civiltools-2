"""
Edit frame section properties dialog — change beam/column section fc'.

Ported from civilTools/py_widget/edit/edit_frame_sections_props.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class EditFrameSectionsDialog(QDialog):
    """Change concrete strength (fc') for beam/column sections."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "edit" / "edit_frame_sections_props.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Edit Frame Section Properties")
        self.resize(self.ui.size())
        set_dialog_icon(self, "property_editor.svg")

        run_btn = getattr(self.ui, "assign_pushbutton", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        # Read concrete materials combobox
        mats_combo = getattr(self.ui, "concrete_mats", None)
        concrete_fc = mats_combo.currentText() if mats_combo else ""

        # Which to update: beams and/or columns
        beams_cb = getattr(self.ui, "beams", None)
        cols_cb = getattr(self.ui, "columns", None)
        do_beams = beams_cb.isChecked() if beams_cb else True
        do_columns = cols_cb.isChecked() if cols_cb else True

        try:
            self._etabs.prop_frame.change_beams_columns_section_fc(
                concrete_fc=concrete_fc,
                beams=do_beams,
                columns=do_columns,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        parts = []
        if do_beams:
            parts.append(f"Beams fc'={concrete_fc}")
        if do_columns:
            parts.append(f"Columns fc'={concrete_fc}")
        summary = ", ".join(parts) if parts else "No changes"

        self._result = CommandResult(
            title="Edit Sections",
            ok=True,
            summary=summary,
        )
        QMessageBox.information(self, "Done", f"Section properties updated: {summary}")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
