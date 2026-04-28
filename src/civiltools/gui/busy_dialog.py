"""
Busy / progress overlay shown while a blocking ETABS command runs.

Usage
-----
    with BusyDialog("Running Drift…", parent=self):
        result = cmd_class.execute(etabs, params)

The dialog shows:
  - Command label
  - Indeterminate progress bar (animated via QTimer every 40 ms)
  - Elapsed-time counter updated every second
  - processEvents() called each timer tick so the animation actually renders

Because COM calls block the main thread, a real QThread is not used here.
The animation relies on processEvents() between timer ticks — fine for
commands that take > ~0.5 s.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)


class BusyDialog(QDialog):
    """Non-blocking modal overlay with an animated progress bar."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._start_time = 0.0
        self._anim_timer = QTimer(self)
        self._elapsed_timer = QTimer(self)

        self.setWindowTitle("Please wait…")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            # No close button — user cannot cancel a blocking COM call
        )
        self.setFixedWidth(360)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 20, 24, 20)

        # Command name
        self._lbl_cmd = QLabel(label)
        self._lbl_cmd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_cmd.setStyleSheet("font-size: 13px; font-weight: bold;")
        self._lbl_cmd.setWordWrap(True)
        lay.addWidget(self._lbl_cmd)

        # Indeterminate progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)          # indeterminate
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(14)
        lay.addWidget(self._bar)

        # Elapsed time
        self._lbl_elapsed = QLabel("Elapsed: 0 s")
        self._lbl_elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_elapsed.setStyleSheet("color: #666; font-size: 11px;")
        lay.addWidget(self._lbl_elapsed)

        # Timer: pump the event loop so the bar animates
        self._anim_timer.setInterval(40)          # ~25 fps
        self._anim_timer.timeout.connect(self._pump)

        # Timer: update elapsed label
        self._elapsed_timer.setInterval(1_000)    # every 1 s
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    # ── Context-manager interface ────────────────────────────────────────────

    def __enter__(self):
        from PySide6.QtWidgets import QApplication
        self._start_time = time.monotonic()
        self.show()
        self.raise_()
        self.activateWindow()
        self.repaint()                   # synchronous paint before blocking call
        QApplication.processEvents()     # flush OS paint messages
        self._anim_timer.start()
        self._elapsed_timer.start()
        return self

    def __exit__(self, *_):
        self._anim_timer.stop()
        self._elapsed_timer.stop()
        self.hide()
        self.deleteLater()

    # ── Internals ────────────────────────────────────────────────────────────

    def _pump(self):
        """Process pending Qt events so the animation frame renders."""
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    def _update_elapsed(self):
        elapsed = int(time.monotonic() - self._start_time)
        self._lbl_elapsed.setText(f"Elapsed: {elapsed} s")

    # Prevent accidental close via Escape
    def keyPressEvent(self, e):   # noqa: N802
        if e.key() != Qt.Key.Key_Escape:
            super().keyPressEvent(e)
