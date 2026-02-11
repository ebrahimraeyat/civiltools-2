"""
Column detection — filter ``DxfRect`` entries from a ``DxfContent`` and
build *Grid* axis data from their centre coordinates.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass, field
from typing import Sequence

from civiltools.dxf.dxf_reader import DxfContent, DxfRect, Vec2


# ═══════════════════════════════════════════════════════════════════════════
# Column detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_columns(
    content: DxfContent,
    *,
    source_filter: str | None = None,
    name_filter: str | None = None,
) -> list[DxfRect]:
    """Return column rectangles matching the given filter.

    Parameters
    ----------
    source_filter
        ``"block"``, ``"hatch"``, ``"polyline"`` — or *None* for all.
    name_filter
        Block name or hatch pattern name — or *None* for all.
    """
    columns: list[DxfRect] = []
    for r in content.rects:
        if source_filter and r.source != source_filter:
            continue
        if name_filter and r.source_name != name_filter:
            continue
        columns.append(r)
    return columns


# ═══════════════════════════════════════════════════════════════════════════
# Grid axis builder
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GridLine:
    """One axis line with a label and a coordinate (in mm)."""
    label: str
    coordinate: float


@dataclass
class GridAxes:
    """X and Y grid axes derived from column centres."""
    x_lines: list[GridLine] = field(default_factory=list)
    y_lines: list[GridLine] = field(default_factory=list)

    def x_coords(self) -> list[float]:
        return [g.coordinate for g in self.x_lines]

    def y_coords(self) -> list[float]:
        return [g.coordinate for g in self.y_lines]


def build_axes(
    columns: Sequence[DxfRect],
    *,
    x_style: str = "A,B,C",
    snap_tolerance: float = 10.0,
) -> GridAxes:
    """Cluster column centres into unique X and Y coordinates and label them.

    Parameters
    ----------
    columns
        Column rectangles (from ``detect_columns``).
    x_style
        ``"A,B,C"`` or ``"1,2,3"`` — labelling for the X direction.
        The other direction gets the complementary style.
    snap_tolerance
        Columns whose coordinate differs by less than this (mm) are
        considered on the same grid line.
    """
    raw_x: list[float] = []
    raw_y: list[float] = []
    for c in columns:
        raw_x.append(c.center.x)
        raw_y.append(c.center.y)

    unique_x = _cluster(raw_x, snap_tolerance)
    unique_y = _cluster(raw_y, snap_tolerance)

    if x_style == "A,B,C":
        x_labels = _alpha_labels(len(unique_x))
        y_labels = _numeric_labels(len(unique_y))
    else:
        x_labels = _numeric_labels(len(unique_x))
        y_labels = _alpha_labels(len(unique_y))

    axes = GridAxes()
    for coord, label in zip(unique_x, x_labels):
        axes.x_lines.append(GridLine(label=label, coordinate=coord))
    for coord, label in zip(unique_y, y_labels):
        axes.y_lines.append(GridLine(label=label, coordinate=coord))

    return axes


def move_origin_to_intersection(
    axes: GridAxes,
    columns: list[DxfRect],
    content: DxfContent,
    *,
    x_index: int = 0,
    y_index: int = 0,
) -> tuple[float, float]:
    """Translate everything so that *x_index* / *y_index* grid intersection
    sits at (0, 0).

    Returns the (dx, dy) applied.
    """
    if not axes.x_lines or not axes.y_lines:
        return (0.0, 0.0)
    dx = -axes.x_lines[x_index].coordinate
    dy = -axes.y_lines[y_index].coordinate

    # Shift axes
    for g in axes.x_lines:
        g.coordinate += dx
    for g in axes.y_lines:
        g.coordinate += dy

    # Shift column centres
    for c in columns:
        c.center = Vec2(c.center.x + dx, c.center.y + dy)

    # Shift raw geometry
    for line in content.lines:
        line.start = Vec2(line.start.x + dx, line.start.y + dy)
        line.end = Vec2(line.end.x + dx, line.end.y + dy)
    for circ in content.circles:
        circ.center = Vec2(circ.center.x + dx, circ.center.y + dy)
    for r in content.rects:
        r.center = Vec2(r.center.x + dx, r.center.y + dy)

    return (dx, dy)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _cluster(values: list[float], tol: float) -> list[float]:
    """Sort *values* and merge neighbours within *tol* → unique sorted list."""
    if not values:
        return []
    sv = sorted(values)
    groups: list[list[float]] = [[sv[0]]]
    for v in sv[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _alpha_labels(n: int) -> list[str]:
    """A, B, C, … AA, AB, …"""
    labels: list[str] = []
    for i in range(n):
        s = ""
        idx = i
        while True:
            s = string.ascii_uppercase[idx % 26] + s
            idx = idx // 26 - 1
            if idx < 0:
                break
        labels.append(s)
    return labels


def _numeric_labels(n: int) -> list[str]:
    """1, 2, 3, …"""
    return [str(i + 1) for i in range(n)]
