"""
Create materials dialog — ported from
civilTools/py_widget/define/create_materials.py.

Two tabs: Concrete (f'c + Ec method) and Rebars (standard S340/400/420/500 or a
custom rebar).  Writes materials to the model via ``etabs.material.add_concrete``
/ ``etabs.material.add_rebar``.  The Create button can be used repeatedly; Close
returns the last result.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class CreateMaterialsDialog(QDialog):
    """Create concrete and rebar materials in the ETABS model."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None

        loader = QUiLoader()
        ui_file = QFile(str(_UI_DIR / "define" / "create_materials.ui"))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle("Create Materials")
        self.resize(self.ui.size())
        set_dialog_icon(self, "materials.svg")

        # The .ui only has a Create button — add Close so the modal dialog can
        # return its result without forcing a create.
        bbox = QDialogButtonBox()
        bbox.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        bbox.accepted.connect(self.accept)
        layout.addWidget(bbox)

        self._create_connections()
        self._set_ec_label()

    def _create_connections(self):
        f = self.ui
        f.create_pushbutton.clicked.connect(self._create_materials)
        f.ec1.clicked.connect(self._ec_clicked)
        f.ec2.clicked.connect(self._ec_clicked)
        f.fc_spinbox.valueChanged.connect(self._set_fc_name)
        f.wc.valueChanged.connect(self._set_ec_label)
        f.standard_rebars_groupbox.clicked.connect(self._rebar_group_clicked)
        f.other_rebars_groupbox.clicked.connect(self._rebar_group_clicked)
        for cb in (f.s340_checkbox, f.s400_checkbox, f.s420_checkbox, f.s500_checkbox):
            cb.clicked.connect(self._standard_rebar_clicked)

    def _standard_rebar_clicked(self, check):
        fy = self.sender().objectName()[1:4]   # 's340_checkbox' -> '340'
        f = self.ui
        getattr(f, f"s{fy}fy_spinbox").setEnabled(check)
        getattr(f, f"s{fy}fu_spinbox").setEnabled(check)
        getattr(f, f"s{fy}_name").setEnabled(check)

    def _rebar_group_clicked(self, check):
        f = self.ui
        sender = self.sender()
        if sender is f.standard_rebars_groupbox:
            f.other_rebars_groupbox.setChecked(not check)
        elif sender is f.other_rebars_groupbox:
            f.standard_rebars_groupbox.setChecked(not check)

    def _set_fc_name(self, value):
        self.ui.fc_name.setText(f"C{value}")
        self._set_ec_label()

    def _ec_clicked(self, check):
        f = self.ui
        sender = self.sender()
        if sender is f.ec1:
            f.wc.setEnabled(check)
        elif sender is f.ec2:
            f.wc.setEnabled(not check)
        self._set_ec_label()

    def _set_ec_label(self):
        f = self.ui
        if f.ec1.isChecked():
            par = 0.043 * f.wc.value() ** 1.5
        else:
            par = 4700
        ec = par * f.fc_spinbox.value() ** 0.5
        f.ec_label.setText(f"Ec = {ec:.0f} MPa")

    def _create_materials(self):
        etabs = self._etabs
        f = self.ui
        if etabs.SapModel.GetModelIsLocked():
            if QMessageBox.question(
                self, "Unlock Model?", "The model is locked, do you want to unlock it?"
            ) == QMessageBox.StandardButton.No:
                return
            etabs.unlock_model()

        if f.tabWidget.currentIndex() == 0:  # Concrete
            name = f.fc_name.text()
            fc = f.fc_spinbox.value()
            weight = f.wc.value() if f.ec1.isChecked() else 0
            etabs.material.add_concrete(name, fc, weight_for_calculate_ec=weight)
            self._result = CommandResult(
                title="Create Materials",
                ok=True,
                summary=f"Concrete {name} (f'c = {fc} MPa) added to model.",
            )
            QMessageBox.information(
                self, "Done", f"The concrete {name} with f'c={fc} MPa added to model."
            )
            return

        # Rebars tab
        add_standards = f.standard_rebars_groupbox.isChecked()
        add_others = f.other_rebars_groupbox.isChecked()
        if not add_standards and not add_others:
            QMessageBox.warning(
                self, "Selection", "Please select at least one rebar to create!"
            )
            return

        rebar_names: list[str] = []
        if add_standards:
            checkboxes = (f.s340_checkbox, f.s400_checkbox, f.s420_checkbox, f.s500_checkbox)
            fys = (f.s340fy_spinbox, f.s400fy_spinbox, f.s420fy_spinbox, f.s500fy_spinbox)
            fus = (f.s340fu_spinbox, f.s400fu_spinbox, f.s420fu_spinbox, f.s500fu_spinbox)
            names = (f.s340_name, f.s400_name, f.s420_name, f.s500_name)
            for i, cb in enumerate(checkboxes):
                if cb.isChecked():
                    etabs.material.add_rebar(names[i].text(), fys[i].value(), fus[i].value())
                    rebar_names.append(names[i].text())
        if add_others:
            etabs.material.add_rebar(
                f.other_name.text(), f.other_fy_spinbox.value(), f.other_fu_spinbox.value()
            )
            rebar_names.append(f.other_name.text())

        if not rebar_names:
            QMessageBox.warning(self, "Selection", "No rebar selected to create.")
            return

        self._result = CommandResult(
            title="Create Materials",
            ok=True,
            summary=f"Added rebar material(s): {', '.join(rebar_names)}.",
        )
        QMessageBox.information(
            self, "Done", f"The {', '.join(rebar_names)} rebar/s added to model."
        )

    @property
    def result(self) -> CommandResult | None:
        return self._result
