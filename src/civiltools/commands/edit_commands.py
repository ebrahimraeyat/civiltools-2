"""Edit commands — frame section properties."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class EditFrameSectionsCommand(BaseCommand):
    command_id = "edit_frame_sections"
    label = "Edit Frame Sections"
    menu_path = "Edit"
    tooltip = "Change beam/column section concrete strength (fc')"
    dialog_class = "civiltools.gui.dialogs.edit_frame_sections_dialog.EditFrameSectionsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Edit Sections", ok=True)
