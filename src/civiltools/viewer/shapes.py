"""
OCC shape builders for structural elements.

Creates OpenCASCADE TopoDS_Shape objects for beams, columns, walls
(with boolean window cuts), floor slabs, and grid axis lines.

All units in **meters**.  No GUI dependencies — pure geometry.
"""

from __future__ import annotations

from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB


# ═══════════════════════════════════════════════════════════════════════════
# Color palette (matches civilTools / FreeCAD scheme)
# ═══════════════════════════════════════════════════════════════════════════

COLORS: dict[str, Quantity_Color] = {
    "beam":    Quantity_Color(0.85, 0.75, 0.00, Quantity_TOC_RGB),   # yellow
    "column":  Quantity_Color(0.00, 0.65, 0.00, Quantity_TOC_RGB),   # green
    "wall":    Quantity_Color(0.80, 0.22, 0.22, Quantity_TOC_RGB),   # red
    "floor":   Quantity_Color(0.65, 0.65, 0.65, Quantity_TOC_RGB),   # gray
    "opening": Quantity_Color(1.00, 0.55, 0.75, Quantity_TOC_RGB),   # pink
    "axis":    Quantity_Color(0.15, 0.15, 0.75, Quantity_TOC_RGB),   # blue
    "brace":   Quantity_Color(0.60, 0.30, 0.00, Quantity_TOC_RGB),   # brown
}

TRANSPARENCY: dict[str, float] = {
    "beam":   0.0,
    "column": 0.0,
    "wall":   0.25,
    "floor":  0.50,
    "brace":  0.0,
}


# ═══════════════════════════════════════════════════════════════════════════
# Shape builders
# ═══════════════════════════════════════════════════════════════════════════

def make_column(
    x: float, y: float, z_base: float, height: float,
    bx: float = 0.50, by: float = 0.50,
) -> TopoDS_Shape:
    """Rectangular column centered at *(x, y)*, extruded from *z_base*."""
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x - bx / 2, y - by / 2, z_base),
        bx, by, height,
    ).Shape()


def make_circular_column(
    x: float, y: float, z_base: float, height: float,
    radius: float = 0.25,
) -> TopoDS_Shape:
    """Circular column centered at *(x, y)*."""
    ax = gp_Ax2(gp_Pnt(x, y, z_base), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(ax, radius, height).Shape()


def make_beam(
    x1: float, y1: float, x2: float, y2: float, z_top: float,
    width: float = 0.30, depth: float = 0.50,
) -> TopoDS_Shape:
    """Beam between two plan points — top face at *z_top*.

    Handles X-aligned, Y-aligned, and diagonal beams.
    """
    dx, dy = abs(x2 - x1), abs(y2 - y1)

    if dy < 0.001:  # X-aligned
        return BRepPrimAPI_MakeBox(
            gp_Pnt(min(x1, x2), y1 - width / 2, z_top - depth),
            max(dx, 0.01), width, depth,
        ).Shape()

    if dx < 0.001:  # Y-aligned
        return BRepPrimAPI_MakeBox(
            gp_Pnt(x1 - width / 2, min(y1, y2), z_top - depth),
            width, max(dy, 0.01), depth,
        ).Shape()

    # Diagonal — approximate with bounding box (proper would use sweep)
    return BRepPrimAPI_MakeBox(
        gp_Pnt(min(x1, x2), min(y1, y2), z_top - depth),
        max(dx, width), max(dy, width), depth,
    ).Shape()


def make_floor_slab(
    x1: float, y1: float, x2: float, y2: float,
    z_top: float, thickness: float = 0.25,
) -> TopoDS_Shape:
    """Rectangular floor slab — top at *z_top*."""
    return BRepPrimAPI_MakeBox(
        gp_Pnt(min(x1, x2), min(y1, y2), z_top - thickness),
        abs(x2 - x1), abs(y2 - y1), thickness,
    ).Shape()


def make_wall(
    x1: float, y1: float, x2: float, y2: float,
    z_base: float, height: float,
    thickness: float = 0.20,
    openings: list[dict[str, float]] | None = None,
) -> TopoDS_Shape:
    """Axis-aligned wall with optional rectangular openings.

    Each opening dict: ``{'offset': m, 'z_offset': m, 'width': m, 'height': m}``
    """
    dx, dy = x2 - x1, y2 - y1

    if abs(dy) < 0.001:                                   # wall along X
        wall_len = abs(dx)
        x_min = min(x1, x2)
        wall = BRepPrimAPI_MakeBox(
            gp_Pnt(x_min, y1 - thickness / 2, z_base),
            wall_len, thickness, height,
        ).Shape()
        if openings:
            for op in openings:
                cut = BRepPrimAPI_MakeBox(
                    gp_Pnt(x_min + op["offset"],
                            y1 - thickness / 2 - 0.01,
                            z_base + op["z_offset"]),
                    op["width"], thickness + 0.02, op["height"],
                ).Shape()
                wall = BRepAlgoAPI_Cut(wall, cut).Shape()
        return wall

    if abs(dx) < 0.001:                                   # wall along Y
        wall_len = abs(dy)
        y_min = min(y1, y2)
        wall = BRepPrimAPI_MakeBox(
            gp_Pnt(x1 - thickness / 2, y_min, z_base),
            thickness, wall_len, height,
        ).Shape()
        if openings:
            for op in openings:
                cut = BRepPrimAPI_MakeBox(
                    gp_Pnt(x1 - thickness / 2 - 0.01,
                            y_min + op["offset"],
                            z_base + op["z_offset"]),
                    thickness + 0.02, op["width"], op["height"],
                ).Shape()
                wall = BRepAlgoAPI_Cut(wall, cut).Shape()
        return wall

    # Fallback: non-axis-aligned — simple box
    return BRepPrimAPI_MakeBox(
        gp_Pnt(min(x1, x2), min(y1, y2), z_base),
        max(abs(dx), thickness), max(abs(dy), thickness), height,
    ).Shape()


def make_axis_line(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
) -> TopoDS_Shape:
    """Single edge between two 3D points (for grid axes)."""
    return BRepBuilderAPI_MakeEdge(gp_Pnt(*p1), gp_Pnt(*p2)).Edge()
