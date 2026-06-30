"""
Distance dialog — ported from
civilTools/py_widget/tools/distance_between_two_points.py.

Computes the distance between two points selected in ETABS (or the two ends of a
selected frame).  Shows dx / dy / dz / total distance, with Calculate (re-read the
ETABS selection) and Show (highlight the points in ETABS) actions.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult


class DistanceDialog(QDialog):
    """Distance between two ETABS points (or the ends of a frame)."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self._p1: str | None = None
        self._p2: str | None = None

        self.setWindowTitle("Distance Between Two Points")
        self.resize(320, 300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Selected points:"))
        self.point_list = QListWidget()
        self.point_list.setMaximumHeight(70)
        layout.addWidget(self.point_list)

        form = QFormLayout()
        self.dx = self._make_spin()
        self.dy = self._make_spin()
        self.dz = self._make_spin()
        self.dist = self._make_spin()
        form.addRow("dx (m):", self.dx)
        form.addRow("dy (m):", self.dy)
        form.addRow("dz (m):", self.dz)
        form.addRow("Distance (m):", self.dist)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.calc_button = QPushButton("Calculate")
        self.show_button = QPushButton("Show")
        btn_row.addWidget(self.calc_button)
        btn_row.addWidget(self.show_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        bbox = QDialogButtonBox()
        bbox.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        bbox.accepted.connect(self.accept)
        layout.addWidget(bbox)

        self.calc_button.clicked.connect(lambda: self.calculate(silent=False))
        self.show_button.clicked.connect(self.show_points)

        # Try an initial calculation silently (no warning if nothing is selected).
        self.calculate(silent=True)

    def _make_spin(self) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setReadOnly(True)
        sp.setDecimals(4)
        sp.setRange(-1e9, 1e9)
        sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return sp

    def _read_selection(self, silent: bool = False) -> bool:
        points = self._etabs.select_obj.get_selected_obj_type(1) or []
        frames = self._etabs.select_obj.get_selected_obj_type(2) or []
        if not points and not frames:
            if not silent:
                QMessageBox.information(
                    self,
                    "Selection",
                    "Please select two points or a frame in the ETABS model.",
                )
            return False
        if len(points) >= 2:
            self._p1, self._p2 = points[:2]
        elif frames:
            self._p1, self._p2, _ = self._etabs.SapModel.FrameObj.GetPoints(frames[0])
        else:
            if not silent:
                QMessageBox.information(
                    self, "Selection", "Select two points or a single frame."
                )
            return False
        self.point_list.clear()
        self.point_list.addItems([self._p1, self._p2])
        return True

    def calculate(self, silent: bool = False):
        if not self._read_selection(silent=silent):
            return
        self._etabs.set_current_unit("N", "m")
        dx, dy, dz, distance = self._etabs.points.get_distance_between_two_points(
            self._p1, self._p2
        )
        self.dx.setValue(dx)
        self.dy.setValue(dy)
        self.dz.setValue(dz)
        self.dist.setValue(distance)
        self._result = CommandResult(
            title="Distance",
            headers=["Point 1", "Point 2", "dx (m)", "dy (m)", "dz (m)", "Distance (m)"],
            rows=[[
                self._p1, self._p2,
                round(dx, 4), round(dy, 4), round(dz, 4), round(distance, 4),
            ]],
            summary=f"Distance between {self._p1} and {self._p2} = {distance:.4f} m",
            ok=True,
        )

    def show_points(self):
        if not self._p1 or not self._p2:
            return
        try:
            self._etabs.SapModel.SelectObj.ClearSelection()
            self._etabs.SapModel.PointObj.SetSelected(self._p1, True)
            self._etabs.SapModel.PointObj.SetSelected(self._p2, True)
            self._etabs.SapModel.View.RefreshView()
        except Exception as exc:
            QMessageBox.warning(self, "Show", str(exc))

    @property
    def result(self) -> CommandResult | None:
        return self._result
