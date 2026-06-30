"""
Mass irregularity check — ported from
civilTools/gui_civiltools/gui_irregularity_of_mass.py.

Reads per-story mass and flags any story whose mass exceeds 1.5× the mass
of the story immediately below or above it (vertical mass irregularity per
Standard 2800).  Single ETABS read → colored table, no user input.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class IrregularityOfMassCheck(BaseCommand):
    command_id = "irregularity_of_mass"
    label = "Mass Irregularity"
    menu_path = "Control"
    tooltip = "Check vertical mass irregularity (story mass vs 1.5× adjacent stories)"
    table_model = "IrregularityOfMassModel"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        try:
            data, headers = etabs.get_irregularity_of_mass()
        except Exception as exc:
            return CommandResult(
                title="Mass Irregularity",
                ok=False,
                error=f"Failed to read story mass data: {exc}",
            )

        if not data:
            return CommandResult(
                title="Mass Irregularity",
                ok=False,
                error="No story mass data available. Run the model first.",
            )

        df = pd.DataFrame(data, columns=list(headers))

        # Irregular when story mass exceeds 1.5× the below or above story mass.
        # (For the top/bottom stories the limits equal the mass itself, so they
        #  never raise a false positive.)
        mass = df["Mass (tonf)"].astype(float)
        below = df["1.5 * Below"].astype(float)
        above = df["1.5 * Above"].astype(float)
        irregular = bool(((mass > below) | (mass > above)).any())

        summary = (
            "MASS IRREGULARITY found (story mass > 1.5× adjacent story)"
            if irregular
            else "OK — no vertical mass irregularity"
        )

        return CommandResult(
            title="Mass Irregularity",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            summary=summary,
            ok=not irregular,
        )
