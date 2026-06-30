"""
Restore backup dialog — ported from civilTools/py_widget/tools/restore_backup.py.

Lists ``BACKUP_*`` files in the model's ``backups`` folder and restores the
selected one over the current model.  The latest backup for the current model
is pre-selected.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult


class RestoreBackupDialog(QDialog):
    """List and restore a ``BACKUP_*`` file over the current model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._backup_dir: Path | None = None

        self.setWindowTitle("Restore Backup File")
        self.resize(380, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a backup to restore over the current model:"))

        self.list = QListWidget()
        layout.addWidget(self.list)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Ok).setText("Restore")
        bbox.accepted.connect(self._restore)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

        self._fill_list()

    def _fill_list(self):
        self.list.clear()
        try:
            self._backup_dir = Path(self._etabs.get_filepath()) / "backups"
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Cannot locate model folder:\n{exc}")
            return
        if not self._backup_dir.exists():
            return
        names = sorted(p.name for p in self._backup_dir.glob("BACKUP_*"))
        self.list.addItems(names)
        self._preselect_latest(names)

    def _preselect_latest(self, names: list[str]):
        """Select the highest-numbered backup for the current model."""
        if not names:
            return
        try:
            filename = self._etabs.get_file_name_without_suffix()
        except Exception:
            filename = ""
        prefix = f"BACKUP_{filename}_"
        best_idx = len(names) - 1   # fallback: last item
        max_num = -1
        for i, name in enumerate(names):
            stem = name[:-4] if name.lower().endswith(".edb") else name
            if stem.startswith(prefix):
                try:
                    num = int(stem[len(prefix):])
                except ValueError:
                    continue
                if num > max_num:
                    max_num = num
                    best_idx = i
        self.list.setCurrentRow(best_idx)

    def _restore(self):
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, "No Selection", "Select a backup to restore.")
            return
        confirm = QMessageBox.question(
            self,
            "Confirm Restore",
            f"Restore '{item.text()}' over the current model?\n"
            "The current model will be overwritten.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        filepath = self._backup_dir / item.text()
        try:
            self._etabs.restore_backup(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))
            return

        self._result = CommandResult(
            title="Restore Backup",
            ok=True,
            summary=f"Restored backup '{item.text()}' over the current model.",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
