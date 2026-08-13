"""
civilTools configuration manager — reads/writes settings to ETABS ProjectInfo.

Ported from civilTools/exporter/civiltools_config.py with improvements:
- All ``exec()`` calls replaced with ``getattr()``/``setattr()``
- PySide → PySide6
- No FreeCAD dependency
"""

from __future__ import annotations

import json
import csv
import copy
import math
from pathlib import Path
from typing import Any, Union

_DB_DIR = Path(__file__).resolve().parent.parent / "db"


# ─── Core read/write ────────────────────────────────────────────────

def get_settings_from_etabs(etabs) -> dict[str, Any]:
    """Read civilTools JSON from ETABS ProjectInfo 'Company Name' field."""
    d: dict[str, Any] = {}
    try:
        info = etabs.SapModel.GetProjectInfo(0)
    except Exception:
        return d
    json_str = info[2][0]
    try:
        company_name = json.loads(json_str)
    except (json.JSONDecodeError, TypeError, IndexError):
        return d
    if isinstance(company_name, dict):
        d = company_name
    return d


def set_settings_to_etabs(etabs, d: dict):
    """Write civilTools JSON to ETABS ProjectInfo and save."""
    json_str = json.dumps(d)
    etabs.SapModel.SetProjectInfo("Company Name", json_str)
    etabs.SapModel.File.Save()
    try:
        name = etabs.get_file_name_without_suffix()
        json_file_name = f"{name}_model_settings.json"
        filename = etabs.get_json_file_path_for_table_results(
            json_filename=json_file_name
        )
        if filename and isinstance(filename, Path):
            if not filename.parent.exists():
                filename.parent.mkdir(parents=True)
            with open(filename, "w") as f:
                json.dump(d, f, indent=4)
    except (PermissionError, Exception):
        pass


def update_setting(etabs, keys: Union[list, dict], values=None):
    """Partial update of ETABS settings dictionary."""
    d = get_settings_from_etabs(etabs)
    if isinstance(keys, dict):
        d.update(keys)
    else:
        d.update(dict(zip(keys, values)))
    set_settings_to_etabs(etabs, d)


# ─── Save from widget ──────────────────────────────────────────────

_COMBOBOX_KEYS = (
    "ostan", "city", "risk_level", "soil_type", "importance_factor",
    "bot_x_combo", "top_x_combo", "top_story_for_height",
    "bot_x1_combo", "top_x1_combo", "top_story_for_height1",
    "dead_combobox", "sdead_combobox", "partition_dead_combobox",
    "live_combobox", "lred_combobox", "live_parking_combobox",
    "lroof_combobox", "live5_combobox", "lred5_combobox",
    "partition_live_combobox", "mass_combobox", "ev_combobox",
    "hxp_combobox", "hxn_combobox", "hyp_combobox", "hyn_combobox",
    "ex_combobox", "exp_combobox", "exn_combobox",
    "ey_combobox", "eyp_combobox", "eyn_combobox",
    "rhox_combobox", "rhoy_combobox",
    "ex1_combobox", "exp1_combobox", "exn1_combobox",
    "ey1_combobox", "eyp1_combobox", "eyn1_combobox",
    "rhox1_combobox", "rhoy1_combobox",
    "sx_combobox", "sxe_combobox", "sy_combobox", "sye_combobox",
    "ex_drift_combobox", "exp_drift_combobox", "exn_drift_combobox",
    "ey_drift_combobox", "eyp_drift_combobox", "eyn_drift_combobox",
    "rhox_drift_combobox", "rhoy_drift_combobox",
    "ex1_drift_combobox", "exp1_drift_combobox", "exn1_drift_combobox",
    "ey1_drift_combobox", "eyp1_drift_combobox", "eyn1_drift_combobox",
    "rhox1_drift_combobox", "rhoy1_drift_combobox",
    "sx_drift_combobox", "sxe_drift_combobox",
    "sy_drift_combobox", "sye_drift_combobox",
    "x_scalefactor_combobox", "y_scalefactor_combobox",
    "modal_combobox", "snow_combobox",
)

_SPINBOX_KEYS = (
    "height_x", "no_of_story_x", "height_x1", "no_of_story_x1",
    "t_an_x", "t_an_y", "t_an_x1", "t_an_y1",
    "tx_an", "ty_an", "tx1_an", "ty1_an", "tx_all_an", "ty_all_an",
)

_CHECKBOX_KEYS = (
    "top_story_for_height_checkbox", "infill",
    "top_story_for_height_checkbox_1", "infill_1",
    "activate_second_system", "special_case",
    "dynamic_analysis_groupbox", "partition_dead_checkbox",
    "torsional_irregularity_groupbox",
    "torsion_irregular_checkbox", "extreme_torsion_irregular_checkbox",
    "reentrance_corner_checkbox", "diaphragm_discontinuity_checkbox",
    "out_of_plane_offset_checkbox", "nonparallel_system_checkbox",
    "stiffness_soft_story_groupbox",
    "stiffness_irregular_checkbox", "extreme_stiffness_irregular_checkbox",
    "weight_mass_checkbox", "geometric_checkbox",
    "in_plane_discontinuity_checkbox",
    "lateral_strength_weak_story_groupbox",
    "strength_irregular_checkbox", "extreme_strength_irregular_checkbox",
    "concrete_radiobutton", "steel_radiobutton",
    "combination_response_spectrum_checkbox",
    "angular_response_spectrum_checkbox",
    "retaining_wall_groupbox", "partition_live_checkbox",
)


def get_prop_from_widget(etabs, widget) -> dict:
    """Collect all widget values into a dict (no exec() calls)."""
    new_d: dict[str, Any] = {}

    for key in _COMBOBOX_KEYS:
        w = getattr(widget, key, None)
        if w is not None:
            new_d[key] = w.currentText()

    for key in _SPINBOX_KEYS:
        w = getattr(widget, key, None)
        if w is not None:
            new_d[key] = w.value()

    for key in _CHECKBOX_KEYS:
        w = getattr(widget, key, None)
        if w is not None:
            new_d[key] = w.isChecked()

    # Angular tableview
    atv = getattr(widget, "angular_tableview", None)
    if atv is not None:
        model = atv.model()
        if model is not None:
            dic = {}
            for row in range(model.rowCount()):
                angle = model.data(model.index(row, 0))
                spec = model.data(model.index(row, 1))
                sec_cut = model.data(model.index(row, 2))
                dic[angle] = (sec_cut, spec)
            new_d["angular_tableview"] = dic

    # Treeviews
    from civiltools.gui.models.treeview_system import get_treeview_item_prop
    try:
        from civiltools.building.RuTable import Ru
    except ImportError:
        Ru = {}

    for prefix, view_name in [
        ("x", "x_treeview"), ("y", "y_treeview"),
        ("x", "x_treeview_1"), ("y", "y_treeview_1"),
    ]:
        view = getattr(widget, view_name, None)
        if view is None:
            continue
        ret = get_treeview_item_prop(view)
        if ret is None:
            continue
        system, lateral, i, n = ret
        suffix = "_1" if "1" in view_name else ""
        new_d[f"{prefix}_system{suffix}"] = [i, n]
        new_d[f"{prefix}_system_name{suffix}"] = system
        new_d[f"{prefix}_lateral_name{suffix}"] = lateral
        if system in Ru and lateral in Ru[system]:
            cd_key = f"cd{prefix}{suffix.replace('_', '')}"
            ru_key = f"Ru{prefix}{suffix.replace('_', '')}"
            new_d[cd_key] = Ru[system][lateral][2]
            new_d[ru_key] = Ru[system][lateral][0]

    d = get_settings_from_etabs(etabs)
    d.update(new_d)
    return d


def save(etabs, widget) -> dict:
    """Save all widget values to ETABS."""
    d = get_prop_from_widget(etabs=etabs, widget=widget)
    set_settings_to_etabs(etabs, d)
    return d


# ─── Load into widget ──────────────────────────────────────────────

def _safe_set_combo(widget, key, text):
    w = getattr(widget, key, None)
    if w is None:
        return
    idx = w.findText(str(text))
    if idx == -1:
        w.addItem(str(text))
        idx = w.findText(str(text))
    w.setCurrentIndex(idx)


def _safe_set_checked(widget, key, checked: bool):
    w = getattr(widget, key, None)
    if w is not None:
        w.setChecked(checked)


def _safe_set_value(widget, key, value):
    w = getattr(widget, key, None)
    if w is not None:
        w.setValue(value)


def _safe_set_enabled(widget, key, enabled: bool):
    w = getattr(widget, key, None)
    if w is not None:
        w.setEnabled(enabled)


def load(etabs, widget=None, d=None, reverse=False, include_base=True):
    """Master load: populate widget from ETABS settings."""
    if d is None:
        d = get_settings_from_etabs(etabs)
    if widget is None:
        return d

    _fill_load_pattern_combos(etabs, widget)
    fill_cities(widget)
    fill_top_bot_stories(etabs, widget)
    fill_height_and_no_of_stories(etabs, widget)
    fill_stories(etabs, widget, reverse, include_base)

    keys = d.keys()

    _fill_seismic_combos(etabs, widget, d, drift=False)
    _fill_seismic_combos(etabs, widget, d, drift=True)
    _fill_seismic_lists(etabs, widget, d, drift=False)
    _fill_seismic_lists(etabs, widget, d, drift=True)
    _fill_dynamic_combos(etabs, widget, d)
    _fill_dynamic_lists(etabs, widget, d)
    _fill_dynamic_drift_lists(etabs, widget, d)
    _fill_angular_list(etabs, widget, d)
    _fill_angular_table(etabs, widget, d)

    for key in (
        "ostan", "city", "risk_level", "soil_type", "importance_factor",
        "bot_x_combo", "top_x_combo", "top_story_for_height",
        "bot_x1_combo", "top_x1_combo", "top_story_for_height1",
        "dead_combobox", "sdead_combobox", "partition_dead_combobox",
        "live_combobox", "lred_combobox", "live_parking_combobox",
        "lroof_combobox", "live5_combobox", "lred5_combobox",
        "partition_live_combobox", "mass_combobox", "ev_combobox",
        "hxp_combobox", "hxn_combobox", "hyp_combobox", "hyn_combobox",
        "rhox_combobox", "rhoy_combobox",
        "rhox1_combobox", "rhoy1_combobox",
        "x_scalefactor_combobox", "y_scalefactor_combobox",
        "modal_combobox", "snow_combobox",
    ):
        if key in keys and hasattr(widget, key):
            _safe_set_combo(widget, key, d[key])
        elif key in ("ostan", "city") and hasattr(widget, key):
            _safe_set_combo(widget, key, "قم")

    setA(widget, d)
    _load_checkboxes(widget, d)
    _load_response_spectrum_mode(widget, d)

    if "retaining_wall_groupbox" in keys and hasattr(widget, "retaining_wall_groupbox"):
        checked = d.get("retaining_wall_groupbox", False)
        widget.retaining_wall_groupbox.setChecked(checked)
        if checked:
            for w_name in ("hxp_combobox", "hxn_combobox", "hyp_combobox", "hyn_combobox"):
                _safe_set_enabled(widget, w_name, True)

    _load_second_system(widget, d)

    for key in ("height_x", "no_of_story_x", "height_x1", "no_of_story_x1"):
        if key in keys and hasattr(widget, key):
            _safe_set_value(widget, key, d[key])

    for old_key, new_key in zip(
        ("t_an_x", "t_an_y", "t_an_x1", "t_an_y1"),
        ("tx_an", "ty_an", "tx1_an", "ty1_an"),
    ):
        if old_key in keys:
            _safe_set_value(widget, old_key, d[old_key])
            _safe_set_value(widget, new_key, d[old_key])
        if new_key in keys:
            _safe_set_value(widget, new_key, d[new_key])

    _load_system_treeviews(widget, d)
    check_heights(etabs, widget)
    return d


def _fill_load_pattern_combos(etabs, widget):
    """Populate load-pattern and modal combo boxes from the ETABS model."""
    try:
        load_patterns = etabs.load_patterns.get_load_patterns()
    except Exception:
        return

    try:
        load_types = {lp: etabs.SapModel.LoadPatterns.GetLoadType(lp)[0] for lp in load_patterns}
    except Exception:
        load_types = {}

    live_loads = [""] + [lp for lp in load_patterns if load_types.get(lp) in (3, 4, 11)]
    other_loads = [""] + [lp for lp in load_patterns if load_types.get(lp) == 8]

    for combo_name in (
        "live_combobox", "lred_combobox", "lroof_combobox",
        "live5_combobox", "lred5_combobox", "live_parking_combobox",
    ):
        combo = getattr(widget, combo_name, None)
        if combo is not None:
            combo.clear()
            combo.addItems(live_loads)
            _select_first_real_item(combo)

    for combo_name in ("mass_combobox", "ev_combobox", "hxp_combobox", "hxn_combobox", "hyp_combobox", "hyn_combobox"):
        combo = getattr(widget, combo_name, None)
        if combo is not None:
            combo.clear()
            combo.addItems(other_loads)
            _select_first_real_item(combo)

    if hasattr(widget, "dead_combobox"):
        combo = widget.dead_combobox
        combo.clear()
        for lp in load_patterns:
            if load_types.get(lp) == 1:
                combo.addItem(lp)
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    if hasattr(widget, "sdead_combobox"):
        combo = widget.sdead_combobox
        combo.clear()
        for lp in load_patterns:
            if load_types.get(lp) == 2:
                combo.addItem(lp)
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    if hasattr(widget, "snow_combobox"):
        combo = widget.snow_combobox
        combo.clear()
        for lp in load_patterns:
            if load_types.get(lp) == 7:
                combo.addItem(lp)
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    for lp in load_patterns:
        load_type = load_types.get(lp)
        if load_type == 3 and "5" in lp:
            combo = getattr(widget, "live5_combobox", None)
            if combo is not None:
                combo.setCurrentIndex(combo.findText(lp))
        elif load_type == 4 and "5" in lp:
            combo = getattr(widget, "lred5_combobox", None)
            if combo is not None:
                combo.setCurrentIndex(combo.findText(lp))
        elif load_type == 8:
            lower = lp.lower()
            if "mass" in lower or "wall" in lower:
                combo = getattr(widget, "mass_combobox", None)
                if combo is not None:
                    combo.setCurrentIndex(combo.findText(lp))
            elif any(token in lower for token in ("ev", "ez", "qv", "qz")):
                combo = getattr(widget, "ev_combobox", None)
                if combo is not None:
                    combo.setCurrentIndex(combo.findText(lp))

    modal_combo = getattr(widget, "modal_combobox", None)
    if modal_combo is not None:
        try:
            modals = etabs.load_cases.get_loadcase_withtype(3)
        except Exception:
            modals = []
        modal_combo.clear()
        modal_combo.addItems(modals)
        if modal_combo.count() > 0:
            modal_combo.setCurrentIndex(0)


def _select_first_real_item(combo):
    """Select the first non-empty item; fall back to index 0."""
    if combo is None or combo.count() == 0:
        return
    for index in range(combo.count()):
        if combo.itemText(index).strip():
            combo.setCurrentIndex(index)
            return
    combo.setCurrentIndex(0)


# ─── Internal fill helpers ──────────────────────────────────────────

def _fill_seismic_combos(etabs, widget, d, drift=False):
    if drift:
        pairs = [
            ("ex_drift_combobox", "ex1_drift_combobox"),
            ("exn_drift_combobox", "exn1_drift_combobox"),
            ("exp_drift_combobox", "exp1_drift_combobox"),
            ("ey_drift_combobox", "ey1_drift_combobox"),
            ("eyn_drift_combobox", "eyn1_drift_combobox"),
            ("eyp_drift_combobox", "eyp1_drift_combobox"),
        ]
        try:
            seismic_loads = etabs.load_patterns.get_seismic_load_patterns(drifts=True)
        except Exception:
            return
    else:
        pairs = [
            ("ex_combobox", "ex1_combobox"),
            ("exn_combobox", "exn1_combobox"),
            ("exp_combobox", "exp1_combobox"),
            ("ey_combobox", "ey1_combobox"),
            ("eyn_combobox", "eyn1_combobox"),
            ("eyp_combobox", "eyp1_combobox"),
        ]
        try:
            seismic_loads = etabs.load_patterns.get_seismic_load_patterns()
        except Exception:
            return

    if not any(hasattr(widget, p[0]) or hasattr(widget, p[1]) for p in pairs):
        return

    for (e1, e2), names in zip(pairs, seismic_loads):
        for combo_key in (e1, e2):
            combo = getattr(widget, combo_key, None)
            if combo is None:
                continue
            names_set = set(names) if not isinstance(names, set) else names
            saved = d.get(combo_key)
            if saved:
                names_set.add(saved)
            if names_set:
                combo.clear()
                combo.addItems(sorted(names_set))
            if combo_key in d:
                idx = combo.findText(d[combo_key])
                if idx != -1:
                    combo.setCurrentIndex(idx)


def _fill_seismic_lists(etabs, widget, d, drift=False):
    from PySide6.QtCore import Qt
    if drift:
        x_list = getattr(widget, "x_drift_loadcase_list", None)
        y_list = getattr(widget, "y_drift_loadcase_list", None)
        getter = etabs.get_first_system_seismic_drift
        getter2 = etabs.get_second_system_seismic_drift
    else:
        x_list = getattr(widget, "x_loadcase_list", None)
        y_list = getattr(widget, "y_loadcase_list", None)
        getter = etabs.get_first_system_seismic
        getter2 = etabs.get_second_system_seismic

    if not (x_list and y_list):
        return
    try:
        ex, exn, exp, ey, eyn, eyp = getter(d)
    except Exception:
        return

    x_cases = [ex, exn, exp]
    y_cases = [ey, eyn, eyp]
    if d.get("activate_second_system", False):
        try:
            ex1, exn1, exp1, ey1, eyn1, eyp1 = getter2(d)
            x_cases.extend([ex1, exn1, exp1])
            y_cases.extend([ey1, eyn1, eyp1])
        except Exception:
            pass

    for lw, cases in [(x_list, x_cases), (y_list, y_cases)]:
        lw.addItems(cases)
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)


def _fill_dynamic_combos(etabs, widget, d):
    combo_keys = (
        "sx_combobox", "sxe_combobox", "sy_combobox", "sye_combobox",
        "sx_drift_combobox", "sxe_drift_combobox",
        "sy_drift_combobox", "sye_drift_combobox",
    )
    if not any(hasattr(widget, k) for k in combo_keys):
        return
    try:
        sx, sxe, sy, sye = etabs.load_cases.get_response_spectrum_sxye_loadcases_names()
    except Exception:
        return
    all_rs = sx.union(sxe).union(sy).union(sye)
    sources = (sx, sxe, sy, sye, sx, sxe, sy, sye)
    for key, spectrum_lc in zip(combo_keys, sources):
        combo = getattr(widget, key, None)
        if combo is None or not spectrum_lc:
            continue
        lc = set(spectrum_lc)
        if "drift" in key and len(lc) == 1:
            combo.clear()
            combo.addItem(f"{lc.pop()}_drift")
            continue
        saved = d.get(key)
        if saved and saved in all_rs:
            lc.add(saved)
        combo.clear()
        combo.addItems(sorted(lc))
        if key in d:
            idx = combo.findText(d[key])
            if idx != -1:
                combo.setCurrentIndex(idx)

    if "dynamic_analysis_groupbox" in d and hasattr(widget, "dynamic_analysis_groupbox"):
        widget.dynamic_analysis_groupbox.setChecked(d.get("dynamic_analysis_groupbox", False))


def _fill_dynamic_lists(etabs, widget, d):
    from PySide6.QtCore import Qt
    x_list = getattr(widget, "x_dynamic_loadcase_list", None)
    y_list = getattr(widget, "y_dynamic_loadcase_list", None)
    if not (x_list and y_list):
        return
    try:
        sx, sxe, sy, sye = etabs.get_dynamic_loadcases(d)
    except Exception:
        return
    x_list.addItems((sx, sxe))
    y_list.addItems((sy, sye))
    for lw in (x_list, y_list):
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)


def _fill_dynamic_drift_lists(etabs, widget, d):
    from PySide6.QtCore import Qt
    x_list = getattr(widget, "x_dynamic_drift_loadcase_list", None)
    y_list = getattr(widget, "y_dynamic_drift_loadcase_list", None)
    if not (x_list and y_list):
        return
    try:
        sx, sxe, sy, sye = etabs.get_dynamic_drift_loadcases(d)
    except Exception:
        return
    x_list.addItems((sx, sxe))
    y_list.addItems((sy, sye))
    for lw in (x_list, y_list):
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)


def _fill_angular_list(etabs, widget, d):
    from PySide6.QtCore import Qt
    lw = getattr(widget, "angular_loadcase_list", None)
    if lw is None:
        return
    try:
        angles, _, specs, _ = etabs.load_cases.get_angular_response_spectrum_with_section_cuts()
    except Exception:
        return
    dic = d.get("angular_tableview")
    if dic is not None:
        for angle, cut_spec in dic.items():
            if float(angle) in angles:
                specs.append(cut_spec[1])
        lw.addItems(sorted(set(specs)))
        for i in range(lw.count()):
            item = lw.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)


def _fill_angular_table(etabs, widget, d):
    table = getattr(widget, "angular_tableview", None)
    if table is None:
        return
    try:
        angles, section_cuts, spectra, all_spectra = (
            etabs.load_cases.get_angular_response_spectrum_with_section_cuts()
        )
    except Exception:
        return

    spectra = list(spectra)
    section_cuts = list(section_cuts)
    saved_rows = d.get("angular_tableview", {})
    for row, angle in enumerate(angles):
        saved = next(
            (
                value
                for saved_angle, value in saved_rows.items()
                if float(saved_angle) == float(angle)
            ),
            None,
        )
        if not saved or len(saved) != 2:
            continue
        section_cut, spectrum = saved
        section_cuts[row] = section_cut
        spectra[row] = spectrum

    from civiltools.gui.table_models import AngularSpectrumDelegate, AngularSpectrumModel

    table.setModel(AngularSpectrumModel(angles, spectra, section_cuts, all_spectra))
    table.setItemDelegate(AngularSpectrumDelegate(table))


def _load_checkboxes(widget, d):
    for key in (
        "infill", "infill_1", "special_case",
        "torsional_irregularity_groupbox",
        "torsion_irregular_checkbox", "extreme_torsion_irregular_checkbox",
        "reentrance_corner_checkbox", "diaphragm_discontinuity_checkbox",
        "out_of_plane_offset_checkbox", "nonparallel_system_checkbox",
        "stiffness_soft_story_groupbox",
        "stiffness_irregular_checkbox", "extreme_stiffness_irregular_checkbox",
        "weight_mass_checkbox", "geometric_checkbox", "in_plane_discontinuity_checkbox",
        "lateral_strength_weak_story_groupbox",
        "strength_irregular_checkbox", "extreme_strength_irregular_checkbox",
    ):
        if key in d and hasattr(widget, key):
            _safe_set_checked(widget, key, d[key])

    for key, target in [
        ("top_story_for_height_checkbox", "top_story_for_height"),
        ("top_story_for_height_checkbox_1", "top_story_for_height1"),
    ]:
        if key in d and hasattr(widget, key):
            checked = d.get(key, True)
            _safe_set_checked(widget, key, checked)
            _safe_set_enabled(widget, target, checked)

    if hasattr(widget, "steel_radiobutton") and hasattr(widget, "concrete_radiobutton"):
        if "steel_radiobutton" in d:
            _safe_set_checked(widget, "steel_radiobutton", d["steel_radiobutton"])

    if "partition_dead_checkbox" in d and hasattr(widget, "partition_dead_checkbox"):
        checked = d.get("partition_dead_checkbox", False)
        _safe_set_checked(widget, "partition_dead_checkbox", checked)
        _safe_set_enabled(widget, "partition_dead_combobox", checked)
        _safe_set_checked(widget, "partition_live_checkbox", not checked)
        _safe_set_enabled(widget, "partition_live_combobox", not checked)


def _load_response_spectrum_mode(widget, d):
    from civiltools.gui.helpers import set_children_enabled
    key = "combination_response_spectrum_checkbox"
    if key in d and hasattr(widget, key):
        checked = d.get(key, True)
        _safe_set_checked(widget, key, checked)
        for group_name in ("dynamic_group_x", "dynamic_group_y"):
            group = getattr(widget, group_name, None)
            if group is not None:
                group.setEnabled(checked)
                set_children_enabled(group, checked)
        _safe_set_enabled(widget, "y_scalefactor_combobox", checked)
        _safe_set_enabled(widget, "angular_tableview", not checked)

    key = "angular_response_spectrum_checkbox"
    if key in d and hasattr(widget, key):
        checked = d.get(key, False)
        _safe_set_checked(widget, key, checked)
        _safe_set_enabled(widget, "x_dynamic_loadcase_list", not checked)
        _safe_set_enabled(widget, "y_dynamic_loadcase_list", not checked)


def _load_second_system(widget, d):
    if "activate_second_system" not in d or not hasattr(widget, "activate_second_system"):
        return
    checked = d.get("activate_second_system", False)
    _safe_set_checked(widget, "activate_second_system", checked)
    if checked:
        for w_name in (
            "ex1_combobox", "ey1_combobox", "exp1_combobox", "eyp1_combobox",
            "exn1_combobox", "eyn1_combobox",
            "x_system_label", "y_system_label",
            "x_treeview_1", "y_treeview_1",
            "stories_for_apply_earthquake_groupox",
            "stories_for_height_groupox",
            "infill_1", "second_earthquake_properties",
            "second_earthquake_properties_drifts", "special_case",
        ):
            _safe_set_enabled(widget, w_name, True)
    if hasattr(widget, "top_story_for_height_checkbox") and checked:
        _safe_set_checked(widget, "top_story_for_height_checkbox", False)
        _safe_set_enabled(widget, "top_story_for_height_checkbox", False)
        _safe_set_enabled(widget, "top_story_for_height", False)


def _load_system_treeviews(widget, d):
    from civiltools.gui.models.treeview_system import (
        load_system_nodes, setup_system_treeview, select_treeview_item,
    )
    nodes = load_system_nodes()
    for view_name in ("x_treeview", "y_treeview", "x_treeview_1", "y_treeview_1"):
        view = getattr(widget, view_name, None)
        if view is not None:
            setup_system_treeview(view, nodes)

    if hasattr(widget, "x_treeview") and hasattr(widget, "y_treeview"):
        select_treeview_item(widget.x_treeview, *d.get("x_system", [2, 1]))
        select_treeview_item(widget.y_treeview, *d.get("y_system", [2, 1]))
    if hasattr(widget, "x_treeview_1") and hasattr(widget, "y_treeview_1"):
        select_treeview_item(widget.x_treeview_1, *d.get("x_system_1", [2, 1]))
        select_treeview_item(widget.y_treeview_1, *d.get("y_system_1", [2, 1]))


# ─── Widget populate helpers ────────────────────────────────────────

def fill_cities(widget):
    if not hasattr(widget, "ostan"):
        return
    from civiltools.db import ostanha
    widget.ostan.addItems(list(ostanha.ostans.keys()))


def fill_stories(etabs, widget, reverse=False, include_base=True):
    lw = getattr(widget, "stories", None)
    if lw is None:
        return
    stories = etabs.story.get_sorted_story_name(reverse=reverse, include_base=include_base)
    lw.addItems(stories)
    for i in range(lw.count()):
        lw.item(i).setSelected(True)


def fill_top_bot_stories(etabs, widget):
    try:
        stories = etabs.story.get_sorted_story_name(reverse=False, include_base=True)
    except Exception:
        return
    for name in ("bot_x_combo", "top_x_combo", "top_story_for_height",
                 "bot_x1_combo", "top_x1_combo", "top_story_for_height1"):
        combo = getattr(widget, name, None)
        if combo is not None:
            combo.addItems(stories)
    n = len(stories)
    if hasattr(widget, "bot_x_combo"):
        widget.bot_x_combo.setCurrentIndex(0)
    if hasattr(widget, "top_x_combo"):
        widget.top_x_combo.setCurrentIndex(n - 1)
    if hasattr(widget, "top_story_for_height"):
        widget.top_story_for_height.setCurrentIndex(max(n - 2, 0))


def fill_height_and_no_of_stories(etabs, widget):
    if not (hasattr(widget, "height_x") and hasattr(widget, "no_of_story_x")):
        return
    try:
        checkbox = getattr(widget, "top_story_for_height_checkbox", None)
        if checkbox and checkbox.isChecked():
            top = widget.top_story_for_height.currentText()
        else:
            top = widget.top_x_combo.currentText()
        bot = widget.bot_x_combo.currentText()
        bot_level, top_level, _, _ = etabs.story.get_top_bot_levels(bot, top, bot, top, False)
        hx, _ = etabs.story.get_heights(bot, top, bot, top, False)
        nx, _ = etabs.story.get_no_of_stories(bot_level, top_level, bot_level, top_level)
        widget.no_of_story_x.setValue(nx)
        widget.height_x.setValue(hx)
    except Exception:
        pass


def check_heights(etabs, widget):
    if not hasattr(widget, "height_x"):
        return
    try:
        checkbox = getattr(widget, "top_story_for_height_checkbox", None)
        top = widget.top_story_for_height.currentText() if (checkbox and checkbox.isChecked()) else widget.top_x_combo.currentText()
        bot = widget.bot_x_combo.currentText()
        hx_model, _ = etabs.story.get_heights(bot, top, bot, top, False)
        hx_widget = widget.height_x.value()
        if not math.isclose(hx_model, hx_widget, abs_tol=0.01):
            widget.height_x.setStyleSheet(
                "QDoubleSpinBox { background-color: yellow; color: black; }"
            )
        else:
            widget.height_x.setStyleSheet("")
    except Exception:
        pass


def setA(widget, d):
    if not hasattr(widget, "risk_level"):
        return
    sotoh = ["خیلی زیاد", "زیاد", "متوسط", "کم"]
    w = widget.risk_level
    if w.count() == 0:
        w.addItems(sotoh)
    risk = d.get("risk_level", sotoh[1])
    idx = w.findText(risk)
    if idx != -1:
        w.setCurrentIndex(idx)
    acc_widget = getattr(widget, "acc", None)
    if acc_widget is not None and "risk_level" in d:
        accs = ["کم", "متوسط", "زیاد", "خیلی زیاد"]
        try:
            acc_widget.setCurrentIndex(accs.index(d["risk_level"]))
        except ValueError:
            pass


# ─── Period / Cd helpers ────────────────────────────────────────────

def save_analytical_periods(etabs, tx, ty, tx1=4, ty1=4):
    d = get_settings_from_etabs(etabs)
    d.update({"tx_an": tx, "ty_an": ty, "tx1_an": tx1, "ty1_an": ty1})
    set_settings_to_etabs(etabs, d)


def get_analytical_periods(etabs):
    d = get_settings_from_etabs(etabs)
    return (
        d.get("t_an_x", d.get("tx_an", 4)),
        d.get("t_an_y", d.get("ty_an", 4)),
        d.get("t_an_x1", d.get("tx1_an", 4)),
        d.get("t_an_y1", d.get("ty1_an", 4)),
    )


def save_cd(etabs, cdx, cdy, cdx1=0, cdy1=0):
    d = get_settings_from_etabs(etabs)
    d.update({"cdx": cdx, "cdy": cdy, "cdx1": cdx1, "cdy1": cdy1})
    set_settings_to_etabs(etabs, d)


def get_cd(etabs):
    d = get_settings_from_etabs(etabs)
    return d.get("cdx"), d.get("cdy"), d.get("cdx1", 0), d.get("cdy1", 0)


# ─── Building construction ─────────────────────────────────────────

def current_building_from_etabs(etabs):
    return current_building_from_config(get_settings_from_etabs(etabs))


def current_building_from_config(d):
    from civiltools.building.build import Building, StructureSystem
    x_system = StructureSystem(d["x_system_name"], d["x_lateral_name"], "X")
    y_system = StructureSystem(d["y_system_name"], d["y_lateral_name"], "Y")

    x_system1 = y_system1 = None
    if d.get("activate_second_system", False):
        x_system1 = StructureSystem(d["x_system_name_1"], d["x_lateral_name_1"], "X")
        y_system1 = StructureSystem(d["y_system_name_1"], d["y_lateral_name_1"], "Y")

    return Building(
        d["risk_level"], float(d["importance_factor"]), d["soil_type"], d["city"],
        d["no_of_story_x"], d["height_x"], d["infill"], x_system, y_system,
        d.get("tx_an", d.get("t_an_x", 4)), d.get("ty_an", d.get("t_an_y", 4)),
        x_system1, y_system1, d.get("height_x1", 0), d.get("infill_1", False),
        d.get("no_of_story_x1", 0), d.get("tx1_an", d.get("t_an_x1", 4)),
        d.get("ty1_an", d.get("t_an_y1", 4)), d.get("tx_all_an", 4), d.get("ty_all_an", 4),
    )


def current_building_from_widget(widget):
    from civiltools.building.build import Building, StructureSystem
    from civiltools.gui.models.treeview_system import get_treeview_item_prop

    def _get_system(view):
        ret = get_treeview_item_prop(view)
        if ret is None:
            return None
        system, lateral, *_ = ret
        direction = "X" if "x" in view.objectName() else "Y"
        return StructureSystem(system, lateral, direction)

    x_sys = _get_system(widget.x_treeview)
    y_sys = _get_system(widget.y_treeview)
    if x_sys is None or y_sys is None:
        return None

    x_sys2 = y_sys2 = None
    if widget.activate_second_system.isChecked():
        x_sys2 = _get_system(widget.x_treeview_1)
        y_sys2 = _get_system(widget.y_treeview_1)

    def _spin(name, default=4):
        w = getattr(widget, name, None)
        return w.value() if w is not None else default

    return Building(
        widget.risk_level.currentText(), float(widget.importance_factor.currentText()),
        widget.soil_type.currentText(), widget.city.currentText(),
        widget.no_of_story_x.value(), widget.height_x.value(),
        widget.infill.isChecked(), x_sys, y_sys,
        _spin("tx_an"), _spin("ty_an"),
        x_sys2, y_sys2, widget.height_x1.value(),
        widget.infill_1.isChecked(), widget.no_of_story_x1.value(),
        _spin("tx1_an"), _spin("ty1_an"), _spin("tx_all_an"), _spin("ty_all_an"),
    )


# ─── Seismic name accessors ────────────────────────────────────────

def get_first_system_seismic(widget):
    return (
        widget.ex_combobox.currentText(), widget.exn_combobox.currentText(),
        widget.exp_combobox.currentText(), widget.ey_combobox.currentText(),
        widget.eyn_combobox.currentText(), widget.eyp_combobox.currentText(),
    )


def get_first_system_seismic_drift(widget):
    return (
        widget.ex_drift_combobox.currentText(), widget.exn_drift_combobox.currentText(),
        widget.exp_drift_combobox.currentText(), widget.ey_drift_combobox.currentText(),
        widget.eyn_drift_combobox.currentText(), widget.eyp_drift_combobox.currentText(),
    )


def get_second_system_seismic(widget):
    return (
        widget.ex1_combobox.currentText(), widget.exn1_combobox.currentText(),
        widget.exp1_combobox.currentText(), widget.ey1_combobox.currentText(),
        widget.eyn1_combobox.currentText(), widget.eyp1_combobox.currentText(),
    )


def get_second_system_seismic_drift(widget):
    return (
        widget.ex1_drift_combobox.currentText(), widget.exn1_drift_combobox.currentText(),
        widget.exp1_drift_combobox.currentText(), widget.ey1_drift_combobox.currentText(),
        widget.eyn1_drift_combobox.currentText(), widget.eyp1_drift_combobox.currentText(),
    )


def ensure_required_loads_exist(
    etabs,
    widget,
    spectrum_function: str | None = None,
    allow_dynamic_without_function: bool = False,
):
    """Create missing required load patterns/load cases from current settings."""
    _ensure_retaining_wall_load_patterns(etabs, widget)
    _ensure_dynamic_loadcases(
        etabs,
        widget,
        spectrum_function=spectrum_function,
        allow_without_function=allow_dynamic_without_function,
    )


def _ensure_retaining_wall_load_patterns(etabs, widget):
    group = getattr(widget, "retaining_wall_groupbox", None)
    if group is None or not group.isChecked():
        return

    existing = set(etabs.load_patterns.get_load_patterns())
    for key in ("hxp_combobox", "hxn_combobox", "hyp_combobox", "hyn_combobox"):
        combo = getattr(widget, key, None)
        if combo is None:
            continue
        name = combo.currentText().strip()
        if name and name not in existing:
            etabs.SapModel.LoadPatterns.Add(name, 8)
            existing.add(name)


def _ensure_dynamic_loadcases(
    etabs,
    widget,
    spectrum_function: str | None = None,
    allow_without_function: bool = False,
):
    group = getattr(widget, "dynamic_analysis_groupbox", None)
    if group is None or not group.isChecked():
        return

    dynamic_keys = (
        "sx_combobox", "sxe_combobox", "sy_combobox", "sye_combobox",
        "sx_drift_combobox", "sxe_drift_combobox", "sy_drift_combobox", "sye_drift_combobox",
    )
    names = []
    for key in dynamic_keys:
        combo = getattr(widget, key, None)
        names.append(combo.currentText().strip() if combo is not None else "")

    if any(not name for name in names):
        raise ValueError("Dynamic loadcase names cannot be empty.")
    if len(set(names)) != 8:
        raise ValueError("Dynamic loadcase names must be unique.")

    existing_rs = set(etabs.load_cases.get_response_spectrum_loadcase_name())
    missing = [name for name in names if name not in existing_rs]
    if not missing:
        return

    funcs = list(etabs.func.response_spectrum_names())
    if not funcs and not allow_without_function:
        joined = ", ".join(missing)
        raise ValueError(
            "Define at least one response spectrum function in ETABS before creating "
            f"missing dynamic loadcases: {joined}"
        )

    func = spectrum_function.strip() if isinstance(spectrum_function, str) else None
    if func and funcs and func not in funcs:
        raise ValueError(f"Selected response spectrum function not found in ETABS: {func}")
    if not func and funcs:
        func = funcs[0]

    sx, sxe, sy, sye, sx_drift, sxe_drift, sy_drift, sye_drift = names
    ecc_dirs = {
        sx: (0.0, "U1"),
        sxe: (0.05, "U1"),
        sy: (0.0, "U2"),
        sye: (0.05, "U2"),
        sx_drift: (0.0, "U1"),
        sxe_drift: (0.05, "U1"),
        sy_drift: (0.0, "U2"),
        sye_drift: (0.05, "U2"),
    }

    for loadcase in missing:
        ecc, direction = ecc_dirs[loadcase]
        etabs.load_cases.add_response_spectrum_loadcases([loadcase], ecc)
        if func:
            args = [1, (direction,), (func,), (1,), ("Global",), (0.0,)]
            etabs.SapModel.LoadCases.ResponseSpectrum.SetLoads(loadcase, *args)


# ─── Earthquake factor data helpers ────────────────────────────────

def get_data_for_apply_earthquakes(building, etabs=None, d=None, widget=None):
    if widget is None:
        if d is None:
            d = get_settings_from_etabs(etabs)
        bot_1, top_1, bot_2, top_2 = etabs.get_top_bot_stories(d)
        first = etabs.get_first_system_seismic(d)
        second_active = d.get("activate_second_system", False)
        if second_active:
            special = d.get("special_case", False)
            second = etabs.get_second_system_seismic(d)
    else:
        bot_1 = widget.bot_x_combo.currentText()
        top_1 = widget.top_x_combo.currentText()
        bot_2 = widget.bot_x1_combo.currentText()
        top_2 = widget.top_x1_combo.currentText()
        first = get_first_system_seismic(widget)
        second_active = widget.activate_second_system.isChecked()
        if second_active:
            special = widget.special_case.isChecked()
            second = get_second_system_seismic(widget)

    cx_1, cy_1 = building.results[1:]
    kx_1, ky_1 = building.kx, building.ky
    data = []

    if second_active:
        cx_2, cy_2 = building.building2.results[1:]
        kx_2, ky_2 = building.building2.kx, building.building2.ky
        if special and building.x_system.Ru == building.building2.x_system.Ru and \
                building.y_system.Ru == building.building2.y_system.Ru:
            data.append((first[:3], [top_1, bot_1, str(cx_1), str(kx_1)]))
            data.append((first[3:], [top_1, bot_1, str(cy_1), str(ky_1)]))
            data.append((second[:3], [top_2, bot_2, str(cx_2), str(kx_2)]))
            data.append((second[3:], [top_2, bot_2, str(cy_2), str(ky_2)]))
        elif building.x_system.Ru >= building.building2.x_system.Ru and \
                building.y_system.Ru >= building.building2.y_system.Ru:
            cx_all, cy_all = building.results_all_top[1:]
            kx_all, ky_all = building.kx_all, building.ky_all
            data.append((first[:3], [top_2, bot_1, str(cx_all), str(kx_all)]))
            data.append((first[3:], [top_2, bot_1, str(cy_all), str(ky_all)]))
        else:
            return None
    else:
        data.append((first[:3], [top_1, bot_1, str(cx_1), str(kx_1)]))
        data.append((first[3:], [top_1, bot_1, str(cy_1), str(ky_1)]))
    return data


def get_data_for_apply_earthquakes_drift(building, etabs=None, d=None, widget=None):
    if widget is None:
        if d is None:
            d = get_settings_from_etabs(etabs)
        bot_1, top_1, bot_2, top_2 = etabs.get_top_bot_stories(d)
        first = etabs.get_first_system_seismic_drift(d)
        second_active = d.get("activate_second_system", False)
        if second_active:
            special = d.get("special_case", False)
            second = etabs.get_second_system_seismic_drift(d)
    else:
        bot_1 = widget.bot_x_combo.currentText()
        top_1 = widget.top_x_combo.currentText()
        bot_2 = widget.bot_x1_combo.currentText()
        top_2 = widget.top_x1_combo.currentText()
        first = get_first_system_seismic_drift(widget)
        second_active = widget.activate_second_system.isChecked()
        if second_active:
            special = widget.special_case.isChecked()
            second = get_second_system_seismic_drift(widget)

    cx_1, cy_1 = building.results_drift[1:]
    kx_1, ky_1 = building.kx_drift, building.ky_drift
    data = []

    if second_active:
        cx_2, cy_2 = building.building2.results_drift[1:]
        kx_2, ky_2 = building.building2.kx_drift, building.building2.ky_drift
        if special and building.x_system.Ru == building.building2.x_system.Ru and \
                building.y_system.Ru == building.building2.y_system.Ru:
            data.append((first[:3], [top_1, bot_1, str(cx_1), str(kx_1)]))
            data.append((first[3:], [top_1, bot_1, str(cy_1), str(ky_1)]))
            data.append((second[:3], [top_2, bot_2, str(cx_2), str(kx_2)]))
            data.append((second[3:], [top_2, bot_2, str(cy_2), str(ky_2)]))
        elif building.x_system.Ru >= building.building2.x_system.Ru and \
                building.y_system.Ru >= building.building2.y_system.Ru:
            cx_all, cy_all = building.results_drift_all_top[1:]
            kx_all, ky_all = building.kx_drift_all, building.ky_drift_all
            data.append((first[:3], [top_2, bot_1, str(cx_all), str(kx_all)]))
            data.append((first[3:], [top_2, bot_1, str(cy_all), str(ky_all)]))
        else:
            return None
    else:
        data.append((first[:3], [top_1, bot_1, str(cx_1), str(kx_1)]))
        data.append((first[3:], [top_1, bot_1, str(cy_1), str(ky_1)]))
    return data
