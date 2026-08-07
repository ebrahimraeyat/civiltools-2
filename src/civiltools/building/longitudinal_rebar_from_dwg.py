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
Typical longitudinal/slab rebar blocks expose these tags (case-insensitive):

- ``DES1`` : rebar designation text; size is read from the diameter symbol,
  e.g. ``"2T25"``, ``"T16(B)"``, ``"T12@120(T)"`` -> diameter = 25/16/12 mm.
- ``DES2`` : total length, e.g. ``"L=240"`` -> length = 240 cm.
- ``DES3`` : shape identifier ``TI`` / ``TL`` / ``TU`` (optionally + a number),
  ``TI`` = straight, ``TL`` = L-shape (one hook), ``TU`` = U-shape (two hooks).
- ``N``    : count (optional fallback).
- ``TN``   : total count (primary source for quantity).
- ``PO``   : position number (informational).

The shape's trailing number (e.g. ``TL40``) is used only to recognise the shape
type; the drawn bend length is computed from
``calculate_hook_parameters(diameter, '90')`` (the straight tail, mm -> cm).

Stirrup annotations (``T12@15``, ``1T12(ADD)``) are intentionally ignored here.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
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

import pythoncom  # noqa: E402,I001
import win32com.client  # noqa: E402

from civiltools.building.listofer_style import (  # noqa: E402
    CELL_HEIGHT as DEFAULT_LONGITUDINAL_TABLE_CELL_H,
    DEFAULT_LISTOFER_TEMPLATE,
    DESCRIPTION_COL_WIDTH,
    DIA_COL_WIDTH as DEFAULT_LONGITUDINAL_TABLE_DIA_COL_WIDTH,
    HEADER_FILL_COLOR,
    MIN_TEXT_HEIGHT as DEFAULT_LONGITUDINAL_TABLE_MIN_TEXT_H,
    POS_COL_WIDTH,
    ROW_COL_WIDTH,
    SHAPE_COL_WIDTH,
    SUMMARY_FILL_COLOR,
    TEXT_HEIGHT as DEFAULT_LONGITUDINAL_TABLE_TEXT_H,
    TEXT_HEIGHT_FACTOR as DEFAULT_LONGITUDINAL_TABLE_TEXT_FACTOR,
    UNIT_WEIGHT_COL_WIDTH,
    VIEW_TABLE_GAP_CELLS,
    resolve_text_height,
)
from civiltools.building.rebar_from_dwg import (  # noqa: E402
    calculate_hook_parameters,
    calculate_length_with_hooks,
)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

STEEL_DENSITY = 7850.0          # kg/m³
STANDARD_BAR_LENGTH_M = 12.0    # standard rebar stock length
DEFAULT_BLOCK_NAME = "buble"    # block reference name to look for
DEFAULT_SHAPE_LAYER = "ListoferRebarShapes"
# Fixed columns: Row, POS, Description, Shape (shared widths) + Cnt,
# Len, Bend (longitudinal-specific) + UnitW (shared width)
DEFAULT_LONGITUDINAL_TABLE_COL_WIDTHS = [
    ROW_COL_WIDTH, POS_COL_WIDTH, DESCRIPTION_COL_WIDTH, SHAPE_COL_WIDTH,
    12, 14, 14, UNIT_WEIGHT_COL_WIDTH,
]

# All AutoCAD representations of the diameter symbol
_DIA = r'(?:%%[cC]|[∅Ø⌀øφΦ~T])'

# ---------------------------------------------------------------------------
#  Regex patterns
# ---------------------------------------------------------------------------

# DES1 legacy form: count + diameter, e.g. 2T25 -> (2, 25)
RE_DES1_COUNT_DIA = re.compile(rf'(\d+)\s*{_DIA}\s*(\d+)', re.IGNORECASE)

# DES1 diameter token: T16, %%c20, ∅25, ...
RE_DES1_DIA = re.compile(rf'{_DIA}\s*(\d+)', re.IGNORECASE)

# DES2: total length, e.g. L=240 or L=240cm / L=2.4m
RE_DES2_LEN = re.compile(r'L\s*=\s*(\d+(?:\.\d+)?)\s*(cm|m)?', re.IGNORECASE)

# Des3: shape identifier TI / TL / TU with optional trailing number, e.g. TL40
RE_SHAPE = re.compile(r'T\s*([ILU])\s*(\d+(?:\.\d+)?)?', re.IGNORECASE)


def _parse_int_attr(value: str | None) -> int | None:
    """Parse an integer attribute value; return ``None`` on failure."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


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
    """Compute bend dimension in cm via :func:`calculate_length_with_hooks`.

    Longitudinal rebar bends are 90-degree hooks by default. Falls back to
    ``16 * d / 10`` cm when the diameter is out of the function's supported
    range, recording a warning.
    """
    warnings: list[str] = []
    try:
        bend_size_cm = calculate_length_with_hooks(diameter_mm, hook_type)
        return round(bend_size_cm, 2), warnings
    except ValueError:
        warnings.append(
            f"diameter {diameter_mm}mm out of hook range; used 16*d/10 fallback")
        return round(16.0 * diameter_mm / 10.0, 2), warnings


def _bend_radius_cm(diameter_mm: float, hook_type: str = '90') -> float:
    """Return bend radius in cm from hook parameters."""
    try:
        bend_dia_mm, _tail_mm = calculate_hook_parameters(diameter_mm, hook_type)
        return round(bend_dia_mm / 20.0, 2)  # dia(mm)/2 -> radius(mm), then mm -> cm
    except ValueError:
        return round((4.0 * diameter_mm) / 10.0, 2)


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
    des1: str = ""
    des2: str = ""
    des3: str = ""
    n: int | None = None
    tn: int | None = None
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
        block_names: list[str] | tuple[str, ...] | set[str] | None = None,
        block_layers: list[str] | tuple[str, ...] | set[str] | None = None,
        hook_type: str = '90',
        layer: str = DEFAULT_SHAPE_LAYER,
        template_path: str | Path | None = DEFAULT_LISTOFER_TEMPLATE,
        # Match stirrup listofer: fixed insert scale (not multiplied by table scale).
        block_scale: float = 0.08,
    ) -> None:
        if doc is None:
            self.acad: Any = win32com.client.Dispatch("AutoCAD.Application")
            self.acad.Visible = True
            self.doc: Any = self.acad.ActiveDocument
        else:
            self.acad = getattr(doc, "Application", None)
            self.doc = doc
        # ``None``/empty filters mean: accept every block reference.
        self.block_name = block_name  # backward compatibility
        names: set[str] = set()
        if block_names:
            names.update(str(n).strip().lower() for n in block_names if str(n).strip())
        elif block_name and str(block_name).strip():
            names.add(str(block_name).strip().lower())
        self.block_names: set[str] | None = names or None

        layers: set[str] = set()
        if block_layers:
            layers.update(str(n).strip().lower() for n in block_layers if str(n).strip())
        self.block_layers: set[str] | None = layers or None

        self.hook_type = hook_type
        self.layer = layer
        self.template_path = Path(template_path) if template_path else None
        self.block_scale = float(block_scale)
        self._template_blocks_ready = False
        # Cached template metrics: name -> (width, height, center_x, center_y)
        self._shape_block_metrics: dict[str, tuple[float, float, float, float]] | None = None

        self.blocks: list[Any] = []              # raw COM block references
        self.leaders: list[_LeaderInfo] = []     # cached leader geometry
        self.text_objects: list[tuple[int, str, tuple, float]] = []  # id,text,ip,h
        self.rebars: list[LongitudinalRebarData] = []

    # ------------------------------------------------------------------
    #  Template block loading
    # ------------------------------------------------------------------
    @staticmethod
    def _to_deg(rad: float) -> float:
        return rad * 180.0 / math.pi

    def _get_ezdxf(self):
        try:
            import ezdxf
        except ImportError as exc:
            raise ImportError(
                "Install ezdxf to load listofer template blocks (pip install ezdxf)."
            ) from exc
        return ezdxf

    def _entity_color(self, ent: Any) -> int | None:
        try:
            c = int(ent.dxf.color)
            return c if c > 0 else None
        except Exception:
            return None

    def _copy_template_entity_to_block(self, blk_com: Any, ent: Any) -> None:
        etype = ent.dxftype()
        color = self._entity_color(ent)
        created = None

        if etype == "LINE":
            s = ent.dxf.start
            e = ent.dxf.end
            created = blk_com.AddLine(
                _spoint3(s.x, s.y, getattr(s, "z", 0.0)),
                _spoint3(e.x, e.y, getattr(e, "z", 0.0)),
            )

        elif etype == "ARC":
            c = ent.dxf.center
            created = blk_com.AddArc(
                _spoint3(c.x, c.y, getattr(c, "z", 0.0)),
                float(ent.dxf.radius),
                float(ent.dxf.start_angle) * math.pi / 180.0,
                float(ent.dxf.end_angle) * math.pi / 180.0,
            )

        elif etype == "CIRCLE":
            c = ent.dxf.center
            created = blk_com.AddCircle(
                _spoint3(c.x, c.y, getattr(c, "z", 0.0)),
                float(ent.dxf.radius),
            )

        elif etype == "LWPOLYLINE":
            pts = list(ent.get_points("xyb"))
            if len(pts) >= 2:
                flat = []
                for x, y, _bulge in pts:
                    flat.extend([x, y])
                pl = blk_com.AddLightWeightPolyline(
                    win32com.client.VARIANT(
                        pythoncom.VT_ARRAY | pythoncom.VT_R8,
                        tuple(flat),
                    )
                )
                for i, (_x, _y, bulge) in enumerate(pts):
                    if abs(float(bulge or 0.0)) > 1e-9:
                        try:
                            pl.SetBulge(i, float(bulge))
                        except Exception:
                            pass
                try:
                    pl.Closed = bool(ent.closed)
                except Exception:
                    pass
                created = pl

        elif etype == "TEXT":
            ins = ent.dxf.insert
            created = blk_com.AddText(
                str(ent.dxf.text),
                _spoint3(ins.x, ins.y, getattr(ins, "z", 0.0)),
                float(getattr(ent.dxf, "height", 1.0) or 1.0),
            )
            try:
                created.Rotation = float(getattr(ent.dxf, "rotation", 0.0) or 0.0) * math.pi / 180.0
            except Exception:
                pass

        elif etype == "ATTDEF":
            ins = ent.dxf.insert
            created = blk_com.AddAttribute(
                float(getattr(ent.dxf, "height", 1.0) or 1.0),
                0,
                str(getattr(ent.dxf, "prompt", ent.dxf.tag)),
                _spoint3(ins.x, ins.y, getattr(ins, "z", 0.0)),
                str(ent.dxf.tag),
                str(getattr(ent.dxf, "text", "") or ""),
            )

        if created is not None and color is not None:
            try:
                created.Color = color
            except Exception:
                pass

    def _ensure_template_blocks(self) -> None:
        if self._template_blocks_ready:
            return
        if self.template_path is None:
            return
        if not self.template_path.exists():
            print(f"Template not found: {self.template_path}")
            return

        needed = {"TI", "TL", "TU", "tc", "TO"}
        try:
            blocks = self.doc.Blocks
            existing = {blocks.Item(i).Name for i in range(blocks.Count)}
        except Exception:
            existing = set()

        missing = [name for name in needed if name not in existing]
        if not missing:
            self._template_blocks_ready = True
            return

        ezdxf = self._get_ezdxf()
        readfile_fn = getattr(ezdxf, "readfile", None)
        if readfile_fn is None:
            from ezdxf import filemanagement as _filemanagement

            readfile_fn = _filemanagement.readfile
        tdoc = readfile_fn(str(self.template_path))

        for bname in missing:
            if bname not in tdoc.blocks:
                continue
            try:
                blk_com = self.doc.Blocks.Add(_spoint3(0.0, 0.0, 0.0), bname)
            except Exception:
                continue
            for ent in tdoc.blocks.get(bname):
                try:
                    self._copy_template_entity_to_block(blk_com, ent)
                except Exception:
                    continue

        self._template_blocks_ready = True

    def _set_block_attributes(self, block_ref: Any, values: dict[str, str]) -> None:
        try:
            attrs = block_ref.GetAttributes()
        except Exception:
            return
        for at in attrs:
            try:
                tag = str(getattr(at, "TagString", "") or "").strip().upper()
                if tag in values:
                    at.TextString = str(values[tag])
            except Exception:
                continue

    def _collect_entity_points(self, entity: Any) -> list[tuple[float, float]]:
        """Collect 2D points from a template entity for bounding-box metrics."""
        points: list[tuple[float, float]] = []
        etype = entity.dxftype()
        try:
            get_points = getattr(entity, "get_points", None)
            if get_points is not None:
                points.extend((float(pt[0]), float(pt[1])) for pt in get_points("xy"))
                return points
        except Exception:
            pass

        try:
            if etype == "LINE":
                points.extend(
                    [
                        (float(entity.dxf.start.x), float(entity.dxf.start.y)),
                        (float(entity.dxf.end.x), float(entity.dxf.end.y)),
                    ]
                )
            elif etype in {"CIRCLE", "ARC"}:
                center = entity.dxf.center
                radius = float(entity.dxf.radius)
                points.extend(
                    [
                        (float(center.x) - radius, float(center.y) - radius),
                        (float(center.x) + radius, float(center.y) + radius),
                    ]
                )
            elif etype in {"TEXT", "ATTDEF", "MTEXT", "INSERT"}:
                insert = entity.dxf.insert
                points.append((float(insert.x), float(insert.y)))
                # Pad attribute/text extents so length labels keep a visual margin.
                height = float(getattr(entity.dxf, "height", 0.0) or 0.0)
                if height > 0.0:
                    # ~half-width of a short numeric label around the insert point.
                    pad_x = height * 1.6
                    pad_y = height * 0.6
                    points.extend(
                        [
                            (float(insert.x) - pad_x, float(insert.y) - pad_y),
                            (float(insert.x) + pad_x, float(insert.y) + pad_y),
                        ]
                    )
        except Exception:
            return points
        return points

    def _load_shape_block_metrics(self) -> dict[str, tuple[float, float, float, float]]:
        """Return template block size/center metrics for TI/TL/TU."""
        metrics: dict[str, tuple[float, float, float, float]] = {}
        if not self.template_path or not self.template_path.exists():
            return metrics
        try:
            ezdxf = self._get_ezdxf()
            readfile_fn = getattr(ezdxf, "readfile", None)
            if readfile_fn is None:
                from ezdxf import filemanagement as _filemanagement

                readfile_fn = _filemanagement.readfile
            template = readfile_fn(str(self.template_path))
        except Exception:
            return metrics

        for name in ("TI", "TL", "TU"):
            if name not in template.blocks:
                continue
            points: list[tuple[float, float]] = []
            for entity in template.blocks[name]:
                points.extend(self._collect_entity_points(entity))
            if not points:
                continue
            xs = [pt[0] for pt in points]
            ys = [pt[1] for pt in points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            width = max_x - min_x
            height = max_y - min_y
            if width <= 0.0 or height <= 0.0:
                continue
            metrics[name] = (
                width,
                height,
                0.5 * (min_x + max_x),
                0.5 * (min_y + max_y),
            )
        return metrics

    def _shape_block_metrics_for(
        self, block_name: str
    ) -> tuple[float, float, float, float] | None:
        """Lazy-load and return (width, height, center_x, center_y) for a block."""
        if self._shape_block_metrics is None:
            self._shape_block_metrics = self._load_shape_block_metrics()
        return self._shape_block_metrics.get(block_name)

    def _shape_placement_for_cell(
        self,
        block_name: str,
        x: float,
        y_top: float,
        width: float,
        height: float,
    ) -> tuple[float, float, float]:
        """Return (insert_x, insert_y, scale) so the shape fits with cell margin."""
        # Keep a clear margin around geometry + bend labels (L1/L2/L3).
        margin_x = 0.12
        margin_y = 0.16
        usable_w = max(width * (1.0 - 2.0 * margin_x), width * 0.5)
        usable_h = max(height * (1.0 - 2.0 * margin_y), height * 0.5)

        metrics = self._shape_block_metrics_for(block_name)
        cell_cx = x + width * 0.5
        cell_cy = y_top - height * 0.5
        if metrics is None:
            # Fallback: fixed scale, slightly above geometric mid like before.
            return cell_cx, y_top - height * 0.60, self.block_scale

        block_w, block_h, center_x, center_y = metrics
        fit_scale = min(usable_w / block_w, usable_h / block_h)
        # Never larger than the configured default; shrink when the cell is tight.
        block_scale = min(self.block_scale, fit_scale) if self.block_scale > 0 else fit_scale
        if block_scale <= 0.0:
            block_scale = fit_scale

        # Shift insert point so the content bbox center lands on the cell center.
        insert_x = cell_cx - center_x * block_scale
        insert_y = cell_cy - center_y * block_scale
        return insert_x, insert_y, block_scale

    @staticmethod
    def _shape_attr_values(rd: LongitudinalRebarData) -> dict[str, str]:
        """Build L1/L2/L3 attribute values for a longitudinal shape block."""
        total_len = float(rd.length or 0.0)
        bend_len = float(rd.bend_length or 0.0)
        shape = rd.shape_type.upper()
        if shape == "L":
            straight = max(total_len - bend_len, 0.0)
            return {
                "L1": str(int(round(straight))),
                "L2": str(int(round(bend_len))),
                "L3": str(int(round(bend_len))),
            }
        if shape == "U":
            straight = max(total_len - 2.0 * bend_len, 0.0)
            return {
                "L1": str(int(round(straight))),
                "L2": str(int(round(bend_len))),
                "L3": str(int(round(bend_len))),
            }
        # TI should not modify L2/L3 even if they exist in the block.
        return {"L1": str(int(round(max(total_len, 0.0))))}

    def _insert_template_shape_block(
        self,
        rd: LongitudinalRebarData,
        x: float,
        y_top: float,
        width: float,
        height: float,
        scale: float = 1.0,
    ) -> bool:
        self._ensure_template_blocks()

        block_map = {
            "I": "TI",
            "L": "TL",
            "U": "TU",
        }
        bname = block_map.get(rd.shape_type.upper(), "TI")
        attr_values = self._shape_attr_values(rd)
        ins_x, ins_y, block_scale = self._shape_placement_for_cell(
            bname, x, y_top, width, height
        )

        try:
            bref = self.doc.ModelSpace.InsertBlock(
                _spoint3(ins_x, ins_y, 0.0),
                bname,
                block_scale,
                block_scale,
                block_scale,
                0.0,
            )
            try:
                bref.Layer = self.layer
            except Exception:
                pass
            self._set_block_attributes(bref, attr_values)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    #  DXF export helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _current_doc_dir(doc: Any) -> Path:
        """Return directory of active AutoCAD document, fallback to cwd."""
        try:
            full_name = str(getattr(doc, "FullName", "") or "").strip()
            if full_name:
                return Path(full_name).resolve().parent
        except Exception:
            pass
        return Path.cwd().resolve()

    def _resolve_output_dxf_path(
        self,
        output_path: str | Path | None,
        filename: str | None,
        prefix: str = "longitudinal_listofer",
    ) -> Path:
        """Build output DXF path next to current DWG unless explicit path is passed."""
        if output_path is not None:
            return Path(output_path).resolve()

        out_dir = self._current_doc_dir(self.doc)
        if filename:
            name = filename
            if not name.lower().endswith(".dxf"):
                name += ".dxf"
        else:
            name = f"{prefix}_{uuid.uuid4().hex[:8]}.dxf"
        return out_dir / name

    @staticmethod
    def _draw_cell_dxf(msp: Any, x: float, y_top: float, width: float, height: float) -> None:
        """Draw one rectangular cell in a DXF modelspace."""
        pts = [
            (x, y_top),
            (x + width, y_top),
            (x + width, y_top - height),
            (x, y_top - height),
            (x, y_top),
        ]
        msp.add_lwpolyline(pts)

    @staticmethod
    def _add_text_center_dxf(
        msp: Any,
        text: str,
        x: float,
        y: float,
        text_h: float,
    ) -> None:
        """Add centered text in DXF using MIDDLE_CENTER alignment."""
        if not text:
            return
        from ezdxf.enums import TextEntityAlignment

        txt = msp.add_text(str(text), dxfattribs={"height": text_h})
        txt.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)

    def _insert_shape_block_dxf(
        self,
        msp: Any,
        rd: LongitudinalRebarData,
        x: float,
        y_top: float,
        width: float,
        height: float,
        scale: float = 1.0,
    ) -> bool:
        """Insert TI/TL/TU block with L1/L2/L3 attributes in DXF modelspace."""
        doc = msp.doc
        block_map = {"I": "TI", "L": "TL", "U": "TU"}
        bname = block_map.get(rd.shape_type.upper(), "TI")
        if bname not in doc.blocks:
            return False

        attr_values = self._shape_attr_values(rd)
        insert_x, insert_y, block_scale = self._shape_placement_for_cell(
            bname, x, y_top, width, height
        )
        bref = msp.add_blockref(
            bname,
            (insert_x, insert_y),
            dxfattribs={
                "xscale": block_scale,
                "yscale": block_scale,
                "zscale": block_scale,
                "rotation": 0.0,
            },
        )
        try:
            bref.add_auto_attribs(attr_values)
        except Exception:
            pass
        return True

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

    @staticmethod
    def _block_layer_of(block_ref: Any) -> str:
        """Best-effort block layer name."""
        try:
            return str(getattr(block_ref, "Layer", "") or "")
        except Exception:
            return ""

    @staticmethod
    def _parse_des1(des1: str) -> tuple[int | None, int | None]:
        """Parse DES1 into ``(legacy_count, diameter_mm)``.

        Supports both classic forms (``2T25``) and designation-only forms
        (``T16(B)``, ``T12@120(T)``). The caller decides how to source count.
        """
        text = str(des1 or "").strip()
        if not text:
            return None, None

        legacy_count: int | None = None
        diameter: int | None = None

        m_count = RE_DES1_COUNT_DIA.search(text)
        if m_count:
            legacy_count = int(m_count.group(1))
            diameter = int(m_count.group(2))

        if diameter is None:
            m_dia = RE_DES1_DIA.search(text)
            if m_dia:
                diameter = int(m_dia.group(1))

        return legacy_count, diameter

    def _block_matches_filters(self, block_ref: Any) -> bool:
        """Return True when block passes configured name/layer filters."""
        bname = self._block_name_of(block_ref).strip().lower()
        blayer = self._block_layer_of(block_ref).strip().lower()
        if self.block_names is not None and bname not in self.block_names:
            return False
        if self.block_layers is not None and blayer not in self.block_layers:
            return False
        return True

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

        try:
            msp = self.doc.ModelSpace
            for i in range(msp.Count):
                obj = msp.Item(i)
                name = obj.ObjectName

                if name == "AcDbBlockReference":
                    if self._block_matches_filters(obj):
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

            rd.des1 = attrs.get("DES1", "")
            rd.des2 = attrs.get("DES2", "")
            rd.des3 = attrs.get("DES3", "")
            rd.n = _parse_int_attr(attrs.get("N", ""))
            rd.tn = _parse_int_attr(attrs.get("TN", ""))

            # DES1 -> diameter (+ optional legacy count from classic 2T25 style)
            des1_count, des1_dia = self._parse_des1(rd.des1)
            rd.diameter = des1_dia

            # Quantity source priority: TN, then N, then legacy DES1 count.
            if rd.tn is not None:
                rd.count = rd.tn
                if rd.n is not None and rd.n != rd.tn:
                    rd.warnings.append(f"N={rd.n} differs from TN={rd.tn}; used TN")
                if des1_count is not None and des1_count != rd.tn:
                    rd.warnings.append(
                        f"DES1 count={des1_count} differs from TN={rd.tn}; used TN"
                    )
            elif rd.n is not None:
                rd.count = rd.n
                rd.warnings.append("TN missing; used N as count")
            elif des1_count is not None:
                rd.count = des1_count
                rd.warnings.append("TN/N missing; used legacy DES1 count")

            # DES2 -> length (cm)
            m2 = RE_DES2_LEN.search(rd.des2)
            if m2:
                rd.length = _length_cm(float(m2.group(1)), m2.group(2))

            # PO -> position (informational only)
            rd.pos = attrs.get("PO", "")

            # Des3 -> shape identifier, else search nearby text, else default TI
            ms = RE_SHAPE.search(rd.des3)
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

    def _add_line(self, p1: tuple, p2: tuple, color: int | None = None) -> None:
        """Add a line on the output layer."""
        try:
            line = self.doc.ModelSpace.AddLine(
                _spoint3(p1[0], p1[1], p1[2] if len(p1) > 2 else 0.0),
                _spoint3(p2[0], p2[1], p2[2] if len(p2) > 2 else 0.0),
            )
            try:
                line.Layer = self.layer
                if color is not None:
                    line.Color = color
            except Exception:
                pass
        except Exception as exc:
            print(f"AddLine error: {exc}")

    def _add_arc(
        self,
        center: tuple[float, float, float],
        radius: float,
        start_angle: float,
        end_angle: float,
        color: int | None = None,
    ) -> None:
        """Add an arc on the output layer."""
        if radius <= 0:
            return
        try:
            arc = self.doc.ModelSpace.AddArc(
                _spoint3(center[0], center[1], center[2] if len(center) > 2 else 0.0),
                radius,
                start_angle,
                end_angle,
            )
            try:
                arc.Layer = self.layer
                if color is not None:
                    arc.Color = color
            except Exception:
                pass
        except Exception as exc:
            print(f"AddArc error: {exc}")

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

    def _add_text_center(
        self,
        text: str,
        x: float,
        y: float,
        text_h: float,
        color: int | None = None,
    ) -> None:
        """Add centered text at a point."""
        if not text:
            return
        try:
            txt = self.doc.ModelSpace.AddText(text, _spoint3(x, y, 0.0), text_h)
            txt.Alignment = 4  # acAlignmentMiddleCenter
            txt.TextAlignmentPoint = _spoint3(x, y, 0.0)
            txt.Layer = self.layer
            if color is not None:
                txt.Color = color
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
        scale: float = 1.0,
    ) -> None:
        """Insert TI/TL/TU block and rewrite L1/L2/L3 attributes only."""
        _ = text_h  # shape text is inside template block attributes
        ok = self._insert_template_shape_block(rd, x, y_top, width, height, scale)
        if not ok:
            print(
                "Template block insertion failed for shape "
                f"T{rd.shape_type} (POS={rd.pos or '-'})"
            )

    def _used_diameters(
        self,
        rebars: list[LongitudinalRebarData] | None = None,
    ) -> list[int]:
        """Return the sorted list of unique rebar diameters actually used."""
        source = self.rebars if rebars is None else rebars
        return sorted({int(rd.diameter) for rd in source if rd.diameter})

    @staticmethod
    def _longitudinal_table_headers(dias: list[int]) -> tuple[list[str], int]:
        """Build table headers: fixed columns + one column per used diameter."""
        fixed = ["Row", "POS", "Description", "Shape", "Cnt", "Len", "Bend", "UnitW"]
        headers = fixed + [f"T{d}" for d in dias]
        return headers, len(fixed)

    @staticmethod
    def _longitudinal_row_values(
        row_no: int,
        rd: LongitudinalRebarData,
        dias: list[int],
    ) -> list[str]:
        """Build one data-row cell values (shape column left empty for graphics)."""
        desc = ""
        if rd.count is not None and rd.diameter is not None and rd.length is not None:
            desc = f"{rd.count}T{rd.diameter} L={int(round(rd.length))}"

        unit_w = rd.unit_weight()
        total_w = rd.weight_kg()

        values = [
            str(row_no),
            rd.pos or "",
            desc,
            "",  # shape cell drawn graphically
            str(rd.count or ""),
            str(int(round(rd.length))) if rd.length is not None else "",
            f"{rd.bend_length:.1f}" if rd.shape_type != "I" else "0",
            f"{unit_w:.3f}" if unit_w is not None else "",
        ]
        for dia in dias:
            values.append(
                f"{total_w:.2f}" if rd.diameter == dia and total_w is not None else ""
            )
        return values

    @staticmethod
    def _diameter_summary_maps(
        summary: list[dict[str, Any]],
    ) -> tuple[dict[int, float], dict[int, float], float]:
        """Split ``summary_by_size()`` rows into per-diameter maps + grand total."""
        length_map: dict[int, float] = {}
        weight_map: dict[int, float] = {}
        grand_weight = 0.0
        for row in summary:
            size = row.get('Size (mm)')
            if size == 'TOTAL':
                grand_weight = float(row.get('Total Weight (kg)') or 0.0)
                continue
            if not isinstance(size, (int, float)):
                continue
            dia = int(size)
            length_map[dia] = float(row.get('Total Length (m)') or 0.0)
            weight_map[dia] = float(row.get('Total Weight (kg)') or 0.0)
        return length_map, weight_map, grand_weight

    @staticmethod
    def _longitudinal_view_rows(
        rebars: list[LongitudinalRebarData],
        view_mode: str | None,
    ) -> list[tuple[str, list[LongitudinalRebarData]]]:
        """Expand *view_mode* into one or two ``(label, rebars)`` table views."""
        from civiltools.building.listofer_grouping import (
            DEFAULT_LISTOFER_VIEW_MODE,
            group_longitudinal_rebars,
            iter_listofer_views,
        )

        return iter_listofer_views(
            rebars,
            group_longitudinal_rebars,
            view_mode if view_mode is not None else DEFAULT_LISTOFER_VIEW_MODE,
        )

    def _draw_longitudinal_summary(
        self,
        dias: list[int],
        x0: float,
        y: float,
        col_widths: list[float],
        cell_h: float,
        text_h: float,
        fixed_col_count: int,
        rebars: list[LongitudinalRebarData] | None = None,
    ) -> float:
        """Draw the per-size TOTAL LENGTH / TOTAL WEIGHT / PERCENTAGE / GRAND TOTAL block.

        Returns the Y coordinate after the summary block (bottom of last row).
        """
        if not dias:
            return y
        length_map, weight_map, grand_weight = self._diameter_summary_maps(
            self.summary_by_size(rebars)
        )
        label_width = sum(col_widths[:fixed_col_count])
        dia_widths = col_widths[fixed_col_count:]

        def draw_label_row(label: str, dia_values: list[str]) -> None:
            nonlocal y
            self._draw_cell(x0, y, label_width, cell_h)
            self._add_text_center(
                label, x0 + label_width * 0.5, y - cell_h * 0.5, text_h,
                color=SUMMARY_FILL_COLOR,
            )
            x = x0 + label_width
            for width, value in zip(dia_widths, dia_values):
                self._draw_cell(x, y, width, cell_h)
                self._add_text_center(
                    value, x + width * 0.5, y - cell_h * 0.5, text_h,
                    color=SUMMARY_FILL_COLOR,
                )
                x += width
            y -= cell_h

        draw_label_row(
            "TOTAL LENGTH (m)", [f"{length_map.get(d, 0.0):.2f}" for d in dias]
        )
        draw_label_row(
            "TOTAL WEIGHT (Kg)", [f"{weight_map.get(d, 0.0):.2f}" for d in dias]
        )
        draw_label_row(
            "PERCENTAGE (%)",
            [
                f"{(weight_map.get(d, 0.0) / grand_weight * 100.0):.0f}%"
                if grand_weight else "0%"
                for d in dias
            ],
        )

        # Grand total: merged label cell + merged value cell spanning all sizes
        self._draw_cell(x0, y, label_width, cell_h)
        self._add_text_center(
            "GRAND TOTAL (Kg)", x0 + label_width * 0.5, y - cell_h * 0.5, text_h,
            color=SUMMARY_FILL_COLOR,
        )
        dia_total_width = sum(dia_widths)
        self._draw_cell(x0 + label_width, y, dia_total_width, cell_h)
        self._add_text_center(
            f"{grand_weight:.2f} Kg.",
            x0 + label_width + dia_total_width * 0.5,
            y - cell_h * 0.5,
            text_h,
            color=SUMMARY_FILL_COLOR,
        )
        return y - cell_h

    def _draw_one_longitudinal_table_acad(
        self,
        rebars: list[LongitudinalRebarData],
        x0: float,
        y0: float,
        scaled_col_widths: list[float],
        cell_h: float,
        text_h: float,
        dias: list[int],
        fixed_col_count: int,
        scale: float,
        title: str | None = None,
    ) -> tuple[float, int]:
        """Draw one longitudinal table in AutoCAD; return (bottom Y, row count)."""
        y = y0
        if title:
            self._add_text_center(
                title, x0 + sum(scaled_col_widths) * 0.5, y - cell_h * 0.5, text_h,
            )
            y -= cell_h

        headers, _ = self._longitudinal_table_headers(dias)
        x = x0
        for w, htxt in zip(scaled_col_widths, headers):
            self._draw_cell(x, y, w, cell_h)
            self._add_text_center(
                htxt, x + w * 0.5, y - cell_h * 0.5, text_h, color=HEADER_FILL_COLOR,
            )
            x += w
        y -= cell_h

        row_count = 0
        for i, rd in enumerate(rebars, 1):
            values = self._longitudinal_row_values(i, rd, dias)
            x = x0
            for col_idx, (w, value) in enumerate(zip(scaled_col_widths, values)):
                self._draw_cell(x, y, w, cell_h)
                if col_idx == 3:
                    self._draw_shape_in_cell(rd, x, y, w, cell_h, text_h, scale)
                else:
                    self._add_text_center(value, x + w * 0.5, y - cell_h * 0.5, text_h)
                x += w
            row_count += 1
            y -= cell_h

        y = self._draw_longitudinal_summary(
            dias, x0, y, scaled_col_widths, cell_h, text_h, fixed_col_count,
            rebars=rebars,
        )
        return y, row_count

    def draw_rebar_shapes(
        self,
        insert_point: tuple[float, float] = (0.0, 0.0),
        scale: float = 1.0,
        col_widths: list[float] | None = None,
        dia_col_width: float = DEFAULT_LONGITUDINAL_TABLE_DIA_COL_WIDTH,
        view_mode: str | None = None,
    ) -> int:
        """Draw listofer table and fill shape column via template blocks.

        *view_mode*: ``\"detailed\"`` | ``\"grouped\"`` | ``\"both\"`` (default both).
        When ``both``, draws the full table then a grouped table below it.
        """
        if not self.rebars:
            print("No parsed rebars to draw.")
            return 0

        self._ensure_layer()

        x0, y0 = insert_point
        cell_h = DEFAULT_LONGITUDINAL_TABLE_CELL_H * scale
        # Same text model as stirrup listofer: base TEXT_HEIGHT (0.2), floored at min.
        text_h = resolve_text_height(
            scale,
            text_height=DEFAULT_LONGITUDINAL_TABLE_TEXT_H,
            text_height_factor=DEFAULT_LONGITUDINAL_TABLE_TEXT_FACTOR,
            cell_height=DEFAULT_LONGITUDINAL_TABLE_CELL_H,
            min_text_height=DEFAULT_LONGITUDINAL_TABLE_MIN_TEXT_H,
        )

        views = self._longitudinal_view_rows(self.rebars, view_mode)
        dias = self._used_diameters()
        _, fixed_col_count = self._longitudinal_table_headers(dias)

        width_base = col_widths or DEFAULT_LONGITUDINAL_TABLE_COL_WIDTHS
        scaled_col_widths = [w * scale for w in width_base] + [
            dia_col_width * scale for _ in dias
        ]
        gap = cell_h * VIEW_TABLE_GAP_CELLS
        show_titles = len(views) > 1

        y = y0
        total_rows = 0
        for idx, (label, rebars) in enumerate(views):
            if idx > 0:
                y -= gap
            title = f"LONGITUDINAL LISTOFER — {label.upper()}" if show_titles else None
            y, n = self._draw_one_longitudinal_table_acad(
                rebars,
                x0,
                y,
                scaled_col_widths,
                cell_h,
                text_h,
                dias,
                fixed_col_count,
                scale,
                title=title,
            )
            total_rows += n

        print(f"Drew listofer table with {total_rows} row(s) on layer '{self.layer}'.")
        return total_rows

    def _draw_longitudinal_summary_dxf(
        self,
        msp: Any,
        dias: list[int],
        x0: float,
        y: float,
        col_widths: list[float],
        cell_h: float,
        text_h: float,
        fixed_col_count: int,
        rebars: list[LongitudinalRebarData] | None = None,
    ) -> float:
        """DXF equivalent of :meth:`_draw_longitudinal_summary`.

        Returns the Y coordinate after the summary block (bottom of last row).
        """
        if not dias:
            return y
        length_map, weight_map, grand_weight = self._diameter_summary_maps(
            self.summary_by_size(rebars)
        )
        label_width = sum(col_widths[:fixed_col_count])
        dia_widths = col_widths[fixed_col_count:]

        def draw_label_row(label: str, dia_values: list[str]) -> None:
            nonlocal y
            self._draw_cell_dxf(msp, x0, y, label_width, cell_h)
            self._add_text_center_dxf(
                msp, label, x0 + label_width * 0.5, y - cell_h * 0.5, text_h
            )
            x = x0 + label_width
            for width, value in zip(dia_widths, dia_values):
                self._draw_cell_dxf(msp, x, y, width, cell_h)
                self._add_text_center_dxf(msp, value, x + width * 0.5, y - cell_h * 0.5, text_h)
                x += width
            y -= cell_h

        draw_label_row(
            "TOTAL LENGTH (m)", [f"{length_map.get(d, 0.0):.2f}" for d in dias]
        )
        draw_label_row(
            "TOTAL WEIGHT (Kg)", [f"{weight_map.get(d, 0.0):.2f}" for d in dias]
        )
        draw_label_row(
            "PERCENTAGE (%)",
            [
                f"{(weight_map.get(d, 0.0) / grand_weight * 100.0):.0f}%"
                if grand_weight else "0%"
                for d in dias
            ],
        )

        self._draw_cell_dxf(msp, x0, y, label_width, cell_h)
        self._add_text_center_dxf(
            msp, "GRAND TOTAL (Kg)", x0 + label_width * 0.5, y - cell_h * 0.5, text_h
        )
        dia_total_width = sum(dia_widths)
        self._draw_cell_dxf(msp, x0 + label_width, y, dia_total_width, cell_h)
        self._add_text_center_dxf(
            msp,
            f"{grand_weight:.2f} Kg.",
            x0 + label_width + dia_total_width * 0.5,
            y - cell_h * 0.5,
            text_h,
        )
        return y - cell_h

    def _draw_one_longitudinal_table_dxf(
        self,
        msp: Any,
        rebars: list[LongitudinalRebarData],
        x0: float,
        y0: float,
        scaled_col_widths: list[float],
        cell_h: float,
        text_h: float,
        dias: list[int],
        fixed_col_count: int,
        scale: float,
        title: str | None = None,
    ) -> float:
        """Draw one longitudinal table in DXF; return bottom Y."""
        y = y0
        if title:
            self._add_text_center_dxf(
                msp, title, x0 + sum(scaled_col_widths) * 0.5, y - cell_h * 0.5, text_h,
            )
            y -= cell_h

        headers, _ = self._longitudinal_table_headers(dias)
        x = x0
        for width, header in zip(scaled_col_widths, headers):
            self._draw_cell_dxf(msp, x, y, width, cell_h)
            self._add_text_center_dxf(msp, header, x + width * 0.5, y - cell_h * 0.5, text_h)
            x += width
        y -= cell_h

        for i, rd in enumerate(rebars, 1):
            values = self._longitudinal_row_values(i, rd, dias)
            x = x0
            for col_idx, (width, value) in enumerate(zip(scaled_col_widths, values)):
                self._draw_cell_dxf(msp, x, y, width, cell_h)
                if col_idx == 3:
                    self._insert_shape_block_dxf(msp, rd, x, y, width, cell_h, scale)
                else:
                    self._add_text_center_dxf(
                        msp, value, x + width * 0.5, y - cell_h * 0.5, text_h,
                    )
                x += width
            y -= cell_h

        return self._draw_longitudinal_summary_dxf(
            msp, dias, x0, y, scaled_col_widths, cell_h, text_h, fixed_col_count,
            rebars=rebars,
        )

    def draw_table_to_dxf(
        self,
        insert_point: tuple[float, float] = (0.0, 0.0),
        scale: float = 1.0,
        col_widths: list[float] | None = None,
        dia_col_width: float = DEFAULT_LONGITUDINAL_TABLE_DIA_COL_WIDTH,
        cell_height: float = DEFAULT_LONGITUDINAL_TABLE_CELL_H,
        text_height: float = DEFAULT_LONGITUDINAL_TABLE_TEXT_H,
        min_text_height: float = DEFAULT_LONGITUDINAL_TABLE_MIN_TEXT_H,
        output_path: str | Path | None = None,
        filename: str | None = None,
        open_file: bool = True,
        view_mode: str | None = None,
    ) -> Path:
        """Write the longitudinal-rebar listofer into a DXF file (template copy + write + open).

        *view_mode*: ``\"detailed\"`` | ``\"grouped\"`` | ``\"both\"`` (default both).
        When ``both``, draws the full table then a grouped table below it.
        """
        if not self.rebars:
            raise ValueError("No parsed rebars to draw. Call parse_longitudinal_rebars() first.")

        try:
            import ezdxf
        except ImportError as exc:
            raise ImportError(
                "ezdxf is required for DXF output. Install: pip install ezdxf"
            ) from exc

        readfile_fn = getattr(ezdxf, "readfile", None)
        if readfile_fn is None:
            from ezdxf import filemanagement as _filemanagement

            readfile_fn = _filemanagement.readfile

        new_fn = getattr(ezdxf, "new", None)
        if new_fn is None:
            from ezdxf import filemanagement as _filemanagement

            new_fn = _filemanagement.new

        out_path = self._resolve_output_dxf_path(output_path, filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if self.template_path and self.template_path.exists():
            shutil.copy2(self.template_path, out_path)
            dxf_doc = readfile_fn(str(out_path))
        else:
            dxf_doc = new_fn("R2010")

        msp = dxf_doc.modelspace()
        x0, y0 = insert_point

        views = self._longitudinal_view_rows(self.rebars, view_mode)
        dias = self._used_diameters()
        _, fixed_col_count = self._longitudinal_table_headers(dias)

        cell_h = cell_height * scale
        width_base = col_widths or DEFAULT_LONGITUDINAL_TABLE_COL_WIDTHS
        scaled_col_widths = [w * scale for w in width_base] + [
            dia_col_width * scale for _ in dias
        ]
        # Same as stirrup DXF path: pass explicit base text height (default 0.2).
        text_h = resolve_text_height(
            scale,
            text_height,
            text_height_factor=DEFAULT_LONGITUDINAL_TABLE_TEXT_FACTOR,
            cell_height=cell_height,
            min_text_height=min_text_height,
        )
        gap = cell_h * VIEW_TABLE_GAP_CELLS
        show_titles = len(views) > 1

        y = y0
        for idx, (label, rebars) in enumerate(views):
            if idx > 0:
                y -= gap
            title = f"LONGITUDINAL LISTOFER — {label.upper()}" if show_titles else None
            y = self._draw_one_longitudinal_table_dxf(
                msp,
                rebars,
                x0,
                y,
                scaled_col_widths,
                cell_h,
                text_h,
                dias,
                fixed_col_count,
                scale,
                title=title,
            )

        dxf_doc.saveas(str(out_path))
        if open_file and os.name == "nt":
            try:
                os.startfile(str(out_path))
            except OSError:
                pass

        print(f"DXF listofer saved: {out_path}")
        return out_path

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

    def summary_by_size(
        self,
        rebars: list[LongitudinalRebarData] | None = None,
    ) -> list[dict[str, Any]]:
        """Group complete rebars by diameter and return summary rows.

        Each row: size (mm), total length (m), number (ceil of total_length /
        12 m), unit weight (kg/m), total weight (kg), plus a TOTAL row.

        If *rebars* is given, summarize that list (e.g. a grouped view);
        otherwise use ``self.rebars``.
        """
        source = self.rebars if rebars is None else rebars
        groups: dict[int, float] = defaultdict(float)  # dia -> total length (m)
        for rd in source:
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
