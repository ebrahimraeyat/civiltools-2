"""
Response spectrum (dynamic scale) dialog — loads response_spectrum.ui.

Ported from civilTools/py_widget/response_spectrum.py.
The .ui has: 100-30 / Angular radio, scale factor combos, iteration,
tolerance, analyze/reset checkboxes, x/y dynamic loadcase lists,
ex/ey comboboxes, Run button.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from civiltools.commands.base import CommandResult
from civiltools.etabs import config
from civiltools.gui.busy_dialog import BusyDialog
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def _get_checked_items(lw) -> list[str]:
    """Return checked items from a QListWidget."""
    return [
        lw.item(i).text()
        for i in range(lw.count())
        if lw.item(i).checkState() == Qt.CheckState.Checked
    ]


class ResponseSpectrumDialog(QDialog):
    """Dialog for dynamic scale factor — mirrors response_spectrum.ui."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        # Load .ui
        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "response_spectrum.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Response Spectrum Analysis")
        self.resize(self.ui.size())
        set_dialog_icon(self, "spectral.svg")

        # Config
        self._d = config.get_settings_from_etabs(self._etabs)

        # Populate
        self._populate()

        # Connections
        self.ui.run.clicked.connect(self._run)
        self.ui.combination_response_spectrum_checkbox.clicked.connect(
            self._reset_widget
        )
        self.ui.angular_response_spectrum_checkbox.clicked.connect(
            self._reset_widget
        )

    # ── populate ────────────────────────────────────────────────────

    def _populate(self):
        config.load(self._etabs, self.ui, self._d)

        # Disable second-system comboboxes if not active
        if not self._d.get("activate_second_system", False):
            for name in (
                "ex1_combobox", "ey1_combobox",
                "ex1_drift_combobox", "ey1_drift_combobox",
            ):
                w = getattr(self.ui, name, None)
                if w:
                    w.setEnabled(False)

    def _reset_widget(self, checked):
        """Toggle 100-30 vs Angular mode."""
        sender = self.sender()
        is_100_30 = sender == self.ui.combination_response_spectrum_checkbox
        self.ui.angular_tableview.setEnabled(not is_100_30)
        self.ui.angular_response_spectrum_checkbox.setChecked(not is_100_30)
        self.ui.combination_response_spectrum_checkbox.setChecked(is_100_30)
        self.ui.x_dynamic_loadcase_list.setEnabled(is_100_30)
        self.ui.y_dynamic_loadcase_list.setEnabled(is_100_30)
        self.ui.y_scalefactor_combobox.setEnabled(is_100_30)
        self.ui.x_label.setEnabled(is_100_30)
        self.ui.y_label.setEnabled(is_100_30)

    # ── run ─────────────────────────────────────────────────────────

    def _run(self):
        d = self._d
        two_sys = d.get("activate_second_system", False)

        tab_index = self.ui.tabwidget.currentIndex()
        is_angular = self.ui.angular_response_spectrum_checkbox.isChecked()

        # Get EX/EY names
        if tab_index == 0 or is_angular:
            ex_name = self.ui.ex_combobox.currentText()
            ey_name = self.ui.ey_combobox.currentText()
            if two_sys:
                ex1 = self.ui.ex1_combobox.currentText()
                ey1 = self.ui.ey1_combobox.currentText()
                ex_name = [ex_name, ex1]
                ey_name = [ey_name, ey1]
            lw_x = self.ui.x_dynamic_loadcase_list
            lw_y = self.ui.y_dynamic_loadcase_list
        else:
            ex_name = self.ui.ex_drift_combobox.currentText()
            ey_name = self.ui.ey_drift_combobox.currentText()
            if two_sys:
                ex1 = self.ui.ex1_drift_combobox.currentText()
                ey1 = self.ui.ey1_drift_combobox.currentText()
                ex_name = [ex_name, ex1]
                ey_name = [ey_name, ey1]
            lw_x = self.ui.x_dynamic_drift_loadcase_list
            lw_y = self.ui.y_dynamic_drift_loadcase_list

        x_scale = float(self.ui.x_scalefactor_combobox.currentText())
        y_scale = float(self.ui.y_scalefactor_combobox.currentText())
        num_iter = self.ui.iteration.value()
        tolerance = self.ui.tolerance.value()
        reset = self.ui.reset.isChecked()
        analyze = self.ui.analyze.isChecked()
        consider_min = self.ui.consider_min_static_base_shear.isChecked()

        if is_angular:
            # Angular response spectrum
            angular_model = self.ui.angular_tableview.model()
            if angular_model is None:
                QMessageBox.warning(self, "No Data",
                                    "No angular spectrum data loaded.")
                return
            angular_specs, section_cuts = [], []
            for row in range(angular_model.rowCount()):
                angular_specs.append(
                    angular_model.data(angular_model.index(row, 1))
                )
                section_cuts.append(
                    angular_model.data(angular_model.index(row, 2))
                )
            try:
                with BusyDialog(
                    "Response Spectrum Analysis",
                    status_text="ETABS is scaling spectra and collecting base-shear results…",
                    parent=self,
                    disable_widgets=[self.ui],
                ) as dlg:
                    _, df = dlg.run(lambda: self._etabs.angles_response_spectrums_analysis(
                        ex_name, ey_name, angular_specs, section_cuts,
                        x_scale, num_iter, tolerance, reset, analyze,
                    ))
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))
                return
            way = "Angular"
        else:
            # 100-30 combination
            x_specs = _get_checked_items(lw_x)
            y_specs = _get_checked_items(lw_y)
            if not x_specs and not y_specs:
                QMessageBox.warning(self, "No Load Cases",
                                    "Select at least one spectrum load case.")
                return
            try:
                with BusyDialog(
                    "Response Spectrum Analysis",
                    status_text="ETABS is running the combination analysis and updating response-spectrum scales…",
                    parent=self,
                    disable_widgets=[self.ui],
                ) as dlg:
                    _, _, df = dlg.run(lambda: self._etabs.scale_response_spectrums(
                        ex_name, ey_name, x_specs, y_specs,
                        x_scale, y_scale, num_iter, tolerance,
                        reset, analyze, consider_min,
                    ))
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))
                return
            way = "100-30"

        self._result = CommandResult(
            title=f"Base Shear — {way}",
            ok=True,
            dataframe=df,
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
