"""Qt-free DOCX report generator for civilTools.

Orchestrates ETABS data extraction, parallel image rendering, and Word document
generation without depending on PySide6.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from civiltools.report.data_extractor import (
    AreaInfo,
    FrameInfo,
    LoadSetDef,
    extract_report_data,
)
from civiltools.report.report_config import ReportConfig

log = logging.getLogger(__name__)


def _ensure_output_file_writable(path: Path) -> None:
    """Raise a friendly error if an existing Word document is locked."""
    if not path.exists():
        return
    try:
        with path.open("ab"):
            pass
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot write the Word report because the file is open or locked: {path}\n"
            "Please close it in Word and try again."
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Cannot access the Word report: {path}\n"
            "Please close any application using it and try again."
        ) from exc


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


class ReportGenerator:
    """Qt-free orchestrator for generating DOCX structural reports."""

    def __init__(
        self,
        etabs: Any,
        building: Any = None,
        config: ReportConfig | None = None,
        output_dir: str | Path = ".",
        max_workers: int = 4,
        dpi: int = 150,
        on_progress: Callable[[int, str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.etabs = etabs
        self.building = building
        self.config = config or ReportConfig(language="en", output_format="docx")
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.dpi = dpi
        self.on_progress = on_progress
        self.on_error = on_error

    def generate(self) -> tuple[str, str]:
        """Run the report pipeline and return ``(docx_path, "")``."""
        try:
            return self._generate()
        except Exception:
            traceback_text = traceback.format_exc()
            log.error("Report generation failed:\n%s", traceback_text)
            if self.on_error:
                self.on_error(traceback_text)
                return "", ""
            raise

    def generate_async(self) -> threading.Thread:
        """Run report generation in a background thread."""
        thread = threading.Thread(target=self.generate, name="ReportGenerator", daemon=True)
        thread.start()
        return thread

    def _prog(self, percent: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(percent, message)
        else:
            log.info("[%3d%%] %s", percent, message)

    def _generate(self) -> tuple[str, str]:
        self._prog(0, "Phase 1 - Extracting data from ETABS...")

        def extraction_progress(percent: int, message: str) -> None:
            self._prog(int(percent * 0.33), f"Data: {message}")

        data = extract_report_data(
            self.etabs,
            self.building,
            progress=extraction_progress,
        )

        self._prog(33, "Phase 2 - Rendering images...")
        self._render_images(data)

        self._prog(67, "Phase 3 - Generating Word document...")
        stem = (
            (data.project_name or "report")
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{stem}_report.docx"
        _ensure_output_file_writable(output_path)

        from civiltools.report.docx_report import create_docx_report

        create_docx_report(data, self.config, output_path)
        docx_path = str(output_path)
        log.info("DOCX saved: %s", docx_path)
        self._prog(100, "Report generation complete!")
        return docx_path, ""

    def _render_images(self, data) -> None:
        """Render story plans and area-load plans in parallel processes."""
        total_images = len(data.frame_data) + len(data.area_data)
        if total_images == 0:
            return

        completed_images = 0
        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures: dict = {}
            for story, frames in data.frame_data.items():
                future = pool.submit(_render_plan, frames, story, self.dpi)
                futures[future] = ("plan", story)

            for story, areas in data.area_data.items():
                context_frames = data.frame_data.get(story, [])
                future = pool.submit(
                    _render_area,
                    areas,
                    dict(data.load_set_defs),
                    context_frames,
                    story,
                    self.dpi,
                )
                futures[future] = ("area", story)

            for future in as_completed(futures):
                kind, story = futures[future]
                try:
                    image_bytes = future.result()
                    if kind == "plan":
                        data.story_plan_images[story] = image_bytes
                    else:
                        data.area_load_images[story] = image_bytes
                except Exception as exc:
                    log.warning("Image render failed for %s/%s: %s", kind, story, exc)

                completed_images += 1
                percent = 33 + int(34 * completed_images / total_images)
                self._prog(percent, f"Images: {story} ({kind})")
