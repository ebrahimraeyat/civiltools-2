"""Extract rebar information from AutoCAD drawings via COM.

Supported text formats
---------------------
**Main rebars** (two separate text objects close to each other):
    Count / Size / Spacing :  ``4∅20@25``
    Length                 :  ``L=1200cm``

**Additional rebars** (single text):
    ``1∅25  L=440``

The diameter symbol can be any of: ``%%c  %%C  ∅  Ø  ⌀  ø  φ  Φ``
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# ── Fix pywin32 DLL loading ────────────────────────────────────────
# pywin32 keeps its DLLs (pywintypes*.dll, pythoncom*.dll) in a
# separate directory that may not be on PATH when running from a
# conda env.  Add it before importing.
_pywin32_system32 = os.path.join(
    os.path.dirname(os.path.dirname(os.__file__)),
    "Lib", "site-packages", "pywin32_system32",
)
if os.path.isdir(_pywin32_system32):
    os.add_dll_directory(_pywin32_system32)
    if _pywin32_system32 not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _pywin32_system32 + os.pathsep + os.environ.get("PATH", "")

import win32com.client  # noqa: E402
import pythoncom        # noqa: E402

# ---------------------------------------------------------------------------
#  Regex helpers
# ---------------------------------------------------------------------------

# All AutoCAD representations of the diameter symbol
_DIA = r'(?:%%[cC]|[∅Ø⌀øφΦ~T])'

# Combined main rebar in one text:  4∅20@25 … L=1200cm
RE_COMBINED_MAIN = re.compile(
    rf'(\d+)\s*{_DIA}\s*(\d+)\s*@\s*(\d+).*?L\s*=\s*(\d+)\s*(cm|m)?',
    re.IGNORECASE | re.DOTALL,
)

# Combined additional rebar in one text:  1∅25  L=440  (no @spacing)
RE_COMBINED_ADDITIONAL = re.compile(
    rf'(\d+)\s*{_DIA}\s*(\d+)\s+L\s*=\s*(\d+)\s*(cm|m)?',
    re.IGNORECASE,
)

# Standalone count / size / spacing:  4∅20@25
RE_STANDALONE_MAIN = re.compile(
    rf'(\d+)\s*{_DIA}\s*(\d+)\s*@\s*(\d+)',
    re.IGNORECASE,
)

# Standalone count / size only:  3∅28
RE_STANDALONE_COUNT = re.compile(
    rf'^\s*(\d+)\s*{_DIA}\s*(\d+)\s*$',
    re.IGNORECASE,
)

# Standalone length text:  L=1200cm  or  L=1200
RE_STANDALONE_LENGTH = re.compile(
    r'^\s*L\s*=\s*(\d+)\s*(cm|m)?\s*$',
    re.IGNORECASE,
)

STEEL_DENSITY = 7850.0  # kg/m³


def _length_cm(value: int, unit: str | None) -> int:
    """Convert a parsed length *value* with *unit* to centimetres."""
    if unit and unit.lower() == 'm':
        return value * 100
    return value  # default = cm


def _spoint(x: float, y: float):
    """Create an AutoCAD 2-D point VARIANT."""
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y))


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class RebarTextInfo:
    """One Text / MText entity read from AutoCAD."""

    obj_id: int
    text_string: str
    insertion_point: tuple[float, float, float]
    rotation: float = 0.0
    text_height: float = 1.0


@dataclass
class RebarData:
    """One logical rebar entry (may combine multiple text objects)."""

    count: int | None = None
    diameter: int | None = None   # mm
    spacing: int | None = None    # cm  (main rebars only)
    length: int | None = None     # cm
    rebar_type: str = "unknown"   # 'main' | 'additional' | 'unknown'
    text_ids: list[int] = field(default_factory=list)
    raw_texts: list[str] = field(default_factory=list)
    complete: bool = False
    errors: list[str] = field(default_factory=list)

    def check_completeness(self) -> bool:
        self.errors = []
        if self.count is None:
            self.errors.append("count")
        if self.diameter is None:
            self.errors.append("diameter")
        if self.length is None:
            self.errors.append("length")
        self.complete = len(self.errors) == 0
        return self.complete

    def weight_kg(self) -> float | None:
        """Total weight of this bar group (kg), or *None* if incomplete."""
        if self.count is None or self.diameter is None or self.length is None:
            return None
        d_m = self.diameter / 1000.0
        l_m = self.length / 100.0
        area = math.pi / 4.0 * d_m**2
        return round(self.count * area * l_m * STEEL_DENSITY, 2)


# ---------------------------------------------------------------------------
#  Main engine
# ---------------------------------------------------------------------------

class RebarFromDwg:
    """Read and parse rebar annotation text from an open AutoCAD drawing."""

    PROXIMITY_FACTOR: int = 20  # max distance = text_height × factor

    def __init__(self) -> None:
        self.acad: Any = win32com.client.Dispatch("AutoCAD.Application")
        self.acad.Visible = True
        self.doc: Any = self.acad.ActiveDocument
        self.text_objects: list[RebarTextInfo] = []
        self.rebar_data: list[RebarData] = []

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
    #  Read text entities
    # ------------------------------------------------------------------
    def _read_text_obj(self, obj: Any) -> RebarTextInfo | None:
        """Convert one COM text entity to a *RebarTextInfo*, or *None*."""
        if obj.ObjectName not in ("AcDbText", "AcDbMText"):
            return None
        raw = obj.TextString
        text = self.clean_mtext(raw) if obj.ObjectName == "AcDbMText" else raw
        ip = obj.InsertionPoint
        return RebarTextInfo(
            obj_id=obj.ObjectID,
            text_string=text,
            insertion_point=(ip[0], ip[1], ip[2] if len(ip) > 2 else 0.0),
            rotation=getattr(obj, 'Rotation', 0),
            text_height=getattr(obj, 'Height', 1.0),
        )

    def get_text_objects_from_selection(self) -> list[RebarTextInfo]:
        """Prompt the user to select objects; keep only Text / MText."""
        texts: list[RebarTextInfo] = []
        ss_name = f"_RebarSel_{int(time.time())}"
        try:
            ss_col = self.doc.SelectionSets
            for i in range(ss_col.Count):
                if ss_col.Item(i).Name == ss_name:
                    ss_col.Item(i).Delete()
                    break
            ss = ss_col.Add(ss_name)
            print("Select rebar texts in AutoCAD and press Enter …")
            ss.SelectOnScreen()
            for i in range(ss.Count):
                info = self._read_text_obj(ss.Item(i))
                if info:
                    texts.append(info)
            ss.Delete()
        except Exception as exc:
            print(f"Selection error: {exc}")
            try:
                self.doc.SelectionSets.Item(ss_name).Delete()
            except Exception:
                pass
        self.text_objects = texts
        return texts

    def get_all_text_objects(self) -> list[RebarTextInfo]:
        """Get ALL Text & MText from model space."""
        texts: list[RebarTextInfo] = []
        ss_name = f"_RebarAll_{int(time.time())}"
        try:
            ss_col = self.doc.SelectionSets
            for i in range(ss_col.Count):
                if ss_col.Item(i).Name == ss_name:
                    ss_col.Item(i).Delete()
                    break
            ss = ss_col.Add(ss_name)
            ft = win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_I2, (-4, 0, 0, -4))
            fv = win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_VARIANT,
                ("<OR", "TEXT", "MTEXT", "OR>"))
            ss.Select(5, None, None, ft, fv)  # 5 = acSelectionSetAll
            for i in range(ss.Count):
                info = self._read_text_obj(ss.Item(i))
                if info:
                    texts.append(info)
            ss.Delete()
        except Exception as exc:
            print(f"Select-all error: {exc}")
            try:
                self.doc.SelectionSets.Item(ss_name).Delete()
            except Exception:
                pass
        self.text_objects = texts
        return texts

    # ------------------------------------------------------------------
    #  Parse → RebarData
    # ------------------------------------------------------------------
    @staticmethod
    def _dist(p1: tuple, p2: tuple) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def parse_rebars(self) -> list[RebarData]:
        """Classify collected text objects into RebarData entries."""
        self.rebar_data = []
        partial_mains: list[tuple[RebarTextInfo, int, int, int]] = []
        partial_counts: list[tuple[RebarTextInfo, int, int]] = []  # standalone N∅D (no @)
        lengths: list[tuple[RebarTextInfo, int]] = []
        used_ids: set[int] = set()

        for ti in self.text_objects:
            txt = ti.text_string.strip()

            # 1) Combined main  (N∅D@S … L=…)
            m = RE_COMBINED_MAIN.search(txt)
            if m:
                rd = RebarData(
                    count=int(m.group(1)),
                    diameter=int(m.group(2)),
                    spacing=int(m.group(3)),
                    length=_length_cm(int(m.group(4)), m.group(5)),
                    rebar_type='main',
                    text_ids=[ti.obj_id],
                    raw_texts=[txt],
                )
                rd.check_completeness()
                self.rebar_data.append(rd)
                used_ids.add(ti.obj_id)
                continue

            # 2) Combined additional  (N∅D  L=…, no @)
            m = RE_COMBINED_ADDITIONAL.search(txt)
            if m:
                rd = RebarData(
                    count=int(m.group(1)),
                    diameter=int(m.group(2)),
                    length=_length_cm(int(m.group(3)), m.group(4)),
                    rebar_type='additional',
                    text_ids=[ti.obj_id],
                    raw_texts=[txt],
                )
                rd.check_completeness()
                self.rebar_data.append(rd)
                used_ids.add(ti.obj_id)
                continue

            # 3) Standalone main count/size/spacing  (N∅D@S)
            m = RE_STANDALONE_MAIN.search(txt)
            if m:
                partial_mains.append(
                    (ti, int(m.group(1)), int(m.group(2)), int(m.group(3))))
                used_ids.add(ti.obj_id)
                continue

            # 4) Standalone length  (L=…)
            m = RE_STANDALONE_LENGTH.search(txt)
            if m:
                lengths.append((ti, _length_cm(int(m.group(1)), m.group(2))))
                used_ids.add(ti.obj_id)
                continue

            # 5) Standalone count/size only  (N∅D, no @, no L=)
            m = RE_STANDALONE_COUNT.search(txt)
            if m:
                partial_counts.append(
                    (ti, int(m.group(1)), int(m.group(2))))
                used_ids.add(ti.obj_id)
                continue

            # 6) Not a rebar text → skip

        # ---- Match partial mains (N∅D@S) with nearest unused length ----
        used_length_ids: set[int] = set()
        for ti, cnt, dia, spc in partial_mains:
            rd = RebarData(
                count=cnt, diameter=dia, spacing=spc,
                rebar_type='main',
                text_ids=[ti.obj_id],
                raw_texts=[ti.text_string],
            )
            best_dist = float('inf')
            best_idx = -1
            max_d = ti.text_height * self.PROXIMITY_FACTOR
            for idx, (li, lv) in enumerate(lengths):
                if li.obj_id in used_length_ids:
                    continue
                d = self._dist(ti.insertion_point, li.insertion_point)
                if d < best_dist and d <= max_d:
                    best_dist = d
                    best_idx = idx
            if best_idx >= 0:
                li, lv = lengths[best_idx]
                rd.length = lv
                rd.text_ids.append(li.obj_id)
                rd.raw_texts.append(li.text_string)
                used_length_ids.add(li.obj_id)
            rd.check_completeness()
            self.rebar_data.append(rd)

        # ---- Match partial counts (N∅D) with nearest unused length ----
        for ti, cnt, dia in partial_counts:
            rd = RebarData(
                count=cnt, diameter=dia,
                rebar_type='additional',
                text_ids=[ti.obj_id],
                raw_texts=[ti.text_string],
            )
            best_dist = float('inf')
            best_idx = -1
            max_d = ti.text_height * self.PROXIMITY_FACTOR
            for idx, (li, lv) in enumerate(lengths):
                if li.obj_id in used_length_ids:
                    continue
                d = self._dist(ti.insertion_point, li.insertion_point)
                if d < best_dist and d <= max_d:
                    best_dist = d
                    best_idx = idx
            if best_idx >= 0:
                li, lv = lengths[best_idx]
                rd.length = lv
                rd.text_ids.append(li.obj_id)
                rd.raw_texts.append(li.text_string)
                used_length_ids.add(li.obj_id)
            rd.check_completeness()
            self.rebar_data.append(rd)

        # ---- Orphan length texts → partial entries ----
        for li, lv in lengths:
            if li.obj_id not in used_length_ids:
                rd = RebarData(
                    length=lv,
                    rebar_type='unknown',
                    text_ids=[li.obj_id],
                    raw_texts=[li.text_string],
                )
                rd.check_completeness()
                self.rebar_data.append(rd)

        return self.rebar_data

    # ------------------------------------------------------------------
    #  Post-processing helpers
    # ------------------------------------------------------------------
    def get_incomplete_ids(self) -> list[int]:
        """ObjectIDs of text entities belonging to incomplete rebars."""
        ids: list[int] = []
        for rd in self.rebar_data:
            if not rd.complete:
                ids.extend(rd.text_ids)
        return ids

    def highlight_incomplete(self) -> int:
        """Highlight incomplete rebar texts and zoom to them in AutoCAD.

        Returns the number of highlighted items.
        """
        ids = self.get_incomplete_ids()
        if not ids:
            return 0

        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')

        for obj_id in ids:
            try:
                obj = self.doc.ObjectIdToObject(obj_id)
                obj.Highlight(True)
                mn, mx = obj.GetBoundingBox()
                min_x = min(min_x, mn[0])
                min_y = min(min_y, mn[1])
                max_x = max(max_x, mx[0])
                max_y = max(max_y, mx[1])
            except Exception:
                pass

        # Zoom to the bounding box with padding
        if min_x < float('inf'):
            dx = max(max_x - min_x, 1) * 0.15
            dy = max(max_y - min_y, 1) * 0.15
            try:
                self.acad.ZoomWindow(
                    _spoint(min_x - dx, min_y - dy),
                    _spoint(max_x + dx, max_y + dy),
                )
            except Exception:
                try:
                    self.doc.SendCommand("ZOOM E\n")
                except Exception:
                    pass

        return len(ids)

    def summary(self) -> dict[str, int]:
        total = len(self.rebar_data)
        ok = sum(1 for r in self.rebar_data if r.complete)
        return {
            'total': total,
            'complete': ok,
            'incomplete': total - ok,
            'main': sum(1 for r in self.rebar_data if r.rebar_type == 'main'),
            'additional': sum(1 for r in self.rebar_data
                              if r.rebar_type == 'additional'),
        }

    STANDARD_BAR_LENGTH_M = 12.0  # standard rebar length in metres

    def summary_by_size(self) -> list[dict[str, Any]]:
        """Group complete rebars by diameter and return summary rows.

        Each row: size (mm), total_length (m), number (ceil of
        total_length / 12 m), weight (kg), unit_weight (kg/m).
        """
        from collections import defaultdict

        groups: dict[int, float] = defaultdict(float)  # dia → total length in m
        for rd in self.rebar_data:
            if rd.diameter is None or rd.count is None or rd.length is None:
                continue
            l_m = (rd.count * rd.length) / 100.0  # cm → m
            groups[rd.diameter] += l_m

        rows: list[dict[str, Any]] = []
        grand_length = 0.0
        grand_number = 0
        grand_weight = 0.0

        for dia in sorted(groups):
            total_l = groups[dia]
            d_m = dia / 1000.0
            area = math.pi / 4.0 * d_m ** 2
            unit_w = area * STEEL_DENSITY           # kg per metre
            weight = round(total_l * unit_w, 2)
            n_bars = math.ceil(total_l / self.STANDARD_BAR_LENGTH_M)

            grand_length += total_l
            grand_number += n_bars
            grand_weight += weight

            rows.append({
                'Size (mm)': dia,
                'Total Length (m)': round(total_l, 2),
                'Number (12 m bars)': n_bars,
                'Unit Weight (kg/m)': round(unit_w, 3),
                'Total Weight (kg)': weight,
            })

        # Grand total row
        if rows:
            rows.append({
                'Size (mm)': 'TOTAL',
                'Total Length (m)': round(grand_length, 2),
                'Number (12 m bars)': grand_number,
                'Unit Weight (kg/m)': '',
                'Total Weight (kg)': round(grand_weight, 2),
            })

        return rows

def calculate_hook_parameters(diameter_mm: float, hook_type: str) -> tuple[float, float]:
    """
    Calculate the minimum internal bend diameter and straight extension (tail) length
    for 90° and 135° hooks in rebar detailing, based on standard code rules
    (covering bar diameters from 10 mm to 90 mm).

    Args:
        diameter_mm (float): Nominal diameter of the rebar (mm). Must be between 10 and 90.
        hook_type (str): Type of hook, either '90' or '135'.

    Returns:
        tuple[float, float]: (internal_bend_diameter_mm, straight_extension_mm)
            - internal_bend_diameter_mm: Minimum internal diameter of the bend.
            - straight_extension_mm: Straight length beyond the end of the bend
              (also known as the hook tail length).

    Raises:
        ValueError: If the diameter is outside the supported range (10-90 mm)
                    or if hook_type is invalid.
    """
    db = diameter_mm
    if not (10 <= db <= 90):
        raise ValueError("Rebar diameter must be between 10 and 90 mm.")

    if hook_type == '90':
        if db <= 16:   # Range: 10 to 16 mm
            bend_diameter = 4 * db
            # Maximum of 75 mm or 6*db (minimum code requirement)
            straight_length = max(75, 6 * db)
        else:          # Range: greater than 16 mm up to 90 mm
            bend_diameter = 6 * db
            straight_length = 12 * db

    elif hook_type == '135':
        if db <= 16:   # Range: 10 to 16 mm
            bend_diameter = 4 * db
            # Maximum of 75 mm or 6*db (minimum code requirement)
        else:          # Range: greater than 16 mm up to 90 mm
            bend_diameter = 6 * db
        straight_length = max(75, 6 * db)
    elif hook_type == '180':
        if db <= 16:   # Range: 10 to 16 mm
            bend_diameter = 4 * db
            # Maximum of 75 mm or 6*db (minimum code requirement)
        else:          # Range: greater than 16 mm up to 90 mm
            bend_diameter = 6 * db
        straight_length = max(65, 4 * db)
    else:
        raise ValueError("Hook type must be '90', '135' or '180'.")

    return bend_diameter, straight_length

def calculate_length_with_hooks(diameter_mm: float, hook_type: str) -> float:
    """
    Calculate the total length of a rebar including hooks.

    Args:
        diameter_mm (float): The nominal diameter of the rebar in millimeters.
        hook_type (str): Type of hook, either '90', '135', or '180'.

    Returns:
        float: Total length of the rebar including hooks in centimeters.
    """
    bend_diameter, straight_length = calculate_hook_parameters(diameter_mm, hook_type)
    # Convert straight length from mm to cm
    straight_length_cm = straight_length / 10.0
    # Total length is base length plus two hooks (one at each end)
    mid_bend_radus_cm = (bend_diameter + diameter_mm) / 20.0  # Convert diameter to center radius in cm
    total_length_cm = mid_bend_radus_cm + straight_length_cm
    return total_length_cm
