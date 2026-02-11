"""Extract rebar data from AutoCAD drawings — command registration."""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class ExtractRebarsCommand(BaseCommand):
    command_id = "extract_rebars"
    label = "Extract Rebars from DWG"
    menu_path = "Tools"
    tooltip = "Read rebar annotations (Text/MText) from AutoCAD and list them"
    table_model = "RebarModel"
    dialog_class = "civiltools.gui.dialogs.extract_rebars_dialog.ExtractRebarsDialog"
    requires_etabs = False          # AutoCAD-only — no ETABS needed

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Extract Rebars", ok=True)
