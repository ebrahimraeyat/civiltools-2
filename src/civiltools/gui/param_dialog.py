"""
Command parameter dialog — dynamically built from ``CommandParam`` list.

Matches how civilTools loads parameters from civiltools_config + .ui files,
but generates widgets programmatically instead of using Qt Designer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QLabel,
)


class ParamDialog(QDialog):
    """Dynamic dialog for command parameters."""

    def __init__(self, title: str, params: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._widgets: dict[str, object] = {}

        for p in params:
            widget = self._make_widget(p)
            self._widgets[p.name] = widget
            label = QLabel(p.label)
            if p.tooltip:
                label.setToolTip(p.tooltip)
                widget.setToolTip(p.tooltip)
            form.addRow(label, widget)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_widget(self, param):
        if param.param_type == "int":
            w = QSpinBox()
            w.setRange(0, 9999)
            w.setValue(int(param.default) if param.default is not None else 0)
            return w
        elif param.param_type == "float":
            w = QDoubleSpinBox()
            w.setRange(0.0, 9999.0)
            w.setDecimals(3)
            w.setSingleStep(0.1)
            w.setValue(float(param.default) if param.default is not None else 0.0)
            return w
        elif param.param_type == "combo":
            w = QComboBox()
            if param.choices:
                w.addItems(param.choices)
            if param.default and param.default in (param.choices or []):
                w.setCurrentText(param.default)
            return w
        else:  # str
            w = QLineEdit()
            w.setText(str(param.default) if param.default is not None else "")
            return w

    def get_values(self) -> dict:
        """Return dict of {param_name: value}."""
        result = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, QSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QComboBox):
                result[name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                result[name] = widget.text()
        return result
