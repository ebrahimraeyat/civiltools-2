"""
Busy / progress overlay shown while a blocking ETABS command runs.

Usage
-----
    with BusyDialog(
        "Running Drift…",
        status_text="ETABS is running the analysis and collecting results…",
        parent=self,
        disable_widgets=[self.ui],
    ):
        result = cmd_class.execute(etabs, params)

The dialog shows:
  - Command label
  - Circular indeterminate spinner
  - Indeterminate progress bar
  - Status message
  - Elapsed-time counter updated every second
  - processEvents() called each timer tick so the animation actually renders

Because COM calls block the main thread, a real QThread is not used here.
The animation relies on processEvents() between timer ticks — fine for
commands that take > ~0.5 s.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QLabel,
    QWidget,
    QVBoxLayout,
    QTextEdit,
)


class _CircularSpinner(QWidget):
    """Rotating comet-tail circular spinner with elapsed counter."""

    _TAIL_DEG   = 240   # degrees covered by the fading tail
    _SEGMENTS   = 40   # number of arc segments in the tail
    _PEN_WIDTH  = 10
    _SIZE       = 110

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle   = 0
        self._elapsed = 0
        self._timer   = QTimer(self)
        self._timer.setInterval(16)          # ~60 fps
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(self._SIZE, self._SIZE)

    def start(self):
        self._elapsed = 0
        self._angle   = 0
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()
        self.update()

    def set_elapsed(self, seconds: int):
        self._elapsed = seconds
        self.update()

    def _tick(self):
        self._angle = (self._angle + 4) % 360
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        p = self._PEN_WIDTH
        rect = QRectF(p, p, self.width() - 2 * p, self.height() - 2 * p)
        cx = rect.center().x()
        cy = rect.center().y()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── track ring ──────────────────────────────────────────────
        track_pen = QPen(QColor("#dde6f8"), p)
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)

        # ── comet tail: SEGMENTS short arcs, fading toward the back ─
        seg_deg = self._TAIL_DEG / self._SEGMENTS
        for i in range(self._SEGMENTS):
            frac   = (i + 1) / self._SEGMENTS          # 0 → 1 at head
            alpha  = int(255 * (frac ** 1.8))
            r      = int(54  + (22  - 54)  * (1 - frac))   # 54 → 22 (blue channel)
            g      = int(140 + (162 - 140) * frac)          # slight teal shift
            color  = QColor(79, g, 255, alpha)

            seg_pen = QPen(color, p)
            seg_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(seg_pen)

            # Qt: 0° = 3 o'clock, positive = CCW; we want CW rotation
            start_angle = self._angle - self._TAIL_DEG + i * seg_deg
            qt_start    = int((90 - start_angle) * 16)
            qt_span     = int(-seg_deg * 16)
            painter.drawArc(rect, qt_start, qt_span)

        # ── bright rounded head ──────────────────────────────────────
        head_pen = QPen(QColor("#4f8cff"), p + 1)
        head_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(head_pen)
        painter.drawArc(rect, int((90 - self._angle) * 16), -int(seg_deg * 16))

        # ── elapsed seconds counter in the centre ───────────────────
        font = QFont()
        font.setPixelSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#2a5ab8")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._elapsed))


class BusyDialog(QDialog):
    """Non-blocking modal overlay with circular comet-tail spinner."""

    def __init__(
        self,
        label: str,
        status_text: str = "Working with ETABS…",
        parent=None,
        disable_widgets: list[QWidget] | tuple[QWidget, ...] | None = None,
    ):
        super().__init__(parent)
        self._start_time = 0.0
        self._elapsed_timer = QTimer(self)
        self._disable_widgets = [w for w in (disable_widgets or []) if w is not None]
        self._disabled_prev_state: list[tuple[QWidget, bool]] = []

        self.setWindowTitle("Please wait…")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(520)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(18, 18, 18, 18)

        card = QFrame()
        card.setObjectName("busyCard")
        card.setStyleSheet(
            """
            QFrame#busyCard {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ffffff,
                    stop:1 #f4f8ff
                );
                border: 1px solid #d7e3ff;
                border-radius: 18px;
            }
            QLabel#titleLabel {
                color: #15315b;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#statusLabel {
                color: #4e6485;
                font-size: 11px;
            }
            QLabel#elapsedLabel {
                color: #6a7a92;
                font-size: 11px;
            }
            """
        )
        lay.addWidget(card)

        card_lay = QVBoxLayout(card)
        card_lay.setSpacing(14)
        card_lay.setContentsMargins(28, 24, 28, 22)

        self._spinner = _CircularSpinner(card)
        card_lay.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        card_lay.setSpacing(10)

        # Command name
        self._lbl_cmd = QLabel(label)
        self._lbl_cmd.setObjectName("titleLabel")
        self._lbl_cmd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_cmd.setWordWrap(True)
        card_lay.addWidget(self._lbl_cmd)

        # Status line
        self._lbl_status = QLabel(status_text)
        self._lbl_status.setObjectName("statusLabel")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setWordWrap(True)
        card_lay.addWidget(self._lbl_status)

        # Timer: update elapsed seconds inside spinner
        self._elapsed_timer.setInterval(1_000)    # every 1 s
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        # Live output panel — mini read-only log for current command output
        self._live_log = QTextEdit()
        self._live_log.setReadOnly(True)
        self._live_log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._live_log.setFont(mono)
        self._live_log.setFixedHeight(130)
        self._live_log.setStyleSheet(
            "QTextEdit {"
            "  background: #0d1b2e;"
            "  color: #c9d8ee;"
            "  border: 1px solid #2a4a7a;"
            "  border-radius: 6px;"
            "  padding: 4px;"
            "}"
            "QScrollBar:vertical { width: 6px; }"
        )
        self._live_log.hide()
        card_lay.addWidget(self._live_log)


    # ── Public API ───────────────────────────────────────────────────────────

    def run(self, func):
        """Show the spinner, run *func()* in a background thread, return its result.

        The main thread processes Qt events continuously so the spinner
        animates.  Any exception raised by *func* is re-raised here.

        Usage::

            with BusyDialog("Drift…", parent=self, disable_widgets=[self.ui]) as dlg:
                result = dlg.run(lambda: etabs.get_drifts(…))
        """
        _result: list = [None]
        _exc:    list = [None]

        def _worker():
            try:
                _result[0] = func()
            except BaseException as e:  # noqa: BLE001
                _exc[0] = e

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while t.is_alive():
            QApplication.processEvents()
            t.join(timeout=0.016)   # yield 16 ms then check again

        if _exc[0] is not None:
            raise _exc[0]   # type: ignore[misc]
        return _result[0]

    # ── Context-manager interface ────────────────────────────────────────────

    def __enter__(self):
        self._start_time = time.monotonic()
        self._set_disabled(True)
        self.show()
        self._center_on_parent()
        self.raise_()
        self.activateWindow()
        self.repaint()
        QApplication.processEvents()
        self._spinner.start()
        self._elapsed_timer.start()
        # Clear the live output panel for this command
        self._live_log.clear()
        # Hook into app_log to show live stdout lines in the dialog
        try:
            from civiltools.gui.log_widget import app_log
            app_log._bridge.message_ready.connect(self._on_log_message)
            self._log_hooked = True
        except Exception:   # noqa: BLE001
            self._log_hooked = False
        return self

    def __exit__(self, *_):
        self._spinner.stop()
        self._elapsed_timer.stop()
        # Unhook from app_log
        if getattr(self, "_log_hooked", False):
            try:
                from civiltools.gui.log_widget import app_log
                app_log._bridge.message_ready.disconnect(self._on_log_message)
            except Exception:   # noqa: BLE001
                pass
        self._set_disabled(False)
        self.hide()
        self.deleteLater()

    def set_label(self, text: str):
        self._lbl_cmd.setText(text)
        QApplication.processEvents()

    def set_status(self, text: str):
        self._lbl_status.setText(text)
        QApplication.processEvents()

    # ── Live log tail ────────────────────────────────────────────────────────

    def _on_log_message(self, level: str, text: str):
        """Slot connected to app_log._bridge.message_ready during execution."""
        if level != "CMD_OUT":
            return
        # Strip the pipe prefix ("  │  ") inserted by the logger
        display = text.lstrip().lstrip("│").strip()
        if not display:
            return

        self._live_log.show()
        self._center_on_parent()

        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#c9d8ee"))   # default: light blue-white

        # Colour-code common patterns
        low = display.lower()
        if any(kw in low for kw in ("error", "fail", "exception", "traceback")):
            fmt.setForeground(QColor("#ff6b6b"))   # red
            fmt.setFontWeight(QFont.Weight.Bold)
        elif any(kw in low for kw in ("warn", "warning")):
            fmt.setForeground(QColor("#ffd166"))   # amber
        elif display.startswith("-" * 5) or display.startswith("=" * 5):
            fmt.setForeground(QColor("#6ee7b7"))   # mint green for section headers
            fmt.setFontWeight(QFont.Weight.Bold)
        elif "=" in display and any(c.isdigit() for c in display):
            fmt.setForeground(QColor("#93c5fd"))   # light blue for key=value lines

        cursor = self._live_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(display + "\n", fmt)
        self._live_log.setTextCursor(cursor)
        self._live_log.ensureCursorVisible()

    # ── Internals ────────────────────────────────────────────────────────────

    def _update_elapsed(self):
        elapsed = int(time.monotonic() - self._start_time)
        self._spinner.set_elapsed(elapsed)

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        geom = parent.frameGeometry()
        self.move(
            geom.center().x() - self.width() // 2,
            geom.center().y() - self.height() // 2,
        )

    def _set_disabled(self, disabled: bool):
        if disabled:
            self._disabled_prev_state = []
            for widget in self._disable_widgets:
                self._disabled_prev_state.append((widget, widget.isEnabled()))
                widget.setEnabled(False)
            return

        for widget, was_enabled in self._disabled_prev_state:
            widget.setEnabled(was_enabled)
        self._disabled_prev_state.clear()

    # Prevent accidental close via Escape
    def keyPressEvent(self, e):   # noqa: N802
        if e.key() != Qt.Key.Key_Escape:
            super().keyPressEvent(e)
