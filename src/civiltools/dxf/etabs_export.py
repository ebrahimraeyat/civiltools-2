"""
Export grid axes and columns to an ETABS model.

Operates on the ``GridAxes`` / ``DxfRect`` objects produced by the
column-detector pipeline and pushes them into a live ETABS COM session.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from civiltools.dxf.dxf_reader import DxfRect
from civiltools.dxf.column_detector import GridAxes


# ═══════════════════════════════════════════════════════════════════════════
# Grid lines
# ═══════════════════════════════════════════════════════════════════════════

def export_axes_to_etabs(
    etabs: Any,
    axes: GridAxes,
    *,
    grid_system_name: str = "G1",
) -> str:
    """Create / update an ETABS Cartesian grid system from *axes*.

    Returns the grid-system name that was used.
    """
    sap = etabs.SapModel
    etabs.set_current_unit("N", "mm")
    etabs.unlock_model()

    # Find (or create) the grid system
    grids = sap.GridSys.GetNameList()[1]
    g1: str | None = None
    if grids:
        for g in grids:
            if sap.GridSys.GetGridSysType(g)[0] == "Cartesian":
                g1 = g
                break
    if g1 is None:
        sap.GridSys.SetGridSys(grid_system_name, 0, 0, 0)
        g1 = grid_system_name

    # Build the flat data list expected by etabs_api.database.add_grid_lines
    data: list[str] = []
    for gl in axes.x_lines:
        data.extend([
            g1, "X (Cartesian)", gl.label,
            str(gl.coordinate), "End", "Yes",
        ])
    for gl in axes.y_lines:
        data.extend([
            g1, "Y (Cartesian)", gl.label,
            str(gl.coordinate), "Start", "Yes",
        ])

    etabs.database.add_grid_lines(data=data)
    return g1


# ═══════════════════════════════════════════════════════════════════════════
# Columns
# ═══════════════════════════════════════════════════════════════════════════

def export_columns_to_etabs(
    etabs: Any,
    columns: Sequence[DxfRect],
    level_names: list[str],
    all_level_names: list[str],
) -> int:
    """Add frame objects (columns) to ETABS at the selected story levels.

    Parameters
    ----------
    etabs : EtabsModel
    columns : detected column rectangles (centres in mm)
    level_names : stories where columns should be created (checked by user)
    all_level_names : full story list (top → base), so we can look up
        the story *below* each selected level.

    Returns
    -------
    int — number of column objects created.
    """
    sap = etabs.SapModel
    etabs.set_current_unit("N", "mm")
    etabs.unlock_model()

    n = 0
    for col in columns:
        x, y = col.center.x, col.center.y
        rot = col.rotation

        for level_name in level_names:
            idx = all_level_names.index(level_name)
            if idx + 1 >= len(all_level_names):
                continue
            next_level_name = all_level_names[idx + 1]

            level_elev = sap.Story.GetElevation(level_name)[0]
            next_elev = sap.Story.GetElevation(next_level_name)[0]

            name = sap.FrameObj.AddByCoord(
                x, y, level_elev, x, y, next_elev,
            )[0]
            if name is None:
                continue

            sap.FrameObj.SetLocalAxes(name, rot)

            # Centre insertion point
            ins = sap.FrameObj.GetInsertionPoint(name)
            ins_list = list(ins)
            ins_list[0] = 10  # centred
            sap.FrameObj.SetInsertionPoint(name, *ins_list[:-1])

            n += 1

    return n
