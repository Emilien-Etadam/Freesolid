"""Validation du plan neutre de dépouille — pur Python, sans FreeCAD."""

import pytest

from engine.kernel import KernelError, parse_neutral_plane


def test_parse_neutral_plane_defaults_and_aliases():
    assert parse_neutral_plane() == "XY"
    assert parse_neutral_plane("XY") == "XY"
    assert parse_neutral_plane("xz") == "XZ"
    assert parse_neutral_plane("Yz") == "YZ"


def test_parse_neutral_plane_rejects_unknown():
    with pytest.raises(KernelError) as excinfo:
        parse_neutral_plane("UV")
    assert "plan neutre inconnu" in str(excinfo.value)
    assert "UV" in str(excinfo.value)
