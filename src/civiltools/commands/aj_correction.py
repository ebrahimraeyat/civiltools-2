"""Aj correction command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class AjCorrectionCommand(BaseCommand):
    command_id = "aj_correction"
    label = "Aj Correction"
    menu_path = "Control"
    tooltip = "Calculate and apply Aj accidental eccentricity correction factors"
    dialog_class = "civiltools.gui.dialogs.aj_correction_dialog.AjCorrectionDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Aj Correction", ok=True)
