"""
Torsion check dialog — loads torsion.ui from civilTools widgets.

Ported from civilTools/py_widget/torsion.py.  The .ui gives two
QListWidgets (x_loadcase_list / y_loadcase_list) plus a Run button.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class TorsionDialog(QDialog):
    """Dialog for torsion irregularity check — mirrors civilTools torsion.ui."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        # Load .ui
        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "torsion.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        # Embed loaded widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle(self.ui.windowTitle() or "Torsion Check")
        self.resize(self.ui.size())
        set_dialog_icon(self, "torsion.svg")

        # Populate & wire
        self._populate_load_cases()
        self.ui.run.clicked.connect(self._run)

    # ── populate ────────────────────────────────────────────────────

    def _populate_load_cases(self):
        d = get_settings_from_etabs(self._etabs)
        try:
            ex, exn, exp, ey, eyn, eyp = self._etabs.get_first_system_seismic(d)
        except Exception:
            # Fallback: get all seismic load patterns
            seismic = self._etabs.load_patterns.get_seismic_load_patterns()
            flat = []
            for s in seismic:
                if isinstance(s, (set, list, tuple)):
                    flat.extend(s)
                else:
                    flat.append(str(s))
            half = len(flat) // 2
            x_names = flat[:half] if flat else ["EX"]
            y_names = flat[half:] if flat else ["EY"]
            self._fill_list(self.ui.x_loadcase_list, x_names)
            self._fill_list(self.ui.y_loadcase_list, y_names)
            return

        x_names = [ex, exp, exn]
        y_names = [ey, eyp, eyn]
        if d.get("activate_second_system", False):
            try:
                ex2, exn2, exp2, ey2, eyn2, eyp2 = (
                    self._etabs.get_second_system_seismic(d)
                )
                x_names.extend([ex2, exp2, exn2])
                y_names.extend([ey2, eyp2, eyn2])
            except Exception:
                pass

        self._fill_list(self.ui.x_loadcase_list, x_names)
        self._fill_list(self.ui.y_loadcase_list, y_names)

    @staticmethod
    def _fill_list(lw, names: list[str]):
        """Add checkable items to a QListWidget."""
        lw.clear()
        lw.addItems([n for n in names if n])
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)

    # ── run ─────────────────────────────────────────────────────────

    def _run(self):
        loadcases = []
        for lw in (self.ui.x_loadcase_list, self.ui.y_loadcase_list):
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    loadcases.append(item.text())

        if not loadcases:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Load Cases",
                                "Please select at least one load case.")
            return

        try:
            df = self._etabs.get_diaphragm_max_over_avg_drifts(
                loadcases=loadcases
            )
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Torsion Irregularity",
            ok=True,
            dataframe=df,
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
