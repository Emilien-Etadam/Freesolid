"""Corps concernés : calculs purs, sans FreeCAD."""

import pytest

from engine.bodyscope import format_scope, is_subtractive_type, scope_names


def test_corps_concernes_ranges_en_texte():
    assert scope_names("Body001;;Body002") == ["Body001", "Body002"]
    assert scope_names(None) == []
    assert format_scope(["Body001", "Body002"]) == "Body001;Body002"


@pytest.mark.parametrize("type_id, expected", [
    ("PartDesign::Pocket", True),
    ("PartDesign::Groove", True),
    ("PartDesign::Hole", True),
    ("PartDesign::SubtractiveBox", True),
    ("PartDesign::SubtractiveLoft", True),
    ("PartDesign::Pad", False),
    ("PartDesign::AdditiveBox", False),
    ("PartDesign::Fillet", False),
])
def test_seuls_les_enlevements_creusent(type_id, expected):
    assert is_subtractive_type(type_id) is expected
