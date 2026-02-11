"""
Joint shear check — ported from civilTools/py_widget/control/control_joint_shear.py.

Creates a joint-shear analysis file and reads results.
Uses JointShearBCCModel for color-coded ratio display.
"""

from __future__ import annotations

from typing import Any

from civiltools.commands.base import BaseCommand, CommandParam, CommandResult
from civiltools.commands import register


@register
class JointShearCheck(BaseCommand):
    command_id = "joint_shear"
    label = "Joint Shear"
    menu_path = "Control"
    tooltip = "Beam-column joint shear and BCC ratios"
    table_model = "JointShearBCCModel"
    dialog_class = "civiltools.gui.dialogs.joint_shear_dialog.JointShearDialog"

    @classmethod
    def parameters(cls) -> list[CommandParam]:
        return [
            CommandParam(
                "structure_type", "Structure Type", "combo",
                default="Sway Intermediate",
                choices=["Sway Intermediate", "Sway Special"],
                tooltip="Framing type for joint shear design",
            ),
            CommandParam(
                "show_js", "Show Joint Shear", "combo",
                default="Yes",
                choices=["Yes", "No"],
                tooltip="Show joint shear ratios",
            ),
            CommandParam(
                "show_bc", "Show Beam-Column", "combo",
                default="Yes",
                choices=["Yes", "No"],
                tooltip="Show beam-column capacity ratios",
            ),
        ]

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        params = params or {}
        structure_type = params.get("structure_type", "Sway Intermediate")
        show_js = params.get("show_js", "Yes") == "Yes"
        show_bc = params.get("show_bc", "Yes") == "Yes"

        # Build filename based on what to show (matches original)
        filename = ""
        if show_js:
            filename += "js"
        if show_bc:
            filename += "bc"
        if not filename:
            filename = "jsbc"

        try:
            etabs.save()
            df = etabs.create_joint_shear_bcc_file(
                file_name=filename,
                structure_type=structure_type,
                open_main_file=True,
                create_file=True,
            )
        except Exception as exc:
            return CommandResult(
                title="Joint Shear",
                ok=False,
                error=f"Failed to create joint shear file: {exc}",
            )

        if df is None or (hasattr(df, "empty") and df.empty):
            return CommandResult(
                title="Joint Shear",
                ok=False,
                error="No joint shear data available.",
            )

        # Filter columns based on user choice (matches original control_joint_shear.py)
        if show_js and show_bc:
            pass  # keep all
        elif show_js:
            keep = ['Story', 'Label', 'UniqueName', 'JSMajRatio', 'JSMinRatio']
            available = [c for c in keep if c in df.columns]
            df = df[available]
        elif show_bc:
            keep = ['Story', 'Label', 'UniqueName', 'BCMajRatio', 'BCMinRatio']
            available = [c for c in keep if c in df.columns]
            df = df[available]

        # Check max ratios
        js_max = bc_max = 0.0
        for col in df.columns:
            if "JS" in col:
                try:
                    js_max = max(js_max, df[col].astype(float).max())
                except (ValueError, TypeError):
                    pass
            if "BC" in col:
                try:
                    bc_max = max(bc_max, df[col].astype(float).max())
                except (ValueError, TypeError):
                    pass

        js_ok = js_max <= 1.0
        bc_ok = bc_max <= 1.0
        parts = []
        if show_js:
            parts.append(f"JS max = {js_max:.3f} {'OK' if js_ok else 'EXCEEDS 1.0'}")
        if show_bc:
            parts.append(f"BCC max = {bc_max:.3f} {'OK' if bc_ok else 'EXCEEDS 1.0'}")
        summary = "  |  ".join(parts)

        return CommandResult(
            title="Joint Shear",
            headers=list(df.columns),
            rows=df.values.tolist(),
            dataframe=df,
            summary=summary,
            ok=js_ok and bc_ok,
        )
