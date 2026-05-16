# pyright: reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from civiltools.config import config_dir

__all__ = ["ControlsInputSettingsDialog", "load_controls_input_settings"]


_DEFAULT_SETTINGS: dict[str, Any] = {
    "control_end_rigid_zone_factor": {"expected_factor": 0.5, "tolerance": 0.01},
    "control_beam_depth_main_vs_secondary": {"tolerance_mm": 0.0},
    "control_mass_stiffness_modifiers_beams": {"expected": {"i22": 0.35, "i33": 0.35, "mass": 1.0}},
    "control_mass_stiffness_modifiers_columns": {"expected": {"i22": 0.7, "i33": 0.7, "mass": 1.0}},
    "control_mass_stiffness_modifiers_shear_walls": {"expected": {"m11": 1.0, "m22": 1.0, "mass": 1.0}},
    "control_min_max_floor_loads": {"min_load": 0.0, "max_load": 1000000000.0},
    "control_min_max_beam_dead_live_loads": {"min_load": 0.0, "max_load": 1000000000.0},
    "control_rebar_percentage_at_splice_location": {"max_percentage": 6.0},
    "control_concrete_cover_beams_columns": {"beam_cover": 40.0, "column_cover": 40.0},
    "control_response_spectrum": {"include_importance_factor_delta_i": False, "tolerance": 0.05},
}


def _settings_path() -> Path:
    return config_dir() / "controls_input_settings.json"


def load_controls_input_settings() -> dict[str, Any]:
    path = _settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = json.loads(json.dumps(_DEFAULT_SETTINGS))
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
            return merged
        except (OSError, json.JSONDecodeError):
            pass
    return json.loads(json.dumps(_DEFAULT_SETTINGS))


class ControlsInputSettingsDialog(QDialog):
    """Dialog for editing key control parameters."""

    def __init__(self, settings: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Input Controls Settings")
        self.setMinimumWidth(420)
        self._settings = settings or load_controls_input_settings()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configure default values for the most important pre-analysis checks."))

        form = QFormLayout()
        layout.addLayout(form)

        self.rigid_zone = self._double_box(self._settings["control_end_rigid_zone_factor"]["expected_factor"], 0.0, 1.0, 3)
        form.addRow("Rigid zone factor", self.rigid_zone)

        self.floor_min = self._double_box(self._settings["control_min_max_floor_loads"]["min_load"], 0.0, 1e12, 2)
        self.floor_max = self._double_box(self._settings["control_min_max_floor_loads"]["max_load"], 0.0, 1e12, 2)
        form.addRow("Floor min load", self.floor_min)
        form.addRow("Floor max load", self.floor_max)

        self.beam_min = self._double_box(self._settings["control_min_max_beam_dead_live_loads"]["min_load"], 0.0, 1e12, 2)
        self.beam_max = self._double_box(self._settings["control_min_max_beam_dead_live_loads"]["max_load"], 0.0, 1e12, 2)
        form.addRow("Beam min load", self.beam_min)
        form.addRow("Beam max load", self.beam_max)

        self.splice_limit = self._double_box(self._settings["control_rebar_percentage_at_splice_location"]["max_percentage"], 0.0, 20.0, 2)
        form.addRow("Splice rebar % limit", self.splice_limit)

        self.beam_cover = self._double_box(self._settings["control_concrete_cover_beams_columns"]["beam_cover"], 0.0, 200.0, 1)
        self.column_cover = self._double_box(self._settings["control_concrete_cover_beams_columns"]["column_cover"], 0.0, 200.0, 1)
        form.addRow("Beam cover", self.beam_cover)
        form.addRow("Column cover", self.column_cover)

        self.include_delta_i = QCheckBox("Include ΔI validation in spectrum control")
        self.include_delta_i.setChecked(bool(self._settings["control_response_spectrum"].get("include_importance_factor_delta_i", False)))
        form.addRow("Spectrum option", self.include_delta_i)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _double_box(value: float, minimum: float, maximum: float, decimals: int) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setValue(float(value))
        widget.setSingleStep(0.1 if decimals else 1.0)
        return widget

    def values(self) -> dict[str, Any]:
        data = load_controls_input_settings()
        data["control_end_rigid_zone_factor"]["expected_factor"] = self.rigid_zone.value()
        data["control_min_max_floor_loads"]["min_load"] = self.floor_min.value()
        data["control_min_max_floor_loads"]["max_load"] = self.floor_max.value()
        data["control_min_max_beam_dead_live_loads"]["min_load"] = self.beam_min.value()
        data["control_min_max_beam_dead_live_loads"]["max_load"] = self.beam_max.value()
        data["control_rebar_percentage_at_splice_location"]["max_percentage"] = self.splice_limit.value()
        data["control_concrete_cover_beams_columns"]["beam_cover"] = self.beam_cover.value()
        data["control_concrete_cover_beams_columns"]["column_cover"] = self.column_cover.value()
        data["control_response_spectrum"]["include_importance_factor_delta_i"] = self.include_delta_i.isChecked()
        return data

    def accept(self) -> None:
        data = self.values()
        _settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._settings = data
        super().accept()
