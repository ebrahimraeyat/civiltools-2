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
from civiltools.gui.busy_dialog import BusyDialog
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
            with BusyDialog(
                "Columns Control",
                status_text="ETABS is reading stacked columns, comparing section properties, and checking design continuity…",
                parent=self,
                disable_widgets=[self.ui],
            ) as dlg:
                def _do_check():
                    etabs = self._etabs
                    _names_df = etabs.frame_obj.stacked_columns_dataframe_by_points()
                    _secs_df  = _names_df.copy(deep=True)
                    etabs.set_current_unit('kgf', 'cm')
                    col_names    = etabs.frame_obj.concrete_section_names('Column')
                    _sec_areas   = etabs.frame_obj.get_section_area(col_names)
                    for col in _secs_df.columns:
                        for row_idx in _secs_df.index:
                            name = _secs_df.at[row_idx, col]
                            if name and name != '':
                                sec = etabs.SapModel.FrameObj.GetSection(name)[0]
                                _secs_df.at[row_idx, col] = sec or ''
                    nrows = len(_names_df)
                    _cmp  = {}
                    for col in _names_df.columns:
                        for pos in range(nrows - 1):
                            idx  = _names_df.index[pos]
                            idn  = _names_df.index[pos + 1]
                            ab   = _names_df.at[idx, col]
                            bl   = _names_df.at[idn, col]
                            if ab and bl and ab != '' and bl != '':
                                try:
                                    _cmp[(idx, col)] = etabs.prop_frame.compare_two_columns(
                                        bl, ab, _sec_areas
                                    ).name
                                except Exception:
                                    _cmp[(idx, col)] = 'not_checked'
                            else:
                                _cmp[(idx, col)] = 'not_checked'
                        _cmp[(_names_df.index[-1], col)] = 'OK'
                    return _names_df, _secs_df, _sec_areas, _cmp

                columns_type_names_df, columns_type_sections_df, section_areas, comparison_results = dlg.run(_do_check)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

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
