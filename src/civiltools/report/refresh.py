"""Refresh selected cached report checks from a live ETABS model."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from civiltools.commands.columns_100_30 import Columns10030Command
from civiltools.commands.design_columns import DesignColumnsCheck
from civiltools.commands.drift import DriftCheck
from civiltools.commands.joint_shear import JointShearCheck
from civiltools.commands.torsion import TorsionCheck
from civiltools.report.report_config import ReportConfig, ResultManifest, model_fingerprint

log = logging.getLogger(__name__)

_SECTION_COMMANDS = {
    "drift": (DriftCheck, "drift"),
    "torsion": (TorsionCheck, "torsion"),
    "pmm_columns": (DesignColumnsCheck, "design_columns"),
    "joint_shear": (JointShearCheck, "joint_shear"),
    "columns_100_30": (Columns10030Command, "columns_100_30"),
}


def refresh_report_results(
    etabs: Any,
    config: ReportConfig,
    progress: Callable[[int, str], None] | None = None,
) -> None:
    """Rerun selected checks and replace their cached report tables."""
    selected = [key for key in config.refresh_sections if key in _SECTION_COMMANDS]
    if not selected:
        return

    model_path = _get_model_path(etabs)
    if model_path is None:
        log.warning("Cannot refresh report checks because the ETABS model path is unavailable")
        return

    results_dir = model_path.parent / f"{model_path.stem}_table_results"
    saved_params = _load_saved_params(model_path)
    total = len(selected)
    for index, section_key in enumerate(selected, start=1):
        command_class, command_id = _SECTION_COMMANDS[section_key]
        params = dict(saved_params.get(command_id, {}))
        params.update(config.refresh_params.get(section_key, {}))
        if command_id in config.refresh_params:
            params.update(config.refresh_params[command_id])

        if progress:
            progress(
                int((index - 1) * 100 / total),
                f"Refreshing {command_class.label}...",
            )
        try:
            result = command_class.execute(etabs, params)
            if result.error:
                log.warning("Could not refresh %s: %s", section_key, result.error)
                continue
            rows, headers = _result_rows(result)
            if not headers or not rows:
                log.warning("Refresh returned no table for %s", section_key)
                continue
            output = results_dir / f"{command_id}.json"
            _write_table(output, headers, rows, section_key)
            display_name = result.title or command_class.label
            ResultManifest(results_dir).register_table(
                output.name,
                {"en": display_name, "fa": display_name},
                category="checks",
                section_key=section_key,
                source_model_fingerprint=model_fingerprint(model_path),
            )
        except Exception as exc:
            log.warning("Could not refresh %s: %s", section_key, exc)
        finally:
            if progress:
                progress(int(index * 100 / total), f"Finished {command_class.label}.")


def _get_model_path(etabs: Any) -> Path | None:
    try:
        value = etabs.SapModel.GetModelFilename()
    except Exception:
        return None
    return Path(value) if value else None


def _load_saved_params(model_path: Path) -> dict[str, dict[str, Any]]:
    path = model_path.parent / f"{model_path.stem}_table_results" / "refresh_params.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _result_rows(result) -> tuple[list[list[Any]], list[str]]:
    if result.dataframe is not None:
        headers = [str(column) for column in result.dataframe.columns]
        return result.dataframe.values.tolist(), headers
    return result.rows, result.headers


_LOW = "#00ffff"
_INTERMEDIATE = "#ffff7f"
_HIGH = "#ff557f"


def _write_table(
    path: Path,
    headers: list[str],
    rows: list[list[Any]],
    section_key: str,
) -> None:
    data = [
        {"row": 0, "col": column, "text": _display_text(header), "color": ""}
        for column, header in enumerate(headers)
    ]
    for row_number, row in enumerate(rows, start=1):
        data.extend(
            {
                "row": row_number,
                "col": column,
                "text": _format_display_text(section_key, headers, row, column, value),
                "color": _cell_color(section_key, headers, row, column),
            }
            for column, value in enumerate(row)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def _format_display_text(
    section_key: str,
    headers: list[str],
    row: list[Any],
    column: int,
    value: Any,
) -> str:
    header = headers[column] if column < len(headers) else ""
    precision = None
    if section_key == "drift" and header in {"Max Drift", "Avg Drift", "Allowable Drift"}:
        precision = 4
    elif section_key == "torsion" and header in {"Max Drift", "Avg Drift", "Ratio"}:
        precision = 4
    elif section_key == "joint_shear" and header in {
        "JSMajRatio", "JSMinRatio", "BCMajRatio", "BCMinRatio",
        "Ratio", "Ratio_JS (ETABS)", "Ratio_BC (ETABS)",
    }:
        precision = 2
    elif section_key == "pmm_columns" and header == "PMMRatio":
        precision = 3
    if precision is not None:
        try:
            return f"{float(value):.{precision}f}"
        except (TypeError, ValueError):
            pass
    return _display_text(value)


def _cell_color(section_key: str, headers: list[str], row: list[Any], column: int) -> str:
    header = headers[column] if column < len(headers) else ""
    ratio = _number(row, headers, "Ratio")
    if section_key == "drift" and header in {"Max Drift", "Avg Drift"}:
        value = _number(row, headers, header)
        allowable = _number(row, headers, "Allowable Drift")
        return _HIGH if value is not None and allowable is not None and value > allowable else _LOW
    if section_key == "torsion" and ratio is not None:
        return _LOW if ratio <= 1.2 else _INTERMEDIATE if ratio < 1.4 else _HIGH
    if section_key == "joint_shear" and header in {
        "JSMajRatio", "JSMinRatio", "BCMajRatio", "BCMinRatio",
        "Ratio", "Ratio_JS (ETABS)", "Ratio_BC (ETABS)",
    }:
        value = _number(row, headers, header)
        if value is None:
            return _INTERMEDIATE
        return _LOW if value <= 1.0 else _HIGH
    if section_key == "pmm_columns" and header == "PMMRatio":
        value = _number(row, headers, header)
        return _HIGH if value is not None and value > 1.0 else _LOW if value is not None else ""
    return ""


def _number(row: list[Any], headers: list[str], header: str) -> float | None:
    if header not in headers:
        return None
    try:
        return float(row[headers.index(header)])
    except (IndexError, TypeError, ValueError):
        return None


def _display_text(value: Any) -> str:
    return "" if value is None else str(value)
