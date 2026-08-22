"""
Torsion irregularity check — ported from civilTools/py_widget/torsion.py.

Reads diaphragm max/avg drifts, displays via TorsionModel with
3-tier coloring (≤1.2 OK, 1.2–1.4 warning, >1.4 fail).
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class TorsionCheck(BaseCommand):
    command_id = "torsion"
    label = "Torsion Irregularity"
    menu_path = "Control"
    tooltip = "Check diaphragm max/avg drift ratios for torsional irregularity"
    table_model = "TorsionModel"
    dialog_class = "civiltools.gui.dialogs.torsion_dialog.TorsionDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        params = params or {}
        try:
            loadcases = params.get("loadcases")
            if loadcases:
                df = etabs.get_diaphragm_max_over_avg_drifts(loadcases=loadcases)
            else:
                df = etabs.get_diaphragm_max_over_avg_drifts()
        except Exception as exc:
            return CommandResult(
                title="Torsion Check",
                ok=False,
                error=f"Failed to read torsion data: {exc}",
            )

        if df is None or df.empty:
            return CommandResult(
                title="Torsion Check",
                ok=False,
                error="No torsion data available. Run the model first.",
            )

        # Original keeps: Story, Label, OutputCase, Max Drift, Avg Drift, Ratio
        cols = ['Story', 'Label', 'OutputCase', 'Max Drift', 'Avg Drift', 'Ratio']
        available = [c for c in cols if c in df.columns]
        df = df[available]

        max_ratio = df["Ratio"].astype(float).max() if "Ratio" in df.columns else 0
        irregular = max_ratio > 1.2
        summary = (
            f"Max ratio = {max_ratio:.3f}  →  "
            f"{'TORSIONAL IRREGULARITY (> 1.2)' if irregular else 'OK (≤ 1.2)'}"
        )

        return CommandResult(
            title="Torsion Check",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            summary=summary,
            ok=not irregular,
        )
