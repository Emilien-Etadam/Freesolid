"""Matières — parties pures."""
import re

from engine.materials import LIBRARY, clean_face_colors, material_by_id


def test_library_entries_are_well_formed():
    ids = [m[0] for m in LIBRARY]
    assert len(ids) == len(set(ids))
    for mid, name, density, color in LIBRARY:
        assert mid and name and density > 0
        assert re.fullmatch(r"#[0-9a-f]{6}", color)
    assert material_by_id("steel")[2] == 7.85
    assert material_by_id("nope") is None


def test_clean_face_colors_keeps_valid_entries():
    assert clean_face_colors({"0": "#FF0000", "-1": "#00ff00", "x": "#000000",
                              "3": "rouge"}) == {"0": "#ff0000"}
