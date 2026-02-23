"""
Live Load Management Dialog.

Layout
------
Top-left  : project / floor / area tree with load-pattern combos.
Top-right : properties panel, favorites bar, Persian load catalog.
Bottom    : floor plan viewer (full width) with story-navigation arrows.

Features
--------
* Auto-loads from ETABS on open.
* Save / restore per-model assignments (JSON next to .EDB).
* Top-5 most-used loads (persisted in %APPDATA%/civiltools).
* Gradient-coloured floor plan; click area → select in tree.
* Drag from catalog → drop on plan area or floor.
* Up / down arrows to navigate stories (looping).
* Auto-set load-pattern type by category (roof → ROOF Live, residential
  → Reducible Live, etc.).
* Tree collapsed by default (only project + floors visible).
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QMimeData, QPointF, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPen,
    QPolygonF,
)

from civiltools.building.database import LiveLoadDatabase
from civiltools.building.etabs_reader import ETABSProjectBuilder
from civiltools.building.models import Area, Floor, LoadSource, Point, Project
from civiltools.commands.base import CommandResult

log = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────
_REDUCIBLE_THRESHOLD = 500.0  # kgf/m²
_CSV_PATH = Path(__file__).resolve().parents[2] / "db" / "live_loads.csv"
_GLOBAL_PREFS_DIR = Path.home() / "AppData" / "Roaming" / "civiltools"
_FAVORITES_FILE = _GLOBAL_PREFS_DIR / "live_load_favorites.json"
_NUM_RE = re.compile(r"^[\d.]+$")
_MIME_CATALOG = "application/x-civiltools-liveload"
_MAX_FAVORITES = 10


# ── Helper functions ────────────────────────────────────────────────
def _parse_load_value(text: str) -> float | None:
    text = text.strip()
    return float(text) if _NUM_RE.match(text) else None


def _get_root_code(code: str) -> str:
    """Return the root category code for *code* (e.g. '2-1' → '1')."""
    return code.rsplit("-", 1)[-1] if "-" in code else code


def _load_to_color(val: float | None, lo: float = 0.0, hi: float = 1000.0) -> QColor:
    """Map a load value to a green → yellow → red gradient."""
    if val is None:
        return QColor("#e0e0e0")
    span = hi - lo if hi > lo else 1.0
    t = max(0.0, min(1.0, (val - lo) / span))
    if t < 0.5:
        f = t * 2
        r = int(76 + (250 - 76) * f)
        g = int(217 + (204 - 217) * f)
        b = int(100 + (21 - 100) * f)
    else:
        f = (t - 0.5) * 2
        r = int(250 + (239 - 250) * f)
        g = int(204 + (68 - 204) * f)
        b = int(21 + (68 - 21) * f)
    return QColor(r, g, b)


# ── Custom widgets ──────────────────────────────────────────────────
class _CatalogTree(QTreeWidget):
    """QTreeWidget that supports *dragging* catalog items."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    # Qt calls this to build the MIME payload
    def mimeData(self, items):  # noqa: N802
        md = QMimeData()
        if items:
            it = items[0]
            # "code|load_text|name"
            md.setText(f"{it.text(0).strip()}|{it.text(2).strip()}|{it.text(1).strip()}")
        return md


class _PlanView(QGraphicsView):
    """QGraphicsView that accepts *drops* and emits click / drop signals."""

    area_clicked = Signal(str)           # area_id
    area_dropped = Signal(str, str)      # area_id, mime_text
    floor_dropped = Signal(str)          # mime_text  (outside any area)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._polys: dict[str, QPolygonF] = {}

    def set_area_polygons(self, polys: dict[str, QPolygonF]):
        self._polys = polys

    # -- Drag-and-drop ------------------------------------------------
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):   # noqa: N802
        e.acceptProposedAction()

    def dropEvent(self, e):       # noqa: N802
        pos = self.mapToScene(e.position().toPoint())
        txt = e.mimeData().text()
        for aid, poly in self._polys.items():
            if poly.containsPoint(QPointF(pos.x(), pos.y()), Qt.FillRule.OddEvenFill):
                self.area_dropped.emit(aid, txt)
                e.acceptProposedAction()
                return
        self.floor_dropped.emit(txt)
        e.acceptProposedAction()

    # -- Click-to-select ----------------------------------------------
    def mousePressEvent(self, e):  # noqa: N802
        pos = self.mapToScene(e.position().toPoint())
        for aid, poly in self._polys.items():
            if poly.containsPoint(QPointF(pos.x(), pos.y()), Qt.FillRule.OddEvenFill):
                self.area_clicked.emit(aid)
                return
        super().mousePressEvent(e)


# ════════════════════════════════════════════════════════════════════
#  Main dialog
# ════════════════════════════════════════════════════════════════════
class LiveLoadDialog(QDialog):
    """Dialog for managing live loads across floors and areas."""

    def __init__(self, etabs, parent=None):
        super().__init__(parent)
        self._etabs = etabs
        self._result: CommandResult | None = None
        self.database = LiveLoadDatabase()
        self.project: Project | None = None

        # CSV lookups
        self._code_to_load: dict[str, float] = {}
        self._code_to_name: dict[str, str] = {}
        self._code_non_reducible: dict[str, bool] = {}

        # Load-pattern data
        self._all_live_patterns: list[str] = []
        self._reducible_patterns: set[str] = set()
        self._roof_live_patterns: set[str] = set()

        # Combo references
        self._floor_combos: dict[str, QComboBox] = {}
        self._area_combos: dict[tuple[str, str], QComboBox] = {}

        # Frame context data (beams/columns per story)
        self._frame_data: dict[str, list[tuple]] = {}  # fid → [(type,x1,y1,x2,y2), …]

        # Undo / redo
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

        # Floor navigation
        self._floor_ids: list[str] = []
        self._current_floor_idx: int = 0

        self.setWindowTitle("Live Load Management")
        self.resize(1100, 800)

        self._setup_ui()
        self._connect_signals()

        # Auto-load on open
        self._try_auto_load()

    # ================================================================
    #  UI
    # ================================================================
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # ── top splitter (tree | right panel) ───────────────────────
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: project tree
        left_w = QWidget()
        left_lay = QVBoxLayout(left_w)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Use Type", "Live Load (kgf/m²)", "Load Pattern"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        left_lay.addWidget(self.tree)
        top_splitter.addWidget(left_w)

        # ── Right: floor plan + navigation ─────────────────────────
        plan_w = QWidget()
        plan_outer = QHBoxLayout(plan_w)
        plan_outer.setContentsMargins(0, 0, 0, 0)

        plan_navigation = QVBoxLayout()
        self.btn_prev_floor = QToolButton()
        self.btn_prev_floor.setArrowType(Qt.ArrowType.UpArrow)
        self.btn_prev_floor.setToolTip("Previous floor")
        plan_navigation.addWidget(self.btn_prev_floor)

        self.btn_next_floor = QToolButton()
        self.btn_next_floor.setArrowType(Qt.ArrowType.DownArrow)
        self.btn_next_floor.setToolTip("Next floor")
        plan_navigation.addWidget(self.btn_next_floor)

        plan_inner = QVBoxLayout()
        self.lbl_floor_name = QLabel("Floor Plan")
        self.lbl_floor_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bold_font = QFont()
        bold_font.setBold(True)
        self.lbl_floor_name.setFont(bold_font)
        plan_inner.addWidget(self.lbl_floor_name)

        self.plan_scene = QGraphicsScene(self)
        self.plan_view = _PlanView()
        self.plan_view.setScene(self.plan_scene)
        self.plan_view.setMinimumHeight(180)
        plan_inner.addWidget(self.plan_view)
        plan_outer.addLayout(plan_inner, 1)
        plan_outer.addLayout(plan_navigation)

        top_splitter.addWidget(plan_w)
        root.addWidget(top_splitter, 2)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 2)

        
        # BOTTOM: properties + favorites + catalog
        bot_w = QWidget()
        right_lay = QVBoxLayout(bot_w)
        right_lay.setContentsMargins(0, 0, 0, 0)
        catalog_lay = QHBoxLayout()
        catalog_lay.setContentsMargins(0, 0, 0, 0)

        # Properties
        self.prop_group = QGroupBox("Properties")
        pl = QFormLayout(self.prop_group)
        self.lbl_id = QLabel("-")
        pl.addRow("ID:", self.lbl_id)
        self.lbl_use_type = QLabel("-")
        self.lbl_use_type.setWordWrap(True)
        pl.addRow("Use Type:", self.lbl_use_type)
        self.spin_manual = QDoubleSpinBox()
        self.spin_manual.setRange(0, 10000)
        self.spin_manual.setDecimals(0)
        self.spin_manual.setSpecialValueText("None")
        self.spin_manual.setValue(0)
        pl.addRow("Manual Load (kgf/m²):", self.spin_manual)
        self.chk_balcony = QCheckBox("Balcony")
        pl.addRow("", self.chk_balcony)
        self.lbl_calc_load = QLabel("-")
        pl.addRow("Calculated Load:", self.lbl_calc_load)
        self.lbl_source = QLabel("-")
        pl.addRow("Load Source:", self.lbl_source)
        self.lbl_notes = QLabel("-")
        self.lbl_notes.setWordWrap(True)
        pl.addRow("Notes:", self.lbl_notes)
        self.prop_group.setFixedWidth(280)
        catalog_lay.addWidget(self.prop_group)

        # Favorites
        self.fav_group = QGroupBox("Favorites (most used)")
        fav_lay = QVBoxLayout(self.fav_group)
        self._fav_buttons: list[QPushButton] = []
        for _ in range(_MAX_FAVORITES):
            btn = QPushButton("-")
            btn.setEnabled(False)
            btn.setToolTip("")
            fav_lay.addWidget(btn)
            self._fav_buttons.append(btn)
        catalog_lay.addWidget(self.fav_group)

        # Catalog
        self.catalog_group = QGroupBox(
            "Live Load Catalog  —  double-click or drag to floor plan"
        )
        cat_lay = QVBoxLayout(self.catalog_group)
        self.load_tree = _CatalogTree()
        self.load_tree.setHeaderLabels(["Code", "Use Type", "Load (kgf/m²)"])
        self.load_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.load_tree.header().setStretchLastSection(True)
        self.load_tree.setColumnWidth(0, 50)
        self.load_tree.setColumnWidth(1, 350)
        cat_lay.addWidget(self.load_tree)
        catalog_lay.addWidget(self.catalog_group)
        right_lay.addLayout(catalog_lay, 1)

        root.addWidget(bot_w, 1)

        # ── button bar ──────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setEnabled(False)
        self.btn_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setEnabled(False)
        self.btn_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.btn_apply = QPushButton("Apply to ETABS")
        self.btn_apply.setEnabled(False)
        self.btn_close = QPushButton("Close")
        btn_bar.addWidget(self.btn_undo)
        btn_bar.addWidget(self.btn_redo)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_apply)
        btn_bar.addWidget(self.btn_close)
        root.addLayout(btn_bar)

        self._enable_properties(False)
        self._load_persian_load_tree()
        self._load_favorites_ui()

    # ================================================================
    #  Signals
    # ================================================================
    def _connect_signals(self):
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_apply.clicked.connect(self._apply_to_etabs)
        self.btn_close.clicked.connect(self.reject)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.spin_manual.valueChanged.connect(self._on_property_changed)
        self.chk_balcony.stateChanged.connect(self._on_property_changed)
        self.load_tree.itemDoubleClicked.connect(self._on_catalog_applied)
        self.btn_prev_floor.clicked.connect(lambda: self._navigate_floor(-1))
        self.btn_next_floor.clicked.connect(lambda: self._navigate_floor(1))
        self.plan_view.area_clicked.connect(self._on_plan_area_clicked)
        self.plan_view.area_dropped.connect(self._on_plan_area_dropped)
        self.plan_view.floor_dropped.connect(self._on_plan_floor_dropped)

        for btn in self._fav_buttons:
            btn.clicked.connect(self._on_fav_clicked)

    def _enable_properties(self, enable: bool):
        self.prop_group.setEnabled(enable)

    # ================================================================
    #  Undo / Redo
    # ================================================================
    def _capture_state(self) -> dict:
        """Snapshot current area/floor assignments for undo."""
        if not self.project:
            return {}
        state: dict = {"default_use": self.project.default_use, "floors": {}}
        for fid, floor in self.project.floors.items():
            fs: dict = {"default_use": floor.default_use, "areas": {}}
            for aid, area in floor.areas.items():
                fs["areas"][aid] = {
                    "use_type": area.use_type,
                    "manual_override": area.manual_override,
                    "is_balcony": area.is_balcony,
                }
            state["floors"][fid] = fs
        return state

    def _push_undo(self):
        """Save current state to undo stack before a change."""
        self._undo_stack.append(self._capture_state())
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _restore_state(self, state: dict):
        """Apply a previously captured state snapshot."""
        if not self.project or not state:
            return
        self.project.default_use = state.get("default_use")
        for fid, fs in state.get("floors", {}).items():
            floor = self.project.floors.get(fid)
            if not floor:
                continue
            floor.default_use = fs.get("default_use")
            for aid, ad in fs.get("areas", {}).items():
                area = floor.areas.get(aid)
                if not area:
                    continue
                area.use_type = ad.get("use_type")
                area.manual_override = ad.get("manual_override")
                area.is_balcony = ad.get("is_balcony", False)
        self._update_tree_loads()
        self._on_selection_changed()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._capture_state())
        self._restore_state(self._undo_stack.pop())
        self._update_undo_redo_buttons()

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._capture_state())
        self._restore_state(self._redo_stack.pop())
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))

    # ================================================================
    #  ETABS I/O
    # ================================================================
    def _try_auto_load(self):
        """Silently attempt to load from ETABS when the dialog opens."""
        try:
            self._load_from_etabs()
        except Exception:
            pass

    def _load_from_etabs(self):
        try:
            builder = ETABSProjectBuilder(self._etabs)
            self.project = builder.build()
            self._fetch_live_load_patterns()
            self._populate_floor_areas()
            self._floor_ids = list(self.project.floors.keys())
            self._current_floor_idx = 0
            self._restore_model_data()
            self._populate_tree()
            self.btn_apply.setEnabled(True)
            if self._floor_ids:
                self._render_floor_plan(self._floor_ids[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load from ETABS:\n{e}")

    def _apply_to_etabs(self):
        if not self.project:
            return
        if not self._all_live_patterns:
            QMessageBox.warning(
                self, "Warning",
                "No live load patterns found in the model.\n"
                "Please define at least one Live load pattern first.",
            )
            return

        applied = 0
        errors: list[str] = []
        try:
            self._etabs.set_current_unit("kgf", "m")
            for fid, floor in self.project.floors.items():
                fc = self._floor_combos.get(fid)
                fpat = fc.currentText() if fc else ""
                for aid in floor.areas:
                    ac = self._area_combos.get((fid, aid))
                    pat = ac.currentText() if ac else fpat
                    if not pat:
                        continue
                    val = self._resolve_area_load(fid, aid)
                    if val is None:
                        continue
                    try:
                        # Remove existing live loads before assigning new
                        for ep in self._all_live_patterns:
                            try:
                                self._etabs.SapModel.AreaObj.DeleteLoadUniform(aid, ep)
                            except Exception:
                                pass
                        self._etabs.SapModel.AreaObj.SetLoadUniform(aid, pat, -val, 6)
                        applied += 1
                    except Exception as exc:
                        errors.append(f"{aid}: {exc}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply:\n{e}")
            return

        self._save_model_data()
        msg = f"Applied live load to {applied} area(s)."
        if errors:
            msg += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:10])
            QMessageBox.warning(self, "Partial Success", msg)
        else:
            QMessageBox.information(self, "Success", msg)
        # self.accept()

    def _resolve_area_load(self, fid: str, aid: str) -> float | None:
        if not self.project:
            return None
        floor = self.project.floors.get(fid)
        if not floor:
            return None
        area = floor.areas.get(aid)
        if not area:
            return None
        if area.manual_override is not None:
            return area.manual_override
        code = area.use_type or floor.default_use or (self.project.default_use if self.project else None)
        if code and code in self._code_to_load:
            return self._code_to_load[code]
        return None

    # ================================================================
    #  Load-pattern helpers
    # ================================================================
    def _fetch_live_load_patterns(self):
        self._all_live_patterns = []
        self._reducible_patterns = set()
        self._roof_live_patterns = set()
        try:
            for lp_type in (3, 4, 11):
                names = self._etabs.load_patterns.get_special_load_pattern_names(lp_type)
                self._all_live_patterns.extend(names)
                if lp_type == 4:
                    self._reducible_patterns.update(names)
                elif lp_type == 11:
                    self._roof_live_patterns.update(names)
        except Exception:
            pass

    def _populate_floor_areas(self):
        if not self.project:
            return
        for fid in self.project.floors:
            try:
                ret = self._etabs.SapModel.AreaObj.GetNameListOnStory(fid)
                names = list(ret[1]) if ret[1] else []
            except Exception:
                names = []
            floor = self.project.floors[fid]
            for n in names:
                if n not in floor.areas:
                    floor.add_area(Area(area_id=n))
                # Fetch geometry if missing
                area = floor.areas[n]
                if not area.geometry:
                    area.geometry = self._fetch_area_geometry(n)
        # Fetch frame context for all stories
        self._fetch_frame_context()

    # ----------------------------------------------------------------
    #  Geometry helpers
    # ----------------------------------------------------------------
    def _fetch_area_geometry(self, area_name: str) -> list[Point]:
        """Get polygon vertices for an area object via ETABS COM."""
        try:
            result = self._etabs.SapModel.AreaObj.GetPoints(area_name)
            pt_names = result[1]
            pts: list[Point] = []
            for pt in pt_names:
                coord = self._etabs.SapModel.PointObj.GetCoordCartesian(pt)
                pts.append(Point(x=coord[0], y=-coord[1]))
            return pts
        except Exception as exc:
            log.debug("Could not get area vertices for %s: %s", area_name, exc)
            return []

    def _fetch_frame_context(self):
        """Fetch beam/column coordinates per story for context lines."""
        self._frame_data.clear()
        try:
            story_frames = self._etabs.frame_obj.get_beams_columns_on_stories()
        except Exception:
            return
        for story, parts in story_frames.items():
            items: list[tuple] = []
            beams = parts[0] if len(parts) > 0 else []
            columns = parts[1] if len(parts) > 1 else []
            for name in beams:
                try:
                    x1, y1, x2, y2 = self._etabs.frame_obj.get_xy_of_frame_points(name)
                    items.append(("beam", x1, -y1, x2, -y2))
                except Exception:
                    continue
            for name in columns:
                try:
                    x1, y1, x2, y2 = self._etabs.frame_obj.get_xy_of_frame_points(name)
                    items.append(("column", x1, -y1, x2, -y2))
                except Exception:
                    continue
            self._frame_data[story] = items

    def _create_lp_combo(self, fid: str, aid: str | None = None,
                         load_val: float | None = None) -> QComboBox:
        combo = QComboBox()
        code = None
        if self.project:
            floor = self.project.floors.get(fid)
            if floor:
                if aid:
                    area = floor.areas.get(aid)
                    code = area.use_type if area else None
                else:
                    code = floor.default_use
        self._fill_combo(combo, load_val, code)
        if aid is None:
            combo.currentTextChanged.connect(
                lambda t, f=fid: self._on_floor_pattern_changed(f, t))
        return combo

    def _fill_combo(self, combo: QComboBox, load_val: float | None = None,
                    code: str | None = None):
        prev = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        is_nr = self._code_non_reducible.get(code, False) if code else False
        for p in self._all_live_patterns:
            if p in self._reducible_patterns and (
                is_nr or (load_val is not None and load_val >= _REDUCIBLE_THRESHOLD)
            ):
                continue
            combo.addItem(p)
        idx = combo.findText(prev)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _on_floor_pattern_changed(self, fid: str, text: str):
        floor = self.project.floors.get(fid) if self.project else None
        if not floor:
            return
        for aid in floor.areas:
            c = self._area_combos.get((fid, aid))
            if c:
                c.blockSignals(True)
                idx = c.findText(text)
                if idx >= 0:
                    c.setCurrentIndex(idx)
                c.blockSignals(False)

    def _get_load_type_label(self, code: str) -> str:
        """Return the load pattern type label for a category code."""
        if not code:
            return ""
        root = _get_root_code(code)
        load_val = self._code_to_load.get(code)
        is_nr = self._code_non_reducible.get(code, False)
        if root == "1":
            return "ROOF Live"
        if root == "4" and not is_nr and load_val is not None and load_val < _REDUCIBLE_THRESHOLD:
            return "Reducible Live"
        return "Live"

    def _auto_set_load_pattern(self, code: str, combo: QComboBox):
        """Set combo to an appropriate load-pattern type based on category.

        Root "1" (بام / roof)       → ROOF Live  (type 11)
        Root "4" (مسکونی / residential) → Reducible Live (type 4)
          — unless non-reducible flag set or load ≥ threshold
        Everything else              → Live (type 3)
        """
        root = _get_root_code(code)
        target: str | None = None
        is_nr = self._code_non_reducible.get(code, False)
        if root == "1" and self._roof_live_patterns:
            target = next(iter(self._roof_live_patterns))
        elif root == "4" and self._reducible_patterns and not is_nr:
            load_val = self._code_to_load.get(code)
            if load_val is not None and load_val < _REDUCIBLE_THRESHOLD:
                target = next(iter(self._reducible_patterns))
        if target is None:
            # default: first Live (type 3) pattern
            for p in self._all_live_patterns:
                if p not in self._reducible_patterns and p not in self._roof_live_patterns:
                    target = p
                    break
        if target:
            idx = combo.findText(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    # ================================================================
    #  Save / Restore (per-model)
    # ================================================================
    def _model_save_path(self) -> Path | None:
        try:
            p = self._etabs.get_filepath()
            stem = self._etabs.get_file_name_without_suffix()
            return Path(p) / f"{stem}_liveloads.json"
        except Exception:
            return None

    def _save_model_data(self):
        path = self._model_save_path()
        if path is None or not self.project:
            return
        data: dict = {"project_default_use": self.project.default_use, "floors": {}}
        for fid, floor in self.project.floors.items():
            fc = self._floor_combos.get(fid)
            fd: dict = {
                "default_use": floor.default_use,
                "load_pattern": fc.currentText() if fc else "",
                "areas": {},
            }
            for aid, area in floor.areas.items():
                ac = self._area_combos.get((fid, aid))
                fd["areas"][aid] = {
                    "use_type": area.use_type,
                    "manual_override": area.manual_override,
                    "load_pattern": ac.currentText() if ac else "",
                }
            data["floors"][fid] = fd
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _restore_model_data(self):
        path = self._model_save_path()
        if path is None or not self.project or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if data.get("project_default_use"):
            self.project.default_use = data["project_default_use"]
        for fid, fd in data.get("floors", {}).items():
            floor = self.project.floors.get(fid)
            if not floor:
                continue
            if fd.get("default_use"):
                floor.default_use = fd["default_use"]
            # area data
            for aid, ad in fd.get("areas", {}).items():
                area = floor.areas.get(aid)
                if not area:
                    continue
                if ad.get("use_type"):
                    area.use_type = ad["use_type"]
                if ad.get("manual_override") is not None:
                    area.set_manual_load(ad["manual_override"])
        # Load-pattern combo selections are restored after _populate_tree
        self._saved_lp_data = data

    def _restore_combo_selections(self):
        """Called after _populate_tree to set combo values from saved data."""
        data = getattr(self, "_saved_lp_data", None)
        if not data:
            return
        for fid, fd in data.get("floors", {}).items():
            lp = fd.get("load_pattern", "")
            fc = self._floor_combos.get(fid)
            if fc and lp:
                idx = fc.findText(lp)
                if idx >= 0:
                    fc.blockSignals(True)
                    fc.setCurrentIndex(idx)
                    fc.blockSignals(False)
            for aid, ad in fd.get("areas", {}).items():
                alp = ad.get("load_pattern", "")
                ac = self._area_combos.get((fid, aid))
                if ac and alp:
                    idx = ac.findText(alp)
                    if idx >= 0:
                        ac.blockSignals(True)
                        ac.setCurrentIndex(idx)
                        ac.blockSignals(False)
        self._saved_lp_data = None

    # ================================================================
    #  Favorites (global, %APPDATA%)
    # ================================================================
    def _load_favorites(self) -> dict[str, int]:
        try:
            return json.loads(_FAVORITES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_favorites(self, fav: dict[str, int]):
        try:
            _GLOBAL_PREFS_DIR.mkdir(parents=True, exist_ok=True)
            _FAVORITES_FILE.write_text(
                json.dumps(fav, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _bump_favorite(self, code: str):
        fav = self._load_favorites()
        fav[code] = fav.get(code, 0) + 1
        self._save_favorites(fav)
        self._load_favorites_ui()

    def _load_favorites_ui(self):
        fav = self._load_favorites()
        top = sorted(fav.items(), key=lambda x: -x[1])[:_MAX_FAVORITES]
        for i, btn in enumerate(self._fav_buttons):
            if i < len(top):
                code, _count = top[i]
                name = self._code_to_name.get(code, code)
                load = self._code_to_load.get(code)
                label = f"{name}"
                if load is not None:
                    label += f" ({load:.0f} kgf/m²)"
                btn.setText(label)
                btn.setToolTip(f"Code {code} — click to apply")
                btn.setEnabled(True)
                btn.setProperty("fav_code", code)
            else:
                btn.setText("-")
                btn.setEnabled(False)
                btn.setProperty("fav_code", "")

    def _on_fav_clicked(self):
        btn = self.sender()
        if not btn:
            return
        code = btn.property("fav_code")
        if not code or not self.project:
            return
        load_val = self._code_to_load.get(code)
        if load_val is None:
            return
        self._apply_catalog_code(code, load_val, self._code_to_name.get(code, code))

    # ================================================================
    #  CSV catalog
    # ================================================================
    def _load_persian_load_tree(self):
        self.load_tree.clear()
        self._code_to_load.clear()
        self._code_to_name.clear()
        self._code_non_reducible.clear()
        if not _CSV_PATH.exists():
            return

        roots: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)

        with _CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("ردیف") or "").strip()
                name = (row.get("نوع کاربری") or "").strip()
                dist = (row.get("بار گسترده کیلونیوتن بر مترمربع") or "").strip()
                if not code:
                    continue
                nr = (row.get("غیرقابل کاهش") or "").strip()
                lv = _parse_load_value(dist)
                if lv is not None:
                    self._code_to_load[code] = lv * 100  # kN/m² → kgf/m² (g=10)
                    dist_display = f"{lv * 100:.0f}"
                else:
                    dist_display = dist
                if nr == "1":
                    self._code_non_reducible[code] = True
                if name:
                    self._code_to_name[code] = name

                item = QTreeWidgetItem([code, name, dist_display])
                if "-" not in code:
                    item.setFont(1, bold)
                    self.load_tree.addTopLevelItem(item)
                    roots[code] = item
                else:
                    pc = code.rsplit("-", 1)[-1]
                    parent = roots.get(pc)
                    if parent:
                        parent.addChild(item)
                    else:
                        self.load_tree.addTopLevelItem(item)

        # collapsed by default — user expands as needed
        # (top-level categories are visible)

    # ================================================================
    #  Catalog / favorite → apply
    # ================================================================
    def _on_catalog_applied(self, item: QTreeWidgetItem, _col: int):
        if not self.project:
            QMessageBox.warning(self, "Warning", "Load a project from ETABS first.")
            return
        if item.childCount() > 0:
            return
        load_text = item.text(2).strip()
        load_val = _parse_load_value(load_text)
        name = item.text(1).strip()
        code = item.text(0).strip()
        if load_val is None:
            QMessageBox.information(
                self, "Non-numeric",
                f"'{load_text}' is not numeric. Enter value manually.")
            return
        payloads = self._selected_payloads()
        if not payloads:
            QMessageBox.warning(self, "Warning", "Select floors/areas first.")
            return
        self._apply_catalog_code(code, load_val, name)

    def _apply_catalog_code(self, code: str, load_val: float, use_name: str):
        """Apply *code* / *load_val* to every selected project-tree item."""
        payloads = self._selected_payloads()
        if not payloads or not self.project:
            return

        self._push_undo()
        afl = 0
        aar = 0
        for d in payloads:
            kind = d[0]
            if kind == "floor":
                floor = self.project.floors.get(d[1])
                if floor:
                    floor.default_use = code
                    afl += 1
                    for area in floor.areas.values():
                        area.set_manual_load(load_val)
                        area.use_type = code
                    aar += len(floor.areas)
                    # Auto-set load-pattern combo
                    fc = self._floor_combos.get(d[1])
                    if fc:
                        self._auto_set_load_pattern(code, fc)
            elif kind == "area":
                area = self.project.floors[d[1]].areas.get(d[2])
                if area:
                    area.set_manual_load(load_val)
                    area.use_type = code
                    aar += 1
                    ac = self._area_combos.get((d[1], d[2]))
                    if ac:
                        self._auto_set_load_pattern(code, ac)
            elif kind == "project":
                self.project.default_use = code
                for fid, floor in self.project.floors.items():
                    floor.default_use = code
                    afl += 1
                    for area in floor.areas.values():
                        area.set_manual_load(load_val)
                        area.use_type = code
                        aar += 1
                    fc = self._floor_combos.get(fid)
                    if fc:
                        self._auto_set_load_pattern(code, fc)

        self._bump_favorite(code)
        self._update_tree_loads()
        self._on_selection_changed()

        parts = []
        if afl:
            parts.append(f"{afl} floor(s)")
        if aar:
            parts.append(f"{aar} area(s)")
        self.lbl_notes.setText(
            f"'{use_name}' ({load_val:.0f} kgf/m²) applied to {' and '.join(parts) or 'item(s)'}."
        )

    # ================================================================
    #  Plan drag-and-drop handlers
    # ================================================================
    def _on_plan_area_dropped(self, area_id: str, mime_text: str):
        """Catalog item dropped onto a specific area polygon."""
        parts = mime_text.split("|", 2)
        if len(parts) < 3:
            return
        code, load_str, name = parts
        load_val = _parse_load_value(load_str)
        if load_val is None or not self.project:
            return
        fid = self._current_floor_id()
        if not fid:
            return
        area = self.project.floors[fid].areas.get(area_id)
        if not area:
            return
        self._push_undo()
        area.set_manual_load(load_val)
        area.use_type = code
        ac = self._area_combos.get((fid, area_id))
        if ac:
            self._auto_set_load_pattern(code, ac)
        self._bump_favorite(code)
        self._update_tree_loads()
        self._render_floor_plan(fid, highlight_area_id=area_id)
        self.lbl_notes.setText(f"'{name}' ({load_val:.0f} kgf/m²) → area {area_id}")

    def _on_plan_floor_dropped(self, mime_text: str):
        """Catalog item dropped outside any area — apply to whole floor."""
        parts = mime_text.split("|", 2)
        if len(parts) < 3:
            return
        code, load_str, name = parts
        load_val = _parse_load_value(load_str)
        if load_val is None or not self.project:
            return
        fid = self._current_floor_id()
        if not fid:
            return
        ans = QMessageBox.question(
            self, "Apply to Floor",
            f"Apply '{name}' ({load_val:.0f} kgf/m²) to ALL areas on {fid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._push_undo()
        floor = self.project.floors[fid]
        floor.default_use = code
        for area in floor.areas.values():
            area.set_manual_load(load_val)
            area.use_type = code
        fc = self._floor_combos.get(fid)
        if fc:
            self._auto_set_load_pattern(code, fc)
        self._bump_favorite(code)
        self._update_tree_loads()
        self._render_floor_plan(fid)
        self.lbl_notes.setText(f"'{name}' ({load_val:.0f} kgf/m²) → floor {fid}")

    def _on_plan_area_clicked(self, area_id: str):
        """Click on area polygon → select matching item in project tree."""
        fid = self._current_floor_id()
        if not fid:
            return
        root = self.tree.invisibleRootItem()
        proj = root.child(0)
        if not proj:
            return
        for i in range(proj.childCount()):
            fi = proj.child(i)
            d = fi.data(0, Qt.ItemDataRole.UserRole)
            if d and d[1] == fid:
                for j in range(fi.childCount()):
                    ai = fi.child(j)
                    ad = ai.data(0, Qt.ItemDataRole.UserRole)
                    if ad and ad[2] == area_id:
                        self.tree.clearSelection()
                        ai.setSelected(True)
                        self.tree.scrollToItem(ai)
                        return

    # ================================================================
    #  Project tree
    # ================================================================
    def _populate_tree(self):
        self.tree.clear()
        self._floor_combos.clear()
        self._area_combos.clear()
        if not self.project:
            return

        puc = self.project.default_use or ""
        proj_type = self._code_to_name.get(puc, "")
        proj_item = QTreeWidgetItem(
            self.tree,
            [self.project.project_name or "Project", proj_type, "", ""],
        )
        proj_item.setData(0, Qt.ItemDataRole.UserRole, ("project", self.project.project_id))

        for fid, floor in self.project.floors.items():
            fuc = floor.default_use or ""
            ftype = self._code_to_name.get(fuc, "")
            fl_item = QTreeWidgetItem(proj_item, [floor.floor_name or fid, ftype, "", ""])
            fl_item.setData(0, Qt.ItemDataRole.UserRole, ("floor", fid))

            floor_load = self._code_to_load.get(floor.default_use or "")
            fc = self._create_lp_combo(fid, load_val=floor_load)
            self.tree.setItemWidget(fl_item, 3, fc)
            self._floor_combos[fid] = fc

            for aid in floor.areas:
                area_obj = floor.areas[aid]
                auc = area_obj.use_type or ""
                atype = self._code_to_name.get(auc, "")
                a_item = QTreeWidgetItem(fl_item, [aid, atype, "", ""])
                a_item.setData(0, Qt.ItemDataRole.UserRole, ("area", fid, aid))
                al = self._resolve_area_load(fid, aid)
                ac = self._create_lp_combo(fid, aid, load_val=al)
                self.tree.setItemWidget(a_item, 3, ac)
                self._area_combos[(fid, aid)] = ac

        # Expand only top-level (project) — floors & areas collapsed
        proj_item.setExpanded(True)
        self._update_tree_loads()
        self._restore_combo_selections()

    def _selected_payloads(self) -> list[tuple]:
        return [d for it in self.tree.selectedItems()
                if (d := it.data(0, Qt.ItemDataRole.UserRole)) is not None]

    # ================================================================
    #  Floor plan rendering
    # ================================================================
    def _current_floor_id(self) -> str | None:
        if not self._floor_ids:
            return None
        return self._floor_ids[self._current_floor_idx % len(self._floor_ids)]

    def _navigate_floor(self, delta: int):
        if not self._floor_ids:
            return
        self._current_floor_idx = (self._current_floor_idx + delta) % len(self._floor_ids)
        fid = self._floor_ids[self._current_floor_idx]
        self._render_floor_plan(fid)

    def _render_floor_plan(self, fid: str, highlight_area_id: str | None = None):
        self.plan_scene.clear()
        poly_map: dict[str, QPolygonF] = {}
        self.lbl_floor_name.setText(f"Floor Plan — {fid}")

        # Update nav index to match
        if fid in self._floor_ids:
            self._current_floor_idx = self._floor_ids.index(fid)

        if not self.project:
            return
        floor = self.project.floors.get(fid)
        if not floor:
            return

        # ── 1. Draw context beams / columns (grey, behind areas) ───
        beam_pen = QPen(QColor("#c0c0c0"))
        beam_pen.setWidthF(0.08)
        col_brush = QBrush(QColor("#b0b0b0"))
        col_pen = QPen(QColor("#999999"))
        col_pen.setWidthF(0.04)
        col_size = 0.15  # half-side of column square in model units

        for ftype, x1, y1, x2, y2 in self._frame_data.get(fid, []):
            if ftype == "beam":
                self.plan_scene.addLine(x1, y1, x2, y2, beam_pen)
            else:
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                self.plan_scene.addRect(
                    cx - col_size, cy - col_size,
                    col_size * 2, col_size * 2,
                    col_pen, col_brush,
                )

        # ── 2. Collect load values for gradient range ──────────────
        load_vals: list[float] = []
        for area in floor.areas.values():
            v = self._resolve_area_load(fid, area.area_id)
            if v is not None:
                load_vals.append(v)
        lo = min(load_vals) if load_vals else 0.0
        hi = max(load_vals) if load_vals else 1000.0
        if hi == lo:
            hi = lo + 1.0

        # ── 3. Draw area polygons with gradient fills ──────────────
        has_geom = False
        use_name_groups: dict[str, tuple[QColor, str]] = {}  # for legend

        for area in floor.areas.values():
            if len(area.geometry) < 3:
                continue
            has_geom = True
            poly = QPolygonF([QPointF(p.x, p.y) for p in area.geometry])
            poly_map[area.area_id] = poly
            av = self._resolve_area_load(fid, area.area_id)
            hl = highlight_area_id == area.area_id

            fill_color = _load_to_color(av, lo, hi) if not hl else QColor("#ffd166")
            pen_color = QColor("#bc6c25") if hl else QColor("#555555")
            pen = QPen(pen_color)
            pen.setWidthF(0.12 if hl else 0.04)
            self.plan_scene.addPolygon(poly, pen, QBrush(fill_color))

            # Track group colour for legend
            uc = area.use_type or ""
            uname = self._code_to_name.get(uc, uc) or "Unassigned"
            if uname not in use_name_groups and av is not None:
                lt = self._get_load_type_label(uc)
                use_name_groups[uname] = (fill_color, lt)

        self.plan_view.set_area_polygons(poly_map)

        if not has_geom:
            self.plan_scene.addText("No geometry available for this floor.")
            self.plan_view.fitInView(
                self.plan_scene.itemsBoundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            return

        # ── Compute text scale from geometry bounds ────────────────
        # QGraphicsTextItem font size is in points (~10 scene-units
        # for a 7pt font).  We scale texts so they are proportional
        # to the actual model extent (metres).
        geom_rect = self.plan_scene.itemsBoundingRect()
        ref_dim = min(geom_rect.width(), geom_rect.height()) or 1.0
        # Target label height ≈ 3 % of the shorter plan dimension.
        # Unscaled 7pt text is ~10 scene-units tall.
        text_scale = ref_dim * 0.03 / 10.0
        label_font = QFont("Segoe UI", 7)

        # ── 3b. Add centred area labels (scaled proportionally) ────
        for area in floor.areas.values():
            if len(area.geometry) < 3:
                continue
            av = self._resolve_area_load(fid, area.area_id)
            if av is None:
                continue
            cx = sum(p.x for p in area.geometry) / len(area.geometry)
            cy = sum(p.y for p in area.geometry) / len(area.geometry)
            lbl_text = f"{av:.0f}"
            txt = self.plan_scene.addText(lbl_text, label_font)
            txt.setDefaultTextColor(QColor("#1a1a1a"))
            txt.setScale(text_scale)
            br = txt.boundingRect()
            txt.setPos(
                cx - br.width() * text_scale / 2,
                cy - br.height() * text_scale / 2,
            )

        # ── 4. Draw gradient legend ────────────────────────────────
        self._draw_plan_legend(lo, hi, use_name_groups, geom_rect, text_scale)

        self.plan_view.fitInView(
            self.plan_scene.itemsBoundingRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _draw_plan_legend(
        self,
        lo: float,
        hi: float,
        use_groups: dict[str, tuple[QColor, str]],
        geom_rect,
        text_scale: float,
    ):
        """Draw a colour-bar legend and category list in the scene.

        All sizes are derived from *geom_rect* (the model-unit bounding
        box of geometry items) so the legend stays proportional to the
        plan regardless of building size.
        """
        plan_w = geom_rect.width() or 1.0
        plan_h = geom_rect.height() or 1.0

        lx = geom_rect.right() + plan_w * 0.04
        ly = geom_rect.top()

        bar_w = plan_w * 0.06
        bar_h = plan_h * 0.7

        # Gradient rectangle (n_steps colour blocks)
        n_steps = 20
        step_h = bar_h / n_steps
        no_pen = QPen(Qt.PenStyle.NoPen)
        for i in range(n_steps):
            t_val = hi - (hi - lo) * i / (n_steps - 1) if n_steps > 1 else lo
            color = _load_to_color(t_val, lo, hi)
            self.plan_scene.addRect(
                lx, ly + i * step_h, bar_w, step_h + 0.01,
                no_pen, QBrush(color),
            )

        # Border
        border_pen = QPen(QColor("#555555"))
        border_pen.setWidthF(plan_w * 0.002)
        self.plan_scene.addRect(lx, ly, bar_w, bar_h, border_pen)

        # Scale labels (same text_scale as area labels)
        lbl_font = QFont("Segoe UI", 7)
        gap = bar_w * 0.2  # small gap after bar

        legend_scale = text_scale * 2.0

        hi_txt = self.plan_scene.addText(f"{hi:.0f}", lbl_font)
        hi_txt.setDefaultTextColor(QColor("#333333"))
        hi_txt.setScale(legend_scale)
        hi_txt.setPos(lx + bar_w + gap, ly)

        lo_txt = self.plan_scene.addText(f"{lo:.0f}", lbl_font)
        lo_txt.setDefaultTextColor(QColor("#333333"))
        lo_txt.setScale(legend_scale)
        lo_br = lo_txt.boundingRect()
        lo_txt.setPos(
            lx + bar_w + gap,
            ly + bar_h - lo_br.height() * legend_scale,
        )

        unit_txt = self.plan_scene.addText("kgf/m²", lbl_font)
        unit_txt.setDefaultTextColor(QColor("#666666"))
        unit_txt.setScale(legend_scale)
        unit_br = unit_txt.boundingRect()
        unit_txt.setPos(lx, ly - unit_br.height() * legend_scale * 1.1)

        # ── Category legend below the gradient bar ─────────────────
        if not use_groups:
            return
        swatch_size = bar_w * 0.8
        cat_y = ly + bar_h + swatch_size * 1.5

        for name, (color, load_type) in use_groups.items():
            sw_pen = QPen(QColor("#555555"))
            sw_pen.setWidthF(plan_w * 0.001)
            self.plan_scene.addRect(
                lx, cat_y, swatch_size, swatch_size,
                sw_pen, QBrush(color),
            )
            label = f"{name} [{load_type}]" if load_type else name
            ctxt = self.plan_scene.addText(label, lbl_font)
            ctxt.setDefaultTextColor(QColor("#333333"))
            ctxt.setScale(legend_scale)
            ctxt.setPos(lx + swatch_size * 1.3, cat_y)
            cat_y += swatch_size * 1.8

    # ================================================================
    #  Selection handling
    # ================================================================
    def _on_selection_changed(self):
        payloads = self._selected_payloads()
        if not payloads:
            self._enable_properties(False)
            return

        self._enable_properties(True)
        self.spin_manual.blockSignals(True)
        self.chk_balcony.blockSignals(True)

        data = payloads[0]

        if len(payloads) > 1:
            fids = sorted({d[1] for d in payloads if d[0] == "floor"})
            self.lbl_id.setText(f"{len(payloads)} items selected")
            self.lbl_use_type.setText("-")
            if fids:
                self._render_floor_plan(fids[0])
            self.spin_manual.setEnabled(False)
            self.chk_balcony.setEnabled(False)
            self.lbl_calc_load.setText("-")
            self.lbl_source.setText("-")
            self.lbl_notes.setText("Double-click or drag a catalog entry to apply.")
            self.spin_manual.blockSignals(False)
            self.chk_balcony.blockSignals(False)
            return

        kind = data[0]
        if kind == "project":
            self.lbl_id.setText(self.project.project_id)
            uc = self.project.default_use or ""
            self.lbl_use_type.setText(self._code_to_name.get(uc, uc) or "-")
            self.spin_manual.setEnabled(False)
            self.chk_balcony.setEnabled(False)
            lv = self._code_to_load.get(uc)
            self.lbl_calc_load.setText(f"{lv:.0f} kgf/m²" if lv is not None else "-")
            self.lbl_source.setText("-")
            self.lbl_notes.setText("-")

        elif kind == "floor":
            fid = data[1]
            floor = self.project.floors[fid]
            self.lbl_id.setText(fid)
            uc = floor.default_use or ""
            self.lbl_use_type.setText(self._code_to_name.get(uc, uc) or "-")
            self.spin_manual.setEnabled(False)
            self.chk_balcony.setEnabled(False)
            lv = self._code_to_load.get(uc)
            self.lbl_calc_load.setText(f"{lv:.0f} kgf/m²" if lv is not None else "-")
            self.lbl_source.setText("Floor Default" if uc else "-")
            self.lbl_notes.setText("-")
            self._render_floor_plan(fid)

        elif kind == "area":
            fid, aid = data[1], data[2]
            area = self.project.floors[fid].areas[aid]
            self.lbl_id.setText(aid)
            uc = area.use_type or ""
            self.lbl_use_type.setText(self._code_to_name.get(uc, uc) or "-")
            self.spin_manual.setEnabled(True)
            self.spin_manual.setValue(area.manual_override if area.manual_override is not None else 0)
            self.chk_balcony.setEnabled(True)
            self.chk_balcony.setChecked(area.is_balcony)
            self._update_area_load_display(fid, aid)
            self._render_floor_plan(fid, highlight_area_id=aid)

        self.spin_manual.blockSignals(False)
        self.chk_balcony.blockSignals(False)

    # ================================================================
    #  Property edits
    # ================================================================
    def _on_property_changed(self):
        payloads = self._selected_payloads()
        if not payloads or not self.project:
            return
        if len(payloads) != 1 or payloads[0][0] != "area":
            return
        fid, aid = payloads[0][1], payloads[0][2]
        area = self.project.floors[fid].areas[aid]
        self._push_undo()
        if self.spin_manual.value() > 0:
            area.set_manual_load(self.spin_manual.value())
        else:
            area.clear_manual_load()
        area.is_balcony = self.chk_balcony.isChecked()
        area._cached_load = None
        self._update_area_load_display(fid, aid)
        self._render_floor_plan(fid, highlight_area_id=aid)
        self._update_tree_loads()

    # ================================================================
    #  Tree / display helpers
    # ================================================================
    def _update_area_load_display(self, fid: str, aid: str):
        val = self._resolve_area_load(fid, aid)
        self.lbl_calc_load.setText(f"{val:.0f} kgf/m²" if val is not None else "-")
        area = self.project.floors[fid].areas[aid]
        self.lbl_source.setText(area.load_source.value)
        self.lbl_notes.setText("")

    def _update_tree_loads(self):
        root = self.tree.invisibleRootItem()
        proj = root.child(0)
        if not proj:
            return
        pc = self.project.default_use or ""
        pn = self._code_to_name.get(pc, "")
        proj.setText(1, pn)
        pl = self._code_to_load.get(pc)
        proj.setText(2, f"{pl:.0f}" if pl is not None else "")

        for i in range(proj.childCount()):
            fi = proj.child(i)
            fid = fi.data(0, Qt.ItemDataRole.UserRole)[1]
            floor = self.project.floors.get(fid)
            fc_code = (floor.default_use or "") if floor else ""
            fn = self._code_to_name.get(fc_code, "")
            fi.setText(1, fn)
            fl = self._code_to_load.get(fc_code)
            fi.setText(2, f"{fl:.0f}" if fl is not None else "")

            fc = self._floor_combos.get(fid)
            if fc:
                self._fill_combo(fc, fl, fc_code)

            for j in range(fi.childCount()):
                ai = fi.child(j)
                aid = ai.data(0, Qt.ItemDataRole.UserRole)[2]
                area = floor.areas.get(aid) if floor else None
                auc = (area.use_type or "") if area else ""
                an = self._code_to_name.get(auc, "")
                ai.setText(1, an)
                al = self._resolve_area_load(fid, aid)
                ai.setText(2, f"{al:.0f}" if al is not None else "")
                ac = self._area_combos.get((fid, aid))
                if ac:
                    self._fill_combo(ac, al, auc)
