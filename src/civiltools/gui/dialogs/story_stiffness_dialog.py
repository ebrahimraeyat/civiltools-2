"""
Story stiffness dialogs — compute and display story stiffness data.

Ported from civilTools/py_widget/get_siffness_story_way.py and show_siffness_story_way.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"

_METHOD_LABELS = {
    "2800": "2800",
    "modal": "Modal",
    "earthquake": "Earthquake (Ex, Ey)",
    "file": "File",
}


def _method_title(prefix: str, way: str) -> str:
    return f"{prefix} - {_METHOD_LABELS.get(way, way)}"


def _button_checked(ui, name: str) -> bool:
    button = getattr(ui, name, None)
    return bool(button and button.isChecked())


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
        self._connect_method_buttons()
        self._update_window_title()
        self.resize(self.ui.size())
        set_dialog_icon(self, "stiffness.svg")

        run_btn = getattr(self.ui, "run", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _connect_method_buttons(self):
        for name in (
            "radio_button_2800",
            "radio_button_modal",
            "radio_button_earthquake",
        ):
            button = getattr(self.ui, name, None)
            if button:
                button.toggled.connect(self._update_window_title)

    def _selected_way(self) -> str:
        if _button_checked(self.ui, "radio_button_2800"):
            return "2800"
        if _button_checked(self.ui, "radio_button_modal"):
            return "modal"
        return "earthquake"

    def _update_window_title(self):
        self.setWindowTitle(_method_title("Story Stiffness", self._selected_way()))

    def _run(self):
        # Determine method from radio buttons
        way = self._selected_way()

        try:
            rows, headers = self._etabs.get_story_stiffness_table(way=way)
            df = pd.DataFrame(rows, columns=headers)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        # Cache to JSON
        try:
            json_name = f"StoryStiffness {self._etabs.get_file_name_without_suffix()}"
            self._etabs.save_to_json_in_edb_folder(
                json_name,
                {"columns": list(df.columns), "rows": df.values.tolist()},
            )
        except Exception:
            pass

        self._result = CommandResult(
            title=self.windowTitle(),
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
        self._connect_method_buttons()
        self._update_window_title()
        self.resize(self.ui.size())
        set_dialog_icon(self, "show_stiffness.svg")

        run_btn = getattr(self.ui, "run", None)
        if run_btn:
            run_btn.clicked.connect(self._run)

    def _connect_method_buttons(self):
        for name in (
            "radio_button_2800",
            "radio_button_modal",
            "radio_button_earthquake",
            "radio_button_file",
        ):
            button = getattr(self.ui, name, None)
            if button:
                button.toggled.connect(self._update_window_title)

    def _selected_way(self) -> str:
        if _button_checked(self.ui, "radio_button_file"):
            return "file"
        if _button_checked(self.ui, "radio_button_2800"):
            return "2800"
        if _button_checked(self.ui, "radio_button_modal"):
            return "modal"
        return "earthquake"

    def _update_window_title(self):
        self.setWindowTitle(_method_title("Show Story Stiffness", self._selected_way()))

    def _run(self):
        import pandas as pd
        try:
            json_name = f"StoryStiffness {self._etabs.get_file_name_without_suffix()}"
            data = self._etabs.load_from_json_in_edb_folder(json_name)
            if isinstance(data, dict) and {"columns", "rows"} <= data.keys():
                df = pd.DataFrame(data["rows"], columns=data["columns"])
            else:
                df = pd.DataFrame(data)
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"No cached stiffness data:\n{exc}")
            return

        self._result = CommandResult(
            title=self.windowTitle(),
            dataframe=df,
            ok=True,
            summary="Loaded from cached analysis.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
