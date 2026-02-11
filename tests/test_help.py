"""
Tests for the help system.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from civiltools.help.help_engine import HelpEngine


@pytest.fixture
def engine():
    """Help engine loaded from the bundled content directory."""
    content_dir = Path(__file__).resolve().parent.parent / "src" / "civiltools" / "help" / "content"
    return HelpEngine(content_dir)


class TestHelpEngine:
    def test_loads_topics(self, engine):
        engine.ensure_loaded()
        topics = engine.all_topics()
        assert len(topics) >= 4  # index, getting_started, viewer, seismic, reports, licensing

    def test_get_topic(self, engine):
        topic = engine.get_topic("index")
        assert topic is not None
        assert "civilTools" in topic.body

    def test_context_lookup(self, engine):
        topic = engine.get_by_context("help.index")
        assert topic is not None
        assert topic.id == "index"

    def test_search(self, engine):
        results = engine.search("seismic")
        assert len(results) >= 1
        ids = [t.id for t in results]
        assert "seismic_design" in ids

    def test_render_html(self, engine):
        html = engine.render_topic_html("getting_started")
        assert "<html" in html.lower() or "<h1" in html.lower()

    def test_all_md_paths(self, engine):
        paths = engine.all_md_paths()
        assert all(p.suffix == ".md" for p in paths)
        assert len(paths) >= 4
