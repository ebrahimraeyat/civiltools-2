"""Group identical listofer rows for stirrup / longitudinal schedules.

Pure helpers (no AutoCAD / Qt). Table drawers accept a ``view_mode`` option:

* ``"detailed"`` — one row per parsed item (no merge)
* ``"grouped"`` — merge identical bars into one row
* ``"both"`` — draw both tables (default)

Grouping keys
-------------
Longitudinal
    diameter (mm), total length (cm), shape type (``I`` / ``L`` / ``U``)

Stirrup
    diameter (mm), single cutting length (m), beam width B (cm),
    beam height H (cm)

Aggregation
-----------
* ``count`` / zone count is **summed**
* ``pos`` keeps the **first** item in the group
* derived totals (weight, total length) are recomputed after the merge
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from copy import deepcopy
from typing import Literal, TypeVar

from civiltools.building.extract_stirrups_from_dwg import (
    BeamDimensions,
    StirrupZone,
    calculate_unit_weight,
)
from civiltools.building.longitudinal_rebar_from_dwg import LongitudinalRebarData

ListoferViewMode = Literal["detailed", "grouped", "both"]
DEFAULT_LISTOFER_VIEW_MODE: ListoferViewMode = "both"
VALID_LISTOFER_VIEW_MODES: frozenset[str] = frozenset({"detailed", "grouped", "both"})

T = TypeVar("T")


def normalize_listofer_view_mode(mode: str | None) -> ListoferViewMode:
    """Return a valid view mode; default is ``both``."""
    if mode is None or str(mode).strip() == "":
        return DEFAULT_LISTOFER_VIEW_MODE
    key = str(mode).strip().lower()
    if key not in VALID_LISTOFER_VIEW_MODES:
        allowed = ", ".join(sorted(VALID_LISTOFER_VIEW_MODES))
        raise ValueError(f"Invalid listofer view_mode {mode!r}; expected one of: {allowed}")
    return key  # type: ignore[return-value]


def iter_listofer_views(
    items: Sequence[T],
    group_fn: Callable[[Sequence[T]], list[T]],
    view_mode: str | None = DEFAULT_LISTOFER_VIEW_MODE,
) -> list[tuple[ListoferViewMode, list[T]]]:
    """Expand *view_mode* into one or two ``(label, rows)`` pairs.

    Labels are ``\"detailed\"`` and/or ``\"grouped\"`` so callers can title
    separate tables or DXF outputs.
    """
    mode = normalize_listofer_view_mode(view_mode)
    detailed = list(items)
    if mode == "detailed":
        return [("detailed", detailed)]
    grouped = group_fn(detailed)
    if mode == "grouped":
        return [("grouped", grouped)]
    return [("detailed", detailed), ("grouped", grouped)]


def _round_key(value: float | int | None, ndigits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def longitudinal_group_key(rd: LongitudinalRebarData) -> tuple:
    """Key: diameter + total length + shape (I/L/U)."""
    shape = (rd.shape_type or "I").strip().upper() or "I"
    return (
        int(rd.diameter) if rd.diameter is not None else None,
        _round_key(rd.length, 3),
        shape,
    )


def stirrup_group_key(zone: StirrupZone) -> tuple:
    """Key: diameter + single length + beam B + beam H."""
    beam = zone.beam or BeamDimensions()
    return (
        int(round(float(zone.diameter or 0.0))),
        _round_key(zone.single_length, 3),
        _round_key(beam.width, 3),
        _round_key(beam.height, 3),
    )


def group_longitudinal_rebars(
    rebars: Iterable[LongitudinalRebarData],
) -> list[LongitudinalRebarData]:
    """Merge longitudinal bars that share diameter, length, and shape.

    * ``count`` is summed
    * ``pos`` is taken from the first member
    * incomplete rows (missing diameter/length/count) stay unmerged as-is
    """
    groups: OrderedDict[tuple, LongitudinalRebarData] = OrderedDict()
    passthrough: list[LongitudinalRebarData] = []

    for rd in rebars:
        if rd.diameter is None or rd.length is None or rd.count is None:
            passthrough.append(deepcopy(rd))
            continue
        key = longitudinal_group_key(rd)
        if key not in groups:
            groups[key] = deepcopy(rd)
            continue
        target = groups[key]
        target.count = int(target.count or 0) + int(rd.count or 0)
        # Keep first pos; append raw texts for traceability.
        if rd.raw_texts:
            target.raw_texts = list(target.raw_texts) + list(rd.raw_texts)
        if rd.errors:
            target.errors = list(dict.fromkeys([*target.errors, *rd.errors]))
        if rd.warnings:
            target.warnings = list(dict.fromkeys([*target.warnings, *rd.warnings]))
        target.check_completeness()

    return list(groups.values()) + passthrough


def group_stirrup_zones(zones: Iterable[StirrupZone]) -> list[StirrupZone]:
    """Merge stirrup zones that share diameter, single length, B, and H.

    * ``count`` is summed
    * ``pos`` is taken from the first member
    * ``total_length`` / ``total_weight`` are recomputed from the summed count
    * spacing / zone_length / zone_type keep the first member's values
    """
    groups: OrderedDict[tuple, StirrupZone] = OrderedDict()
    passthrough: list[StirrupZone] = []

    for zone in zones:
        if float(zone.diameter or 0.0) <= 0.0 or float(zone.single_length or 0.0) <= 0.0:
            passthrough.append(deepcopy(zone))
            continue
        key = stirrup_group_key(zone)
        if key not in groups:
            groups[key] = deepcopy(zone)
            continue
        target = groups[key]
        target.count = int(target.count or 0) + int(zone.count or 0)
        target.has_add = bool(target.has_add or zone.has_add)
        target.add_count = int(target.add_count or 0) + int(zone.add_count or 0)
        if zone.raw_texts:
            target.raw_texts = list(target.raw_texts) + list(zone.raw_texts)
        if zone.text_ids:
            target.text_ids = list(target.text_ids) + list(zone.text_ids)
        if zone.errors:
            target.errors = list(dict.fromkeys([*target.errors, *zone.errors]))

        # Recompute quantity fields from summed count.
        target.total_length = round(float(target.count) * float(target.single_length), 3)
        if target.unit_weight <= 0.0 and target.diameter > 0:
            target.unit_weight = calculate_unit_weight(target.diameter)
        target.total_weight = round(target.total_length * float(target.unit_weight), 2)

    return list(groups.values()) + passthrough
