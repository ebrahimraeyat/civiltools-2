"""
DXF file reader — uses *ezdxf* to extract lines, blocks, hatches, circles,
and closed polylines from a DXF file.

Returns lightweight dataclasses that the rest of the workflow operates on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import ezdxf


# ═══════════════════════════════════════════════════════════════════════════
# Data containers
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Vec2:
    """Simple 2-D point."""
    x: float
    y: float


@dataclass
class DxfLine:
    """A line or polyline segment."""
    start: Vec2
    end: Vec2
    layer: str = ""


@dataclass
class DxfCircle:
    """A circle entity."""
    center: Vec2
    radius: float
    layer: str = ""


@dataclass
class DxfRect:
    """Axis-aligned bounding rectangle of a column-like entity.

    *rotation* is in **degrees** CCW from X-axis.
    """
    center: Vec2
    width: float
    height: float
    rotation: float = 0.0
    layer: str = ""
    source: str = ""          # "block" | "hatch" | "polyline"
    source_name: str = ""     # block name or hatch pattern


@dataclass
class DxfContent:
    """Everything extracted from a DXF file (or AutoCAD selection)."""
    lines: list[DxfLine] = field(default_factory=list)
    circles: list[DxfCircle] = field(default_factory=list)
    rects: list[DxfRect] = field(default_factory=list)
    block_names: list[str] = field(default_factory=list)
    hatch_patterns: list[str] = field(default_factory=list)
    scale: float = 1.0        # unit multiplier → mm


# ═══════════════════════════════════════════════════════════════════════════
# Reader
# ═══════════════════════════════════════════════════════════════════════════

_UNIT_SCALES: dict[str, float] = {
    "m": 1000.0,
    "cm": 10.0,
    "mm": 1.0,
}


def read_dxf(filepath: str | Path, unit: str = "m") -> DxfContent:
    """Parse a DXF file and return all relevant entities.

    Parameters
    ----------
    filepath : path to ``.dxf`` file
    unit : length unit of the DXF drawing (``"m"``, ``"cm"``, ``"mm"``).
        All coordinates are scaled to millimetres internally.
    """
    scale = _UNIT_SCALES.get(unit.lower(), 1000.0)
    doc = ezdxf.readfile(str(filepath))
    msp = doc.modelspace()

    content = DxfContent(scale=scale)

    # ── Collect block names ─────────────────────────────────────────
    block_names: set[str] = set()
    for insert in msp.query("INSERT"):
        block_names.add(insert.dxf.name)
    content.block_names = sorted(block_names)

    # ── Collect hatch pattern names ─────────────────────────────────
    hatch_names: set[str] = set()
    for hatch in msp.query("HATCH"):
        hatch_names.add(str(hatch.dxf.pattern_name))
    content.hatch_patterns = sorted(hatch_names)

    # ── Lines ───────────────────────────────────────────────────────
    for line in msp.query("LINE"):
        s = line.dxf.start
        e = line.dxf.end
        content.lines.append(DxfLine(
            start=Vec2(s.x * scale, s.y * scale),
            end=Vec2(e.x * scale, e.y * scale),
            layer=line.dxf.layer,
        ))

    # ── Polylines (LWPOLYLINE) ──────────────────────────────────────
    for lwp in msp.query("LWPOLYLINE"):
        pts = lwp.get_points(format="xy")
        if len(pts) < 2:
            continue
        # Draw segments
        for a, b in zip(pts[:-1], pts[1:]):
            content.lines.append(DxfLine(
                start=Vec2(a[0] * scale, a[1] * scale),
                end=Vec2(b[0] * scale, b[1] * scale),
                layer=lwp.dxf.layer,
            ))
        # If closed polyline → also close it
        if lwp.closed and len(pts) >= 3:
            content.lines.append(DxfLine(
                start=Vec2(pts[-1][0] * scale, pts[-1][1] * scale),
                end=Vec2(pts[0][0] * scale, pts[0][1] * scale),
                layer=lwp.dxf.layer,
            ))
        # Detect rectangle (closed, 4 vertices) → column candidate
        if lwp.closed and len(pts) == 4:
            rect = _rect_from_points(
                [(p[0] * scale, p[1] * scale) for p in pts],
                layer=lwp.dxf.layer,
                source="polyline",
            )
            if rect is not None:
                content.rects.append(rect)

    # ── Circles ─────────────────────────────────────────────────────
    for circle in msp.query("CIRCLE"):
        c = circle.dxf.center
        content.circles.append(DxfCircle(
            center=Vec2(c.x * scale, c.y * scale),
            radius=circle.dxf.radius * scale,
            layer=circle.dxf.layer,
        ))

    # ── Block inserts ───────────────────────────────────────────────
    for insert in msp.query("INSERT"):
        name = insert.dxf.name
        block = doc.blocks.get(name)
        if block is None:
            continue
        rect = _rect_from_block_insert(insert, block, scale)
        if rect is not None:
            content.rects.append(rect)

    # ── Hatches ─────────────────────────────────────────────────────
    for hatch in msp.query("HATCH"):
        rect = _rect_from_hatch(hatch, scale)
        if rect is not None:
            content.rects.append(rect)

    return content


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _rect_from_points(
    pts: Sequence[tuple[float, float]],
    *,
    layer: str = "",
    source: str = "polyline",
    source_name: str = "",
) -> DxfRect | None:
    """Try to interpret four scaled (mm) points as an axis-aligned rectangle."""
    if len(pts) != 4:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = sum(xs) / 4
    cy = sum(ys) / 4

    # Compute width/height from bounding box
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    if w < 1 or h < 1:
        return None

    # Estimate rotation — angle of first edge
    dx = pts[1][0] - pts[0][0]
    dy = pts[1][1] - pts[0][1]
    angle = math.degrees(math.atan2(dy, dx))

    return DxfRect(
        center=Vec2(cx, cy), width=w, height=h,
        rotation=angle, layer=layer,
        source=source, source_name=source_name,
    )


def _rect_from_block_insert(insert, block, scale: float) -> DxfRect | None:
    """Compute bounding rect from an INSERT entity."""
    try:
        # Gather all vertices from sub-entities
        xs: list[float] = []
        ys: list[float] = []
        ins_pt = insert.dxf.insert
        rot = insert.dxf.get("rotation", 0.0)
        sx = insert.dxf.get("xscale", 1.0)
        sy = insert.dxf.get("yscale", 1.0)
        rad = math.radians(rot)

        for entity in block:
            pts: list[tuple[float, float]] = []
            if entity.dxftype() == "LINE":
                pts = [(entity.dxf.start.x, entity.dxf.start.y),
                       (entity.dxf.end.x, entity.dxf.end.y)]
            elif entity.dxftype() == "LWPOLYLINE":
                pts = entity.get_points(format="xy")
            elif entity.dxftype() == "CIRCLE":
                c = entity.dxf.center
                r = entity.dxf.radius
                pts = [(c.x - r, c.y - r), (c.x + r, c.y + r)]
            for px, py in pts:
                # Apply block transform: scale → rotate → translate
                tx = px * sx
                ty = py * sy
                rx = tx * math.cos(rad) - ty * math.sin(rad) + ins_pt.x
                ry = tx * math.sin(rad) + ty * math.cos(rad) + ins_pt.y
                xs.append(rx * scale)
                ys.append(ry * scale)

        if not xs:
            return None
        cx = (max(xs) + min(xs)) / 2
        cy = (max(ys) + min(ys)) / 2
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w < 1 or h < 1:
            return None
        return DxfRect(
            center=Vec2(cx, cy), width=w, height=h,
            rotation=rot, layer=insert.dxf.layer,
            source="block", source_name=insert.dxf.name,
        )
    except Exception:
        return None


def _rect_from_hatch(hatch, scale: float) -> DxfRect | None:
    """Compute bounding rect from a HATCH entity's boundary paths."""
    try:
        xs: list[float] = []
        ys: list[float] = []
        for path in hatch.paths:
            if hasattr(path, "vertices"):              # PolylinePath
                for v in path.vertices:
                    xs.append(v[0] * scale)
                    ys.append(v[1] * scale)
            elif hasattr(path, "edges"):               # EdgePath
                for edge in path.edges:
                    if hasattr(edge, "start"):
                        xs.append(edge.start.x * scale)
                        ys.append(edge.start.y * scale)
                    if hasattr(edge, "end"):
                        xs.append(edge.end.x * scale)
                        ys.append(edge.end.y * scale)

        if len(xs) < 3:
            return None
        cx = (max(xs) + min(xs)) / 2
        cy = (max(ys) + min(ys)) / 2
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w < 1 or h < 1:
            return None
        return DxfRect(
            center=Vec2(cx, cy), width=w, height=h,
            rotation=0.0, layer=hatch.dxf.layer,
            source="hatch",
            source_name=str(hatch.dxf.pattern_name),
        )
    except Exception:
        return None
