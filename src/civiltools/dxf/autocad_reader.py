"""
AutoCAD COM reader — read selected entities from a running AutoCAD instance.

Uses *comtypes* to connect to ``AutoCAD.Application`` via COM and iterate
over the current selection set.  Produces the same ``DxfContent`` as
``dxf_reader`` so the rest of the pipeline is source-agnostic.

Every public function does exactly one thing.  Internal helpers are
prefixed with ``_`` and handle a single entity type each.
"""

from __future__ import annotations

import math
from typing import Any

from civiltools.dxf.dxf_reader import DxfContent, DxfLine, DxfCircle, DxfRect, Vec2


_UNIT_SCALES: dict[str, float] = {"m": 1000.0, "cm": 10.0, "mm": 1.0}


# ═══════════════════════════════════════════════════════════════════════════
# Connection
# ═══════════════════════════════════════════════════════════════════════════

def get_autocad_app():
    """Return a live AutoCAD COM Application object, or *None*."""
    try:
        import comtypes.client
        return comtypes.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        return None


def is_autocad_running() -> bool:
    """Return *True* if an AutoCAD instance is reachable via COM."""
    return get_autocad_app() is not None


def get_active_document(acad=None):
    """Return the active AutoCAD document.

    Raises ``RuntimeError`` if AutoCAD is not running or no document is open.
    """
    if acad is None:
        acad = get_autocad_app()
    if acad is None:
        raise RuntimeError("Cannot connect to AutoCAD.  Is it running?")
    doc = acad.ActiveDocument
    if doc is None:
        raise RuntimeError("No AutoCAD document is open.")
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# Selection
# ═══════════════════════════════════════════════════════════════════════════

def prompt_selection(doc=None) -> Any:
    """Ask the user to pick objects in AutoCAD and return a SelectionSet.

    The returned selection set must be deleted by the caller when done.
    Raises ``RuntimeError`` on failure or empty selection.
    """
    if doc is None:
        doc = get_active_document()

    sset_name = "_CivilToolsSel"
    _delete_selection_set(doc, sset_name)

    try:
        sset = doc.SelectionSets.Add(sset_name)
    except Exception as exc:
        raise RuntimeError("Failed to create AutoCAD selection set.") from exc

    try:
        sset.SelectOnScreen()
    except Exception as exc:
        _safe_delete(sset)
        raise RuntimeError(
            "Selection cancelled or failed.  "
            "Please select objects in AutoCAD and try again."
        ) from exc

    if sset.Count == 0:
        _safe_delete(sset)
        raise RuntimeError("No objects were selected in AutoCAD.")

    return sset


def read_selection_set(sset: Any, scale: float = 1.0) -> DxfContent:
    """Convert an AutoCAD SelectionSet into a ``DxfContent``.

    Each entity type is dispatched to a dedicated reader function.
    Unrecognised entities are silently skipped.
    """
    content = DxfContent(scale=scale)
    block_names: set[str] = set()
    hatch_names: set[str] = set()

    # Map EntityName patterns → handler
    _HANDLERS: dict[str, Any] = {
        "LINE":           _read_line,
        "LWPOLYLINE":     _read_polyline,
        "POLYLINE":       _read_polyline,
        "2DPOLYLINE":     _read_polyline,
        "CIRCLE":         _read_circle,
        "BLOCKREFERENCE": _read_block_ref,
        "HATCH":          _read_hatch,
    }

    for i in range(sset.Count):
        entity = sset.Item(i)
        etype = _normalise_entity_name(entity.EntityName)

        handler = _HANDLERS.get(etype)
        if handler is None:
            continue

        try:
            if etype == "BLOCKREFERENCE":
                handler(entity, content, scale, block_names)
            elif etype == "HATCH":
                handler(entity, content, scale, hatch_names)
            else:
                handler(entity, content, scale)
        except Exception:
            continue  # skip problematic entities

    content.block_names = sorted(block_names)
    content.hatch_patterns = sorted(hatch_names)
    return content


# ═══════════════════════════════════════════════════════════════════════════
# High-level convenience (the old API, now built from clean pieces)
# ═══════════════════════════════════════════════════════════════════════════

def read_autocad_selection(unit: str = "mm") -> DxfContent:
    """One-call: prompt user → read selection → return ``DxfContent``.

    This is the function the dialog calls.  It chains:
    ``get_active_document → prompt_selection → read_selection_set``.
    """
    scale = _UNIT_SCALES.get(unit.lower(), 1.0)
    doc = get_active_document()
    sset = prompt_selection(doc)
    try:
        return read_selection_set(sset, scale)
    finally:
        _safe_delete(sset)


# ═══════════════════════════════════════════════════════════════════════════
# Per-entity readers — each does exactly one thing
# ═══════════════════════════════════════════════════════════════════════════

def _read_line(entity: Any, content: DxfContent, scale: float) -> None:
    """Read a single LINE entity."""
    sp = _point2d(entity.StartPoint, scale)
    ep = _point2d(entity.EndPoint, scale)
    content.lines.append(DxfLine(start=sp, end=ep, layer=_layer(entity)))


def _read_polyline(entity: Any, content: DxfContent, scale: float) -> None:
    """Read a LWPOLYLINE / POLYLINE — extract segments and detect rectangles."""
    pts = _polyline_points(entity, scale)
    if len(pts) < 2:
        return

    _add_segments(pts, content, _layer(entity))

    is_closed = _is_closed(entity)
    if is_closed and len(pts) >= 3:
        _add_closing_segment(pts, content, _layer(entity))
    if is_closed and len(pts) == 4:
        _try_add_rect(pts, content, _layer(entity), source="polyline")


def _read_circle(entity: Any, content: DxfContent, scale: float) -> None:
    """Read a single CIRCLE entity."""
    c = _point2d(entity.Center, scale)
    content.circles.append(DxfCircle(center=c, radius=entity.Radius * scale, layer=_layer(entity)))


def _read_block_ref(
    entity: Any, content: DxfContent, scale: float,
    block_names: set[str],
) -> None:
    """Read an INSERT / BlockReference — compute bounding rect."""
    name = str(entity.Name)
    block_names.add(name)

    rect = _bounding_rect(entity, scale, source="block", source_name=name)
    if rect is not None:
        content.rects.append(rect)


def _read_hatch(
    entity: Any, content: DxfContent, scale: float,
    hatch_names: set[str],
) -> None:
    """Read a HATCH — compute bounding rect."""
    pname = _safe_attr(entity, "PatternName", "")
    hatch_names.add(pname)

    rect = _bounding_rect(entity, scale, source="hatch", source_name=pname)
    if rect is not None:
        content.rects.append(rect)


# ═══════════════════════════════════════════════════════════════════════════
# Tiny pure helpers — each does one thing
# ═══════════════════════════════════════════════════════════════════════════

def _normalise_entity_name(raw: str) -> str:
    """Strip vendor prefixes → canonical name.

    ``"AcDbLine"`` → ``"LINE"``, ``"AcDbBlockReference"`` → ``"BLOCKREFERENCE"``.
    """
    upper = raw.upper()
    # Strip common prefixes
    for prefix in ("ACDB", "ACAD", "ACAD_"):
        if upper.startswith(prefix):
            upper = upper[len(prefix):]
            break
    return upper


def _point2d(com_point: Any, scale: float) -> Vec2:
    """Convert a COM Point (tuple/array) to a scaled ``Vec2``."""
    return Vec2(com_point[0] * scale, com_point[1] * scale)


def _layer(entity: Any) -> str:
    """Safely get the layer name."""
    try:
        return str(entity.Layer)
    except Exception:
        return ""


def _safe_attr(entity: Any, attr: str, default: str = "") -> str:
    """Read an attribute without raising."""
    try:
        return str(getattr(entity, attr, default))
    except Exception:
        return default


def _is_closed(entity: Any) -> bool:
    """Check if a polyline is closed, safely."""
    try:
        return bool(entity.Closed)
    except Exception:
        return False


def _polyline_points(entity: Any, scale: float) -> list[tuple[float, float]]:
    """Extract 2-D vertices from a polyline COM object."""
    try:
        coords = list(entity.Coordinates)
    except Exception:
        return []
    # Flat array: x0,y0[,z0], x1,y1[,z1], …
    stride = 3 if (len(coords) > 4 and len(coords) % 3 == 0) else 2
    pts: list[tuple[float, float]] = []
    for j in range(0, len(coords), stride):
        if j + 1 < len(coords):
            pts.append((coords[j] * scale, coords[j + 1] * scale))
    return pts


def _add_segments(
    pts: list[tuple[float, float]], content: DxfContent, layer: str,
) -> None:
    """Add consecutive line segments from a list of points."""
    for a, b in zip(pts[:-1], pts[1:]):
        content.lines.append(DxfLine(
            start=Vec2(a[0], a[1]), end=Vec2(b[0], b[1]), layer=layer,
        ))


def _add_closing_segment(
    pts: list[tuple[float, float]], content: DxfContent, layer: str,
) -> None:
    """Add the segment that closes a polyline."""
    content.lines.append(DxfLine(
        start=Vec2(pts[-1][0], pts[-1][1]),
        end=Vec2(pts[0][0], pts[0][1]),
        layer=layer,
    ))


def _try_add_rect(
    pts: list[tuple[float, float]], content: DxfContent,
    layer: str, source: str,
) -> None:
    """If *pts* form a rectangle, append a ``DxfRect``."""
    from civiltools.dxf.dxf_reader import _rect_from_points
    rect = _rect_from_points(pts, layer=layer, source=source)
    if rect is not None:
        content.rects.append(rect)


def _bounding_rect(
    entity: Any, scale: float,
    *, source: str, source_name: str,
) -> DxfRect | None:
    """Compute a ``DxfRect`` from an entity's bounding box."""
    try:
        bb_min, bb_max = entity.GetBoundingBox()
    except Exception:
        return None

    x1, y1 = bb_min[0] * scale, bb_min[1] * scale
    x2, y2 = bb_max[0] * scale, bb_max[1] * scale
    w, h = abs(x2 - x1), abs(y2 - y1)
    if w < 1 or h < 1:
        return None

    rot = 0.0
    try:
        rot = math.degrees(entity.Rotation)
    except Exception:
        pass

    return DxfRect(
        center=Vec2((x1 + x2) / 2, (y1 + y2) / 2),
        width=w, height=h, rotation=rot,
        layer=_layer(entity),
        source=source, source_name=source_name,
    )


def _delete_selection_set(doc: Any, name: str) -> None:
    """Delete a named selection set if it exists."""
    try:
        doc.SelectionSets.Item(name).Delete()
    except Exception:
        pass


def _safe_delete(sset: Any) -> None:
    """Delete a selection set without raising."""
    try:
        sset.Delete()
    except Exception:
        pass
