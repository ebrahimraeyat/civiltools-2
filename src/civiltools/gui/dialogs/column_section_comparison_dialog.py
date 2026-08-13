"""Side-by-side section comparison used by Columns Control."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from etabs_api.python_functions import rectangle_vertexes, rebar_centers


@dataclass(frozen=True)
class _SectionGeometry:
    name: str
    width: float
    height: float
    cover: float
    bars_width: int
    bars_height: int
    corner_diameter: float
    longitudinal_diameter: float


class ColumnSectionComparisonDialog(QDialog):
    """Show the current section and the section immediately below it."""

    def __init__(self, etabs: Any, above_section: str, below_section: str, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._above_section = above_section
        self._below_section = below_section

        self.setWindowTitle("Column Section Comparison")
        self.resize(620, 820)

        layout = QVBoxLayout(self)
        self._figure = Figure(figsize=(6, 8), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        layout.addWidget(self._canvas)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._draw_sections()

    def _draw_sections(self) -> None:
        self._etabs.set_current_unit("kgf", "cm")
        above = self._read_section(self._above_section)
        below = self._read_section(self._below_section)

        above_axis = self._figure.add_subplot(211)
        below_axis = self._figure.add_subplot(212)
        self._draw_section(above_axis, above, "Above")
        self._draw_section(below_axis, below, "Below")
        self._figure.tight_layout()
        self._canvas.draw()

    def _read_section(self, section_name: str) -> _SectionGeometry:
        _, _, height, width, *_ = self._etabs.SapModel.PropFrame.GetRectangle(section_name)
        prop_frame = getattr(self._etabs.SapModel, "propframe", self._etabs.SapModel.PropFrame)
        rebar = prop_frame.GetRebarColumn_1(section_name)
        return _SectionGeometry(
            name=section_name,
            width=float(width),
            height=float(height),
            cover=float(rebar[4]),
            bars_width=int(rebar[6]),
            bars_height=int(rebar[7]),
            longitudinal_diameter=math.sqrt(float(rebar[15]) * 4 / math.pi),
            corner_diameter=math.sqrt(float(rebar[16]) * 4 / math.pi),
        )

    @staticmethod
    def _draw_section(axis, section: _SectionGeometry, position: str) -> None:
        outer = rectangle_vertexes(section.width, section.height)
        inner = rectangle_vertexes(
            section.width - 2 * section.cover - 1,
            section.height - 2 * section.cover - 1,
        )
        axis.plot(*zip(*outer), color="black", linewidth=2)
        axis.plot(*zip(*inner), color="black", linewidth=1)

        corners, longitudinals = rebar_centers(
            section.width,
            section.height,
            section.bars_width,
            section.bars_height,
            section.corner_diameter,
            section.longitudinal_diameter,
            1,
            section.cover,
        )
        for x, y in corners:
            axis.plot(x, y, "ro", markersize=section.corner_diameter * 5)
        for x, y in longitudinals:
            axis.plot(x, y, "bo", markersize=section.longitudinal_diameter * 5)

        margin = 1
        axis.set_xlim(-margin - section.width / 2, section.width / 2 + margin)
        axis.set_ylim(-margin - section.height / 2, section.height / 2 + margin)
        axis.set_aspect("equal")
        axis.set_axis_off()
        axis.set_title(f"{position}: {section.name}")
