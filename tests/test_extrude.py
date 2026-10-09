"""Conditions de fin d'extrusion — sans FreeCAD."""

import pytest

from engine.extrude import ExtrudeError, extrude_settings


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
