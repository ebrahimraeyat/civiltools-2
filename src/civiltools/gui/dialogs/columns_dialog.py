"""
Columns control dialog — loads columns_control.ui.

Ported from civilTools/py_widget/control/columns_control.py.
The .ui has an "Area" checkbox (disabled) and Check button.
Compares adjacent-story column sections for dimension, rebar, area adequacy.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class ColumnsControlDialog(QDialog):
    """Dialog for column section comparison (above/below adequacy check)."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        # Load .ui
        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "columns_control.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Columns Control")
        self.resize(self.ui.size())
        set_dialog_icon(self, "columns_control.svg")

        # Wire
        self.ui.check.clicked.connect(self._check)

    def _check(self):
        """Compare adjacent-story column sections and build result."""
        try:
            QApplication.setOverrideCursor(QApplication.instance().overrideCursor() or __import__('PySide6.QtCore', fromlist=['Qt']).Qt.CursorShape.WaitCursor)
        except Exception:
            pass

        try:
            etabs = self._etabs
            columns_type_names_df = etabs.frame_obj.stacked_columns_dataframe_by_points()
            columns_type_sections_df = columns_type_names_df.copy(deep=True)
            etabs.set_current_unit('kgf', 'cm')
            column_names = etabs.frame_obj.concrete_section_names('Column')
            section_areas = etabs.frame_obj.get_section_area(column_names)

            # Replace column names with section names in the display DF
            for col in columns_type_sections_df.columns:
                for row_idx in columns_type_sections_df.index:
                    name = columns_type_sections_df.at[row_idx, col]
                    if name and name != '':
                        sec = etabs.SapModel.FrameObj.GetSection(name)[0]
                        columns_type_sections_df.at[row_idx, col] = sec or ''

            # Build comparison results
            nrows = len(columns_type_names_df)
            comparison_results = {}
            for col in columns_type_names_df.columns:
                for row_idx_pos in range(nrows - 1):
                    row_idx = columns_type_names_df.index[row_idx_pos]
                    above_col = columns_type_names_df.at[row_idx, col]
                    below_row_idx = columns_type_names_df.index[row_idx_pos + 1]
                    below_col = columns_type_names_df.at[below_row_idx, col]
                    if above_col and below_col and above_col != '' and below_col != '':
                        try:
                            result = etabs.prop_frame.compare_two_columns(
                                below_col, above_col, section_areas
                            )
                            comparison_results[(row_idx, col)] = result.name
                        except Exception:
                            comparison_results[(row_idx, col)] = 'not_checked'
                    else:
                        comparison_results[(row_idx, col)] = 'not_checked'
                # Last row is always OK
                last_row_idx = columns_type_names_df.index[-1]
                comparison_results[(last_row_idx, col)] = 'OK'

        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error", str(exc))
            return

        QApplication.restoreOverrideCursor()

        # Count issues
        issues = [v for v in comparison_results.values()
                  if v not in ('OK', 'not_checked')]
        n_issues = len(issues)
        ok = n_issues == 0
        summary = (
            "All columns OK — no issues found"
            if ok else
            f"{n_issues} issue(s) found in column section comparisons"
        )

        self._result = CommandResult(
            title="Columns Control",
            dataframe=columns_type_sections_df,
            summary=summary,
            ok=ok,
            kwargs={
                'section_areas': section_areas,
                'columns_type_names_df': columns_type_names_df,
                'comparison_results': comparison_results,
            },
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
        return self._result
