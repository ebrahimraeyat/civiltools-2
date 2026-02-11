"""Columns 100-30 check command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class Columns10030Command(BaseCommand):
    command_id = "columns_100_30"
    label = "Columns 100-30"
    menu_path = "Control"
    tooltip = "Check columns for 100%-30% orthogonal combination requirement"
    dialog_class = "civiltools.gui.dialogs.columns_100_30_dialog.Columns10030Dialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Columns 100-30", ok=True)
