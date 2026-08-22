"""
Report configuration — controls language, format, section ordering, and
result manifest management.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# Section definitions
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_SECTION_ORDER: list[str] = [
    "model_settings",
    "project_info",
    "earthquake_formulation",
    "earthquake_values",
    "load_combinations",
    "story_forces",
    "drift",
    "torsion",
    "joint_shear",
    "pmm_columns",
    "columns_100_30",
    "story_plans",
    "area_loads",
    "irregularities",
    "design_results",
    "json_tables",
]

SECTION_NAMES: dict[str, dict[str, str]] = {
    "model_settings":          {"fa": "تنظیمات مدل", "en": "Model Settings"},
    "project_info":            {"fa": "اطلاعات پروژه", "en": "Project Information"},
    "loads":                   {"fa": "بارهای وارد بر سازه", "en": "Loads on Structure"},
    "seismic_params":          {"fa": "پارامترهای لرزه‌ای", "en": "Seismic Parameters"},
    "structural_system":       {"fa": "سیستم سازه‌ای", "en": "Structural System"},
    "earthquake_formulation":  {"fa": "فرمول‌های ضریب زلزله", "en": "Earthquake Formulas"},
    "earthquake_values":       {"fa": "مقادیر ضریب زلزله", "en": "Earthquake Coefficient Values"},
    "load_combinations":       {"fa": "ترکیبات بار", "en": "Load Combinations"},
    "story_forces":            {"fa": "نیروهای طبقات", "en": "Story Forces"},
    "drift":                   {"fa": "تغییرمکان نسبی طبقات", "en": "Story Drift"},
    "torsion":                 {"fa": "بی‌نظمی پیچشی", "en": "Torsional Irregularity"},
    "joint_shear":             {"fa": "برش در گره‌ها", "en": "Joint Shear Check"},
    "pmm_columns":             {"fa": "نتایج طراحی ستون‌ها", "en": "Column PMM Design Results"},
    "columns_100_30":          {"fa": "کنترل 100-30 ستون‌ها", "en": "100%-30% Column Check"},
    "story_plans": {
        "fa": "پلان تیر و ستون طبقات",
        "en": "Story Plans — Beams & Columns",
    },
    "area_loads":              {"fa": "پلان بارگذاری سطوح", "en": "Area Load Plans"},
    "irregularities":          {"fa": "بی‌نظمی‌ها", "en": "Irregularities"},
    "design_results":          {"fa": "نتایج طراحی", "en": "Design Results"},
    "json_tables":             {"fa": "جداول نتایج", "en": "Result Tables"},
}

REFRESHABLE_SECTIONS: tuple[str, ...] = (
    "drift",
    "torsion",
    "pmm_columns",
    "joint_shear",
    "columns_100_30",
)

MODEL_REPORT_SOURCES_SCHEMA_VERSION = 1
RESULT_TABLE_SCHEMA_VERSION = 1


def model_fingerprint(model_path: Path | str) -> str:
    """Return a stable, non-secret identity for an ETABS model path."""
    normalized = os.path.normcase(str(Path(model_path).resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════════
# ReportConfig
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ReportConfig:
    """Configuration for report generation."""

    language: str = "fa"                          # 'fa', 'en', 'both'
    output_format: str = "docx"
    section_order: list[str] = field(default_factory=lambda: list(DEFAULT_SECTION_ORDER))
    disabled_sections: list[str] = field(default_factory=list)
    json_table_order: list[str] = field(default_factory=list)  # explicit JSON table order
    refresh_sections: list[str] = field(default_factory=list)
    refresh_params: dict[str, dict] = field(default_factory=dict)
    section_sources: dict[str, str] = field(default_factory=dict)
    section_json_paths: dict[str, str] = field(default_factory=dict)
    section_titles: dict[str, dict[str, str]] = field(default_factory=dict)
    fallback_to_etabs_if_missing: bool = True
    page_size: str = "A4"                         # 'A4' or 'Letter'
    include_table_of_contents: bool = True
    include_page_numbers: bool = True
    font_name: str = "B Nazanin"
    # App-level preference: show only design-active load combinations
    filter_active_combinations: bool = True

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_rtl(self) -> bool:
        return self.language in ("fa", "both")

    @property
    def active_sections(self) -> list[str]:
        """Sections in order, excluding disabled ones."""
        return [s for s in self.section_order if s not in self.disabled_sections]

    def get_section_name(self, key: str) -> str:
        """Get localized section display name."""
        entry = SECTION_NAMES.get(key, {"en": key})
        lang = "fa" if self.language in ("fa", "both") else "en"
        return entry.get(lang, entry.get("en", key))

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ReportConfig:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def save(self, filepath: Path | str):
        Path(filepath).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, filepath: Path | str) -> ReportConfig:
        data = json.loads(Path(filepath).read_text("utf-8"))
        return cls.from_dict(data)

    @staticmethod
    def default_config_path(model_path: Path | str) -> Path:
        """Convention: ``<model_stem>_report_config.json``."""
        p = Path(model_path)
        return p.parent / f"{p.stem}_report_config.json"


@dataclass
class ModelReportSources:
    """Model-local paths to explicitly selected civilTools result JSON files."""

    schema_version: int = MODEL_REPORT_SOURCES_SCHEMA_VERSION
    section_json_paths: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def path_for_model(model_path: Path | str) -> Path:
        model = Path(model_path)
        return model.parent / f"{model.stem}_report_sources.json"

    def save_for_model(self, model_path: Path | str) -> Path:
        path = self.path_for_model(model_path)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load_for_model(cls, model_path: Path | str) -> ModelReportSources:
        path = cls.path_for_model(model_path)
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        paths = data.get("section_json_paths", {}) if isinstance(data, dict) else {}
        return cls(
            schema_version=MODEL_REPORT_SOURCES_SCHEMA_VERSION,
            section_json_paths={
                str(key): str(value)
                for key, value in paths.items()
                if isinstance(key, str) and isinstance(value, str)
            },
        )


# ═══════════════════════════════════════════════════════════════════════════
# ResultManifest
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class _TableEntry:
    filename: str
    display_name: dict[str, str]  # {'fa': '…', 'en': '…'}
    category: str = ""
    order: int = 50
    schema_version: int | None = None
    section_key: str | None = None
    model_fingerprint: str | None = None


class ResultManifest:
    """Track available JSON result table files with metadata.

    Stored as ``manifest.json`` alongside the result tables.
    """

    def __init__(self, results_dir: Path | str):
        self._dir = Path(results_dir)
        self._entries: dict[str, _TableEntry] = {}
        self._manifest_path = self._dir / "manifest.json"
        if self._manifest_path.exists():
            self._load()

    def register_table(
        self, filename: str,
        display_name: dict[str, str] | str,
        category: str = "",
        order: int = 50,
        section_key: str | None = None,
        source_model_fingerprint: str | None = None,
    ):
        """Add or update a table entry."""
        if isinstance(display_name, str):
            display_name = {"en": display_name, "fa": display_name}
        self._entries[filename] = _TableEntry(
            filename,
            display_name,
            category,
            order,
            RESULT_TABLE_SCHEMA_VERSION,
            section_key,
            source_model_fingerprint,
        )
        self._save()

    def get_ordered_files(self, custom_order: list[str] | None = None) -> list[Path]:
        """Return paths to JSON files in display order."""
        if custom_order:
            ordered = [
                self._dir / f for f in custom_order
                if (self._dir / f).exists()
            ]
            # Add any remaining files not in custom_order
            remaining = sorted(
                f for f in self._entries
                if f not in custom_order and (self._dir / f).exists()
            )
            ordered.extend(self._dir / f for f in remaining)
            return ordered

        # Use manifest order
        entries = sorted(self._entries.values(), key=lambda e: (e.order, e.filename))
        return [self._dir / e.filename for e in entries if (self._dir / e.filename).exists()]

    def get_display_name(self, filename: str, lang: str = "fa") -> str:
        """Get localized display name for a table file."""
        entry = self._entries.get(filename)
        if entry:
            return entry.display_name.get(lang, entry.display_name.get("en", filename))
        return Path(filename).stem.replace("_", " ").title()

    # ── Persistence ───────────────────────────────────────────────────

    def _save(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            fn: {
                "display_name": e.display_name,
                "category": e.category,
                "order": e.order,
                "schema_version": e.schema_version,
                "section_key": e.section_key,
                "model_fingerprint": e.model_fingerprint,
            }
            for fn, e in self._entries.items()
        }
        self._manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        data = json.loads(self._manifest_path.read_text("utf-8"))
        for fn, meta in data.items():
            self._entries[fn] = _TableEntry(
                filename=fn,
                display_name=meta.get("display_name", {"en": fn}),
                category=meta.get("category", ""),
                order=meta.get("order", 50),
                schema_version=meta.get("schema_version"),
                section_key=meta.get("section_key"),
                model_fingerprint=meta.get("model_fingerprint"),
            )
