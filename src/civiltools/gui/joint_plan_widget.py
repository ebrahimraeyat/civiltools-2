"""
joint_plan_widget.py
====================
QPainter-based plan view of a beam-column joint.

Renders:
- Column cross-section (gold rectangle) at the center.
- Each connected beam as a coloured rectangle extending outward from the
  column face, following the beam's plan-view angle.
- A direction line (blue = Major, green = Minor) through the joint
  derived from the actual angles of the ± checked beams.

Accepts a ``geometry`` dict (JSON-decoded from the ``__geometry__`` column):
    {
        "col_b":    float,          # column width  (mm)
        "col_h":    float,          # column depth  (mm)
        "direction": "Major" | "Minor",
        "beams": [
            {
                "name":      str,
                "angle_deg": float,   # 0=right, 90=up-in-plan, 180=left, 270=down
                "width":     float,   # beam width in plan view (mm)
                "height":    float,   # beam total depth (mm) — visual only
                "side":      "plus" | "minus" | "transverse",
            },
            ...
        ]
    }
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF, QRectF, QSizeF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QFontMetricsF, QPolygonF,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


# ── Colour palette (matches ETABS MATE screenshots) ────────────────
_C_BG          = QColor(230, 237, 248)   # background
_C_COLUMN      = QColor(255, 215, 0)     # gold — column fill
_C_COL_BORDER  = QColor(160, 130, 0)     # dark gold — column border
_C_BEAM_PLUS   = QColor(215, 95, 85)     # salmon-red — checked beams (+)
_C_BEAM_MINUS  = QColor(215, 95, 85)     # same for − side beams
_C_TRANSVERSE  = QColor(190, 195, 215)   # blue-gray — transverse beams
_C_DIR_MAJOR   = QColor(30, 100, 215)    # blue  — Direction 2 (Major)
_C_DIR_MINOR   = QColor(30, 175, 65)     # green — Direction 1 (Minor)
_C_LABEL       = QColor(30, 30, 50)
_C_RATIO_OK    = QColor(0, 120, 0)
_C_RATIO_NG    = QColor(180, 0, 0)
_C_DISABLED    = QColor(150, 155, 165)

_BEAM_SIDE_COLORS: dict[str, QColor] = {
    "plus":       _C_BEAM_PLUS,
    "minus":      _C_BEAM_MINUS,
    "transverse": _C_TRANSVERSE,
}


class JointPlanWidget(QWidget):
    """
    Schematic plan-view drawing of a beam-column joint.

    Call :meth:`set_geometry` with the decoded ``__geometry__`` dict
    (and optionally the computed ratio and ETABS ratio) to update the view.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._geom: dict | None = None
        self._ratio: float | None = None
        self._ratio_etabs: str | float | None = None

        self.setMinimumSize(220, 220)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    # ── Public API ─────────────────────────────────────────────────

    def set_geometry(
        self,
        geom: dict | None,
        ratio: float | None = None,
        ratio_etabs: str | float | None = None,
    ) -> None:
        """Update the displayed joint geometry and trigger a repaint."""
        self._geom   = geom
        self._ratio  = ratio
        self._ratio_etabs = ratio_etabs
        self.update()

    def clear(self) -> None:
        self._geom = None
        self._ratio = None
        self._ratio_etabs = None
        self.update()

    # ── Painting ───────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        p.fillRect(self.rect(), _C_BG)

        if not self._geom:
            p.setPen(QPen(_C_DISABLED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Select a row to view joint geometry")
            return

        cx, cy = w / 2, h / 2

        # ── Scale ────────────────────────────────────────────────────
        col_b  = float(self._geom.get("col_b", 500))
        col_h  = float(self._geom.get("col_h", 500))
        col_local2_deg = float(self._geom.get("col_local2_angle_deg", 0.0))
        beams  = self._geom.get("beams", [])

        col_size = max(col_b, col_h)
        max_bw   = max((float(b["width"]) for b in beams), default=300.0)
        beam_ext = max(max_bw * 3.5, col_size * 2.2)  # mm from column face

        # Fit column + beams within 82% of the smaller widget dimension
        view_r = min(w, h) * 0.41
        scale  = view_r / (col_size / 2 + beam_ext)    # px/mm

        col_px_b = col_b * scale
        col_px_h = col_h * scale

        # ── Beams (drawn behind column) ───────────────────────────────
        for beam in beams:
            self._draw_beam(p, cx, cy, scale, col_b, col_h, col_local2_deg,
                            beam, beam_ext)

        # ── Column — rotated to match local axes ─────────────────────
        col_local2_rad = math.radians(col_local2_deg)
        # local-2 screen unit vector  (screen Y is down, so negate sin)
        u2x =  math.cos(col_local2_rad);  u2y = -math.sin(col_local2_rad)
        # local-3 screen unit vector  (perpendicular CCW)
        u3x = -u2y;                        u3y =  u2x

        half2 = col_px_b / 2   # half-width in local-2 direction
        half3 = col_px_h / 2   # half-width in local-3 direction

        # Four corners of the (possibly rotated) column rectangle
        col_corners = QPolygonF([
            QPointF(cx + u2x * half2 + u3x * half3,
                    cy + u2y * half2 + u3y * half3),
            QPointF(cx - u2x * half2 + u3x * half3,
                    cy - u2y * half2 + u3y * half3),
            QPointF(cx - u2x * half2 - u3x * half3,
                    cy - u2y * half2 - u3y * half3),
            QPointF(cx + u2x * half2 - u3x * half3,
                    cy + u2y * half2 - u3y * half3),
        ])
        p.setBrush(QBrush(_C_COLUMN))
        p.setPen(QPen(_C_COL_BORDER, 2.5))
        p.drawPolygon(col_corners)

        # ── Direction line ────────────────────────────────────────────
        direction = self._geom.get("direction", "Major")

        # Major checks beams along local-2 axis → direction line along local-2
        # Minor checks beams along local-3 axis → direction line along local-3 (local-2 + 90°)
        if direction == "Major":
            line_angle_deg = col_local2_deg
        else:
            line_angle_deg = col_local2_deg + 90.0

        dir_color = _C_DIR_MAJOR if direction == "Major" else _C_DIR_MINOR
        line_angle_rad = math.radians(line_angle_deg)
        line_len = min(w, h) * 0.48
        lx = math.cos(line_angle_rad) * line_len
        ly = -math.sin(line_angle_rad) * line_len   # negate Y (screen Y is down)

        pen_dir = QPen(dir_color, 3.5, Qt.PenStyle.SolidLine)
        pen_dir.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_dir)
        p.drawLine(QPointF(cx - lx, cy - ly), QPointF(cx + lx, cy + ly))

        # ── Ratio overlay ─────────────────────────────────────────────
        self._draw_ratio_overlay(p, w, h, direction, dir_color)

        # ── Border ───────────────────────────────────────────────────
        p.setPen(QPen(_C_COL_BORDER.lighter(150), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(1, 1, w - 2, h - 2)

        p.end()

    # ── Drawing helpers ────────────────────────────────────────────

    def _draw_beam(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        scale: float,
        col_b: float,
        col_h: float,
        col_local2_deg: float,
        beam: dict,
        beam_ext_mm: float,
    ):
        angle_deg = float(beam["angle_deg"])
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Screen unit vector (invert Y so north = screen-up)
        ux, uy = cos_a, -sin_a

        # Perpendicular screen vector (rotated 90° CCW)
        px_vec, py_vec = -uy, ux

        # Distance from column centre to column face in the beam's direction.
        # For a rectangle rotated by col_local2_deg, with half-widths:
        #   a = col_b/2 (along local-2),  b = col_h/2 (along local-3)
        # the boundary distance in direction phi is:
        #   min( a / |cos(phi - theta)|,  b / |sin(phi - theta)| )
        theta = math.radians(col_local2_deg)
        dphi  = angle_rad - theta          # angle relative to local-2
        cos_dp = abs(math.cos(dphi))
        sin_dp = abs(math.sin(dphi))
        half2_mm = col_b / 2
        half3_mm = col_h / 2
        # avoid division by zero with a small epsilon
        eps = 1e-9
        dist_a = half2_mm / (cos_dp + eps)
        dist_b = half3_mm / (sin_dp + eps)
        col_half_mm = min(dist_a, dist_b)

        near_px = col_half_mm * scale
        far_px  = near_px + beam_ext_mm * scale

        bw_px = float(beam["width"]) * scale    # beam width in pixels
        half_bw = bw_px / 2

        # Four corners of beam rectangle
        def pt(along: float, perp: float) -> QPointF:
            return QPointF(
                cx + ux * along + px_vec * perp,
                cy + uy * along + py_vec * perp,
            )

        corners = [
            pt(near_px, -half_bw),
            pt(far_px,  -half_bw),
            pt(far_px,   half_bw),
            pt(near_px,  half_bw),
        ]

        color = _BEAM_SIDE_COLORS.get(beam.get("side", "plus"), _C_BEAM_PLUS)

        p.save()
        p.setBrush(QBrush(color))
        p.setPen(QPen(color.darker(140), 1.0))
        from PySide6.QtGui import QPolygonF
        p.drawPolygon(QPolygonF(corners))
        p.restore()

    def _draw_ratio_overlay(
        self,
        p: QPainter,
        w: float,
        h: float,
        direction: str,
        dir_color: QColor,
    ):
        """Draw the ratio text in the bottom-left corner."""
        lines: list[tuple[str, QColor]] = []

        dir_label = "Direction 2 — Major" if direction == "Major" else "Direction 1 — Minor"
        lines.append((dir_label, dir_color))

        if self._ratio is not None:
            ratio    = self._ratio
            ok       = ratio <= 1.0
            r_color  = _C_RATIO_OK if ok else _C_RATIO_NG
            lines.append((f"Ratio (calc.) = {ratio:.3f}", r_color))

        if self._ratio_etabs is not None and str(self._ratio_etabs) != "N/A":
            try:
                er = float(self._ratio_etabs)
                er_color = _C_RATIO_OK if er <= 1.0 else _C_RATIO_NG
                lines.append((f"Ratio (ETABS) = {er:.3f}", er_color))
            except (ValueError, TypeError):
                pass

        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetricsF(font)
        line_h = fm.height() + 2
        y0 = h - 8 - line_h * len(lines)

        for i, (txt, color) in enumerate(lines):
            p.setPen(QPen(color))
            p.drawText(QPointF(6, y0 + i * line_h + fm.ascent()), txt)
