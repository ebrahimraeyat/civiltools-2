"""
License activation / registration dialog.

Shown when:
- Trial has expired
- User clicks Help → Register
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

if TYPE_CHECKING:
    from civiltools.licensing.license_manager import LicenseManager


class ActivationDialog(QDialog):
    """Serial key entry dialog."""

    def __init__(self, manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("civilTools — Registration")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("civilTools Registration")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Info
        info = self.manager.get_info()
        if info.is_trial and info.days_remaining > 0:
            msg = f"Trial: {info.days_remaining} days remaining"
        else:
            msg = "Your trial period has expired. Please enter a serial key to continue."
        msg_label = QLabel(msg)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg_label)

        layout.addSpacing(10)

        # Machine ID (read-only — for support)
        form = QFormLayout()

        self._machine_id_edit = QLineEdit(info.machine_id)
        self._machine_id_edit.setReadOnly(True)
        self._machine_id_edit.setStyleSheet("background: #f0f0f0;")
        form.addRow("Machine ID:", self._machine_id_edit)

        self._serial_edit = QLineEdit()
        self._serial_edit.setPlaceholderText("CT-XXXXX-XXXXX-XXXXX-XXXXX")
        self._serial_edit.setFont(QFont("Consolas", 12))
        form.addRow("Serial Key:", self._serial_edit)

        layout.addLayout(form)

        # Hint
        hint = QLabel(
            '<small>Send your <b>Machine ID</b> to the civilTools developer '
            'to receive your serial key.</small>'
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hint)

        layout.addSpacing(10)

        # Buttons
        buttons = QDialogButtonBox()
        self._activate_btn = buttons.addButton("Activate", QDialogButtonBox.ButtonRole.AcceptRole)
        self._activate_btn.clicked.connect(self._on_activate)

        if info.is_trial and info.days_remaining > 0:
            self._trial_btn = buttons.addButton(
                f"Continue Trial ({info.days_remaining}d)",
                QDialogButtonBox.ButtonRole.RejectRole,
            )
            self._trial_btn.clicked.connect(self.accept)

        self._quit_btn = buttons.addButton("Quit", QDialogButtonBox.ButtonRole.DestructiveRole)
        self._quit_btn.clicked.connect(self.reject)

        layout.addWidget(buttons)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet("color: red;")
        layout.addWidget(self._status)

    def _on_activate(self):
        serial = self._serial_edit.text().strip()
        if not serial:
            self._status.setText("Please enter a serial key.")
            return

        if self.manager.activate(serial):
            QMessageBox.information(
                self,
                "Activated",
                "civilTools has been activated successfully!\n"
                "Thank you for your purchase.",
            )
            self.accept()
        else:
            self._status.setText(
                "Invalid serial key for this machine. "
                "Please double-check and try again."
            )

    @property
    def activated(self) -> bool:
        return self.result() == QDialog.DialogCode.Accepted


def show_activation_dialog(manager: LicenseManager) -> bool:
    """Show the activation dialog (creating QApplication if needed).

    Returns True if the user activated or is continuing trial.
    """
    app = QApplication.instance()
    created_app = False
    if app is None:
        import sys
        app = QApplication(sys.argv)
        created_app = True

    dlg = ActivationDialog(manager)
    result = dlg.exec()

    if created_app:
        # Don't exit the event loop; we just needed a temporary QApp
        pass

    return result == QDialog.DialogCode.Accepted
