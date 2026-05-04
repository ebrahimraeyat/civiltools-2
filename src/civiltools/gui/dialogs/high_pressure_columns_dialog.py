"""
High-pressure columns check dialog.

Ported from civilTools/py_widget/control/high_pressure_columns.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QDialogButtonBox

from civiltools.commands.base import CommandResult
from civiltools.gui.busy_dialog import BusyDialog
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class HighPressureColumnsDialog(QDialog):
    """Check columns with axial pressure exceeding threshold."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "high_pressure_columns.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("High Pressure Columns")
        self.resize(self.ui.size())
        set_dialog_icon(self, "high_pressure_columns.svg")

        self._create_connections()

    def _create_connections(self):
        sp = getattr(self.ui, "limit_spinbox", None)
        if sp:
            sp.valueChanged.connect(self._set_group_name)

        # Add OK/Cancel since the .ui has no action button
        from PySide6.QtWidgets import QDialogButtonBox
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._run)
        bbox.rejected.connect(self.reject)
        self.layout().addWidget(bbox)

    def _set_group_name(self, val):
        gn = getattr(self.ui, "group_name", None)
        if gn:
            gn.setText(f"{val:.2f}*Ag*fc")

    def _run(self):
        sp = getattr(self.ui, "limit_spinbox", None)
        limit = sp.value() if sp else 0.3

        try:
            with BusyDialog(
                "High Pressure Columns",
                status_text="ETABS is checking axial pressure demand and collecting overstressed columns…",
                parent=self,
                disable_widgets=[self.ui],
            ) as dlg:
                df = dlg.run(lambda: self._etabs.database.get_axial_pressure_columns(limit))
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if df is None or df.empty:
            QMessageBox.information(self, "No Data", "No column data returned.")
            return

        # Create group in ETABS
        gcb = getattr(self.ui, "group_checkbox", None)
        gn_w = getattr(self.ui, "group_name", None)
        group_name = gn_w.text() if (gcb and gcb.isChecked() and gn_w) else None
        try:
            if "Result" in df.columns:
                hp_names = df.loc[df["Result"] == True, "UniqueName"].tolist()
                if group_name and hp_names:
                    self._etabs.group.add(group_name)
                    for n in hp_names:
                        self._etabs.SapModel.FrameObj.SetGroupAssign(n, group_name)
                sel_all = getattr(self.ui, "select_all", None)
                if sel_all and sel_all.isChecked() and hp_names:
                    self._etabs.view.show_frames(hp_names)
        except Exception:
            pass

        n_hp = len(df[df["Result"] == True]) if "Result" in df.columns else 0
        self._result = CommandResult(
            title="High Pressure Columns",
            dataframe=df,
            ok=n_hp == 0,
            summary=f"{n_hp} columns exceed {limit:.2f}*Ag*fc" if n_hp else "All columns OK",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
