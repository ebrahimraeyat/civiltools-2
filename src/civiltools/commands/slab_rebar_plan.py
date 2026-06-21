"""Slab Rebar Plan command — generate DXF plans with optimized reinforcement.

Command registration for "Slab Rebar Plan" tool under Tools menu.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class SlabRebarPlanCommand(BaseCommand):
    """Generate DXF floor plans with optimized slab rebar layout."""

    command_id = "slab_rebar_plan"
    label = "Slab Rebar Plan"
    menu_path = "Tools"
    tooltip = "Generate floor plans with optimized slab reinforcement from ETABS design data"
    table_model = None  # Uses custom preview in dialog instead of tab result
    dialog_class = "civiltools.gui.dialogs.slab_rebar_plan_dialog.SlabRebarPlanDialog"
    requires_etabs = True

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        """Execute is a no-op; dialog handles all logic and returns result on accept."""
        return CommandResult(title="Slab Rebar Plan", ok=True)
