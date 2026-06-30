"""Tools commands — match property, offset."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class MatchPropertyCommand(BaseCommand):
    command_id = "match_property"
    label = "Match Property"
    menu_path = "Tools"
    tooltip = "Copy frame section assignment from source to target frames"
    dialog_class = "civiltools.gui.dialogs.match_property_dialog.MatchPropertyDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Match Property", ok=True)


@register
class OffsetCommand(BaseCommand):
    command_id = "offset"
    label = "Offset Frame"
    menu_path = "Tools"
    tooltip = "Apply offset to selected frames"
    dialog_class = "civiltools.gui.dialogs.offset_dialog.OffsetDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Offset", ok=True)


@register
class CopyElementsCommand(BaseCommand):
    command_id = "copy_elements_between_models"
    label = "Copy Elements Between Models"
    menu_path = "Tools"
    tooltip = "Copy beams/columns from source ETABS model to target ETABS model"
    dialog_class = "civiltools.gui.dialogs.copy_elements_dialog.CopyElementsDialog"
    requires_etabs = False

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Copy Elements", ok=True)


@register
class DistanceCommand(BaseCommand):
    command_id = "distance"
    label = "Distance Between Points"
    menu_path = "Tools"
    tooltip = "Measure distance between two selected points (or the ends of a frame)"
    dialog_class = "civiltools.gui.dialogs.distance_dialog.DistanceDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Distance", ok=True)
