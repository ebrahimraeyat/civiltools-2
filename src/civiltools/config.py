"""
Application-wide configuration and paths.

Uses ``platformdirs`` so data files go to the correct OS-specific
locations (AppData on Windows, ~/.config on Linux).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

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
SETTINGS_SCHEMA_VERSION = 1
MIN_REPORT_WORKERS = 1
MAX_REPORT_WORKERS = 16


def _default_report_sections() -> list[dict]:
    from civiltools.report.report_config import DEFAULT_SECTION_ORDER, SECTION_NAMES

    return [
        {
            "key": key,
            "title_en": SECTION_NAMES.get(key, {}).get("en", key),
            "title_fa": SECTION_NAMES.get(key, {}).get("fa", key),
            "included": True,
            "read_from_etabs": False,
        }
        for key in DEFAULT_SECTION_ORDER
    ]


def _default_settings() -> dict:
    return {
        "settings_schema_version": SETTINGS_SCHEMA_VERSION,
        "language": "fa",
        "theme": "fusion",
        "dark_theme": False,
        "last_etabs_path": "",
        "report_format": "docx",
        "font_name": "B Nazanin",
        "recent_files": [],
        "webhook_url": "",
        "report": {
            "language": "en",
            "workers": min(4, os.cpu_count() or 4),
            "include_table_of_contents": True,
            "fallback_to_etabs_if_missing": True,
            "sections": _default_report_sections(),
        },
    }


def default_report_preferences() -> dict:
    """Return a fresh copy of the application-wide report defaults."""
    return copy.deepcopy(_default_settings()["report"])


def _normalize_report(raw_report) -> dict:
    defaults = _default_settings()["report"]
    report = copy.deepcopy(raw_report) if isinstance(raw_report, dict) else {}
    normalized = {**defaults, **{key: value for key, value in report.items() if key != "sections"}}

    try:
        workers = int(normalized["workers"])
    except (TypeError, ValueError):
        workers = defaults["workers"]
    normalized["workers"] = max(MIN_REPORT_WORKERS, min(MAX_REPORT_WORKERS, workers))
    if normalized.get("language") not in {"en", "fa", "both"}:
        normalized["language"] = defaults["language"]
    normalized["include_table_of_contents"] = bool(normalized["include_table_of_contents"])
    normalized["fallback_to_etabs_if_missing"] = bool(
        normalized["fallback_to_etabs_if_missing"]
    )

    default_sections = {section["key"]: section for section in defaults["sections"]}
    sections = []
    seen = set()
    raw_sections = report.get("sections", [])
    if isinstance(raw_sections, list):
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                continue
            key = raw_section.get("key")
            if not isinstance(key, str) or not key or key in seen:
                continue
            fallback = default_sections.get(
                key,
                {
                    "key": key,
                    "title_en": key,
                    "title_fa": key,
                    "included": True,
                    "read_from_etabs": False,
                },
            )
            sections.append(
                {
                    "key": key,
                    "title_en": str(raw_section.get("title_en") or fallback["title_en"]),
                    "title_fa": str(raw_section.get("title_fa") or fallback["title_fa"]),
                    "included": bool(raw_section.get("included", fallback["included"])),
                    "read_from_etabs": bool(
                        raw_section.get("read_from_etabs", fallback["read_from_etabs"])
                    ),
                }
            )
            seen.add(key)

    sections.extend(
        copy.deepcopy(section)
        for key, section in default_sections.items()
        if key not in seen
    )
    normalized["sections"] = sections
    return normalized


def _normalize_settings(raw_data) -> dict:
    defaults = _default_settings()
    raw = copy.deepcopy(raw_data) if isinstance(raw_data, dict) else {}
    normalized = {**defaults, **raw}
    normalized["report"] = _normalize_report(raw.get("report"))
    normalized["settings_schema_version"] = SETTINGS_SCHEMA_VERSION
    return normalized


class Settings:
    """Simple JSON-backed settings store."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path is not None else config_dir() / _SETTINGS_FILE
        self._data: dict = {}
        self.load()

    def load(self):
        raw_data = {}
        if self._path.exists():
            try:
                raw_data = json.loads(self._path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                raw_data = {}
        self._data = _normalize_settings(raw_data)
        if self._data != raw_data:
            self.save()

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self.update({key: value})

    def update(self, values: dict) -> None:
        """Update multiple settings and persist them in one write."""
        self._data.update(copy.deepcopy(values))
        self._data = _normalize_settings(self._data)
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self.set(key, value)
