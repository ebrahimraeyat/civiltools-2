"""Beam J correction command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class BeamJCommand(BaseCommand):
    command_id = "beam_j"
    label = "Beam J Correction"
    menu_path = "Assign"
    tooltip = "Iteratively correct beam torsion stiffness factor (J)"
    dialog_class = "civiltools.gui.dialogs.beam_j_dialog.BeamJDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Beam J", ok=True)
