"""Application-wide General and Report settings dialog."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from civiltools.config import Settings, default_report_preferences


class RtlTextDelegate(QStyledItemDelegate):
    """Create right-to-left editors for Persian section titles."""

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            editor.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        return editor


class AppSettingsDialog(QDialog):
    """Edit application-wide preferences without changing model settings."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumSize(760, 560)
        self.resize(900, 650)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_general_tab(), "General")
        self._tabs.addTab(self._build_report_tab(), "Report")
        layout.addWidget(self._tabs)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        self._buttons.accepted.connect(self._accept)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(self._buttons)

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        appearance_group = QGroupBox("Appearance")
        form = QFormLayout(appearance_group)
        self._appearance_combo = QComboBox()
        self._appearance_combo.addItem("Light", False)
        self._appearance_combo.addItem("Dark", True)
        form.addRow("Color mode:", self._appearance_combo)

        self._language_combo = QComboBox()
        self._language_combo.addItem("English", "en")
        self._language_combo.addItem("Persian", "fa")
        form.addRow("Application language:", self._language_combo)
        layout.addWidget(appearance_group)
        layout.addStretch()
        return tab

    def _build_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        options = QGroupBox("Report Defaults")
        form = QFormLayout(options)
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 16)
        self._workers_spin.setToolTip("Parallel workers are used only for image rendering")
        form.addRow("Image workers:", self._workers_spin)

        self._toc_check = QCheckBox("Include table of contents")
        form.addRow("", self._toc_check)
        self._fallback_check = QCheckBox("Read from ETABS when saved results are missing")
        form.addRow("", self._fallback_check)
        layout.addWidget(options)

        layout.addWidget(QLabel("Drag rows to set report order. Double-click titles to edit."))
        self._sections = QTreeWidget()
        self._sections.setColumnCount(4)
        self._sections.setHeaderLabels(
            ["Include", "English title", "Persian title", "Read from ETABS"]
        )
        self._sections.setRootIsDecorated(False)
        self._sections.setAlternatingRowColors(True)
        self._sections.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sections.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._sections.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._sections.setItemDelegateForColumn(2, RtlTextDelegate(self._sections))
        header = self._sections.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._sections, 1)

        self._restore_button = QPushButton("Restore Report Defaults")
        self._restore_button.clicked.connect(self._restore_report_defaults)
        layout.addWidget(self._restore_button)
        return tab

    def _load(self) -> None:
        self._set_combo_data(self._appearance_combo, bool(self._settings.get("dark_theme", False)))
        self._set_combo_data(self._language_combo, self._settings.get("language", "en"))
        self._load_report(copy.deepcopy(self._settings.get("report", default_report_preferences())))

    def _load_report(self, report: dict) -> None:
        self._workers_spin.setValue(report.get("workers", 4))
        self._toc_check.setChecked(report.get("include_table_of_contents", True))
        self._fallback_check.setChecked(report.get("fallback_to_etabs_if_missing", True))
        self._sections.clear()
        for section in report.get("sections", []):
            item = QTreeWidgetItem(
                ["", section["title_en"], section["title_fa"], ""]
            )
            item.setData(1, Qt.ItemDataRole.UserRole, section["key"])
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                0,
                Qt.CheckState.Checked if section["included"] else Qt.CheckState.Unchecked,
            )
            item.setCheckState(
                3,
                Qt.CheckState.Checked
                if section["read_from_etabs"]
                else Qt.CheckState.Unchecked,
            )
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._sections.addTopLevelItem(item)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _report_values(self) -> dict | None:
        sections = []
        for index in range(self._sections.topLevelItemCount()):
            item = self._sections.topLevelItem(index)
            title_en = item.text(1).strip()
            title_fa = item.text(2).strip()
            if not title_en or not title_fa:
                QMessageBox.warning(
                    self,
                    "Invalid Section Title",
                    "English and Persian section titles cannot be empty.",
                )
                return None
            sections.append(
                {
                    "key": item.data(1, Qt.ItemDataRole.UserRole),
                    "title_en": title_en,
                    "title_fa": title_fa,
                    "included": item.checkState(0) == Qt.CheckState.Checked,
                    "read_from_etabs": item.checkState(3) == Qt.CheckState.Checked,
                }
            )
        return {
            "language": self._settings.get("report", {}).get("language", "en"),
            "workers": self._workers_spin.value(),
            "include_table_of_contents": self._toc_check.isChecked(),
            "fallback_to_etabs_if_missing": self._fallback_check.isChecked(),
            "sections": sections,
        }

    def _apply(self) -> bool:
        report = self._report_values()
        if report is None:
            return False
        self._settings.update(
            {
                "dark_theme": self._appearance_combo.currentData(),
                "language": self._language_combo.currentData(),
                "report": report,
            }
        )
        return True

    def _accept(self) -> None:
        if self._apply():
            self.accept()

    def _restore_report_defaults(self) -> None:
        self._load_report(default_report_preferences())
