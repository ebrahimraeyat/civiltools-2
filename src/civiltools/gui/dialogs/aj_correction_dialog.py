"""
Aj correction dialog — accidental eccentricity amplification factor.

Ported from civilTools/py_widget/aj_correction.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class AjCorrectionDialog(QDialog):
    """Calculate and apply Aj correction factors for accidental eccentricity."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "aj_correction.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Aj Correction")
        self.resize(self.ui.size())
        set_dialog_icon(self, "show_aj.svg")

        self._d = get_settings_from_etabs(self._etabs)
        self._populate()
        self.ui.static_apply.clicked.connect(self._run)

    def _populate(self):
        """Fill load case lists from config."""
        d = self._d
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic(d)
        except Exception:
            return

        x_names = [exp, exn]
        y_names = [eyp, eyn]
        if d.get("activate_second_system", False):
            try:
                _, exn2, exp2, _, eyn2, eyp2 = self._etabs.get_second_system_seismic(d)
                x_names.extend([exp2, exn2])
                y_names.extend([eyp2, eyn2])
            except Exception:
                pass

        from PySide6.QtCore import Qt
        for lw_name, names in [
            ("x_loadcase_list", x_names),
            ("y_loadcase_list", y_names),
        ]:
            lw = getattr(self.ui, lw_name, None)
            if lw is None:
                continue
            lw.clear()
            lw.addItems([n for n in names if n])
            for i in range(lw.count()):
                item = lw.item(i)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)

    def _get_checked(self, list_name: str) -> list[str]:
        from PySide6.QtCore import Qt
        lw = getattr(self.ui, list_name, None)
        if lw is None:
            return []
        return [
            lw.item(i).text()
            for i in range(lw.count())
            if lw.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _run(self):
        x_cases = self._get_checked("x_loadcase_list")
        y_cases = self._get_checked("y_loadcase_list")
        if not x_cases and not y_cases:
            QMessageBox.warning(self, "No Cases", "Select at least one load case.")
            return

        try:
            aj_df, aj_applied_df = self._etabs.apply_aj_df(
                x_names=x_cases, y_names=y_cases)
            self._etabs.database.write_daynamic_aj_user_coefficient(aj_applied_df)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Aj Correction",
            dataframe=aj_df,
            ok=True,
            summary="Aj correction factors calculated and applied.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
