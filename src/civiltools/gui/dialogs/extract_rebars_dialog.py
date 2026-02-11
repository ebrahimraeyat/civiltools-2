"""
Extract rebar data from AutoCAD — dialog.

This dialog does NOT require an ETABS connection.  It connects directly
to a running AutoCAD instance via COM (win32com), reads Text/MText
rebar annotations, and shows results in a colour-coded table.

Incomplete rows are red; the user can highlight them back in AutoCAD.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSpinBox,
    QMessageBox,
    QApplication,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon


class ExtractRebarsDialog(QDialog):
    """Standalone dialog — reads rebar annotations from AutoCAD."""

    def __init__(self, etabs: Any = None, parent=None):
        # *etabs* is accepted (but ignored) so the dialog fits the
        # standard  ``dlg_cls(self._conn.etabs, parent=self)``  call
        # in MainWindow._run_dialog_command.
        super().__init__(parent)
        self._result: CommandResult | None = None
        self._engine = None  # lazy — created on first use
        self._rebar_data: list = []

        self.setWindowTitle("Extract Rebars from AutoCAD")
        self.setMinimumSize(950, 550)
        self.resize(1150, 680)
        set_dialog_icon(self, "rebars.svg")

        self._build_ui()

    # ------------------------------------------------------------------
    #  UI construction (programmatic — no .ui file needed)
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Top buttons ─────────────────────────────────────────────
        top = QHBoxLayout()

        self.btn_from_sel = QPushButton("Read from Selection")
        self.btn_from_sel.setToolTip(
            "Read rebar texts from user-selected objects in AutoCAD")
        self.btn_from_sel.clicked.connect(self._read_from_selection)
        top.addWidget(self.btn_from_sel)

        self.btn_from_all = QPushButton("Read All Texts")
        self.btn_from_all.setToolTip(
            "Read ALL Text/MText in model space and parse rebar info")
        self.btn_from_all.clicked.connect(self._read_from_all)
        top.addWidget(self.btn_from_all)

        top.addStretch()

        top.addWidget(QLabel("Proximity:"))
        self.prox_spin = QSpinBox()
        self.prox_spin.setRange(5, 200)
        self.prox_spin.setValue(20)
        self.prox_spin.setToolTip(
            "Max distance (× text height) for matching\n"
            "main-rebar text with its L=… text.\n"
            "Increase if lengths are not being paired.")
        top.addWidget(self.prox_spin)

        layout.addLayout(top)

        # ── Summary label ───────────────────────────────────────────
        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

        # ── Table (will be a ResultWidget embedded here) ────────────
        self._table_container = QVBoxLayout()
        layout.addLayout(self._table_container)

        # ── Summary-by-size table ──────────────────────────────────
        self._summary_container = QVBoxLayout()
        layout.addLayout(self._summary_container)

        # ── Total weight ────────────────────────────────────────────
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(self.total_label)

        # ── Bottom buttons ──────────────────────────────────────────
        bot = QHBoxLayout()

        self.btn_highlight = QPushButton("Select Incomplete in AutoCAD")
        self.btn_highlight.setEnabled(False)
        self.btn_highlight.setToolTip(
            "Highlight incomplete rebar texts in AutoCAD and zoom to them")
        self.btn_highlight.clicked.connect(self._highlight_incomplete)
        bot.addWidget(self.btn_highlight)

        bot.addStretch()

        self.btn_done = QPushButton("Done")
        self.btn_done.setToolTip("Accept results and show in table tab")
        self.btn_done.setEnabled(False)
        self.btn_done.clicked.connect(self._accept)
        bot.addWidget(self.btn_done)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        bot.addWidget(btn_close)

        layout.addLayout(bot)

    # ------------------------------------------------------------------
    #  Lazy engine creation
    # ------------------------------------------------------------------
    def _ensure_engine(self):
        if self._engine is not None:
            return True
        try:
            from civiltools.building.rebar_from_dwg import RebarFromDwg
            self._engine = RebarFromDwg()
            return True
        except Exception as exc:
            QMessageBox.critical(
                self, "AutoCAD Connection Error",
                f"Cannot connect to AutoCAD:\n\n{exc}\n\n"
                "Make sure AutoCAD is running with a drawing open.")
            return False

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------
    def _read_from_selection(self):
        if not self._ensure_engine():
            return
        self._engine.PROXIMITY_FACTOR = self.prox_spin.value()
        texts = self._engine.get_text_objects_from_selection()
        self._process(texts)

    def _read_from_all(self):
        if not self._ensure_engine():
            return
        self._engine.PROXIMITY_FACTOR = self.prox_spin.value()
        texts = self._engine.get_all_text_objects()
        self._process(texts)

    def _process(self, texts):
        if not texts:
            QMessageBox.warning(
                self, "No Text Found",
                "No Text / MText objects found.\n"
                "Make sure rebar annotations exist in model space.")
            return

        rebars = self._engine.parse_rebars()
        if not rebars:
            QMessageBox.information(
                self, "No Rebars",
                f"{len(texts)} text objects were read but none matched "
                "a rebar format.\n\n"
                "Expected formats:\n"
                "  Main:  4∅20@25  +  L=1200cm  (two texts)\n"
                "  Additional:  1∅25  L=440  (one text)")
            return

        self._rebar_data = rebars
        self._show_result_widget(rebars)

        s = self._engine.summary()
        self.summary_label.setText(
            f"Found {s['total']} rebar entries  —  "
            f"{s['main']} main,  {s['additional']} additional   |   "
            f"Complete: {s['complete']}   Incomplete: {s['incomplete']}")

        total_w = sum(r.weight_kg() or 0 for r in rebars)
        self.total_label.setText(
            f"Total weight (complete items): {total_w:,.1f} kg")

        self._show_summary_table(rebars)

        self.btn_highlight.setEnabled(s['incomplete'] > 0)
        self.btn_done.setEnabled(True)

    def _show_result_widget(self, rebars):
        """Build an inline ResultWidget inside the dialog."""
        # Clear previous
        while self._table_container.count():
            item = self._table_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        df = self._build_dataframe(rebars)

        from civiltools.gui.table_models import RebarModel
        from civiltools.gui.result_widget import ResultWidget

        widget = ResultWidget(
            df=df,
            model_class=RebarModel,
            title="",
            summary="",
            ok=all(r.complete for r in rebars),
            parent=self,
        )
        self._table_container.addWidget(widget)

    def _show_summary_table(self, rebars):
        """Build and show the summary-by-size table below the detail table."""
        # Clear previous
        while self._summary_container.count():
            item = self._summary_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        summary_rows = self._engine.summary_by_size()
        if not summary_rows:
            return

        df = pd.DataFrame(summary_rows)

        from civiltools.gui.table_models import RebarSummaryModel
        from civiltools.gui.result_widget import ResultWidget

        widget = ResultWidget(
            df=df,
            model_class=RebarSummaryModel,
            title="Summary by Size",
            summary="",
            ok=True,
            parent=self,
        )
        self._summary_container.addWidget(widget)

    @staticmethod
    def _build_dataframe(rebars) -> pd.DataFrame:
        rows = []
        for i, rb in enumerate(rebars, 1):
            rows.append({
                '#': i,
                'Type': rb.rebar_type or '?',
                'Count': rb.count if rb.count is not None else None,
                'Diameter (mm)': rb.diameter if rb.diameter is not None else None,
                'Spacing (cm)': rb.spacing if rb.spacing is not None else None,
                'Length (cm)': rb.length if rb.length is not None else None,
                'Weight (kg)': rb.weight_kg(),
                'Raw Text': ' | '.join(rb.raw_texts),
                'Status': ('OK' if rb.complete
                           else f"Missing: {', '.join(rb.errors)}"),
                '_complete': rb.complete,
            })
        return pd.DataFrame(rows)

    def _highlight_incomplete(self):
        if self._engine is None:
            return
        n = self._engine.highlight_incomplete()
        if n:
            QMessageBox.information(
                self, "Incomplete Rebars",
                f"{n} incomplete rebar text(s) highlighted in AutoCAD.")
        else:
            QMessageBox.information(
                self, "All Complete", "All rebar entries are complete!")

    def _accept(self):
        """Build a CommandResult so MainWindow can show it as a tab."""
        if not self._rebar_data:
            self.reject()
            return

        df = self._build_dataframe(self._rebar_data)
        total_w = sum(r.weight_kg() or 0 for r in self._rebar_data)
        s = self._engine.summary()

        # Build summary dataframe
        summary_rows = self._engine.summary_by_size()
        df_summary = pd.DataFrame(summary_rows) if summary_rows else None

        self._result = CommandResult(
            title="Rebar List from AutoCAD",
            dataframe=df,
            summary=(
                f"Total: {s['total']}  |  Main: {s['main']}  "
                f"Additional: {s['additional']}  |  "
                f"Complete: {s['complete']}  Incomplete: {s['incomplete']}  |  "
                f"Weight: {total_w:,.1f} kg"),
            ok=s['incomplete'] == 0,
            kwargs={'summary_df': df_summary},
        )
        super().accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
