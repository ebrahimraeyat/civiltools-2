"""
Earthquake factor dialog — seismic coefficient calculation and ETABS application.

Ported from civilTools/py_widget/earthquake_factor.py.
Loads earthquake_factor.ui, computes Building → C-factors, applies to ETABS.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import QFile, Qt, QAbstractTableModel, QModelIndex, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QFileDialog,
    QLabel, QTableView, QAbstractItemView, QHeaderView, QFrame, QSizePolicy,
)

from civiltools.etabs import config
from civiltools.db import ostanha
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon
from civiltools.gui.icons import icon as load_icon
from civiltools.gui.busy_dialog import BusyDialog

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# ── ETABS C-factor table model ─────────────────────────────────────────────

_MAIN_BG  = QColor("#e8f5e9")   # light green for main earthquake rows
_DRIFT_BG = QColor("#e3f2fd")   # light blue for drift rows
_SEP_BG   = QColor("#b0bec5")   # grey separator row
_HEADERS  = ["Load Pattern", "C", "K", "Top Story", "Bot Story"]


class EtabsCFactorModel(QAbstractTableModel):
    """Displays ETABS seismic load patterns with their C / K coefficients.

    Rows are ordered: main earthquakes first (green), then drift (blue).
    A grey separator row is inserted between the two groups.
    """

    def __init__(self, main_rows: list[tuple], drift_rows: list[tuple], parent=None):
        """
        Parameters
        ----------
        main_rows, drift_rows :
            Each item is a tuple (name, c, k, top_story, bot_story).
        """
        super().__init__(parent)
        self._rows: list = []
        self.set_rows(main_rows, drift_rows)

    def set_rows(self, main_rows: list[tuple], drift_rows: list[tuple]):
        """Update model rows in-place without recreating the model/view."""
        rows: list = []
        for r in main_rows:
            rows.append((r, False))
        if main_rows and drift_rows:
            rows.append((None, False))   # separator
        for r in drift_rows:
            rows.append((r, True))
        # Reset model with new rows
        self.beginResetModel()
        self._rows = rows
        print(f"Model updated with {len(main_rows)} main rows and {len(drift_rows)} drift rows.")
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row_data, is_drift = self._rows[index.row()]

        if role == Qt.BackgroundRole:
            if row_data is None:
                return _SEP_BG
            return _DRIFT_BG if is_drift else _MAIN_BG

        if role == Qt.FontRole and row_data is None:
            f = QFont()
            f.setBold(True)
            return f

        if role == Qt.DisplayRole:
            if row_data is None:
                if index.column() == 0:
                    return "── Drift ──────────────────────────────"
                return ""
            return str(row_data[index.column()])

        if role == Qt.TextAlignmentRole:
            if index.column() == 0:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignCenter)

        return None


class EarthquakeFactorDialog(QDialog):
    """Calculate and apply seismic coefficients (C, K) to ETABS load patterns."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._building = None
        self._structure_model = None
        self._cfactor_model: EtabsCFactorModel | None = None
        self._main_rows: list[tuple] = []
        self._drift_rows: list[tuple] = []
        self._main_splitter = None
        self._top_splitter = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "earthquake_factor.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        # Main dialog layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        self._main_layout.addWidget(self.ui)

        # Status bar label at the very bottom
        self._status_label = QLabel("")
        self._status_label.setContentsMargins(8, 2, 8, 2)
        self._status_label.setFixedHeight(24)
        self._status_label.setStyleSheet(
            "QLabel { background: #f5f5f5; border-top: 1px solid #bdbdbd; "
            "color: #2e7d32; font-size: 11px; }"
        )
        self._main_layout.addWidget(self._status_label)

        self.setWindowTitle("Earthquake Factor")
        self.resize(self.ui.size())
        set_dialog_icon(self, "cfactor.svg")

        self._load_config()
        self._setup_button_icons()
        self._rearrange_results_tab()    # ← move tables
        self._create_connections()
        self._load_etabs_cfactors()   # 1. Load existing patterns from ETABS
        self._calculate()             # 2. Calculate and update them with new C-factors
        self._restore_state()         # ← Restore sizes after everything is initialized

    def _restore_state(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("CivilTools", "EarthquakeFactorDialog")
        if settings.contains("geometry"):
            self.restoreGeometry(settings.value("geometry"))
        if self._main_splitter and settings.contains("main_splitter"):
            self._main_splitter.restoreState(settings.value("main_splitter"))
        if self._top_splitter and settings.contains("top_splitter"):
            self._top_splitter.restoreState(settings.value("top_splitter"))

    def closeEvent(self, event):
        from PySide6.QtCore import QSettings
        settings = QSettings("CivilTools", "EarthquakeFactorDialog")
        settings.setValue("geometry", self.saveGeometry())
        if self._main_splitter:
            settings.setValue("main_splitter", self._main_splitter.saveState())
        if self._top_splitter:
            settings.setValue("top_splitter", self._top_splitter.saveState())
        super().closeEvent(event)

    def _rearrange_results_tab(self):
        """Rearrange Results tab: top for main inputs/struct table, bottom full width for C-factors."""
        tab_3 = getattr(self.ui, "tab_3", None)
        struct_table = getattr(self.ui, "structure_properties_table", None)
        layout_widget = getattr(self.ui, "layoutWidget", None)
        layout_widget_2 = getattr(self.ui, "layoutWidget_2", None)
        old_splitter = getattr(self.ui, "splitter", None)

        if not all([tab_3, struct_table, layout_widget, layout_widget_2, old_splitter]):
            self._cfactor_view = None
            return

        # Hide old splitter to remove it from layout hierarchy
        old_splitter.setParent(None)

        # Clear tab_3 layout cleanly
        if tab_3.layout():
            from PySide6.QtWidgets import QWidget
            QWidget().setLayout(tab_3.layout())

        from PySide6.QtWidgets import QSplitter, QVBoxLayout, QHBoxLayout, QWidget

        # Main layout of the tab is now VBox because we want a vertical splitter
        main_layout = QVBoxLayout(tab_3)
        main_layout.setContentsMargins(4, 4, 4, 4)

        main_splitter = QSplitter(Qt.Vertical)  # Arranges widgets top-to-bottom
        self._main_splitter = main_splitter
        main_layout.addWidget(main_splitter)

        # ── Top Pane: Inputs (Left) and Struct Table (Right) ──
        top_pane = QWidget()
        top_layout = QHBoxLayout(top_pane)
        top_layout.setContentsMargins(0, 0, 0, 0)

        top_splitter = QSplitter(Qt.Horizontal)
        self._top_splitter = top_splitter
        top_layout.addWidget(top_splitter)

        # Top Left: Inputs and Spectral
        left_pane = QWidget()
        left_vbox = QVBoxLayout(left_pane)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.addWidget(layout_widget)
        left_vbox.addWidget(layout_widget_2)
        left_vbox.addStretch(1)
        top_splitter.addWidget(left_pane)

        # Top Right: Structure Properties Table
        right_pane = QWidget()
        right_vbox = QVBoxLayout(right_pane)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(4)
        lbl_calc = QLabel("📊  Calculated Coefficients")
        lbl_calc.setStyleSheet("font-weight: bold; font-size: 12px;")
        lbl_calc.setAlignment(Qt.AlignCenter)
        right_vbox.addWidget(lbl_calc)
        struct_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_vbox.addWidget(struct_table, stretch=1)
        right_vbox.addStretch(0)
        top_splitter.addWidget(right_pane)

        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 1)

        main_splitter.addWidget(top_pane)

        # ── Bottom Pane: C-Factor View (Full Width) ──
        bottom_pane = QWidget()
        bot_vbox = QVBoxLayout(bottom_pane)
        bot_vbox.setContentsMargins(0, 0, 0, 0)
        bot_vbox.setSpacing(4)

        lbl_etabs = QLabel("🏗  Load Pattern Coefficients")
        lbl_etabs.setStyleSheet("font-weight: bold; font-size: 12px;")
        lbl_etabs.setFixedHeight(20)
        lbl_etabs.setAlignment(Qt.AlignCenter)
        bot_vbox.addWidget(lbl_etabs)

        self._cfactor_view = QTableView()
        self._cfactor_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._cfactor_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._cfactor_view.setAlternatingRowColors(False)
        self._cfactor_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._cfactor_view.horizontalHeader().setStretchLastSection(True)
        self._cfactor_view.verticalHeader().setVisible(False)
        self._cfactor_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cfactor_view.setMinimumHeight(100)
        bot_vbox.addWidget(self._cfactor_view, stretch=1)

        main_splitter.addWidget(bottom_pane)

        # Stretch factors for the vertical splitter
        # We give stretch factor 0 to the top pane to prevent it from growing too tall.
        # We give stretch factor 1 to the bottom pane so the C-factor table takes up remaining/extra space.
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        # Initialize reasonable default sizes before user resizing loads:
        main_splitter.setSizes([350, 400])

    def _load_etabs_cfactors(self):
        """Read current C / K values from ETABS and populate _cfactor_view."""
        if self._cfactor_view is None:
            return
        try:
            self._etabs.load_patterns.select_all_load_patterns()
            table_key = "Load Pattern Definitions - Auto Seismic - User Coefficient"
            df = self._etabs.database.read(table_key, to_dataframe=True)
            if df is None or df.empty:
                self._main_rows = []
                self._drift_rows = []
                self._set_cfactor_rows()
                return

            # Keep only patterns with a non-empty C value
            df = df[df["C"].astype(str).str.strip() != ""]
            if df.empty:
                self._main_rows = []
                self._drift_rows = []
                self._set_cfactor_rows()
                return

            drift_names = set(
                self._etabs.load_patterns.get_drift_load_pattern_names()
            )

            cols_needed = ["Name", "C", "K", "TopStory", "BotStory"]
            col_map = {"Top Story": "TopStory", "Bottom Story": "BotStory"}
            df.rename(columns=col_map, inplace=True)
            for c in cols_needed:
                if c not in df.columns:
                    df[c] = ""

            main_rows = []
            drift_rows = []
            for _, row in df.iterrows():
                name = str(row["Name"])
                item = (name, row["C"], row["K"], row.get("TopStory", ""), row.get("BotStory", ""))
                if name in drift_names:
                    drift_rows.append(item)
                else:
                    main_rows.append(item)

            self._main_rows = main_rows
            self._drift_rows = drift_rows
            self._set_cfactor_rows()
        except Exception:
            pass

    def _set_cfactor_rows(self):
        """Reuse existing model and refresh with stored rows."""
        if self._cfactor_view is None:
            return
        if self._cfactor_model is None:
            self._cfactor_model = EtabsCFactorModel(self._main_rows, self._drift_rows, self._cfactor_view)
            self._cfactor_view.setModel(self._cfactor_model)
            return
        print("Updating C-factor model with new rows...")
        self._cfactor_model.set_rows(self._main_rows, self._drift_rows)

    def _load_calculated_cfactors(self):
        """Populate _cfactor_view with the CALCULATED C/K from the Building model."""
        if self._cfactor_view is None or self._building is None:
            return
        try:
            d = config.save(self._etabs, self.ui)
            data = config.get_data_for_apply_earthquakes(
                self._building, etabs=self._etabs, d=d, widget=self.ui,
            )
            data2 = config.get_data_for_apply_earthquakes_drift(
                self._building, etabs=self._etabs, d=d, widget=self.ui,
            )
            if data is None:
                data = []
            if data2 is None:
                data2 = []
            data.extend(data2)
            if not data:
                self._main_rows = []
                self._drift_rows = []
                self._set_cfactor_rows()
                return

            drift_names = set(
                self._etabs.load_patterns.get_drift_load_pattern_names()
            )

            main_rows = []
            drift_rows = []
            for names, props in data:
                top, bot, c_val, k_val = props[0], props[1], props[2], props[3]
                for n in names:
                    item = (n, f"{float(c_val):.4f}", f"{float(k_val):.3f}", top, bot)
                    if n in drift_names:
                        drift_rows.append(item)
                    else:
                        main_rows.append(item)

            self._main_rows = main_rows
            self._drift_rows = drift_rows
            self._set_cfactor_rows()
        except Exception:
            pass

    def _set_status(self, message: str, color: str = "#2e7d32"):
        """Show a status message with a brief colour-flash to grab attention."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._status_label.setText(f"[{ts}]  {message}")
        # Flash: bright highlight → settle to subtle bar
        self._status_label.setStyleSheet(
            f"QLabel {{ background: {color}; border-top: 1px solid #bdbdbd; "
            f"color: #ffffff; font-size: 11px; font-weight: bold; }}"
        )
        QTimer.singleShot(900, lambda: self._status_label.setStyleSheet(
            f"QLabel {{ background: #f5f5f5; border-top: 1px solid #bdbdbd; "
            f"color: {color}; font-size: 11px; }}"
        ))

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
        if self._structure_model is None:
            self._structure_model = StructureModel(self._building)
            table.setModel(self._structure_model)
            return
        self._structure_model.set_rows(self._building)

    def _calculate(self):
        self._building = config.current_building_from_widget(self.ui)
        if not self._building:
            return
        results = self._building.results
        if results[0] is False:
            title, err, direction = results[1:]
            QMessageBox.critical(self, title % direction, str(err))

        # Populate structure properties (calculated coefficients) table
        self._update_structure_table()
        # Update the ETABS C-factor view with calculated coefficients
        self._load_calculated_cfactors()
        self._set_status("✔  ضرایب زلزله محاسبه شد — برای اجرا دکمه Apply را بزنید.", "#1565c0")

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

        with BusyDialog(
            "Applying Earthquake Factor",
            status_text="Applying seismic coefficients to ETABS…",
            parent=self,
            disable_widgets=[self.ui],
        ):
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
        self._set_status("✔  Seismic coefficients written to ETABS successfully.", "#2e7d32")
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
            with BusyDialog(
                "Exporting to Word",
                status_text="Generating Word document…",
                parent=self,
                disable_widgets=[self.ui],
            ):
                export(self._building, filename)
            ans = QMessageBox.question(
                self,
                "Export Complete",
                f"Exported to:\n{filename}\n\nDo you want to open the file?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ans == QMessageBox.Yes:
                import os
                os.startfile(filename)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    @property
    def result(self) -> CommandResult | None:
        return self._result
