"""Weakness check commands — get and show beam/column weakness."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class GetWeaknessCommand(BaseCommand):
    command_id = "get_weakness"
    label = "Get Weakness"
    menu_path = "Control"
    tooltip = "Compute beam/column weakness structure and save to cache"
    dialog_class = "civiltools.gui.dialogs.weakness_dialog.WeaknessDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Get Weakness", ok=True)


@register
class ShowWeaknessCommand(BaseCommand):
    command_id = "show_weakness"
    label = "Show Weakness"
    menu_path = "Control"
    tooltip = "Show cached weakness analysis results"
    dialog_class = "civiltools.gui.dialogs.weakness_dialog.ShowWeaknessDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Show Weakness", ok=True)
