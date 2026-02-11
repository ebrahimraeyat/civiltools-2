"""
Define Axes dialog — import DXF / AutoCAD, detect columns, create grid
axes, and export to ETABS.

Uses an embedded **matplotlib** canvas (2-D plan view) as the preview
and a lightweight undo/redo stack for every destructive operation.

Design: every method does **one thing** (zen of python).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QMessageBox, QListWidgetItem,
)

import matplotlib
matplotlib.use("Agg")                         # headless — we embed manually
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle as MplRect

from civiltools.commands.base import CommandResult
from civiltools.dxf.dxf_reader import DxfContent, DxfRect, read_dxf
from civiltools.dxf.autocad_reader import is_autocad_running, read_autocad_selection
from civiltools.dxf.column_detector import (
    detect_columns, build_axes, move_origin_to_intersection, GridAxes,
)
from civiltools.dxf.etabs_export import export_axes_to_etabs, export_columns_to_etabs
from civiltools.dxf.undo import Action, UndoStack
from civiltools.gui.helpers import set_dialog_icon

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# Colours
_COL_NORMAL_FACE = "#4488CC"
_COL_NORMAL_EDGE = "#224466"
_COL_SELECTED_FACE = "#FF6644"
_COL_SELECTED_EDGE = "#AA2200"
_COL_ALPHA = 0.6
_LINE_COLOR = "#999999"
_CIRCLE_COLOR = "#666666"
_XAXIS_COLOR = "#CC3333"
_YAXIS_COLOR = "#3366CC"


# ═══════════════════════════════════════════════════════════════════════════
# Undo-able actions — each does one thing
# ═══════════════════════════════════════════════════════════════════════════

class _DetectColumnsAction(Action):
    """Replace current columns with freshly detected ones."""

    description = "Detect Columns"

    def __init__(self, dialog: "DefineAxesDialog"):
        self._dlg = dialog
        self._prev: list[DxfRect] = []
        self._detected: list[DxfRect] = []

    def redo(self) -> None:
        self._prev = list(self._dlg._columns)
        self._detected = _run_detection(self._dlg)
        self._dlg._columns = list(self._detected)
        self._dlg._selected_indices.clear()
        self._dlg._refresh_canvas()

    def undo(self) -> None:
        self._dlg._columns = list(self._prev)
        self._dlg._selected_indices.clear()
        self._dlg._refresh_canvas()


class _RemoveColumnsAction(Action):
    """Remove the currently selected columns."""

    description = "Remove Selected Columns"

    def __init__(self, dialog: "DefineAxesDialog"):
        self._dlg = dialog
        self._prev: list[DxfRect] = []
        self._removed_indices: set[int] = set()

    def redo(self) -> None:
        self._prev = list(self._dlg._columns)
        self._removed_indices = set(self._dlg._selected_indices)
        self._dlg._columns = [
            c for i, c in enumerate(self._prev) if i not in self._removed_indices
        ]
        self._dlg._selected_indices.clear()
        self._dlg._refresh_canvas()

    def undo(self) -> None:
        self._dlg._columns = list(self._prev)
        self._dlg._selected_indices.clear()
        self._dlg._refresh_canvas()


class _CreateAxesAction(Action):
    """Build grid axes from detected column centres."""

    description = "Create Axes"

    def __init__(self, dialog: "DefineAxesDialog"):
        self._dlg = dialog
        self._prev_axes: GridAxes | None = None
        self._prev_content: DxfContent | None = None
        self._prev_columns: list[DxfRect] = []

    def redo(self) -> None:
        self._prev_axes = copy.deepcopy(self._dlg._axes)
        self._prev_content = copy.deepcopy(self._dlg._content)
        self._prev_columns = copy.deepcopy(self._dlg._columns)
        _build_axes_from_dialog(self._dlg)
        self._dlg._refresh_canvas()

    def undo(self) -> None:
        self._dlg._axes = self._prev_axes
        self._dlg._content = self._prev_content
        self._dlg._columns = self._prev_columns
        self._dlg._selected_indices.clear()
        self._dlg._refresh_canvas()


# ═══════════════════════════════════════════════════════════════════════════
# Pure helpers used by actions — each does one thing
# ═══════════════════════════════════════════════════════════════════════════

def _run_detection(dlg: "DefineAxesDialog") -> list[DxfRect]:
    """Run column detection using current dialog settings."""
    source_map = {"Block": "block", "Hatch": "hatch", "Polyline": "polyline"}
    src = dlg.ui.col_source_combo.currentText()
    name = dlg.ui.col_name_combo.currentText()
    return detect_columns(
        dlg._content,
        source_filter=source_map.get(src),
        name_filter=name if name != "(all)" else None,
    )


def _build_axes_from_dialog(dlg: "DefineAxesDialog") -> None:
    """Build axes and optionally move origin — mutates dialog state."""
    x_style = dlg.ui.x_style_combo.currentText()
    snap_tol = dlg.ui.snap_spinbox.value()
    dlg._axes = build_axes(dlg._columns, x_style=x_style, snap_tolerance=snap_tol)

    if dlg.ui.chk_move_origin.isChecked():
        move_origin_to_intersection(dlg._axes, dlg._columns, dlg._content)


# ═══════════════════════════════════════════════════════════════════════════
# Dialog
# ═══════════════════════════════════════════════════════════════════════════

class DefineAxesDialog(QDialog):
    """DXF → columns → grid axes → ETABS export, with matplotlib preview."""

    def __init__(self, etabs: Any = None, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self.result: CommandResult | None = None

        # State
        self._content: DxfContent | None = None
        self._columns: list[DxfRect] = []
        self._selected_indices: set[int] = set()
        self._axes: GridAxes | None = None
        self._undo = UndoStack()

        # Patch index stored on each matplotlib column rectangle
        self._column_patches: list[MplRect] = []

        self._load_ui()
        self._setup_canvas()
        self._connect_signals()
        self._fill_levels()
        self._update_undo_buttons()
        self._update_remove_button()

    # ── UI setup (one-task methods) ─────────────────────────────────

    def _load_ui(self) -> None:
        """Load the .ui file and embed it in this QDialog."""
        loader = QUiLoader()
        ui_path = _UI_DIR / "define" / "define_axes.ui"
        ui_file = QFile(str(ui_path))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setWindowTitle(self.ui.windowTitle())
        self.resize(self.ui.size())
        set_dialog_icon(self, "grid_lines.svg")

    def _setup_canvas(self) -> None:
        """Create the matplotlib Figure, Canvas, Toolbar and embed them."""
        self._figure = Figure(figsize=(6, 6), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        self._toolbar = NavToolbar(self._canvas, self.ui.canvas_container)

        canvas_layout = self.ui.canvas_container.layout()
        placeholder = self.ui.canvas_placeholder
        canvas_layout.removeWidget(placeholder)
        placeholder.deleteLater()
        canvas_layout.addWidget(self._toolbar)
        canvas_layout.addWidget(self._canvas)

        self._ax = self._figure.add_subplot(111)
        _reset_axes(self._ax)
        self._canvas.draw()

        # Connect pick event for column selection
        self._canvas.mpl_connect("pick_event", self._on_pick)

    def _connect_signals(self) -> None:
        """Wire up every button / combo to its handler."""
        self.ui.btn_import.clicked.connect(self._on_import)
        self.ui.btn_detect_columns.clicked.connect(self._on_detect_columns)
        self.ui.btn_remove_selected.clicked.connect(self._on_remove_selected)
        self.ui.btn_create_axes.clicked.connect(self._on_create_axes)
        self.ui.btn_export_etabs.clicked.connect(self._on_export_etabs)
        self.ui.btn_refresh_levels.clicked.connect(self._fill_levels)
        self.ui.btn_undo.clicked.connect(self._on_undo)
        self.ui.btn_redo.clicked.connect(self._on_redo)
        self.ui.btn_close.clicked.connect(self.reject)
        self.ui.col_source_combo.currentIndexChanged.connect(self._update_name_combo)
        self.ui.radio_autocad.toggled.connect(self._on_source_toggled)

    # ── Import handlers ─────────────────────────────────────────────

    def _on_source_toggled(self, checked: bool) -> None:
        """Enable/disable DXF-file-specific controls."""
        is_file = self.ui.radio_dxf_file.isChecked()
        for chk in (self.ui.chk_blocks, self.ui.chk_hatches,
                     self.ui.chk_lines, self.ui.chk_polylines):
            chk.setEnabled(is_file)

    def _on_import(self) -> None:
        """Dispatch import to the correct source handler."""
        self._undo.clear()
        if self.ui.radio_dxf_file.isChecked():
            self._import_from_file()
        else:
            self._import_from_autocad()
        self._update_undo_buttons()

    def _import_from_file(self) -> None:
        """Open a DXF file and populate ``_content``."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf)",
        )
        if not filepath:
            return
        try:
            self._content = read_dxf(filepath, unit=self._drawing_unit())
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._reset_after_import()

    def _import_from_autocad(self) -> None:
        """Read selected entities from a live AutoCAD instance."""
        if not is_autocad_running():
            QMessageBox.warning(
                self, "AutoCAD",
                "AutoCAD is not running.\nPlease start AutoCAD and try again.",
            )
            return
        try:
            self._content = read_autocad_selection(unit=self._drawing_unit())
        except RuntimeError as exc:
            QMessageBox.warning(self, "AutoCAD Selection", str(exc))
            return
        self._reset_after_import()

    def _reset_after_import(self) -> None:
        """Clear derived state after a fresh import."""
        self._columns.clear()
        self._selected_indices.clear()
        self._axes = None
        self._update_name_combo()
        self._refresh_canvas()
        self._update_remove_button()
        self.ui.btn_detect_columns.setEnabled(True)

    def _drawing_unit(self) -> str:
        """Return the currently selected drawing unit string."""
        return self.ui.unit_combo.currentText()

    # ── Column detection ────────────────────────────────────────────

    def _update_name_combo(self) -> None:
        """Populate the name combo based on source type and content."""
        combo = self.ui.col_name_combo
        combo.clear()
        combo.addItem("(all)")
        if self._content is None:
            return
        src = self.ui.col_source_combo.currentText()
        if src in ("All", "Block"):
            combo.addItems(self._content.block_names)
        if src in ("All", "Hatch"):
            combo.addItems(self._content.hatch_patterns)

    def _on_detect_columns(self) -> None:
        """Push a detect-columns action onto the undo stack."""
        if self._content is None:
            QMessageBox.warning(self, "No Data", "Import a DXF or AutoCAD selection first.")
            return
        self._undo.push(_DetectColumnsAction(self))
        self._update_undo_buttons()
        self._update_remove_button()
        if not self._columns:
            QMessageBox.information(self, "Columns", "No column-like rectangles detected.")

    # ── Column selection (click-to-select) ──────────────────────────

    def _on_pick(self, event) -> None:
        """Handle a matplotlib pick event on a column rectangle."""
        artist = event.artist
        idx = getattr(artist, "_col_index", None)
        if idx is None:
            return

        mouse = event.mouseevent
        if mouse.key == "shift":
            # Shift+click: add to selection
            self._selected_indices.add(idx)
        elif mouse.key == "control":
            # Ctrl+click: toggle
            self._selected_indices.symmetric_difference_update({idx})
        else:
            # Plain click: exclusive select (or deselect if already sole)
            if self._selected_indices == {idx}:
                self._selected_indices.clear()
            else:
                self._selected_indices = {idx}

        self._update_column_highlight()
        self._update_remove_button()

    def _update_column_highlight(self) -> None:
        """Recolour column patches to reflect the current selection."""
        for patch in self._column_patches:
            idx = getattr(patch, "_col_index", None)
            if idx is None:
                continue
            if idx in self._selected_indices:
                patch.set_facecolor(_COL_SELECTED_FACE)
                patch.set_edgecolor(_COL_SELECTED_EDGE)
            else:
                patch.set_facecolor(_COL_NORMAL_FACE)
                patch.set_edgecolor(_COL_NORMAL_EDGE)
        self._canvas.draw_idle()

    def _update_remove_button(self) -> None:
        """Enable the remove button only when columns are selected."""
        n = len(self._selected_indices)
        self.ui.btn_remove_selected.setEnabled(n > 0)
        if n:
            self.ui.btn_remove_selected.setText(f"Remove Selected ({n})")
        else:
            self.ui.btn_remove_selected.setText("Remove Selected Columns")

    def _on_remove_selected(self) -> None:
        """Push a remove-columns action for the current selection."""
        if not self._selected_indices:
            return
        self._undo.push(_RemoveColumnsAction(self))
        self._update_undo_buttons()
        self._update_remove_button()

    # ── Axis creation ───────────────────────────────────────────────

    def _on_create_axes(self) -> None:
        """Push a create-axes action."""
        if not self._columns:
            QMessageBox.warning(self, "No Columns", "Detect columns first.")
            return
        self._undo.push(_CreateAxesAction(self))
        self._update_undo_buttons()

    # ── ETABS export ────────────────────────────────────────────────

    def _fill_levels(self) -> None:
        """Populate the levels list from ETABS."""
        self.ui.levels_list.clear()
        if self._etabs is None or not getattr(self._etabs, "success", False):
            return
        try:
            names = self._etabs.story.get_sorted_story_name(reverse=True, include_base=True)
        except Exception:
            return
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.ui.levels_list.addItem(item)

    def _on_export_etabs(self) -> None:
        """Export axes + columns to ETABS."""
        if not _check_etabs_ready(self._etabs, self):
            return
        if not self._axes and not self._columns:
            QMessageBox.warning(self, "No Data", "Create axes / detect columns first.")
            return

        _prepare_etabs(self._etabs, purge=self.ui.chk_purge.isChecked())

        grid_name = _export_grid(self._etabs, self._axes)
        checked, all_levels = _gather_levels(self.ui.levels_list)
        ncols = _export_cols(self._etabs, self._columns, checked, all_levels)

        _save_etabs(self._etabs)

        QMessageBox.information(
            self, "Export Complete",
            f"{ncols} columns added.\nGrid system: {grid_name or 'N/A'}",
        )
        self.result = CommandResult(
            title="Define Axes", ok=True,
            summary=f"{ncols} columns, grid: {grid_name}",
        )
        self.accept()

    # ── Undo / Redo ─────────────────────────────────────────────────

    def _on_undo(self) -> None:
        self._undo.undo()
        self._update_undo_buttons()
        self._update_remove_button()

    def _on_redo(self) -> None:
        self._undo.redo()
        self._update_undo_buttons()
        self._update_remove_button()

    def _update_undo_buttons(self) -> None:
        """Sync undo/redo button enable & tooltip with the stack."""
        self.ui.btn_undo.setEnabled(self._undo.can_undo)
        self.ui.btn_redo.setEnabled(self._undo.can_redo)
        self.ui.btn_undo.setToolTip(
            f"Undo: {self._undo.undo_text}" if self._undo.can_undo else "",
        )
        self.ui.btn_redo.setToolTip(
            f"Redo: {self._undo.redo_text}" if self._undo.can_redo else "",
        )

    # ── Canvas refresh — decomposed into single-task drawers ───────

    def _refresh_canvas(self) -> None:
        """Full redraw of the 2-D plan view."""
        self._column_patches.clear()
        ax = self._ax
        ax.clear()
        _reset_axes(ax)

        if self._content is None:
            self._canvas.draw()
            return

        _draw_lines(ax, self._content.lines)
        _draw_circles(ax, self._content.circles)
        self._column_patches = _draw_columns(
            ax, self._columns, self._selected_indices,
        )
        if self._axes:
            _draw_grid_axes(ax, self._axes)

        ax.autoscale_view()
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        self._figure.tight_layout()
        self._canvas.draw()


# ═══════════════════════════════════════════════════════════════════════════
# Pure drawing helpers — each draws ONE thing (zen of python)
# ═══════════════════════════════════════════════════════════════════════════

def _reset_axes(ax) -> None:
    """Set common axes properties."""
    ax.set_aspect("equal")
    ax.set_title("Plan View")
    ax.grid(True, alpha=0.3)


def _draw_lines(ax, lines) -> None:
    """Draw all DxfLine entities as thin grey segments."""
    for ln in lines:
        ax.plot(
            [ln.start.x, ln.end.x], [ln.start.y, ln.end.y],
            color=_LINE_COLOR, linewidth=0.5,
        )


def _draw_circles(ax, circles) -> None:
    """Draw all DxfCircle entities as unfilled circles."""
    for c in circles:
        ax.add_patch(plt.Circle(
            (c.center.x, c.center.y), c.radius,
            fill=False, edgecolor=_CIRCLE_COLOR, linewidth=0.5,
        ))


def _draw_columns(
    ax, columns: list[DxfRect], selected: set[int],
) -> list[MplRect]:
    """Draw column rectangles with selection highlight.  Returns patch list."""
    patches: list[MplRect] = []
    for i, col in enumerate(columns):
        is_sel = i in selected
        rect = MplRect(
            (col.center.x - col.width / 2, col.center.y - col.height / 2),
            col.width, col.height,
            angle=col.rotation,
            rotation_point="center",
            fill=True,
            facecolor=_COL_SELECTED_FACE if is_sel else _COL_NORMAL_FACE,
            edgecolor=_COL_SELECTED_EDGE if is_sel else _COL_NORMAL_EDGE,
            alpha=_COL_ALPHA, linewidth=1,
            picker=True,           # enable pick events
        )
        rect._col_index = i       # custom attr so pick handler knows which column
        ax.add_patch(rect)
        ax.plot(col.center.x, col.center.y, "k+", markersize=4)
        patches.append(rect)
    return patches


def _draw_grid_axes(ax, axes: GridAxes) -> None:
    """Draw X and Y grid lines with circled labels."""
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    pad_x = (xlim[1] - xlim[0]) * 0.1 if xlim[1] != xlim[0] else 1000
    pad_y = (ylim[1] - ylim[0]) * 0.1 if ylim[1] != ylim[0] else 1000

    _draw_x_gridlines(ax, axes.x_lines, ylim, pad_y)
    _draw_y_gridlines(ax, axes.y_lines, xlim, pad_x)


def _draw_x_gridlines(ax, x_lines, ylim, pad_y) -> None:
    """Draw vertical (X) grid lines."""
    y_top = (ylim[1] if ylim[0] != ylim[1] else 1000) + pad_y
    for gl in x_lines:
        ax.axvline(gl.coordinate, color=_XAXIS_COLOR, linewidth=0.8,
                    linestyle="--", alpha=0.7)
        ax.text(
            gl.coordinate, y_top + pad_y * 0.3, gl.label,
            ha="center", va="bottom", fontsize=9, fontweight="bold",
            color=_XAXIS_COLOR,
            bbox=dict(boxstyle="circle", facecolor="white",
                      edgecolor=_XAXIS_COLOR, linewidth=1.2),
        )


def _draw_y_gridlines(ax, y_lines, xlim, pad_x) -> None:
    """Draw horizontal (Y) grid lines."""
    x_left = (xlim[0] if xlim[0] != xlim[1] else -1000) - pad_x
    for gl in y_lines:
        ax.axhline(gl.coordinate, color=_YAXIS_COLOR, linewidth=0.8,
                    linestyle="--", alpha=0.7)
        ax.text(
            x_left - pad_x * 0.3, gl.coordinate, gl.label,
            ha="right", va="center", fontsize=9, fontweight="bold",
            color=_YAXIS_COLOR,
            bbox=dict(boxstyle="circle", facecolor="white",
                      edgecolor=_YAXIS_COLOR, linewidth=1.2),
        )


# ═══════════════════════════════════════════════════════════════════════════
# ETABS export helpers — each does one thing
# ═══════════════════════════════════════════════════════════════════════════

def _check_etabs_ready(etabs, parent) -> bool:
    """Return True if ETABS is connected and show a warning otherwise."""
    if etabs is None or not getattr(etabs, "success", False):
        QMessageBox.warning(parent, "ETABS", "Not connected to ETABS.")
        return False
    return True


def _prepare_etabs(etabs, *, purge: bool) -> None:
    """Set units, unlock, and optionally purge the ETABS model."""
    if purge:
        try:
            etabs.purge_model()
            etabs.view.refresh_view()
        except Exception:
            pass
    etabs.set_current_unit("N", "mm")
    etabs.unlock_model()


def _export_grid(etabs, axes: GridAxes | None) -> str:
    """Export grid axes to ETABS.  Returns the grid system name."""
    if not axes:
        return ""
    return export_axes_to_etabs(etabs, axes)


def _gather_levels(levels_list) -> tuple[list[str], list[str]]:
    """Return ``(checked_levels, all_levels)`` from the QListWidget."""
    all_levels: list[str] = []
    checked: list[str] = []
    for i in range(levels_list.count()):
        item = levels_list.item(i)
        all_levels.append(item.text())
        if item.checkState() == Qt.CheckState.Checked:
            checked.append(item.text())
    return checked, all_levels


def _export_cols(etabs, columns, checked, all_levels) -> int:
    """Export columns to ETABS.  Returns the count exported."""
    if not columns or not checked:
        return 0
    return export_columns_to_etabs(etabs, columns, checked, all_levels)


def _save_etabs(etabs) -> None:
    """Save the ETABS file silently."""
    try:
        etabs.SapModel.File.Save()
    except Exception:
        pass
