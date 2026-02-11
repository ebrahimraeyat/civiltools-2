"""Assign commands — end-length offsets, modifiers, Ev, wall loads."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class AssignsCommand(BaseCommand):
    command_id = "assigns"
    label = "Assignments"
    menu_path = "Assign"
    tooltip = "Apply frame/area assignments: offsets, diaphragm, etc."
    dialog_class = "civiltools.gui.dialogs.assigns_dialog.AssignsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Assignments", ok=True)


@register
class AssignModifiersCommand(BaseCommand):
    command_id = "assign_modifiers"
    label = "Property Modifiers"
    menu_path = "Assign"
    tooltip = "Assign property modifiers to beams, columns, slabs, walls"
    dialog_class = "civiltools.gui.dialogs.assign_modifiers_dialog.AssignModifiersDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Property Modifiers", ok=True)


@register
class AssignEvCommand(BaseCommand):
    command_id = "assign_ev"
    label = "Assign Ev"
    menu_path = "Assign"
    tooltip = "Assign vertical earthquake component to frames"
    dialog_class = "civiltools.gui.dialogs.assign_ev_dialog.AssignEvDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Assign Ev", ok=True)


@register
class WallLoadCommand(BaseCommand):
    command_id = "wall_load"
    label = "Wall Load on Frames"
    menu_path = "Assign"
    tooltip = "Assign gravity wall loads to self and above beams"
    dialog_class = "civiltools.gui.dialogs.wall_load_dialog.WallLoadDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Wall Load", ok=True)
