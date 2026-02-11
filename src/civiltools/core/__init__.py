"""
In-memory building model — framework-agnostic data classes.

No FreeCAD, no OCC. Pure data that can be:
- Populated from ETABS API
- Rendered by the OCC viewer
- Serialized to/from JSON
- Used by report generators
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Core data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Story:
    """One building storey."""

    name: str
    elevation: float  # bottom of storey (m)
    height: float  # storey height (m)

    @property
    def top(self) -> float:
        return self.elevation + self.height


@dataclass
class GridAxis:
    """A grid axis line."""

    name: str  # "A", "1", etc.
    direction: str  # 'X' or 'Y'
    start: tuple[float, float, float] = (0.0, 0.0, 0.0)
    end: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class SectionProfile:
    """Cross-section definition."""

    name: str  # e.g. "IPE200", "C50x50"
    shape: str  # 'rectangular', 'circular', 'H', 'channel', …
    properties: dict[str, float] = field(default_factory=dict)
    # e.g. {'b': 0.5, 'h': 0.5} or {'d': 0.40} or {'bf': 0.2, 'd': 0.4, …}


@dataclass
class StructuralElement:
    """A single structural element (beam, column, wall, floor, brace)."""

    uid: str  # unique id
    element_type: str  # 'beam', 'column', 'wall', 'floor', 'brace', 'opening'
    story: str  # story name
    label: str  # human label ("C-A1", "B-AB-1")
    section: str = ""  # profile name reference
    material: str = ""  # material name

    # Geometry — depends on element_type
    start_point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    end_point: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # For beams/columns: section dimensions override
    width: float = 0.0
    depth: float = 0.0

    # For walls
    thickness: float = 0.0
    openings: list[dict[str, float]] | None = None
    # each opening: {'offset': m, 'z_offset': m, 'width': m, 'height': m}

    # For floors
    vertices: list[tuple[float, float, float]] | None = None

    # Generic property bag for extensions
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadCase:
    """Load case / pattern definition."""

    name: str
    load_type: str  # 'dead', 'live', 'seismic', 'wind', 'snow', …
    self_weight_multiplier: float = 0.0


@dataclass
class Material:
    """Material definition."""

    name: str
    material_type: str  # 'concrete', 'steel', 'rebar'
    fc: float = 0.0  # MPa (concrete)
    fy: float = 0.0  # MPa (steel/rebar)
    Es: float = 0.0  # MPa
    weight: float = 0.0  # kN/m³


# ═══════════════════════════════════════════════════════════════════════════
# Building model container
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BuildingModel:
    """Complete in-memory building representation."""

    # Metadata
    project_name: str = ""
    location: str = ""  # city
    designer: str = ""

    # Structure
    stories: list[Story] = field(default_factory=list)
    axes: list[GridAxis] = field(default_factory=list)
    elements: list[StructuralElement] = field(default_factory=list)
    sections: dict[str, SectionProfile] = field(default_factory=dict)
    materials: dict[str, Material] = field(default_factory=dict)
    load_cases: list[LoadCase] = field(default_factory=list)

    # Seismic parameters (filled by building analysis)
    seismic_params: dict[str, Any] = field(default_factory=dict)

    # ── Helpers ────────────────────────────────────────────────────────

    def stories_by_name(self) -> dict[str, Story]:
        return {s.name: s for s in self.stories}

    def elements_for_story(self, story_name: str) -> list[StructuralElement]:
        return [e for e in self.elements if e.story == story_name]

    def elements_by_type(self, etype: str) -> list[StructuralElement]:
        return [e for e in self.elements if e.element_type == etype]

    @property
    def total_height(self) -> float:
        if not self.stories:
            return 0.0
        return max(s.top for s in self.stories)

    # ── UID generation ────────────────────────────────────────────────

    _counter: int = field(default=0, repr=False, compare=False)

    def next_uid(self, prefix: str = "E") -> str:
        self._counter += 1
        return f"{prefix}{self._counter:05d}"

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path | str):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> BuildingModel:
        data = json.loads(Path(path).read_text("utf-8"))

        model = cls()
        model.project_name = data.get("project_name", "")
        model.location = data.get("location", "")
        model.designer = data.get("designer", "")

        model.stories = [Story(**s) for s in data.get("stories", [])]
        model.axes = [GridAxis(**a) for a in data.get("axes", [])]
        model.elements = [StructuralElement(**e) for e in data.get("elements", [])]
        model.sections = {
            k: SectionProfile(**v) for k, v in data.get("sections", {}).items()
        }
        model.materials = {
            k: Material(**v) for k, v in data.get("materials", {}).items()
        }
        model.load_cases = [LoadCase(**lc) for lc in data.get("load_cases", [])]
        model.seismic_params = data.get("seismic_params", {})

        return model
