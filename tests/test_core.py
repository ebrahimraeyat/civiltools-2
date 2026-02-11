"""
Basic tests for the civilTools core module.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from civiltools.core import (
    BuildingModel, Story, GridAxis, StructuralElement,
    SectionProfile, Material, LoadCase,
)
from civiltools.core.samples import create_sample_building


class TestStory:
    def test_top(self):
        s = Story("Floor1", elevation=3.5, height=3.2)
        assert s.top == pytest.approx(6.7)


class TestBuildingModel:
    def test_empty_model(self):
        m = BuildingModel()
        assert m.total_height == 0.0
        assert m.stories_by_name() == {}

    def test_uid_generation(self):
        m = BuildingModel()
        assert m.next_uid("C") == "C00001"
        assert m.next_uid("B") == "B00002"

    def test_serialization_roundtrip(self):
        model = create_sample_building()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = Path(f.name)

        model.save(path)
        loaded = BuildingModel.load(path)

        assert loaded.project_name == model.project_name
        assert len(loaded.stories) == len(model.stories)
        assert len(loaded.elements) == len(model.elements)
        assert len(loaded.axes) == len(model.axes)

        path.unlink()

    def test_elements_for_story(self):
        model = create_sample_building()
        ground = model.elements_for_story("Ground Floor")
        assert len(ground) > 0
        assert all(e.story == "Ground Floor" for e in ground)

    def test_elements_by_type(self):
        model = create_sample_building()
        columns = model.elements_by_type("column")
        assert len(columns) > 0
        assert all(e.element_type == "column" for e in columns)


class TestSampleBuilding:
    def test_creation(self):
        model = create_sample_building()
        assert len(model.stories) == 3
        assert len(model.axes) == 7  # 4 X-axes + 3 Y-axes
        assert model.total_height == pytest.approx(9.9)

    def test_has_all_element_types(self):
        model = create_sample_building()
        types = {e.element_type for e in model.elements}
        assert "column" in types
        assert "beam" in types
        assert "floor" in types
        assert "wall" in types

    def test_seismic_params(self):
        model = create_sample_building()
        assert model.seismic_params["code"] == "Standard 2800 4th Ed."
        assert model.seismic_params["zone"] == 3
