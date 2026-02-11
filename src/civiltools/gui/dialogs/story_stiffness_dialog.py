"""
Story stiffness dialogs — compute and display story stiffness data.

Ported from civilTools/py_widget/get_siffness_story_way.py and show_siffness_story_way.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class StoryStiffnessDialog(QDialog):
    """Compute story stiffness from ETABS and cache results."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "get_siffness_story_way.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Story Stiffness")
        self.resize(self.ui.size())
        set_dialog_icon(self, "stiffness.svg")

        run_btn = getattr(self.ui, "run", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        # Determine method from radio buttons
        way = "force"
        rb_2800 = getattr(self.ui, "radio_button_2800", None)
        rb_eq = getattr(self.ui, "radio_button_earthquake", None)
        rb_modal = getattr(self.ui, "radio_button_modal", None)
        if rb_2800 and rb_2800.isChecked():
            way = "2800"
        elif rb_eq and rb_eq.isChecked():
            way = "earthquake"
        elif rb_modal and rb_modal.isChecked():
            way = "modal"

        try:
            df = self._etabs.get_story_stiffness_table(way=way)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        # Cache to JSON
        try:
            json_name = f"StoryStiffness {self._etabs.get_file_name_without_suffix()}"
            self._etabs.save_to_json_in_edb_folder(json_name, df.to_dict())
        except Exception:
            pass

        self._result = CommandResult(
            title="Story Stiffness",
            dataframe=df,
            ok=True,
            summary=f"Story stiffness computed via {way} method.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result


class ShowStoryStiffnessDialog(QDialog):
    """Load cached story stiffness results from JSON."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "show_siffness_story_way.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Show Story Stiffness")
        self.resize(self.ui.size())
        set_dialog_icon(self, "show_stiffness.svg")

        run_btn = getattr(self.ui, "run", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _run(self):
        import pandas as pd
        try:
            json_name = f"StoryStiffness {self._etabs.get_file_name_without_suffix()}"
            data = self._etabs.load_from_json_in_edb_folder(json_name)
            df = pd.DataFrame(data)
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"No cached stiffness data:\n{exc}")
            return

        self._result = CommandResult(
            title="Story Stiffness (Cached)",
            dataframe=df,
            ok=True,
            summary="Loaded from cached analysis.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
