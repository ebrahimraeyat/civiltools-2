"""
PDF report generator for civilTools — uses fpdf2.

Generates structural engineering reports from BuildingModel data with
full Persian/English bilingual support, LaTeX formula rendering, and
Standard 2800 earthquake coefficient calculations.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

from fpdf import FPDF

from civiltools.report.report_config import ReportConfig
from civiltools.report.strings import get_string


# ═══════════════════════════════════════════════════════════════════════════
# Font discovery
# ═══════════════════════════════════════════════════════════════════════════

def _find_font(names: list[str], search_paths: list[Path] | None = None) -> Path | None:
    """Case-insensitive font file search."""
    if search_paths is None:
        import platform
        if platform.system() == "Windows":
            search_paths = [Path(r"C:\Windows\Fonts")]
        else:
            search_paths = [Path.home() / ".local/share/fonts", Path("/usr/share/fonts")]

    lower_names = [n.lower() for n in names]
    for sp in search_paths:
        if not sp.exists():
            continue
        for f in sp.rglob("*.ttf"):
            if f.name.lower() in lower_names:
                return f
    return None


def find_persian_font() -> tuple[Path | None, str]:
    """Find a Persian-capable TTF font."""
    p = _find_font(["bnazanin.ttf", "b nazanin.ttf", "BNazanin.ttf"])
    if p:
        return p, "BNazanin"
    p = _find_font(["Vazirmatn-Regular.ttf", "vazirmatn-regular.ttf"])
    if p:
        return p, "Vazirmatn"
    return None, ""


def find_persian_font_bold() -> Path | None:
    """Find bold variant."""
    return _find_font(["bnaznnbd.ttf", "BNazanBd.ttf", "Vazirmatn-Bold.ttf"])


# ═══════════════════════════════════════════════════════════════════════════
# LaTeX rendering via matplotlib
# ═══════════════════════════════════════════════════════════════════════════

def render_latex_to_image(
    latex_str: str, dpi: int = 150, fontsize: int = 14,
) -> bytes:
    """Render a LaTeX string to PNG bytes using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 1.2))
    ax.axis("off")
    ax.text(
        0.5, 0.5, f"${latex_str}$",
        fontsize=fontsize, ha="center", va="center",
        transform=ax.transAxes,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                transparent=True, pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════════════════
# PersianPDF
# ═══════════════════════════════════════════════════════════════════════════

class PersianPDF(FPDF):
    """PDF builder with Persian/RTL support and structural report features."""

    def __init__(self, config: ReportConfig | None = None):
        super().__init__()
        self.config = config or ReportConfig()
        self._font_name = "Helvetica"
        self._temp_files: list[Path] = []
        self._setup_font()
        self._setup_defaults()

    def _setup_font(self):
        font_path, font_name = find_persian_font()
        if font_path:
            self.add_font(font_name, "", str(font_path), uni=True)
            bold_path = find_persian_font_bold()
            if bold_path:
                self.add_font(font_name, "B", str(bold_path), uni=True)
            self._font_name = font_name

    def _setup_defaults(self):
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(15, 15, 15)

    def _s(self, key: str) -> str:
        return get_string(key, self.config.language)

    @property
    def is_rtl(self) -> bool:
        return self.config.is_rtl

    # ── Header / Footer ───────────────────────────────────────────────

    def header(self):
        self.set_font(self._font_name, "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "civilTools — Structural Engineering Report", align="C")
        self.ln(10)
        self.set_draw_color(200, 200, 200)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(3)

    def footer(self):
        if self.config.include_page_numbers:
            self.set_y(-15)
            self.set_font(self._font_name, "", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    # ── Content builders ──────────────────────────────────────────────

    def add_title_page(self, title: str, subtitle: str = "", date: str = ""):
        self.add_page()
        self.ln(60)
        self.set_font(self._font_name, "B", 28)
        self.set_text_color(30, 60, 120)
        self.cell(0, 15, title, align="C")
        self.ln(20)
        if subtitle:
            self.set_font(self._font_name, "", 16)
            self.set_text_color(80, 80, 80)
            self.cell(0, 10, subtitle, align="C")
            self.ln(15)
        if date:
            self.set_font(self._font_name, "", 12)
            self.cell(0, 10, date, align="C")
        self.set_text_color(0, 0, 0)

    def add_heading(self, text: str, level: int = 1):
        sizes = {1: 18, 2: 14, 3: 12}
        colors = {1: (30, 60, 120), 2: (50, 100, 50), 3: (80, 80, 80)}
        self.ln(6)
        self.set_font(self._font_name, "B", sizes.get(level, 12))
        self.set_text_color(*colors.get(level, (0, 0, 0)))
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        if level == 1:
            self.set_draw_color(30, 60, 120)
            self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def add_paragraph(self, text: str, bold: bool = False):
        style = "B" if bold else ""
        self.set_font(self._font_name, style, 11)
        self.multi_cell(0, 6, text)
        self.ln(3)

    def add_key_value_table(self, rows: list[tuple[str, str]], header: tuple[str, str] | None = None):
        """Two-column key/value table."""
        col_w = [70, self.w - 30 - 70]
        self.set_font(self._font_name, "B", 10)

        if header:
            self.set_fill_color(30, 60, 120)
            self.set_text_color(255, 255, 255)
            self.cell(col_w[0], 8, header[0], border=1, fill=True)
            self.cell(col_w[1], 8, header[1], border=1, fill=True)
            self.ln()
            self.set_text_color(0, 0, 0)

        self.set_font(self._font_name, "", 10)
        fill = False
        for key, val in rows:
            if fill:
                self.set_fill_color(240, 245, 250)
            self.cell(col_w[0], 7, key, border="LR", fill=fill)
            self.cell(col_w[1], 7, val, border="LR", fill=fill)
            self.ln()
            fill = not fill

    def add_data_table(
        self, headers: list[str], rows: list[list[str]],
        col_widths: list[float] | None = None,
    ):
        """Generic data table with auto column widths."""
        n = len(headers)
        if col_widths is None:
            available = self.w - 30
            col_widths = [available / n] * n

        # Header
        self.set_font(self._font_name, "B", 9)
        self.set_fill_color(30, 60, 120)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(0, 0, 0)

        # Rows
        self.set_font(self._font_name, "", 9)
        fill = False
        for row in rows:
            if fill:
                self.set_fill_color(245, 248, 252)
            for i, val in enumerate(row):
                self.cell(col_widths[i], 7, str(val), border=1, fill=fill, align="C")
            self.ln()
            fill = not fill

    def add_formula(self, latex_str: str, description: str = ""):
        """Embed a LaTeX formula as an image."""
        if description:
            self.set_font(self._font_name, "", 10)
            self.cell(0, 6, description, new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

        try:
            img_bytes = render_latex_to_image(latex_str)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(img_bytes)
            tmp.close()
            self._temp_files.append(Path(tmp.name))
            self.image(tmp.name, w=140)
            self.ln(3)
        except Exception:
            # Fallback: just print the LaTeX source
            self.set_font("Courier", "", 9)
            self.multi_cell(0, 5, latex_str)
            self.set_font(self._font_name, "", 11)
            self.ln(3)

    def save(self, filepath: str | Path):
        """Output PDF and clean up temp files."""
        self.alias_nb_pages()
        self.output(str(filepath))
        for tmp in self._temp_files:
            try:
                tmp.unlink()
            except OSError:
                pass
        self._temp_files.clear()


# ═══════════════════════════════════════════════════════════════════════════
# High-level report builder
# ═══════════════════════════════════════════════════════════════════════════

def create_pdf_report(
    model,
    config: ReportConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Generate a full PDF report from a BuildingModel.

    Parameters
    ----------
    model : BuildingModel
        The building model with populated seismic_params.
    config : ReportConfig, optional
        Report configuration. Uses defaults if not provided.
    output_path : str or Path, optional
        Output file path. Defaults to ``<project_name>_report.pdf``.
    """
    from civiltools.report.latex_str import full_earthquake_calculation

    config = config or ReportConfig()
    pdf = PersianPDF(config)
    pdf.alias_nb_pages()

    # Title page
    title = model.project_name or "Structural Report"
    pdf.add_title_page(title, "civilTools Structural Engineering Report")

    for section in config.active_sections:
        if section == "project_info":
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            rows = [
                (get_string("PROJECT_INFO", config.language), model.project_name),
                (get_string("CITY", config.language), model.location),
                (get_string("NO_STORIES", config.language), str(len(model.stories))),
                (get_string("HEIGHT_METER", config.language), f"{model.total_height:.1f}"),
            ]
            pdf.add_key_value_table(rows)

        elif section == "seismic_params":
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            sp = model.seismic_params
            if sp:
                rows = [
                    (get_string("SOIL_TYPE", config.language), str(sp.get("soil_type", ""))),
                    (get_string("RISK_LEVEL", config.language), str(sp.get("zone", sp.get("risk_level", "")))),
                    (get_string("IMPORTANCE_FACTOR", config.language), str(sp.get("I", sp.get("importance_factor", "")))),
                    (get_string("DESIGN_BASE_ACCELERATION", config.language), str(sp.get("A", ""))),
                ]
                pdf.add_key_value_table(rows)

        elif section == "earthquake_formulation":
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            sp = model.seismic_params
            if sp:
                for desc, latex in full_earthquake_calculation(sp, "x"):
                    pdf.add_formula(latex, description=desc)

        elif section == "earthquake_values":
            pdf.add_heading(config.get_section_name(section), 1)
            # Y direction
            sp = model.seismic_params
            if sp:
                for desc, latex in full_earthquake_calculation(sp, "y"):
                    pdf.add_formula(latex, description=desc)

        elif section == "drift":
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            pdf.add_paragraph(
                "Story drift analysis results will be populated from "
                "ETABS analysis results when available."
            )

        elif section == "design_results":
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            pdf.add_paragraph(
                "Design results (column ratios, beam reinforcement, etc.) "
                "will be populated from ETABS design results when available."
            )

        elif section == "json_tables":
            # Handled via ResultManifest — placeholder for now
            pass

        else:
            pdf.add_page()
            pdf.add_heading(config.get_section_name(section), 1)
            pdf.add_paragraph(f"[Section: {section} — content pending]")

    # Save
    if output_path is None:
        name = model.project_name.replace(" ", "_") or "report"
        output_path = Path(f"{name}_report.pdf")
    output_path = Path(output_path)
    pdf.save(output_path)
    return output_path
