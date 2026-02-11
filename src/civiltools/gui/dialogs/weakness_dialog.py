"""
Weakness analysis dialogs — get beam/column weakness and show cached results.

Ported from civilTools/py_widget/get_weakness.py and show_weakness.py.
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


class WeaknessDialog(QDialog):
    """Compute beam/column weakness and save to JSON cache."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "weakness.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Beam/Column Weakness Check")
        self.resize(self.ui.size())
        set_dialog_icon(self, "weakness.svg")

        self._d = get_settings_from_etabs(self._etabs)
        self._populate()
        self.ui.run.clicked.connect(self._run)

    def _populate(self):
        d = self._d
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic(d)
            x_names = [ex, exn, exp]
            y_names = [ey, eyn, eyp]
        except Exception:
            x_names, y_names = ["EX"], ["EY"]

        for lw_name, names in [
            ("x_loadcase_list", x_names), ("y_loadcase_list", y_names),
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

    def _get_checked(self, list_name):
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
            self.statusBar = self.parent().statusBar() if self.parent() else None
        except Exception:
            self.statusBar = None

        try:
            beams_df, cols_df = self._etabs.frame_obj.get_beams_columns_weakness_structure(
                loadcases=x_cases + y_cases,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        # Save to JSON for show_weakness
        try:
            json_name = f"Weakness {self._etabs.get_file_name_without_suffix()}"
            self._etabs.save_to_json_in_edb_folder(
                json_name, {"beams": beams_df.to_dict(), "columns": cols_df.to_dict()}
            )
        except Exception:
            pass

        self._result = CommandResult(
            title="Beam/Column Weakness",
            dataframe=cols_df,
            ok=True,
            summary=f"Beams: {len(beams_df)}, Columns: {len(cols_df)}",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result


class ShowWeaknessDialog(QDialog):
    """Show cached weakness results from JSON."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "show_weakness.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Show Weakness Results")
        self.resize(self.ui.size())
        set_dialog_icon(self, "show_weakness.svg")

        self.ui.run.clicked.connect(self._run)

    def _run(self):
        import pandas as pd
        try:
            json_name = f"Weakness {self._etabs.get_file_name_without_suffix()}"
            data = self._etabs.load_from_json_in_edb_folder(json_name)
            cols_df = pd.DataFrame(data["columns"])
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"No cached results found:\n{exc}")
            return

        self._result = CommandResult(
            title="Weakness (Cached)",
            dataframe=cols_df,
            ok=True,
            summary="Loaded from cached analysis.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
