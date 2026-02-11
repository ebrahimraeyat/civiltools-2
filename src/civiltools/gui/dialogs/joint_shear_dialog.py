"""
Joint Shear / BCC dialog — loads control_joint_shear_bc.ui.

Ported from civilTools/py_widget/control/control_joint_shear.py.
The .ui has: structure_type_combobox, show_js_table, show_bc_table,
only_show_results_checkbox, and check button.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class JointShearDialog(QDialog):
    """Dialog for joint shear / beam-column capacity check."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        # Load .ui
        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "control_joint_shear_bc.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Joint Shear / BCC")
        self.resize(self.ui.size())
        set_dialog_icon(self, "joint_shear.svg")

        # Auto-detect structure ductility
        self._set_structure_type()

        # Wire
        self.ui.check.clicked.connect(self._check)

    def _set_structure_type(self):
        """Set structure type combobox based on system ductility."""
        d = get_settings_from_etabs(self._etabs)
        try:
            ductilities = self._etabs.get_x_and_y_system_ductility(d)
            if "M" in ductilities:
                self.ui.structure_type_combobox.setCurrentIndex(0)
            elif "H" in ductilities:
                self.ui.structure_type_combobox.setCurrentIndex(1)
                self.ui.show_bc_table.setChecked(True)
        except Exception:
            pass

    def _check(self):
        show_js = self.ui.show_js_table.isChecked()
        show_bc = self.ui.show_bc_table.isChecked()
        create_file = not self.ui.only_show_results_checkbox.isChecked()

        if not show_js and not show_bc:
            QMessageBox.warning(
                self, "Selection",
                "Please check at least one of JS Table or BC Table.",
            )
            return

        filename = ""
        if show_js:
            filename += "js"
        if show_bc:
            filename += "bc"

        structure_type = self.ui.structure_type_combobox.currentText()

        try:
            self._etabs.save()
            df = self._etabs.create_joint_shear_bcc_file(
                filename,
                structure_type,
                open_main_file=True,
                create_file=create_file,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if df is None:
            QMessageBox.warning(self, "No Data",
                                "No joint shear data returned.")
            return

        # Filter columns based on selection
        if show_js and show_bc:
            title = "Joint Shear & Beam-Column Capacity"
        elif show_js:
            cols = [c for c in ['Story', 'Label', 'UniqueName',
                                'JSMajRatio', 'JSMinRatio'] if c in df.columns]
            df = df[cols]
            title = "Joint Shear"
        else:
            cols = [c for c in ['Story', 'Label', 'UniqueName',
                                'BCMajRatio', 'BCMinRatio'] if c in df.columns]
            df = df[cols]
            title = "Beam-Column Capacity"

        self._result = CommandResult(
            title=title,
            ok=True,
            dataframe=df,
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
