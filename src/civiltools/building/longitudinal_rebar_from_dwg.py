"""Extract longitudinal rebar information from AutoCAD drawings via COM.

This module targets **longitudinal rebars** that are annotated as a BLOCK
reference (default name ``"buble"``) carrying visible ATTRIBUTES, plus an
associated LEADER pointing at the physical rebar location.  It complements the
sibling scripts that read plain Text/MText/Dimension entities:

- :mod:`civiltools.building.rebar_from_dwg`  — main/additional rebars as text
- :mod:`civiltools.building.extract_stirrups_from_dwg` — stirrups as text

Original-source porting notes
-----------------------------
The COM connection boilerplate, the ``_spoint`` / ``_dist`` helpers, the
diameter-symbol regex idea, the MText cleanup and the ``summary`` /
``summary_by_size`` shapes are adapted from the two scripts above so behaviour
stays consistent across the tool-set.  ``calculate_hook_parameters`` is reused
directly from :mod:`civiltools.building.rebar_from_dwg`.

Block attribute specification
-----------------------------
Every ``"buble"`` block exposes these attribute tags (case-insensitive):

- ``DES1`` : count + diameter, e.g. ``"2T25"`` -> count = 2, diameter = 25 mm.
- ``DES2`` : total length, e.g. ``"L=240"`` -> length = 240 cm.
- ``Des3`` : shape identifier ``TI`` / ``TL`` / ``TU`` (optionally + a number),
  ``TI`` = straight, ``TL`` = L-shape (one hook), ``TU`` = U-shape (two hooks).
- ``PO``   : position number — ignored.

The shape's trailing number (e.g. ``TL40``) is used only to recognise the shape
type; the drawn bend length is computed from
``calculate_hook_parameters(diameter, '90')`` (the straight tail, mm -> cm).

Stirrup annotations (``T12@15``, ``1T12(ADD)``) are intentionally ignored here.
"""

from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# ── Fix pywin32 DLL loading ────────────────────────────────────────
# pywin32 keeps its DLLs (pywintypes*.dll, pythoncom*.dll) in a separate
# directory that may not be on PATH when running from a conda env.
_pywin32_system32 = os.path.join(
    os.path.dirname(os.path.dirname(os.__file__)),
    "Lib", "site-packages", "pywin32_system32",
)
if os.path.isdir(_pywin32_system32):
    os.add_dll_directory(_pywin32_system32)
    if _pywin32_system32 not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _pywin32_system32 + os.pathsep + os.environ.get("PATH", "")

import pythoncom  # noqa: E402
import win32com.client  # noqa: E402

from civiltools.building.rebar_from_dwg import calculate_hook_parameters  # noqa: E402

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

STEEL_DENSITY = 7850.0          # kg/m³
STANDARD_BAR_LENGTH_M = 12.0    # standard rebar stock length
DEFAULT_BLOCK_NAME = "buble"    # block reference name to look for
DEFAULT_SHAPE_LAYER = "ListoferRebarShapes"

# All AutoCAD representations of the diameter symbol
_DIA = r'(?:%%[cC]|[∅Ø⌀øφΦ~T])'

# ---------------------------------------------------------------------------
#  Regex patterns
# ---------------------------------------------------------------------------

# DES1: count + diameter, e.g. 2T25  -> (2, 25)
RE_DES1 = re.compile(rf'(\d+)\s*{_DIA}\s*(\d+)', re.IGNORECASE)

# DES2: total length, e.g. L=240 or L=240cm / L=2.4m
RE_DES2_LEN = re.compile(r'L\s*=\s*(\d+(?:\.\d+)?)\s*(cm|m)?', re.IGNORECASE)

# Des3: shape identifier TI / TL / TU with optional trailing number, e.g. TL40
RE_SHAPE = re.compile(r'T\s*([ILU])\s*(\d+(?:\.\d+)?)?', re.IGNORECASE)


def _length_cm(value: float, unit: str | None) -> float:
    """Convert a parsed length *value* with *unit* to centimetres."""
    if unit and unit.lower() == 'm':
        return value * 100.0
    return value  # default = cm


def _spoint(x: float, y: float):
    """Create an AutoCAD 2-D point VARIANT."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y))


def _spoint3(x: float, y: float, z: float = 0.0):
    """Create an AutoCAD 3-D point VARIANT."""
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))


def _dist(p1: tuple, p2: tuple) -> float:
    """2-D Euclidean distance between two points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _unit_weight(diameter_mm: float) -> float:
    """Return the unit weight of a rebar (kg/m): ρ × π/4 × d²."""
    d_m = diameter_mm / 1000.0
    area = math.pi / 4.0 * d_m ** 2
    return round(STEEL_DENSITY * area, 3)


def _bend_length_cm(diameter_mm: float, hook_type: str = '90') -> tuple[float, list[str]]:
    """Compute bend dimension in cm as ``bend_radius + straight_tail``.

    ``calculate_hook_parameters`` returns ``(internal_bend_diameter_mm,
    straight_extension_mm)``.  The bend size used for drawing/text equals:

    ``internal_bend_diameter_mm / 2 + straight_extension_mm``  (then mm -> cm)

    Falls back to ``16 * d / 10`` cm when the diameter is out of the
    function's supported range, recording a warning.
    """
    warnings: list[str] = []
    try:
        bend_dia_mm, tail_mm = calculate_hook_parameters(diameter_mm, hook_type)
        bend_radius_mm = bend_dia_mm / 2.0
        bend_size_cm = (bend_radius_mm + tail_mm) / 10.0
        return round(bend_size_cm, 2), warnings
    except ValueError:
        warnings.append(
            f"diameter {diameter_mm}mm out of hook range; used 16*d/10 fallback")
        return round(16.0 * diameter_mm / 10.0, 2), warnings


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class LongitudinalRebarData:
    """One longitudinal rebar parsed from a block + leader."""

    count: int | None = None
    diameter: int | None = None            # mm
    length: float | None = None            # cm  (total developed length)
    shape_type: str = "I"                  # 'I' | 'L' | 'U'
    bend_length: float = 0.0               # cm  (hook tail per bend)
    anchor_point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, float, float] = (1.0, 0.0, 0.0)  # unit vector
    pos: str = ""                          # PO attribute (informational)
    block_id: int | None = None
    leader_id: int | None = None
    raw_texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    complete: bool = False

    def check_completeness(self) -> bool:
        """Validate that all required fields are present."""
        errs: list[str] = []
        if self.count is None:
            errs.append("count")
        if self.diameter is None:
            errs.append("diameter")
        if self.length is None:
            errs.append("length")
        if self.leader_id is None:
            errs.append("leader")
        # keep any non-field errors already recorded (e.g. shape defaulted)
        preserved = [e for e in self.errors if e not in
                     {"count", "diameter", "length", "leader"}]
        self.errors = errs + preserved
        self.complete = len(errs) == 0
        return self.complete

    def unit_weight(self) -> float | None:
        """Unit weight (kg/m), or *None* if diameter is unknown."""
        if self.diameter is None:
            return None
        return _unit_weight(self.diameter)

    def weight_kg(self) -> float | None:
        """Total weight of this bar group (kg), or *None* if incomplete."""
        if self.count is None or self.diameter is None or self.length is None:
            return None
        l_m = self.length / 100.0
        return round(self.count * _unit_weight(self.diameter) * l_m, 2)


@dataclass
class _LeaderInfo:
    """Cached geometry for one leader entity (classic or multileader)."""

    obj_id: int
    start_pt: tuple[float, float, float]   # arrow / content-facing end
    end_pt: tuple[float, float, float]     # tail end (near the block)
    entity_type: str = "LEADER"            # 'LEADER' | 'MLEADER'


# ---------------------------------------------------------------------------
#  Main engine
# ---------------------------------------------------------------------------

class LongitudinalRebarFromDwg:
    """Read longitudinal rebar blocks + leaders from an open AutoCAD drawing.

    The class is intentionally split into *collection* (:meth:`get_all_blocks_and_leaders`),
    *parsing* (:meth:`parse_longitudinal_rebars`) and *drawing*
    (:meth:`draw_rebar_shapes`) so a future GUI command can drive each phase
    independently.
    """

    # Proximity factor for matching a fallback shape text to a block, in
    # multiples of the text height.
    PROXIMITY_FACTOR: int = 20

    def __init__(
        self,
        doc: Any = None,
        block_name: str | None = DEFAULT_BLOCK_NAME,
        hook_type: str = '90',
        layer: str = DEFAULT_SHAPE_LAYER,
    ) -> None:
        if doc is None:
            self.acad: Any = win32com.client.Dispatch("AutoCAD.Application")
            self.acad.Visible = True
            self.doc: Any = self.acad.ActiveDocument
        else:
            self.acad = getattr(doc, "Application", None)
            self.doc = doc
        # ``None`` block_name means: accept every block reference.
        self.block_name = block_name
        self.hook_type = hook_type
        self.layer = layer

        self.blocks: list[Any] = []              # raw COM block references
        self.leaders: list[_LeaderInfo] = []     # cached leader geometry
        self.text_objects: list[tuple[int, str, tuple, float]] = []  # id,text,ip,h
        self.rebars: list[LongitudinalRebarData] = []

    # ------------------------------------------------------------------
    #  MText cleanup
    # ------------------------------------------------------------------
    @staticmethod
    def clean_mtext(text: str) -> str:
        """Strip MText formatting codes, returning plain text."""
        text = re.sub(r'\{\\[^;]+;([^}]*)\}', r'\1', text)
        text = re.sub(r'\\[AHWQTLOoPpCcFf][^;]*;', '', text)
        text = text.replace('\\P', ' ').replace('\\p', ' ')
        text = text.replace('{', '').replace('}', '')
        return ' '.join(text.split()).strip()

    # ------------------------------------------------------------------
    #  Collection
    # ------------------------------------------------------------------
    @staticmethod
    def _block_name_of(block_ref: Any) -> str:
        """Best-effort block name (prefers dynamic EffectiveName)."""
        for attr in ("EffectiveName", "Name"):
            try:
                val = getattr(block_ref, attr, None)
                if val:
                    return str(val)
            except Exception:
                continue
        return ""

    def _point3(self, p: Any) -> tuple[float, float, float]:
        """Normalise a COM point (2- or 3-tuple) to a 3-tuple."""
        return (p[0], p[1], p[2] if len(p) > 2 else 0.0)

    def _read_leader(self, obj: Any) -> _LeaderInfo | None:
        """Extract endpoints from a classic ``AcDbLeader``."""
        try:
            coords = obj.Coordinates  # flat [x1,y1,z1, x2,y2,z2, ...]
            pts = [
                (coords[i], coords[i + 1],
                 coords[i + 2] if i + 2 < len(coords) else 0.0)
                for i in range(0, len(coords) - 2, 3)
            ]
            if len(pts) < 2:
                return None
            # Vertex 0 is the arrow tip; the last vertex is the tail (block side).
            return _LeaderInfo(
                obj_id=obj.ObjectID,
                start_pt=pts[0],
                end_pt=pts[-1],
                entity_type="LEADER",
            )
        except Exception:
            return None

    def _read_mleader(self, obj: Any) -> _LeaderInfo | None:
        """Extract endpoints from a multileader ``AcDbMLeader``.

        The multileader COM API varies across AutoCAD versions, so several
        strategies are attempted before giving up.
        """
        arrow: tuple[float, float, float] | None = None
        tail: tuple[float, float, float] | None = None

        # Strategy 1: explicit leader-line vertices.
        try:
            vtx = obj.GetLeaderLineVertices(0)
            pts = [
                (vtx[i], vtx[i + 1],
                 vtx[i + 2] if i + 2 < len(vtx) else 0.0)
                for i in range(0, len(vtx) - 2, 3)
            ]
            if len(pts) >= 2:
                arrow, tail = pts[0], pts[-1]
        except Exception:
            pass

        # Strategy 2: dedicated first-vertex / content anchor accessors.
        if arrow is None:
            try:
                arrow = self._point3(obj.GetFirstVertex(0))
            except Exception:
                pass
        if tail is None:
            for attr in ("TextLocation", "ContentBasePoint", "InsertionPoint"):
                try:
                    tail = self._point3(getattr(obj, attr))
                    break
                except Exception:
                    continue

        if arrow is None or tail is None:
            return None
        return _LeaderInfo(
            obj_id=obj.ObjectID,
            start_pt=arrow,
            end_pt=tail,
            entity_type="MLEADER",
        )

    def get_all_blocks_and_leaders(self) -> tuple[list[Any], list[_LeaderInfo]]:
        """Single ModelSpace pass collecting target blocks, leaders and texts."""
        self.blocks = []
        self.leaders = []
        self.text_objects = []
        want = (self.block_name or "").strip().lower()

        try:
            msp = self.doc.ModelSpace
            for i in range(msp.Count):
                obj = msp.Item(i)
                name = obj.ObjectName

                if name == "AcDbBlockReference":
                    if not want or self._block_name_of(obj).strip().lower() == want:
                        self.blocks.append(obj)
                elif name == "AcDbLeader":
                    info = self._read_leader(obj)
                    if info:
                        self.leaders.append(info)
                elif name == "AcDbMLeader":
                    info = self._read_mleader(obj)
                    if info:
                        self.leaders.append(info)
                elif name in ("AcDbText", "AcDbMText"):
                    try:
                        raw = obj.TextString
                        txt = self.clean_mtext(raw) if name == "AcDbMText" else raw
                        ip = self._point3(obj.InsertionPoint)
                        h = float(getattr(obj, 'Height', 1.0))
                        self.text_objects.append((obj.ObjectID, txt, ip, h))
                    except Exception:
                        pass
        except Exception as exc:
            print(f"ModelSpace iteration error: {exc}")

        print(f"Found {len(self.blocks)} target block(s), "
              f"{len(self.leaders)} leader(s), "
              f"{len(self.text_objects)} text object(s)")
        return self.blocks, self.leaders

    # ------------------------------------------------------------------
    #  Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _read_attributes(block_ref: Any) -> tuple[dict[str, str], tuple[float, float, float]]:
        """Return ``{TAG_UPPER: value}`` and the block insertion point."""
        attrs: dict[str, str] = {}
        try:
            for at in block_ref.GetAttributes():
                try:
                    tag = str(getattr(at, 'TagString', '') or '').strip().upper()
                    val = str(getattr(at, 'TextString', '') or '').strip()
                    if tag:
                        attrs[tag] = val
                except Exception:
                    continue
        except Exception:
            pass

        ip = (0.0, 0.0, 0.0)
        try:
            p = block_ref.InsertionPoint
            ip = (p[0], p[1], p[2] if len(p) > 2 else 0.0)
        except Exception:
            pass
        return attrs, ip

    def _find_shape_text_nearby(
        self,
        block_ip: tuple[float, float, float],
    ) -> tuple[str, float] | None:
        """Search Text/MText near *block_ip* for a shape identifier (fallback)."""
        best: tuple[str, float] | None = None
        best_dist = float('inf')
        for _oid, txt, ip, h in self.text_objects:
            m = RE_SHAPE.search(txt)
            if not m:
                continue
            max_d = h * self.PROXIMITY_FACTOR
            d = _dist(block_ip, ip)
            if d <= max_d and d < best_dist:
                best_dist = d
                number = float(m.group(2)) if m.group(2) else 0.0
                best = (m.group(1).upper(), number)
        return best

    def _match_leader(
        self,
        block_ip: tuple[float, float, float],
    ) -> _LeaderInfo | None:
        """Nearest leader whose tail endpoint is closest to *block_ip*.

        Tolerance scales with leader length so short leaders still match.
        """
        best: _LeaderInfo | None = None
        best_dist = float('inf')
        for ld in self.leaders:
            # Distance from block to each endpoint; the closer one is the tail.
            d_end = _dist(block_ip, ld.end_pt)
            d_start = _dist(block_ip, ld.start_pt)
            near = min(d_end, d_start)
            leader_len = _dist(ld.start_pt, ld.end_pt)
            tol = max(leader_len * 0.25, 5.0)
            if near <= tol and near < best_dist:
                best_dist = near
                # Ensure start_pt is the ARROW (far from block), end_pt the tail.
                if d_start < d_end:
                    best = _LeaderInfo(
                        obj_id=ld.obj_id,
                        start_pt=ld.end_pt,
                        end_pt=ld.start_pt,
                        entity_type=ld.entity_type,
                    )
                else:
                    best = ld
        return best

    def parse_longitudinal_rebars(self) -> list[LongitudinalRebarData]:
        """Parse every collected block into a :class:`LongitudinalRebarData`."""
        if not self.blocks and not self.leaders:
            self.get_all_blocks_and_leaders()

        self.rebars = []
        for block in self.blocks:
            attrs, block_ip = self._read_attributes(block)
            rd = LongitudinalRebarData(block_id=getattr(block, 'ObjectID', None))
            rd.raw_texts = [f"{k}={v}" for k, v in attrs.items()]

            # DES1 -> count + diameter
            des1 = attrs.get("DES1", "")
            m1 = RE_DES1.search(des1)
            if m1:
                rd.count = int(m1.group(1))
                rd.diameter = int(m1.group(2))

            # DES2 -> length (cm)
            des2 = attrs.get("DES2", "")
            m2 = RE_DES2_LEN.search(des2)
            if m2:
                rd.length = _length_cm(float(m2.group(1)), m2.group(2))

            # PO -> position (informational only)
            rd.pos = attrs.get("PO", "")

            # Des3 -> shape identifier, else search nearby text, else default TI
            shape_src = attrs.get("DES3", "")
            ms = RE_SHAPE.search(shape_src)
            if ms:
                rd.shape_type = ms.group(1).upper()
            else:
                found = self._find_shape_text_nearby(block_ip)
                if found:
                    rd.shape_type = found[0]
                else:
                    rd.shape_type = "I"
                    rd.warnings.append("shape identifier missing; defaulted to TI")

            # Bend length from standard hook tail (TI has no bend).
            if rd.shape_type == "I" or rd.diameter is None:
                rd.bend_length = 0.0
            else:
                rd.bend_length, warns = _bend_length_cm(rd.diameter, self.hook_type)
                rd.warnings.extend(warns)

            # Leader match -> anchor point + direction.
            ld = self._match_leader(block_ip)
            if ld is not None:
                rd.leader_id = ld.obj_id
                rd.anchor_point = ld.start_pt          # arrow tip
                dx = ld.start_pt[0] - block_ip[0]
                dy = ld.start_pt[1] - block_ip[1]
                norm = math.hypot(dx, dy)
                if norm > 1e-9:
                    rd.direction = (dx / norm, dy / norm, 0.0)

            rd.check_completeness()
            self.rebars.append(rd)

        self._report()
        return self.rebars

    def _report(self) -> None:
        """Print a short per-rebar parsing report."""
        print(f"\n{'-' * 50}")
        print(f"PARSED {len(self.rebars)} LONGITUDINAL REBAR(S)")
        print(f"{'-' * 50}")
        for i, rd in enumerate(self.rebars, 1):
            print(f"  [{i}] {rd.count}T{rd.diameter} L={rd.length}cm "
                  f"shape=T{rd.shape_type} bend={rd.bend_length}cm "
                  f"leader={'yes' if rd.leader_id else 'NO'}")
            if rd.errors:
                print(f"      ERRORS: {rd.errors}")
            if rd.warnings:
                print(f"      WARN:   {rd.warnings}")

    # ------------------------------------------------------------------
    #  Drawing (Listofer table)
    # ------------------------------------------------------------------
    def _ensure_layer(self) -> None:
        """Create the output layer if it does not already exist."""
        try:
            layers = self.doc.Layers
            names = {layers.Item(i).Name for i in range(layers.Count)}
            if self.layer not in names:
                layers.Add(self.layer)
        except Exception as exc:
            print(f"Layer setup warning: {exc}")

    def _add_line(self, p1: tuple, p2: tuple) -> None:
        """Add a line on the output layer."""
        try:
            line = self.doc.ModelSpace.AddLine(
                _spoint3(p1[0], p1[1], p1[2] if len(p1) > 2 else 0.0),
                _spoint3(p2[0], p2[1], p2[2] if len(p2) > 2 else 0.0),
            )
            try:
                line.Layer = self.layer
            except Exception:
                pass
        except Exception as exc:
            print(f"AddLine error: {exc}")

    def _draw_cell(self, x: float, y_top: float, width: float, height: float) -> None:
        """Draw a rectangular table cell as four lines."""
        p1 = (x, y_top, 0.0)
        p2 = (x + width, y_top, 0.0)
        p3 = (x + width, y_top - height, 0.0)
        p4 = (x, y_top - height, 0.0)
        self._add_line(p1, p2)
        self._add_line(p2, p3)
        self._add_line(p3, p4)
        self._add_line(p4, p1)

    def _add_text_center(self, text: str, x: float, y: float, text_h: float) -> None:
        """Add centered text at a point."""
        if not text:
            return
        try:
            txt = self.doc.ModelSpace.AddText(text, _spoint3(x, y, 0.0), text_h)
            txt.Alignment = 4  # acAlignmentMiddleCenter
            txt.TextAlignmentPoint = _spoint3(x, y, 0.0)
            txt.Layer = self.layer
        except Exception:
            pass

    def _draw_shape_in_cell(
        self,
        rd: LongitudinalRebarData,
        x: float,
        y_top: float,
        width: float,
        height: float,
        text_h: float,
    ) -> None:
        """Draw TI/TL/TU schematic inside one table cell.

        Conventions requested by user:
        - L: bend is always on the LEFT side and directed downward.
        - U: both bends are directed downward.
        - Straight and bend dimensions are written near the shape.
        """
        margin_x = width * 0.2
        margin_y = height * 0.2

        x1 = x + margin_x
        x2 = x + width - margin_x
        y_mid = y_top - height * 0.42
        shape_text_h = max(text_h * 0.7, 0.6)

        usable_h = max(height - 2.0 * margin_y, 0.1)
        bend = min(float(rd.bend_length or 0.0), usable_h)
        total_len = float(rd.length or 0.0)
        straight_len_i = max(total_len, 0.0)
        straight_len_l = max(total_len - float(rd.bend_length or 0.0), 0.0)
        straight_len_u = max(total_len - 2.0 * float(rd.bend_length or 0.0), 0.0)
        bend_dim = str(int(round(float(rd.bend_length or 0.0))))

        if rd.shape_type == "I":
            self._add_line((x1, y_mid, 0.0), (x2, y_mid, 0.0))
            self._add_text_center(
                str(int(round(straight_len_i))),
                x + width * 0.5,
                y_mid + shape_text_h * 1.2,
                shape_text_h,
            )
            return

        if rd.shape_type == "L":
            # Left bend, directed downward.
            self._add_line((x1, y_mid, 0.0), (x2, y_mid, 0.0))
            self._add_line((x1, y_mid, 0.0), (x1, y_mid - bend, 0.0))
            self._add_text_center(
                str(int(round(straight_len_l))),
                x + width * 0.5,
                y_mid + shape_text_h * 1.2,
                shape_text_h,
            )
            self._add_text_center(
                bend_dim,
                x1 - margin_x * 0.7,
                y_mid - bend * 0.5,
                shape_text_h,
            )
            return

        if rd.shape_type == "U":
            self._add_line((x1, y_mid, 0.0), (x2, y_mid, 0.0))
            # Both bends directed downward.
            self._add_line((x1, y_mid, 0.0), (x1, y_mid - bend, 0.0))
            self._add_line((x2, y_mid, 0.0), (x2, y_mid - bend, 0.0))
            self._add_text_center(
                str(int(round(straight_len_u))),
                x + width * 0.5,
                y_mid + shape_text_h * 1.2,
                shape_text_h,
            )
            self._add_text_center(
                bend_dim,
                x1 - margin_x * 0.7,
                y_mid - bend * 0.5,
                shape_text_h,
            )
            self._add_text_center(
                bend_dim,
                x2 + margin_x * 0.7,
                y_mid - bend * 0.5,
                shape_text_h,
            )
            return

        self._add_line((x1, y_mid, 0.0), (x2, y_mid, 0.0))
        self._add_text_center(
            str(int(round(straight_len_i))),
            x + width * 0.5,
            y_mid + shape_text_h * 1.2,
            shape_text_h,
        )

    def draw_rebar_shapes(
        self,
        insert_point: tuple[float, float] = (0.0, 0.0),
        scale: float = 1.0,
    ) -> int:
        """Draw a listofer-style table with a shape column inside AutoCAD.

        This method intentionally does not draw bars from leader anchor points.
        It draws a schedule table and sketches TI/TL/TU per row in the shape
        column.
        """
        if not self.rebars:
            print("No parsed rebars to draw.")
            return 0

        self._ensure_layer()

        x0, y0 = insert_point
        cell_h = 8.0 * scale
        text_h = max(2.2 * scale, 0.8)

        headers = [
            "Row", "POS", "Description", "Shape", "Dia", "Count",
            "Len(cm)", "Bend(cm)", "UnitW", "TotalW",
        ]
        col_widths = [10, 12, 34, 20, 10, 12, 14, 14, 14, 14]
        col_widths = [w * scale for w in col_widths]

        # Header row
        y = y0
        x = x0
        for w, htxt in zip(col_widths, headers):
            self._draw_cell(x, y, w, cell_h)
            self._add_text_center(htxt, x + w * 0.5, y - cell_h * 0.5, text_h)
            x += w
        y -= cell_h

        # Data rows
        row_count = 0
        sum_weight = 0.0
        sum_length_m = 0.0
        for i, rd in enumerate(self.rebars, 1):
            x = x0
            desc = ""
            if rd.count is not None and rd.diameter is not None and rd.length is not None:
                desc = f"{rd.count}T{rd.diameter} L={int(round(rd.length))}"

            unit_w = rd.unit_weight()
            total_w = rd.weight_kg()
            if rd.length is not None and rd.count is not None:
                sum_length_m += (rd.length * rd.count) / 100.0
            if total_w is not None:
                sum_weight += total_w

            values = [
                str(i),
                rd.pos or "",
                desc,
                "",  # shape cell drawn graphically
                str(rd.diameter or ""),
                str(rd.count or ""),
                str(int(round(rd.length))) if rd.length is not None else "",
                f"{rd.bend_length:.1f}" if rd.shape_type != "I" else "0",
                f"{unit_w:.3f}" if unit_w is not None else "",
                f"{total_w:.2f}" if total_w is not None else "",
            ]

            for col_idx, (w, value) in enumerate(zip(col_widths, values)):
                self._draw_cell(x, y, w, cell_h)
                if col_idx == 3:
                    self._draw_shape_in_cell(rd, x, y, w, cell_h, text_h)
                else:
                    self._add_text_center(value, x + w * 0.5, y - cell_h * 0.5, text_h)
                x += w

            row_count += 1
            y -= cell_h

        # Total row
        x = x0
        total_values = [
            "", "", "TOTAL", "", "", "",
            f"{sum_length_m:.2f}", "", "", f"{sum_weight:.2f}",
        ]
        for col_idx, (w, value) in enumerate(zip(col_widths, total_values)):
            self._draw_cell(x, y, w, cell_h)
            if col_idx != 3:
                self._add_text_center(value, x + w * 0.5, y - cell_h * 0.5, text_h)
            x += w

        print(f"Drew listofer table with {row_count} row(s) on layer '{self.layer}'.")
        return row_count

    # ------------------------------------------------------------------
    #  Summaries
    # ------------------------------------------------------------------
    def summary(self) -> dict[str, int]:
        """Quick counts of parsed rebars."""
        total = len(self.rebars)
        ok = sum(1 for r in self.rebars if r.complete)
        return {
            'total': total,
            'complete': ok,
            'incomplete': total - ok,
            'straight': sum(1 for r in self.rebars if r.shape_type == 'I'),
            'l_shape': sum(1 for r in self.rebars if r.shape_type == 'L'),
            'u_shape': sum(1 for r in self.rebars if r.shape_type == 'U'),
        }

    def summary_by_size(self) -> list[dict[str, Any]]:
        """Group complete rebars by diameter and return summary rows.

        Each row: size (mm), total length (m), number (ceil of total_length /
        12 m), unit weight (kg/m), total weight (kg), plus a TOTAL row.
        """
        groups: dict[int, float] = defaultdict(float)  # dia -> total length (m)
        for rd in self.rebars:
            if rd.diameter is None or rd.count is None or rd.length is None:
                continue
            groups[rd.diameter] += (rd.count * rd.length) / 100.0  # cm -> m

        rows: list[dict[str, Any]] = []
        grand_length = 0.0
        grand_number = 0
        grand_weight = 0.0

        for dia in sorted(groups):
            total_l = groups[dia]
            unit_w = _unit_weight(dia)
            weight = round(total_l * unit_w, 2)
            n_bars = math.ceil(total_l / STANDARD_BAR_LENGTH_M)

            grand_length += total_l
            grand_number += n_bars
            grand_weight += weight

            rows.append({
                'Size (mm)': dia,
                'Total Length (m)': round(total_l, 2),
                'Number (12 m bars)': n_bars,
                'Unit Weight (kg/m)': unit_w,
                'Total Weight (kg)': weight,
            })

        if rows:
            rows.append({
                'Size (mm)': 'TOTAL',
                'Total Length (m)': round(grand_length, 2),
                'Number (12 m bars)': grand_number,
                'Unit Weight (kg/m)': '',
                'Total Weight (kg)': round(grand_weight, 2),
            })

        return rows


# ---------------------------------------------------------------------------
#  Convenience / Demo
# ---------------------------------------------------------------------------

def demo() -> LongitudinalRebarFromDwg:
    """Run a demonstration with sample data (no AutoCAD required)."""
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    # Populate the minimum state the summary/report methods need without COM.
    extractor.block_name = DEFAULT_BLOCK_NAME
    extractor.hook_type = '90'
    extractor.layer = DEFAULT_SHAPE_LAYER
    extractor.blocks = []
    extractor.leaders = []
    extractor.text_objects = []

    samples = [
        LongitudinalRebarData(
            count=2, diameter=25, length=240.0, shape_type='L',
            bend_length=_bend_length_cm(25)[0], anchor_point=(0, 0, 0),
            direction=(1, 0, 0), pos='20', block_id=1, leader_id=101,
        ),
        LongitudinalRebarData(
            count=4, diameter=25, length=364.5, shape_type='U',
            bend_length=_bend_length_cm(25)[0], anchor_point=(0, 100, 0),
            direction=(1, 0, 0), pos='75', block_id=2, leader_id=102,
        ),
        LongitudinalRebarData(
            count=3, diameter=20, length=180.0, shape_type='I',
            bend_length=0.0, anchor_point=(0, 200, 0),
            direction=(1, 0, 0), pos='30', block_id=3, leader_id=103,
        ),
    ]
    for rd in samples:
        rd.check_completeness()
    extractor.rebars = samples

    print("=" * 60)
    print("LONGITUDINAL REBAR SCHEDULE DEMO")
    print("=" * 60)
    extractor._report()

    print("-" * 60)
    print("Summary:", extractor.summary())
    print("-" * 60)
    for row in extractor.summary_by_size():
        print(f"  {row}")
    print("=" * 60)
    return extractor


if __name__ == "__main__":
    demo()
