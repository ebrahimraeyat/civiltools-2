"""
Joint Shear Check Dialog — ACI 318-19 §18.8
============================================
A self-contained PySide6 dialog that runs ``JointShearChecker`` from
``etabs_api`` in a background thread and displays the results in a
``ResultWidget`` with:
  - A  ``Ratio (ETABS)`` column compared against the manually computed ratio.
  - A detail pane (via the ``__detail__`` column) that shows full calculation
    notes for the selected row.
"""

from __future__ import annotations

import json
import traceback

import pandas as pd
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QLabel, QMessageBox, QProgressBar, QGroupBox,
    QSizePolicy, QWidget,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.result_widget import ResultWidget
from civiltools.gui.helpers import set_dialog_icon


# ──────────────────────────────────────────────────────────────────────
# Background worker
# ──────────────────────────────────────────────────────────────────────

class _Worker(QThread):
    """Runs JointShearChecker in a background thread."""

    finished = Signal(object)   # pd.DataFrame
    errored  = Signal(str)      # traceback string

    def __init__(self, etabs, mode: str, structure_type: str, ductility: str,
                 lambda_: float, cover_mm: float, parent=None):
        super().__init__(parent)
        self._etabs    = etabs
        self._mode     = mode               # "etabs" | "software" | "both"
        self._structure_type = structure_type
        self._ductility = ductility
        self._lambda    = lambda_
        self._cover_mm  = cover_mm

    def run(self):
        try:
            if self._mode == "etabs":
                # Native ETABS joint-shear / beam-column-capacity ratios.
                self._etabs.save()
                df = self._etabs.create_joint_shear_bcc_file(
                    file_name="jsbc",
                    structure_type=self._structure_type,
                    open_main_file=True,
                    create_file=True,
                )
            else:
                # Software calculation (ACI 318-19 §18.8); run() also merges
                # the ETABS ratio columns into the same table.
                from etabs_api.joint_shear import JointShearChecker
                checker = JointShearChecker(
                    self._etabs,
                    ductility=self._ductility,
                    lambda_=self._lambda,
                    cover_mm=self._cover_mm,
                )
                df = checker.run()
            if df is None:
                df = pd.DataFrame()
            self.finished.emit(df)
        except Exception:
            self.errored.emit(traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────

class JointShearDialog(QDialog):
    """
    GUI dialog for ACI 318-19 § 18.8 joint shear check.

    Input parameters
    ----------------
    - Ductility level   : Intermediate (IMF) or High (SMF)
    - Lambda (λ)        : lightweight concrete factor (0.75 – 1.0)
    - Cover             : clear concrete cover in mm (20 – 100)

    Results are shown in a ``ResultWidget`` that includes:
    - All computed columns
    - ``Ratio (ETABS)`` fetched from ETABS database (best-effort)
    - ``__detail__`` column (hidden in table; shown in pane on row click)
    """

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs  = etabs
        self._result: CommandResult | None = None
        self._worker: _Worker | None = None

        self.setWindowTitle("Joint Shear Check — ACI 318-19 §18.8")
        self.resize(1100, 700)
        try:
            set_dialog_icon(self, "joint_shear.svg")
        except Exception:
            pass

        self._build_ui()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Parameters group ──────────────────────────────────────
        params_group = QGroupBox("Parameters")
        form = QFormLayout(params_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._source_combo = QComboBox()
        self._source_combo.addItems(
            ["ETABS only", "Software only", "Both (software + ETABS)"]
        )
        self._source_combo.setCurrentIndex(2)
        self._source_combo.setToolTip(
            "ETABS only: fast — native ETABS joint-shear / BCC ratios.\n"
            "Software only: civilTools ACI 318-19 §18.8 calculation.\n"
            "Both: software calculation with the ETABS ratios side by side."
        )
        form.addRow("Results source:", self._source_combo)

        self._ductility_combo = QComboBox()
        self._ductility_combo.addItems(["Intermediate (IMF)", "High (SMF)"])
        self._try_auto_ductility()
        form.addRow("Ductility level:", self._ductility_combo)

        self._lambda_spin = QDoubleSpinBox()
        self._lambda_spin.setRange(0.75, 1.0)
        self._lambda_spin.setSingleStep(0.05)
        self._lambda_spin.setValue(1.0)
        self._lambda_spin.setDecimals(2)
        self._lambda_spin.setToolTip(
            "Lightweight concrete factor λ (ACI 318-19 §19.2.4)\n1.0 = normal-weight concrete"
        )
        form.addRow("Lambda (λ):", self._lambda_spin)

        self._cover_spin = QSpinBox()
        self._cover_spin.setRange(20, 100)
        self._cover_spin.setValue(40)
        self._cover_spin.setSuffix(" mm")
        self._cover_spin.setToolTip("Clear concrete cover in mm")
        form.addRow("Clear cover:", self._cover_spin)

        root.addWidget(params_group)

        # ── Run button row ────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("▶  Run Joint Shear Check")
        self._run_btn.setFixedHeight(36)
        self._run_btn.setStyleSheet(
            "QPushButton { font-weight: bold; background: #1e6fba; color: white; border-radius: 4px; }"
            "QPushButton:hover { background: #1558a0; }"
            "QPushButton:disabled { background: #999; }"
        )
        self._run_btn.clicked.connect(self._run)
        btn_row.addWidget(self._run_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        btn_row.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._progress.setFixedWidth(180)
        btn_row.addWidget(self._progress)

        root.addLayout(btn_row)

        # ── Results area ──────────────────────────────────────────
        self._results_placeholder = QLabel(
            "<i style='color:#888'>Press <b>Run</b> to compute joint shear ratios.</i>"
        )
        self._results_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._results_container = QWidget()
        container_layout = QVBoxLayout(self._results_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self._results_placeholder)
        root.addWidget(self._results_container, stretch=1)

        # ── Close button ──────────────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row2 = QHBoxLayout()
        btn_row2.addStretch()
        btn_row2.addWidget(close_btn)
        root.addLayout(btn_row2)

    def _try_auto_ductility(self):
        """Pre-select ductility from the ETABS model if possible."""
        try:
            from civiltools.etabs.config import get_settings_from_etabs
            d = get_settings_from_etabs(self._etabs)
            ductilities = self._etabs.get_x_and_y_system_ductility(d)
            if "H" in ductilities:
                self._ductility_combo.setCurrentIndex(1)
        except Exception:
            pass

    # ── Run logic ──────────────────────────────────────────────────

    def _run(self):
        self._run_btn.setEnabled(False)
        self._progress.show()
        self._status_lbl.setText("Running check…")

        ductility_text = self._ductility_combo.currentText()
        ductility = "high" if "High" in ductility_text else "intermediate"
        structure_type = "Sway Special" if ductility == "high" else "Sway Intermediate"
        lambda_   = self._lambda_spin.value()
        cover_mm  = float(self._cover_spin.value())

        source_text = self._source_combo.currentText()
        if source_text.startswith("ETABS"):
            mode = "etabs"
        elif source_text.startswith("Software"):
            mode = "software"
        else:
            mode = "both"
        self._mode = mode

        self._worker = _Worker(
            self._etabs, mode, structure_type, ductility, lambda_, cover_mm, parent=self
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.errored.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, df: pd.DataFrame):
        self._progress.hide()
        self._run_btn.setEnabled(True)

        if df is None or df.empty:
            self._status_lbl.setText("⚠ No results (no qualifying joints found).")
            return

        mode = getattr(self, "_mode", "both")

        # Software-only: hide the merged ETABS ratio columns.
        if mode == "software":
            df = df[[c for c in df.columns if "(ETABS)" not in c]]

        title = {
            "etabs": "Joint Shear — ETABS",
            "software": "Joint Shear — ACI 318-19 §18.8 (software)",
            "both": "Joint Shear — software + ETABS",
        }.get(mode, "Joint Shear")

        # Summary + pass/fail depend on the data shape.
        if "Status" in df.columns:
            ng_count = int((df["Status"] == "NG").sum())
            ok_count = int((df["Status"] == "OK").sum())
            all_ok   = ng_count == 0
            summary  = f"Total: {len(df)}  |  ✓ OK: {ok_count}  |  ✗ NG: {ng_count}"
        else:
            # ETABS table: NG when any JS/BC ratio > 1.
            ratio_cols = [
                c for c in df.columns
                if any(k in c for k in ("JSMaj", "JSMin", "BCMaj", "BCMin"))
            ]
            ng_count = 0
            max_ratio = 0.0
            if ratio_cols:
                vals = df[ratio_cols].apply(pd.to_numeric, errors="coerce")
                ng_count = int((vals > 1.0).any(axis=1).sum())
                try:
                    max_ratio = float(vals.max().max())
                except (ValueError, TypeError):
                    max_ratio = 0.0
            all_ok  = ng_count == 0
            summary = (
                f"Total: {len(df)}  |  ✗ Exceeding 1.0: {ng_count}  |  "
                f"Max ratio: {max_ratio:.3f}"
            )

        self._status_lbl.setText(summary)
        self._df = df  # keep reference for row-selection callback

        try:
            from civiltools.gui.table_models import JointShearBCCModel as model_cls
        except ImportError:
            from civiltools.gui.table_models import PandasModel as model_cls

        result_widget = ResultWidget(
            df=df,
            model_class=model_cls,
            title=title,
            summary=summary,
            ok=all_ok,
        )

        # Joint plan view — only the software check carries joint geometry.
        if "__geometry__" in df.columns:
            from civiltools.gui.joint_plan_widget import JointPlanWidget
            self._plan_widget = JointPlanWidget()
            result_widget.add_right_panel(self._plan_widget)
            result_widget.selection_changed.connect(self._on_joint_selected)

        layout = self._results_container.layout()
        old = layout.itemAt(0)
        if old and old.widget():
            old.widget().hide()
            layout.removeWidget(old.widget())
        layout.addWidget(result_widget)

        self._result = CommandResult(title="Joint Shear", ok=all_ok, dataframe=df)
        self._report_params = {
            "structure_type": structure_type,
            "show_js": mode != "software",
            "show_bc": mode != "software",
        }

    def _on_joint_selected(self, df_row: int):
        """Decode geometry from the selected row and update the plan widget."""
        df = getattr(self, "_df", None)
        if df is None:
            return
        row = df.iloc[df_row]
        geom = None
        if "__geometry__" in df.columns:
            try:
                geom = json.loads(str(row["__geometry__"]))
            except Exception:
                geom = None
        ratio = None
        ratio_etabs = None
        try:
            ratio = float(row["Ratio"])
        except (KeyError, ValueError, TypeError):
            pass
        try:
            ratio_etabs = row["Ratio (ETABS)"]
        except KeyError:
            pass
        self._plan_widget.set_geometry(geom, ratio=ratio, ratio_etabs=ratio_etabs)

    def _on_error(self, tb: str):
        self._progress.hide()
        self._run_btn.setEnabled(True)
        self._status_lbl.setText("✗ Error — see details.")
        QMessageBox.critical(
            self, "Joint Shear Check Error",
            f"<pre style='font-family:Courier New;font-size:11px'>{tb}</pre>",
        )

    @property
    def result(self) -> CommandResult | None:
        return self._result

    @property
    def report_params(self) -> dict:
        return getattr(self, "_report_params", {})
