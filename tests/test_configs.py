"""Configurations — parties pures."""
from engine.configs import apply_order, clean_config_name


def test_config_names():
    assert clean_config_name("  Long  ") == "Long"
    assert clean_config_name("   ") is None
    assert len(clean_config_name("x" * 80)) == 40


def test_variables_first_then_values_then_flags():
    snap = {"suppressed:Fillet": True, "prop:Pad.Length": 30.0,
            "var:Largeur": 20.0}
    assert apply_order(snap) == ["var:Largeur", "prop:Pad.Length",
                                 "suppressed:Fillet"]
