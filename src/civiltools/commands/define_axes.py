"""Define Axes — import DXF / AutoCAD, detect columns, create grid axes."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class DefineAxesCommand(BaseCommand):
    command_id = "define_axes"
    label = "Grid Lines from DXF"
    menu_path = "Define"
    tooltip = "Import DXF / AutoCAD selection → detect columns → create grid axes → export to ETABS"
    dialog_class = "civiltools.gui.dialogs.define_axes_dialog.DefineAxesDialog"
    requires_etabs = False  # can work standalone (just preview), ETABS needed only for export

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Define Axes", ok=True)
