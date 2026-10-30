"""Propriétés du document (engine/docoptions.py) : lecture tolérante,
écriture stricte, écarts de corde."""

import pytest

from engine import docoptions
from engine.kernel import KernelError


def test_defaults_when_nothing_is_kept():
    assert docoptions.normalize(None) == docoptions.DEFAULTS
    assert docoptions.normalize("") == docoptions.DEFAULTS
    assert docoptions.normalize("{abîmé") == docoptions.DEFAULTS
    assert docoptions.normalize("[1, 2]") == docoptions.DEFAULTS


def test_reading_keeps_valid_values_only():
    kept = docoptions.normalize(
        '{"length_decimals": 3, "angle_decimals": 9, "grid_fixed": 1,'
        ' "grid_step": 2.5, "quality": "fine", "autre": true}')
    assert kept == {**docoptions.DEFAULTS, "length_decimals": 3,
                    "grid_step": 2.5, "quality": "fine"}


def test_merge_changes_given_keys_only():
    current = '{"length_decimals": 3}'
    merged = docoptions.merge(current, {"grid_fixed": True, "grid_step": 5})
    assert merged == {**docoptions.DEFAULTS, "length_decimals": 3,
                      "grid_fixed": True, "grid_step": 5.0}


@pytest.mark.parametrize("values", [
    {"inconnue": 1},
    {"length_decimals": 7},
    {"length_decimals": 2.5},
    {"angle_decimals": True},
    {"grid_step": 0},
    {"grid_fixed": "oui"},
    {"quality": "ultra"},
])
def test_merge_refuses_unknown_keys_and_bad_values(values):
    with pytest.raises(KernelError):
        docoptions.merge("", values)


def test_mesh_settings_follow_the_quality():
    # Normale : l'angle du noyau, le maillage gardé en cache dans la pièce.
    assert docoptions.mesh_settings({}) == (0.1, None, 0.05)
    assert docoptions.mesh_settings({"quality": "coarse"}) == (0.5, 0.5, 0.25)
    face, angle, edge = docoptions.mesh_settings('{"quality": "finest"}')
    assert edge == face / 2
    # Du plus grossier au plus fin : l'écart et l'angle diminuent.
    order = ["coarse", "normal", "fine", "finest"]
    assert list(docoptions.QUALITY) == order
    faces = [docoptions.QUALITY[q][0] for q in order]
    angles = [docoptions.QUALITY[q][1] or 0.1 for q in order]
    assert faces == sorted(faces, reverse=True) and len(set(faces)) == 4
    assert angles == sorted(angles, reverse=True) and len(set(angles)) == 4
