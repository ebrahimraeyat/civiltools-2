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
from typing import Any, Callable

import pandas as pd
from PySide6.QtCore import Qt, QSortFilterProxyModel, QRegularExpression, Signal, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QCheckBox, QTableView, QHeaderView,
    QFileDialog, QMessageBox, QApplication, QSplitter, QTextEdit, QFrame,
    QAbstractItemView,
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
        delegate_class: type | None = None,
        legend_items: list[tuple[str, str]] | None = None,
        sortable: bool = True,
        cell_selected: Callable[[int, int], None] | None = None,
        title: str = "",
        summary: str = "",
        ok: bool = True,
        parent: QWidget | None = None,
        kwargs: dict | None = None,
    ):
        super().__init__(parent)
        self._title = title
        self._df = df
        self._cell_selected = cell_selected
        # Defer ETABS selection so double-click can open the editor without
        # waiting on a blocking COM call from the first half of the double-click.
        self._pending_cell: tuple[int, int] | None = None
        self._select_timer = QTimer(self)
        self._select_timer.setSingleShot(True)
        # Slightly past the OS double-click threshold so a real double-click
        # never pays for ETABS selection before the editor opens.
        try:
            interval = int(QApplication.doubleClickInterval()) + 50
        except Exception:
            interval = 350
        self._select_timer.setInterval(max(interval, 300))
        self._select_timer.timeout.connect(self._emit_pending_cell_selection)

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
        self._table.setSortingEnabled(sortable)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
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

        content_layout = QHBoxLayout()
        content_layout.addWidget(self._splitter, 1)
        if legend_items:
            content_layout.addWidget(self._build_color_legend(legend_items))
        main_layout.addLayout(content_layout, 1)

        # Summary bar
        self._summary_lbl = QLabel()
        main_layout.addWidget(self._summary_lbl)

        # ── Model + Proxy ───────────────────────────────────────────
        self._model = model_class(df, kwargs)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._table.setModel(self._proxy)
        if delegate_class is not None:
            # Match FreeCAD ControlColumnResultWidget: custom delegate, no sorting.
            self._table.setItemDelegate(delegate_class(self._table))
            self._table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
            )
        # FreeCAD called resizeColumnsToContents() once — do not keep
        # ResizeToContents mode (recalculates on every paint and freezes large tables).
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.resizeColumnsToContents()

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
        # FreeCAD wired clicked → show_frame. We keep that behaviour for a true
        # single-click, but cancel it when the user double-clicks to edit.
        if self._cell_selected is not None:
            self._table.clicked.connect(self._on_cell_clicked)
            self._table.doubleClicked.connect(self._on_cell_double_clicked)

    def _build_color_legend(self, legend_items: list[tuple[str, str]]) -> QWidget:
        """Build a compact sidebar explaining table background colors."""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFixedWidth(190)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Color legend")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        for color, label in legend_items:
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(f"background-color: {color}; border: 1px solid #666;")
            row.addWidget(swatch)
            row.addWidget(QLabel(label), 1)
            layout.addLayout(row)
        layout.addStretch()
        return panel

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

    def _on_cell_clicked(self, proxy_index):
        """Queue ETABS selection; cancelled if a double-click follows."""
        if self._cell_selected is None:
            return
        # Never call COM while an in-cell editor is open.
        if self._table.state() is not QAbstractItemView.State.NoState:
            self._select_timer.stop()
            self._pending_cell = None
            return
        source_index = self._proxy.mapToSource(proxy_index)
        self._pending_cell = (source_index.row(), source_index.column())
        self._select_timer.start()

    def _on_cell_double_clicked(self, _proxy_index):
        """Open editor without paying the ETABS selection cost first."""
        self._select_timer.stop()
        self._pending_cell = None

    def _emit_pending_cell_selection(self):
        if self._cell_selected is None or self._pending_cell is None:
            return
        if self._table.state() is not QAbstractItemView.State.NoState:
            self._pending_cell = None
            return
        row, col = self._pending_cell
        self._pending_cell = None
        self._cell_selected(row, col)

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
