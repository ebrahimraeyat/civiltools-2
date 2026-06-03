"""Rename rectangular concrete beam/column sections by name patterns."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QMessageBox,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

BEAM_DEFAULT = "B$WidthH$Height"
COLUMN_DEFAULT = "C$WidthX$Height$TotalRebarsT$RebarSize$CornerRebarSize"

BEAM_TOKENS = ["$Width", "$Height", "$Fc"]
COLUMN_TOKENS = [
    "$Width", "$Height", "$Fc",
    "$TotalRebars", "$RebarSize", "$CornerRebarSize",
    "$NumBars3Dir", "$NumBars2Dir",
]

COL_OLD = 0
COL_NEW = 1
COL_STATUS = 2


class RenameConcreteSectionsDialog(QDialog):
    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        self.setWindowTitle("Rename Concrete Sections")
        self.resize(780, 560)
        set_dialog_icon(self, "frame_sections.svg")

        self._build_ui()
        self._setup_token_menus()
        self._create_connections()
        self._refresh_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QWidget(self)
        form = QFormLayout(group)

        beam_row = QWidget(group)
        beam_row_lay = QHBoxLayout(beam_row)
        beam_row_lay.setContentsMargins(0, 0, 0, 0)
        self.beam_pattern = QLineEdit(BEAM_DEFAULT)
        self.beam_token_btn = QPushButton("Insert Token")
        self.beam_token_btn.setMaximumWidth(120)
        beam_row_lay.addWidget(self.beam_pattern)
        beam_row_lay.addWidget(self.beam_token_btn)

        column_row = QWidget(group)
        column_row_lay = QHBoxLayout(column_row)
        column_row_lay.setContentsMargins(0, 0, 0, 0)
        self.column_pattern = QLineEdit(COLUMN_DEFAULT)
        self.column_token_btn = QPushButton("Insert Token")
        self.column_token_btn.setMaximumWidth(120)
        column_row_lay.addWidget(self.column_pattern)
        column_row_lay.addWidget(self.column_token_btn)

        form.addRow("Beam Pattern:", beam_row)
        form.addRow("Column Pattern:", column_row)
        root.addWidget(group)

        top_buttons = QHBoxLayout()
        top_buttons.addStretch(1)
        self.preview_btn = QPushButton("Preview")
        top_buttons.addWidget(self.preview_btn)
        root.addLayout(top_buttons)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Current Name", "New Name", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.warning_label = QLabel("", self)
        self.warning_label.setStyleSheet("color: #a00000; font-weight: bold;")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        root.addWidget(self.warning_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.close_btn = QPushButton("Close")
        actions.addWidget(self.apply_btn)
        actions.addWidget(self.close_btn)
        root.addLayout(actions)

    def _setup_token_menus(self):
        self._attach_token_menu(self.beam_token_btn, BEAM_TOKENS, self.beam_pattern)
        self._attach_token_menu(self.column_token_btn, COLUMN_TOKENS, self.column_pattern)

    def _attach_token_menu(self, button: QPushButton, tokens: list[str], line: QLineEdit):
        menu = QMenu(button)
        for token in tokens:
            action = menu.addAction(token)
            action.triggered.connect(lambda checked=False, t=token, w=line: self._insert_token(w, t))
        button.setMenu(menu)

    def _insert_token(self, line: QLineEdit, token: str):
        pos = line.cursorPosition()
        text = line.text()
        line.setText(text[:pos] + token + text[pos:])
        line.setCursorPosition(pos + len(token))
        self._refresh_preview()

    def _create_connections(self):
        self.preview_btn.clicked.connect(self._refresh_preview)
        self.apply_btn.clicked.connect(self._apply)
        self.close_btn.clicked.connect(self.reject)
        self.beam_pattern.textChanged.connect(self._refresh_preview)
        self.column_pattern.textChanged.connect(self._refresh_preview)

    def _calc_preview(self, beam_pattern: str, column_pattern: str):
        prop = self._etabs.prop_frame
        if hasattr(prop, "get_concrete_rec_rename_preview"):
            return prop.get_concrete_rec_rename_preview(beam_pattern, column_pattern)

        new_names = prop.get_concrete_rec_new_names_with_pattern(beam_pattern, column_pattern)
        if new_names is None:
            return None
        existing_names = set(prop.get_name_list())
        target_counts = Counter(new for old, new in new_names.items() if old != new)

        preview = []
        needs_rebar_size = "$RebarSize" in column_pattern
        needs_corner_rebar_size = "$CornerRebarSize" in column_pattern
        for old_name, new_name in new_names.items():
            conflict = False
            missing_rebar_data = False
            if new_name != old_name and (new_name in existing_names or target_counts[new_name] > 1):
                conflict = True

            if prop.get_type_rebar(old_name) == 1 and (needs_rebar_size or needs_corner_rebar_size):
                rebar_args = prop.get_rebar_column(old_name)
                if rebar_args is None:
                    missing_rebar_data = True
                else:
                    rebar_size = rebar_args[8]
                    corner_rebar_size = rebar_args[14]
                    if needs_rebar_size and str(rebar_size).strip().lower() in ("", "none", "null", "nan"):
                        missing_rebar_data = True
                    if needs_corner_rebar_size and str(corner_rebar_size).strip().lower() in ("", "none", "null", "nan"):
                        missing_rebar_data = True

            preview.append({
                "old_name": old_name,
                "new_name": new_name,
                "conflict": conflict,
                "missing_rebar_data": missing_rebar_data,
            })
        return preview

    def _refresh_preview(self):
        beam_pattern = self.beam_pattern.text().strip()
        column_pattern = self.column_pattern.text().strip()

        preview = self._calc_preview(beam_pattern, column_pattern)
        self.table.setRowCount(0)

        if preview is None:
            self.warning_label.setText("Could not read section data from ETABS.")
            self.warning_label.setVisible(True)
            self.apply_btn.setEnabled(False)
            return

        red = QColor(255, 190, 190)
        green = QColor(200, 245, 205)
        amber = QColor(255, 230, 180)

        has_conflict = False
        has_missing_rebar_data = False
        has_change = False
        self.table.setRowCount(len(preview))

        for i, row in enumerate(preview):
            old_name = str(row.get("old_name", ""))
            new_name = str(row.get("new_name", ""))
            conflict = bool(row.get("conflict", False))
            missing_rebar_data = bool(row.get("missing_rebar_data", False))
            changed = old_name != new_name

            if missing_rebar_data:
                status = "Missing Rebar Data"
                bg = amber
                has_missing_rebar_data = True
            elif conflict:
                status = "Conflict"
                bg = red
                has_conflict = True
            elif changed:
                status = "Rename"
                bg = green
                has_change = True
            else:
                status = "No Change"
                bg = None

            values = [old_name, new_name, status]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg is not None:
                    item.setBackground(bg)
                self.table.setItem(i, col, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        if has_missing_rebar_data:
            self.warning_label.setText(
                "Missing rebar size data detected in ETABS for one or more columns. "
                "Fill section rebar data before applying rename."
            )
            self.warning_label.setVisible(True)
            self.apply_btn.setEnabled(False)
            return

        if has_conflict:
            self.warning_label.setText(
                "Conflicting target names detected. Resolve conflicts before applying."
            )
            self.warning_label.setVisible(True)
            self.apply_btn.setEnabled(False)
            return

        if not has_change:
            self.warning_label.setText("No section names will change with current patterns.")
            self.warning_label.setVisible(True)
            self.apply_btn.setEnabled(False)
            return

        self.warning_label.setVisible(False)
        self.apply_btn.setEnabled(True)

    def _apply(self):
        beam_pattern = self.beam_pattern.text().strip()
        column_pattern = self.column_pattern.text().strip()

        ret = self._etabs.prop_frame.change_concrete_rec_names_with_pattern(
            beam_pattern,
            column_pattern,
        )
        if ret != 0:
            QMessageBox.warning(
                self,
                "Rename Failed",
                "Could not apply rename. Run preview and resolve conflicts first.",
            )
            self._refresh_preview()
            return

        self._result = CommandResult(
            title="Rename Concrete Sections",
            ok=True,
            summary="Rectangular concrete beam/column sections renamed successfully.",
        )
        QMessageBox.information(self, "Done", "Section names updated successfully.")
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
