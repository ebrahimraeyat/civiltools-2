"""
DOCX report generator for civilTools — full English structural report.

Uses python-docx + math2docx.  Accepts a ``ReportData`` instance
produced by ``data_extractor.extract_report_data`` and renders every
active section to a styled Word document.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

import docx
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from civiltools.report.report_config import ReportConfig
from civiltools.report.strings import get_string, ASCE7_IRREGULARITY_DESC
from civiltools.report.data_extractor import ReportData


# ── Farsi → English translations ────────────────────────────────────────
_RISK_EN = {
    "\u06a9\u0645": "Low",
    "\u0645\u062a\u0648\u0633\u0637": "Moderate",
    "\u0632\u06cc\u0627\u062f": "High",
    "\u062e\u06cc\u0644\u06cc \u0632\u06cc\u0627\u062f": "Very High",
}

def _en_risk(risk_level) -> str:
    """Translate Farsi risk level to English."""
    return _RISK_EN.get(str(risk_level), str(risk_level))

def _en_soil(soil_type) -> str:
    """Format soil type for display."""
    return f"Type {soil_type}" if soil_type else ""


# ═══════════════════════════════════════════════════════════════════════════
# Document creation
# ═══════════════════════════════════════════════════════════════════════════

def _create_styled_doc(config: ReportConfig) -> Document:
    """Create a Document with custom styles."""
    doc = Document()

    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    colors = {
        1: RGBColor(30, 60, 120),
        2: RGBColor(50, 100, 50),
        3: RGBColor(80, 80, 80),
    }
    sizes = {1: Pt(18), 2: Pt(14), 3: Pt(12)}

    for level in (1, 2, 3):
        heading_style = doc.styles[f"Heading {level}"]
        heading_style.font.name = "Calibri"
        heading_style.font.size = sizes[level]
        heading_style.font.color.rgb = colors[level]
        heading_style.font.bold = True

    return doc


def _add_table_of_contents(doc: Document):
    """Insert a TOC field (updated when user opens in Word)."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fld_begin = docx.oxml.OxmlElement("w:fldChar")
    fld_begin.set(docx.oxml.ns.qn("w:fldCharType"), "begin")
    run._element.append(fld_begin)

    run2 = paragraph.add_run()
    instr = docx.oxml.OxmlElement("w:instrText")
    instr.set(docx.oxml.ns.qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    run2._element.append(instr)

    run3 = paragraph.add_run()
    fld_end = docx.oxml.OxmlElement("w:fldChar")
    fld_end.set(docx.oxml.ns.qn("w:fldCharType"), "end")
    run3._element.append(fld_end)


# ═══════════════════════════════════════════════════════════════════════════
# Table helpers
# ═══════════════════════════════════════════════════════════════════════════

def _add_kv_table(doc: Document, rows: list[tuple[str, str]]):
    """Two-column key/value table."""
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Light Shading Accent 1"
    for i, (key, val) in enumerate(rows):
        table.cell(i, 0).text = key
        table.cell(i, 1).text = str(val)
    doc.add_paragraph()


def _add_data_table(doc: Document, headers: list[str], rows: list[list]):
    """Generic data table with bold header row."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Light Shading Accent 1"
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = h
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            table.cell(r_idx + 1, c_idx).text = str(val)
    doc.add_paragraph()


def _add_df_table(doc: Document, df, max_rows: int = 500):
    """Add a pandas DataFrame as a table."""
    headers = list(df.columns)
    rows = df.head(max_rows).values.tolist()
    _add_data_table(doc, headers, rows)


def _add_image(doc: Document, img_bytes: bytes, width_inches: float = 6.0):
    """Add PNG image from bytes."""
    stream = io.BytesIO(img_bytes)
    doc.add_picture(stream, width=Inches(width_inches))
    doc.add_paragraph()


def _add_formula_section(doc: Document, steps: list[tuple[str, str]]):
    """Add LaTeX formulas rendered as images, with plain-text fallback."""
    for desc, latex in steps:
        doc.add_paragraph(desc, style="Heading 3")
        try:
            img_bytes = _render_latex_to_png(latex)
            stream = io.BytesIO(img_bytes)
            doc.add_picture(stream, width=Inches(5.5))
        except Exception:
            # Fallback: plain text
            p = doc.add_paragraph()
            p.add_run(latex).font.name = "Consolas"


def _render_latex_to_png(latex_str: str, dpi: int = 150, fontsize: int = 14) -> bytes:
    """Render a LaTeX string to PNG bytes using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 1.2))
    ax.axis("off")
    ax.text(0.5, 0.5, f"${latex_str}$",
            fontsize=fontsize, ha="center", va="center",
            transform=ax.transAxes)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                transparent=True, pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════════════════
# Section renderers
# ═══════════════════════════════════════════════════════════════════════════

def _section_model_settings(doc: Document, data: ReportData, lang: str):
    """Render model settings JSON as well-categorized tables."""
    doc.add_heading("Model Settings", level=1)
    ms = data.model_settings
    if not ms:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    # ── 1. Project Information ────────────────────────────────────────
    doc.add_heading("Project Information", level=2)
    info_rows = [
        ("Province", ms.get("ostan", "")),
        ("City", ms.get("city", "")),
        ("Relative Risk Level", _en_risk(ms.get("risk_level", ""))),
        ("Soil Type", _en_soil(ms.get("soil_type", ""))),
        ("Importance Factor", ms.get("importance_factor", "")),
    ]
    _add_kv_table(doc, [(k, str(v)) for k, v in info_rows if v])

    # ── 2. Gravity Loads ──────────────────────────────────────────────
    doc.add_heading("Gravity Loads", level=2)
    _load_map = [
        ("Dead Load (DL)", "dead_combobox"),
        ("Super Dead Load (SD)", "sdead_combobox"),
        ("Partition Dead", "partition_dead_combobox"),
        ("Live Load", "live_combobox"),
        ("Reducible Live", "lred_combobox"),
        ("Parking Live", "live_parking_combobox"),
        ("Partition Live", "partition_live_combobox"),
        ("Live Load 0.5", "live5_combobox"),
        ("Reducible Live 0.5", "lred5_combobox"),
        ("Roof Live", "lroof_combobox"),
        ("Mass", "mass_combobox"),
        ("Vertical Seismic (EV)", "ev_combobox"),
        ("Modal", "modal_combobox"),
    ]
    load_rows = [(label, ms.get(key, "")) for label, key in _load_map]
    _add_kv_table(doc, [(k, str(v)) for k, v in load_rows if v])

    # Retaining wall loads
    if ms.get("retaining_wall_groupbox"):
        doc.add_heading("Retaining Wall Loads", level=3)
        rw_rows = [
            ("Lateral Soil Pressure X+", ms.get("hxp_combobox", "")),
            ("Lateral Soil Pressure X-", ms.get("hxn_combobox", "")),
            ("Lateral Soil Pressure Y+", ms.get("hyp_combobox", "")),
            ("Lateral Soil Pressure Y-", ms.get("hyn_combobox", "")),
        ]
        _add_kv_table(doc, [(k, str(v)) for k, v in rw_rows if v])

    # ── 3. Structural System (Primary) ────────────────────────────────
    _sys_label = "Structural System" if not ms.get("activate_second_system") else "Structural System (Lower)"
    doc.add_heading(_sys_label, level=2)
    sys_rows = [
        ("X System", ms.get("x_system_name", "")),
        ("X Lateral System", ms.get("x_lateral_name", "")),
        ("Ru (X)", str(ms.get("Rux", ""))),
        ("Cd (X)", str(ms.get("cdx", ""))),
        ("Y System", ms.get("y_system_name", "")),
        ("Y Lateral System", ms.get("y_lateral_name", "")),
        ("Ru (Y)", str(ms.get("Ruy", ""))),
        ("Cd (Y)", str(ms.get("cdy", ""))),
        ("Bottom Story", ms.get("bot_x_combo", "")),
        ("Top Story", ms.get("top_x_combo", "")),
        ("Top Story for Height", ms.get("top_story_for_height", "")),
        ("Number of Stories", str(ms.get("no_of_story_x", ""))),
        ("Building Height (m)", str(ms.get("height_x", ""))),
        ("Infill Panel", "Yes" if ms.get("infill") else "No"),
    ]
    _add_kv_table(doc, [(k, v) for k, v in sys_rows if v and v != "None"])

    # ── 4. Structural System (Secondary) ──────────────────────────────
    if ms.get("activate_second_system"):
        doc.add_heading("Structural System (Upper)", level=2)
        sys2_rows = [
            ("X System", ms.get("x_system_name_1", "")),
            ("X Lateral System", ms.get("x_lateral_name_1", "")),
            ("Ru (X)", str(ms.get("Rux1", ""))),
            ("Cd (X)", str(ms.get("cdx1", ""))),
            ("Y System", ms.get("y_system_name_1", "")),
            ("Y Lateral System", ms.get("y_lateral_name_1", "")),
            ("Ru (Y)", str(ms.get("Ruy1", ""))),
            ("Cd (Y)", str(ms.get("cdy1", ""))),
            ("Bottom Story", ms.get("bot_x1_combo", "")),
            ("Top Story", ms.get("top_x1_combo", "")),
            ("Top Story for Height", ms.get("top_story_for_height1", "")),
            ("Number of Stories", str(ms.get("no_of_story_x1", ""))),
            ("Building Height (m)", str(ms.get("height_x1", ""))),
            ("Infill Panel", "Yes" if ms.get("infill_1") else "No"),
            ("Stiffness 10x", "Yes" if ms.get("special_case") else "No"),
        ]
        _add_kv_table(doc, [(k, v) for k, v in sys2_rows if v and v != "None"])

    # ── 5. Static Earthquake Load Cases ───────────────────────────────
    doc.add_heading("Static Earthquake Load Cases", level=2)
    eq_header = ["Load Case", "X Direction", "Y Direction"]
    eq_rows = [
        ["EQ without Eccentricity", ms.get("ex_combobox", ""), ms.get("ey_combobox", "")],
        ["EQ + Positive Eccentricity", ms.get("exp_combobox", ""), ms.get("eyp_combobox", "")],
        ["EQ + Negative Eccentricity", ms.get("exn_combobox", ""), ms.get("eyn_combobox", "")],
        ["EQ Drift (no eccentricity)", ms.get("ex_drift_combobox", ""), ms.get("ey_drift_combobox", "")],
        ["EQ Drift + Positive Ecc.", ms.get("exp_drift_combobox", ""), ms.get("eyp_drift_combobox", "")],
        ["EQ Drift + Negative Ecc.", ms.get("exn_drift_combobox", ""), ms.get("eyn_drift_combobox", "")],
    ]
    eq_rows = [r for r in eq_rows if r[1] or r[2]]
    if eq_rows:
        _add_data_table(doc, eq_header, eq_rows)

    rho_rows = [
        ("Redundancy Factor (rho) X", ms.get("rhox_combobox", "")),
        ("Redundancy Factor (rho) Y", ms.get("rhoy_combobox", "")),
    ]
    _add_kv_table(doc, [(k, str(v)) for k, v in rho_rows if v])

    # Second system earthquake load cases
    if ms.get("activate_second_system"):
        doc.add_heading("Static EQ Load Cases (Upper System)", level=3)
        eq2_rows = [
            ["EQ without Eccentricity", ms.get("ex1_combobox", ""), ms.get("ey1_combobox", "")],
            ["EQ + Positive Eccentricity", ms.get("exp1_combobox", ""), ms.get("eyp1_combobox", "")],
            ["EQ + Negative Eccentricity", ms.get("exn1_combobox", ""), ms.get("eyn1_combobox", "")],
            ["EQ Drift (no eccentricity)", ms.get("ex1_drift_combobox", ""), ms.get("ey1_drift_combobox", "")],
            ["EQ Drift + Positive Ecc.", ms.get("exp1_drift_combobox", ""), ms.get("eyp1_drift_combobox", "")],
            ["EQ Drift + Negative Ecc.", ms.get("exn1_drift_combobox", ""), ms.get("eyn1_drift_combobox", "")],
        ]
        eq2_rows = [r for r in eq2_rows if r[1] or r[2]]
        if eq2_rows:
            _add_data_table(doc, eq_header, eq2_rows)

    # ── 6. Dynamic Analysis ───────────────────────────────────────────
    if ms.get("dynamic_analysis_groupbox"):
        doc.add_heading("Dynamic Analysis", level=2)
        doc.add_paragraph(
            f"X Scale Factor: {ms.get('x_scalefactor_combobox', '')}, "
            f"Y Scale Factor: {ms.get('y_scalefactor_combobox', '')}"
        )
        if ms.get("combination_response_spectrum_checkbox"):
            dyn_header = ["Load Case", "X Direction", "Y Direction"]
            dyn_rows = [
                ["Spectral (no ecc.)", ms.get("sx_combobox", ""), ms.get("sy_combobox", "")],
                ["Spectral (with ecc.)", ms.get("sxe_combobox", ""), ms.get("sye_combobox", "")],
                ["Spectral Drift (no ecc.)", ms.get("sx_drift_combobox", ""), ms.get("sy_drift_combobox", "")],
                ["Spectral Drift (with ecc.)", ms.get("sxe_drift_combobox", ""), ms.get("sye_drift_combobox", "")],
            ]
            dyn_rows = [r for r in dyn_rows if r[1] or r[2]]
            if dyn_rows:
                _add_data_table(doc, dyn_header, dyn_rows)

    # ── 7. Analytical Periods ─────────────────────────────────────────
    doc.add_heading("Analytical Periods", level=2)
    period_rows = [
        ("T analytical X (s)", str(ms.get("tx_an", ""))),
        ("T analytical Y (s)", str(ms.get("ty_an", ""))),
    ]
    if ms.get("activate_second_system"):
        period_rows.extend([
            ("T analytical X - upper (s)", str(ms.get("tx1_an", ""))),
            ("T analytical Y - upper (s)", str(ms.get("ty1_an", ""))),
        ])
    _add_kv_table(doc, [(k, v) for k, v in period_rows if v and v != "None"])

    # ── 8. Structural Material ────────────────────────────────────────
    material = "Concrete" if ms.get("concrete_radiobutton") else "Steel"
    doc.add_heading("Structural Material", level=2)
    _add_kv_table(doc, [("Material", material)])

    # ── 9. Irregularities ─────────────────────────────────────────────
    doc.add_heading("Irregularities", level=2)

    doc.add_heading("Plan Irregularities", level=3)
    plan_items = []
    if ms.get("torsional_irregularity_groupbox"):
        if ms.get("extreme_torsion_irregular_checkbox"):
            plan_items.append(("Extreme Torsional Irregularity", True))
        elif ms.get("torsion_irregular_checkbox"):
            plan_items.append(("Torsional Irregularity", True))
    else:
        plan_items.append(("Torsional Irregularity", False))
    plan_items.extend([
        ("Re-entrant Corner", ms.get("reentrance_corner_checkbox", False)),
        ("Diaphragm Discontinuity", ms.get("diaphragm_discontinuity_checkbox", False)),
        ("Out-of-Plane Offset", ms.get("out_of_plane_offset_checkbox", False)),
        ("Non-Parallel System", ms.get("nonparallel_system_checkbox", False)),
    ])
    _add_checkbox_table(doc, plan_items)

    doc.add_heading("Vertical Irregularities", level=3)
    vert_items = []
    if ms.get("stiffness_soft_story_groupbox"):
        if ms.get("extreme_stiffness_irregular_checkbox"):
            vert_items.append(("Extreme Soft Story", True))
        elif ms.get("stiffness_irregular_checkbox"):
            vert_items.append(("Soft Story", True))
    else:
        vert_items.append(("Stiffness Irregularity", False))
    vert_items.extend([
        ("Weight (Mass) Irregularity", ms.get("weight_mass_checkbox", False)),
        ("Geometric Irregularity", ms.get("geometric_checkbox", False)),
        ("In-Plane Discontinuity", ms.get("in_plane_discontinuity_checkbox", False)),
    ])
    if ms.get("lateral_strength_weak_story_groupbox"):
        if ms.get("extreme_strength_irregular_checkbox"):
            vert_items.append(("Extreme Weak Story", True))
        elif ms.get("strength_irregular_checkbox"):
            vert_items.append(("Weak Story", True))
    else:
        vert_items.append(("Lateral Strength Irregularity", False))
    _add_checkbox_table(doc, vert_items)


def _add_checkbox_table(doc: Document, items: list[tuple[str, bool]]):
    """Render a checkbox list with ASCE 7-16 descriptions for detected irregularities."""
    table = doc.add_table(rows=len(items), cols=1)
    table.style = "Light Shading Accent 1"
    for i, (label, checked) in enumerate(items):
        mark = "\u2713" if checked else "\u2610"
        table.cell(i, 0).text = f"{mark}  {label}"
    doc.add_paragraph()

    # Add ASCE 7-16 penalty descriptions for each detected irregularity
    detected = [label for label, checked in items if checked]
    if detected:
        doc.add_heading("ASCE 7-16 Irregularity Descriptions", level=4)
        for label in detected:
            desc = ASCE7_IRREGULARITY_DESC.get(label)
            if desc:
                p = doc.add_paragraph()
                run = p.add_run(f"{label}: ")
                run.bold = True
                p.add_run(desc)
        doc.add_paragraph()


def _section_project_info(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("PROJECT_INFO", lang), level=1)
    b = data.building
    rows = [
        (get_string("PROJECT_INFO", lang), data.project_name),
        (get_string("CITY", lang), data.location),
        (get_string("NO_STORIES", lang), str(len(data.stories))),
        (get_string("HEIGHT_METER", lang), f"{data.total_height:.1f}"),
    ]
    if b:
        rows.extend([
            (get_string("SOIL_TYPE", lang), _en_soil(getattr(b, "soil_type", ""))),
            (get_string("RISK_LEVEL", lang), _en_risk(getattr(b, "risk_level", ""))),
            (get_string("IMPORTANCE_FACTOR", lang), str(getattr(b, "importance_factor", ""))),
            (get_string("DESIGN_BASE_ACCELERATION", lang), str(getattr(b, "acc", ""))),
        ])
    _add_kv_table(doc, rows)


def _section_structural_system(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("STRUCTURAL_SYSTEM", lang), level=1)
    b = data.building
    if not b:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    for direction, sys_attr in [("X", "x_system"), ("Y", "y_system")]:
        sys = getattr(b, sys_attr, None)
        if sys is None:
            continue
        doc.add_heading(f"{get_string(direction + '_DIRECTION', lang)}", level=2)
        rows = [
            (get_string("LATERAL_TYPE", lang), str(getattr(sys, "lateral_type", getattr(sys, "system_name", str(sys))))),
            (get_string("RU_FACTOR", lang), str(getattr(sys, "Ru", ""))),
            (get_string("PHI0_FACTOR", lang), str(getattr(sys, "phi0", ""))),
            (get_string("CD_FACTOR", lang), str(getattr(sys, "cd", ""))),
            (get_string("MAX_HEIGHT", lang), str(getattr(sys, "max_height", ""))),
        ]
        _add_kv_table(doc, rows)


def _section_seismic_params(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("SEISMIC_PARAMS", lang), level=1)
    b = data.building
    if not b:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return
    rows = [
        (get_string("SOIL_TYPE", lang), _en_soil(getattr(b, "soil_type", ""))),
        (get_string("RISK_LEVEL", lang), _en_risk(getattr(b, "risk_level", ""))),
        (get_string("DESIGN_BASE_ACCELERATION", lang), str(getattr(b, "acc", ""))),
        (get_string("IMPORTANCE_FACTOR", lang), str(getattr(b, "importance_factor", ""))),
        (get_string("INFILL_PANNEL", lang), get_string("YES" if getattr(b, "is_infill", False) else "NO", lang)),
        (get_string("NO_STORIES", lang), str(getattr(b, "number_of_story", len(data.stories)))),
        (get_string("HEIGHT_METER", lang), f"{getattr(b, 'height', data.total_height):.1f}"),
    ]
    _add_kv_table(doc, rows)

    # Period summary
    doc.add_heading("Period Summary", level=2)
    period_rows = []
    for d_label, attr_exp, attr_an, attr_design in [
        ("X", "tx_exp", "tx_an", "tx"),
        ("Y", "ty_exp", "ty_an", "ty"),
    ]:
        t_exp = getattr(b, attr_exp, None)
        t_an = getattr(b, attr_an, None)
        t_des = getattr(b, attr_design, None)
        period_rows.append([
            d_label,
            f"{t_exp:.3f}" if t_exp else "—",
            f"{t_an:.3f}" if t_an else "—",
            f"{t_des:.3f}" if t_des else "—",
        ])
    _add_data_table(doc,
        ["Direction", "T empirical (s)", "T analytical (s)", "T design (s)"],
        period_rows,
    )


def _section_earthquake_formulation(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("EARTHQUAKE_COEFFICIENT_CALC", lang), level=1)
    b = data.building
    if not b:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    try:
        from civiltools.report.latex_str import full_earthquake_calculation
        sp = _building_to_seismic_dict(b, "x")
        if sp:
            doc.add_heading(get_string("X_DIRECTION", lang), level=2)
            steps = full_earthquake_calculation(sp, "x")
            _add_formula_section(doc, steps)
    except Exception:
        doc.add_paragraph("Earthquake formulas could not be generated.")


def _section_earthquake_values(doc: Document, data: ReportData, lang: str):
    doc.add_heading("Earthquake Coefficient Values", level=1)
    b = data.building
    if not b:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    try:
        from civiltools.report.latex_str import full_earthquake_calculation
        sp = _building_to_seismic_dict(b, "y")
        if sp:
            doc.add_heading(get_string("Y_DIRECTION", lang), level=2)
            steps = full_earthquake_calculation(sp, "y")
            _add_formula_section(doc, steps)
    except Exception:
        doc.add_paragraph("Earthquake formulas could not be generated.")

    # Summary table
    if b and hasattr(b, "results") and b.results:
        _, cx, cy = b.results
        doc.add_heading("Coefficient Summary", level=2)
        rows = [
            ["X", f"{cx:.4f}"],
            ["Y", f"{cy:.4f}"],
        ]
        _add_data_table(doc, ["Direction", "C (Earthquake Coefficient)"], rows)


def _section_load_combinations(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("LOAD_COMBINATIONS", lang), level=1)
    if data.load_combinations is None or data.load_combinations.empty:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    df = data.load_combinations
    combo_names = df["Name"].unique()
    doc.add_paragraph(
        f"Total of {len(combo_names)} load combinations defined in the model."
    )

    # Build one-line format: "ComboName: SF1(Load1) + SF2(Load2) + ..."
    rows = []
    for name in combo_names:
        sub = df[df["Name"] == name]
        parts = []
        for _, r in sub.iterrows():
            sf = r.get("SF", 1)
            load = r.get("LoadName", r.get("Load", ""))
            try:
                sf_val = float(sf)
                if sf_val == 1.0:
                    parts.append(str(load))
                elif sf_val == -1.0:
                    parts.append(f"-{load}")
                else:
                    parts.append(f"{sf_val:g}({load})")
            except (ValueError, TypeError):
                parts.append(f"{sf}({load})")
        formula = " + ".join(parts).replace("+ -", "- ")
        rows.append([name, formula])

    _add_data_table(doc, ["Combination", "Definition"], rows)


def _section_story_forces(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("STORY_FORCES", lang), level=1)
    if not data.story_forces_data or not data.story_forces_fields:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Story forces from seismic load patterns with percentage of "
        "total base shear at each story."
    )
    _add_data_table(doc, data.story_forces_fields, data.story_forces_data)


def _section_drift(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("STORY_DRIFT", lang), level=1)
    if data.drift_data is None or data.drift_data.empty:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Maximum story drift values compared against code-allowable limits. "
        "Drifts exceeding the limit are flagged."
    )
    _add_df_table(doc, data.drift_data)

    if "Max Drift" in data.drift_data.columns and "Allowable Drift" in data.drift_data.columns:
        try:
            max_d = data.drift_data["Max Drift"].astype(float)
            allow = data.drift_data["Allowable Drift"].astype(float)
            if (max_d <= allow).all():
                doc.add_paragraph("Result: ALL DRIFT CHECKS PASSED.")
            else:
                doc.add_paragraph("Result: SOME DRIFT CHECKS FAILED — review required.")
        except Exception:
            pass


def _section_torsion(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("TORSIONAL_IRREGULARITY", lang), level=1)
    if data.torsion_data is None or data.torsion_data.empty:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Ratio of maximum diaphragm drift to average drift. "
        "A ratio > 1.2 indicates torsional irregularity; "
        "> 1.4 indicates extreme torsional irregularity."
    )
    _add_df_table(doc, data.torsion_data)

    if "Ratio" in data.torsion_data.columns:
        try:
            max_ratio = data.torsion_data["Ratio"].astype(float).max()
            if max_ratio <= 1.2:
                doc.add_paragraph("Result: No torsional irregularity detected.")
            elif max_ratio <= 1.4:
                doc.add_paragraph(
                    f"Result: Torsional irregularity detected (max ratio = {max_ratio:.3f})."
                )
            else:
                doc.add_paragraph(
                    f"Result: EXTREME torsional irregularity (max ratio = {max_ratio:.3f})."
                )
        except Exception:
            pass


def _section_pmm_columns(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("PMM_COLUMNS", lang), level=1)
    if data.pmm_data is None or data.pmm_data.empty:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Concrete column design results — PMM interaction ratio. "
        "Columns with ratio > 1.0 are overstressed."
    )
    _add_df_table(doc, data.pmm_data)

    if "PMMRatio" in data.pmm_data.columns:
        try:
            max_pmm = data.pmm_data["PMMRatio"].astype(float).max()
            if max_pmm <= 1.0:
                doc.add_paragraph(
                    f"Result: All columns adequate (max PMM ratio = {max_pmm:.3f})."
                )
            else:
                doc.add_paragraph(
                    f"Result: OVERSTRESSED columns found (max PMM ratio = {max_pmm:.3f})."
                )
        except Exception:
            pass


def _section_story_plans(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("STORY_PLANS", lang), level=1)
    if not data.story_plan_images:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Beam and column plan for each story with section names annotated."
    )
    for story in data.stories:
        img = data.story_plan_images.get(story)
        if img:
            doc.add_heading(f"Story: {story}", level=2)
            _add_image(doc, img, width_inches=6.0)


def _section_area_loads(doc: Document, data: ReportData, lang: str):
    doc.add_heading(get_string("AREA_LOAD_PLANS", lang), level=1)
    if not data.area_load_images:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Floor area load plans for each story. Areas with identical "
        "load patterns are grouped and colour-coded."
    )
    for story in data.stories:
        img = data.area_load_images.get(story)
        if img:
            doc.add_heading(f"Story: {story}", level=2)
            _add_image(doc, img, width_inches=6.0)

            # Per-story load set table
            story_areas = data.area_data.get(story, [])
            story_sets = sorted({a.load_set for a in story_areas})
            if story_sets and data.load_set_defs:
                headers = ["Load Set", "Load Patterns (kg/m\u00b2)"]
                rows = []
                for sname in story_sets:
                    lsd = data.load_set_defs.get(sname)
                    if lsd:
                        desc = ", ".join(
                            f"{p} = {v:.0f}" for p, v in lsd.loads.items()
                        )
                    else:
                        desc = ""
                    rows.append([sname, desc])
                _add_data_table(doc, headers, rows)


def _section_joint_shear(doc: Document, data: ReportData, lang: str):
    doc.add_heading("Joint Shear Check", level=1)
    if data.joint_shear_data is None or data.joint_shear_data.empty:
        doc.add_paragraph(get_string("NOT_AVAILABLE", lang))
        return

    doc.add_paragraph(
        "Beam-column joint shear check results."
    )
    _add_df_table(doc, data.joint_shear_data)


# ═══════════════════════════════════════════════════════════════════════════
# Section dispatch
# ═══════════════════════════════════════════════════════════════════════════

_SECTION_DISPATCH = {
    "model_settings":         _section_model_settings,
    "project_info":           _section_project_info,
    "structural_system":      _section_structural_system,
    "seismic_params":         _section_seismic_params,
    "earthquake_formulation": _section_earthquake_formulation,
    "earthquake_values":      _section_earthquake_values,
    "load_combinations":      _section_load_combinations,
    "story_forces":           _section_story_forces,
    "drift":                  _section_drift,
    "torsion":                _section_torsion,
    "joint_shear":            _section_joint_shear,
    "pmm_columns":            _section_pmm_columns,
    "story_plans":            _section_story_plans,
    "area_loads":             _section_area_loads,
}


# ═══════════════════════════════════════════════════════════════════════════
# High-level builder
# ═══════════════════════════════════════════════════════════════════════════

def create_docx_report(
    data: ReportData,
    config: ReportConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Generate a full DOCX report from extracted data.

    Parameters
    ----------
    data : ReportData
        All report data (from ``extract_report_data``).
    config : ReportConfig, optional
        Report configuration.
    output_path : str | Path, optional
        Output file path.
    """
    config = config or ReportConfig(language="en")
    lang = config.language if config.language != "both" else "en"
    doc = _create_styled_doc(config)

    # ── Title page ────────────────────────────────────────────────────
    title = data.project_name or "Structural Report"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(30, 60, 120)
    run.bold = True

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run(get_string("REPORT_TITLE", lang))
    run2.font.size = Pt(14)
    run2.font.color.rgb = RGBColor(100, 100, 100)

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = p3.add_run(get_string("GENERATED_BY", lang))
    run3.font.size = Pt(10)
    run3.font.color.rgb = RGBColor(140, 140, 140)

    doc.add_page_break()

    # ── Table of Contents ─────────────────────────────────────────────
    if config.include_table_of_contents:
        doc.add_heading(get_string("TABLE_OF_CONTENTS", lang), level=1)
        _add_table_of_contents(doc)
        doc.add_page_break()

    # ── Sections ──────────────────────────────────────────────────────
    for section_key in config.active_sections:
        renderer = _SECTION_DISPATCH.get(section_key)
        if renderer:
            renderer(doc, data, lang)
            doc.add_page_break()
        else:
            doc.add_heading(config.get_section_name(section_key), level=1)
            doc.add_paragraph(f"[Section: {section_key} — content pending]")
            doc.add_page_break()

    # ── Save ──────────────────────────────────────────────────────────
    if output_path is None:
        stem = (data.project_name or "report").replace(" ", "_")
        output_path = Path(f"{stem}_report.docx")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _building_to_seismic_dict(building, direction: str) -> dict | None:
    """Convert Building attributes to a seismic_params dict
    compatible with ``latex_str.full_earthquake_calculation``.
    """
    if building is None:
        return None

    d = direction.lower()
    sys_attr = f"{d}_system"
    sys = getattr(building, sys_attr, None)

    acc = getattr(building, "acc", 0)

    sp = {
        "soil_type": getattr(building, "soil_type", ""),
        "A": acc,
        "I": getattr(building, "importance_factor", 1),
        "zone": getattr(building, "risk_level", ""),
        "risk_level": 3 if acc >= 0.3 else (2 if acc >= 0.25 else 1),
        "T0": getattr(getattr(building, "soil_properties", None), "T0", 0),
        "Ts": getattr(getattr(building, "soil_properties", None), "Ts", 0),
        "S": getattr(getattr(building, "soil_properties", None), "S", 0),
        "S0": getattr(getattr(building, "soil_properties", None), "S0", 0),
        "H": getattr(building, "height", 0),
        "height": getattr(building, "height", 0),
        "is_infill": getattr(building, "is_infill", False),
    }

    # System parameters
    if sys:
        sp["alpha"] = getattr(sys, "alpha", 0)
        sp["Ct"] = getattr(sys, "alpha", 0)
        sp["beta"] = getattr(sys, "pow", 0.75)
        sp[f"R{d}"] = getattr(sys, "Ru", 0)

    # Period values
    sp[f"T{d}"] = getattr(building, f"t{d}", 0)           # design period
    sp[f"T{d}_exp"] = getattr(building, f"t{d}_exp", 0)    # empirical
    sp[f"T{d}_an"] = getattr(building, f"t{d}_an", 0)      # analytical
    sp[f"T{d}_design"] = getattr(building, f"t{d}", 0)     # design = t{d}

    # Reflection factor components from the ReflectionFactor object
    refl = getattr(building, f"soil_reflection_prop_{d}", None)
    if refl:
        sp[f"B1{d}"] = getattr(refl, "B1", 0)
        sp[f"N{d}"] = getattr(refl, "N", 1)
    else:
        sp[f"B1{d}"] = 0
        sp[f"N{d}"] = 1

    sp[f"B{d}"] = getattr(building, f"b{d}", 0)
    sp[f"K{d}"] = getattr(building, f"k{d}", 0)
    sp[f"C{d}"] = 0

    if hasattr(building, "results") and building.results and building.results[0] is True:
        _, cx, cy = building.results
        sp["Cx"] = cx
        sp["Cy"] = cy
        sp[f"C{d}"] = cx if d == "x" else cy

    return sp
