"""Columns 100-30 check command."""

from __future__ import annotations

from pathlib import Path

from typing import Any

from civiltools.commands import register
from civiltools.commands.base import BaseCommand, CommandResult


def run_columns_100_30(etabs, params: dict[str, Any] | None = None):
    """Run the ETABS 100%-30% requirement calculation."""
    params = params or {}
    settings = params.get("settings")
    if settings is None:
        from civiltools.etabs.config import get_settings_from_etabs

        settings = get_settings_from_etabs(etabs)

    load_names = params.get("load_names")
    if load_names is None:
        if params.get("dynamic", False):
            load_names = etabs.get_dynamic_loadcases(settings)
        else:
            load_names = etabs.get_first_system_seismic(settings)

    structure_type = params.get("structure_type", "Concrete")
    code = params.get("code")
    if code is None:
        code = etabs.design.get_code(structure_type)

    file_path = params.get("file_path")
    if file_path:
        file_path = Path(file_path)

    return etabs.frame_obj.require_100_30(
        load_names,
        file_path,
        structure_type,
        code,
    )


@register
class Columns10030Command(BaseCommand):
    command_id = "columns_100_30"
    label = "Columns 100-30"
    menu_path = "Control"
    tooltip = "Check columns for 100%-30% orthogonal combination requirement"
    dialog_class = "civiltools.gui.dialogs.columns_100_30_dialog.Columns10030Dialog"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        try:
            df = run_columns_100_30(etabs, params)
        except Exception as exc:
            return CommandResult(
                title="Columns 100-30",
                ok=False,
                error=f"Failed to run 100-30 check: {exc}",
            )

        if df is None or df.empty:
            return CommandResult(
                title="Columns 100-30",
                ok=False,
                error="No 100-30 data returned.",
            )

        required_count = 0
        if "Result" in df.columns:
            result_values = df["Result"].astype(str).str.strip().str.lower()
            required_count = int(result_values.isin({"false", "0", "no"}).sum())

        return CommandResult(
            title="Columns 100-30",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            ok=required_count == 0,
            summary=(
                f"{required_count} columns require 100-30 combination"
                if required_count
                else "All columns OK"
            ),
        )
