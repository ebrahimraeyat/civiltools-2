"""
Application-wide configuration and paths.

Uses ``platformdirs`` so data files go to the correct OS-specific
locations (AppData on Windows, ~/.config on Linux).
"""

from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir, user_config_dir


APP_NAME = "civilTools"
APP_AUTHOR = "civilTools"


def data_dir() -> Path:
    """Persistent data directory (licenses, cached results)."""
    p = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    """Configuration directory (settings JSON)."""
    p = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    p.mkdir(parents=True, exist_ok=True)
    return p


def resources_dir() -> Path:
    """Bundled resources (icons, fonts, templates).

    Works both in development (source tree) and in frozen builds.
    """
    import sys

    if getattr(sys, "frozen", False):
        # PyInstaller / Nuitka frozen bundle
        return Path(sys._MEIPASS) / "resources"  # type: ignore[attr-defined]
    # Development: relative to project root
    return Path(__file__).resolve().parent.parent.parent / "resources"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_SETTINGS_FILE = "settings.json"
_DEFAULTS = {
    "language": "fa",
    "theme": "fusion",
    "last_etabs_path": "",
    "report_format": "both",
    "font_name": "B Nazanin",
    "recent_files": [],
}


class Settings:
    """Simple JSON-backed settings store."""

    def __init__(self):
        self._path = config_dir() / _SETTINGS_FILE
        self._data: dict = {}
        self.load()

    def load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        for k, v in _DEFAULTS.items():
            self._data.setdefault(k, v)

    def save(self):
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self.set(key, value)
