"""
Background report worker — thin Qt wrapper around etabs_api.ReportGenerator.

All heavy logic (data extraction, parallel image rendering, document
generation) lives in ``etabs_api.report.report_generator.ReportGenerator``.
This module only adds the Qt Signal/Slot glue needed to keep the GUI
responsive.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from etabs_api.report.report_config import ReportConfig
from etabs_api.report.report_generator import ReportGenerator


class ReportWorker(QThread):
    """QThread wrapper around ReportGenerator.

    Signals
    -------
    progress(int, str)
        Overall percent (0–100) and human-readable message.
    finished(str, str)
        Paths to DOCX and PDF files (either may be empty).
    error(str)
        Traceback string on failure.
    """

    progress = Signal(int, str)
    finished = Signal(str, str)
    error = Signal(str)

    def __init__(
        self,
        etabs,
        building=None,
        config: ReportConfig | None = None,
        output_dir: str | Path = ".",
        max_workers: int = 4,
        dpi: int = 150,
        parent=None,
    ):
        super().__init__(parent)
        self._generator = ReportGenerator(
            etabs=etabs,
            building=building,
            config=config,
            output_dir=output_dir,
            max_workers=max_workers,
            dpi=dpi,
            on_progress=self.progress.emit,
            on_error=self.error.emit,
        )

    def run(self):
        docx_path, pdf_path = self._generator.generate()
        self.finished.emit(docx_path, pdf_path)
