"""
Columns Control — compare adjacent-story column sections.

Ported from civilTools/py_widget/control/columns_control.py.
Checks for dimension, rebar, area, local-axis, and material issues
between above/below column sections in each vertical stack.

Uses ColumnsControlModel for per-cell color-coded display.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from civiltools.commands.base import BaseCommand, CommandResult
from civiltools.commands import register


@register
class ColumnsControlCheck(BaseCommand):
    command_id = "columns_control"
    label = "Columns Control"
    menu_path = "Control"
    tooltip = "Compare adjacent-story column sections for adequacy"
    table_model = "ColumnsControlModel"

    @classmethod
    def execute(cls, etabs, params: dict[str, Any] | None = None) -> CommandResult:
        try:
            columns_type_names_df = etabs.frame_obj.stacked_columns_dataframe_by_points()
            columns_type_sections_df = columns_type_names_df.copy(deep=True)
            etabs.set_current_unit('kgf', 'cm')
            column_names = etabs.frame_obj.concrete_section_names('Column')
            section_areas = etabs.frame_obj.get_section_area(column_names)

            nrows, ncols = columns_type_names_df.shape

            # Replace column names with section names.
            # Use positional (iat) access — duplicate row/column labels (e.g. two
            # empty stacks) would make label-based `.at[]` return a Series instead
            # of a scalar, breaking truthiness checks.
            for j in range(ncols):
                for i in range(nrows):
                    name = columns_type_sections_df.iat[i, j]
                    if pd.notna(name) and name != '':
                        sec = etabs.SapModel.FrameObj.GetSection(str(name))[0]
                        columns_type_sections_df.iat[i, j] = sec or ''
                    else:
                        columns_type_sections_df.iat[i, j] = ''

            # Build comparison results
            comparison_results = {}
            for j in range(ncols):
                col = columns_type_names_df.columns[j]
                for i in range(nrows - 1):
                    row_idx = columns_type_names_df.index[i]
                    below_row_idx = columns_type_names_df.index[i + 1]
                    above_col = columns_type_names_df.iat[i, j]
                    below_col = columns_type_names_df.iat[i + 1, j]
                    if (pd.notna(above_col) and above_col != ''
                            and pd.notna(below_col) and below_col != ''):
                        try:
                            result = etabs.prop_frame.compare_two_columns(
                                below_col, above_col, section_areas
                            )
                            comparison_results[(row_idx, col)] = result.name
                        except Exception:
                            comparison_results[(row_idx, col)] = 'not_checked'
                    else:
                        comparison_results[(row_idx, col)] = 'not_checked'
                # Last row is always OK (no below to compare)
                last_row_idx = columns_type_names_df.index[-1]
                comparison_results[(last_row_idx, col)] = 'OK'

        except Exception as exc:
            return CommandResult(
                title="Columns Control",
                ok=False,
                error=f"Failed to check columns: {exc}",
            )

        # Count issues
        issues = [v for v in comparison_results.values()
                  if v not in ('OK', 'not_checked')]
        n_issues = len(issues)
        ok = n_issues == 0
        summary = (
            f"All columns OK — no issues found"
            if ok else
            f"{n_issues} issue(s) found in column section comparisons"
        )

        return CommandResult(
            title="Columns Control",
            dataframe=columns_type_sections_df,
            summary=summary,
            ok=ok,
            kwargs={
                'section_areas': section_areas,
                'columns_type_names_df': columns_type_names_df,
                'comparison_results': comparison_results,
                'etabs': etabs,
            },
        )
