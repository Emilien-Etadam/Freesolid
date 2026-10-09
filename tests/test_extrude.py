"""Conditions de fin d'extrusion — sans FreeCAD."""

import pytest

from engine.extrude import (ExtrudeError, cavity_plan, check_cavity,
                            extrude_settings, thin_cap_offsets, thin_offsets,
                            thin_settings)


def test_borgne_par_defaut():
    props = extrude_settings("pad", length=10)
    assert props == {"SideType": "One side", "Type": "Length",
                     "Length": 10.0, "Reversed": False}


def test_jusqu_a_la_face_avec_decalage():
    props = extrude_settings("pad", cond="face", face=4, offset=2)
    assert props["Type"] == "UpToFace"
    assert props["UpToFace"] == 4
    assert props["Offset"] == 2.0
    assert "Length" not in props


def test_jusqu_a_la_face_sans_face():
    with pytest.raises(ExtrudeError):
        extrude_settings("pad", cond="face")


def test_a_travers_tout_selon_la_fonction():
    assert extrude_settings("pocket", cond="travers")["Type"] == "ThroughAll"
    assert extrude_settings("pad", cond="dernier")["Type"] == "UpToLast"


def test_plan_milieu():
    props = extrude_settings("pad", length=20, midplane=True)
    assert props["SideType"] == "Symmetric"


def test_deuxieme_direction():
    props = extrude_settings("pad", length=10, cond2="borgne", length2=5,
                             taper2=3)
    assert props["SideType"] == "Two sides"
    assert props["Type2"] == "Length" and props["Length2"] == 5.0
    assert props["TaperAngle2"] == -3.0   # vers l'intérieur


def test_plan_milieu_et_direction_2_s_excluent():
    with pytest.raises(ExtrudeError):
        extrude_settings("pad", length=10, midplane=True,
                         cond2="borgne", length2=5)


def test_depouille_et_inversion():
    props = extrude_settings("pocket", length=8, taper=5, reversed=True)
    assert props["TaperAngle"] == -5.0 and props["Reversed"] is True
    # Un angle négatif dépouille vers l'extérieur.
    assert extrude_settings("pad", length=8, taper=-5)["TaperAngle"] == 5.0


def test_profondeur_nulle_refusee():
    with pytest.raises(ExtrudeError):
        extrude_settings("pad", length=0)


def test_condition_inconnue():
    with pytest.raises(ExtrudeError):
        extrude_settings("pad", cond="spirale", length=3)


def test_paroi_mince_un_cote():
    spec = thin_settings("un", thickness=2)
    assert thin_offsets(spec) == [(2.0, True)]
    assert thin_offsets(thin_settings("un", 2, reversed=True)) == [(-2.0, True)]


def test_paroi_mince_plan_milieu_et_deux_cotes():
    assert thin_offsets(thin_settings("milieu", 4)) == [(-2.0, False),
                                                       (4.0, True)]
    spec = thin_settings("deux", thickness=3, thickness2=1)
    assert thin_offsets(spec) == [(-1.0, False), (4.0, True)]
    spec = thin_settings("deux", thickness=3, thickness2=1, reversed=True)
    assert thin_offsets(spec) == [(-3.0, False), (4.0, True)]


@pytest.mark.parametrize("kwargs", [
    {"type": "un", "thickness": 0},
    {"type": "deux", "thickness": 1},
    {"type": "coque", "thickness": 1},
])
def test_paroi_mince_refusee(kwargs):
    with pytest.raises(ExtrudeError):
        thin_settings(**kwargs)


def test_extremites_fermees_contour_et_cavite():
    assert thin_cap_offsets(thin_settings("un", 2, caps=1)) == (2.0, 0.0)
    assert thin_cap_offsets(thin_settings("un", 2, reversed=True,
                                          caps=1)) == (0.0, -2.0)
    assert thin_cap_offsets(thin_settings("milieu", 2, caps=1)) == (1.0, -1.0)
    assert thin_cap_offsets(thin_settings("deux", 3, 1, caps=1)) == (3.0, -1.0)
    with pytest.raises(ExtrudeError):
        thin_settings("un", 2, caps=-1)


def test_cavite_suit_la_fonction():
    assert cavity_plan("One side", "Pad") == {
        "SideType": "Two sides", "Length": "Pad.Length - Pad.CapThickness",
        "Length2": "-Pad.CapThickness"}
    assert cavity_plan("Symmetric", "Pad")["Length"] == (
        "Pad.Length - 2 * Pad.CapThickness")
    assert cavity_plan("Two sides", "Pad")["Length2"] == (
        "Pad.Length2 - Pad.CapThickness")
    check_cavity("One side", 10, 0, 4)
    with pytest.raises(ExtrudeError):
        check_cavity("One side", 10, 0, 5)
    check_cavity("Two sides", 4, 4, 3)
