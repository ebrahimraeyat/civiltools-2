"""Beam deflection control command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class BeamDeflectionCommand(BaseCommand):
    command_id = "beam_deflection"
    label = "Beam Deflection"
    menu_path = "Control"
    tooltip = "Check beam deflection limits per design code"
    dialog_class = "civiltools.gui.dialogs.beam_deflection_dialog.BeamDeflectionDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Beam Deflection", ok=True)
