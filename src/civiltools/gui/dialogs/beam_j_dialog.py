"""
Beam torsion stiffness factor (J) correction dialog.

Ported from civilTools/py_widget/beam_j.py.
Iteratively adjusts beam J-factors until torsional equilibrium.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class BeamJDialog(QDialog):
    """Iterative beam J-factor correction via ETABS frame_obj API."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "beam_j.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Beam J Correction")
        self.resize(self.ui.size())
        set_dialog_icon(self, "beam_j_torsion.svg")

        self._create_connections()

    def _create_connections(self):
        self.ui.run.clicked.connect(self._run)
        init_cb = getattr(self.ui, "initial_checkbox", None)
        if init_cb:
            init_cb.stateChanged.connect(self._toggle_initial_j)

    def _toggle_initial_j(self):
        sp = getattr(self.ui, "initial_spinbox", None)
        cb = getattr(self.ui, "initial_checkbox", None)
        if sp and cb:
            sp.setEnabled(cb.isChecked())

    def _run(self):
        etabs = self._etabs
        # Gather parameters from UI
        selected_beams = getattr(self.ui, "selected_beams", None)
        exclude_selected = getattr(self.ui, "exclude_selected_beams", None)
        beams_names = None

        if (selected_beams and selected_beams.isChecked()) or \
           (exclude_selected and exclude_selected.isChecked()):
            beams, _ = etabs.frame_obj.get_beams_columns()
            names = etabs.select_obj.get_selected_obj_type(2)
            names = [n for n in names if etabs.frame_obj.is_beam(n)]
            if selected_beams and selected_beams.isChecked():
                beams_names = set(names).intersection(beams)
            elif exclude_selected and exclude_selected.isChecked():
                beams_names = set(beams).difference(names)

        num_iteration = self.ui.iteration_spinbox.value()
        tolerance = self.ui.tolerance_spinbox.value()
        j_max = self.ui.maxj_spinbox.value()
        j_min = self.ui.minj_spinbox.value()

        init_cb = getattr(self.ui, "initial_checkbox", None)
        initial_j = None
        if init_cb and init_cb.isChecked():
            initial_j = self.ui.initial_spinbox.value()

        round_cb = getattr(self.ui, "rounding", None)
        decimals = None
        if round_cb and round_cb.isChecked():
            decimals = self.ui.round_decimals.value()

        progressbar = getattr(self.ui, "progressbar", None)

        try:
            gen = etabs.frame_obj.correct_torsion_stiffness_factor(
                load_combinations=None,
                beams_names=beams_names,
                phi=0.75,
                num_iteration=num_iteration,
                tolerance=tolerance,
                j_max_value=j_max,
                j_min_value=j_min,
                initial_j=initial_j,
                decimals=decimals,
            )
            i = 0
            df = None
            while True:
                if progressbar:
                    pct = int(i / max(num_iteration, 1) * 100)
                    progressbar.setValue(pct)
                QApplication.processEvents()
                ret = next(gen)
                if isinstance(ret, int):
                    i += 1
                else:
                    df = ret
                    break
        except StopIteration:
            pass
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if progressbar:
            progressbar.setValue(100)

        if df is not None and not df.empty:
            self._result = CommandResult(
                title="Beam J Factors",
                dataframe=df,
                ok=True,
                summary=f"J-factor correction completed after {i} iterations.",
            )
            self.accept()
        else:
            QMessageBox.information(self, "Done",
                                    "No beam J adjustments needed.")
            self.reject()

    @property
    def result(self) -> CommandResult | None:
        return self._result
