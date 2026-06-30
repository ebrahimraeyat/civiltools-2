"""
Connect beams dialog — ported from civilTools/py_widget/tools/connect.py.

Select two beams in ETABS; the tool finds the intersection of their lines and
pre-selects the end of each beam nearest that intersection, then connects the
two beams at the chosen ends via ``etabs.frame_obj.connect_two_beams()``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from civiltools.commands.base import CommandResult


class ConnectBeamDialog(QDialog):
    """Connect two selected beams at their nearest ends."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._sap = etabs.SapModel
        self._result: CommandResult | None = None
        self._b1: str | None = None
        self._b2: str | None = None

        self.setWindowTitle("Connect Two Beams")
        self.resize(360, 300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the connection end on each beam:"))

        lists_row = QHBoxLayout()
        self.point_list1 = QListWidget()
        self.point_list2 = QListWidget()
        for title, lst in (("Beam 1", self.point_list1), ("Beam 2", self.point_list2)):
            box = QVBoxLayout()
            box.addWidget(QLabel(title))
            box.addWidget(lst)
            lists_row.addLayout(box)
        layout.addLayout(lists_row)

        self.refresh_button = QPushButton("Refresh from ETABS Selection")
        layout.addWidget(self.refresh_button)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        bbox.accepted.connect(self._connect)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

        self.refresh_button.clicked.connect(lambda: self.fill_points(silent=False))
        self.point_list1.itemClicked.connect(self._highlight)
        self.point_list2.itemClicked.connect(self._highlight)

        self.fill_points(silent=True)

    def _highlight(self):
        it1 = self.point_list1.currentItem()
        it2 = self.point_list2.currentItem()
        if it1 is None or it2 is None:
            return
        try:
            self._sap.SelectObj.ClearSelection()
            self._sap.PointObj.SetSelected(it1.text(), True)
            self._sap.PointObj.SetSelected(it2.text(), True)
            self._sap.View.RefreshView()
        except Exception:
            pass

    def fill_points(self, silent: bool = False):
        try:
            names = self._etabs.select_obj.get_selected_obj_type(2) or []
        except Exception:
            names = []
        if len(names) < 2:
            if not silent:
                QMessageBox.information(
                    self, "Selection", "Select at least two beams in ETABS."
                )
            return
        self._b1, self._b2 = names[:2]
        p1, p2, _ = self._sap.FrameObj.GetPoints(self._b1)
        p3, p4, _ = self._sap.FrameObj.GetPoints(self._b2)
        self.point_list1.clear()
        self.point_list2.clear()
        self.point_list1.addItems([p1, p2])
        self.point_list2.addItems([p3, p4])
        self._preselect_nearest(p1, p2, p3, p4)

    def _preselect_nearest(self, p1, p2, p3, p4):
        sap = self._sap
        x1, y1 = sap.PointObj.GetCoordCartesian(p1)[:2]
        x2, y2 = sap.PointObj.GetCoordCartesian(p2)[:2]
        x3, y3 = sap.PointObj.GetCoordCartesian(p3)[:2]
        x4, y4 = sap.PointObj.GetCoordCartesian(p4)[:2]
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denom == 0:
            # Parallel lines — default to the first end of each beam.
            self.point_list1.setCurrentRow(0)
            self.point_list2.setCurrentRow(0)
            return
        xp = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
        yp = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
        pts = self._etabs.points
        d1 = pts.get_distance_between_two_points_in_XY(p1, (xp, yp))
        d2 = pts.get_distance_between_two_points_in_XY(p2, (xp, yp))
        d3 = pts.get_distance_between_two_points_in_XY(p3, (xp, yp))
        d4 = pts.get_distance_between_two_points_in_XY(p4, (xp, yp))
        self.point_list1.setCurrentRow(0 if d1 < d2 else 1)
        self.point_list2.setCurrentRow(0 if d3 < d4 else 1)

    def _connect(self):
        it1 = self.point_list1.currentItem()
        it2 = self.point_list2.currentItem()
        if self._b1 is None or it1 is None or it2 is None:
            QMessageBox.information(
                self, "Selection", "Select a connection point on each beam."
            )
            return
        p1, p2 = it1.text(), it2.text()
        try:
            self._etabs.frame_obj.connect_two_beams((self._b1, self._b2), (p1, p2))
        except Exception as exc:
            QMessageBox.critical(self, "Connect Failed", str(exc))
            return
        self._result = CommandResult(
            title="Connect Beams",
            summary=f"Connected beams {self._b1} and {self._b2} at points {p1}, {p2}.",
            ok=True,
        )
        self.accept()

    @property
    def result(self) -> CommandResult | None:
        return self._result
