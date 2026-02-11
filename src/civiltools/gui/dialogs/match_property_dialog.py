"""
Match property dialog — copy section assignment from one frame to another.

Ported from civilTools/py_widget/tools/match_property.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class MatchPropertyDialog(QDialog):
    """Copy frame section assignment from source to target frames."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "tools" / "match_property.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Match Property")
        self.resize(self.ui.size())
        set_dialog_icon(self, "match_property.svg")

        self._create_connections()

    def _create_connections(self):
        done_btn = getattr(self.ui, "done_pushbutton", None)
        if done_btn:
            done_btn.clicked.connect(self._apply)
        cancel_btn = getattr(self.ui, "cancel_pushbutton", None)
        if cancel_btn:
            cancel_btn.clicked.connect(self.reject)

    def _apply(self):
        try:
            # Get source from currently selected frame in ETABS
            names = self._etabs.select_obj.get_selected_obj_type(2)
            if not names:
                QMessageBox.warning(self, "No Selection", "Select frames in ETABS first.")
                return

            fsec_cb = getattr(self.ui, "frame_section", None)
            if fsec_cb and fsec_cb.isChecked():
                # Copy section from first selected to rest
                source = names[0]
                section = self._etabs.frame_obj.get_section_name(source)
                targets = names[1:]
                if not targets:
                    QMessageBox.warning(self, "Need More",
                                        "Select source + target frames (first = source).")
                    return
                for name in targets:
                    self._etabs.frame_obj.set_section_name(name, section)
                summary = f"Applied '{section}' to {len(targets)} frames."
            else:
                summary = "No property type selected."

        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Match Property",
            ok=True,
            summary=summary,
        )
        QMessageBox.information(self, "Done", summary)
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
