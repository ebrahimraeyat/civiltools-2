"""
Help engine — manages help content, context-sensitive lookup, search, and export.

Architecture:
    help/content/         ← Markdown .md source files (you edit these)
        index.md          ← Top-level help overview
        getting_started.md
        beam_deflection.md
        ...

    Each .md file has a YAML-like front-matter block:

        ---
        id: beam_deflection
        title: Beam Deflection Check
        title_fa: کنترل خیز تیر
        context: control.beam_deflection
        order: 10
        ---

    The ``context`` field links a help topic to a GUI feature.
    Call ``help_engine.show("control.beam_deflection")`` from any dialog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HelpTopic:
    """A single help topic parsed from a .md file."""

    id: str
    title: str
    title_fa: str
    context: str           # dot-separated feature path, e.g. "control.beam_deflection"
    order: int
    source_path: Path
    body: str              # Markdown body (without front-matter)


class HelpEngine:
    """Load, search, and serve help topics."""

    def __init__(self, content_dir: Path | str | None = None):
        if content_dir is None:
            content_dir = Path(__file__).parent / "content"
        self._dir = Path(content_dir)
        self._topics: dict[str, HelpTopic] = {}     # keyed by topic.id
        self._context_map: dict[str, str] = {}       # context → topic.id
        self._loaded = False

    def ensure_loaded(self):
        if not self._loaded:
            self._load_all()
            self._loaded = True

    # ── Loading ───────────────────────────────────────────────────────

    def _load_all(self):
        if not self._dir.exists():
            return
        for md_file in sorted(self._dir.glob("**/*.md")):
            topic = self._parse_topic(md_file)
            if topic:
                self._topics[topic.id] = topic
                if topic.context:
                    self._context_map[topic.context] = topic.id

    @staticmethod
    def _parse_topic(path: Path) -> Optional[HelpTopic]:
        """Parse a .md file with optional YAML front-matter."""
        text = path.read_text("utf-8")

        # Extract front-matter
        meta = {}
        body = text
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = text[fm_match.end():]

        topic_id = meta.get("id", path.stem)
        return HelpTopic(
            id=topic_id,
            title=meta.get("title", topic_id.replace("_", " ").title()),
            title_fa=meta.get("title_fa", ""),
            context=meta.get("context", ""),
            order=int(meta.get("order", 50)),
            source_path=path,
            body=body,
        )

    # ── Queries ───────────────────────────────────────────────────────

    def get_topic(self, topic_id: str) -> Optional[HelpTopic]:
        self.ensure_loaded()
        return self._topics.get(topic_id)

    def get_by_context(self, context: str) -> Optional[HelpTopic]:
        """Find help topic for a GUI context string."""
        self.ensure_loaded()
        tid = self._context_map.get(context)
        return self._topics.get(tid) if tid else None

    def all_topics(self) -> list[HelpTopic]:
        """All topics sorted by order."""
        self.ensure_loaded()
        return sorted(self._topics.values(), key=lambda t: (t.order, t.title))

    def search(self, query: str) -> list[HelpTopic]:
        """Simple text search across title and body."""
        self.ensure_loaded()
        q = query.lower()
        results = []
        for t in self._topics.values():
            if (q in t.title.lower()
                    or q in t.title_fa.lower()
                    or q in t.body.lower()):
                results.append(t)
        return sorted(results, key=lambda t: t.order)

    def all_md_paths(self) -> list[Path]:
        """All .md file paths in topic order (for PDF export)."""
        return [t.source_path for t in self.all_topics()]

    # ── Render ────────────────────────────────────────────────────────

    def render_topic_html(self, topic_id: str, rtl: bool = False) -> str:
        """Render a single topic to HTML."""
        from civiltools.help.md_renderer import md_to_html

        topic = self.get_topic(topic_id)
        if not topic:
            return f"<h1>Topic not found: {topic_id}</h1>"
        return md_to_html(topic.body, rtl=rtl, title=topic.title)

    def render_index_html(self, lang: str = "en") -> str:
        """Render a topic index page as HTML."""
        from civiltools.help.md_renderer import md_to_html

        rtl = lang == "fa"
        lines = ["# civilTools Help\n"]
        for topic in self.all_topics():
            title = topic.title_fa if (rtl and topic.title_fa) else topic.title
            lines.append(f"- [{title}](#{topic.id})")
        return md_to_html("\n".join(lines), rtl=rtl, title="civilTools Help")

    # ── Export ─────────────────────────────────────────────────────────

    def export_pdf(self, output: Path | str, rtl: bool = False):
        """Export all help topics to a single PDF."""
        from civiltools.help.md_to_pdf import md_to_pdf

        return md_to_pdf(
            self.all_md_paths(),
            output,
            rtl=rtl,
            title="civilTools Help Manual",
            subtitle="Complete Reference",
        )

    def export_docx(self, output: Path | str, rtl: bool = False):
        """Export all help topics to a single DOCX."""
        from civiltools.help.md_to_docx import md_to_docx

        return md_to_docx(
            self.all_md_paths(),
            output,
            rtl=rtl,
            title="civilTools Help Manual",
        )
