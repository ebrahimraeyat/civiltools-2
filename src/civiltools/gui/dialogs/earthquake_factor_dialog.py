"""
Earthquake factor dialog — seismic coefficient calculation and ETABS application.

Ported from civilTools/py_widget/earthquake_factor.py.
Loads earthquake_factor.ui, computes Building → C-factors, applies to ETABS.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QFileDialog

from civiltools.etabs import config
from civiltools.db import ostanha
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon
from civiltools.gui.icons import icon as load_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class EarthquakeFactorDialog(QDialog):
    """Calculate and apply seismic coefficients (C, K) to ETABS load patterns."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._building = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "earthquake_factor.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Earthquake Factor")
        self.resize(self.ui.size())
        set_dialog_icon(self, "cfactor.svg")

        self._load_config()
        self._setup_button_icons()
        self._create_connections()
        self._calculate()

    def _setup_button_icons(self):
        """Set button icons from the filesystem (UI uses Qt resource paths that aren't registered)."""
        icon_map = {
            "calculate": "run.svg",
            "apply_to_etabs": "etabs.png",
            "export_to_word": "word.svg",
        }
        for btn_name, icon_name in icon_map.items():
            btn = getattr(self.ui, btn_name, None)
            if btn is not None:
                qicon = load_icon(icon_name)
                if not qicon.isNull():
                    btn.setIcon(qicon)

    def _load_config(self):
        config.load(self._etabs, self.ui)

    def _create_connections(self):
        ui = self.ui
        ostan = getattr(ui, "ostan", None)
        if ostan:
            ostan.currentIndexChanged.connect(self._set_cities)
        city = getattr(ui, "city", None)
        if city:
            city.currentIndexChanged.connect(self._on_city_changed)

        for name in ("bot_x_combo", "top_x_combo",
                      "top_story_for_height", "top_story_for_height_checkbox"):
            w = getattr(ui, name, None)
            if w and hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._fill_heights)
            elif w and hasattr(w, "clicked"):
                w.clicked.connect(self._fill_heights)

        calc_btn = getattr(ui, "calculate", None)
        if calc_btn:
            calc_btn.clicked.connect(self._calculate)

        apply_btn = getattr(ui, "apply_to_etabs", None)
        if apply_btn:
            apply_btn.clicked.connect(self._apply_to_etabs)

        export_btn = getattr(ui, "export_to_word", None)
        if export_btn:
            export_btn.clicked.connect(self._export_to_word)

        act = getattr(ui, "activate_second_system", None)
        if act:
            act.clicked.connect(self._second_system_clicked)

    def _set_cities(self):
        ostan_name = self.ui.ostan.currentText()
        cities = list(ostanha.ostans.get(ostan_name, {}).keys())
        self.ui.city.blockSignals(True)
        self.ui.city.clear()
        self.ui.city.addItems(cities)
        self.ui.city.blockSignals(False)

    def _on_city_changed(self):
        config.setA(self.ui, config.get_settings_from_etabs(self._etabs))

    def _fill_heights(self):
        config.fill_height_and_no_of_stories(self._etabs, self.ui)
        config.check_heights(self._etabs, self.ui)

    def _second_system_clicked(self, checked: bool):
        for name in ("x_system_label", "y_system_label", "x_treeview_1",
                      "y_treeview_1", "stories_for_apply_earthquake_groupox",
                      "stories_for_height_groupox", "infill_1",
                      "second_earthquake_properties", "special_case"):
            w = getattr(self.ui, name, None)
            if w:
                w.setEnabled(checked)
        ck = getattr(self.ui, "top_story_for_height_checkbox", None)
        if ck:
            ck.setEnabled(not checked)
            ck.setChecked(not checked)

    def _update_structure_table(self):
        """Populate the structure_properties_table with the Building model."""
        table = getattr(self.ui, "structure_properties_table", None)
        if table is None or self._building is None:
            return
        from civiltools.gui.table_models import StructureModel
        model = StructureModel(self._building)
        table.setModel(model)
        # Keep a reference to prevent garbage collection
        self._structure_model = model

    def _calculate(self):
        self._building = config.current_building_from_widget(self.ui)
        if not self._building:
            return
        results = self._building.results
        if results[0] is False:
            title, err, direction = results[1:]
            QMessageBox.critical(self, title % direction, str(err))

        # Populate structure properties table
        self._update_structure_table()

    def _apply_to_etabs(self):
        self._calculate()
        if not self._building:
            return
        d = config.save(self._etabs, self.ui)

        # Analytical period check
        bld = self._building
        msg_tpl = "Analytical Period in %s direction < 1.25 × Experimental.\nContinue?"
        if bld.tx_an < 1.25 * bld.tx_exp:
            if QMessageBox.question(self, "X Period", msg_tpl % "X") == QMessageBox.No:
                return
        if bld.ty_an < 1.25 * bld.ty_exp:
            if QMessageBox.question(self, "Y Period", msg_tpl % "Y") == QMessageBox.No:
                return

        data = config.get_data_for_apply_earthquakes(bld, etabs=self._etabs, d=d)
        if data is None:
            QMessageBox.warning(self, "Not Supported",
                                "Cannot apply earthquake for your system configuration.")
            return

        ret = self._etabs.apply_cfactors_to_edb(data, d=d)
        if ret == 1:
            QMessageBox.warning(self, "Error",
                                "Could not write to ETABS.\nTry running analysis first.")
            return

        # Build result DataFrame
        import pandas as pd
        rows = []
        for names, props in data:
            for n in names:
                rows.append({"LoadPattern": n, "Top": props[0], "Bot": props[1],
                             "C": props[2], "K": props[3]})
        df = pd.DataFrame(rows)

        self._result = CommandResult(
            title="Earthquake Factor",
            dataframe=df,
            ok=True,
            summary="Seismic coefficients applied to ETABS.",
        )
        QMessageBox.information(self, "Done", "Successfully written to ETABS.")
        self.accept()

    def _export_to_word(self):
        if not self._building:
            self._calculate()
        if not self._building:
            return
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export to Word", directory, "Word (*.docx)")
        if not filename:
            return
        if not filename.endswith(".docx"):
            filename += ".docx"
        try:
            from civiltools.report.export_to_word import export
            export(self._building, filename)
            QMessageBox.information(self, "Done", f"Exported to {filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    @property
    def result(self) -> CommandResult | None:
        return self._result
