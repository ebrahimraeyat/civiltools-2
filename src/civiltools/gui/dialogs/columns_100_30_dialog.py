"""
Columns 100-30 check dialog — orthogonal combination requirement.

Ported from civilTools/py_widget/control/columns_100_30.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QFileDialog,
)

from civiltools.etabs import config
from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class Columns10030Dialog(QDialog):
    """Check columns for 100%-30% orthogonal combination requirement."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "control" / "columns_100_30.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Columns 100-30 Check")
        self.resize(self.ui.size())
        set_dialog_icon(self, "100_30.svg")

        self._d = config.get_settings_from_etabs(self._etabs)
        config.load(self._etabs, self.ui, self._d)

        # Default to static groupbox checked
        dg = getattr(self.ui, "dynamic_groupbox", None)
        if dg:
            dg.setChecked(False)

        self._set_code()
        self._create_connections()

    def _create_connections(self):
        browse = getattr(self.ui, "browse", None)
        if browse:
            browse.clicked.connect(self._get_filename)
        check_btn = getattr(self.ui, "check", None)
        if check_btn:
            check_btn.clicked.connect(self._run)
        cancel_btn = getattr(self.ui, "cancel_button", None)
        if cancel_btn:
            cancel_btn.clicked.connect(self.reject)

        for rb in ("concrete_radiobutton", "steel_radiobutton"):
            w = getattr(self.ui, rb, None)
            if w:
                w.clicked.connect(self._set_code)

        sg = getattr(self.ui, "static_groupbox", None)
        dg = getattr(self.ui, "dynamic_groupbox", None)
        if sg:
            sg.clicked.connect(lambda c: self._groupbox_clicked("static", c))
        if dg:
            dg.clicked.connect(lambda c: self._groupbox_clicked("dynamic", c))

    def _groupbox_clicked(self, which, checked):
        ui = self.ui
        if which == "static":
            for n in ("static_group_x", "static_group_y"):
                w = getattr(ui, n, None)
                if w: w.setEnabled(checked)
            for n in ("dynamic_group_x", "dynamic_group_y"):
                w = getattr(ui, n, None)
                if w: w.setEnabled(not checked)
            dg = getattr(ui, "dynamic_groupbox", None)
            if dg: dg.setChecked(not checked)
        else:
            for n in ("dynamic_group_x", "dynamic_group_y"):
                w = getattr(ui, n, None)
                if w: w.setEnabled(checked)
            for n in ("static_group_x", "static_group_y"):
                w = getattr(ui, n, None)
                if w: w.setEnabled(not checked)
            sg = getattr(ui, "static_groupbox", None)
            if sg: sg.setChecked(not checked)

    def _set_code(self):
        rb = getattr(self.ui, "concrete_radiobutton", None)
        type_ = "Concrete" if rb and rb.isChecked() else "Steel"
        try:
            self._code = self._etabs.design.get_code(type_)
        except Exception:
            self._code = ""
        code_label = getattr(self.ui, "design_code", None)
        if code_label:
            code_label.setText(self._code)

    def _get_filename(self):
        directory = str(self._etabs.get_filepath())
        filename, _ = QFileDialog.getSaveFileName(
            self, "ETABS 100-30 file", directory, "ETABS(*.EDB)")
        fn_edit = getattr(self.ui, "filename", None)
        if fn_edit and filename:
            fn_edit.setText(filename)

    def _run(self):
        fn_edit = getattr(self.ui, "filename", None)
        filename = fn_edit.text() if fn_edit else ""
        file_path = Path(filename) if filename else None

        d = config.get_prop_from_widget(self._etabs, self.ui)
        rb = getattr(self.ui, "concrete_radiobutton", None)
        type_ = "Concrete" if rb and rb.isChecked() else "Steel"

        sg = getattr(self.ui, "static_groupbox", None)
        if sg and sg.isChecked():
            load_names = self._etabs.get_first_system_seismic(d)
        else:
            load_names = self._etabs.get_dynamic_loadcases(d)

        try:
            df = self._etabs.frame_obj.require_100_30(
                load_names, file_path, type_, self._code)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if df is None or df.empty:
            QMessageBox.information(self, "No Data", "No 100-30 data returned.")
            return

        # Create ETABS groups for required/not-required columns
        try:
            not_req = df.loc[df["Result"] == True, "UniqueName"].tolist()
            req = df.loc[df["Result"] == False, "UniqueName"].tolist()
            if not_req:
                self._etabs.group.add("100_30_NotRequired", remove=True)
                for n in not_req:
                    self._etabs.SapModel.FrameObj.SetGroupAssign(n, "100_30_NotRequired")
            if req:
                self._etabs.group.add("100_30_Required", remove=True)
                for n in req:
                    self._etabs.SapModel.FrameObj.SetGroupAssign(n, "100_30_Required")
        except Exception:
            pass

        n_req = len(df[df["Result"] == False]) if "Result" in df.columns else 0
        self._result = CommandResult(
            title="Columns 100-30",
            dataframe=df,
            ok=n_req == 0,
            summary=f"{n_req} columns require 100-30 combination" if n_req else "All columns OK",
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
