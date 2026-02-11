"""
Drift check dialog — loads drift.ui from civilTools widgets.

Ported from civilTools/py_widget/drift.py.  The .ui has:
- Tab 0: Static Load Cases (x/y drift loadcase lists)
- Tab 1: Dynamic Load Cases (x/y dynamic drift lists, scale factors, angular)
- create_t_file_box, structure type, show_separate checkbox
- Run button
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class DriftDialog(QDialog):
    """Dialog for story drift check — mirrors civilTools drift.ui."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        # Load .ui
        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "drift.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Automatic Drift")
        self.resize(self.ui.size())
        set_dialog_icon(self, "drift.svg")

        # Config
        self._d = get_settings_from_etabs(self._etabs)

        # Populate
        self._populate_static_lists()
        self._populate_dynamic_lists()

        # Connections
        self.ui.run.clicked.connect(self._run)
        self.ui.create_t_file_box.clicked.connect(
            lambda chk: self.ui.structuretype_groupbox.setEnabled(chk)
        )

    # ── populate ────────────────────────────────────────────────────

    def _populate_static_lists(self):
        """Fill x/y drift loadcase lists (Tab 0 - Static)."""
        d = self._d
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic_drift(d)
            x_names = [ex, exn, exp]
            y_names = [ey, eyn, eyp]
            if d.get("activate_second_system", False):
                try:
                    ex2, exn2, exp2, ey2, eyn2, eyp2 = (
                        self._etabs.get_second_system_seismic_drift(d)
                    )
                    x_names.extend([ex2, exn2, exp2])
                    y_names.extend([ey2, eyn2, eyp2])
                except Exception:
                    pass
        except Exception:
            x_names, y_names = ["EXDrift"], ["EYDrift"]

        self._fill_checked_list(self.ui.x_drift_loadcase_list, x_names)
        self._fill_checked_list(self.ui.y_drift_loadcase_list, y_names)

    def _populate_dynamic_lists(self):
        """Fill dynamic drift loadcase lists (Tab 1)."""
        d = self._d
        try:
            sx, sxe, sy, sye = self._etabs.get_dynamic_drift_loadcases(d)
            self._fill_checked_list(
                self.ui.x_dynamic_drift_loadcase_list, [sx, sxe]
            )
            self._fill_checked_list(
                self.ui.y_dynamic_drift_loadcase_list, [sy, sye]
            )
        except Exception:
            pass

        # Angular specs
        try:
            lw = self.ui.angular_specs
            angles_spectral = self._etabs.load_cases.get_spectral_with_angles()
            specs = list(angles_spectral.values())
            self._fill_checked_list(lw, specs)
        except Exception:
            pass

    @staticmethod
    def _fill_checked_list(lw, names: list[str]):
        """Add checkable items to a QListWidget."""
        lw.clear()
        lw.addItems([n for n in names if n])
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)

    @staticmethod
    def _get_checked_items(lw) -> list[str]:
        """Return checked items from a QListWidget."""
        items = []
        for i in range(lw.count()):
            item = lw.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items.append(item.text())
        return items

    # ── run ─────────────────────────────────────────────────────────

    def _run(self):
        d = get_settings_from_etabs(self._etabs)
        tab = self.ui.tab_widget.currentIndex()

        # Get parameters from config
        no_of_stories = d.get("no_of_story_x", 1)
        cdx = d.get("cdx", 1.0)
        cdy = d.get("cdy", 1.0)
        two_system = d.get("activate_second_system", False)

        structure_type = "concrete"
        if hasattr(self.ui, 'steel_radiobutton') and self.ui.steel_radiobutton.isChecked():
            structure_type = "steel"

        create_t_file = self.ui.create_t_file_box.isChecked()

        # Handle two system cd overrides
        if two_system and not create_t_file:
            rux = d.get("Rux", None)
            if rux:
                ruy = d.get("Ruy", None)
                rux1 = d.get("Rux1", None)
                ruy1 = d.get("Ruy1", None)
                if rux1 and rux1 >= rux:
                    cdx = d.get("cdx1", cdx)
                if ruy1 and ruy1 >= ruy:
                    cdy = d.get("cdy1", cdy)

        # T file creation (like original drift.py)
        if create_t_file:
            try:
                from civiltools.etabs.config import get_settings_from_etabs as _gs
                self._etabs.unlock_model()
                tx, ty, main_file = self._etabs.get_drift_periods(
                    structure_type=structure_type
                )
            except Exception as exc:
                QMessageBox.critical(self, "Error",
                                     f"Failed to create T file:\n{exc}")
                return

        # Collect loadcases
        x_loadcases, y_loadcases, loadcases = self._get_load_cases(tab)
        if not loadcases:
            loadcases = x_loadcases + y_loadcases

        if not loadcases:
            QMessageBox.warning(self, "No Load Cases",
                                "Please select at least one load case.")
            return

        # Scale response spectrums if dynamic tab
        if tab == 1 and create_t_file:
            x_specs, y_specs, _ = self._get_load_cases(tab=1)
            ex_name = d.get("ex_drift_combobox", "")
            ey_name = d.get("ey_drift_combobox", "")
            x_sf = float(self.ui.x_scalefactor_combobox.currentText())
            y_sf = float(self.ui.y_scalefactor_combobox.currentText())
            try:
                self._etabs.scale_response_spectrums(
                    ex_name, ey_name, x_specs, y_specs, x_sf, y_sf,
                )
            except Exception:
                pass

        # Get drifts
        try:
            ret = self._etabs.get_drifts(
                no_of_stories, cdx, cdy,
                loadcases, x_loadcases, y_loadcases,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"get_drifts failed:\n{exc}")
            return

        if ret is None:
            QMessageBox.warning(
                self, "Diaphragm",
                "Please check that you assigned diaphragm to stories."
            )
            return

        # Reopen main file if T file was created
        if create_t_file and structure_type == "steel":
            try:
                self._etabs.SapModel.File.OpenFile(str(main_file))
            except Exception:
                pass

        df = pd.DataFrame(ret[0], columns=ret[1])

        analysis_type = "Dynamic" if tab == 1 else "Static"
        show_separate = self.ui.show_separate_checkbox.isChecked()

        if show_separate:
            # Show X direction
            filt = df["OutputCase"].isin(x_loadcases)
            df_x = df.loc[filt]
            self._result = CommandResult(
                title=f"{analysis_type} Drift X-Dir",
                ok=True,
                dataframe=df_x,
            )
            # Store Y for a second tab (caller handles)
            self._result_y = CommandResult(
                title=f"{analysis_type} Drift Y-Dir",
                ok=True,
                dataframe=df.loc[df["OutputCase"].isin(y_loadcases)],
            )
        else:
            self._result = CommandResult(
                title=f"{analysis_type} Drift",
                ok=True,
                dataframe=df,
            )
            self._result_y = None

        self.accept()

    def _get_load_cases(self, tab: int):
        """Get selected load cases from the active tab."""
        x_lc, y_lc, all_lc = [], [], []
        if tab == 0:
            x_lc = self._get_checked_items(self.ui.x_drift_loadcase_list)
            y_lc = self._get_checked_items(self.ui.y_drift_loadcase_list)
        elif tab == 1:
            if self.ui.xy.isChecked():
                x_lc = self._get_checked_items(
                    self.ui.x_dynamic_drift_loadcase_list
                )
                y_lc = self._get_checked_items(
                    self.ui.y_dynamic_drift_loadcase_list
                )
            elif self.ui.angular.isChecked():
                all_lc = self._get_checked_items(self.ui.angular_specs)
        return x_lc, y_lc, all_lc

    @property
    def result(self) -> CommandResult | None:
        return self._result

    @property
    def result_y(self) -> CommandResult | None:
        """Second result when Show Separate is checked."""
        return getattr(self, "_result_y", None)
