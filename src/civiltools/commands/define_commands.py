"""Define commands — load combos, spectral, section cuts."""

from __future__ import annotations
from typing import Any
from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class CreateLoadCombinationsCommand(BaseCommand):
    command_id = "create_load_combinations"
    label = "Load Combinations"
    menu_path = "Define"
    tooltip = "Generate concrete/steel load combinations"
    dialog_class = "civiltools.gui.dialogs.create_load_combinations_dialog.CreateLoadCombinationsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Load Combinations", ok=True)


@register
class CreateSpectralCommand(BaseCommand):
    command_id = "create_spectral"
    label = "Response Spectrum"
    menu_path = "Define"
    tooltip = "Generate spectral response spectrum .txt file"
    dialog_class = "civiltools.gui.dialogs.create_spectral_dialog.CreateSpectralDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Response Spectrum", ok=True)


@register
class CreateSectionCutsCommand(BaseCommand):
    command_id = "create_section_cuts"
    label = "Section Cuts"
    menu_path = "Define"
    tooltip = "Create section cuts in ETABS for force extraction"
    dialog_class = "civiltools.gui.dialogs.create_section_cuts_dialog.CreateSectionCutsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Section Cuts", ok=True)


@register
class RenameConcreteSectionsCommand(BaseCommand):
    command_id = "rename_concrete_sections"
    label = "Rename Concrete Sections"
    menu_path = "Define"
    tooltip = "Preview and rename rectangular concrete beam/column sections by pattern"
    dialog_class = "civiltools.gui.dialogs.rename_concrete_sections_dialog.RenameConcreteSectionsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        return CommandResult(title="Rename Concrete Sections", ok=True)
