"""
Live Load Management Data Models

This module defines the core data structures for the live load management system
using Pydantic for robust validation and serialization.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field, ConfigDict

try:
    from shapely.geometry import Polygon
except ImportError:
    Polygon = None


class LoadSource(str, Enum):
    """Source of the live load value."""
    DIRECT = "direct"
    INHERITED_FLOOR = "inherited_floor"
    INHERITED_PROJECT = "inherited_project"
    CALCULATED = "calculated"


class Point(BaseModel):
    """2D Point for defining geometry."""
    x: float
    y: float


class LoadInfo(BaseModel):
    """Information about a calculated live load."""
    value: float
    source: LoadSource
    use_type: Optional[str] = None
    notes: str = ""


class Area(BaseModel):
    """A specific area or room within a floor."""
    model_config = ConfigDict(validate_assignment=True)

    area_id: str
    geometry: List[Point] = Field(default_factory=list)
    use_type: Optional[str] = None
    manual_override: Optional[float] = None
    is_balcony: bool = False
    
    # Cached load value to prevent recalculation on every GUI render
    _cached_load: Optional[LoadInfo] = None

    @property
    def load_source(self) -> LoadSource:
        """Determine the source of the load for this area."""
        if self.manual_override is not None:
            return LoadSource.DIRECT
        elif self.use_type is not None:
            return LoadSource.DIRECT
        else:
            return LoadSource.INHERITED_FLOOR

    def set_use_type(self, use_type: str, manual: bool = True) -> None:
        """Set the use type for this area."""
        self.use_type = use_type if manual else None
        self._cached_load = None  # Invalidate cache

    def set_manual_load(self, load: float) -> None:
        """Set a manual load override."""
        self.manual_override = load
        self._cached_load = None  # Invalidate cache

    def clear_manual_load(self) -> None:
        """Clear the manual load override."""
        self.manual_override = None
        self._cached_load = None  # Invalidate cache


class Floor(BaseModel):
    """A building story containing multiple areas."""
    model_config = ConfigDict(validate_assignment=True)

    floor_id: str
    floor_name: str = ""
    elevation: float = 0.0
    height: float = 0.0
    default_use: Optional[str] = None
    areas: Dict[str, Area] = Field(default_factory=dict)

    def add_area(self, area: Area) -> None:
        """Add an area to this floor."""
        self.areas[area.area_id] = area

    def apply_default_use(self, use_type: str) -> None:
        """Apply a default use type to the entire floor."""
        self.default_use = use_type
        # Invalidate caches for areas that inherit from floor
        for area in self.areas.values():
            if area.use_type is None and area.manual_override is None:
                area._cached_load = None

    def validate_floor(self) -> List[str]:
        """Validate the floor for structural consistency."""
        errors = []
        if not self.areas:
            errors.append(f"Floor '{self.floor_id}' has no areas defined.")
            
        for area_id, area in self.areas.items():
            if area.use_type is None and self.default_use is None and area.manual_override is None:
                errors.append(f"Area '{area_id}' on floor '{self.floor_id}' has no use type and no floor default is set.")
                
            if len(area.geometry) < 3:
                errors.append(f"Area '{area_id}' on floor '{self.floor_id}' has invalid geometry (less than 3 points).")
                
        return errors

    def get_adjacent_areas(self, area_id: str) -> List[Area]:
        """Find areas adjacent to the given area using Shapely."""
        if Polygon is None:
            return []
            
        target_area = self.areas.get(area_id)
        if not target_area or len(target_area.geometry) < 3:
            return []
            
        target_poly = Polygon([(p.x, p.y) for p in target_area.geometry])
        if not target_poly.is_valid:
            target_poly = target_poly.buffer(0)
            
        adjacent = []
        for other_id, other_area in self.areas.items():
            if other_id == area_id or len(other_area.geometry) < 3:
                continue
                
            other_poly = Polygon([(p.x, p.y) for p in other_area.geometry])
            if not other_poly.is_valid:
                other_poly = other_poly.buffer(0)
                
            # Check if they share a boundary (intersection is a line or polygon)
            if target_poly.touches(other_poly) or target_poly.intersects(other_poly):
                # To be strictly adjacent, they should share an edge, so intersection should be 1D
                intersection = target_poly.intersection(other_poly)
                if intersection.geom_type in ('LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'):
                    adjacent.append(other_area)
                    
        return adjacent


class Project(BaseModel):
    """Top-level container for the building project."""
    model_config = ConfigDict(validate_assignment=True)

    project_id: str
    project_name: str = ""
    default_use: Optional[str] = None
    floors: Dict[str, Floor] = Field(default_factory=dict)

    def add_floor(self, floor: Floor) -> None:
        """Add a floor to the project."""
        self.floors[floor.floor_id] = floor

    def apply_default_use(self, use_type: str) -> None:
        """Apply a default use type to the entire project."""
        self.default_use = use_type
        # Invalidate caches for areas that inherit from project
        for floor in self.floors.values():
            if floor.default_use is None:
                for area in floor.areas.values():
                    if area.use_type is None and area.manual_override is None:
                        area._cached_load = None

    def validate_project(self) -> List[str]:
        """Validate the entire project for structural consistency."""
        errors = []
        if not self.floors:
            errors.append(f"Project '{self.project_id}' has no floors defined.")
            
        for floor_id, floor in self.floors.items():
            floor_errors = floor.validate_floor()
            # Filter out errors that are resolved by project default
            for err in floor_errors:
                if "has no use type and no floor default is set" in err and self.default_use is not None:
                    continue
                errors.append(err)
                
        return errors

    def get_area_load(self, floor_id: str, area_id: str, database: Any) -> LoadInfo:
        """
        Calculate the live load for a specific area based on the priority chain:
        1. Manual Override
        2. Area Use Type
        3. Floor Default Use
        4. Project Default Use
        5. Database Global Default
        
        Also handles balcony calculations.
        """
        floor = self.floors.get(floor_id)
        if not floor:
            raise ValueError(f"Floor {floor_id} not found.")
            
        area = floor.areas.get(area_id)
        if not area:
            raise ValueError(f"Area {area_id} not found on floor {floor_id}.")
            
        if area._cached_load is not None:
            return area._cached_load

        # 1. Manual Override
        if area.manual_override is not None:
            info = LoadInfo(
                value=area.manual_override,
                source=LoadSource.DIRECT,
                notes="Manual override"
            )
            area._cached_load = info
            return info

        # Determine base use type and source
        use_type = None
        source = None
        
        # 2. Area Use Type
        if area.use_type is not None:
            use_type = area.use_type
            source = LoadSource.DIRECT
        # 3. Floor Default Use
        elif floor.default_use is not None:
            use_type = floor.default_use
            source = LoadSource.INHERITED_FLOOR
        # 4. Project Default Use
        elif self.default_use is not None:
            use_type = self.default_use
            source = LoadSource.INHERITED_PROJECT

        # Calculate base load
        notes = ""
        if use_type is not None:
            try:
                base_load = database.get_load(use_type)
            except ValueError:
                base_load = database.get_default_load()
                notes = f"Use type '{use_type}' not found, using global default."
        else:
            base_load = database.get_default_load()
            source = LoadSource.INHERITED_PROJECT
            notes = "No use type defined, using global default."

        # Handle Balcony Logic
        if area.is_balcony:
            adjacent_areas = floor.get_adjacent_areas(area_id)
            adjacent_loads = []
            
            # Temporarily disable caching to prevent infinite recursion if balconies are adjacent
            # Actually, we should just get the base load of adjacent areas, ignoring their balcony status
            # Or we can just call get_area_load recursively but we need to be careful.
            # Let's just get the base load of adjacent areas without balcony multiplier.
            for adj in adjacent_areas:
                if adj.is_balcony:
                    continue # Skip other balconies to avoid recursion
                
                # Determine adjacent area's base load
                adj_use = adj.use_type or floor.default_use or self.default_use
                if adj.manual_override is not None:
                    adj_load = adj.manual_override
                elif adj_use is not None:
                    try:
                        adj_load = database.get_load(adj_use)
                    except ValueError:
                        adj_load = database.get_default_load()
                else:
                    adj_load = database.get_default_load()
                    
                adjacent_loads.append(adj_load)
                
            if adjacent_loads:
                max_adj_load = max(adjacent_loads)
                balcony_load = min(1.5 * max_adj_load, 5.0)
                # Balcony load should not be less than its own base load
                final_load = max(balcony_load, base_load)
                notes = f"Balcony calculated from adjacent max ({max_adj_load})"
            else:
                final_load = base_load
                notes = "Balcony with no adjacent areas, using base load"
                
            info = LoadInfo(
                value=final_load,
                source=LoadSource.CALCULATED,
                use_type=use_type,
                notes=notes
            )
        else:
            info = LoadInfo(
                value=base_load,
                source=source,
                use_type=use_type,
                notes=notes
            )

        area._cached_load = info
        return info
