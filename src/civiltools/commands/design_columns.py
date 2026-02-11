"""
Design columns (PMM) — reads concrete column PMM interaction ratios.

This is the "run concrete design and show PMM ratios" command, NOT the
"columns control" check (which compares adjacent-story column sections).
Uses ColumnsPMMModel for color-coded display.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class DesignColumnsCheck(BaseCommand):
    command_id = "design_columns"
    label = "Design Columns (PMM)"
    menu_path = "Control"
    tooltip = "Concrete column P-M-M interaction ratios"
    table_model = "ColumnsPMMModel"
    dialog_class = ""  # No dialog — just fetch table from ETABS

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        try:
            df = etabs.design.get_concrete_columns_pmm_table()
        except Exception as exc:
            return CommandResult(
                title="Design Columns (PMM)",
                ok=False,
                error=f"Failed to read column design data: {exc}",
            )

        if df is None or (hasattr(df, "empty") and df.empty):
            return CommandResult(
                title="Design Columns (PMM)",
                ok=False,
                error="No column design data. Run concrete design first.",
            )

        # Check max PMM ratio
        pmm_max = 0.0
        if "PMMRatio" in df.columns:
            try:
                pmm_max = df["PMMRatio"].astype(float).max()
            except (ValueError, TypeError):
                pass

        ok = pmm_max <= 1.0
        summary = (
            f"Max PMM ratio = {pmm_max:.3f}  →  "
            f"{'ALL COLUMNS OK' if ok else 'COLUMN OVERSTRESSED (PMM > 1.0)'}"
        )

        return CommandResult(
            title="Design Columns (PMM)",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            summary=summary,
            ok=ok,
        )
