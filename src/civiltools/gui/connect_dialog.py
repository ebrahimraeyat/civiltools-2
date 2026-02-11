"""
Connect to ETABS dialog — standalone port of civilTools/py_widget/connect_to_software.py.

Provides a simple dialog to select software and connect.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QPushButton, QLabel, QMessageBox,
)


class ConnectDialog(QDialog):
    """Dialog to connect to a running ETABS / SAP2000 / SAFE instance."""

    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self._conn = connection
        self.setWindowTitle("Connect to Software")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Software selection
        grp = QGroupBox("Software")
        grp_layout = QHBoxLayout()
        self._rb_etabs = QRadioButton("ETABS")
        self._rb_sap = QRadioButton("SAP2000")
        self._rb_safe = QRadioButton("SAFE")
        self._rb_etabs.setChecked(True)
        grp_layout.addWidget(self._rb_etabs)
        grp_layout.addWidget(self._rb_sap)
        grp_layout.addWidget(self._rb_safe)
        grp.setLayout(grp_layout)
        layout.addWidget(grp)

        # Status
        self._status = QLabel("Not connected")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("padding: 8px; font-size: 13px;")
        layout.addWidget(self._status)

        # Buttons
        btn_layout = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setDefault(True)
        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_close = QPushButton("Close")
        btn_layout.addWidget(self._btn_connect)
        btn_layout.addWidget(self._btn_disconnect)
        btn_layout.addWidget(self._btn_close)
        layout.addLayout(btn_layout)

        # Connections
        self._btn_connect.clicked.connect(self._do_connect)
        self._btn_disconnect.clicked.connect(self._do_disconnect)
        self._btn_close.clicked.connect(self.accept)

        self._update_status()

    def _get_software(self) -> str:
        if self._rb_sap.isChecked():
            return "SAP2000"
        if self._rb_safe.isChecked():
            return "SAFE"
        return "ETABS"

    def _do_connect(self):
        software = self._get_software()
        self._status.setText(f"Connecting to {software}…")
        self._status.repaint()

        ok = self._conn.connect(software=software)
        if ok:
            self._update_status()
        else:
            self._status.setText(
                f'<span style="color:red">{self._conn.last_error}</span>'
            )
            self._btn_disconnect.setEnabled(False)

    def _do_disconnect(self):
        self._conn.disconnect()
        self._update_status()

    def _update_status(self):
        if self._conn.is_connected:
            model = self._conn.model_path or "(no model open)"
            self._status.setText(
                f'<span style="color:green">Connected to {self._conn.software}</span>'
                f'<br><small>{model}</small>'
            )
            self._btn_disconnect.setEnabled(True)
        else:
            self._status.setText("Not connected")
            self._btn_disconnect.setEnabled(False)
