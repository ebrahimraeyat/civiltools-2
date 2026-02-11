"""Explode seismic load patterns command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class ExplodeSeismicCommand(BaseCommand):
    command_id = "explode_seismic"
    label = "Explode Seismic"
    menu_path = "Define"
    tooltip = "Expand seismic load patterns in ETABS model"
    dialog_class = "civiltools.gui.dialogs.explode_seismic_dialog.ExplodeSeismicDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Explode Seismic", ok=True)
