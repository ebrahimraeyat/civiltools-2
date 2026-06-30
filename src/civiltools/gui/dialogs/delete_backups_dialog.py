"""
Delete backups dialog — ported from civilTools/py_widget/tools/delete_backups.py.

Lists ``BACKUP_*`` files in the model's ``backups`` folder and lets the user
delete the selected ones.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult


class DeleteBackupsDialog(QDialog):
    """List and delete ``BACKUP_*`` files for the current model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._backup_dir: Path | None = None
        self._n_deleted = 0

        self.setWindowTitle("Delete Backup Files")
        self.resize(380, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select files to be cleaned:"))

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.select_all_button = QPushButton("Select All")
        self.deselect_all_button = QPushButton("Deselect All")
        btn_row.addWidget(self.delete_button)
        btn_row.addStretch(1)
        btn_row.addWidget(self.select_all_button)
        btn_row.addWidget(self.deselect_all_button)
        layout.addLayout(btn_row)

        bbox = QDialogButtonBox()
        bbox.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        bbox.accepted.connect(self._on_close)
        layout.addWidget(bbox)

        self.delete_button.clicked.connect(self._delete_selected)
        self.select_all_button.clicked.connect(self.list.selectAll)
        self.deselect_all_button.clicked.connect(self.list.clearSelection)

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
        self.list.selectAll()

    def _delete_selected(self):
        items = self.list.selectedItems()
        if not items:
            QMessageBox.information(self, "Nothing Selected", "Select files to delete.")
            return
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete {len(items)} backup file(s)? This cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        errors: list[str] = []
        for item in items:
            fp = self._backup_dir / item.text()
            try:
                fp.unlink()
                self._n_deleted += 1
            except Exception as exc:
                errors.append(f"{item.text()}: {exc}")
        if errors:
            QMessageBox.warning(self, "Some Deletions Failed", "\n".join(errors))
        self._fill_list()

    def _on_close(self):
        self._result = CommandResult(
            title="Delete Backups",
            ok=True,
            summary=f"Deleted {self._n_deleted} backup file(s).",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
