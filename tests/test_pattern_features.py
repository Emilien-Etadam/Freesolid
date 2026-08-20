"""Validation de ``features`` pour les répétitions — pur Python, sans FreeCAD."""

import pytest

from engine.kernel import KernelError, resolve_pattern_originals


_CATALOG = {
    "Pad": {
        "in_body": True, "is_addsub": True, "label": "Bossage extrudé",
    },
    "Pocket": {
        "in_body": True, "is_addsub": True, "label": "Enlèvement de matière",
    },
    "Pad001": {
        "in_body": True, "is_addsub": True, "label": "Bossage 2",
    },
    "Fillet": {
        "in_body": True, "is_addsub": False, "label": "Congé",
    },
    "PadOther": {
        "in_body": False, "is_addsub": True, "label": "Bossage autre pièce",
    },
}


def test_empty_list_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals([], _CATALOG)
    assert "vide" in str(excinfo.value)


def test_not_a_list_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals("Pad", _CATALOG)
    assert "liste" in str(excinfo.value)


def test_unknown_name_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals(["Pad", "Inconnu"], _CATALOG)
    message = str(excinfo.value)
    assert "fonction inconnue" in message
    assert "Inconnu" in message


def test_blank_name_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals(["  "], _CATALOG)
    assert "fonction inconnue" in str(excinfo.value)


def test_feature_outside_body_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals(["PadOther"], _CATALOG)
    message = str(excinfo.value)
    assert "Bossage autre pièce" in message
    assert "corps actif" in message


def test_non_addsub_rejected():
    with pytest.raises(KernelError) as excinfo:
        resolve_pattern_originals(["Fillet"], _CATALOG)
    message = str(excinfo.value)
    assert "Congé" in message
    assert "additive ou soustractive" in message


def test_order_preserved():
    assert resolve_pattern_originals(
        ["Pocket", "Pad", "Pad001"], _CATALOG
    ) == ["Pocket", "Pad", "Pad001"]


def test_duplicates_dropped_order_kept():
    assert resolve_pattern_originals(
        ["Pocket", "Pad", "Pocket", "Pad001", "Pad"], _CATALOG
    ) == ["Pocket", "Pad", "Pad001"]
