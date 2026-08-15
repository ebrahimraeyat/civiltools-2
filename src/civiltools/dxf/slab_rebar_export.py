"""Slab Rebar Export — orchestrate DXF export via etabs_api."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


def export_slab_rebar_dxf(
    etabs: Any,
    data: pd.DataFrame,
    output_file: str | Path,
    layers: list[str] | None = None,
    separate_layers: bool = False,
    top: bool = True,
    bottom: bool = True,
    optimizer_params: dict[str, Any] | None = None,
) -> str:
    """Export grouped slab rebar plans to DXF.
    
    Orchestrates grouped export: calls etabs_api export function once per group,
    generates deterministic filenames, returns summary.
    
    Args:
        etabs: ETABS COM object
        data: Raw slab rebar dataframe from ETABS
        output_file: Base output path (folder or filename); used as template
        layers: List of layers to include (e.g. ["A", "B"]), or None for all
        separate_layers: If True, one DXF per layer; if False, merge layers
        top: Include top rebar
        bottom: Include bottom rebar
        optimizer_params: Parameters for etabs_api optimizer
    
    Returns:
        Summary string describing exported files and counts
    """
    if optimizer_params is None:
        optimizer_params = {
            "continuous_rebar_top": 150,
            "continuous_rebar_bot": 300,
            "region_threshold": 0.0,
            "min_area_threshold": 0.0,
            "extend_length": 0.0,
            "min_bar_length": 0.0,
        }
    
    output_file = Path(output_file)
    
    # Prefer the installed etabs_api dependency; keep local paths for development.
    import sys
    import importlib.util
    import os
    import pathlib
    import site
    if importlib.util.find_spec("rebars") is None:
        candidates = []
        configured_path = os.environ.get("ETABS_API_PATH")
        if configured_path:
            candidates.append(pathlib.Path(configured_path).parent)
        candidates.extend(pathlib.Path(sp) / "etabs_api" for sp in site.getsitepackages())
        candidates.extend([pathlib.Path(r"g:\etabs_api"), pathlib.Path(r"g:\etabs_api\src")])
        for _candidate in candidates:
            if (_candidate / "rebars" / "__init__.py").exists():
                sys.path.insert(0, str(_candidate))
                break

    try:
        from rebars import RebarOptimizer
        from etabs_api.etabs_api_export.export_plans_to_dxf import export_to_dxf_slab_rebars
        from etabs_api.python_functions import open_file
    except ImportError as e:
        raise RuntimeError(
            f"etabs_api/rebars not available: {e}. "
            "Ensure etabs_api package is installed and rebars package is importable."
        )

    # Build a cached-database wrapper so the optimizer uses our pre-loaded
    # DataFrame instead of re-reading from ETABS.
    class _CachedDatabase:
        """Proxy that returns cached DataFrame for get_slab_rebars_for_drawing."""
        def __init__(self, df: pd.DataFrame):
            self._df = df

        def get_slab_rebars_for_drawing(
            self,
            stories=None,
            strip_objects=None,
            layers=None,
            top_bottom="both",
            statuses=None,
        ) -> pd.DataFrame:
            result = self._df.copy()
            if stories:
                result = result[result["Story"].isin(stories)]
            if strip_objects:
                result = result[result["StripObject"].isin(strip_objects)]
            if layers:
                result = result[result["Layer"].isin(layers)]
            if statuses and "Status" in result.columns:
                result = result[result["Status"].isin(statuses)]
            tb = str(top_bottom).strip().lower()
            if tb == "top":
                result = result[result["Face"] == "TOP"]
            elif tb == "bot":
                result = result[result["Face"] == "BOT"]
            return result.reset_index(drop=True)
    
    # Prepare output directory and filename template
    output_dir = output_file.parent if output_file.suffix == ".dxf" else output_file
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = output_file.stem if output_file.suffix == ".dxf" else "slab_rebar_plan"

    if data is None or data.empty:
        raise ValueError("No data to export.")

    # Prepare layer list and top_bottom filter from the cached data
    export_layers = layers if layers else sorted(data["Layer"].unique().tolist())
    if top and bottom:
        export_top_bottom = "both"
    elif top:
        export_top_bottom = "top"
    elif bottom:
        export_top_bottom = "bot"
    else:
        raise ValueError("At least one of top or bottom must be True.")

    cached_db = _CachedDatabase(data)
    optimizer = RebarOptimizer(params=(optimizer_params or {}))

    # Save original ETABS unit (needed for floor-plan geometry, not for rebar data)
    try:
        orig_force, orig_len = etabs.get_current_unit()
    except Exception:
        orig_force, orig_len = "kgf", "mm"

    try:
        etabs.set_current_unit("N", "mm")

        def _run_and_export(fpath: pathlib.Path, layer_filter: list[str]):
            """Run optimizer on cached data and write one DXF."""
            bridge = optimizer.run_from_etabs_slab(
                database=cached_db,
                layers=layer_filter,
                top_bottom=export_top_bottom,
            )
            optimizer.export_etabs_slab_to_dxf(
                etabs=etabs,
                bridge_result=bridge,
                output_path=str(fpath),
                top_color=5,
                bot_color=3,
                story_note_label="Slab Reinforcement",
            )
            return bridge

        if separate_layers:
            output_files = []
            for layer in export_layers:
                fname = f"{base_name}_{layer.lower()}.dxf"
                fpath = output_dir / fname
                _run_and_export(fpath, [layer])
                output_files.append(str(fpath))
                log.info(f"Exported layer {layer} to {fpath}")
        else:
            fname = f"{base_name}.dxf"
            fpath = output_dir / fname
            _run_and_export(fpath, export_layers)
            output_files = [str(fpath)]
            log.info(f"Exported all layers to {fpath}")

        # Auto-open first file
        if output_files:
            try:
                open_file(output_files[0])
            except Exception as e:
                log.warning(f"Could not auto-open file: {e}")

        summary = f"✓ Exported {len(output_files)} DXF file(s):\n"
        for f in output_files:
            summary += f"  • {Path(f).name}\n"
        summary += f"\nLocation: {output_dir.resolve()}"
        return summary

    finally:
        try:
            etabs.set_current_unit(orig_force, orig_len)
            log.info(f"Restored ETABS unit: {orig_force}, {orig_len}")
        except Exception:
            pass
