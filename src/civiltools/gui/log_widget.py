"""
Log panel widget — docked at the bottom of the main window.

Features
--------
* RichTextBox (QTextEdit, read-only) with colour-coded entries:
    - ERROR   → red   (#cc0000)
    - WARNING → amber (#b8860b / dark-yellow)
    - INFO    → black (or white in dark themes)
* Every entry is prefixed with an ISO-8601 timestamp.
* Send button (toolbar):
    - Default  : writes log.txt to the user data directory then opens the
                 system's default e-mail client with the file attached.
    - Advanced : POST the log to a Webhook URL (Telegram Bot API or
                 Discord webhook) if ``webhook_url`` is configured in Settings.
* Clear button clears the view *and* the in-memory buffer.
* Global singleton ``app_log`` — call ``app_log.info()``, ``app_log.warning()``,
  ``app_log.error()`` from anywhere in the application.

Usage
-----
    from civiltools.gui.log_widget import app_log, LogWidget

    # Emit messages from anywhere:
    app_log.info("Analysis started")
    app_log.warning("No load case found")
    app_log.error("Connection lost")

    # In MainWindow.__init__:
    self._log_widget = LogWidget(settings=self._settings, parent=self)
    dock = QDockWidget("Log", self)
    dock.setWidget(self._log_widget)
    self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
    app_log.attach(self._log_widget)
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QToolButton, QSizePolicy,
    QMessageBox,
)


# ─────────────────────────────────────────────────────────────────
#  Colour palette
# ─────────────────────────────────────────────────────────────────
_COLOURS = {
    "INFO":      QColor("#1a1a1a"),   # near-black
    "WARNING":   QColor("#8B6914"),   # dark amber
    "ERROR":     QColor("#cc0000"),   # clear red
    "CMD_START": QColor("#ffffff"),   # white text on teal band
    "CMD_OUT":   QColor("#1b3a5c"),   # dark steel-blue (indented output)
}

_BG_COLOURS = {
    "INFO":      QColor("transparent"),
    "WARNING":   QColor("#fff8e1"),    # very light yellow tint
    "ERROR":     QColor("#fff0f0"),    # very light red tint
    "CMD_START": QColor("#1a7a5e"),    # teal green header band
    "CMD_OUT":   QColor("#f0f5ff"),    # very light blue-grey tint
}

_LEVEL_ICONS = {
    "INFO":      "ℹ",
    "WARNING":   "⚠",
    "ERROR":     "✖",
    "CMD_START": "▶",
    "CMD_OUT":   "  │",              # indented pipe prefix
}


# ─────────────────────────────────────────────────────────────────
#  Signal bridge (thread-safe: can be called from any thread)
# ─────────────────────────────────────────────────────────────────
class _LogBridge(QObject):
    message_ready = Signal(str, str)   # (level, text)


# ─────────────────────────────────────────────────────────────────
#  Global logger
# ─────────────────────────────────────────────────────────────────
class AppLogger:
    """
    Thin logger that buffers log records and forwards them to an
    attached ``LogWidget`` when available.

    Thread-safe: uses Qt signals to post to the GUI thread.
    """

    def __init__(self):
        self._bridge = _LogBridge()
        self._widget: Optional["LogWidget"] = None
        self._buffer: list[tuple[str, str]] = []   # (level, message)

    def attach(self, widget: "LogWidget"):
        """Connect this logger to a LogWidget instance."""
        self._widget = widget
        self._bridge.message_ready.connect(widget._append)
        # Flush buffered messages
        for level, msg in self._buffer:
            widget._append(level, msg)
        self._buffer.clear()

    def _emit(self, level: str, msg: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        icon = _LEVEL_ICONS.get(level, "")
        if level == "CMD_OUT":
            # indented output lines: no timestamp clutter, just the pipe prefix
            full = f"{icon}  {msg}"
        else:
            full = f"[{ts}]  {icon}  {msg}"
        if self._widget is not None:
            # AutoConnection: safe from any thread (Qt queues cross-thread)
            self._bridge.message_ready.emit(level, full)
        else:
            self._buffer.append((level, full))

    def info(self, msg: str):
        self._emit("INFO", msg)

    def warning(self, msg: str):
        self._emit("WARNING", msg)

    def error(self, msg: str):
        self._emit("ERROR", msg)

    def cmd_out(self, msg: str):
        """Live stdout/stderr output from a running command."""
        self._emit("CMD_OUT", msg)

    # Convenience aliases
    warn = warning

    @contextlib.contextmanager
    def capture_output(self, label: str):
        """
        Context manager that:
        1. Emits a CMD_START banner.
        2. Redirects sys.stdout and sys.stderr so that print() calls
           from *any* thread are forwarded to the log as CMD_OUT lines.

        Works in frozen (PyInstaller / Nuitka) builds because it replaces
        the Python-level sys.stdout object, not the OS file descriptor.
        """
        self._emit("CMD_START", f" {label} ")
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = _LogRedirector(self, old_stdout)
        sys.stderr = _LogRedirector(self, old_stderr)
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr



#: Application-wide singleton logger
app_log = AppLogger()


# ─────────────────────────────────────────────────────────────────
#  stdout redirector (installed by capture_output)
# ─────────────────────────────────────────────────────────────────
class _LogRedirector(io.TextIOBase):
    """
    Replaces sys.stdout / sys.stderr.

    * Buffers partial writes (no newline yet) per-thread so concurrent
      threads don’t interleave mid-line.
    * On every complete line, emits to ``app_log.cmd_out()``.
    * Falls back to the original stream for flush / fileno so frozen
      builds that consult isatty() don’t crash.
    """

    def __init__(self, logger: AppLogger, original):
        super().__init__()
        self._logger   = logger
        self._original = original
        self._buffers: dict[int, str] = {}   # thread-id → partial line
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        if not text:
            return 0
        tid = threading.get_ident()
        with self._lock:
            buf = self._buffers.get(tid, "")
            buf += text
            lines = buf.split("\n")
            # Last element is the incomplete tail (may be empty string)
            self._buffers[tid] = lines[-1]
            complete = lines[:-1]
        for line in complete:
            stripped = line.rstrip("\r")
            if stripped:   # skip blank separator lines
                self._logger.cmd_out(stripped)
        return len(text)

    def flush(self):
        # Flush any partial line buffered for this thread
        tid = threading.get_ident()
        with self._lock:
            tail = self._buffers.pop(tid, "")
        if tail.strip():
            self._logger.cmd_out(tail.rstrip("\r"))
        try:
            self._original.flush()
        except Exception:   # noqa: BLE001
            pass

    @property
    def encoding(self):
        return getattr(self._original, "encoding", "utf-8") or "utf-8"

    def isatty(self) -> bool:   # noqa: D401
        return False

    def fileno(self) -> int:
        try:
            return self._original.fileno()
        except Exception:   # noqa: BLE001
            raise io.UnsupportedOperation("fileno") from None


# ─────────────────────────────────────────────────────────────────
#  Widget
# ─────────────────────────────────────────────────────────────────
class LogWidget(QWidget):
    """
    Bottom-panel log viewer with colour-coded entries and a Send button.
    """

    _MAX_ENTRIES = 2_000   # prevent unbounded growth

    def __init__(self, settings=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self._entries: list[tuple[str, str]] = []   # (level, full_text)
        self._build_ui()

    # ── UI setup ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        lbl = QLabel("<b>Log</b>")
        toolbar.addWidget(lbl)
        toolbar.addStretch()

        self._btn_send = QPushButton("📤  Send Log…")
        self._btn_send.setToolTip(
            "Save log to file and send via e-mail (default)\n"
            "or Webhook if configured in Settings."
        )
        self._btn_send.clicked.connect(self._send_log)
        toolbar.addWidget(self._btn_send)

        btn_clear = QToolButton()
        btn_clear.setText("🗑  Clear")
        btn_clear.setToolTip("Clear log panel")
        btn_clear.clicked.connect(self.clear)
        toolbar.addWidget(btn_clear)

        root.addLayout(toolbar)

        # Text area
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        self._view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._view.setFont(font)
        self._view.setMinimumHeight(90)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        root.addWidget(self._view)

    # ── Append ───────────────────────────────────────────────────────

    def _append(self, level: str, text: str):
        """Called via signal (GUI thread guaranteed)."""
        # Enforce maximum
        if len(self._entries) >= self._MAX_ENTRIES:
            self._entries.pop(0)
            cursor = self._view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        self._entries.append((level, text))

        fmt = QTextCharFormat()
        colour = _COLOURS.get(level, _COLOURS["INFO"])
        fmt.setForeground(colour)
        bg = _BG_COLOURS.get(level, _BG_COLOURS["INFO"])
        if bg.alpha() > 0 and bg.name() != "transparent":
            fmt.setBackground(bg)

        if level == "ERROR":
            fmt.setFontWeight(QFont.Weight.Bold)
        elif level == "CMD_START":
            fmt.setFontWeight(QFont.Weight.Bold)
            text = text.center(80, "\u2500")
        elif level == "CMD_OUT":
            font = QFont("Consolas", 9)
            font.setStyleHint(QFont.StyleHint.Monospace)
            fmt.setFont(font)

        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self._view.setTextCursor(cursor)
        self._view.ensureCursorVisible()

    # ── Public helpers ────────────────────────────────────────────────

    def clear(self):
        self._entries.clear()
        self._view.clear()

    def plain_text(self) -> str:
        """Return all log entries as plain text."""
        return "\n".join(t for _, t in self._entries)

    # ── Send logic ────────────────────────────────────────────────────

    def _log_file_path(self) -> Path:
        """Resolve the log.txt path inside the user data directory."""
        try:
            from civiltools.config import data_dir
            return data_dir() / "log.txt"
        except Exception:
            return Path(tempfile.gettempdir()) / "civiltools_log.txt"

    def _save_log_file(self) -> Path:
        path = self._log_file_path()
        path.write_text(self.plain_text(), encoding="utf-8")
        return path

    def _send_log(self):
        if not self._entries:
            QMessageBox.information(self, "Log", "Log is empty — nothing to send.")
            return

        webhook_url: str = ""
        if self._settings:
            webhook_url = self._settings.get("webhook_url", "")

        if webhook_url:
            self._send_via_webhook(webhook_url)
        else:
            self._send_via_email()

    # ── E-mail (default) ───────────────────────────────────────────

    def _send_via_email(self):
        try:
            log_path = self._save_log_file()
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not save log file:\n{exc}")
            return

        subject = "civilTools Log Report"
        body = (
            "Please find the civilTools log file attached.\n\n"
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Build mailto: URI.  Attachment is NOT part of RFC 2368 mailto but
        # Outlook / Thunderbird / Mail.app honour the `attach` or `attachment`
        # parameter.  We also try the platform-specific approach.
        if sys.platform == "win32":
            self._open_email_windows(log_path, subject, body)
        elif sys.platform == "darwin":
            self._open_email_macos(log_path, subject, body)
        else:
            self._open_email_xdg(log_path, subject, body)

    def _open_email_windows(self, log_path: Path, subject: str, body: str):
        """Use MAPI via mailto or fall back to explorer."""
        import urllib.parse

        # Outlook supports ?attach= but standard mailto doesn't.
        # The most portable approach on Windows is to write a .eml file
        # that references the log, or simply open the log path and let
        # the user attach it manually together with a mailto: link.
        encoded_body = body + f"\n\nLog saved at:\n{log_path}"
        params = urllib.parse.urlencode(
            {"subject": subject, "body": encoded_body}, quote_via=urllib.parse.quote
        )
        mailto = f"mailto:?{params}"
        os.startfile(mailto)   # type: ignore[attr-defined]      # noqa: S606
        QMessageBox.information(
            self,
            "Log Saved",
            f"Log file saved to:\n{log_path}\n\n"
            "Your e-mail client has been opened.\n"
            "Please attach the log file manually.",
        )

    def _open_email_macos(self, log_path: Path, subject: str, body: str):
        import urllib.parse

        encoded_body = body + f"\n\nLog saved at:\n{log_path}"
        params = urllib.parse.urlencode(
            {"subject": subject, "body": encoded_body}, quote_via=urllib.parse.quote
        )
        mailto = f"mailto:?{params}"
        subprocess.Popen(["open", mailto])
        QMessageBox.information(
            self,
            "Log Saved",
            f"Log file saved to:\n{log_path}\n\n"
            "Your e-mail client has been opened.\n"
            "Please attach the log file manually.",
        )

    def _open_email_xdg(self, log_path: Path, subject: str, body: str):
        import urllib.parse

        encoded_body = body + f"\n\nLog saved at:\n{log_path}"
        params = urllib.parse.urlencode(
            {"subject": subject, "body": encoded_body}, quote_via=urllib.parse.quote
        )
        mailto = f"mailto:?{params}"
        subprocess.Popen(["xdg-open", mailto])
        QMessageBox.information(
            self,
            "Log Saved",
            f"Log file saved to:\n{log_path}\n\n"
            "Your e-mail client has been opened.\n"
            "Please attach the log file manually.",
        )

    # ── Webhook (advanced) ────────────────────────────────────────────

    def _send_via_webhook(self, url: str):
        """
        POST the log text to a Discord or Telegram webhook.

        Discord  : POST application/json with ``{"content": "..."}``
        Telegram : POST to https://api.telegram.org/bot{TOKEN}/sendDocument
                   Detected when URL contains ``api.telegram.org``.
        """
        try:
            log_path = self._save_log_file()
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not save log file:\n{exc}")
            return

        try:
            if "api.telegram.org" in url:
                self._post_telegram(url, log_path)
            else:
                self._post_discord(url, log_path)
            QMessageBox.information(
                self, "Log Sent", "Log successfully sent to the configured webhook."
            )
        except Exception as exc:   # noqa: BLE001
            QMessageBox.critical(
                self,
                "Webhook Error",
                f"Failed to send log via webhook:\n\n{exc}\n\n"
                f"Log saved locally at:\n{log_path}",
            )

    def _post_discord(self, url: str, log_path: Path):
        """
        Discord webhook: multipart/form-data file upload so there is no
        2000-char limit.
        """
        import io
        import email.mime.multipart
        import uuid

        boundary = uuid.uuid4().hex
        content_type = f"multipart/form-data; boundary={boundary}"

        log_bytes = log_path.read_bytes()
        # Build multipart body manually (no requests dependency)
        parts: list[bytes] = []
        # JSON payload part
        json_part = json.dumps({
            "content": f"**civilTools Log** — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }).encode()
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n\r\n'.encode()
            + json_part
        )
        # File part
        fname = log_path.name
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
            f'Content-Type: text/plain\r\n\r\n'.encode()
            + log_bytes
        )
        body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Discord returned HTTP {resp.status}")

    def _post_telegram(self, url: str, log_path: Path):
        """
        Telegram Bot API sendDocument.
        URL format expected:
            https://api.telegram.org/bot<TOKEN>/sendDocument?chat_id=<ID>
        """
        import uuid

        boundary = uuid.uuid4().hex
        content_type = f"multipart/form-data; boundary={boundary}"
        log_bytes = log_path.read_bytes()
        fname = log_path.name
        caption = f"civilTools Log — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        parts: list[bytes] = []
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}'.encode()
        )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{fname}"\r\n'
            f'Content-Type: text/plain\r\n\r\n'.encode()
            + log_bytes
        )
        body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            if not data.get("ok"):
                raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
