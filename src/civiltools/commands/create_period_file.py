"""
Create period file — ported from
civilTools/gui_civiltools/gui_create_period_file.py.

Creates the ``*_T.EDB`` period model (beams I=0.5, columns/walls I=1.0 per ACI),
runs it, reads the analytical periods Tx/Ty, and stores them in the project
settings so the earthquake-factor / drift commands can use them.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register
from civiltools.etabs.config import update_setting


@register
class CreatePeriodFileCommand(BaseCommand):
    command_id = "create_period_file"
    label = "Create Period File"
    menu_path = "Control"
    tooltip = "Create the T.EDB period model and compute analytical periods Tx, Ty"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        try:
            t_filename = etabs.get_file_name_without_suffix() + "_T.EDB"
            tx, ty, _ = etabs.get_drift_periods(t_filename=t_filename)
            update_setting(
                etabs,
                {"t_an_x": tx, "t_an_y": ty, "tx_an": tx, "ty_an": ty},
            )
            t_file_path = etabs.get_filepath() / "periods" / t_filename
        except Exception as exc:
            return CommandResult(
                title="Create Period File",
                ok=False,
                error=f"Failed to create period file: {exc}",
            )

        return CommandResult(
            title="Create Period File",
            headers=["Direction", "Analytical Period (s)"],
            rows=[["Tx", round(float(tx), 4)], ["Ty", round(float(ty), 4)]],
            summary=(
                f"Created period file: {t_file_path}  |  "
                f"Tx = {float(tx):.4f} s, Ty = {float(ty):.4f} s"
            ),
            ok=True,
        )
