"""Settings command — open project settings dialog."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class SettingsCommand(BaseCommand):
    command_id = "settings"
    label = "Project Settings"
    menu_path = "Edit"
    tooltip = "Configure project seismic parameters, structural systems, and load patterns"
    dialog_class = "civiltools.gui.dialogs.settings_dialog.SettingsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Settings", ok=True)
