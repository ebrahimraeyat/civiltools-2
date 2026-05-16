# pyright: reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etabs_api.controls_input import ControlsInput

from civiltools.commands import register
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands.controls_input_report import ControlsInputReportExporter
from civiltools.commands.controls_input_settings import (
    ControlsInputSettingsDialog,
    load_controls_input_settings,
)
from civiltools.commands.controls_input_worker import ControlWorker

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - optional dependency fallback
    FigureCanvas = None
    Figure = None


@register
class ControlsInputCheck(BaseCommand):
    command_id = "controls_input"
    label = "Input Controls"
    menu_path = "Control"
    tooltip = "Run pre-analysis input validation checks"
    table_model = "PandasModel"
    dialog_class = "civiltools.commands.controls_input.ControlsInputDialog"


class ControlsInputDialog(QDialog):
    """Interactive dialog for running and reviewing ETABS input controls."""

    STATUS_MAP = {
        "pending": ("⏳", "Pending", "#808080"),
        "running": ("🔄", "Running", "#1e88e5"),
        "PASS": ("✅", "Pass", "#2e7d32"),
        "FAIL": ("❌", "Fail", "#c62828"),
        "WARNING": ("⚠️", "Warning", "#f9a825"),
        "ERROR": ("❌", "Error", "#8e24aa"),
        "CANCELLED": ("⏹️", "Cancelled", "#616161"),
    }

    # Registry of fixable controls: key → {label, description, func(etabs, settings)}
    _FIX_REGISTRY: dict[str, dict] = {
        "control_end_rigid_zone_factor": {
            "label": "Fix End Offsets",
            "description": "Apply the expected rigid-zone factor to all frames",
            "func": lambda etabs, settings: etabs.frame_obj.set_end_length_offsets(
                settings.get("control_end_rigid_zone_factor", {}).get("expected_factor", 0.5)
            ),
        },
    }

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self.etabs = etabs
        self.settings = load_controls_input_settings()
        self.controls = ControlsInput.available_controls()
        self.results: dict[str, dict[str, Any]] = {}
        self.result: CommandResult | None = None
        self.result_y = None
        self.worker: ControlWorker | None = None
        self._checkboxes: dict[str, QCheckBox] = {}
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._progress_animation: QPropertyAnimation | None = None

        self._all_details_df: pd.DataFrame = pd.DataFrame()
        self._selected_key: str | None = None

        self.setWindowTitle("Input Controls")
        self.setMinimumSize(1200, 760)
        self._build_ui()
        self._populate_controls()
        self._refresh_outputs()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("<h2>ETABS Input Controls</h2><div>Pre-analysis validation with live status, details, and export.</div>")
        header.addWidget(title, 1)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        controls_group = QGroupBox("Controls")
        controls_group_layout = QVBoxLayout(controls_group)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.controls_layout = QVBoxLayout(scroll_content)
        self.controls_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        controls_group_layout.addWidget(scroll)
        left_layout.addWidget(controls_group, 1)

        button_grid = QGridLayout()
        self.run_all_button = QPushButton("Run All")
        self.run_selected_button = QPushButton("Run Selected")
        self.settings_button = QPushButton("Settings")
        self.export_button = QPushButton("Export")
        self.cancel_button = QPushButton("Cancel")
        self.skip_button = QPushButton("⏭ Skip")
        self.done_button = QPushButton("Done")
        self.cancel_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.skip_button.setToolTip("Skip the currently running control and continue with the next one")
        self.done_button.setEnabled(False)
        button_grid.addWidget(self.run_all_button, 0, 0)
        button_grid.addWidget(self.run_selected_button, 0, 1)
        button_grid.addWidget(self.settings_button, 1, 0)
        button_grid.addWidget(self.export_button, 1, 1)
        button_grid.addWidget(self.cancel_button, 2, 0)
        button_grid.addWidget(self.skip_button, 2, 1)
        button_grid.addWidget(self.done_button, 3, 0, 1, 2)
        left_layout.addLayout(button_grid)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("Ready")
        right_layout.addWidget(self.progress_label)
        right_layout.addWidget(self.progress_bar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Control", "Status", "Checked", "Failed"])
        self.tree.setAlternatingRowColors(True)
        right_layout.addWidget(self.tree, 1)

        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs, 2)

        # ── Summary tab: left=text, right=overall pie chart ─────────────
        summary_container = QWidget()
        summary_outer = QSplitter(Qt.Orientation.Horizontal)
        summary_outer_layout = QVBoxLayout(summary_container)
        summary_outer_layout.setContentsMargins(0, 0, 0, 0)
        summary_outer_layout.addWidget(summary_outer)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_outer.addWidget(self.summary_text)

        self.summary_chart_widget = QWidget()
        summary_chart_layout = QVBoxLayout(self.summary_chart_widget)
        summary_chart_layout.setContentsMargins(0, 0, 0, 0)
        if FigureCanvas and Figure:
            self.summary_chart_figure = Figure(figsize=(4, 4))
            self.summary_chart_canvas = FigureCanvas(self.summary_chart_figure)
            summary_chart_layout.addWidget(self.summary_chart_canvas)
        else:
            self.summary_chart_figure = None
            self.summary_chart_canvas = None
            summary_chart_layout.addWidget(QLabel("matplotlib is not available."))
        summary_outer.addWidget(self.summary_chart_widget)
        summary_outer.setStretchFactor(0, 1)
        summary_outer.setStretchFactor(1, 1)

        self.tabs.addTab(summary_container, "Summary")

        # ── Details tab: table+chart in splitter ─────────────────────
        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)

        details_btn_row = QHBoxLayout()
        self.select_failed_button = QPushButton("⚠ Select All Failed in ETABS")
        self.select_failed_button.setToolTip("Select every failed element in the ETABS model")
        self.select_failed_button.clicked.connect(self._select_all_failed)
        self.fix_button = QPushButton("🔧 Fix")
        self.fix_button.setToolTip("Auto-fix the selected control in the ETABS model")
        self.fix_button.setVisible(False)
        self.fix_button.clicked.connect(self._on_fix_clicked)
        details_btn_row.addWidget(self.select_failed_button)
        details_btn_row.addStretch(1)
        details_btn_row.addWidget(self.fix_button)
        details_layout.addLayout(details_btn_row)

        self.details_table = QTableWidget(0, 3)
        self.details_table.setHorizontalHeaderLabels([" ", "Story", "Element"])
        self.details_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.details_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.details_table.setSortingEnabled(True)
        self.details_table.cellClicked.connect(self._handle_detail_click)

        self.details_chart_widget = QWidget()
        details_chart_layout = QVBoxLayout(self.details_chart_widget)
        details_chart_layout.setContentsMargins(0, 0, 0, 0)
        if FigureCanvas and Figure:
            self.details_chart_figure = Figure(figsize=(4, 4))
            self.details_chart_canvas = FigureCanvas(self.details_chart_figure)
            details_chart_layout.addWidget(self.details_chart_canvas)
        else:
            self.details_chart_figure = None
            self.details_chart_canvas = None
            details_chart_layout.addWidget(QLabel("matplotlib is not available."))

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(self.details_table)
        bottom_splitter.addWidget(self.details_chart_widget)
        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 1)

        details_layout.addWidget(bottom_splitter, 1)
        self.tabs.addTab(details_container, "Details")

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.run_all_button.clicked.connect(self._run_all)
        self.run_selected_button.clicked.connect(self._run_selected)
        self.settings_button.clicked.connect(self._open_settings)
        self.export_button.clicked.connect(self._export_results)
        self.cancel_button.clicked.connect(self._cancel_worker)
        self.skip_button.clicked.connect(self._skip_current_control)
        self.done_button.clicked.connect(self.accept)

    def _populate_controls(self) -> None:
        for control in self.controls:
            key = control["key"]
            checkbox = QCheckBox(f"{control['control_id']:02d}. {control['title']}")
            checkbox.setChecked(True)
            self._checkboxes[key] = checkbox
            self.controls_layout.insertWidget(self.controls_layout.count() - 1, checkbox)

            item = QTreeWidgetItem([control["title"], self.STATUS_MAP["pending"][1], "0", "0"])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self.tree.addTopLevelItem(item)
            self._tree_items[key] = item
            self._set_item_status(item, "pending")

        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.currentItemChanged.connect(
            lambda current, _prev: self._on_tree_item_clicked(current, 0) if current else None
        )

    def _apply_theme(self, dark: bool) -> None:
        """Theme is now controlled globally from the main window."""
        pass

    def _selected_keys(self) -> list[str]:
        return [key for key, checkbox in self._checkboxes.items() if checkbox.isChecked()]

    def _run_all(self) -> None:
        self._start_worker([control["key"] for control in self.controls])

    def _run_selected(self) -> None:
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, "Input Controls", "Select at least one control.")
            return
        self._start_worker(keys)

    def _start_worker(self, keys: list[str]) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Input Controls", "A control run is already in progress.")
            return
        self.results = {}
        self.result = None
        self.done_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Running controls…")
        for key, item in self._tree_items.items():
            self._set_item_status(item, "pending")
            item.setText(2, "0")
            item.setText(3, "0")
            if key in keys:
                self._set_item_status(item, "running")
        self._refresh_outputs()

        self.worker = ControlWorker(self.etabs, keys, settings=self.settings)
        self.worker.progress.connect(self._on_progress)
        self.worker.control_started.connect(self._on_control_started)
        self.worker.control_finished.connect(self._on_control_finished)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _cancel_worker(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            # Disable Cancel to prevent double-click; keep Skip active so the
            # user can still interrupt the currently running (stuck) control.
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("Cancelling… (use ⏭ Skip to interrupt current control)")

    def _skip_current_control(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.skip_current()
            self.progress_label.setText("Skipping current control…")

    def _on_progress(self, current: int, total: int) -> None:
        percentage = int((100 * current) / max(total, 1))
        self._animate_progress(percentage)
        self.progress_label.setText(f"Completed {current} of {total} controls")

    def _animate_progress(self, value: int) -> None:
        animation = QPropertyAnimation(self.progress_bar, b"value", self)
        animation.setDuration(250)
        animation.setStartValue(self.progress_bar.value())
        animation.setEndValue(value)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.start()
        self._progress_animation = animation

    def _on_control_started(self, key: str) -> None:
        item = self._tree_items.get(key)
        if item is not None:
            self._set_item_status(item, "running")

    def _on_control_finished(self, key: str, result: dict) -> None:
        self.results[key] = result
        item = self._tree_items.get(key)
        if item is not None:
            status = result.get("status", "WARNING")
            self._set_item_status(item, status)
            summary = result.get("summary", {})
            item.setText(2, str(summary.get("total_checked", 0)))
            item.setText(3, str(summary.get("failed", 0)))
        self._refresh_outputs()

    def _on_all_finished(self, results: dict[str, dict]) -> None:
        self.results = results
        self.cancel_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.done_button.setEnabled(True)
        self.progress_label.setText("✅ Run completed")
        self._animate_progress(100)
        self._build_command_result()
        self._refresh_outputs()
        self._sort_tree()
        # Show overall pie chart on completion
        exporter = ControlsInputReportExporter(self.results)
        self._refresh_chart(exporter.summary_dataframe())
        self.tabs.setCurrentIndex(0)

    def _sort_tree(self) -> None:
        """Re-order tree items: FAIL → ERROR → WARNING → PASS → others."""
        _ORDER = {"PASS": 0, "WARNING": 1, "ERROR": 2, "FAIL": 3}
        root = self.tree.invisibleRootItem()
        count = root.childCount()
        items = [root.takeChild(0) for _ in range(count)]
        items.sort(key=lambda item: _ORDER.get(
            self.results.get(item.data(0, Qt.ItemDataRole.UserRole), {}).get("status", ""),
            99,
        ))
        for item in items:
            root.addChild(item)

    def _on_cancelled(self) -> None:
        self.cancel_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.done_button.setEnabled(True)
        self.progress_label.setText("Run cancelled")
        self._refresh_outputs()
        self._sort_tree()

    def _on_failed(self, message: str) -> None:
        self.cancel_button.setEnabled(False)
        QMessageBox.critical(self, "Input Controls", message)

    def _set_item_status(self, item: QTreeWidgetItem, status: str) -> None:
        icon_text, label, color = self.STATUS_MAP.get(status, self.STATUS_MAP["pending"])
        item.setText(1, f"{icon_text} {label}")
        for column in range(item.columnCount()):
            item.setForeground(column, QColor(color))

    def _refresh_outputs(self) -> None:
        exporter = ControlsInputReportExporter(self.results)
        summary_df = exporter.summary_dataframe()
        details_df = exporter.details_dataframe()

        if summary_df.empty:
            self.summary_text.setPlainText("No results yet.")
        else:
            counts = summary_df["Status"].value_counts().to_dict()
            summary_lines = ["Input Controls Summary", "=" * 26, ""]
            for _, row in summary_df.iterrows():
                summary_lines.append(
                    f"- {row['Control Name']}: {row['Status']} | checked={row['Checked']} | failed={row['Failed']}"
                )
            summary_lines.append("")
            summary_lines.append("Status counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
            self.summary_text.setPlainText("\n".join(summary_lines))

        self._all_details_df = details_df
        # Re-populate details table for the currently selected key (if any)
        if self._selected_key and not details_df.empty and "Control Key" in details_df.columns:
            self._populate_details_table(details_df[details_df["Control Key"] == self._selected_key])
        # Update summary chart with current run progress
        self._refresh_chart(summary_df)

    def _populate_details_table(self, df: pd.DataFrame) -> None:
        """Fill the details table with dynamic columns per control."""
        # Columns handled explicitly (not shown as extra)
        _FIXED_COLS = {"Control Name", "Control Key", "Status", "story", "element_id", "failed"}
        # Everything else becomes a visible dynamic column
        extra_keys = [k for k in df.columns if k not in _FIXED_COLS and k != "nan"]

        def _display_name(col: str) -> str:
            """Strip the word 'value' (and surrounding underscores) from column names."""
            cleaned = col.replace("_value", "").replace("value_", "").strip("_")
            return cleaned if cleaned else col

        # Rebuild columns: icon | Story | Element | [dynamic...]
        all_display = [" ", "Story", "Element"] + [_display_name(k) for k in extra_keys]
        self.details_table.setSortingEnabled(False)
        self.details_table.setColumnCount(len(all_display))
        self.details_table.setHorizontalHeaderLabels(all_display)
        self.details_table.setRowCount(len(df.index))

        for row_index, (_, row) in enumerate(df.iterrows()):
            failed = row.get("failed", True)
            if failed:
                icon = self.STATUS_MAP["FAIL"][0]
            else:
                icon = self.STATUS_MAP["PASS"][0]

            row_values = [
                icon,
                str(row.get("story", "")),
                str(row.get("element_id", "")),
            ] + [
                str(row[k]) if k in row.index and pd.notna(row[k]) else ""
                for k in extra_keys
            ]
            for col_idx, value in enumerate(row_values):
                self.details_table.setItem(row_index, col_idx, QTableWidgetItem(value if value != "nan" else ""))

        self.details_table.resizeColumnsToContents()
        self.details_table.setSortingEnabled(True)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Filter details table and refresh chart for the clicked/selected control."""
        if item is None:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key is None:
            return
        self._selected_key = key
        self._selected_key = key

        # Filter details
        if not self._all_details_df.empty and "Control Key" in self._all_details_df.columns:
            filtered = self._all_details_df[self._all_details_df["Control Key"] == key]
        else:
            filtered = self._all_details_df
        self._populate_details_table(filtered)

        # Switch to Details tab (index 1)
        self.tabs.setCurrentIndex(1)
        self._refresh_chart_for_key(key)

        # Show/hide Fix button
        fix_info = self._FIX_REGISTRY.get(key)
        if fix_info and key in self.results:
            self.fix_button.setText(f"🔧 {fix_info['label']}")
            self.fix_button.setToolTip(fix_info["description"])
            self.fix_button.setVisible(True)
        else:
            self.fix_button.setVisible(False)

    def _refresh_chart(self, summary_df: pd.DataFrame) -> None:
        """Overall pie chart (Summary tab) — PASS / FAIL / WARNING / ERROR counts."""
        if self.summary_chart_figure is None or self.summary_chart_canvas is None:
            return
        self.summary_chart_figure.clear()
        axis = self.summary_chart_figure.add_subplot(111)
        if summary_df.empty:
            axis.text(0.5, 0.5, "No results", ha="center", va="center", fontsize=8)
            axis.set_axis_off()
        else:
            counts = summary_df["Status"].value_counts()
            colors = [self.STATUS_MAP.get(s, self.STATUS_MAP["pending"])[2] for s in counts.index]
            axis.pie(
                counts.values.tolist(),
                labels=counts.index.tolist(),
                colors=colors,
                autopct="%1.0f%%",
                startangle=90,
                textprops={"fontsize": 7},
            )
            axis.set_title("Overall status", fontsize=9, pad=4)
        self.summary_chart_figure.tight_layout(pad=0.5)
        self.summary_chart_canvas.draw_idle()

    def _refresh_chart_for_key(self, key: str) -> None:
        """Pie chart for a single control (Details tab) — pass vs fail."""
        if self.details_chart_figure is None or self.details_chart_canvas is None:
            return
        result = self.results.get(key, {})
        summary = result.get("summary", {})
        total = summary.get("total_checked", 0)
        failed = summary.get("failed", 0)
        passed = total - failed

        self.details_chart_figure.clear()
        axis = self.details_chart_figure.add_subplot(111)
        if total == 0:
            axis.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=8)
            axis.set_axis_off()
        else:
            labels, sizes, colors = [], [], []
            if passed > 0:
                labels.append("Pass"); sizes.append(passed); colors.append(self.STATUS_MAP["PASS"][2])
            if failed > 0:
                labels.append("Fail"); sizes.append(failed); colors.append(self.STATUS_MAP["FAIL"][2])
            axis.pie(sizes, labels=labels, colors=colors, autopct="%1.0f%%",
                     startangle=90, textprops={"fontsize": 7})
            ctrl_name = next((c["title"] for c in self.controls if c["key"] == key), key)
            if len(ctrl_name) > 28:
                ctrl_name = ctrl_name[:26] + "…"
            axis.set_title(f"{ctrl_name}\n({total} checked, {failed} failed)",
                           fontsize=8, pad=4)
        self.details_chart_figure.tight_layout(pad=0.5)
        self.details_chart_canvas.draw_idle()

    def _handle_detail_click(self, row: int, _column: int) -> None:
        """Single-click: select the element in the ETABS model."""
        element_item = self.details_table.item(row, 2)
        if element_item is None:
            return
        element_id = element_item.text().strip()
        if not element_id:
            return
        self._select_elements_in_etabs([element_id])

    def _select_elements_in_etabs(self, names: list[str]) -> None:
        """Clear selection then select *names* (frame / area / point) in ETABS."""
        if not names or self.etabs is None:
            return
        try:
            sap = self.etabs.SapModel
            sap.SelectObj.ClearSelection()
            for name in names:
                # Try frame first, then area, then point — errors are silently swallowed
                try:
                    sap.FrameObj.SetSelected(name, True)
                except Exception:
                    pass
                try:
                    sap.AreaObj.SetSelected(name, True)
                except Exception:
                    pass
                try:
                    sap.PointObj.SetSelected(name, True)
                except Exception:
                    pass
        except Exception:
            pass

    def _select_all_failed(self) -> None:
        """Select every failed element from current details view in ETABS."""
        if self._all_details_df.empty:
            QMessageBox.information(self, "Input Controls", "No results to select.")
            return
        df = self._all_details_df
        if self._selected_key and "Control Key" in df.columns:
            df = df[df["Control Key"] == self._selected_key]
        failed = df[df["failed"].astype(bool) == True]["element_id"].dropna().astype(str).tolist()
        failed = [n for n in failed if n.strip()]
        if not failed:
            QMessageBox.information(self, "Input Controls", "No failed elements to select.")
            return
        self._select_elements_in_etabs(failed)
        QMessageBox.information(self, "Input Controls", f"{len(failed)} failed element(s) selected in ETABS.")

    def _on_fix_clicked(self) -> None:
        """Execute the fix function registered for the currently selected control."""
        key = self._selected_key
        if not key:
            return
        fix_info = self._FIX_REGISTRY.get(key)
        if not fix_info:
            return
        reply = QMessageBox.question(
            self, "Confirm Fix",
            f"{fix_info['description']}\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            fix_info["func"](self.etabs, self.settings)
            QMessageBox.information(self, "Fix Applied", "Fix applied successfully.\nRe-run the control to verify.")
        except Exception as exc:
            QMessageBox.critical(self, "Fix Failed", str(exc))

    def _open_settings(self) -> None:
        dialog = ControlsInputSettingsDialog(self.settings, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.values()

    def _export_results(self) -> None:
        if not self.results:
            QMessageBox.information(self, "Input Controls", "No results available for export.")
            return
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Input Controls Report",
            str(Path.home() / "controls_input_report.xlsx"),
            "Excel (*.xlsx);;Word (*.docx);;PDF (*.pdf)",
        )
        if not file_path:
            return
        exporter = ControlsInputReportExporter(self.results)
        try:
            if selected_filter.startswith("Excel") or file_path.lower().endswith(".xlsx"):
                target = exporter.export_excel(file_path if file_path.lower().endswith(".xlsx") else f"{file_path}.xlsx")
            elif selected_filter.startswith("Word") or file_path.lower().endswith(".docx"):
                target = exporter.export_word(file_path if file_path.lower().endswith(".docx") else f"{file_path}.docx")
            else:
                target = exporter.export_pdf(file_path if file_path.lower().endswith(".pdf") else f"{file_path}.pdf")
            QMessageBox.information(self, "Input Controls", f"Report exported to:\n{target}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _build_command_result(self) -> None:
        exporter = ControlsInputReportExporter(self.results)
        summary_df = exporter.summary_dataframe()
        counts = summary_df["Status"].value_counts().to_dict() if not summary_df.empty else {}
        ok = counts.get("FAIL", 0) == 0 and counts.get("ERROR", 0) == 0
        summary = "No controls executed."
        if counts:
            summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        self.result = CommandResult(
            title="Input Controls",
            dataframe=summary_df,
            summary=summary,
            ok=ok,
            kwargs={"results": self.results},
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Ensure the worker thread is stopped before the dialog closes."""
        self._cancel_worker()
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)  # wait up to 3 s; then terminate
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(1000)
        super().closeEvent(event)

    def accept(self) -> None:
        if self.result is None and self.results:
            self._build_command_result()
        super().accept()
