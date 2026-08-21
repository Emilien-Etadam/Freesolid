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


def test_reconstitution_table_is_pure():
    from engine.replay import reconstitution_table
    table = reconstitution_table()
    assert "PartDesign::Pad" in table["replayable"]
    assert "add_loft" in table["unreplayable"]
    assert "add_text" in table["unreplayable"]
    assert "add_repeat_feature" in table["unreplayable"]


def test_topology_verdict_ok_when_counts_and_kinds_match():
    from engine.replay import topology_verdict
    expected = {"edges": 12, "faces": 6,
                "kinds": {"Edge3": "Line", "Face1": "Plane"}}
    assert topology_verdict(expected, dict(expected)) is None


def test_topology_verdict_refuses_count_change():
    from engine.replay import topology_verdict
    expected = {"edges": 12, "faces": 6, "kinds": {"Edge3": "Line"}}
    actual = {"edges": 24, "faces": 10, "kinds": {"Edge3": "Line"}}
    reason = topology_verdict(expected, actual)
    assert reason is not None
    assert "12" in reason and "24" in reason
    assert "6" in reason and "10" in reason


def test_topology_verdict_refuses_kind_change():
    from engine.replay import topology_verdict
    expected = {"edges": 12, "faces": 6,
                "kinds": {"Edge3": "Line"}}
    actual = {"edges": 12, "faces": 6,
              "kinds": {"Edge3": "Circle"}}
    reason = topology_verdict(expected, actual)
    assert reason == "Edge3 était Line, elle est Circle"


def test_topology_verdict_refuses_out_of_bounds():
    from engine.replay import topology_verdict
    expected = {"edges": 8, "faces": 6, "kinds": {"Edge9": "Line"}}
    actual = {"edges": 8, "faces": 6, "kinds": {}}
    reason = topology_verdict(expected, actual)
    assert reason is not None
    assert "Edge9" in reason
    assert "8" in reason


def test_topology_verdict_swapped_same_kind_passes():
    """Deux arêtes Line qui échangent leur indice : la garde ne voit rien."""
    from engine.replay import topology_verdict
    expected = {"edges": 12, "faces": 6,
                "kinds": {"Edge3": "Line", "Edge7": "Line"}}
    actual = {"edges": 12, "faces": 6,
              "kinds": {"Edge3": "Line", "Edge7": "Line"}}
    assert topology_verdict(expected, actual) is None


def test_parse_repeat_instances_accepts_numbers():
    from engine.replay import parse_repeat_instances
    parsed = parse_repeat_instances(
        [{"offset": [40, 0, 0], "params": {"Pad": {"Length": 10}}}],
        ["Pad", "Pocket"],
    )
    assert parsed[0]["offset"] == (40.0, 0.0, 0.0)
    assert parsed[0]["params"]["Pad"]["Length"] == 10.0


def test_parse_repeat_instances_refuses_expression():
    from engine.kernel import KernelError
    from engine.replay import parse_repeat_instances
    with pytest.raises(KernelError) as excinfo:
        parse_repeat_instances(
            [{"params": {"Pad": {"Length": "Variables.x"}}}],
            ["Pad"],
        )
    assert "nombres" in str(excinfo.value)


def test_parse_repeat_instances_ceiling_names_500():
    from engine.kernel import KernelError
    from engine.replay import REPEAT_INSTANCE_MAX, parse_repeat_instances
    assert REPEAT_INSTANCE_MAX == 500
    with pytest.raises(KernelError) as excinfo:
        parse_repeat_instances(
            [{"offset": [0, 0, 0], "params": {}}] * 501,
            ["Pad"],
        )
    assert "500" in str(excinfo.value)


def test_parse_repeat_instances_empty_refused():
    from engine.kernel import KernelError
    from engine.replay import parse_repeat_instances
    with pytest.raises(KernelError) as excinfo:
        parse_repeat_instances([], ["Pad"])
    assert "vide" in str(excinfo.value)
