"""Icon resource helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

_ICONS_DIR = Path(__file__).resolve().parent


def icon(name: str) -> QIcon:
    """Return a QIcon for the given icon filename (e.g. ``'torsion.svg'``).

    Falls back to a null QIcon if the file does not exist.
    """
    path = _ICONS_DIR / name
    if path.exists():
        return QIcon(str(path))
    # Try without extension
    for ext in ('.svg', '.png'):
        candidate = _ICONS_DIR / f"{name}{ext}"
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def icon_path(name: str) -> str:
    """Return the absolute path string for an icon file."""
    path = _ICONS_DIR / name
    if path.exists():
        return str(path)
    for ext in ('.svg', '.png'):
        candidate = _ICONS_DIR / f"{name}{ext}"
        if candidate.exists():
            return str(candidate)
    return ""


# Mapping: command_id → icon filename
COMMAND_ICONS: dict[str, str] = {
    "torsion": "torsion.svg",
    "drift": "drift.svg",
    "joint_shear": "joint_shear.svg",
    "design_columns": "run_concrete_design.svg",
    "columns_control": "columns_control.svg",
    "dynamic_scale": "spectral.svg",
    "settings": "settings.svg",
    "edit_frame_sections": "frame_sections.svg",
    "aj_correction": "show_aj.svg",
    "live_load": "wall_load.svg",
    "get_weakness": "weakness.svg",
    "show_weakness": "show_weakness.svg",
    "story_stiffness": "stiffness.svg",
    "show_story_stiffness": "show_stiffness.svg",
    "beam_deflection": "deflection.svg",
    "columns_100_30": "100_30.svg",
    "high_pressure_columns": "high_pressure_columns.svg",
    "story_forces": "shear.svg",
    "diaphragm_forces": "mass.svg",
    "earthquake_factor": "cfactor.svg",
    "beam_j": "beam_j_torsion.svg",
    "assigns": "assigns.svg",
    "assign_modifiers": "assign_modifiers.svg",
    "assign_ev": "assign_ev.svg",
    "wall_load": "wall_load.svg",
    "explode_seismic": "explode.svg",
    "create_load_combinations": "load_combination.svg",
    "create_spectral": "spectral.svg",
    "create_section_cuts": "cut.svg",
    "match_property": "match_property.svg",
    "offset": "offset.svg",
    "create_25percent": "create_25percent_file.svg",
    "extract_rebars": "rebars.svg",
    "copy_elements_between_models": "transfer_loads_between_two_files.svg",
}

# Special icons for app-level use
APP_ICON = "civiltools.svg"
CONNECT_ICON = "connect.svg"
REPORT_ICON = "word.svg"
QUIT_ICON = "quit.svg"
HELP_ICON = "about.svg"
