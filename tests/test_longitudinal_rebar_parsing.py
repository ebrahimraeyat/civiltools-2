from civiltools.building.longitudinal_rebar_from_dwg import (
    LongitudinalRebarFromDwg,
    _parse_int_attr,
)


def test_parse_des1_legacy_count_and_diameter() -> None:
    count, dia = LongitudinalRebarFromDwg._parse_des1("2T25")
    assert count == 2
    assert dia == 25


def test_parse_des1_parenthesized_designation() -> None:
    count, dia = LongitudinalRebarFromDwg._parse_des1("T16(B)")
    assert count is None
    assert dia == 16


def test_parse_des1_spacing_designation() -> None:
    count, dia = LongitudinalRebarFromDwg._parse_des1("T12@120(T)")
    assert count is None
    assert dia == 12


def test_parse_int_attr_variants() -> None:
    assert _parse_int_attr("12") == 12
    assert _parse_int_attr("12.0") == 12
    assert _parse_int_attr("") is None
    assert _parse_int_attr("abc") is None


def test_block_filter_match_name_and_layer() -> None:
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    extractor.block_names = {"st"}
    extractor.block_layers = {"ahan"}

    class _Block:
        EffectiveName = "ST"
        Layer = "AHAN"

    assert extractor._block_matches_filters(_Block()) is True


def test_block_filter_reject_wrong_layer() -> None:
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    extractor.block_names = {"st"}
    extractor.block_layers = {"ahan"}

    class _Block:
        EffectiveName = "ST"
        Layer = "OTHER"

    assert extractor._block_matches_filters(_Block()) is False


class _FakeAttr:
    def __init__(self, tag: str, value: str) -> None:
        self.TagString = tag
        self.TextString = value


class _FakeBlock:
    def __init__(self, attrs: dict[str, str], object_id: int = 1) -> None:
        self.ObjectID = object_id
        self.InsertionPoint = (0.0, 0.0, 0.0)
        self._attrs = [_FakeAttr(k, v) for k, v in attrs.items()]

    def GetAttributes(self):  # noqa: N802 - matches AutoCAD COM API
        return self._attrs


def test_parse_uses_tn_and_captures_des_fields() -> None:
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    extractor.hook_type = "90"
    extractor.leaders = []
    extractor.text_objects = []
    extractor.blocks = [
        _FakeBlock(
            {
                "PO": "37",
                "DES1": "T16(B)",
                "DES2": "L=900",
                "DES3": "TU30",
                "N": "4",
                "TN": "12",
            }
        )
    ]

    rebars = extractor.parse_longitudinal_rebars()
    assert len(rebars) == 1
    rd = rebars[0]
    assert rd.pos == "37"
    assert rd.des1 == "T16(B)"
    assert rd.des2 == "L=900"
    assert rd.des3 == "TU30"
    assert rd.n == 4
    assert rd.tn == 12
    assert rd.count == 12  # TN is primary
    assert rd.diameter == 16
    assert rd.length == 900.0  # cm
    assert rd.shape_type == "U"
    assert any("used TN" in w for w in rd.warnings)


def test_parse_spacing_des1_ignores_spacing() -> None:
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    extractor.hook_type = "90"
    extractor.leaders = []
    extractor.text_objects = []
    extractor.blocks = [
        _FakeBlock(
            {
                "DES1": "T12@120(T)",
                "DES2": "L=450",
                "DES3": "TI",
                "TN": "8",
            }
        )
    ]

    rd = extractor.parse_longitudinal_rebars()[0]
    assert rd.diameter == 12
    assert rd.count == 8
    assert rd.length == 450.0
    assert rd.shape_type == "I"
    assert rd.bend_length == 0.0


def test_parse_falls_back_to_n_when_tn_missing() -> None:
    extractor = LongitudinalRebarFromDwg.__new__(LongitudinalRebarFromDwg)
    extractor.hook_type = "90"
    extractor.leaders = []
    extractor.text_objects = []
    extractor.blocks = [
        _FakeBlock(
            {
                "DES1": "2T25",
                "DES2": "L=240",
                "DES3": "TL",
                "N": "3",
            }
        )
    ]

    rd = extractor.parse_longitudinal_rebars()[0]
    assert rd.count == 3
    assert rd.diameter == 25
    assert any("used N" in w for w in rd.warnings)
