"""
civiltools.commands.wind_commands
==================================
Wind load commands — standalone (no ETABS connection required).
"""

from __future__ import annotations

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class BillboardWindCommand(BaseCommand):
    """Wind load calculation for free-standing billboards per مبحث ششم Ch. 10."""

    command_id  = "billboard_wind"
    label       = "Billboard Wind Load"
    menu_path   = "Wind"
    tooltip     = (
        "Calculate wind load on a free-standing billboard / signboard\n"
        "per Iranian National Building Code – Section 6, Chapter 10."
    )
    dialog_class = (
        "civiltools.gui.dialogs.billboard_wind_dialog.BillboardWindDialog"
    )
    requires_etabs = False   # standalone — no ETABS model needed

    @classmethod
    def execute(cls, etabs, params=None) -> CommandResult:
        # Execution happens entirely inside the dialog; this is never called directly.
        return CommandResult(title="Billboard Wind Load", ok=True)
