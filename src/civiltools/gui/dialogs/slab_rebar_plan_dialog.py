"""Slab Rebar Plan Dialog — read ETABS data, preview, and export DXF."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon
from civiltools.gui.busy_dialog import BusyDialog

log = logging.getLogger(__name__)


class SlabRebarPlanDialog(QDialog):
    """Dialog for slab rebar plan generation with cache, preview, and DXF export."""

    def __init__(self, etabs: Any = None, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        
        # State
        self._cache_data: pd.DataFrame | None = None
        self._cache_time: float = 0.0
        self._read_count: int = 0

        self.setWindowTitle("Slab Rebar Plan")
        self.setMinimumSize(900, 700)
        self.resize(1100, 850)
        set_dialog_icon(self, "rebars.svg")

        self._build_ui()
        self._connect_signals()

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        """Build the dialog layout."""
        main_layout = QVBoxLayout(self)

        # ── Tab widget for organizing sections ─────────────────────────────
        tabs = QTabWidget()

        # TAB 1: Read & Filter
        read_filter_w = self._build_read_filter_tab()
        tabs.addTab(read_filter_w, "Read & Filter")

        # TAB 2: Strategy & Settings
        strategy_w = self._build_strategy_tab()
        tabs.addTab(strategy_w, "Strategy & Settings")

        # TAB 3: Preview
        preview_w = self._build_preview_tab()
        tabs.addTab(preview_w, "Preview")

        main_layout.addWidget(tabs, 1)

        # ── Bottom buttons ──────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        self.btn_export = QPushButton("Export to DXF")
        self.btn_export.setEnabled(False)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close")
        btn_layout.addWidget(self.btn_close)
        main_layout.addLayout(btn_layout)

    def _build_read_filter_tab(self) -> QWidget:
        """Build Read & Filter tab."""
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        layout = QVBoxLayout(w)

        # Read section
        read_group = QGroupBox("ETABS Data Source")
        read_lay = QHBoxLayout(read_group)
        self.btn_read = QPushButton("Read from ETABS")
        self.btn_read.setToolTip("Load slab rebar data into cache (once per session)")
        read_lay.addWidget(self.btn_read)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setToolTip("Re-read from ETABS (clear cache and reload)")
        read_lay.addWidget(self.btn_refresh)
        self.lbl_cache_info = QLabel("Cache: not loaded")
        read_lay.addWidget(self.lbl_cache_info)
        read_lay.addStretch()
        layout.addWidget(read_group)

        # Story filter
        story_group = QGroupBox("Story Selection")
        story_lay = QVBoxLayout(story_group)
        self.story_list = QListWidget()
        self.story_list.setMaximumHeight(150)
        story_lay.addWidget(self.story_list)
        layout.addWidget(story_group)

        # Layer & side filter
        filter_group = QGroupBox("Layer & Side Filters")
        filter_lay = QHBoxLayout(filter_group)
        
        # Layers
        self.chk_layer_a = QCheckBox("Layer A")
        self.chk_layer_a.setChecked(True)
        filter_lay.addWidget(self.chk_layer_a)
        
        self.chk_layer_b = QCheckBox("Layer B")
        filter_lay.addWidget(self.chk_layer_b)
        
        self.chk_layer_other = QCheckBox("Layer Other")
        filter_lay.addWidget(self.chk_layer_other)
        
        filter_lay.addSpacing(20)
        
        self.chk_separate_layers = QCheckBox("Separate Layers (one plan per layer)")
        self.chk_separate_layers.setToolTip("When ON: generate separate DXF plans per layer")
        filter_lay.addWidget(self.chk_separate_layers)
        filter_lay.addStretch()
        
        layout.addWidget(filter_group)

        # Top/Bottom
        side_group = QGroupBox("Rebar Location")
        side_lay = QHBoxLayout(side_group)
        self.chk_top = QCheckBox("Top Rebar")
        self.chk_top.setChecked(True)
        side_lay.addWidget(self.chk_top)
        self.chk_bottom = QCheckBox("Bottom Rebar")
        self.chk_bottom.setChecked(True)
        side_lay.addWidget(self.chk_bottom)
        side_lay.addStretch()
        layout.addWidget(side_group)

        layout.addStretch()
        return w

    def _build_strategy_tab(self) -> QWidget:
        """Build Strategy & Settings tab."""
        from PySide6.QtWidgets import QWidget, QScrollArea
        w = QWidget()
        layout = QVBoxLayout(w)

        # Optimizer parameters
        opt_group = QGroupBox("Optimizer Parameters")
        opt_lay = QVBoxLayout(opt_group)

        # Continuous rebar top/bot
        row_cont_top = QHBoxLayout()
        row_cont_top.addWidget(QLabel("Continuous Rebar Top (mm):"))
        self.spin_cont_top = QDoubleSpinBox()
        self.spin_cont_top.setRange(0, 1000)
        self.spin_cont_top.setValue(150)
        row_cont_top.addWidget(self.spin_cont_top)
        row_cont_top.addStretch()
        opt_lay.addLayout(row_cont_top)

        row_cont_bot = QHBoxLayout()
        row_cont_bot.addWidget(QLabel("Continuous Rebar Bottom (mm):"))
        self.spin_cont_bot = QDoubleSpinBox()
        self.spin_cont_bot.setRange(0, 1000)
        self.spin_cont_bot.setValue(300)
        row_cont_bot.addWidget(self.spin_cont_bot)
        row_cont_bot.addStretch()
        opt_lay.addLayout(row_cont_bot)

        # Region threshold
        row_region = QHBoxLayout()
        row_region.addWidget(QLabel("Region Threshold (mm²):"))
        self.spin_region_thr = QDoubleSpinBox()
        self.spin_region_thr.setRange(0, 100000)
        self.spin_region_thr.setValue(0)
        row_region.addWidget(self.spin_region_thr)
        row_region.addStretch()
        opt_lay.addLayout(row_region)

        # Min area threshold
        row_min_area = QHBoxLayout()
        row_min_area.addWidget(QLabel("Min Area Threshold (mm²):"))
        self.spin_min_area = QDoubleSpinBox()
        self.spin_min_area.setRange(0, 100000)
        self.spin_min_area.setValue(0)
        row_min_area.addWidget(self.spin_min_area)
        row_min_area.addStretch()
        opt_lay.addLayout(row_min_area)

        # Extend length
        row_extend = QHBoxLayout()
        row_extend.addWidget(QLabel("Extend Length (mm):"))
        self.spin_extend = QDoubleSpinBox()
        self.spin_extend.setRange(0, 10000)
        self.spin_extend.setValue(0)
        row_extend.addWidget(self.spin_extend)
        row_extend.addStretch()
        opt_lay.addLayout(row_extend)

        # Min bar length
        row_min_bar = QHBoxLayout()
        row_min_bar.addWidget(QLabel("Min Bar Length (mm):"))
        self.spin_min_bar = QDoubleSpinBox()
        self.spin_min_bar.setRange(0, 10000)
        self.spin_min_bar.setValue(0)
        row_min_bar.addWidget(self.spin_min_bar)
        row_min_bar.addStretch()
        opt_lay.addLayout(row_min_bar)

        layout.addWidget(opt_group)
        layout.addStretch()
        return w

    def _build_preview_tab(self) -> QWidget:
        """Build Preview tab."""
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        layout = QVBoxLayout(w)

        # Preview mode selector
        prev_mode_lay = QHBoxLayout()
        prev_mode_lay.addWidget(QLabel("Preview Mode:"))
        self.combo_prev_mode = QComboBox()
        self.combo_prev_mode.addItems(["Fast (cached data)", "Accurate (optimizer output)"])
        prev_mode_lay.addWidget(self.combo_prev_mode)
        self.btn_refresh_preview = QPushButton("Refresh Preview")
        self.btn_refresh_preview.setEnabled(False)
        prev_mode_lay.addWidget(self.btn_refresh_preview)
        prev_mode_lay.addStretch()
        layout.addLayout(prev_mode_lay)

        # Preview table
        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(7)
        self.table_preview.setHorizontalHeaderLabels([
            "Story", "Strip", "Layer", "Side", "Regions", "Total Area (mm²)", "Notes"
        ])
        layout.addWidget(self.table_preview)

        return w

    def _connect_signals(self):
        """Wire up signal slots."""
        self.btn_read.clicked.connect(self._on_read)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_refresh_preview.clicked.connect(self._on_refresh_preview)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_close.clicked.connect(self.reject)

    # ── Slots ───────────────────────────────────────────────────────────────

    def _on_read(self):
        """Read slab rebar data from ETABS into cache."""
        if self._etabs is None or not getattr(self._etabs, "success", False):
            QMessageBox.warning(self, "ETABS", "Not connected to ETABS.")
            return

        def read_task():
            from civiltools.building.slab_rebar_service import SlabRebarService
            service = SlabRebarService(self._etabs)
            return service.read_slab_rebars()

        with BusyDialog("Reading ETABS Data…", "Fetching slab rebar design results…", parent=self) as dlg:
            try:
                self._cache_data = dlg.run(read_task)
                self._read_count += 1
                import time
                self._cache_time = time.time()
                self._update_cache_info()
                self._populate_story_list()
                self.btn_refresh.setEnabled(True)
                self.btn_refresh_preview.setEnabled(True)
                self.btn_export.setEnabled(True)
                QMessageBox.information(self, "Success", f"Loaded {len(self._cache_data)} rebar rows.")
            except Exception as e:
                QMessageBox.critical(self, "Read Error", str(e))

    def _on_refresh(self):
        """Refresh cache from ETABS."""
        self._cache_data = None
        self._on_read()

    def _on_refresh_preview(self):
        """Refresh the preview table."""
        if self._cache_data is None or self._cache_data.empty:
            QMessageBox.warning(self, "Preview", "No cached data. Read from ETABS first.")
            return
        self._populate_preview_table()

    def _on_export(self):
        """Export to DXF."""
        if self._cache_data is None or self._cache_data.empty:
            QMessageBox.warning(self, "Export", "No data to export. Read from ETABS first.")
            return

        # Get selected stories from checkable list
        selected_stories = []
        for i in range(self.story_list.count()):
            item = self.story_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_stories.append(item.text())
        
        if not selected_stories:
            QMessageBox.warning(self, "Export", "No stories selected.")
            return
        
        # Filter cache by selected stories
        filtered_data = self._cache_data[self._cache_data["Story"].isin(selected_stories)]
        
        # Ask user for output path (optional; default to report folder)
        try:
            report_folder = self._etabs.get_new_filename_in_folder_and_add_name("report", "slab_rebar_plan")[0]
        except Exception:
            report_folder = Path.home() / "Documents"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Slab Rebar Plan to DXF", 
            str(report_folder / "slab_rebar_plan.dxf"),
            "DXF Files (*.dxf);;All Files (*)"
        )
        if not path:
            return

        def export_task():
            from civiltools.dxf.slab_rebar_export import export_slab_rebar_dxf
            return export_slab_rebar_dxf(
                etabs=self._etabs,
                data=filtered_data,
                output_file=path,
                layers=[l for l, c in [("A", self.chk_layer_a), ("B", self.chk_layer_b), ("Other", self.chk_layer_other)] if c.isChecked()],
                separate_layers=self.chk_separate_layers.isChecked(),
                top=self.chk_top.isChecked(),
                bottom=self.chk_bottom.isChecked(),
                optimizer_params={
                    "continuous_rebar_top": self.spin_cont_top.value(),
                    "continuous_rebar_bot": self.spin_cont_bot.value(),
                    "region_threshold": self.spin_region_thr.value(),
                    "min_area_threshold": self.spin_min_area.value(),
                    "extend_length": self.spin_extend.value(),
                    "min_bar_length": self.spin_min_bar.value(),
                }
            )

        with BusyDialog("Exporting…", "Generating DXF with optimized rebar layout…", parent=self) as dlg:
            try:
                summary = dlg.run(export_task)
                QMessageBox.information(self, "Export Complete", summary)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _update_cache_info(self):
        """Update cache info label."""
        if self._cache_data is None or self._cache_data.empty:
            self.lbl_cache_info.setText("Cache: not loaded")
        else:
            self.lbl_cache_info.setText(
                f"Cache: {len(self._cache_data)} rows, "
                f"read count: {self._read_count}"
            )

    def _populate_story_list(self):
        """Populate checkable story list from cache."""
        if self._cache_data is None or self._cache_data.empty:
            return
        
        self.story_list.clear()
        stories = sorted(self._cache_data["Story"].unique())
        for story in stories:
            item = QListWidgetItem(story)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.story_list.addItem(item)

    def _populate_preview_table(self):
        """Populate preview table with grouped data."""
        if self._cache_data is None or self._cache_data.empty:
            return

        # Group by story, strip, layer, side and summarize
        # Column name from etabs_api is 'Face' (values: 'TOP', 'BOT')
        face_col = "Face" if "Face" in self._cache_data.columns else "TopBot"
        groups = self._cache_data.groupby(["Story", "StripObject", "Layer", face_col]).agg({
            "Area": ["count", "sum"]
        }).reset_index()
        groups.columns = ["Story", "StripObject", "Layer", "Face", "Regions", "TotalArea"]

        self.table_preview.setRowCount(len(groups))
        for row_idx, row in groups.iterrows():
            self.table_preview.setItem(row_idx, 0, QTableWidgetItem(str(row["Story"])))
            self.table_preview.setItem(row_idx, 1, QTableWidgetItem(str(row["StripObject"])))
            self.table_preview.setItem(row_idx, 2, QTableWidgetItem(str(row["Layer"])))
            self.table_preview.setItem(row_idx, 3, QTableWidgetItem(str(row["Face"])))
            self.table_preview.setItem(row_idx, 4, QTableWidgetItem(str(int(row["Regions"]))))
            self.table_preview.setItem(row_idx, 5, QTableWidgetItem(f"{row['TotalArea']:,.0f}"))
            self.table_preview.setItem(row_idx, 6, QTableWidgetItem(""))

    @property
    def result(self) -> CommandResult | None:
        return self._result
