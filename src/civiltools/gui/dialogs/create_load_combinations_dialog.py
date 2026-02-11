"""
Create load combinations dialog — generate seismic load combos per Iranian code.

Ported from civilTools/py_widget/define/create_load_combinations.py.
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


class CreateLoadCombinationsDialog(QDialog):
    """Generate concrete/steel load combinations and apply to ETABS."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "define" / "create_load_combinations.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Create Load Combinations")
        self.resize(self.ui.size())
        set_dialog_icon(self, "load_combination.svg")

        self._d = get_settings_from_etabs(self._etabs)
        self._populate()
        self._create_connections()

    def _populate(self):
        d = self._d
        # Load pattern combos
        try:
            lp = self._etabs.load_patterns.get_load_patterns()
        except Exception:
            lp = []
        for name in ("dead_combobox", "sdead_combobox", "live_combobox",
                      "lred_combobox", "live_parking_combobox", "lroof_combobox",
                      "live5_combobox", "lred5_combobox", "snow_combobox",
                      "ev_combobox", "mass_combobox",
                      "partition_dead_combobox", "partition_live_combobox"):
            combo = getattr(self.ui, name, None)
            if combo:
                combo.clear()
                combo.addItems(lp)
                if name in d:
                    idx = combo.findText(d[name])
                    if idx >= 0:
                        combo.setCurrentIndex(idx)

        # Seismic combos
        from civiltools.etabs import config
        config._fill_seismic_combos(self._etabs, self.ui, d, drift=False)

        # Importance factor
        imp = getattr(self.ui, "importance_factor", None)
        if imp:
            if imp.count() == 0:
                imp.addItems(["1.4", "1.2", "1.0"])
            if "importance_factor" in d:
                idx = imp.findText(d["importance_factor"])
                if idx >= 0:
                    imp.setCurrentIndex(idx)

    def _create_connections(self):
        run_btn = getattr(self.ui, "create_button", None)
        if run_btn:
            run_btn.clicked.connect(self._run)
        export_btn = getattr(self.ui, "export_to_etabs_button", None)
        if export_btn:
            export_btn.clicked.connect(self._run)

    def _run(self):
        try:
            # Determine combo type (LRFD or ASD)
            lrfd_rb = getattr(self.ui, "lrfd", None)
            type_ = "Concrete" if (lrfd_rb and lrfd_rb.isChecked()) else "Steel"

            # Get equal / direction separation options
            equal = False
            eq_cb = getattr(self.ui, "equal_checkbox", None)
            if eq_cb:
                equal = eq_cb.isChecked()

            separate = False
            sep_cb = getattr(self.ui, "separate_direction", None)
            if sep_cb:
                separate = sep_cb.isChecked()

            prefix = ""
            prefix_edit = getattr(self.ui, "prefix", None)
            if prefix_edit:
                prefix = prefix_edit.text()

            rho_x = getattr(self.ui, "rhox_combobox", None)
            rho_y = getattr(self.ui, "rhoy_combobox", None)

            self._etabs.load_combinations.generate_concrete_load_combinations(
                type_=type_,
                prefix=prefix,
                equal=equal,
                separate_direction=separate,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._result = CommandResult(
            title="Load Combinations",
            ok=True,
            summary=f"Generated {type_} load combinations.",
        )
        QMessageBox.information(self, "Done",
                                f"{type_} load combinations created in ETABS.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
