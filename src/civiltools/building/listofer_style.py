"""Shared visual style for listofer (rebar schedule) tables.

Centralizes fonts/row-heights/common column widths/colors so that the
stirrup listofer (:mod:`civiltools.building.extract_stirrups_from_dwg`),
the longitudinal rebar listofer
(:mod:`civiltools.building.longitudinal_rebar_from_dwg`), and future
foundation / slab listofer generators all look consistent.

Import these constants (and :func:`resolve_text_height`) instead of
hard-coding sizes/colors in each table-drawer module. Columns that only
exist in one table type (e.g. stirrup ``Zone``/``Spc`` or longitudinal
``Bend(cm)``) stay defined locally in their own module.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
#  Template (contains the TI / TL / TU / TO / tc shape blocks)
# ---------------------------------------------------------------------------

DEFAULT_LISTOFER_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "dxf" / "templates" / "listofer_template.dxf"
)

# ---------------------------------------------------------------------------
#  Row / text sizing
# ---------------------------------------------------------------------------

CELL_HEIGHT = 8.0
TEXT_HEIGHT = 0.2
MIN_TEXT_HEIGHT = 0.2
TEXT_HEIGHT_FACTOR = 0.35

# ---------------------------------------------------------------------------
#  Common column widths (shared by every listofer table)
# ---------------------------------------------------------------------------

ROW_COL_WIDTH = 10.0
POS_COL_WIDTH = 12.0
DESCRIPTION_COL_WIDTH = 28.0
SHAPE_COL_WIDTH = 20.0
COUNT_COL_WIDTH = 12.0
UNIT_WEIGHT_COL_WIDTH = 14.0
DIA_COL_WIDTH = 14.0

# Gap between detailed and grouped tables when view_mode="both"
# (multiples of the scaled cell height).
VIEW_TABLE_GAP_CELLS = 2.0

# ---------------------------------------------------------------------------
#  Colors (AutoCAD Color Index / ACI)
# ---------------------------------------------------------------------------

ACI_YELLOW = 2
ACI_BLUE = 5
HEADER_FILL_COLOR = ACI_BLUE
SUMMARY_FILL_COLOR = 8


def resolve_text_height(
    scale: float,
    text_height: float | None = None,
    text_height_factor: float = TEXT_HEIGHT_FACTOR,
    cell_height: float = CELL_HEIGHT,
    min_text_height: float = MIN_TEXT_HEIGHT,
) -> float:
    """Compute the effective text height for a table row.

    If *text_height* is given it is scaled directly; otherwise it is derived
    from ``cell_height * scale * text_height_factor``. Either way the result
    is never smaller than *min_text_height*. Shared by every listofer table
    drawer so row text stays visually consistent across tables.
    """
    if text_height is not None:
        return max(text_height * scale, min_text_height)
    return max(cell_height * scale * text_height_factor, min_text_height)
