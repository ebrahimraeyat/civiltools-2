"""
Dynamic scale factor — ported from civilTools/py_widget/response_spectrum.py.

Scales response spectrum cases to match static base shear.
Uses BaseShearModel for display.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandParam, CommandResult
from civiltools.commands import register


@register
class DynamicScaleCheck(BaseCommand):
    command_id = "dynamic_scale"
    label = "Dynamic Scale Factor"
    menu_path = "Control"
    tooltip = "Scale response spectrum to match static base shear"
    table_model = "BaseShearModel"
    dialog_class = "civiltools.gui.dialogs.response_spectrum_dialog.ResponseSpectrumDialog"

    @classmethod
    def parameters(cls) -> list[CommandParam]:
        return [
            CommandParam("scale_factor", "Target ratio (e.g. 0.9)", "float", 0.9,
                         tooltip="V_dynamic / V_static target (0.85, 0.9, or 1.0)"),
            CommandParam("num_iteration", "Iterations", "int", 3,
                         tooltip="Number of scaling iterations"),
            CommandParam("tolerance", "Tolerance", "float", 0.05,
                         tooltip="Acceptable tolerance for convergence"),
            CommandParam("reset_scale", "Reset scales first", "combo",
                         default="Yes", choices=["Yes", "No"],
                         tooltip="Reset scale factors before iterating"),
        ]

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        params = params or {}
        scale_factor = float(params.get("scale_factor", 0.9))
        num_iter = int(params.get("num_iteration", 3))
        tolerance = float(params.get("tolerance", 0.05))
        reset = params.get("reset_scale", "Yes") == "Yes"

        # Auto-detect earthquake and spectral cases (like original response_spectrum.py)
        try:
            lp = etabs.load_patterns
            lc = etabs.load_cases

            eq_names = lp.get_EX_EY_earthquake_name()
            if eq_names is None or len(eq_names) < 2:
                return CommandResult(
                    title="Dynamic Scale",
                    ok=False,
                    error="Cannot detect EX/EY earthquake load patterns.",
                )
            ex_name, ey_name = eq_names[0], eq_names[1]

            # Get response spectrum load cases
            specs = lc.get_response_spectrum_loadcases_loadpatterns()
            if not specs:
                return CommandResult(
                    title="Dynamic Scale",
                    ok=False,
                    error="No response spectrum load cases found.",
                )
            x_specs = [s for s in specs if "x" in s.lower() or "X" in s]
            y_specs = [s for s in specs if "y" in s.lower() or "Y" in s]

            if not x_specs or not y_specs:
                mid = len(specs) // 2
                x_specs = specs[:mid] if mid > 0 else specs[:1]
                y_specs = specs[mid:] if mid > 0 else specs[1:2]
        except Exception as exc:
            return CommandResult(
                title="Dynamic Scale",
                ok=False,
                error=f"Failed to detect load cases: {exc}",
            )

        try:
            x_scales, y_scales, df = etabs.scale_response_spectrums(
                ex_name=ex_name,
                ey_name=ey_name,
                x_specs=x_specs,
                y_specs=y_specs,
                x_scale_factor=scale_factor,
                y_scale_factor=scale_factor,
                num_iteration=num_iter,
                tolerance=tolerance,
                reset_scale=reset,
                analyze=True,
            )
        except Exception as exc:
            return CommandResult(
                title="Dynamic Scale",
                ok=False,
                error=f"Failed to scale response spectrums: {exc}",
            )

        if df is None or (hasattr(df, "empty") and df.empty):
            return CommandResult(
                title="Dynamic Scale",
                ok=False,
                error="No results from scaling operation.",
            )

        # Check if ratios meet target
        all_ok = True
        if "Ratio" in df.columns:
            try:
                ratios = df["Ratio"].astype(float)
                if (ratios < scale_factor - tolerance).any():
                    all_ok = False
            except (ValueError, TypeError):
                pass

        summary = (
            f"Target ratio = {scale_factor}  |  "
            f"X scales: {x_scales}  |  Y scales: {y_scales}  →  "
            f"{'SCALING OK' if all_ok else 'SOME RATIOS BELOW TARGET'}"
        )

        return CommandResult(
            title="Dynamic Scale",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            summary=summary,
            ok=all_ok,
        )
