"""
Wall load on frames dialog — assign gravity loads to beams from wall loads.

Ported from civilTools/py_widget/assign/wall_load_on_frames.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.etabs.config import get_settings_from_etabs
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class WallLoadDialog(QDialog):
    """Assign gravity wall loads to self and above beams."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "assign" / "wall_load_on_frames.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Wall Load on Frames")
        self.resize(self.ui.size())
        set_dialog_icon(self, "wall_load.svg")

        self._populate()
        run_btn = getattr(self.ui, "assign_button", None)
        if run_btn:
            run_btn.clicked.connect(self._run)
        cancel_btn = getattr(self.ui, "cancel_button", None)
        if cancel_btn:
            cancel_btn.clicked.connect(self.reject)

    def _populate(self):
        d = get_settings_from_etabs(self._etabs)
        # Fill load pattern combo
        try:
            lp = self._etabs.load_patterns.get_load_patterns()
        except Exception:
            lp = []
        combo = getattr(self.ui, "loadpat", None)
        if combo:
            combo.clear()
            combo.addItems(lp)

        # Fill stories
        stories_w = getattr(self.ui, "stories", None)
        if stories_w:
            try:
                stories = self._etabs.story.get_sorted_story_name(
                    reverse=False, include_base=False)
                stories_w.clear()
                stories_w.addItems(stories)
            except Exception:
                pass

    def _run(self):
        loadpat = getattr(self.ui, "loadpat", None)
        lp_name = loadpat.currentText() if loadpat else "Dead"

        # Wall parameters from .ui widgets
        mass_sp = getattr(self.ui, "mass", None)
        mass = mass_sp.value() if mass_sp else 0.22

        user_h = getattr(self.ui, "user_height", None)
        height = user_h.value() if user_h else 3.2

        opening = getattr(self.ui, "opening_ratio", None)
        opening_ratio = opening.value() if opening else 0.0

        try:
            self._etabs.frame_obj.assign_gravity_load_to_selfs_and_above_beams(
                loadpat=lp_name,
                mass=mass,
                height=height,
                opening_ratio=opening_ratio,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Wall Load",
            ok=True,
            summary="Wall loads assigned to beams.",
        )
        QMessageBox.information(self, "Done", "Wall loads applied to frames.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
