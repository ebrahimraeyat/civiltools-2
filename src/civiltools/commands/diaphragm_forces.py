"""Diaphragm applied forces command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class DiaphragmForcesCommand(BaseCommand):
    command_id = "diaphragm_forces"
    label = "Diaphragm Forces"
    menu_path = "Control"
    tooltip = "Create separate ETABS files with diaphragm applied forces"
    dialog_class = "civiltools.gui.dialogs.diaphragm_forces_dialog.DiaphragmForcesDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Diaphragm Forces", ok=True)
