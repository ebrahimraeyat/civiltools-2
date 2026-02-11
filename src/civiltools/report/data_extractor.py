"""
Data extraction layer — pulls all structural analysis results from
a live ETABS connection for report generation.

All ETABS COM calls are sequential (COM is single-threaded).
The returned ``ReportData`` contains everything needed to render
both DOCX and PDF reports, including raw data for parallel image
generation.

Results for drift, torsion, PMM and joint shear are first looked up
in the JSON table-results folder next to the .edb file. If not found,
the live ETABS API is used as fallback.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FrameInfo:
    """Coordinates and section name for a single beam or column."""
    name: str
    frame_type: str          # 'beam' or 'column'
    section: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class AreaInfo:
    """Polygon vertices and associated load set for a floor area."""
    unique_name: str
    label: str
    vertices: list[tuple[float, float]]
    load_set: str            # group identifier (e.g. "Load Set 1")


@dataclass
class LoadSetDef:
    """Definition of a grouped load set."""
    name: str
    loads: dict[str, float]  # {LoadPattern: value_kgf_per_m2, …}


@dataclass
class ReportData:
    """All data needed to generate the structural report."""

    # ── Project / building info ───────────────────────────────────────
    project_name: str = ""
    location: str = ""
    stories: list[str] = field(default_factory=list)
    total_height: float = 0.0
    building: Any = None            # building.build.Building instance
    model_dir: Path | None = None   # directory containing the .edb
    model_stem: str = ""            # model filename without extension

    # ── Load combinations ─────────────────────────────────────────────
    load_combinations: pd.DataFrame | None = None

    # ── Story drift ───────────────────────────────────────────────────
    drift_data: pd.DataFrame | None = None

    # ── Torsional irregularity ────────────────────────────────────────
    torsion_data: pd.DataFrame | None = None

    # ── Story forces ──────────────────────────────────────────────────
    story_forces_data: list | None = None
    story_forces_fields: list | None = None

    # ── Column PMM design ─────────────────────────────────────────────
    pmm_data: pd.DataFrame | None = None

    # ── Joint shear check ─────────────────────────────────────────────
    joint_shear_data: pd.DataFrame | None = None

    # ── Frame geometry per story ──────────────────────────────────────
    frame_data: dict[str, list[FrameInfo]] = field(default_factory=dict)

    # ── Area load data per story ──────────────────────────────────────
    area_data: dict[str, list[AreaInfo]] = field(default_factory=dict)
    load_set_defs: dict[str, LoadSetDef] = field(default_factory=dict)

    # ── Pre-rendered images (filled by parallel renderer) ─────────────
    story_plan_images: dict[str, bytes] = field(default_factory=dict)
    area_load_images: dict[str, bytes] = field(default_factory=dict)

    # ── Model settings from JSON ──────────────────────────────────────
    model_settings: dict | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Main extraction entry point
# ═══════════════════════════════════════════════════════════════════════════

def extract_report_data(
    etabs,
    building=None,
    progress: Callable[[int, str], None] | None = None,
) -> ReportData:
    """Extract all report data from a live ETABS connection.

    Parameters
    ----------
    etabs : EtabsModel
        Connected ``etabs_obj.EtabsModel`` instance.
    building : Building, optional
        ``civiltools.building.build.Building`` with seismic calcs.
    progress : callable(int, str), optional
        Progress callback ``(percent, message)``.
    """
    data = ReportData(building=building)

    def _prog(pct: int, msg: str):
        if progress:
            progress(pct, msg)

    _prog(0, "Setting units…")
    try:
        etabs.set_current_unit("kgf", "m")
    except Exception:
        pass

    # Resolve model directory for JSON table results
    try:
        model_file = Path(etabs.SapModel.GetModelFilename())
        data.model_dir = model_file.parent
        data.model_stem = model_file.stem
    except Exception:
        pass

    # ── Model settings from JSON ──────────────────────────────────────
    _prog(1, "Reading model settings...")
    _extract_model_settings(data)

    # ── Project / story info ──────────────────────────────────────────
    _prog(2, "Reading project info…")
    _extract_project_info(etabs, building, data)

    # ── Load combinations ─────────────────────────────────────────────
    _prog(8, "Reading load combinations…")
    _extract_load_combinations(etabs, data)

    # ── Story drift (JSON first, then API) ────────────────────────────
    _prog(15, "Reading story drifts…")
    _extract_drift(etabs, building, data)

    # ── Torsion (JSON first, then API) ────────────────────────────────
    _prog(25, "Reading torsion data…")
    _extract_torsion(etabs, data)

    # ── Story forces ──────────────────────────────────────────────────
    _prog(32, "Reading story forces…")
    _extract_story_forces(etabs, data)

    # ── Column PMM (JSON first, then API) ─────────────────────────────
    _prog(40, "Reading column design results…")
    _extract_pmm(etabs, data)

    # ── Joint shear (JSON only) ───────────────────────────────────────
    _prog(45, "Reading joint shear data…")
    _extract_joint_shear(data)

    # ── Frame geometry ────────────────────────────────────────────────
    _prog(50, "Reading frame geometry…")
    _extract_frame_data(etabs, data)

    # ── Area loads ────────────────────────────────────────────────────
    _prog(70, "Reading area loads…")
    _extract_area_data(etabs, data)

    _prog(90, "Data extraction complete.")
    return data


# ═══════════════════════════════════════════════════════════════════════════
# JSON table-results loader
# ═══════════════════════════════════════════════════════════════════════════

def _get_table_results_dir(data: ReportData) -> Path | None:
    """Return the {ModelName}_table_results directory, or None."""
    if data.model_dir and data.model_stem:
        d = data.model_dir / f"{data.model_stem}_table_results"
        if d.is_dir():
            return d
    return None


def _find_json_file(data: ReportData, *keywords: str) -> Path | None:
    """Find a JSON file in the table_results dir matching any keyword."""
    tr = _get_table_results_dir(data)
    if tr is None:
        return None
    for f in sorted(tr.glob("*.json")):
        name_lower = f.stem.lower()
        for kw in keywords:
            if kw.lower() in name_lower:
                return f
    return None


def _load_json_table(filepath: Path) -> pd.DataFrame | None:
    """Load a JSON table saved by result_widget (FreeCAD format).

    FreeCAD format: list of {row, col, text, color} dicts.
    Row 0 = headers, row 1+ = data.
    """
    try:
        raw = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(raw, list) or not raw:
        # Might be a dict (e.g. DataFrame.to_dict())
        if isinstance(raw, dict):
            try:
                return pd.DataFrame(raw)
            except Exception:
                return None
        return None

    # Check if this is the flat {row,col,text,color} format
    if isinstance(raw[0], dict) and "row" in raw[0] and "col" in raw[0]:
        # FreeCAD table format
        max_row = max(item["row"] for item in raw)
        max_col = max(item["col"] for item in raw)

        grid: dict[tuple[int, int], str] = {}
        for item in raw:
            grid[(item["row"], item["col"])] = item.get("text", "")

        headers = [grid.get((0, c), f"Col{c}") for c in range(max_col + 1)]
        rows = []
        for r in range(1, max_row + 1):
            rows.append([grid.get((r, c), "") for c in range(max_col + 1)])

        return pd.DataFrame(rows, columns=headers)

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Individual extractors
# ═══════════════════════════════════════════════════════════════════════════

def _extract_model_settings(data: ReportData):
    """Load model_settings.json from the table_results directory."""
    tr = _get_table_results_dir(data)
    if tr is None:
        return
    settings_file = tr / f"{data.model_stem}_model_settings.json"
    if not settings_file.exists():
        # Try any file matching *model_settings*
        candidates = list(tr.glob("*model_settings*.json"))
        if candidates:
            settings_file = candidates[0]
        else:
            return
    try:
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.model_settings = raw
            log.info("Loaded model settings from %s", settings_file.name)
    except Exception as exc:
        log.warning("Could not load model settings: %s", exc)


def _extract_project_info(etabs, building, data: ReportData):
    """Extract project name, stories, height."""
    try:
        data.project_name = etabs.SapModel.GetModelFilename() or "Untitled"
    except Exception:
        data.project_name = "Untitled"

    if building:
        data.location = getattr(building, "city", "")
        data.total_height = getattr(building, "height", 0.0)

    # Story names
    try:
        story_table = etabs.database.read(
            "Story Definitions", to_dataframe=True,
            cols=["Name", "Height"],
        )
        if story_table is not None and not story_table.empty:
            data.stories = story_table["Name"].tolist()
    except Exception:
        pass

    if not data.stories:
        try:
            bc = etabs.frame_obj.get_beams_columns_on_stories()
            data.stories = list(bc.keys())
        except Exception:
            pass


def _extract_load_combinations(etabs, data: ReportData):
    """Load combination table."""
    try:
        data.load_combinations = etabs.load_combinations.get_table_of_load_combinations()
    except Exception as exc:
        log.warning("Could not read load combinations: %s", exc)


def _extract_drift(etabs, building, data: ReportData):
    """Story drift data — JSON first, then API fallback."""
    # Try JSON
    jf = _find_json_file(data, "drift")
    if jf:
        df = _load_json_table(jf)
        if df is not None and not df.empty:
            data.drift_data = df
            log.info("Loaded drift data from %s", jf.name)
            return

    # API fallback
    try:
        no_story = len(data.stories) if data.stories else 5
        cdx = cdy = 4.0
        if building:
            no_story = getattr(building, "number_of_story", no_story)
            xs = getattr(building, "x_system", None)
            ys = getattr(building, "y_system", None)
            if xs:
                cdx = getattr(xs, "cd", cdx)
            if ys:
                cdy = getattr(ys, "cd", cdy)

        result = etabs.get_drifts(no_story, cdx, cdy)
        if result and result[0]:
            rows, fields = result
            data.drift_data = pd.DataFrame(rows, columns=fields)
    except Exception as exc:
        log.warning("Could not read drift data: %s", exc)


def _extract_torsion(etabs, data: ReportData):
    """Torsional irregularity — JSON first, then API fallback."""
    jf = _find_json_file(data, "torsion")
    if jf:
        df = _load_json_table(jf)
        if df is not None and not df.empty:
            data.torsion_data = df
            log.info("Loaded torsion data from %s", jf.name)
            return

    try:
        df = etabs.get_diaphragm_max_over_avg_drifts()
        if df is not None and not df.empty:
            data.torsion_data = df
    except Exception as exc:
        log.warning("Could not read torsion data: %s", exc)


def _extract_story_forces(etabs, data: ReportData):
    """Story forces with percentages."""
    try:
        result = etabs.get_story_forces_with_percentages()
        if result:
            data.story_forces_data, data.story_forces_fields = result
    except Exception as exc:
        log.warning("Could not read story forces: %s", exc)


def _extract_pmm(etabs, data: ReportData):
    """Column PMM design results — JSON first, then API fallback."""
    jf = _find_json_file(data, "pmm", "column")
    if jf:
        df = _load_json_table(jf)
        if df is not None and not df.empty:
            data.pmm_data = df
            log.info("Loaded PMM data from %s", jf.name)
            return

    try:
        df = etabs.design.get_concrete_columns_pmm_table()
        if df is not None and not df.empty:
            data.pmm_data = df
    except Exception as exc:
        log.warning("Could not read PMM data: %s", exc)


def _extract_joint_shear(data: ReportData):
    """Joint shear check — JSON only (no live API equivalent)."""
    jf = _find_json_file(data, "joint", "shear")
    if jf:
        df = _load_json_table(jf)
        if df is not None and not df.empty:
            data.joint_shear_data = df
            log.info("Loaded joint shear data from %s", jf.name)


def _extract_frame_data(etabs, data: ReportData):
    """Beam / column coordinates and section names per story."""
    try:
        story_frames = etabs.frame_obj.get_beams_columns_on_stories()
    except Exception as exc:
        log.warning("Could not read frame data: %s", exc)
        return

    for story, parts in story_frames.items():
        frames: list[FrameInfo] = []
        beams = parts[0] if len(parts) > 0 else []
        columns = parts[1] if len(parts) > 1 else []

        for name in beams:
            try:
                x1, y1, x2, y2 = etabs.frame_obj.get_xy_of_frame_points(name)
                sec = etabs.frame_obj.get_section_name(name)
                frames.append(FrameInfo(name, "beam", sec, x1, y1, x2, y2))
            except Exception:
                continue

        for name in columns:
            try:
                x1, y1, x2, y2 = etabs.frame_obj.get_xy_of_frame_points(name)
                sec = etabs.frame_obj.get_section_name(name)
                frames.append(FrameInfo(name, "column", sec, x1, y1, x2, y2))
            except Exception:
                continue

        data.frame_data[story] = frames


def _extract_area_data(etabs, data: ReportData):
    """Area load sets, polygon vertices, and load grouping per story."""
    # Step 1: get all shell uniform loads
    try:
        load_df = etabs.area.get_shell_uniform_loads()
    except Exception as exc:
        log.warning("Could not read area loads: %s", exc)
        return

    if load_df is None or load_df.empty:
        return

    # Step 2: group areas by their load signature to define load sets
    # Signature = frozenset of (LoadPattern, Load) tuples per area
    area_signatures: dict[str, frozenset] = {}
    area_story: dict[str, str] = {}
    area_label: dict[str, str] = {}

    for uname, grp in load_df.groupby("UniqueName"):
        signature = frozenset(
            (row["LoadPattern"], round(float(row["Load"]), 2))
            for _, row in grp.iterrows()
        )
        area_signatures[uname] = signature
        area_story[uname] = grp["Story"].iloc[0]
        area_label[uname] = grp["Label"].iloc[0] if "Label" in grp.columns else str(uname)

    # Map unique signatures to set names
    sig_to_set: dict[frozenset, str] = {}
    set_counter = 0
    for sig in sorted(set(area_signatures.values()), key=lambda s: sorted(s)):
        set_counter += 1
        name = f"Load Set {set_counter}"
        sig_to_set[sig] = name
        data.load_set_defs[name] = LoadSetDef(
            name=name,
            loads={pat: val for pat, val in sorted(sig)},
        )

    # Step 3: get polygon vertices for each area using COM
    for uname, sig in area_signatures.items():
        story = area_story[uname]
        label = area_label[uname]
        set_name = sig_to_set[sig]

        vertices = _get_area_vertices(etabs, uname)
        if not vertices:
            continue

        info = AreaInfo(
            unique_name=uname,
            label=label,
            vertices=vertices,
            load_set=set_name,
        )
        data.area_data.setdefault(story, []).append(info)


def _get_area_vertices(etabs, area_name: str) -> list[tuple[float, float]]:
    """Get polygon vertices for an area object via COM."""
    try:
        result = etabs.SapModel.AreaObj.GetPoints(area_name)
        # result = (NumberPoints, PointNames_tuple, ReturnCode)
        num_pts = result[0]
        pt_names = result[1]
        vertices = []
        for pt in pt_names:
            coord = etabs.SapModel.PointObj.GetCoordCartesian(pt)
            x, y = coord[0], coord[1]
            vertices.append((x, y))
        return vertices
    except Exception as exc:
        log.debug("Could not get area vertices for %s: %s", area_name, exc)
        return []
