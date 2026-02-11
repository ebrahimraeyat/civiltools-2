"""
Bilingual string constants for structural engineering reports.

Keys are used throughout the report generators.  Each key maps to
``{'fa': '…', 'en': '…'}`` with Persian and English translations.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
# Master bilingual dictionary
# ═══════════════════════════════════════════════════════════════════════════

_STRINGS: dict[str, dict[str, str]] = {
    # ── Earthquake load cases ─────────────────────────────────────────
    "EX":  {"fa": "بار زلزله در جهت X", "en": "Earthquake Load in X Direction"},
    "EXP": {"fa": "بار زلزله در جهت X با خروج از مرکز مثبت", "en": "EQ X + Positive Eccentricity"},
    "EXN": {"fa": "بار زلزله در جهت X با خروج از مرکز منفی", "en": "EQ X + Negative Eccentricity"},
    "EY":  {"fa": "بار زلزله در جهت Y", "en": "Earthquake Load in Y Direction"},
    "EYP": {"fa": "بار زلزله در جهت Y با خروج از مرکز مثبت", "en": "EQ Y + Positive Eccentricity"},
    "EYN": {"fa": "بار زلزله در جهت Y با خروج از مرکز منفی", "en": "EQ Y + Negative Eccentricity"},

    # ── Project info ──────────────────────────────────────────────────
    "PROJECT_INFO":           {"fa": "اطلاعات پروژه", "en": "Project Information"},
    "PROVINCE":               {"fa": "استان", "en": "Province"},
    "CITY":                   {"fa": "شهر", "en": "City"},
    "RISK_LEVEL":             {"fa": "خطرپذیری نسبی", "en": "Relative Risk Level"},
    "SOIL_TYPE":              {"fa": "نوع خاک", "en": "Soil Type"},
    "IMPORTANCE_FACTOR":      {"fa": "ضریب اهمیت", "en": "Importance Factor"},
    "DESIGN_BASE_ACCELERATION": {"fa": "شتاب مبنای طرح", "en": "Design Base Acceleration"},
    "BUILDING_USAGE":         {"fa": "کاربری ساختمان", "en": "Building Usage"},

    # ── Seismic parameters ────────────────────────────────────────────
    "BOT_STORY_APPLY_EARTHQUAKE": {"fa": "طبقه پایین اعمال زلزله", "en": "Bottom Story for Earthquake"},
    "TOP_STORY_APPLY_EARTHQUAKE": {"fa": "طبقه بالای اعمال زلزله", "en": "Top Story for Earthquake"},
    "TOP_STORY_FOR_T":            {"fa": "طبقه بالا برای محاسبه T", "en": "Top Story for Period Calc"},
    "NO_STORIES":                 {"fa": "تعداد طبقات", "en": "Number of Stories"},
    "HEIGHT_METER":               {"fa": "ارتفاع ساختمان (متر)", "en": "Building Height (m)"},
    "INFILL_PANNEL":              {"fa": "میانقاب", "en": "Infill Panel"},
    "STIFFNESS_10_TIMES":         {"fa": "سختی 10 برابر اعضای سازه‌ای", "en": "Stiffness 10x Structural Members"},

    # ── Loads ─────────────────────────────────────────────────────────
    "LOADS_ON_STRUCTURE": {"fa": "بارهای وارد بر سازه", "en": "Loads on Structure"},
    "DEAD":               {"fa": "بار مرده", "en": "Dead Load"},
    "SDEAD":              {"fa": "بار مرده اضافی", "en": "Super Dead Load"},
    "PARTITION_DEAD":     {"fa": "بار تیغه‌بندی (مرده)", "en": "Partition Dead Load"},
    "LIVE":               {"fa": "بار زنده", "en": "Live Load"},
    "LIVE_REDUCIBLE":     {"fa": "بار زنده قابل کاهش", "en": "Reducible Live Load"},
    "LIVE_PARKING":       {"fa": "بار زنده پارکینگ", "en": "Parking Live Load"},
    "PARTITION_LIVE":     {"fa": "بار تیغه‌بندی (زنده)", "en": "Partition Live Load"},
    "LIVE_05":            {"fa": "بار زنده 0.5", "en": "Live Load 0.5"},
    "LIVE_ROOF":          {"fa": "بار زنده بام", "en": "Roof Live Load"},
    "SNOW":               {"fa": "بار برف", "en": "Snow Load"},
    "MASS":               {"fa": "جرم", "en": "Mass"},
    "EV_VERTICAL":        {"fa": "EV (بار قائم زلزله)", "en": "EV (Vertical Seismic)"},
    "MODAL":              {"fa": "مودال", "en": "Modal"},

    # ── Retaining walls ───────────────────────────────────────────────
    "HXP": {"fa": "فشار جانبی خاک X+", "en": "Lateral Soil Pressure X+"},
    "HXN": {"fa": "فشار جانبی خاک X-", "en": "Lateral Soil Pressure X-"},
    "HYP": {"fa": "فشار جانبی خاک Y+", "en": "Lateral Soil Pressure Y+"},
    "HYN": {"fa": "فشار جانبی خاک Y-", "en": "Lateral Soil Pressure Y-"},

    # ── Dynamic analysis ──────────────────────────────────────────────
    "DYNAMIC_LOAD_CASES":          {"fa": "حالات بار دینامیکی", "en": "Dynamic Load Cases"},
    "X_SCALE_FACTOR":              {"fa": "ضریب مقیاس جهت X", "en": "X Scale Factor"},
    "Y_SCALE_FACTOR":              {"fa": "ضریب مقیاس جهت Y", "en": "Y Scale Factor"},
    "SPECTRAL_WITHOUT_ECC":        {"fa": "طیفی بدون خروج از مرکز", "en": "Spectral without Eccentricity"},
    "SPECTRAL_WITH_ECC":           {"fa": "طیفی با خروج از مرکز", "en": "Spectral with Eccentricity"},
    "SPECTRAL_DRIFT_WITHOUT_ECC":  {"fa": "طیفی دریفت بدون خروج از مرکز", "en": "Spectral Drift w/o Eccentricity"},
    "SPECTRAL_DRIFT_WITH_ECC":     {"fa": "طیفی دریفت با خروج از مرکز", "en": "Spectral Drift with Eccentricity"},

    # ── Irregularities ────────────────────────────────────────────────
    "TORSIONAL_IRREGULARITY":      {"fa": "بی‌نظمی پیچشی", "en": "Torsional Irregularity"},
    "REENTRANT_CORNER":            {"fa": "بی‌نظمی گوشه فرورفته", "en": "Re-entrant Corner"},
    "DIAPHRAGM_DISCONTINUITY":     {"fa": "ناپیوستگی دیافراگم", "en": "Diaphragm Discontinuity"},
    "OUT_OF_PLANE_OFFSET":         {"fa": "برون‌صفحه‌ای", "en": "Out-of-Plane Offset"},
    "NON_PARALLEL_SYSTEM":         {"fa": "سیستم غیرموازی", "en": "Non-Parallel System"},
    "SOFT_STORY":                  {"fa": "طبقه نرم", "en": "Soft Story"},
    "WEIGHT_IRREGULARITY":         {"fa": "بی‌نظمی جرمی", "en": "Weight (Mass) Irregularity"},
    "GEOMETRIC_IRREGULARITY":      {"fa": "بی‌نظمی هندسی", "en": "Geometric Irregularity"},
    "IN_PLANE_DISCONTINUITY":      {"fa": "ناپیوستگی درون‌صفحه‌ای", "en": "In-Plane Discontinuity"},
    "WEAK_STORY":                  {"fa": "طبقه ضعیف", "en": "Weak Story"},
    "EXTREME_TORSIONAL":           {"fa": "بی‌نظمی پیچشی شدید", "en": "Extreme Torsional Irregularity"},
    "EXTREME_SOFT_STORY":          {"fa": "طبقه نرم شدید", "en": "Extreme Soft Story"},
    "EXTREME_WEAK_STORY":          {"fa": "طبقه ضعیف شدید", "en": "Extreme Weak Story"},
    "TORSIONAL_DRIFT":             {"fa": "نسبت دریفت پیچشی", "en": "Torsional Drift Ratio"},

    # ── Earthquake coefficient ────────────────────────────────────────
    "EARTHQUAKE_COEFFICIENT_CALC": {"fa": "محاسبه ضریب زلزله", "en": "Earthquake Coefficient Calculation"},
    "SEISMIC_PARAMS":              {"fa": "پارامترهای لرزه‌ای", "en": "Seismic Parameters"},
    "STATIC_EQ_LOADS":             {"fa": "بارهای معادل استاتیکی", "en": "Equivalent Static Loads"},
    "YES":                         {"fa": "بله", "en": "Yes"},
    "NO":                          {"fa": "خیر", "en": "No"},

    # ── Structural system ─────────────────────────────────────────────
    "STRUCTURAL_SYSTEM":  {"fa": "سیستم سازه‌ای", "en": "Structural System"},
    "LATERAL_TYPE":       {"fa": "نوع سیستم باربر جانبی", "en": "Lateral System Type"},
    "RU_FACTOR":          {"fa": "ضریب رفتار (Ru)", "en": "Response Modification Factor (Ru)"},
    "PHI0_FACTOR":        {"fa": "ضریب بزرگ‌نمایی (Φ₀)", "en": "Overstrength Factor (Φ₀)"},
    "CD_FACTOR":          {"fa": "ضریب بزرگ‌نمایی تغییرمکان (Cd)", "en": "Displacement Amp. Factor (Cd)"},
    "MAX_HEIGHT":         {"fa": "حداکثر ارتفاع مجاز (متر)", "en": "Maximum Allowable Height (m)"},
    "X_DIRECTION":        {"fa": "جهت X", "en": "X Direction"},
    "Y_DIRECTION":        {"fa": "جهت Y", "en": "Y Direction"},

    # ── Period & factors ──────────────────────────────────────────────
    "EMPIRICAL_PERIOD":    {"fa": "پریود تجربی", "en": "Empirical Period"},
    "ANALYTICAL_PERIOD":   {"fa": "پریود تحلیلی", "en": "Analytical Period"},
    "DESIGN_PERIOD":       {"fa": "پریود طراحی", "en": "Design Period"},
    "REFLECTION_FACTOR":   {"fa": "ضریب بازتاب", "en": "Reflection Factor"},
    "EARTHQUAKE_FACTOR":   {"fa": "ضریب زلزله", "en": "Earthquake Coefficient"},
    "K_DISTRIBUTION":      {"fa": "ضریب توزیع (K)", "en": "Distribution Factor (K)"},
    "DRIFT_EQ_FACTOR":     {"fa": "ضریب زلزله برای دریفت", "en": "Earthquake Coefficient (Drift)"},
    "DRIFT_K_DISTRIBUTION": {"fa": "ضریب توزیع برای دریفت", "en": "Distribution Factor K (Drift)"},

    # ── Spectral ──────────────────────────────────────────────────────
    "SPECTRAL_MOD_DESC":   {"fa": "مشخصات طیف", "en": "Spectrum Description"},
    "HIGH_HAZARD":         {"fa": "خطرپذیری زیاد و خیلی زیاد", "en": "High / Very-High Hazard"},
    "LOW_HAZARD":          {"fa": "خطرپذیری کم و متوسط", "en": "Low / Moderate Hazard"},

    # ── Report headings ───────────────────────────────────────────────
    "TABLE_OF_CONTENTS":       {"fa": "فهرست مطالب", "en": "Table of Contents"},
    "COLUMN_DESIGN_RESULTS":   {"fa": "نتایج طراحی ستون‌ها", "en": "Column Design Results"},
    "JOINT_SHEAR_RATIOS":      {"fa": "نسبت برش در گره‌ها", "en": "Joint Shear Ratios"},
    "STORY_DRIFT":             {"fa": "تغییرمکان نسبی طبقات", "en": "Story Drift"},
    "TORSION_IRREGULARITY_TABLE": {"fa": "جدول بی‌نظمی پیچشی", "en": "Torsional Irregularity Table"},
    "BEAM_REINFORCEMENT":      {"fa": "آرماتور تیرها", "en": "Beam Reinforcement"},
    "SPECTRAL_COMPARISON":     {"fa": "مقایسه طیفی", "en": "Spectral Comparison"},

    # ── Base shear ────────────────────────────────────────────────────
    "BASE_SHEAR":          {"fa": "برش پایه", "en": "Base Shear"},
    "BUILDING_WEIGHT":     {"fa": "وزن ساختمان", "en": "Building Weight"},
    "SEISMIC_COEFFICIENT": {"fa": "ضریب لرزه‌ای", "en": "Seismic Coefficient"},

    # ── Load combinations ─────────────────────────────────────────────
    "LOAD_COMBINATIONS":       {"fa": "ترکیبات بار", "en": "Load Combinations"},
    "COMBO_NAME":              {"fa": "نام ترکیب", "en": "Combination Name"},
    "LOAD_CASE":               {"fa": "حالت بار", "en": "Load Case"},
    "COMBO_TYPE":              {"fa": "نوع ترکیب", "en": "Type"},
    "SCALE_FACTOR":            {"fa": "ضریب مقیاس", "en": "Scale Factor"},

    # ── Story forces ──────────────────────────────────────────────────
    "STORY_FORCES":            {"fa": "نیروهای طبقات", "en": "Story Forces"},

    # ── Column design ─────────────────────────────────────────────────
    "PMM_COLUMNS":             {"fa": "نتایج طراحی ستون‌ها", "en": "Column PMM Design Results"},
    "PMM_RATIO":               {"fa": "نسبت PMM", "en": "PMM Ratio"},
    "DESIGN_SECTION":          {"fa": "مقطع طراحی", "en": "Design Section"},
    "PMM_COMBO":               {"fa": "ترکیب PMM", "en": "PMM Combo"},

    # ── Story plans ───────────────────────────────────────────────────
    "STORY_PLANS":             {"fa": "پلان تیر و ستون طبقات", "en": "Story Plans — Beams & Columns"},
    "AREA_LOAD_PLANS":         {"fa": "پلان بارگذاری سطوح", "en": "Area Load Plans"},
    "LOAD_SET":                {"fa": "گروه بار", "en": "Load Set"},
    "SECTION_NAME":            {"fa": "نام مقطع", "en": "Section Name"},

    # ── Report misc ───────────────────────────────────────────────────
    "REPORT_TITLE":            {"fa": "گزارش مهندسی سازه", "en": "Structural Engineering Report"},
    "GENERATED_BY":            {"fa": "تولید شده توسط civilTools", "en": "Generated by civilTools"},
    "PAGE":                    {"fa": "صفحه", "en": "Page"},
    "ALL_OK":                  {"fa": "تمام بررسی‌ها قبول", "en": "All checks passed"},
    "SOME_FAIL":               {"fa": "برخی بررسی‌ها مردود", "en": "Some checks failed"},
    "NOT_AVAILABLE":           {"fa": "در دسترس نیست", "en": "Data not available"},
}


# ═══════════════════════════════════════════════════════════════════════════
# Access helpers
# ═══════════════════════════════════════════════════════════════════════════

def get_string(key: str, lang: str = "fa") -> str:
    """Get a localized string by key and language."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("en", key))


def get_all_strings(lang: str = "fa") -> dict[str, str]:
    """Get all strings for a language as a flat dict."""
    return {k: v.get(lang, v.get("en", k)) for k, v in _STRINGS.items()}


class _StringAccessor:
    """Attribute-style access: ``S.EX['fa']`` → Persian EX string."""

    def __getattr__(self, name: str) -> dict[str, str]:
        if name.startswith("_"):
            raise AttributeError(name)
        entry = _STRINGS.get(name)
        if entry is None:
            raise AttributeError(f"Unknown string key: {name}")
        return entry


S = _StringAccessor()
