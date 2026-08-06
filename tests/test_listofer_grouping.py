"""Unit tests for listofer identical-bar grouping helpers."""

from __future__ import annotations

import pytest

from civiltools.building.extract_stirrups_from_dwg import BeamDimensions, StirrupZone
from civiltools.building.listofer_grouping import (
    DEFAULT_LISTOFER_VIEW_MODE,
    group_longitudinal_rebars,
    group_stirrup_zones,
    iter_listofer_views,
    longitudinal_group_key,
    normalize_listofer_view_mode,
    stirrup_group_key,
)
from civiltools.building.longitudinal_rebar_from_dwg import LongitudinalRebarData


class TestViewMode:
    def test_default_is_both(self):
        assert DEFAULT_LISTOFER_VIEW_MODE == "both"
        assert normalize_listofer_view_mode(None) == "both"
        assert normalize_listofer_view_mode("") == "both"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="view_mode"):
            normalize_listofer_view_mode("all")

    def test_iter_both_returns_two_views(self):
        items = [1, 2, 2]
        views = iter_listofer_views(items, lambda xs: [sum(xs)], view_mode="both")
        assert [label for label, _ in views] == ["detailed", "grouped"]
        assert views[0][1] == [1, 2, 2]
        assert views[1][1] == [5]

    def test_iter_detailed_and_grouped(self):
        items = [1, 1]
        assert iter_listofer_views(items, lambda xs: [9], "detailed") == [
            ("detailed", [1, 1])
        ]
        assert iter_listofer_views(items, lambda xs: [9], "grouped") == [
            ("grouped", [9])
        ]


class TestLongitudinalGrouping:
    def _bar(self, **kwargs) -> LongitudinalRebarData:
        defaults = dict(
            count=2,
            diameter=25,
            length=1640.0,
            shape_type="U",
            bend_length=39.0,
            pos="78",
        )
        defaults.update(kwargs)
        return LongitudinalRebarData(**defaults)

    def test_group_key_ignores_bend_and_pos(self):
        a = self._bar(pos="78", bend_length=39.0)
        b = self._bar(pos="25", bend_length=99.0)
        assert longitudinal_group_key(a) == longitudinal_group_key(b)

    def test_merges_same_size_length_shape_and_sums_count(self):
        rows = [
            self._bar(count=3, pos="78"),
            self._bar(count=2, pos="25"),
            self._bar(count=1, pos="20", shape_type="I", length=400.0),
        ]
        grouped = group_longitudinal_rebars(rows)
        assert len(grouped) == 2

        u_row = next(r for r in grouped if r.shape_type == "U")
        assert u_row.count == 5
        assert u_row.pos == "78"  # first POS kept
        assert u_row.diameter == 25
        assert u_row.length == 1640.0
        assert u_row.weight_kg() == pytest.approx(5 * 3.853 * 16.40, rel=1e-3)

        i_row = next(r for r in grouped if r.shape_type == "I")
        assert i_row.count == 1
        assert i_row.pos == "20"

    def test_different_shape_not_merged(self):
        rows = [
            self._bar(shape_type="L", length=500.0, count=1, pos="1"),
            self._bar(shape_type="U", length=500.0, count=1, pos="2"),
        ]
        assert len(group_longitudinal_rebars(rows)) == 2

    def test_incomplete_passthrough(self):
        rows = [
            self._bar(count=None, pos="x"),
            self._bar(count=1, pos="1"),
            self._bar(count=1, pos="2"),
        ]
        grouped = group_longitudinal_rebars(rows)
        assert len(grouped) == 2
        assert grouped[0].count == 2
        assert grouped[1].count is None


class TestStirrupGrouping:
    def _zone(self, **kwargs) -> StirrupZone:
        defaults = dict(
            pos=1,
            diameter=12.0,
            spacing=15.0,
            zone_length=140.0,
            count=11,
            single_length=2.49,
            total_length=27.39,
            unit_weight=0.888,
            total_weight=24.32,
            beam=BeamDimensions(width=60.0, height=70.0),
            description="T12@15",
        )
        defaults.update(kwargs)
        if "beam" in kwargs and isinstance(kwargs["beam"], tuple):
            w, h = kwargs["beam"]
            defaults["beam"] = BeamDimensions(width=w, height=h)
        return StirrupZone(**defaults)

    def test_group_key_uses_b_h_and_single_length(self):
        a = self._zone(pos=1, spacing=15.0)
        b = self._zone(pos=3, spacing=30.0)  # spacing ignored
        assert stirrup_group_key(a) == stirrup_group_key(b)

    def test_merges_and_sums_count_keeps_first_pos(self):
        rows = [
            self._zone(pos=1, count=11),
            self._zone(pos=3, count=11, spacing=20.0),
            self._zone(
                pos=5,
                count=12,
                beam=BeamDimensions(width=50.0, height=70.0),
                single_length=2.29,
                total_length=27.48,
            ),
        ]
        grouped = group_stirrup_zones(rows)
        assert len(grouped) == 2

        main = next(z for z in grouped if z.beam.width == 60.0)
        assert main.pos == 1
        assert main.count == 22
        assert main.single_length == pytest.approx(2.49)
        assert main.total_length == pytest.approx(22 * 2.49)
        assert main.total_weight == pytest.approx(round(22 * 2.49 * 0.888, 2))

        other = next(z for z in grouped if z.beam.width == 50.0)
        assert other.count == 12
        assert other.pos == 5

    def test_different_b_h_not_merged(self):
        rows = [
            self._zone(beam=BeamDimensions(60, 70), count=5, pos=1),
            self._zone(beam=BeamDimensions(60, 80), count=5, pos=2),
        ]
        assert len(group_stirrup_zones(rows)) == 2
