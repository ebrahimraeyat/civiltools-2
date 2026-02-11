"""
License manager — trial period + hardware-locked serial keys.

Workflow:
    1. First launch → record install date → start 30-day trial
    2. During trial → show "X days remaining" in title bar
    3. After trial expires → show registration dialog
    4. User enters serial key → verify against machine_id
    5. If valid → save to license file → unlock permanently
    6. If invalid → allow retry or quit

Serial key format:  CT-XXXXX-XXXXX-XXXXX-XXXXX
    (CT prefix + 4 groups of 5 alphanumeric chars)

Key generation (your admin tool):
    HMAC-SHA256(secret + machine_id) → encode as serial blocks

License file is stored in the user data directory (AppData).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from civiltools.config import data_dir
from civiltools.licensing.machine_id import get_machine_id


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRIAL_DAYS = 30
LICENSE_FILENAME = "license.json"
# WARNING: Change this secret before distributing to users.
# In a Nuitka build this string is compiled to C and hard to extract.
_SECRET = b"cT_2024_s3cr3t_k3y_ch4ng3_m3!"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class LicenseInfo(NamedTuple):
    """Parsed license state."""

    is_licensed: bool
    is_trial: bool
    days_remaining: int
    machine_id: str
    serial: str  # empty if trial


# ---------------------------------------------------------------------------
# Key generation / verification
# ---------------------------------------------------------------------------

def generate_serial(machine_id: str, secret: bytes = _SECRET) -> str:
    """Generate a valid serial key for a given machine_id.

    This function is your **admin tool**.  Keep it out of end-user builds
    or at least don't expose the secret in plain source (Nuitka helps).
    """
    raw = hmac.new(secret, machine_id.encode(), hashlib.sha256).hexdigest().upper()
    blocks = [raw[i: i + 5] for i in range(0, 20, 5)]
    return "CT-" + "-".join(blocks)


def verify_serial(serial: str, machine_id: str, secret: bytes = _SECRET) -> bool:
    """Check whether *serial* is valid for *machine_id*."""
    expected = generate_serial(machine_id, secret)
    return hmac.compare_digest(serial.strip().upper(), expected.upper())


# ---------------------------------------------------------------------------
# License file I/O
# ---------------------------------------------------------------------------

def _license_path(override_dir: Path | None = None) -> Path:
    d = override_dir or data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / LICENSE_FILENAME


def _read_license(override_dir: Path | None = None) -> dict:
    path = _license_path(override_dir)
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_license(data: dict, override_dir: Path | None = None):
    path = _license_path(override_dir)
    path.write_text(json.dumps(data, indent=2), "utf-8")


# ---------------------------------------------------------------------------
# LicenseManager
# ---------------------------------------------------------------------------

class LicenseManager:
    """Manages trial and serial key licensing."""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir
        self._data = _read_license(data_dir)
        self._machine_id = get_machine_id()

    @property
    def machine_id(self) -> str:
        return self._machine_id

    # ── State queries ─────────────────────────────────────────────────

    def get_info(self) -> LicenseInfo:
        """Return current license state."""
        # Check for a valid serial
        serial = self._data.get("serial", "")
        if serial and verify_serial(serial, self._machine_id):
            return LicenseInfo(
                is_licensed=True,
                is_trial=False,
                days_remaining=999,
                machine_id=self._machine_id,
                serial=serial,
            )

        # Check trial
        install_ts = self._data.get("install_ts")
        if install_ts is None:
            # First launch — start trial now
            install_ts = time.time()
            self._data["install_ts"] = install_ts
            self._data["machine_id"] = self._machine_id
            _write_license(self._data, self._data_dir)

        install_date = datetime.fromtimestamp(install_ts)
        expiry = install_date + timedelta(days=TRIAL_DAYS)
        remaining = (expiry - datetime.now()).days

        return LicenseInfo(
            is_licensed=remaining > 0,
            is_trial=True,
            days_remaining=max(remaining, 0),
            machine_id=self._machine_id,
            serial="",
        )

    # ── Actions ───────────────────────────────────────────────────────

    def activate(self, serial: str) -> bool:
        """Try to activate with a serial key.  Returns True on success."""
        if verify_serial(serial, self._machine_id):
            self._data["serial"] = serial.strip().upper()
            self._data["activated_ts"] = time.time()
            self._data["machine_id"] = self._machine_id
            _write_license(self._data, self._data_dir)
            return True
        return False

    def check_or_prompt(self) -> bool:
        """Check license and show GUI prompt if needed.

        Returns True if the app should start, False to exit.
        """
        info = self.get_info()

        if info.is_licensed and not info.is_trial:
            return True  # fully licensed

        if info.is_licensed and info.is_trial:
            return True  # trial still valid — main window will show days left

        # Trial expired and no valid serial → prompt
        return self._show_activation_dialog()

    def _show_activation_dialog(self) -> bool:
        """Show the activation dialog.  Returns True if user activates."""
        from civiltools.licensing.dialogs import show_activation_dialog

        return show_activation_dialog(self)
