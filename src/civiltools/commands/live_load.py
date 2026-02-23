"""Live Load Management Command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class LiveLoadCommand(BaseCommand):
    command_id = "live_load"
    label = "Live Load Management"
    menu_path = "Assign"
    tooltip = "Manage and assign live loads to floors and areas"
    dialog_class = "civiltools.gui.dialogs.live_load_dialog.LiveLoadDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Live Load Management", ok=True)
