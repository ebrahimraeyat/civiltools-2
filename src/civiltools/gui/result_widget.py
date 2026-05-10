"""
Result display widget — ported from civilTools/table_model.py ResultWidget.

Shows a pandas-backed table with:
- Column filter (combobox + text search)
- Sort by clicking headers
- Export to Excel, Word, CSV
- Copy to clipboard
- Color-coded cells via the model's BackgroundRole
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QSortFilterProxyModel, QRegularExpression, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QCheckBox, QTableView, QHeaderView,
    QFileDialog, QMessageBox, QApplication, QSplitter, QTextEdit,
)

from civiltools.gui.table_models import PandasModel


class ResultWidget(QWidget):
    """Main result display — mirrors civilTools ``table_model.ResultWidget``."""

    #: Emitted when a table row is selected; carries the source DataFrame row index.
    selection_changed = Signal(int)

    def __init__(
        self,
        df: pd.DataFrame,
        model_class: type[PandasModel] = PandasModel,
        title: str = "",
        summary: str = "",
        ok: bool = True,
        parent: QWidget | None = None,
        kwargs: dict | None = None,
    ):
        super().__init__(parent)
        self._title = title
        self._df = df

        # ── Layout ──────────────────────────────────────────────────
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Title
        if title:
            title_lbl = QLabel(f"<b style='font-size:14px'>{title}</b>")
            main_layout.addWidget(title_lbl)

        # Filter bar (matches original: Filter [text] By Column: [combo])
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Filter"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to filter…")
        filter_bar.addWidget(self._filter_edit)
        filter_bar.addWidget(QLabel("By Column:"))
        self._col_combo = QComboBox()
        filter_bar.addWidget(self._col_combo)

        # Export buttons
        self._btn_excel = QPushButton("Excel")
        self._btn_excel.setToolTip("Export to Excel (.xlsx)")
        filter_bar.addWidget(self._btn_excel)
        self._btn_word = QPushButton("Word")
        self._btn_word.setToolTip("Export to Word (.docx)")
        filter_bar.addWidget(self._btn_word)
        self._btn_csv = QPushButton("CSV")
        self._btn_csv.setToolTip("Export to CSV")
        filter_bar.addWidget(self._btn_csv)
        self._btn_copy = QPushButton("Copy")
        self._btn_copy.setToolTip("Copy table to clipboard")
        filter_bar.addWidget(self._btn_copy)

        self._open_after = QCheckBox("Open")
        self._open_after.setChecked(True)
        filter_bar.addWidget(self._open_after)

        main_layout.addLayout(filter_bar)

        # Table + detail pane in a vertical splitter
        self._splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableView()
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._splitter.addWidget(self._table)

        # Bottom pane: a horizontal QSplitter that holds
        #   [detail text | (optional right panel added via add_right_panel())]
        self._bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._bottom_splitter.hide()  # shown only when __detail__ column is present

        self._detail_pane = QTextEdit()
        self._detail_pane.setReadOnly(True)
        self._detail_pane.setPlaceholderText("Select a row to see calculation details…")
        self._detail_pane.setFontFamily("Courier New")
        self._bottom_splitter.addWidget(self._detail_pane)

        self._splitter.addWidget(self._bottom_splitter)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter)

        # Summary bar
        self._summary_lbl = QLabel()
        main_layout.addWidget(self._summary_lbl)

        # ── Model + Proxy ───────────────────────────────────────────
        self._model = model_class(df, kwargs)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._table.setModel(self._proxy)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)

        # Populate column combo (skip hidden system columns)
        for col_name in self._model.df.columns:
            if not str(col_name).startswith("__"):
                self._col_combo.addItem(str(col_name))

        # Hide any __ system columns from the visible table
        for col_name in self._model.df.columns:
            if str(col_name).startswith("__"):
                idx = self._model.df.columns.get_loc(col_name)
                self._table.setColumnHidden(idx, True)

        # If a __detail__ column exists: show detail pane
        self._detail_col = "__detail__"
        if self._detail_col in self._model.df.columns:
            self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
            self._bottom_splitter.show()
            # connect after model is set (done below)

        # Summary
        if summary:
            color = "#006400" if ok else "#8B0000"
            self._summary_lbl.setText(
                f'<span style="color:{color}; font-weight:bold">{summary}</span>'
            )

        # ── Connections ─────────────────────────────────────────────
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        self._col_combo.currentIndexChanged.connect(self._on_col_changed)
        self._btn_excel.clicked.connect(self.export_to_excel)
        self._btn_word.clicked.connect(self.export_to_word)
        self._btn_csv.clicked.connect(self.export_to_csv)
        self._btn_copy.clicked.connect(self.copy_to_clipboard)

        # Ctrl+C shortcut
        sc = QShortcut(QKeySequence.StandardKey.Copy, self._table)
        sc.activated.connect(self.copy_to_clipboard)

        # Connect row-click detail pane (after model is assigned)
        if self._detail_col in self._model.df.columns:
            self._table.selectionModel().selectionChanged.connect(self._on_row_selected)

    # ── Public API for extending the bottom panel ───────────────────

    def add_right_panel(self, widget: QWidget) -> None:
        """
        Add a widget to the right of the detail text pane.
        The bottom splitter is shown automatically.
        """
        self._bottom_splitter.addWidget(widget)
        self._bottom_splitter.setStretchFactor(0, 1)  # detail text
        self._bottom_splitter.setStretchFactor(
            self._bottom_splitter.count() - 1, 1
        )  # right panel
        self._bottom_splitter.show()

    # ── Detail pane slot ────────────────────────────────────────────

    def _on_row_selected(self):
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            self._detail_pane.clear()
            return
        source_idx = self._proxy.mapToSource(indexes[0])
        df_row = source_idx.row()
        detail_text = self._model.df.iloc[df_row].get(self._detail_col, "")
        self._detail_pane.setPlainText(str(detail_text))
        self.selection_changed.emit(df_row)

    # ── Filter slots ────────────────────────────────────────────────

    def _on_filter_changed(self, text: str):
        regex = QRegularExpression(
            text, QRegularExpression.PatternOption.CaseInsensitiveOption
        )
        self._proxy.setFilterRegularExpression(regex)

    def _on_col_changed(self, index: int):
        self._proxy.setFilterKeyColumn(index)

    # ── Export: Excel ───────────────────────────────────────────────

    def export_to_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", f"{self._title}.xlsx",
            "Excel (*.xlsx);;All Files (*)",
        )
        if not path:
            return
        try:
            with pd.ExcelWriter(path) as writer:
                self._model.df.to_excel(writer, index=False)
            if self._open_after.isChecked():
                import os; os.startfile(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Export: Word ────────────────────────────────────────────────

    def export_to_word(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Word", f"{self._title}.docx",
            "Word (*.docx);;All Files (*)",
        )
        if not path:
            return
        try:
            from docx import Document
            from docx.oxml.ns import nsdecls
            from docx.oxml import parse_xml

            doc = Document()
            nrows = self._model.rowCount()
            ncols = self._model.columnCount()
            table = doc.add_table(rows=nrows + 1, cols=ncols)
            table.style = "Table Grid"

            # Header row
            for j in range(ncols):
                cell = table.cell(0, j)
                cell.text = str(self._model.headerData(
                    j, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                ))
                run = cell.paragraphs[0].runs[0]
                run.bold = True
                shading = parse_xml(
                    f'<w:shd {nsdecls("w")} w:fill="#244061"/>'
                )
                cell._tc.get_or_add_tcPr().append(shading)

            # Data rows
            for row in range(nrows):
                for col in range(ncols):
                    idx = self._model.index(row, col)
                    text = self._model.data(idx, Qt.ItemDataRole.DisplayRole) or ""
                    bg = self._model.data(idx, Qt.ItemDataRole.BackgroundRole)
                    cell = table.cell(row + 1, col)
                    cell.text = str(text)
                    if bg and isinstance(bg, QColor):
                        shading = parse_xml(
                            f'<w:shd {nsdecls("w")} w:fill="{bg.name()}"/>'
                        )
                        cell._tc.get_or_add_tcPr().append(shading)

            doc.save(path)
            if self._open_after.isChecked():
                import os; os.startfile(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Export: CSV ─────────────────────────────────────────────────

    def export_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV", f"{self._title}.csv",
            "CSV (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            self._model.df.to_csv(path, index=False, encoding="utf-8-sig")
            if self._open_after.isChecked():
                import os; os.startfile(path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    # ── Copy to clipboard ───────────────────────────────────────────

    def copy_to_clipboard(self):
        """Copy entire table as tab-separated text."""
        lines = ["\t".join(str(c) for c in self._model.df.columns)]
        for r in range(self._model.rowCount()):
            row = []
            for c in range(self._model.columnCount()):
                idx = self._model.index(r, c)
                val = self._model.data(idx, Qt.ItemDataRole.DisplayRole)
                row.append(str(val) if val is not None else "")
            lines.append("\t".join(row))
        QApplication.clipboard().setText("\n".join(lines))

    # ── JSON save (matching original) ───────────────────────────────

    def save_to_json(self, filepath: str | Path):
        """Save table data + cell colors to JSON (matches FreeCAD format)."""
        data = []
        for col in range(self._model.columnCount()):
            text = self._model.headerData(
                col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            data.append({"row": 0, "col": col, "text": str(text), "color": ""})

        for row in range(self._model.rowCount()):
            for col in range(self._model.columnCount()):
                idx = self._model.index(row, col)
                text = self._model.data(idx, Qt.ItemDataRole.DisplayRole) or ""
                bg = self._model.data(idx, Qt.ItemDataRole.BackgroundRole)
                color = bg.name() if isinstance(bg, QColor) else ""
                data.append({
                    "row": row + 1, "col": col,
                    "text": str(text), "color": color,
                })

        Path(filepath).write_text(
            json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8"
        )
