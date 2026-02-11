"""Shear wall commands — 25% file creation."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class Create25PercentCommand(BaseCommand):
    command_id = "create_25percent"
    label = "Create 25% File"
    menu_path = "Shear Wall"
    tooltip = "Create ETABS file with 25% shear wall stiffness for PMM"
    dialog_class = "civiltools.gui.dialogs.create_25percent_dialog.Create25PercentDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="25% File", ok=True)
