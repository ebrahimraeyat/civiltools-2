"""
Story drift check — ported from civilTools/py_widget/drift.py.

Reads drifts from ETABS, compares to allowable limits.
Uses DriftModel for color-coded display.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from civiltools.commands.base import BaseCommand, CommandParam, CommandResult
from civiltools.commands import register


@register
class DriftCheck(BaseCommand):
    command_id = "drift"
    label = "Story Drift"
    menu_path = "Control"
    tooltip = "Check story drifts against allowable limits"
    table_model = "DriftModel"
    dialog_class = "civiltools.gui.dialogs.drift_dialog.DriftDialog"

    @classmethod
    def parameters(cls) -> list[CommandParam]:
        return [
            CommandParam("no_story", "Number of stories", "int", 5,
                         tooltip="Total number of stories (≤5 → limit 0.025, >5 → 0.02)"),
            CommandParam("cdx", "Cd (X direction)", "float", 4.5,
                         tooltip="Deflection amplification factor in X"),
            CommandParam("cdy", "Cd (Y direction)", "float", 4.5,
                         tooltip="Deflection amplification factor in Y"),
        ]

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        params = params or {}
        no_story = int(params.get("no_story", 5))
        cdx = float(params.get("cdx", 4.5))
        cdy = float(params.get("cdy", 4.5))

        try:
            result = etabs.get_drifts(no_story, cdx, cdy)
        except Exception as exc:
            return CommandResult(
                title="Drift Check",
                ok=False,
                error=f"Failed to read drift data: {exc}",
            )

        if result is None:
            return CommandResult(
                title="Drift Check",
                ok=False,
                error="No drift data available. Check diaphragm assignment.",
            )

        data, fields = result
        if data is None:
            return CommandResult(
                title="Drift Check",
                ok=False,
                error="Could not compute drifts (check Cd values).",
            )

        # Build DataFrame exactly as the original drift.py does
        df = pd.DataFrame(data, columns=fields)

        # Keep columns matching DriftModel expectations
        keep = ['Story', 'OutputCase', 'Max Drift', 'Avg Drift', 'Allowable Drift']
        available = [c for c in keep if c in df.columns]
        df_display = df[available].copy()

        # Check if any drift exceeds allowable
        all_ok = True
        if 'Max Drift' in df_display.columns and 'Allowable Drift' in df_display.columns:
            try:
                max_drifts = pd.to_numeric(df_display['Max Drift'], errors='coerce')
                allowable = pd.to_numeric(df_display['Allowable Drift'], errors='coerce')
                if (max_drifts > allowable).any():
                    all_ok = False
            except Exception:
                pass

        summary = (
            f"Stories={no_story}, Cdx={cdx}, Cdy={cdy}  →  "
            f"{'ALL DRIFTS OK' if all_ok else 'DRIFT EXCEEDS LIMIT'}"
        )

        return CommandResult(
            title="Drift Check",
            headers=list(df_display.columns),
            rows=df_display.values.tolist(),
            dataframe=df_display,
            summary=summary,
            ok=all_ok,
        )
