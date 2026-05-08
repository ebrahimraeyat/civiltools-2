"""Copy beams/columns between two ETABS models with progress feedback."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult
from civiltools.etabs.connection import EtabsConnection
from civiltools.gui.helpers import set_dialog_icon


class CopyWorker(QThread):
    """Run copy operation in a background thread."""

    progress = Signal(int, int, str)  # current, total, frame_name
    finished = Signal(list)  # sections with corner-bar differences
    error = Signal(str)

    def __init__(
        self,
        source_etabs: Any,
        target_etabs: Any,
        selection: bool,
        overwrite: bool,
        include_beams: bool,
        include_columns: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._source = source_etabs
        self._target = target_etabs
        self._selection = selection
        self._overwrite = overwrite
        self._include_beams = include_beams
        self._include_columns = include_columns

    def run(self):
        try:
            from etabs_api.frame_obj import copy_elements_from_one_model_to_another

            result = copy_elements_from_one_model_to_another(
                source_etabs=self._source,
                target_etabs=self._target,
                selection=self._selection,
                overwrite=self._overwrite,
                include_beams=self._include_beams,
                include_columns=self._include_columns,
                progress_callback=lambda i, t, n: self.progress.emit(i, t, n),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class _ModelPanel(QGroupBox):
    """Reusable panel for source/target model selection and connection."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._conn = EtabsConnection()
        self._instances: list[dict] = []

        lay = QGridLayout(self)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Attach to running instance",
            "Open EDB file",
        ])

        self.instance_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh")

        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Select .EDB file...")
        self.browse_btn = QPushButton("Browse...")

        self.connect_btn = QPushButton("Connect")
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet("color: #888;")

        lay.addWidget(QLabel("Mode:"), 0, 0)
        lay.addWidget(self.mode_combo, 0, 1, 1, 2)

        lay.addWidget(QLabel("Instance:"), 1, 0)
        lay.addWidget(self.instance_combo, 1, 1)
        lay.addWidget(self.refresh_btn, 1, 2)

        lay.addWidget(QLabel("EDB File:"), 2, 0)
        lay.addWidget(self.file_edit, 2, 1)
        lay.addWidget(self.browse_btn, 2, 2)

        lay.addWidget(self.connect_btn, 3, 1)
        lay.addWidget(self.status_label, 3, 2)

        self.mode_combo.currentIndexChanged.connect(self._update_mode_ui)
        self.refresh_btn.clicked.connect(self.refresh_instances)
        self.browse_btn.clicked.connect(self._browse_file)

        self._update_mode_ui()
        self.refresh_instances()

    @property
    def etabs(self) -> Any:
        return self._conn.etabs

    @property
    def is_connected(self) -> bool:
        return self._conn.is_connected

    def refresh_instances(self):
        self.instance_combo.clear()
        self._instances = self._conn.list_instances("ETABS")
        for inst in self._instances:
            title = inst.get("title") or f"ETABS PID {inst['pid']}"
            self.instance_combo.addItem(f"{title} (PID {inst['pid']})", inst["pid"])
        if not self._instances:
            self.instance_combo.addItem("No running ETABS instances")

    def connect_selected(self) -> tuple[bool, str]:
        mode_is_attach = self.mode_combo.currentIndex() == 0
        if mode_is_attach:
            if not self._instances:
                return False, "No running ETABS instances found."
            pid = self.instance_combo.currentData()
            if pid is None:
                return False, "Please select a running ETABS instance."
            ok = self._conn.connect_pid(int(pid), software="ETABS")
            if not ok:
                return False, self._conn.last_error or "Failed to connect to selected instance."
            model = Path(self._conn.model_path).name if self._conn.model_path else "(unsaved model)"
            return True, f"Connected to PID {pid} — {model}"

        model_path = self.file_edit.text().strip()
        if not model_path:
            return False, "Please select an EDB file."
        ok = self._conn.connect_file(model_path, software="ETABS")
        if not ok:
            return False, self._conn.last_error or "Failed to open EDB file."
        return True, f"Opened {Path(model_path).name}"

    def _browse_file(self):
        start = self.file_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Select ETABS EDB File", start, "ETABS Model (*.edb *.EDB)")
        if path:
            self.file_edit.setText(path)

    def _update_mode_ui(self):
        mode_is_attach = self.mode_combo.currentIndex() == 0
        self.instance_combo.setEnabled(mode_is_attach)
        self.refresh_btn.setEnabled(mode_is_attach)
        self.file_edit.setEnabled(not mode_is_attach)
        self.browse_btn.setEnabled(not mode_is_attach)


class CopyElementsDialog(QDialog):
    """Dialog for copying beams/columns from source model to target model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._result: CommandResult | None = None
        self._worker: Optional[CopyWorker] = None
        self._t0: float = 0.0

        self.setWindowTitle("Copy Elements Between ETABS Models")
        self.setMinimumWidth(760)
        set_dialog_icon(self, "transfer_loads_between_two_files.svg")

        root = QVBoxLayout(self)

        self.source_panel = _ModelPanel("Source Model", self)
        self.target_panel = _ModelPanel("Target Model", self)

        root.addWidget(self.source_panel)
        root.addWidget(self.target_panel)

        conn_row = QHBoxLayout()
        self.connect_source_btn = QPushButton("Connect Source")
        self.connect_target_btn = QPushButton("Connect Target")
        conn_row.addWidget(self.connect_source_btn)
        conn_row.addWidget(self.connect_target_btn)
        conn_row.addStretch()
        root.addLayout(conn_row)

        options_box = QGroupBox("Copy Options")
        options_lay = QHBoxLayout(options_box)
        self.selection_only_chk = QCheckBox("Selection only")
        self.overwrite_chk = QCheckBox("Overwrite existing")
        self.include_beams_chk = QCheckBox("Beams")
        self.include_columns_chk = QCheckBox("Columns")
        self.include_beams_chk.setChecked(True)
        self.include_columns_chk.setChecked(True)
        options_lay.addWidget(self.selection_only_chk)
        options_lay.addWidget(self.overwrite_chk)
        options_lay.addWidget(self.include_beams_chk)
        options_lay.addWidget(self.include_columns_chk)
        options_lay.addStretch()
        root.addWidget(options_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #555;")
        root.addWidget(self.status)

        error_box = QGroupBox("Messages")
        error_lay = QVBoxLayout(error_box)
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setMaximumHeight(120)
        error_lay.addWidget(self.error_text)
        root.addWidget(error_box)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("Start Copy")
        self.copy_btn.setDefault(True)
        self.close_btn = QPushButton("Close")
        btn_row.addStretch()
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

        self.connect_source_btn.clicked.connect(self._connect_source)
        self.connect_target_btn.clicked.connect(self._connect_target)
        self.copy_btn.clicked.connect(self._start_copy)
        self.close_btn.clicked.connect(self.reject)

    @property
    def result(self) -> CommandResult | None:
        return self._result

    def _connect_source(self):
        self._connect_panel(self.source_panel)

    def _connect_target(self):
        self._connect_panel(self.target_panel)

    def _connect_panel(self, panel: _ModelPanel):
        self.progress.setRange(0, 0)
        self.status.setText("Connecting...")
        self.status.repaint()

        ok, msg = panel.connect_selected()

        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        if ok:
            panel.status_label.setText(msg)
            panel.status_label.setStyleSheet("color: #006400; font-weight: 600;")
            self.status.setText(msg)
        else:
            panel.status_label.setText(msg)
            panel.status_label.setStyleSheet("color: #b00020;")
            self._append_error(msg)
            self.status.setText("Connection failed")

    def _start_copy(self):
        if not self.source_panel.is_connected:
            QMessageBox.warning(self, "Source Not Connected", "Connect the source model first.")
            return
        if not self.target_panel.is_connected:
            QMessageBox.warning(self, "Target Not Connected", "Connect the target model first.")
            return
        if not (self.include_beams_chk.isChecked() or self.include_columns_chk.isChecked()):
            QMessageBox.warning(self, "Invalid Options", "Select at least one of Beams or Columns.")
            return

        self.error_text.clear()
        self.copy_btn.setEnabled(False)
        self.connect_source_btn.setEnabled(False)
        self.connect_target_btn.setEnabled(False)
        self.progress.setValue(0)
        self._t0 = time.monotonic()
        self.status.setText("Copy started...")

        self._worker = CopyWorker(
            source_etabs=self.source_panel.etabs,
            target_etabs=self.target_panel.etabs,
            selection=self.selection_only_chk.isChecked(),
            overwrite=self.overwrite_chk.isChecked(),
            include_beams=self.include_beams_chk.isChecked(),
            include_columns=self.include_columns_chk.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, frame_name: str):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress.setValue(max(0, min(100, pct)))
            elapsed = max(0.001, time.monotonic() - self._t0)
            eta = int((elapsed / current) * (total - current)) if current > 0 else 0
            self.status.setText(f"Copying {current}/{total}: {frame_name} | ETA ~{eta}s")
        else:
            self.progress.setValue(0)
            self.status.setText("No matching frames to copy.")

    def _on_finished(self, diff_sections: list):
        self.progress.setValue(100)
        self.copy_btn.setEnabled(True)
        self.connect_source_btn.setEnabled(True)
        self.connect_target_btn.setEnabled(True)

        if diff_sections:
            self._append_error(
                "Sections needing manual review (corner bars differ):\n"
                + "\n".join(sorted(set(diff_sections)))
            )

        try:
            import pandas as pd

            df = pd.DataFrame({"Section": sorted(set(diff_sections))})
            if not df.empty:
                df["NeedsManualReview"] = True
            self._result = CommandResult(
                title="Copy Elements",
                dataframe=df,
                ok=True,
                summary=f"Copy completed. Sections requiring review: {len(set(diff_sections))}",
            )
        except Exception:
            self._result = CommandResult(
                title="Copy Elements",
                headers=["Section"],
                rows=[[s] for s in sorted(set(diff_sections))],
                ok=True,
                summary=f"Copy completed. Sections requiring review: {len(set(diff_sections))}",
            )

        self.status.setText("Copy completed.")
        self.accept()

    def _on_error(self, message: str):
        self.copy_btn.setEnabled(True)
        self.connect_source_btn.setEnabled(True)
        self.connect_target_btn.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Copy failed")
        self._append_error(message)
        QMessageBox.critical(self, "Copy Error", message)

    def _append_error(self, text: str):
        self.error_text.append(text)
        sb = self.error_text.verticalScrollBar()
        sb.setValue(sb.maximum())
