"""Story shear forces command."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class StoryForcesCommand(BaseCommand):
    command_id = "story_forces"
    label = "Story Shear Forces"
    menu_path = "Control"
    tooltip = "Show story shear forces with percentage distribution"
    dialog_class = "civiltools.gui.dialogs.story_forces_dialog.StoryForcesDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Story Forces", ok=True)
