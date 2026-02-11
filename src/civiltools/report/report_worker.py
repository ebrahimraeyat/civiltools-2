"""
Background report worker — orchestrates data extraction, parallel
image rendering, and document generation.

Uses a QThread to keep the GUI responsive and ProcessPoolExecutor
to parallelise heavyweight matplotlib rendering across CPU cores.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from civiltools.report.report_config import ReportConfig
from civiltools.report.data_extractor import (
    ReportData,
    extract_report_data,
    FrameInfo,
    AreaInfo,
    LoadSetDef,
)

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Top-level render functions  (must be importable / picklable)
# ═══════════════════════════════════════════════════════════════════════════

def _render_plan(frames: list[FrameInfo], story: str, dpi: int = 150) -> bytes:
    """Process-safe wrapper for plan_renderer.render_story_plan."""
    from civiltools.report.plan_renderer import render_story_plan
    return render_story_plan(frames, story, dpi)


def _render_area(
    areas: list[AreaInfo],
    load_set_defs: dict[str, LoadSetDef],
    frames: list[FrameInfo],
    story: str,
    dpi: int = 150,
) -> bytes:
    """Process-safe wrapper for area_renderer.render_area_load_plan."""
    from civiltools.report.area_renderer import render_area_load_plan
    return render_area_load_plan(areas, load_set_defs, frames, story, dpi)


# ═══════════════════════════════════════════════════════════════════════════
# ReportWorker
# ═══════════════════════════════════════════════════════════════════════════

class ReportWorker(QThread):
    """Background thread that generates Word + PDF reports.

    Signals
    -------
    progress(int, str)
        Overall percent (0–100), human-readable message.
    finished(str, str)
        Path to DOCX, path to PDF  (either may be empty if format
        was disabled in config).
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
        self.etabs = etabs
        self.building = building
        self.config = config or ReportConfig(language="en")
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.dpi = dpi

    # ──────────────────────────────────────────────────────────────────
    def run(self):  # noqa: C901
        try:
            self._generate()
        except Exception:
            self.error.emit(traceback.format_exc())

    def _generate(self):
        # ── Phase 1: Data extraction (sequential COM) ─────────────
        self.progress.emit(0, "Phase 1 — Extracting data from ETABS…")

        def _ext_progress(pct, msg):
            # Map 0-90 → 0-30 overall
            self.progress.emit(int(pct * 0.33), f"Data: {msg}")

        data = extract_report_data(
            self.etabs,
            self.building,
            progress=_ext_progress,
        )

        # ── Phase 2: Parallel image rendering ─────────────────────
        self.progress.emit(33, "Phase 2 — Rendering images…")

        total_images = len(data.frame_data) + len(data.area_data)
        done_images = 0

        if total_images > 0:
            with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {}

                # Story plan images
                for story, frames in data.frame_data.items():
                    fut = pool.submit(_render_plan, frames, story, self.dpi)
                    futures[fut] = ("plan", story)

                # Area load images
                for story, areas in data.area_data.items():
                    ctx_frames = data.frame_data.get(story, [])
                    fut = pool.submit(
                        _render_area, areas,
                        dict(data.load_set_defs),
                        ctx_frames, story, self.dpi,
                    )
                    futures[fut] = ("area", story)

                for fut in as_completed(futures):
                    kind, story = futures[fut]
                    try:
                        img_bytes = fut.result()
                        if kind == "plan":
                            data.story_plan_images[story] = img_bytes
                        else:
                            data.area_load_images[story] = img_bytes
                    except Exception as exc:
                        log.warning("Image render failed for %s/%s: %s",
                                    kind, story, exc)

                    done_images += 1
                    pct = 33 + int(34 * done_images / max(total_images, 1))
                    self.progress.emit(pct, f"Images: {story} ({kind})")

        # ── Phase 3: Document generation ──────────────────────────
        self.progress.emit(67, "Phase 3 — Generating documents…")

        docx_path = ""
        pdf_path = ""
        fmt = self.config.output_format

        stem = (data.project_name or "report").replace(" ", "_").replace("/", "_").replace("\\", "_")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if fmt in ("docx", "both"):
            self.progress.emit(70, "Writing Word document…")
            from civiltools.report.docx_report import create_docx_report
            out = self.output_dir / f"{stem}_report.docx"
            create_docx_report(data, self.config, out)
            docx_path = str(out)

        if fmt in ("pdf", "both"):
            self.progress.emit(85, "Writing PDF document…")
            from civiltools.report.pdf_report import create_pdf_report
            out = self.output_dir / f"{stem}_report.pdf"
            create_pdf_report(data, self.config, out)
            pdf_path = str(out)

        self.progress.emit(100, "Report generation complete!")
        self.finished.emit(docx_path, pdf_path)
