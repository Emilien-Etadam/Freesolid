"""Validation de couleur par corps — pur Python, sans FreeCAD."""

import pytest

from engine.kernel import KernelError, parse_body_color


def test_parse_body_color_accepts_hex():
    assert parse_body_color("#cc5533") == "#cc5533"
    assert parse_body_color("#AABBCC") == "#AABBCC"


def test_parse_body_color_default_is_empty():
    assert parse_body_color(None) == ""
    assert parse_body_color("") == ""


def test_parse_body_color_rejects_invalid():
    for value in ("rouge", "#fff", "#gg0000", "cc5533", 1, True, []):
        with pytest.raises(KernelError) as excinfo:
            parse_body_color(value)
        assert "couleur invalide" in str(excinfo.value)
        assert "#rrggbb" in str(excinfo.value)
