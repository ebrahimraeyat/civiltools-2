"""
OCC viewer widget — wraps pythonocc qtViewer3d and manages displayed shapes.

Bridges the BuildingModel data classes to OCC display shapes.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget

from OCC.Display.backend import load_backend

load_backend("pyside6")

from OCC.Display.qtDisplay import qtViewer3d  # noqa: E402

from civiltools.core import BuildingModel, StructuralElement, GridAxis
from civiltools.viewer.shapes import (
    make_column,
    make_beam,
    make_floor_slab,
    make_wall,
    make_axis_line,
    COLORS,
    TRANSPARENCY,
)


class OccViewerWidget(qtViewer3d):
    """Enhanced OCC viewer with structural-element display management.

    Tracks displayed AIS shapes per (story, element_type) for quick
    visibility toggling.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # { story_name: { element_type: [(ais_handle, label), …] } }
        self._shapes: dict[str, dict[str, list]] = {}
        self._story_vis: dict[str, bool] = {}
        self._type_vis: dict[str, bool] = {
            "beam": True, "column": True, "wall": True,
            "floor": True, "brace": True,
        }
        self._display = None
        self._initialized = False
        self._wireframe = False
        self._model: BuildingModel | None = None

    # Guard against events before InitDriver — the base qtViewer3d
    # accesses self._display in resize/paint/mouse events, which is None
    # until InitDriver() is called.
    def _guard(self) -> bool:
        return self._initialized and self._display is not None

    def resizeEvent(self, event):
        if self._guard():
            super().resizeEvent(event)

    def paintEvent(self, event):
        if self._guard():
            super().paintEvent(event)

    def mouseMoveEvent(self, event):
        if self._guard():
            super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._guard():
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._guard():
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self._guard():
            super().wheelEvent(event)

    # ── Initialization ────────────────────────────────────────────────

    def init_viewer(self):
        """Call once after the widget is mapped on screen."""
        if self._initialized:
            return
        self._initialized = True
        self.InitDriver()
        self._display = self._display  # already set by InitDriver

        # Background gradient
        try:
            self._display.set_bg_gradient_color(
                [217, 230, 242], [130, 150, 172],
            )
        except Exception:
            pass

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ── Model loading ─────────────────────────────────────────────────

    def load_model(self, model: BuildingModel):
        """Display all elements from a BuildingModel."""
        if not self._initialized:
            self.init_viewer()

        self._model = model
        self._shapes.clear()
        self._story_vis.clear()

        # Prepare story buckets
        for story in model.stories:
            self._story_vis[story.name] = True
            self._shapes[story.name] = {
                "beam": [], "column": [], "wall": [],
                "floor": [], "brace": [],
            }

        # Grid axes
        for ax in model.axes:
            edge = make_axis_line(ax.start, ax.end)
            self._display.DisplayShape(
                edge, color=COLORS["axis"], update=False,
            )

        # Elements
        for elem in model.elements:
            shape = self._build_shape(elem)
            if shape is None:
                continue
            et = elem.element_type
            clr = COLORS.get(et, COLORS["beam"])
            trans = TRANSPARENCY.get(et, 0.0)
            result = self._display.DisplayShape(
                shape, color=clr, transparency=trans, update=False,
            )
            ais = result[0] if isinstance(result, (list, tuple)) else result
            if elem.story in self._shapes:
                bucket = self._shapes[elem.story]
                if et not in bucket:
                    bucket[et] = []
                bucket[et].append((ais, elem.label))

        self._display.FitAll()
        self._display.View_Iso()

    def clear_model(self):
        """Remove all displayed shapes."""
        if self._display:
            self._display.EraseAll()
        self._shapes.clear()
        self._story_vis.clear()
        self._model = None

    # ── Shape factory ─────────────────────────────────────────────────

    @staticmethod
    def _build_shape(elem: StructuralElement):
        """Convert a StructuralElement to a TopoDS_Shape."""
        et = elem.element_type
        sp, ep = elem.start_point, elem.end_point
        props = elem.properties

        if et == "column":
            z_base = sp[2]
            height = ep[2] - sp[2] if ep[2] > sp[2] else props.get("height", 3.0)
            bx = elem.width or props.get("bx", 0.50)
            by = elem.depth or props.get("by", 0.50)
            return make_column(sp[0], sp[1], z_base, height, bx, by)

        if et == "beam":
            z_top = sp[2] if sp[2] == ep[2] else max(sp[2], ep[2])
            w = elem.width or props.get("width", 0.30)
            d = elem.depth or props.get("depth", 0.50)
            return make_beam(sp[0], sp[1], ep[0], ep[1], z_top, w, d)

        if et == "floor":
            # Use vertices if available (for non-rectangular)
            # Otherwise fall back to start/end bounding box
            x1, y1, _ = sp
            x2, y2, _ = ep
            z_top = sp[2]
            thick = elem.thickness or props.get("thickness", 0.25)
            return make_floor_slab(x1, y1, x2, y2, z_top, thick)

        if et == "wall":
            x1, y1, _ = sp
            x2, y2, _ = ep
            z_base = sp[2]
            height = props.get("height", ep[2] - sp[2] if ep[2] != sp[2] else 3.0)
            thick = elem.thickness or props.get("thickness", 0.20)
            return make_wall(x1, y1, x2, y2, z_base, height, thick, elem.openings)

        return None

    # ── Visibility ────────────────────────────────────────────────────

    def _context(self):
        return self._display.Context

    def toggle_element_type(self, etype: str, visible: bool):
        """Show / hide all elements of a given type across all stories."""
        self._type_vis[etype] = visible
        ctx = self._context()
        for sn, story_shapes in self._shapes.items():
            if not self._story_vis.get(sn, True):
                continue
            for ais, _ in story_shapes.get(etype, []):
                if visible:
                    ctx.Display(ais, False)
                else:
                    ctx.Erase(ais, False)
        ctx.UpdateCurrentViewer()

    def toggle_story(self, story_name: str, visible: bool):
        """Show / hide all elements in a story."""
        self._story_vis[story_name] = visible
        ctx = self._context()
        for etype, shapes in self._shapes.get(story_name, {}).items():
            if not self._type_vis.get(etype, True):
                continue
            for ais, _ in shapes:
                if visible:
                    ctx.Display(ais, False)
                else:
                    ctx.Erase(ais, False)
        ctx.UpdateCurrentViewer()

    def isolate_story(self, target: str):
        """Hide every story except *target*."""
        ctx = self._context()
        for sn in self._shapes:
            vis = sn == target
            self._story_vis[sn] = vis
            for etype, shapes in self._shapes[sn].items():
                if not self._type_vis.get(etype, True):
                    continue
                for ais, _ in shapes:
                    if vis:
                        ctx.Display(ais, False)
                    else:
                        ctx.Erase(ais, False)
        ctx.UpdateCurrentViewer()

    def show_all_stories(self):
        """Restore visibility of every story."""
        ctx = self._context()
        for sn in self._shapes:
            self._story_vis[sn] = True
            for etype, shapes in self._shapes[sn].items():
                if not self._type_vis.get(etype, True):
                    continue
                for ais, _ in shapes:
                    ctx.Display(ais, False)
        ctx.UpdateCurrentViewer()

    def story_visibility(self) -> dict[str, bool]:
        return dict(self._story_vis)

    # ── Display modes ─────────────────────────────────────────────────

    def toggle_wireframe(self) -> bool:
        """Toggle wireframe / shaded.  Returns new wireframe state."""
        self._wireframe = not self._wireframe
        mode = 0 if self._wireframe else 1
        ctx = self._context()
        for sn in self._shapes:
            for etype, shapes in self._shapes[sn].items():
                for ais, _ in shapes:
                    ctx.SetDisplayMode(ais, mode, False)
        ctx.UpdateCurrentViewer()
        return self._wireframe

    # ── View presets ──────────────────────────────────────────────────

    def view_fit(self):
        if self._display:
            self._display.FitAll()

    def view_iso(self):
        if self._display:
            self._display.View_Iso()

    def view_front(self):
        if self._display:
            self._display.View_Front()

    def view_top(self):
        if self._display:
            self._display.View_Top()

    def view_right(self):
        if self._display:
            self._display.View_Right()

    def view_left(self):
        if self._display:
            self._display.View_Left()
