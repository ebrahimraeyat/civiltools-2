"""
Backup management commands — ported from
civilTools/gui_civiltools/gui_delete_backups.py (and restore).

Manage the ``BACKUP_*.EDB`` files that the software auto-creates in the
model's ``backups`` folder.  All interaction happens in the dialog.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class DeleteBackupsCommand(BaseCommand):
    command_id = "delete_backups"
    label = "Delete Backups"
    menu_path = "Tools"
    tooltip = "Delete BACKUP_*.EDB files created automatically by the software"
    dialog_class = "civiltools.gui.dialogs.delete_backups_dialog.DeleteBackupsDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        # Interaction happens entirely inside the dialog; never called directly.
        return CommandResult(title="Delete Backups", ok=True)


@register
class RestoreBackupCommand(BaseCommand):
    command_id = "restore_backup"
    label = "Restore Backup"
    menu_path = "Tools"
    tooltip = "Restore a BACKUP_*.EDB file over the current model"
    dialog_class = "civiltools.gui.dialogs.restore_backup_dialog.RestoreBackupDialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        # Interaction happens entirely inside the dialog; never called directly.
        return CommandResult(title="Restore Backup", ok=True)
