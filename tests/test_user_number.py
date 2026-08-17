"""Nombre saisi utilisateur — pur Python, sans FreeCAD."""

from engine.kernel import parse_user_number


def test_virgule_francaise():
    assert parse_user_number("6,5") == 6.5
    assert parse_user_number(" 15,0 ") == 15.0


def test_point_et_entier():
    assert parse_user_number("6.5") == 6.5
    assert parse_user_number("4") == 4.0


def test_non_nombres():
    assert parse_user_number("") is None
    assert parse_user_number("  ") is None
    assert parse_user_number("largeur/2") is None
    assert parse_user_number("_") is None
    assert parse_user_number("6 8") is None
