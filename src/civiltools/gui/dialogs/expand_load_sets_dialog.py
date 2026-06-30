"""
Expand area load sets dialog — ported from
civilTools/py_widget/tools/expand_area_load_sets.py.

Previews the shell *uniform load sets* expanded into individual uniform loads,
then (on Apply) writes them back to the model, replacing the load sets.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QTableView,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.table_models import PandasModel


class ExpandLoadSetsDialog(QDialog):
    """Preview expanded shell uniform load sets and apply them to the model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._df = None

        self.setWindowTitle("Expand Area Load Sets")
        self.resize(640, 600)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Preview of load sets expanded into individual uniform loads.\n"
                "Apply will replace the load sets in the model with these loads."
            )
        )
        self.table = QTableView()
        layout.addWidget(self.table)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        self.apply_btn = bbox.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_btn.clicked.connect(self._apply)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

        self._load()

    def _load(self):
        try:
            df = self._etabs.area.get_expanded_shell_uniform_load_sets()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to read load sets:\n{exc}")
            self.apply_btn.setEnabled(False)
            return
        if df is None or df.empty:
            QMessageBox.warning(
                self, "Empty Load Sets", "There are no load sets in this model."
            )
            self.apply_btn.setEnabled(False)
            return
        self._df = df
        display = df.drop(columns=["Direction"], errors="ignore").reset_index(drop=True)
        self.table.setModel(PandasModel(display))
        self.table.resizeColumnsToContents()

    def _apply(self):
        if self._df is None or self._df.empty:
            return
        try:
            # Pass a copy — the apply method mutates the frame internally.
            ok = self._etabs.area.expand_uniform_load_sets_and_apply_to_model(
                self._df.copy()
            )
        except Exception as exc:
            QMessageBox.critical(self, "Failed", f"Load sets did not expand:\n{exc}")
            return
        if ok:
            self._result = CommandResult(
                title="Expand Load Sets",
                summary=f"Expanded {len(self._df)} load-set rows and applied "
                "uniform loads to the model.",
                ok=True,
            )
            QMessageBox.information(
                self, "Successful", "All load sets expanded successfully."
            )
            self.accept()
        else:
            QMessageBox.warning(self, "Failed", "Load sets did not expand!")

    @property
    def result(self) -> CommandResult | None:
        return self._result
