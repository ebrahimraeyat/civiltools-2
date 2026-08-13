"""Story stiffness commands — compute and show story stiffness."""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class StoryStiffnessCommand(BaseCommand):
    command_id = "story_stiffness"
    label = "Story Stiffness"
    menu_path = "Control"
    tooltip = "Compute story stiffness and save to cache"
    table_model = "StoryStiffnessModel"
    dialog_class = "civiltools.gui.dialogs.story_stiffness_dialog.StoryStiffnessDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Story Stiffness", ok=True)


@register
class ShowStoryStiffnessCommand(BaseCommand):
    command_id = "show_story_stiffness"
    label = "Show Story Stiffness"
    menu_path = "Control"
    tooltip = "Display cached story stiffness results"
    table_model = "StoryStiffnessModel"
    dialog_class = "civiltools.gui.dialogs.story_stiffness_dialog.ShowStoryStiffnessDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Show Story Stiffness", ok=True)
