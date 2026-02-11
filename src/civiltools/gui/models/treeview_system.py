"""
Treeview model for structural system selection.

Ported from civilTools qt_models/treeview_system.py to PySide6.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtWidgets import QWidget

_DB_DIR = Path(__file__).resolve().parent.parent.parent / "db"

HEADERS = ("System", "Ru", "Omega", "Cd", "H_max", "alpha", "beta", "note", "ID")

# Persian category prefix letters used as group separators in systems.csv
_CATEGORY_LETTERS = {"ا", "ب", "پ", "ت", "ث"}


class CustomNode:
    """A tree node that holds one row of data."""

    def __init__(self, data):
        self._data = data
        if isinstance(data, tuple):
            self._data = list(data)
        if isinstance(data, str) or not hasattr(data, "__getitem__"):
            self._data = [data]
        self._columncount = len(self._data)
        self._children: list[CustomNode] = []
        self._parent: CustomNode | None = None
        self._row = 0

    def data(self, column: int):
        if 0 <= column < len(self._data):
            return self._data[column]
        return None

    def columnCount(self) -> int:
        return self._columncount

    def childCount(self) -> int:
        return len(self._children)

    def child(self, row: int) -> "CustomNode | None":
        if 0 <= row < self.childCount():
            return self._children[row]
        return None

    def parent(self) -> "CustomNode | None":
        return self._parent

    def row(self) -> int:
        return self._row

    def addChild(self, child: "CustomNode"):
        child._parent = self
        child._row = len(self._children)
        self._children.append(child)
        self._columncount = max(child.columnCount(), self._columncount)


class SystemTreeModel(QAbstractItemModel):
    """Qt item-model that exposes structural systems from systems.csv."""

    def __init__(self, nodes: list[CustomNode], headers=HEADERS, parent=None):
        super().__init__(parent)
        self._root = CustomNode(None)
        for node in nodes:
            self._root.addChild(node)
        self._headers = headers

    # ---- required overrides ----

    def rowCount(self, index=QModelIndex()):
        if index.isValid():
            return index.internalPointer().childCount()
        return self._root.childCount()

    def columnCount(self, index=QModelIndex()):
        if index.isValid():
            return index.internalPointer().columnCount()
        return self._root.columnCount()

    def index(self, row, column, parent=QModelIndex()):
        if parent is None or not parent.isValid():
            parent_node = self._root
        else:
            parent_node = parent.internalPointer()
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        child = parent_node.child(row)
        if child:
            return self.createIndex(row, column, child)
        return QModelIndex()

    def parent(self, index):
        if index.isValid():
            p = index.internalPointer().parent()
            if p and p is not self._root:
                return self.createIndex(p.row(), 0, p)
        return QModelIndex()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        column = index.column()
        if role == Qt.DisplayRole:
            return node.data(column)
        if role == Qt.TextAlignmentRole:
            if column == 0:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignHCenter | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        if role == Qt.TextAlignmentRole:
            if orientation == Qt.Horizontal:
                return int(Qt.AlignHCenter | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_system_nodes(csv_path: Path | None = None) -> list[CustomNode]:
    """Read systems.csv and return a list of root CustomNode objects."""
    if csv_path is None:
        csv_path = _DB_DIR / "systems.csv"
    items: dict[str, CustomNode] = {}
    root: CustomNode | None = None
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=",")
        for row in reader:
            first = row[0]
            if (len(first) > 1 and first[1] in _CATEGORY_LETTERS) or first[0] in _CATEGORY_LETTERS:
                root = CustomNode(first)
                items[first] = root
            elif root is not None:
                root.addChild(CustomNode(row))
    return list(items.values())


def setup_system_treeview(view, nodes: list[CustomNode] | None = None):
    """Populate a QTreeView with the system model and adjust column widths."""
    if nodes is None:
        nodes = load_system_nodes()
    view.setModel(SystemTreeModel(nodes, headers=HEADERS))
    view.setColumnWidth(0, 400)
    for i in range(1, len(HEADERS)):
        view.setColumnWidth(i, 40)


def get_treeview_item_prop(view) -> tuple[str, str, int, int] | None:
    """Extract (system, lateral, parent_row, child_row) from the selected item."""
    indexes = view.selectedIndexes()
    if not indexes:
        return None
    index = indexes[0]
    if not index.isValid():
        return None
    data = index.internalPointer()._data
    if len(data) == 1:
        return None  # selected a category header, not a system
    lateral = data[0].split("-")[1].lstrip(" ")
    parent_data = index.parent().data()
    system = parent_data.split("-")[1].lstrip(" ")
    i = index.parent().row()
    n = index.row()
    return system, lateral, i, n


def select_treeview_item(view, i: int, n: int):
    """Programmatically select item (parent row *i*, child row *n*)."""
    model = view.model()
    if model is None:
        return
    root_index = model.index(i, 0, QModelIndex())
    child_index = model.index(n, 0, root_index)
    view.clearSelection()
    view.setCurrentIndex(child_index)
    view.setExpanded(child_index, True)
