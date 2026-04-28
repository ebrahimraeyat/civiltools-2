"""
Connect to Software dialog.

Replaces the old FreeCAD py_widget/connect_to_software.py with a
standalone PySide6 dialog that:

1. Lets the user pick ETABS / SAP2000 / SAFE.
2. Scans for all running instances (using psutil + win32gui).
3. Shows each instance as a thumbnail card (live screenshot via Qt).
4. Connects to the selected instance via COM pid_moniker so the user
   can choose between multiple open ETABS windows.
5. Falls back to the generic "attach to any" connect if only one
   instance is found or if scanning fails.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)

_THUMB_W = 260
_THUMB_H = 160


# ── Background scanner ───────────────────────────────────────────────────────

class _ScanWorker(QThread):
    """Finds running instances in a background thread."""

    finished = Signal(list)   # list[dict]
    error    = Signal(str)

    def __init__(self, connection, software: str, parent=None):
        super().__init__(parent)
        self._conn = connection
        self._software = software

    def run(self):
        try:
            instances = self._conn.list_instances(self._software)
            self.finished.emit(instances)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Instance card widget ─────────────────────────────────────────────────────

class _InstanceCard(QWidget):
    """One selectable card: screenshot thumbnail + window title."""

    selected = Signal(dict)       # emits the instance dict on click

    def __init__(self, instance: dict, parent=None):
        super().__init__(parent)
        self._instance = instance
        self._chosen = False

        self.setFixedWidth(_THUMB_W + 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._normal_style = (
            "border: 2px solid #cccccc; border-radius: 6px; background: #f9f9f9;"
        )
        self._hover_style = (
            "border: 2px solid #4a90d9; border-radius: 6px; background: #eef5ff;"
        )
        self._chosen_style = (
            "border: 3px solid #006400; border-radius: 6px; background: #e8f5e9;"
        )
        self.setStyleSheet(self._normal_style)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet("border: none; background: #e0e0e0;")
        lay.addWidget(self._thumb)

        # Title
        title = instance.get("title", "") or f"PID {instance['pid']}"
        lbl = QLabel(title)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("border: none; font-size: 11px;")
        lay.addWidget(lbl)

        pid_lbl = QLabel(f"PID {instance['pid']}")
        pid_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pid_lbl.setStyleSheet("border: none; color: #888; font-size: 10px;")
        lay.addWidget(pid_lbl)

        self._load_thumbnail(instance.get("hwnd", 0))

    # ── Screenshot ──────────────────────────────────────────────────────────

    def _load_thumbnail(self, hwnd: int):
        """Grab a screenshot of the window and scale it to thumbnail size."""
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap()
        if hwnd:
            try:
                screen = QApplication.primaryScreen()
                pixmap = screen.grabWindow(hwnd)
            except Exception:
                pass
        if pixmap.isNull():
            pixmap = QPixmap(_THUMB_W, _THUMB_H)
            pixmap.fill(Qt.GlobalColor.lightGray)
        self._thumb.setPixmap(
            pixmap.scaled(
                _THUMB_W, _THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Mouse events ────────────────────────────────────────────────────────

    def set_chosen(self, chosen: bool):
        self._chosen = chosen
        self.setStyleSheet(self._chosen_style if chosen else self._normal_style)

    def mousePressEvent(self, _e):   # noqa: N802
        self.selected.emit(self._instance)

    def enterEvent(self, _e):        # noqa: N802
        if not self._chosen:
            self.setStyleSheet(self._hover_style)

    def leaveEvent(self, _e):        # noqa: N802
        if not self._chosen:
            self.setStyleSheet(self._normal_style)


# ── Main dialog ──────────────────────────────────────────────────────────────

class ConnectDialog(QDialog):
    """Dialog to connect to a specific running ETABS / SAP2000 / SAFE instance."""

    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self._conn = connection
        self._selected_instance: dict | None = None
        self._cards: list[_InstanceCard] = []
        self._scan_worker: _ScanWorker | None = None

        self.setWindowTitle("Connect to Software")
        self.setMinimumWidth(580)
        self.setMinimumHeight(500)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Software selector ────────────────────────────────────────────
        sw_grp = QGroupBox("Software")
        sw_row = QHBoxLayout(sw_grp)
        self._rb_etabs = QRadioButton("ETABS")
        self._rb_sap   = QRadioButton("SAP2000")
        self._rb_safe  = QRadioButton("SAFE")
        self._rb_etabs.setChecked(True)
        for rb in (self._rb_etabs, self._rb_sap, self._rb_safe):
            sw_row.addWidget(rb)
            rb.toggled.connect(self._on_software_changed)
        sw_row.addStretch()
        self._btn_scan = QPushButton("🔍  Scan for Running Instances")
        self._btn_scan.setFixedHeight(30)
        self._btn_scan.clicked.connect(self._do_scan)
        sw_row.addWidget(self._btn_scan)
        root.addWidget(sw_grp)

        # ── Hint label ───────────────────────────────────────────────────
        self._lbl_hint = QLabel(
            'Click "Scan" to find open instances, then select one and click Connect.'
        )
        self._lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_hint.setStyleSheet(
            "color: #555; font-style: italic; padding: 4px;"
        )
        root.addWidget(self._lbl_hint)

        # ── Scrollable card row ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(250)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._cards_container = QWidget()
        self._cards_row = QHBoxLayout(self._cards_container)
        self._cards_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._cards_row.setSpacing(12)
        self._cards_row.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(self._cards_container)
        root.addWidget(scroll, 1)

        # ── Status label ─────────────────────────────────────────────────
        self._status = QLabel()
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("padding: 6px; font-size: 12px;")
        root.addWidget(self._status)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setEnabled(False)
        self._btn_connect.setDefault(True)
        self._btn_connect.setFixedHeight(32)

        self._btn_connect_any = QPushButton("Connect (any)")
        self._btn_connect_any.setToolTip(
            "Attach to whichever instance is registered in the COM Running "
            "Object Table — same as the old single-instance connect."
        )
        self._btn_connect_any.setFixedHeight(32)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.setFixedHeight(32)

        self._btn_close = QPushButton("Close")
        self._btn_close.setFixedHeight(32)

        btn_row.addWidget(self._btn_connect)
        btn_row.addWidget(self._btn_connect_any)
        btn_row.addWidget(self._btn_disconnect)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        # Signals
        self._btn_connect.clicked.connect(self._do_connect_selected)
        self._btn_connect_any.clicked.connect(self._do_connect_any)
        self._btn_disconnect.clicked.connect(self._do_disconnect)
        self._btn_close.clicked.connect(self.accept)

        self._update_status_label()

    # ── Software radio ────────────────────────────────────────────────────────

    def _get_software(self) -> str:
        if self._rb_sap.isChecked():
            return "SAP2000"
        if self._rb_safe.isChecked():
            return "SAFE"
        return "ETABS"

    def _on_software_changed(self):
        self._clear_cards()
        self._lbl_hint.setText(
            'Click "Scan" to find open instances, then select one and click Connect.'
        )

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _do_scan(self):
        self._clear_cards()
        self._btn_scan.setEnabled(False)
        self._btn_scan.setText("Scanning…")
        self._lbl_hint.setText("Scanning for running instances…")
        QApplication.processEvents()

        software = self._get_software()
        self._scan_worker = _ScanWorker(self._conn, software, self)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_done(self, instances: list[dict]):
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText("🔍  Scan for Running Instances")

        if not instances:
            self._lbl_hint.setText(
                f'No running {self._get_software()} instances found. '
                'Open the software and try again, or use "Connect (any)".'
            )
            return

        self._lbl_hint.setText(
            f"Found {len(instances)} instance(s). "
            "Click a card to select, then click Connect."
        )
        for inst in instances:
            card = _InstanceCard(inst, self._cards_container)
            card.selected.connect(self._on_card_selected)
            self._cards_row.addWidget(card)
            self._cards.append(card)

        # Auto-select when only one instance
        if len(instances) == 1:
            self._on_card_selected(instances[0])

    def _on_scan_error(self, msg: str):
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText("🔍  Scan for Running Instances")
        self._lbl_hint.setText(f"Scan failed: {msg}")
        log.warning("Instance scan error: %s", msg)

    def _clear_cards(self):
        self._selected_instance = None
        self._btn_connect.setEnabled(False)
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

    # ── Card selection ─────────────────────────────────────────────────────────

    def _on_card_selected(self, instance: dict):
        self._selected_instance = instance
        for card in self._cards:
            card.set_chosen(card._instance is instance)
        self._btn_connect.setEnabled(True)

    # ── Connect / disconnect ───────────────────────────────────────────────────

    def _do_connect_selected(self):
        if not self._selected_instance:
            return
        software = self._get_software()
        pid = self._selected_instance["pid"]
        self._status.setText(f"Connecting to {software} (PID {pid})…")
        self._status.repaint()

        ok = self._conn.connect_pid(pid, software)
        self._update_status_label()
        if not ok:
            self._status.setText(
                f'<span style="color:red">{self._conn.last_error}</span>'
            )

    def _do_connect_any(self):
        software = self._get_software()
        self._status.setText(f"Connecting to {software}…")
        self._status.repaint()

        ok = self._conn.connect(software=software)
        self._update_status_label()
        if not ok:
            self._status.setText(
                f'<span style="color:red">{self._conn.last_error}</span>'
            )

    def _do_disconnect(self):
        self._conn.disconnect()
        self._update_status_label()

    # ── Status label ───────────────────────────────────────────────────────────

    def _update_status_label(self):
        if self._conn.is_connected:
            ver = self._conn.version
            ver_str = f" v{ver}" if ver else ""
            model = self._conn.model_path or "(no model path)"
            self._status.setText(
                f'<span style="color:green; font-weight:bold;">'
                f"✔ Connected to {self._conn.software}{ver_str}"
                f"</span><br><small>{model}</small>"
            )
            self._btn_disconnect.setEnabled(True)
            self._btn_connect.setEnabled(False)
        else:
            self._status.setText(
                '<span style="color:#888;">Not connected</span>'
            )
            self._btn_disconnect.setEnabled(False)
