"""High-pressure columns check command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class HighPressureColumnsCommand(BaseCommand):
    command_id = "high_pressure_columns"
    label = "High Pressure Columns"
    menu_path = "Control"
    tooltip = "Identify columns with axial pressure exceeding threshold"
    dialog_class = "civiltools.gui.dialogs.high_pressure_columns_dialog.HighPressureColumnsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="High Pressure Columns", ok=True)
