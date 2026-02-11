"""
Export Markdown help content to PDF.

Uses ``fpdf2`` with a styled template matching the HTML theme.
Supports:
  - Persian (RTL) and English text
  - Headings, paragraphs, tables, code blocks
  - Images (embedded)
  - Page numbers, headers/footers

This produces a single consolidated PDF from one or more .md files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from markdown_it import MarkdownIt
from markdown_it.token import Token


# ═══════════════════════════════════════════════════════════════════════════
# Font discovery (reused from report module)
# ═══════════════════════════════════════════════════════════════════════════

def _find_font(names: list[str], search_dirs: list[Path] | None = None) -> Path | None:
    """Find a .ttf font file by name."""
    import os
    if search_dirs is None:
        search_dirs = [
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
            Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        ]
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.name.lower() in [n.lower() for n in names]:
                return f
    return None


# ═══════════════════════════════════════════════════════════════════════════
# HelpPDF class
# ═══════════════════════════════════════════════════════════════════════════

class HelpPDF(FPDF):
    """PDF generator for help documentation."""

    def __init__(self, rtl: bool = False, title: str = "civilTools Help"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._rtl = rtl
        self._title = title
        self._font_family = "Helvetica"
        self._heading_count = 0
        self._setup_font()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)

    def _setup_font(self):
        """Load Persian font if available."""
        font_path = _find_font(
            ["BNazanin.ttf", "B Nazanin.ttf", "bnazanin.ttf"]
        )
        if font_path:
            self._font_family = "BNazanin"
            self.add_font("BNazanin", "", str(font_path), uni=True)
            bold_path = _find_font(
                ["BNaznnBd.ttf", "B Nazanin Bold.ttf"]
            )
            if bold_path:
                self.add_font("BNazanin", "B", str(bold_path), uni=True)
            else:
                self.add_font("BNazanin", "B", str(font_path), uni=True)
        try:
            self.set_text_shaping(True)
        except Exception:
            pass

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self._font_family, "", 8)
        self.set_text_color(128, 128, 128)
        align = Align.R if self._rtl else Align.L
        self.cell(0, 8, self._title, align=align,
                  new_x=XPos.LEFT, new_y=YPos.NEXT)
        self.set_draw_color(200, 200, 200)
        self.line(20, self.get_y(), self.w - 20, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font_family, "", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, str(self.page_no()), align=Align.C,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)

    # ── Content methods ───────────────────────────────────────────────

    def add_title_page(self, title: str, subtitle: str = ""):
        self.add_page()
        self.ln(50)
        self.set_font(self._font_family, "B", 28)
        self.cell(0, 15, title, align=Align.C,
                  new_x=XPos.LEFT, new_y=YPos.NEXT)
        self.ln(10)
        if subtitle:
            self.set_font(self._font_family, "", 16)
            self.set_text_color(100, 100, 100)
            self.cell(0, 12, subtitle, align=Align.C,
                      new_x=XPos.LEFT, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)

    def add_heading(self, text: str, level: int = 1):
        self._heading_count += 1
        sizes = {1: 20, 2: 16, 3: 13}
        size = sizes.get(level, 12)
        self.ln(6 if level > 1 else 10)
        self.set_font(self._font_family, "B", size)
        self.set_text_color(36, 64, 97)  # #244061
        align = Align.R if self._rtl else Align.L
        self.cell(0, size * 0.6, text, align=align,
                  new_x=XPos.LEFT, new_y=YPos.NEXT)
        if level <= 2:
            self.set_draw_color(46, 116, 181)  # #2E74B5
            y = self.get_y() + 1
            self.line(20, y, self.w - 20, y)
            self.ln(3)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def add_paragraph(self, text: str):
        self.set_font(self._font_family, "", 11)
        align = Align.R if self._rtl else Align.L
        self.multi_cell(0, 6, text, align=align,
                        new_x=XPos.LEFT, new_y=YPos.NEXT)
        self.ln(3)

    def add_code_block(self, code: str, lang: str = ""):
        self.set_font("Courier", "", 9)
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(200, 200, 200)
        x = self.get_x()
        w = self.w - 40
        self.rect(x, self.get_y(), w, 6 + len(code.splitlines()) * 4, style="DF")
        self.set_xy(x + 3, self.get_y() + 2)
        for line in code.splitlines():
            self.cell(w - 6, 4, line, new_x=XPos.LEFT, new_y=YPos.NEXT)
            self.set_x(x + 3)
        self.ln(5)
        self.set_font(self._font_family, "", 11)

    def add_table(self, headers: list[str], rows: list[list[str]]):
        col_count = len(headers)
        col_w = (self.w - 40) / col_count

        # Header
        self.set_font(self._font_family, "B", 10)
        self.set_fill_color(36, 64, 97)
        self.set_text_color(255, 255, 255)
        for h in headers:
            self.cell(col_w, 7, h, border=1, fill=True, align=Align.C,
                      new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln()

        # Rows
        self.set_font(self._font_family, "", 10)
        self.set_text_color(0, 0, 0)
        for i, row in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(240, 244, 248)
            else:
                self.set_fill_color(255, 255, 255)
            for cell in row:
                self.cell(col_w, 6, cell, border=1, fill=True, align=Align.C,
                          new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.ln()
        self.ln(3)

    def add_blockquote(self, text: str):
        self.set_fill_color(248, 249, 250)
        self.set_draw_color(46, 116, 181)
        x = self.get_x()
        w = self.w - 40
        self.set_font(self._font_family, "I", 11)
        # Draw left border
        y0 = self.get_y()
        self.set_x(x + 8)
        self.multi_cell(w - 8, 6, text, align=Align.L if not self._rtl else Align.R,
                        new_x=XPos.LEFT, new_y=YPos.NEXT)
        y1 = self.get_y()
        self.line(x + 2, y0, x + 2, y1)
        self.set_font(self._font_family, "", 11)
        self.ln(3)


# ═══════════════════════════════════════════════════════════════════════════
# Markdown → PDF pipeline
# ═══════════════════════════════════════════════════════════════════════════

def _parse_md_tokens(text: str) -> list[Token]:
    """Parse markdown text into tokens."""
    md = MarkdownIt("commonmark", {"html": True})
    md.enable(["table", "strikethrough"])
    return md.parse(text)


def _tokens_to_pdf(pdf: HelpPDF, tokens: list[Token]):
    """Walk token stream and render to PDF."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])
            # Next token is the inline content
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                text = tokens[i + 1].content
                pdf.add_heading(text, level)
                i += 3  # heading_open, inline, heading_close
                continue

        elif tok.type == "paragraph_open":
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                text = tokens[i + 1].content
                pdf.add_paragraph(text)
                i += 3
                continue

        elif tok.type == "fence":
            pdf.add_code_block(tok.content, tok.info)
            i += 1
            continue

        elif tok.type == "blockquote_open":
            # Collect blockquote content
            depth = 1
            j = i + 1
            bq_text = ""
            while j < len(tokens) and depth > 0:
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                elif tokens[j].type == "inline":
                    bq_text += tokens[j].content + "\n"
                j += 1
            pdf.add_blockquote(bq_text.strip())
            i = j
            continue

        elif tok.type == "table_open":
            headers, rows = _extract_table(tokens, i)
            if headers:
                pdf.add_table(headers, rows)
            # Skip to table_close
            while i < len(tokens) and tokens[i].type != "table_close":
                i += 1
            i += 1
            continue

        i += 1


def _extract_table(tokens: list[Token], start: int) -> tuple[list[str], list[list[str]]]:
    """Extract table headers and rows from token sequence."""
    headers: list[str] = []
    rows: list[list[str]] = []
    current_row: list[str] = []
    in_head = False
    in_body = False

    for i in range(start, len(tokens)):
        tok = tokens[i]
        if tok.type == "table_close":
            break
        if tok.type == "thead_open":
            in_head = True
        elif tok.type == "thead_close":
            in_head = False
        elif tok.type == "tbody_open":
            in_body = True
        elif tok.type == "tbody_close":
            in_body = False
        elif tok.type == "tr_open":
            current_row = []
        elif tok.type == "tr_close":
            if in_head:
                headers = current_row
            elif in_body:
                rows.append(current_row)
        elif tok.type == "inline":
            current_row.append(tok.content)

    return headers, rows


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def md_to_pdf(
    md_files: Sequence[Path | str],
    output: Path | str,
    *,
    rtl: bool = False,
    title: str = "civilTools Help Manual",
    subtitle: str = "",
):
    """Convert one or more Markdown files to a single PDF.

    Parameters
    ----------
    md_files : sequence of paths
        Markdown files to include, in order.
    output : path
        Output PDF file.
    rtl : bool
        RTL layout for Persian content.
    title : str
        Cover page title.
    subtitle : str
        Cover page subtitle.
    """
    pdf = HelpPDF(rtl=rtl, title=title)
    pdf.add_title_page(title, subtitle)

    for md_path in md_files:
        md_path = Path(md_path)
        text = md_path.read_text("utf-8")
        tokens = _parse_md_tokens(text)
        pdf.add_page()
        _tokens_to_pdf(pdf, tokens)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output))
    return Path(output)
