"""
In-app help panel — QDockWidget with HTML browser, TOC sidebar, and search.

Uses QTextBrowser (no WebEngine dependency) for lightweight rendering.
Falls back to QWebEngineView if available for richer display.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QAction, QKeySequence, QDesktopServices
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolBar,
    QComboBox,
    QFileDialog,
    QMessageBox,
)

from civiltools.help.help_engine import HelpEngine, HelpTopic


class HelpBrowser(QTextBrowser):
    """QTextBrowser with back-navigation and anchor handling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self._history: list[str] = []
        self._pos: int = -1

    def setHtml(self, html: str, topic_id: str = ""):
        super().setHtml(html)
        if topic_id and (self._pos < 0 or self._history[self._pos] != topic_id):
            self._history = self._history[: self._pos + 1]
            self._history.append(topic_id)
            self._pos = len(self._history) - 1

    def can_go_back(self) -> bool:
        return self._pos > 0

    def can_go_forward(self) -> bool:
        return self._pos < len(self._history) - 1

    def go_back(self) -> str:
        if self.can_go_back():
            self._pos -= 1
            return self._history[self._pos]
        return ""

    def go_forward(self) -> str:
        if self.can_go_forward():
            self._pos += 1
            return self._history[self._pos]
        return ""

    def _on_anchor(self, url: QUrl):
        scheme = url.scheme()
        if scheme in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif not scheme and url.fragment():
            # Internal anchor
            self.scrollToAnchor(url.fragment())


class _TopicListWidget(QListWidget):
    """Filterable topic list."""

    topic_selected = Signal(str)  # topic_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, str, str]] = []  # (id, title, title_fa)
        self.currentItemChanged.connect(self._on_change)

    def load_topics(self, topics: list[HelpTopic]):
        self._items.clear()
        for t in topics:
            self._items.append((t.id, t.title, t.title_fa))
        self._rebuild()

    def filter(self, text: str):
        text = text.lower()
        self.clear()
        for tid, title, title_fa in self._items:
            if text in title.lower() or text in title_fa.lower() or text in tid.lower():
                item = QListWidgetItem(f"{title}  {title_fa}" if title_fa else title)
                item.setData(Qt.UserRole, tid)
                self.addItem(item)

    def _rebuild(self):
        self.clear()
        for tid, title, title_fa in self._items:
            display = f"{title}  {title_fa}" if title_fa else title
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, tid)
            self.addItem(item)

    def _on_change(self, current: QListWidgetItem, _prev):
        if current:
            self.topic_selected.emit(current.data(Qt.UserRole))


class HelpPanel(QDockWidget):
    """
    Dockable help panel.

    Usage::

        panel = HelpPanel(parent=main_window)
        main_window.addDockWidget(Qt.RightDockWidgetArea, panel)
        panel.show_topic("getting_started")    # explicit
        panel.show_context("control.beam_deflection")  # context-sensitive
    """

    def __init__(self, parent=None, engine: HelpEngine | None = None, lang: str = "en"):
        super().__init__("Help", parent)
        self.setObjectName("HelpPanel")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(360)

        self._engine = engine or HelpEngine()
        self._lang = lang

        self._build_ui()
        self._load_topics()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)

        # Toolbar
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize() * 0.8)

        self._btn_back = QAction("◀", self)
        self._btn_back.setToolTip("Back")
        self._btn_back.triggered.connect(self._go_back)
        tb.addAction(self._btn_back)

        self._btn_fwd = QAction("▶", self)
        self._btn_fwd.setToolTip("Forward")
        self._btn_fwd.triggered.connect(self._go_forward)
        tb.addAction(self._btn_fwd)

        self._btn_home = QAction("🏠", self)
        self._btn_home.setToolTip("Home")
        self._btn_home.triggered.connect(self._go_home)
        tb.addAction(self._btn_home)

        tb.addSeparator()

        self._btn_pdf = QAction("PDF", self)
        self._btn_pdf.setToolTip("Export all help to PDF")
        self._btn_pdf.triggered.connect(self._export_pdf)
        tb.addAction(self._btn_pdf)

        self._btn_docx = QAction("DOCX", self)
        self._btn_docx.setToolTip("Export all help to DOCX")
        self._btn_docx.triggered.connect(self._export_docx)
        tb.addAction(self._btn_docx)

        layout.addWidget(tb)

        # Search bar
        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search help…")
        self._search_edit.textChanged.connect(self._on_search)
        self._search_edit.setClearButtonEnabled(True)
        search_row.addWidget(self._search_edit)
        layout.addLayout(search_row)

        # Splitter: topic list | browser
        splitter = QSplitter(Qt.Horizontal)

        self._topic_list = _TopicListWidget()
        self._topic_list.topic_selected.connect(self.show_topic)
        splitter.addWidget(self._topic_list)

        self._browser = HelpBrowser()
        splitter.addWidget(self._browser)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, 1)
        self.setWidget(container)

    # ── Topic Management ──────────────────────────────────────────────

    def _load_topics(self):
        self._engine.ensure_loaded()
        topics = self._engine.all_topics()
        self._topic_list.load_topics(topics)
        if topics:
            self.show_topic(topics[0].id)

    def show_topic(self, topic_id: str):
        """Display a help topic by its id."""
        rtl = self._lang == "fa"
        html = self._engine.render_topic_html(topic_id, rtl=rtl)
        self._browser.setHtml(html, topic_id=topic_id)
        self._update_nav()

    def show_context(self, context: str):
        """Show help for a GUI context string (e.g. 'control.beam_deflection')."""
        topic = self._engine.get_by_context(context)
        if topic:
            self.show_topic(topic.id)
            self.show()
            self.raise_()
        else:
            # Fall back to index
            self._go_home()
            self.show()

    def set_language(self, lang: str):
        self._lang = lang

    # ── Navigation ────────────────────────────────────────────────────

    def _go_back(self):
        tid = self._browser.go_back()
        if tid:
            self.show_topic(tid)

    def _go_forward(self):
        tid = self._browser.go_forward()
        if tid:
            self.show_topic(tid)

    def _go_home(self):
        topics = self._engine.all_topics()
        if topics:
            self.show_topic(topics[0].id)

    def _update_nav(self):
        self._btn_back.setEnabled(self._browser.can_go_back())
        self._btn_fwd.setEnabled(self._browser.can_go_forward())

    # ── Search ────────────────────────────────────────────────────────

    def _on_search(self, text: str):
        if not text.strip():
            self._load_topics()
            return
        results = self._engine.search(text)
        self._topic_list.load_topics(results)

    # ── Export ─────────────────────────────────────────────────────────

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Help to PDF", "civiltools_help.pdf", "PDF Files (*.pdf)"
        )
        if path:
            try:
                self._engine.export_pdf(path, rtl=(self._lang == "fa"))
                QMessageBox.information(self, "Export", f"PDF saved to:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Error", str(e))

    def _export_docx(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Help to DOCX", "civiltools_help.docx", "Word Files (*.docx)"
        )
        if path:
            try:
                self._engine.export_docx(path, rtl=(self._lang == "fa"))
                QMessageBox.information(self, "Export", f"DOCX saved to:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Error", str(e))
