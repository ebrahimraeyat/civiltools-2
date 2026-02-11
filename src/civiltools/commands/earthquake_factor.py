"""Earthquake factor command — calculate and apply seismic coefficients."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class EarthquakeFactorCommand(BaseCommand):
    command_id = "earthquake_factor"
    label = "Earthquake Factor"
    menu_path = "Assign"
    tooltip = "Calculate seismic C and K factors and apply to ETABS load patterns"
    dialog_class = "civiltools.gui.dialogs.earthquake_factor_dialog.EarthquakeFactorDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Earthquake Factor", ok=True)
