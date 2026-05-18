"""
civiltools.gui.dialogs.billboard_wind_dialog
============================================
Standalone Qt dialog for billboard wind load calculation
per Iranian National Building Code – Section 6 (مبحث ششم), Chapter 10.

No ETABS connection required — this is a self-contained design tool.
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings
from pathlib import Path

_SESSION_FILE = Path.home() / ".civiltools" / "billboard_wind_session.json"

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QDoubleValidator, QFont, QColor, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
    QWidget,
    QSizePolicy,
    QApplication,
)

from civiltools.wind.billboard import (
    BillboardInputs,
    WindLoadOutput,
    calculate_wind_load,
    WIND_SPEEDS,
)


# ── Colour constants ──────────────────────────────────────────────────────────
_COLOR_HEADER_BG  = "#1e3c78"   # dark blue
_COLOR_HEADER_FG  = "#ffffff"
_COLOR_RESULT_BG  = "#f0f4fc"   # very light blue
_COLOR_RESULT_VAL = "#1a6b1a"   # dark green for result values
_COLOR_STEP_BG    = "#e8f5e9"   # light green for step boxes
_COLOR_WARN       = "#b71c1c"   # red for warnings
_COLOR_BORDER     = "#c0cfe8"


class _ResultRow(QWidget):
    """
    A horizontal widget showing ``label : value`` with styled colours.
    Used inside the results panel.
    """

    def __init__(
        self,
        label: str,
        value: str = "—",
        is_primary: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setMinimumWidth(240)
        font = lbl.font()
        font.setPointSize(10)
        if is_primary:
            font.setBold(True)
        lbl.setFont(font)
        layout.addWidget(lbl)

        self._value_label = QLabel(value)
        val_font = self._value_label.font()
        val_font.setPointSize(10)
        val_font.setBold(True)
        self._value_label.setFont(val_font)
        self._value_label.setStyleSheet(f"color: {_COLOR_RESULT_VAL};")
        self._value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._value_label)
        layout.addStretch()

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)


class _BillboardSketch(QWidget):
    """
    Schematic side-view of a billboard on its support column.

    Shows the billboard panel (rectangle) with dimension labels:
      h  — sign height
      w  — sign width (= support length l)
      b  — bottom elevation from ground
    Automatically redraws when update() is called.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._h = 2.0
        self._w = 4.0
        self._b = 1.0

    def set_dims(self, h: float, w: float, b: float) -> None:
        self._h = max(h, 0.01)
        self._w = max(w, 0.01)
        self._b = max(b, 0.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        W = self.width()
        H = self.height()
        margin = 36

        total_h = self._b + self._h          # total height from ground to top
        scale = (H - margin * 2) / total_h   # pixels per metre

        # ── Ground line ──────────────────────────────────────────────────────
        ground_y = H - margin
        painter.setPen(QPen(QColor("#555"), 2))
        painter.drawLine(margin // 2, ground_y, W - margin // 2, ground_y)

        # Ground hatch
        painter.setPen(QPen(QColor("#888"), 1))
        for i in range(6):
            x = margin // 2 + i * 18
            painter.drawLine(x, ground_y, x - 10, ground_y + 10)

        # ── Support column ───────────────────────────────────────────────────
        col_x = W // 2
        support_top_y = ground_y - int(self._b * scale)
        painter.setPen(QPen(QColor("#1e3c78"), 3))
        painter.drawLine(col_x, ground_y, col_x, support_top_y)

        # ── Billboard panel ───────────────────────────────────────────────────
        panel_w_px = min(int(self._w * scale), W - margin * 2)
        panel_h_px = int(self._h * scale)
        panel_x = col_x - panel_w_px // 2
        panel_y = support_top_y - panel_h_px

        painter.setPen(QPen(QColor("#1e3c78"), 2))
        painter.setBrush(QBrush(QColor("#d0e4f7")))
        painter.drawRect(panel_x, panel_y, panel_w_px, panel_h_px)

        # Wind arrow on the panel
        arrow_y = panel_y + panel_h_px // 2
        ax1 = panel_x - 28
        ax2 = panel_x - 4
        painter.setPen(QPen(QColor("#c62828"), 2))
        painter.drawLine(ax1, arrow_y, ax2, arrow_y)
        painter.setBrush(QBrush(QColor("#c62828")))
        pts = [QPointF(ax2, arrow_y),
               QPointF(ax2 - 8, arrow_y - 5),
               QPointF(ax2 - 8, arrow_y + 5)]
        path = QPainterPath()
        path.moveTo(pts[0])
        path.lineTo(pts[1])
        path.lineTo(pts[2])
        path.closeSubpath()
        painter.drawPath(path)
        painter.setPen(QPen(QColor("#c62828"), 1))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(ax1 - 2, arrow_y - 6, "Wind")

        # ── Dimension labels ──────────────────────────────────────────────────
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QPen(QColor("#1a6b1a"), 1))

        # h — right side of panel (double arrow)
        dax = panel_x + panel_w_px + 6
        painter.drawLine(dax, panel_y, dax, panel_y + panel_h_px)
        painter.drawLine(dax - 3, panel_y + 2, dax + 3, panel_y + 2)
        painter.drawLine(dax - 3, panel_y + panel_h_px - 2, dax + 3, panel_y + panel_h_px - 2)
        painter.drawText(dax + 5, panel_y + panel_h_px // 2 + 4,
                         f"h={self._h:.1f}m")

        # w — top of panel
        painter.drawLine(panel_x, panel_y - 6, panel_x + panel_w_px, panel_y - 6)
        painter.drawLine(panel_x + 2, panel_y - 9, panel_x + 2, panel_y - 3)
        painter.drawLine(panel_x + panel_w_px - 2, panel_y - 9,
                         panel_x + panel_w_px - 2, panel_y - 3)
        lbl_w = f"w=l={self._w:.1f}m"
        fm_w = painter.fontMetrics().horizontalAdvance(lbl_w)
        painter.drawText(panel_x + panel_w_px // 2 - fm_w // 2, panel_y - 9, lbl_w)

        # b — left of column, ground to bottom of panel
        if self._b > 0.001:
            bax = panel_x - 14
            painter.drawLine(bax, support_top_y, bax, ground_y)
            painter.drawLine(bax - 3, support_top_y + 2, bax + 3, support_top_y + 2)
            painter.drawLine(bax - 3, ground_y - 2, bax + 3, ground_y - 2)
            lbl_b = f"b={self._b:.1f}m"
            mid_b = (support_top_y + ground_y) // 2
            painter.save()
            painter.translate(bax - 10, mid_b)
            painter.rotate(-90)
            fm_b = painter.fontMetrics().horizontalAdvance(lbl_b)
            painter.drawText(-fm_b // 2, 0, lbl_b)
            painter.restore()

        painter.end()


class BillboardWindDialog(QDialog):
    """
    Dialog for billboard wind load calculation.

    Top half  → input form (geometry, site, support, factors)
    Bottom half → scrollable results panel (filled after Calculate is pressed)
    Buttons   → Calculate | Generate Word Report | Close
    """

    def __init__(self, etabs=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Billboard Wind Load — Section 6 Chapter 10")
        self.setMinimumWidth(680)
        self.setMinimumHeight(820)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._output: WindLoadOutput | None = None
        self._inputs: BillboardInputs | None = None
        self._sketch: _BillboardSketch | None = None

        self._build_ui()
        self._populate_cities()
        self._load_session()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- Title banner ----------------------------------------------------
        title = QLabel("  Billboard Wind Load Calculator  ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"background-color: {_COLOR_HEADER_BG}; color: {_COLOR_HEADER_FG};"
            "font-size: 14pt; font-weight: bold; padding: 8px; border-radius: 4px;"
        )
        root.addWidget(title)

        subtitle = QLabel(
            "Iranian National Building Code – Section 6, Chapter 10 (Wind Load)"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #555; font-style: italic; font-size: 9pt;")
        root.addWidget(subtitle)

        # --- Input groups + sketch side by side ------------------------------
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        # Left column: Geometry + Site stacked
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # Geometry group
        geo_group = QGroupBox("Geometry")
        geo_group.setStyleSheet(
            f"QGroupBox {{ font-weight: bold; border: 1px solid {_COLOR_BORDER};"
            "border-radius: 4px; margin-top: 6px; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        geo_form = QFormLayout(geo_group)
        geo_form.setLabelAlignment(Qt.AlignRight)
        geo_form.setSpacing(6)

        _pos_validator = QDoubleValidator(0.001, 9999.0, 4)
        _pos_validator.setNotation(QDoubleValidator.StandardNotation)
        _nn_validator  = QDoubleValidator(0.0,   9999.0, 4)
        _nn_validator.setNotation(QDoubleValidator.StandardNotation)

        self._height_edit = QLineEdit("2.0")
        self._width_edit  = QLineEdit("4.0")
        self._bottom_edit = QLineEdit("1.0")

        self._height_edit.setValidator(_pos_validator)
        self._width_edit.setValidator(_pos_validator)
        self._bottom_edit.setValidator(_nn_validator)

        for widget in (self._height_edit, self._width_edit, self._bottom_edit):
            widget.setMaximumWidth(90)

        geo_form.addRow("Height h (m):", self._height_edit)
        geo_form.addRow("Width w (m):", self._width_edit)
        geo_form.addRow("Bottom elevation b (m):", self._bottom_edit)

        # live redraw on input change
        self._height_edit.textChanged.connect(self._update_sketch)
        self._width_edit.textChanged.connect(self._update_sketch)
        self._bottom_edit.textChanged.connect(self._update_sketch)

        # Site group
        site_group = QGroupBox("Site")
        site_group.setStyleSheet(geo_group.styleSheet())
        site_form = QFormLayout(site_group)
        site_form.setLabelAlignment(Qt.AlignRight)
        site_form.setSpacing(6)

        self._city_combo    = QComboBox()
        self._city_combo.setMinimumWidth(140)
        self._terrain_combo = QComboBox()
        self._terrain_combo.addItems(["open", "crowded"])

        site_form.addRow("City:", self._city_combo)
        site_form.addRow("Terrain type:", self._terrain_combo)

        left_col.addWidget(geo_group)
        left_col.addWidget(site_group)

        # Factors group (support type is derived from b automatically)
        factors_group = QGroupBox("Factors")
        factors_group.setStyleSheet(geo_group.styleSheet())
        factors_form = QFormLayout(factors_group)
        factors_form.setLabelAlignment(Qt.AlignRight)
        factors_form.setSpacing(6)

        _factor_validator = QDoubleValidator(0.01, 100.0, 4)
        _factor_validator.setNotation(QDoubleValidator.StandardNotation)

        self._iw_edit = QLineEdit("1.0")
        self._ct_edit = QLineEdit("1.0")
        self._iw_edit.setValidator(_factor_validator)
        self._ct_edit.setValidator(_factor_validator)
        for w in (self._iw_edit, self._ct_edit):
            w.setMaximumWidth(90)

        factors_form.addRow("Importance factor I_w:", self._iw_edit)
        factors_form.addRow("Topographic factor C_t:", self._ct_edit)

        left_col.addWidget(factors_group)
        left_col.addStretch()

        # Right column: schematic sketch
        sketch_group = QGroupBox("Schematic")
        sketch_group.setStyleSheet(geo_group.styleSheet())
        sketch_layout = QVBoxLayout(sketch_group)
        sketch_layout.setContentsMargins(4, 8, 4, 4)

        self._sketch = _BillboardSketch()
        sketch_layout.addWidget(self._sketch)

        input_row.addLayout(left_col, stretch=3)
        input_row.addWidget(sketch_group, stretch=2)
        root.addLayout(input_row)

        # --- Separator -------------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_COLOR_BORDER};")
        root.addWidget(sep)

        # --- Buttons ---------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._calc_btn = QPushButton("  ▶  Calculate")
        self._calc_btn.setStyleSheet(
            f"background-color: {_COLOR_HEADER_BG}; color: white;"
            "font-size: 11pt; font-weight: bold; padding: 6px 16px; border-radius: 4px;"
            f"border: none;"
        )
        self._calc_btn.setMinimumHeight(36)
        self._calc_btn.clicked.connect(self._on_calculate)

        self._save_btn = QPushButton("  💾  Save Inputs")
        self._save_btn.setStyleSheet(
            "background-color: #5c6bc0; color: white;"
            "font-size: 10pt; padding: 6px 12px; border-radius: 4px; border: none;"
        )
        self._save_btn.setMinimumHeight(36)
        self._save_btn.clicked.connect(self._on_save_inputs)

        self._load_btn = QPushButton("  📂  Load Inputs")
        self._load_btn.setStyleSheet(
            "background-color: #6d4c41; color: white;"
            "font-size: 10pt; padding: 6px 12px; border-radius: 4px; border: none;"
        )
        self._load_btn.setMinimumHeight(36)
        self._load_btn.clicked.connect(self._on_load_inputs)

        self._report_btn = QPushButton("  📄  Generate Word Report")
        self._report_btn.setStyleSheet(
            "background-color: #2e7d32; color: white;"
            "font-size: 10pt; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
            "border: none;"
        )
        self._report_btn.setMinimumHeight(36)
        self._report_btn.setEnabled(False)
        self._report_btn.clicked.connect(self._on_generate_report)

        self._close_btn = QPushButton("  ✕  Close")
        self._close_btn.setStyleSheet(
            "background-color: #c62828; color: white;"
            "font-size: 10pt; padding: 6px 14px; border-radius: 4px; border: none;"
        )
        self._close_btn.setMinimumHeight(36)
        self._close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self._calc_btn)
        btn_row.addWidget(self._report_btn)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._load_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._close_btn)
        root.addLayout(btn_row)

        # --- Results panel ---------------------------------------------------
        results_label = QLabel(" Results")
        results_label.setStyleSheet(
            f"background-color: {_COLOR_HEADER_BG}; color: {_COLOR_HEADER_FG};"
            "font-size: 11pt; font-weight: bold; padding: 4px 8px; border-radius: 4px;"
        )
        root.addWidget(results_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {_COLOR_BORDER}; border-radius: 4px; }}"
        )

        results_container = QWidget()
        results_container.setStyleSheet(f"background-color: {_COLOR_RESULT_BG};")
        self._results_layout = QVBoxLayout(results_container)
        self._results_layout.setContentsMargins(4, 4, 4, 4)
        self._results_layout.setSpacing(2)
        self._results_layout.setAlignment(Qt.AlignTop)

        self._placeholder = QLabel(
            "Press  ▶ Calculate  to compute wind load."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #999; font-style: italic; padding: 30px;")
        self._results_layout.addWidget(self._placeholder)

        scroll.setWidget(results_container)
        root.addWidget(scroll, stretch=1)

        # Pre-build result rows (hidden until first calculation)
        self._result_rows: dict[str, _ResultRow] = {}
        self._build_result_rows()

    def _build_result_rows(self) -> None:
        """Pre-build all result row widgets (hidden initially)."""
        sections = {
            "── Inputs ──────────────────────────────": [
                ("Height x Width", True),
                ("Bottom elevation", False),
                ("Area (A)", True),
                ("City", False),
                ("Terrain", False),
                ("Support type (auto)", False),
                ("l/h ratio  (l = w)", False),
            ],
            "── Step 1: Wind Speed & Pressure ───────": [
                ("Basic wind speed V", True),
                ("V (m/s)", False),
                ("Basic pressure q", True),
            ],
            "── Step 2: Reference Height ────────────": [
                ("Reference height Z", True),
            ],
            "── Step 3: Exposure Coefficient ────────": [
                ("Terrain type", False),
                ("Ce", True),
            ],
            "── Step 4: Gust Factor ─────────────────": [
                ("Cg method", False),
                ("Cg", True),
            ],
            "── Step 5: Force Coefficient ───────────": [
                ("l/h ratio (Cf lookup)", False),
                ("Cf", True),
            ],
            "── Step 6: Total Force ─────────────────": [
                ("F = I_w × Cf × q × Cg × Ce × A", True),
                ("F (kgf)", False),
            ],
            "── Step 7: Design Pressure ─────────────": [
                ("P_design = F / A", True),
                ("P_design (kgf/m²)", False),
            ],
        }

        for section_title, row_defs in sections.items():
            # Section header label
            hdr = QLabel(section_title)
            hdr.setStyleSheet(
                f"background-color: {_COLOR_STEP_BG}; color: #1a3a1a;"
                "font-size: 9pt; font-weight: bold; padding: 3px 8px;"
                "border-left: 3px solid #2e7d32;"
            )
            hdr.hide()
            self._result_rows[f"__hdr__{section_title}"] = hdr  # type: ignore[assignment]
            self._results_layout.addWidget(hdr)

            for label, primary in row_defs:
                row = _ResultRow(label, is_primary=primary)
                row.hide()
                self._result_rows[label] = row
                self._results_layout.addWidget(row)

        self._results_layout.addStretch()

    # ── Sketch update ─────────────────────────────────────────────────────────

    def _update_sketch(self) -> None:
        """Redraw the schematic whenever geometry inputs change."""
        if self._sketch is None:
            return
        try:
            h = float(self._height_edit.text())
            w = float(self._width_edit.text())
            b = float(self._bottom_edit.text())
            if h > 0 and w > 0 and b >= 0:
                self._sketch.set_dims(h, w, b)
        except ValueError:
            pass

    # ── City list ─────────────────────────────────────────────────────────────

    def _populate_cities(self) -> None:
        sorted_cities = sorted(WIND_SPEEDS.keys())
        self._city_combo.addItems(sorted_cities)
        # Default: Tehran
        idx = self._city_combo.findText("Tehran")
        if idx >= 0:
            self._city_combo.setCurrentIndex(idx)

    # ── Input parsing ─────────────────────────────────────────────────────────

    def _parse_float(self, widget: QLineEdit, name: str) -> float:
        text = widget.text().strip()
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"Invalid value for '{name}': '{text}' is not a number.")
        return value

    def _collect_inputs(self) -> BillboardInputs:
        height        = self._parse_float(self._height_edit, "Height h")
        width         = self._parse_float(self._width_edit,  "Width w")
        bottom_elev   = self._parse_float(self._bottom_edit, "Bottom elevation")
        iw            = self._parse_float(self._iw_edit,     "Importance factor I_w")
        ct            = self._parse_float(self._ct_edit,     "Topographic factor C_t")

        city        = self._city_combo.currentText()
        terrain_str = self._terrain_combo.currentText()
        terrain     = terrain_str.split(" ")[0]          # "open" or "crowded"
        # Support type auto-derived: b==0 → on_ground, b>0 → elevated
        support = "on_ground" if bottom_elev == 0.0 else "elevated"

        return BillboardInputs(
            height=height,
            width=width,
            bottom_elevation=bottom_elev,
            city=city,
            terrain_type=terrain,       # type: ignore[arg-type]
            support_type=support,       # type: ignore[arg-type]
            importance_factor=iw,
            topographic_factor=ct,
        )

    # ── Calculation ───────────────────────────────────────────────────────────

    def _on_calculate(self) -> None:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                inputs = self._collect_inputs()
                output = calculate_wind_load(inputs, verbose=True)

            if caught:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "\n".join(str(w.message) for w in caught),
                )

        except ValueError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))
            return

        self._inputs = inputs
        self._output = output
        self._populate_results(inputs, output)
        self._report_btn.setEnabled(True)
        self._save_session()  # auto-save after each successful calculation

    def _populate_results(
        self, inputs: BillboardInputs, out: WindLoadOutput
    ) -> None:
        """Fill all result rows with computed values and show them."""
        # Show placeholder hide
        self._placeholder.hide()

        def show(key: str, value: str) -> None:
            row = self._result_rows.get(key)
            if row is not None:
                if isinstance(row, _ResultRow):
                    row.set_value(value)
                row.show()

        # Show all section headers
        for key, widget in self._result_rows.items():
            if key.startswith("__hdr__"):
                widget.show()

        show("Height x Width",        f"{inputs.height:.3f} m x {inputs.width:.3f} m")
        show("Bottom elevation",       f"{inputs.bottom_elevation:.3f} m")
        show("Area (A)",               f"{out.A:.3f} m\u00b2")
        show("City",                   inputs.city)
        show("Terrain",                inputs.terrain_type)
        show("Support type (auto)",    f"{inputs.support_type}  (b={'0' if inputs.bottom_elevation == 0 else f'{inputs.bottom_elevation:.2f} m'} → auto)")
        show("l/h ratio  (l = w)",     f"{out.lh_ratio:.4f}  (l = {inputs.width:.3f} m)")

        show("Basic wind speed V",       f"{out.V_kmh:.2f} km/h")
        show("V (m/s)",                  f"{out.V_ms:.4f} m/s")
        show("Basic pressure q",         f"{out.q:.4f} kN/m²")

        show("Reference height Z",       f"{out.Z_ref:.4f} m")

        show("Terrain type",             inputs.terrain_type)
        show("Ce",                       f"{out.Ce:.4f}")

        show("Cg method",                out.cg_method)
        show("Cg",                       f"{out.Cg:.2f}")

        show("l/h ratio (Cf lookup)",    f"{out.lh_ratio:.4f}")
        show("Cf",                       f"{out.Cf:.4f}")

        _KN_TO_KGF = 101.972
        show("F = I_w × Cf × q × Cg × Ce × A",
             f"{out.F_total_kN:.4f} kN")
        show("F (kgf)",
             f"{out.F_total_kN * _KN_TO_KGF:.2f} kgf")

        show("P_design = F / A",         f"{out.P_design_kPa:.4f} kN/m²")
        show("P_design (kgf/m²)",        f"{out.P_design_kPa * _KN_TO_KGF:.2f} kgf/m²")

    # ── Session persist (JSON) ──────────────────────────────────────────

    def _current_state_dict(self) -> dict:
        return {
            "height":            self._height_edit.text(),
            "width":             self._width_edit.text(),
            "bottom_elevation":  self._bottom_edit.text(),
            "city":              self._city_combo.currentText(),
            "terrain_type":      self._terrain_combo.currentText(),
            "importance_factor": self._iw_edit.text(),
            "topographic_factor":self._ct_edit.text(),
        }

    def _apply_state_dict(self, d: dict) -> None:
        if "height"             in d: self._height_edit.setText(str(d["height"]))
        if "width"              in d: self._width_edit.setText(str(d["width"]))
        if "bottom_elevation"   in d: self._bottom_edit.setText(str(d["bottom_elevation"]))
        if "importance_factor"  in d: self._iw_edit.setText(str(d["importance_factor"]))
        if "topographic_factor" in d: self._ct_edit.setText(str(d["topographic_factor"]))
        if "city" in d:
            idx = self._city_combo.findText(d["city"])
            if idx >= 0:
                self._city_combo.setCurrentIndex(idx)
        if "terrain_type" in d:
            idx = self._terrain_combo.findText(d["terrain_type"])
            if idx >= 0:
                self._terrain_combo.setCurrentIndex(idx)

    def _save_session(self, path: Path | None = None) -> None:
        target = path or _SESSION_FILE
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(self._current_state_dict(), f, indent=2)
        except Exception:
            pass  # silently ignore persistence errors

    def _load_session(self, path: Path | None = None) -> None:
        target = path or _SESSION_FILE
        if not target.exists():
            return
        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
            self._apply_state_dict(data)
        except Exception:
            pass

    def _on_save_inputs(self) -> None:
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Inputs", str(Path.home() / "billboard_wind_inputs.json"),
            "JSON Files (*.json)"
        )
        if save_path:
            self._save_session(Path(save_path))
            QMessageBox.information(self, "Saved", f"Inputs saved to:\n{save_path}")

    def _on_load_inputs(self) -> None:
        load_path, _ = QFileDialog.getOpenFileName(
            self, "Load Inputs", str(Path.home()),
            "JSON Files (*.json)"
        )
        if load_path:
            self._load_session(Path(load_path))

    # ── Report generation ─────────────────────────────────────────────────────

    def _on_generate_report(self) -> None:
        if self._output is None or self._inputs is None:
            return

        default_name = (
            f"wind_billboard_{self._inputs.city}_{self._inputs.height:.0f}x"
            f"{self._inputs.width:.0f}.docx"
        )
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Word Report",
            str(Path.home() / default_name),
            "Word Documents (*.docx)",
        )
        if not save_path:
            return

        try:
            from civiltools.wind.report import generate_word_report

            # Render the schematic sketch to a temp PNG
            sketch_img_path: str | None = None
            if self._sketch is not None:
                try:
                    pix = self._sketch.grab()
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp.close()
                    pix.save(tmp.name, "PNG")
                    sketch_img_path = tmp.name
                except Exception:
                    sketch_img_path = None

            generate_word_report(
                self._inputs, self._output,
                save_path=save_path,
                sketch_image_path=sketch_img_path,
            )

            # Clean up temp sketch file
            if sketch_img_path:
                try:
                    os.unlink(sketch_img_path)
                except Exception:
                    pass

            answer = QMessageBox.question(
                self,
                "Report Saved",
                f"Word report saved to:\n{save_path}\n\nOpen the file now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                os.startfile(save_path)  # Windows
        except Exception as exc:
            QMessageBox.critical(self, "Report Error", str(exc))


# ── Standalone entry point ────────────────────────────────────────────────────

def show_billboard_wind_dialog(parent=None) -> None:
    """
    Open the BillboardWindDialog.  Creates a QApplication if none exists.
    """
    app = QApplication.instance()
    created = app is None
    if created:
        import sys
        app = QApplication(sys.argv)

    dlg = BillboardWindDialog(parent=parent)
    dlg.exec()

    if created:
        app.quit()


if __name__ == "__main__":
    show_billboard_wind_dialog()
