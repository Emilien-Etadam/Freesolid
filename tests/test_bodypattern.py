"""Réseau de corps, corps concernés : calculs purs, sans FreeCAD."""

import pytest

from engine.bodypattern import (
    body_pattern_offsets,
    copy_key,
    format_scope,
    is_subtractive_type,
    linear_steps,
    parse_copy_key,
    polar_angles,
    scope_names,
)


def test_pas_lineaire_longueur_totale_et_pas():
    assert linear_steps("Extent", 3, 20, 0) == [0.0, 10.0, 20.0]
    assert linear_steps("Spacing", 3, 0, 15) == [0.0, 15.0, 30.0]
    assert linear_steps("Extent", 1, 20, 0) == [0.0]


def test_pas_lineaire_ecarts_propres_puis_motif():
    # Un écart à -1 laisse la place au motif, puis au pas commun.
    assert linear_steps("Spacing", 4, 0, 5, spacings=(2.0, -1.0)) == [
        0.0, 2.0, 7.0, 12.0]
    assert linear_steps("Spacing", 4, 0, 5, pattern=(1.0, 3.0)) == [
        0.0, 1.0, 4.0, 5.0]


def test_angles_tour_complet_ou_ouvert():
    assert polar_angles("Extent", 4, 360) == [0.0, 90.0, 180.0, 270.0]
    assert polar_angles("Extent", 3, 90) == [0.0, 45.0, 90.0]
    assert polar_angles("Spacing", 3, 0, offset=30) == [0.0, 30.0, 60.0]
    assert polar_angles("Extent", 1, 360) == [0.0]


def test_occurrences_lineaires_sans_la_source():
    assert body_pattern_offsets("linear", 3, 20, True) == [
        ("1", 2, 20.0, 0.0), ("2", 3, 40.0, 0.0)]
    assert body_pattern_offsets("linear", 3, 20, False) == [
        ("1", 2, 10.0, 0.0), ("2", 3, 20.0, 0.0)]


def test_occurrences_deux_directions():
    out = body_pattern_offsets("linear", 2, 10, True, count2=2, length2=5)
    assert out == [("0,1", 2, 0.0, 5.0), ("1,0", 3, 10.0, 0.0),
                   ("1,1", 4, 10.0, 5.0)]


def test_occurrences_circulaires_et_symetrie():
    assert body_pattern_offsets("polar", 3, 0, False, angle=360) == [
        ("1", 2, 120.0, 0.0), ("2", 3, 240.0, 0.0)]
    assert body_pattern_offsets("mirror", 0, 0, False) == [
        ("1", 2, 0.0, 0.0)]


def test_cle_de_copie_aller_retour():
    key = copy_key("BodyPattern", "Body", "1,0")
    assert key == "BodyPattern|Body|1,0"
    assert parse_copy_key(key) == ("BodyPattern", "Body", "1,0")
    for bad in ("", None, "a|b", "a||c", "a|b|c|d"):
        assert parse_copy_key(bad) is None


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
