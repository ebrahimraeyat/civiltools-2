"""
Report generation dialog — choose format, sections, output directory,
then run the ReportWorker (QThread + ProcessPoolExecutor) to generate
Word and/or PDF reports with parallel image rendering.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from civiltools.gui.helpers import set_dialog_icon
from civiltools.report.report_config import ReportConfig, SECTION_NAMES


def _open_file(path: Path) -> None:
    """Open a file with the default OS application."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])



# ── Format maps ─────────────────────────────────────────────────────

_FORMAT_MAP = {
    "Word + PDF": "both",
    "Word (DOCX) only": "docx",
    "PDF only": "pdf",
}


class ReportDialog(QDialog):
    """Report configuration + generation dialog."""

    def __init__(self, etabs, building=None, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._building = building
        self._worker = None
        self.result = None  # not used as table command

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

        # ── Format + workers ────────────────────────────────────────
        opt_group = QGroupBox("Options")
        opt_lay = QHBoxLayout(opt_group)

        opt_lay.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(list(_FORMAT_MAP.keys()))
        opt_lay.addWidget(self._fmt_combo)

        opt_lay.addWidget(QLabel("Workers:"))
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 16)
        self._workers_spin.setValue(min(4, os.cpu_count() or 4))
        self._workers_spin.setToolTip("Parallel processes for image rendering")
        opt_lay.addWidget(self._workers_spin)

        # TOC check
        self._toc_check = QCheckBox("Table of Contents")
        self._toc_check.setChecked(True)
        opt_lay.addWidget(self._toc_check)

        layout.addWidget(opt_group)

        # ── Section list (checkable, drag-reorderable) ──────────────
        sec_group = QGroupBox("Report Sections (drag to reorder)")
        sec_lay = QVBoxLayout(sec_group)
        self._order_list = QListWidget()
        self._order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        for key in ReportConfig().section_order:
            names = SECTION_NAMES.get(key, {})
            display = names.get("en", key)
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            item.setCheckState(Qt.CheckState.Checked)
            self._order_list.addItem(item)

        sec_lay.addWidget(self._order_list)
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
        # Build config
        config = ReportConfig(
            language="en",
            output_format=_FORMAT_MAP.get(self._fmt_combo.currentText(), "both"),
            include_table_of_contents=self._toc_check.isChecked(),
        )

        # Section order
        active = []
        disabled = []
        for i in range(self._order_list.count()):
            item = self._order_list.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            if item.checkState() == Qt.CheckState.Checked:
                active.append(key)
            else:
                disabled.append(key)
        config.section_order = active
        config.disabled_sections = disabled

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

    def _on_finished(self, docx_path: str, pdf_path: str):
        self._progress.setValue(100)
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)

        parts = []
        if docx_path:
            parts.append(f"Word: {docx_path}")
        if pdf_path:
            parts.append(f"PDF:  {pdf_path}")

        msg = "Report generated successfully!\n\n" + "\n".join(parts)
        self._log.append("\n" + msg)

        answer = QMessageBox.information(
            self, "Report Complete",
            msg + "\n\nOpen file(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            for p in (docx_path, pdf_path):
                if p:
                    _open_file(Path(p))

    def _on_error(self, tb: str):
        self._progress.setValue(0)
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._log.append(f"\nERROR:\n{tb}")
        QMessageBox.critical(
            self, "Report Error",
            f"Report generation failed:\n\n{tb[:600]}",
        )

    # ── Building creation ───────────────────────────────────────────

    def _get_building(self):
        """Create Building object from ETABS settings."""
        try:
            from civiltools.etabs.config import (
                get_settings_from_etabs,
                current_building_from_config,
            )
            d = get_settings_from_etabs(self._etabs)
            if not d:
                return None
            return current_building_from_config(d)
        except Exception:
            return None
