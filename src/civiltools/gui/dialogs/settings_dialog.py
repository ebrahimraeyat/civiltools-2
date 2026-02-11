"""
Project Settings dialog — 5-tab dialog for all civilTools seismic parameters.

Ported from civilTools/py_widget/settings.py with improvements:
- PySide6, no FreeCAD dependency
- Uses getattr/setattr (via config module) instead of exec()
- Cleaner signal/slot wiring
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

from civiltools.etabs import config
from civiltools.db import ostanha
from civiltools.gui.models.treeview_system import (
    load_system_nodes, setup_system_treeview,
)
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class SettingsDialog(QDialog):
    """Full project settings — 5 tabs: Systems, Loads, Dynamic, Irregularity."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "edit" / "civiltools_project_settings.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Project Settings")
        self.resize(900, 700)
        set_dialog_icon(self, "settings.svg")

        self._setup_treeviews()
        self._create_connections()
        self._load_config()
        self._fix_dark_mode_combos()

    # ── setup ───────────────────────────────────────────────────────

    def _fix_dark_mode_combos(self):
        """Ensure combo boxes remain readable in dark mode."""
        for name in ("top_story_for_height", "top_story_for_height1",
                      "bot_x_combo", "top_x_combo",
                      "bot_x1_combo", "top_x1_combo"):
            w = getattr(self.ui, name, None)
            if w is not None:
                w.setStyleSheet(
                    "QComboBox { color: palette(text); "
                    "background-color: palette(base); }"
                    "QComboBox:disabled { color: palette(dark); }"
                )

    def _setup_treeviews(self):
        nodes = load_system_nodes()
        for view_name in ("x_treeview", "y_treeview", "x_treeview_1", "y_treeview_1"):
            view = getattr(self.ui, view_name, None)
            if view is not None:
                setup_system_treeview(view, nodes)

    def _create_connections(self):
        ui = self.ui
        # Province → city cascade
        ostan = getattr(ui, "ostan", None)
        if ostan:
            ostan.currentIndexChanged.connect(self._set_cities_of_current_ostan)
        city = getattr(ui, "city", None)
        if city:
            city.currentIndexChanged.connect(self._on_city_changed)

        # Save / Cancel
        save_btn = (getattr(ui, "save_pushbutton", None)
                    or getattr(ui, "save", None)
                    or getattr(ui, "buttonBox", None))
        if save_btn is not None:
            if hasattr(save_btn, "clicked"):
                save_btn.clicked.connect(self._save_and_accept)
            elif hasattr(save_btn, "accepted"):
                save_btn.accepted.connect(self._save_and_accept)
                save_btn.rejected.connect(self.reject)

        cancel_btn = (getattr(ui, "cancel_pushbutton", None)
                      or getattr(ui, "cancel", None))
        if cancel_btn is not None:
            cancel_btn.clicked.connect(self.reject)

        # Second system toggle
        act = getattr(ui, "activate_second_system", None)
        if act:
            act.clicked.connect(self._second_system_clicked)

        # Height recalculation
        for name in ("bot_x_combo", "top_x_combo",
                      "top_story_for_height", "top_story_for_height_checkbox"):
            w = getattr(ui, name, None)
            if w is None:
                continue
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._fill_heights)
            elif hasattr(w, "clicked"):
                w.clicked.connect(self._fill_heights)

        # Partition checkboxes
        pdc = getattr(ui, "partition_dead_checkbox", None)
        if pdc:
            pdc.clicked.connect(self._partition_dead_toggled)

    def _load_config(self):
        config.load(self._etabs, self.ui)

    # ── city cascade ────────────────────────────────────────────────

    def _set_cities_of_current_ostan(self):
        ostan_name = self.ui.ostan.currentText()
        cities = list(ostanha.ostans.get(ostan_name, {}).keys())
        self.ui.city.blockSignals(True)
        self.ui.city.clear()
        self.ui.city.addItems(cities)
        self.ui.city.blockSignals(False)
        if cities:
            self._on_city_changed()

    def _on_city_changed(self):
        config.setA(self.ui, config.get_settings_from_etabs(self._etabs))

    # ── second system ───────────────────────────────────────────────

    def _second_system_clicked(self, checked: bool):
        ui = self.ui
        for name in (
            "x_system_label", "y_system_label",
            "x_treeview_1", "y_treeview_1",
            "stories_for_apply_earthquake_groupox",
            "stories_for_height_groupox",
            "infill_1", "second_earthquake_properties",
            "second_earthquake_properties_drifts", "special_case",
        ):
            w = getattr(ui, name, None)
            if w is not None:
                w.setEnabled(checked)

        ck = getattr(ui, "top_story_for_height_checkbox", None)
        if ck:
            ck.setEnabled(not checked)
            ck.setChecked(not checked)
        th = getattr(ui, "top_story_for_height", None)
        if th:
            th.setEnabled(not checked)

    # ── heights ─────────────────────────────────────────────────────

    def _fill_heights(self):
        config.fill_height_and_no_of_stories(self._etabs, self.ui)
        config.check_heights(self._etabs, self.ui)

    # ── partition ───────────────────────────────────────────────────

    def _partition_dead_toggled(self, checked):
        pd_combo = getattr(self.ui, "partition_dead_combobox", None)
        pl_cb = getattr(self.ui, "partition_live_checkbox", None)
        pl_combo = getattr(self.ui, "partition_live_combobox", None)
        if pd_combo:
            pd_combo.setEnabled(checked)
        if pl_cb:
            pl_cb.setChecked(not checked)
        if pl_combo:
            pl_combo.setEnabled(not checked)

    # ── save ────────────────────────────────────────────────────────

    def _save_and_accept(self):
        try:
            config.save(self._etabs, self.ui)
            self._result = CommandResult(title="Settings", ok=True,
                                         summary="Settings saved to ETABS.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    @property
    def result(self) -> CommandResult | None:
        return self._result
