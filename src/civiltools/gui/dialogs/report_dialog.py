"""
Report generation dialog — choose sections and output directory,
then run the ReportWorker (QThread + ProcessPoolExecutor) to generate
a DOCX report with parallel image rendering.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from civiltools.config import Settings
from civiltools.gui.helpers import set_dialog_icon
from civiltools.report.report_config import (
    REFRESHABLE_SECTIONS,
    ModelReportSources,
    ReportConfig,
)

_RESULT_FILENAMES = {
    "drift": "drift.json",
    "torsion": "torsion.json",
    "pmm_columns": "design_columns.json",
    "joint_shear": "joint_shear.json",
    "columns_100_30": "columns_100_30.json",
}


def validate_table_json(path: str | Path, section_key: str) -> str | None:
    """Return an error message unless *path* is a compatible civilTools table grid."""
    if section_key not in REFRESHABLE_SECTIONS:
        return "This report section does not support a saved table JSON."
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Could not read JSON: {exc}"
    required = {"row", "col", "text"}
    if not isinstance(data, list) or not data:
        return "The file is not a civilTools table result."
    if any(not isinstance(cell, dict) or not required.issubset(cell) for cell in data):
        return "The file is not a civilTools colored-grid JSON."
    return None


def _open_file(path: Path) -> None:
    """Open a file with the default OS application."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])



class ReportDialog(QDialog):
    """Report configuration + generation dialog."""

    def __init__(self, etabs, building=None, settings: Settings | None = None, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._building = building
        self._settings = settings or Settings()
        self._worker = None
        self.result = None  # not used as table command
        self._updating_sources = False
        self._browse_buttons: dict[str, QPushButton] = {}

        self._model_path = self._get_model_path()
        self._model_sources = (
            ModelReportSources.load_for_model(self._model_path)
            if self._model_path is not None
            else ModelReportSources()
        )
        self._section_json_paths = dict(self._model_sources.section_json_paths)
        self._report_preferences = self._settings.get("report", {})

        # Try to get building from parent main window
        if self._building is None and parent is not None:
            self._building = getattr(parent, "_building", None)

        self.setWindowTitle("Generate Structural Report")
        self.setMinimumWidth(520)
        self.resize(560, 680)
        set_dialog_icon(self, "word.svg")

        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Output directory ────────────────────────────────────────
        dir_group = QGroupBox("Output Directory")
        dir_lay = QHBoxLayout(dir_group)
        self._dir_edit = QLabel()
        self._dir_edit.setWordWrap(True)
        default_dir = str(Path.home() / "Documents" / "civiltools_reports")
        try:
            model_file = self._etabs.SapModel.GetModelFilename()
            if model_file:
                default_dir = str(Path(model_file).parent)
        except Exception:
            pass
        self._output_dir = default_dir
        self._dir_edit.setText(default_dir)
        dir_lay.addWidget(self._dir_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_dir)
        dir_lay.addWidget(browse_btn)
        layout.addWidget(dir_group)

        # ── Output + workers ────────────────────────────────────────
        opt_group = QGroupBox("Options")
        opt_lay = QHBoxLayout(opt_group)

        opt_lay.addWidget(QLabel("Output: Word (DOCX)"))

        opt_lay.addWidget(QLabel("Workers:"))
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 16)
        self._workers_spin.setValue(self._report_preferences.get("workers", 4))
        self._workers_spin.setToolTip("Parallel processes for image rendering")
        opt_lay.addWidget(self._workers_spin)

        # TOC check
        self._toc_check = QCheckBox("Table of Contents")
        self._toc_check.setChecked(
            self._report_preferences.get("include_table_of_contents", True)
        )
        opt_lay.addWidget(self._toc_check)

        layout.addWidget(opt_group)

        # ── Unified report sections and sources ────────────────────
        sec_group = QGroupBox("Report Sections and Sources")
        sec_lay = QVBoxLayout(sec_group)
        section_buttons = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        clear_all_btn = QPushButton("Clear All")
        select_all_btn.clicked.connect(lambda: self._set_include_checks(True))
        clear_all_btn.clicked.connect(lambda: self._set_include_checks(False))
        section_buttons.addWidget(select_all_btn)
        section_buttons.addWidget(clear_all_btn)
        section_buttons.addStretch()
        sec_lay.addLayout(section_buttons)

        self._fallback_check = QCheckBox("Read from ETABS if saved result is missing")
        self._fallback_check.setChecked(
            self._report_preferences.get("fallback_to_etabs_if_missing", True)
        )
        self._fallback_check.toggled.connect(self._refresh_all_source_statuses)
        sec_lay.addWidget(self._fallback_check)

        self._sections = QTreeWidget()
        self._sections.setColumnCount(5)
        self._sections.setHeaderLabels(
            ["Include", "Section", "Read from ETABS", "Source", ""]
        )
        self._sections.setRootIsDecorated(False)
        self._sections.setAlternatingRowColors(True)
        self._sections.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sections.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._sections.setDefaultDropAction(Qt.DropAction.MoveAction)
        header = self._sections.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._populate_sections()
        self._sections.itemChanged.connect(self._on_section_changed)
        sec_lay.addWidget(self._sections)
        layout.addWidget(sec_group)

        # ── Progress + log ──────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        self._log.setPlaceholderText("Generation log…")
        layout.addWidget(self._log)

        # ── Buttons ─────────────────────────────────────────────────
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        self._gen_btn = QPushButton("Generate Report")
        self._gen_btn.setDefault(True)
        self._gen_btn.clicked.connect(self._on_generate)
        btn_lay.addWidget(self._gen_btn)

        self._cancel_btn = QPushButton("Close")
        self._cancel_btn.clicked.connect(self.reject)
        btn_lay.addWidget(self._cancel_btn)
        layout.addLayout(btn_lay)

    # ── Slots ───────────────────────────────────────────────────────

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._output_dir
        )
        if d:
            self._output_dir = d
            self._dir_edit.setText(d)

    def _on_generate(self):
        """Build config from UI and launch the report worker."""
        config = self._build_config()
        self._persist_preferences()

        # Get building if not already provided
        if self._building is None:
            self._building = self._get_building()

        # Disable UI
        self._gen_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._progress.setValue(0)
        self._log.clear()
        self._log.append("Starting report generation…")
        QApplication.processEvents()

        # Launch worker
        from civiltools.report.report_worker import ReportWorker

        self._worker = ReportWorker(
            etabs=self._etabs,
            building=self._building,
            config=config,
            output_dir=self._output_dir,
            max_workers=self._workers_spin.value(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._log.append(f"[{pct:3d}%] {msg}")
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
        QApplication.processEvents()

    def _on_finished(self, docx_path: str, _unused_pdf_path: str):
        self._progress.setValue(100)
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)

        parts = []
        if docx_path:
            parts.append(f"Word: {docx_path}")
        msg = "Report generated successfully!\n\n" + "\n".join(parts)
        self._log.append("\n" + msg)

        answer = QMessageBox.information(
            self, "Report Complete",
            msg + "\n\nOpen file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if docx_path:
                _open_file(Path(docx_path))

    def _on_error(self, tb: str):
        self._progress.setValue(0)
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._log.append(f"\nERROR:\n{tb}")
        QMessageBox.critical(
            self, "Report Error",
            f"Report generation failed:\n\n{tb[:600]}",
        )

    def _get_model_path(self) -> Path | None:
        try:
            model_file = self._etabs.SapModel.GetModelFilename()
        except Exception:
            return None
        return Path(model_file) if model_file else None

    def _populate_sections(self) -> None:
        self._updating_sources = True
        language = self._report_preferences.get("language", "en")
        title_key = "title_fa" if language in {"fa", "both"} else "title_en"
        for section in self._report_preferences.get("sections", []):
            key = section["key"]
            item = QTreeWidgetItem(["", section[title_key], "", "", ""])
            item.setData(1, Qt.ItemDataRole.UserRole, key)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            item.setCheckState(
                0,
                Qt.CheckState.Checked if section["included"] else Qt.CheckState.Unchecked,
            )
            item.setCheckState(
                2,
                Qt.CheckState.Checked
                if section["read_from_etabs"]
                else Qt.CheckState.Unchecked,
            )
            self._sections.addTopLevelItem(item)
            browse = QPushButton("Browse...")
            browse.clicked.connect(
                lambda checked=False, section_key=key: self._browse_json(section_key)
            )
            self._browse_buttons[key] = browse
            self._sections.setItemWidget(item, 4, browse)
        self._updating_sources = False
        self._refresh_all_source_statuses()

    def _section_item(self, section_key: str) -> QTreeWidgetItem | None:
        for index in range(self._sections.topLevelItemCount()):
            item = self._sections.topLevelItem(index)
            if item.data(1, Qt.ItemDataRole.UserRole) == section_key:
                return item
        return None

    def _set_include_checks(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self._sections.topLevelItemCount()):
            self._sections.topLevelItem(index).setCheckState(0, state)

    def _on_section_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating_sources or column != 2:
            return
        self._refresh_source_status(item.data(1, Qt.ItemDataRole.UserRole))

    def _default_json_path(self, section_key: str) -> Path | None:
        if self._model_path is None or section_key not in _RESULT_FILENAMES:
            return None
        return (
            self._model_path.parent
            / f"{self._model_path.stem}_table_results"
            / _RESULT_FILENAMES[section_key]
        )

    def _effective_json_path(self, section_key: str) -> Path | None:
        configured = self._section_json_paths.get(section_key)
        if configured and Path(configured).is_file():
            return Path(configured)
        default = self._default_json_path(section_key)
        return default if default is not None and default.is_file() else None

    def _refresh_source_status(self, section_key: str) -> None:
        item = self._section_item(section_key)
        if item is None:
            return
        read_from_etabs = item.checkState(2) == Qt.CheckState.Checked
        source_path = self._effective_json_path(section_key)
        if read_from_etabs:
            status = "ETABS"
        elif source_path is not None:
            status = f"Saved JSON: {source_path.name}"
        elif self._fallback_check.isChecked():
            status = "ETABS fallback"
        else:
            status = "Unavailable"
        item.setText(3, status)
        button = self._browse_buttons.get(section_key)
        if button is not None:
            button.setEnabled(section_key in REFRESHABLE_SECTIONS and not read_from_etabs)

    def _refresh_all_source_statuses(self) -> None:
        for index in range(self._sections.topLevelItemCount()):
            item = self._sections.topLevelItem(index)
            self._refresh_source_status(item.data(1, Qt.ItemDataRole.UserRole))

    def _browse_json(self, section_key: str) -> None:
        start_dir = str(self._model_path.parent) if self._model_path else str(Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select civilTools Result JSON",
            start_dir,
            "JSON Files (*.json)",
        )
        if selected:
            self._set_section_json_path(section_key, selected, show_error=True)

    def _set_section_json_path(
        self,
        section_key: str,
        path: str | Path,
        *,
        show_error: bool = False,
    ) -> bool:
        error = validate_table_json(path, section_key)
        if error:
            if show_error:
                QMessageBox.warning(self, "Invalid Result JSON", error)
            return False
        self._section_json_paths[section_key] = str(Path(path))
        self._refresh_source_status(section_key)
        return True

    def _section_records(self) -> list[dict]:
        existing = {
            section["key"]: section for section in self._report_preferences.get("sections", [])
        }
        records = []
        for index in range(self._sections.topLevelItemCount()):
            item = self._sections.topLevelItem(index)
            key = item.data(1, Qt.ItemDataRole.UserRole)
            record = dict(existing[key])
            record["included"] = item.checkState(0) == Qt.CheckState.Checked
            record["read_from_etabs"] = item.checkState(2) == Qt.CheckState.Checked
            records.append(record)
        return records

    def _build_config(self) -> ReportConfig:
        sections = self._section_records()
        section_order = [section["key"] for section in sections]
        disabled = [section["key"] for section in sections if not section["included"]]
        refresh = [
            section["key"]
            for section in sections
            if section["included"]
            and section["read_from_etabs"]
            and section["key"] in REFRESHABLE_SECTIONS
        ]
        return ReportConfig(
            language=self._report_preferences.get("language", "en"),
            output_format="docx",
            section_order=section_order,
            disabled_sections=disabled,
            refresh_sections=refresh,
            section_sources={
                section["key"]: (
                    "etabs" if section["read_from_etabs"] else "json"
                )
                for section in sections
            },
            section_json_paths=dict(self._section_json_paths),
            section_titles={
                section["key"]: {
                    "en": section["title_en"],
                    "fa": section["title_fa"],
                }
                for section in sections
            },
            fallback_to_etabs_if_missing=self._fallback_check.isChecked(),
            include_table_of_contents=self._toc_check.isChecked(),
        )

    def _persist_preferences(self) -> None:
        report = dict(self._report_preferences)
        report.update(
            {
                "workers": self._workers_spin.value(),
                "include_table_of_contents": self._toc_check.isChecked(),
                "fallback_to_etabs_if_missing": self._fallback_check.isChecked(),
                "sections": self._section_records(),
            }
        )
        self._settings.update({"report": report})
        self._report_preferences = self._settings.get("report")
        if self._model_path is not None:
            ModelReportSources(
                section_json_paths=dict(self._section_json_paths)
            ).save_for_model(self._model_path)

    # ── Building creation ───────────────────────────────────────────

    def _get_building(self):
        """Create Building object from ETABS settings."""
        try:
            from civiltools.etabs.config import (
                current_building_from_config,
                get_settings_from_etabs,
            )
            d = get_settings_from_etabs(self._etabs)
            if not d:
                return None
            return current_building_from_config(d)
        except Exception:
            return None
