"""Tests for application-wide settings and report preferences."""

from __future__ import annotations

import json

from civiltools.config import SETTINGS_SCHEMA_VERSION, Settings
from civiltools.report.report_config import DEFAULT_SECTION_ORDER


def test_first_run_creates_complete_report_preferences(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings = Settings(path=settings_path)

    report = settings.get("report")
    assert settings.get("settings_schema_version") == SETTINGS_SCHEMA_VERSION
    assert [section["key"] for section in report["sections"]] == DEFAULT_SECTION_ORDER
    assert all(section["included"] for section in report["sections"])
    assert not any(section["read_from_etabs"] for section in report["sections"])
    assert all(section["title_en"] and section["title_fa"] for section in report["sections"])
    assert report["fallback_to_etabs_if_missing"] is True
    assert 1 <= report["workers"] <= 16
    assert report["include_table_of_contents"] is True
    assert report["language"] == "en"


def test_legacy_settings_migrate_once_and_preserve_section_preferences(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "language": "en",
                "dark_theme": True,
                "report": {
                    "workers": 99,
                    "sections": [
                        {
                            "key": "drift",
                            "title_en": "Custom Drift",
                            "title_fa": "دریفت سفارشی",
                            "included": False,
                            "read_from_etabs": True,
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    settings = Settings(path=settings_path)
    report = settings.get("report")

    assert settings.get("language") == "en"
    assert settings.get("dark_theme") is True
    assert report["workers"] == 16
    assert report["sections"][0] == {
        "key": "drift",
        "title_en": "Custom Drift",
        "title_fa": "دریفت سفارشی",
        "included": False,
        "read_from_etabs": True,
    }
    assert [section["key"] for section in report["sections"]] == [
        "drift",
        *[key for key in DEFAULT_SECTION_ORDER if key != "drift"],
    ]

    migrated_text = settings_path.read_text(encoding="utf-8")
    Settings(path=settings_path)
    assert settings_path.read_text(encoding="utf-8") == migrated_text


def test_batch_update_persists_report_preferences_once(tmp_path, monkeypatch):
    settings = Settings(path=tmp_path / "settings.json")
    report = settings.get("report")
    report["sections"][0]["title_en"] = "Renamed Section"
    report["sections"][0]["title_fa"] = "عنوان جدید"
    report["workers"] = 8

    save_calls = 0
    original_save = settings.save

    def counted_save():
        nonlocal save_calls
        save_calls += 1
        original_save()

    monkeypatch.setattr(settings, "save", counted_save)
    settings.update({"report": report, "dark_theme": True})

    assert save_calls == 1
    restored = Settings(path=tmp_path / "settings.json")
    assert restored.get("report")["sections"][0]["title_en"] == "Renamed Section"
    assert restored.get("report")["sections"][0]["title_fa"] == "عنوان جدید"
    assert restored.get("report")["workers"] == 8
    assert restored.get("dark_theme") is True
