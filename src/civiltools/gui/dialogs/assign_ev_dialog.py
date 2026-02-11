"""
Assign Ev (vertical earthquake) dialog.

Ported from civilTools/py_widget/assign/assign_ev.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class AssignEvDialog(QDialog):
    """Assign vertical earthquake component (Ev) to frames."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "assign" / "assign_ev.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Assign Ev")
        self.resize(self.ui.size())
        set_dialog_icon(self, "assign_ev.svg")

        self._populate()
        run_btn = getattr(self.ui, "export_to_etabs_button", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _populate(self):
        from civiltools.etabs.config import get_settings_from_etabs
        d = get_settings_from_etabs(self._etabs)
        ev_combo = getattr(self.ui, "ev_combobox", None)
        if ev_combo:
            try:
                lp = self._etabs.load_patterns.get_load_patterns()
                ev_combo.clear()
                ev_combo.addItems(lp)
                if "ev_combobox" in d:
                    idx = ev_combo.findText(d["ev_combobox"])
                    if idx >= 0:
                        ev_combo.setCurrentIndex(idx)
            except Exception:
                pass

    def _run(self):
        ev_combo = getattr(self.ui, "ev_combobox", None)
        ev_name = ev_combo.currentText() if ev_combo else "Ev"

        try:
            self._etabs.frame_obj.assign_ev(ev_name)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Assign Ev",
            ok=True,
            summary=f"Ev ({ev_name}) assigned to frames.",
        )
        QMessageBox.information(self, "Done", f"Ev ({ev_name}) assigned.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
