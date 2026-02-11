"""
Markdown → HTML renderer with beautiful styling.

Uses ``markdown-it-py`` for parsing and ``Pygments`` for code highlighting.
Produces self-contained HTML with embedded CSS suitable for:
  - QWebEngineView (in-app help)
  - Standalone HTML files
  - Feeding into the PDF/DOCX exporters
"""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline

# Optional: code highlighting
try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name, TextLexer

    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False


# ═══════════════════════════════════════════════════════════════════════════
# CSS theme
# ═══════════════════════════════════════════════════════════════════════════

HELP_CSS = dedent("""\
    :root {
        --bg:       #FFFFFF;
        --fg:       #1E1E1E;
        --heading:  #244061;
        --accent:   #2E74B5;
        --border:   #D0D0D0;
        --code-bg:  #F5F5F5;
        --table-hd: #244061;
        --table-fg: #FFFFFF;
        --table-alt:#F0F4F8;
    }
    body {
        font-family: 'Segoe UI', 'B Nazanin', Tahoma, sans-serif;
        font-size: 14px;
        line-height: 1.7;
        color: var(--fg);
        background: var(--bg);
        max-width: 860px;
        margin: 0 auto;
        padding: 20px 30px;
        direction: ltr;  /* override per-page for RTL */
    }
    body.rtl {
        direction: rtl;
        text-align: right;
        font-family: 'B Nazanin', 'Vazirmatn', Tahoma, sans-serif;
        font-size: 15px;
    }
    h1, h2, h3, h4 {
        color: var(--heading);
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    h1 { font-size: 24px; border-bottom: 2px solid var(--accent); padding-bottom: 6px; }
    h2 { font-size: 20px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
    h3 { font-size: 17px; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    code {
        background: var(--code-bg);
        padding: 2px 6px;
        border-radius: 3px;
        font-family: Consolas, monospace;
        font-size: 13px;
    }
    pre {
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 12px 16px;
        overflow-x: auto;
        line-height: 1.4;
    }
    pre code { background: none; padding: 0; }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 1em 0;
    }
    th {
        background: var(--table-hd);
        color: var(--table-fg);
        padding: 8px 12px;
        text-align: left;
        font-weight: 600;
    }
    body.rtl th { text-align: right; }
    td {
        padding: 6px 12px;
        border-bottom: 1px solid var(--border);
    }
    tr:nth-child(even) td { background: var(--table-alt); }
    blockquote {
        border-left: 4px solid var(--accent);
        margin: 1em 0;
        padding: 8px 16px;
        background: #F8F9FA;
    }
    body.rtl blockquote {
        border-left: none;
        border-right: 4px solid var(--accent);
    }
    img { max-width: 100%; border-radius: 4px; }
    .note, .warning, .tip {
        padding: 12px 16px;
        margin: 1em 0;
        border-radius: 4px;
        border-left: 4px solid;
    }
    .note    { background: #E8F4FD; border-color: #2196F3; }
    .warning { background: #FFF3E0; border-color: #FF9800; }
    .tip     { background: #E8F5E9; border-color: #4CAF50; }

    /* Math (KaTeX-style inline) */
    .math { font-family: 'Latin Modern Math', 'STIX Two Math', serif; }

    /* TOC */
    .toc { background: #F8F9FA; border: 1px solid var(--border);
           border-radius: 4px; padding: 12px 20px; margin: 1em 0; }
    .toc ul { list-style: none; padding-left: 1.2em; }
    .toc > ul { padding-left: 0; }
    .toc a { color: var(--fg); }
    .toc a:hover { color: var(--accent); }
""")


# ═══════════════════════════════════════════════════════════════════════════
# Markdown → HTML
# ═══════════════════════════════════════════════════════════════════════════

def _create_md_parser() -> MarkdownIt:
    """Create a configured markdown-it-py parser."""
    md = MarkdownIt("commonmark", {"html": True, "typographer": True})
    md.enable(["table", "strikethrough"])
    return md


_parser = _create_md_parser()


def _highlight_code(code: str, lang: str) -> str:
    """Highlight a code block with Pygments."""
    if not _HAS_PYGMENTS or not lang:
        return f"<pre><code>{code}</code></pre>"
    try:
        lexer = get_lexer_by_name(lang, stripall=True)
    except Exception:
        lexer = TextLexer()
    fmt = HtmlFormatter(nowrap=True, style="friendly")
    highlighted = highlight(code, lexer, fmt)
    return f'<pre><code class="language-{lang}">{highlighted}</code></pre>'


def md_to_html(
    markdown_text: str,
    *,
    rtl: bool = False,
    title: str = "",
    standalone: bool = True,
    toc: bool = True,
) -> str:
    """Convert Markdown text to styled HTML.

    Parameters
    ----------
    markdown_text : str
        Source Markdown.
    rtl : bool
        Add RTL direction (Persian content).
    title : str
        HTML ``<title>``.
    standalone : bool
        If True, wraps in full ``<html>`` document with CSS.
        If False, returns just the ``<body>`` content.
    toc : bool
        Generate table of contents from headings.
    """
    body = _parser.render(markdown_text)

    # Code highlighting post-processing
    if _HAS_PYGMENTS:
        body = _apply_code_highlighting(body)

    # Build TOC
    toc_html = ""
    if toc:
        toc_html = _build_toc(body)

    if not standalone:
        return (toc_html + body) if toc_html else body

    body_class = 'class="rtl"' if rtl else ''
    html_dir = 'dir="rtl"' if rtl else ''

    return dedent(f"""\
    <!DOCTYPE html>
    <html lang="{'fa' if rtl else 'en'}" {html_dir}>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title or 'civilTools Help'}</title>
        <style>{HELP_CSS}</style>
    </head>
    <body {body_class}>
    {toc_html}
    {body}
    </body>
    </html>
    """)


def _apply_code_highlighting(html: str) -> str:
    """Find <pre><code class="language-xxx"> blocks and highlight them."""
    pattern = re.compile(
        r'<pre><code class="language-(\w+)">(.*?)</code></pre>',
        re.DOTALL,
    )

    def _replace(m):
        lang = m.group(1)
        code = m.group(2)
        # Unescape HTML entities that markdown-it escaped
        code = code.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return _highlight_code(code, lang)

    return pattern.sub(_replace, html)


def _build_toc(html: str) -> str:
    """Extract headings and build a table of contents."""
    heading_re = re.compile(r"<h([1-3])[^>]*>(.*?)</h\1>", re.DOTALL)
    headings = heading_re.findall(html)
    if len(headings) < 3:
        return ""  # too few headings, skip TOC

    items = []
    for level_str, text in headings:
        level = int(level_str)
        # Strip HTML tags from heading text
        clean = re.sub(r"<[^>]+>", "", text).strip()
        anchor = re.sub(r"[^\w\s-]", "", clean).strip().replace(" ", "-").lower()
        indent = "  " * (level - 1)
        items.append(f'{indent}<li><a href="#{anchor}">{clean}</a></li>')

    return '<div class="toc"><h3>Contents</h3><ul>\n' + "\n".join(items) + "\n</ul></div>\n"


# ═══════════════════════════════════════════════════════════════════════════
# File-level convenience
# ═══════════════════════════════════════════════════════════════════════════

def render_md_file(path: Path | str, **kwargs) -> str:
    """Read a .md file and return styled HTML."""
    text = Path(path).read_text("utf-8")
    return md_to_html(text, **kwargs)
