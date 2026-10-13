"""Édition directe — partie pure."""
from engine.directedit import drag_factor


def test_pad_cap_lengthens_pocket_floor_shortens():
    assert drag_factor(1.0, 20.0, "PartDesign::Pad") == 1.0
    assert drag_factor(1.0, -5.0, "PartDesign::Pocket") == -1.0
    assert drag_factor(-1.0, -10.0, "PartDesign::Pad") == 1.0
    assert drag_factor(1.0, 10.0, "PartDesign::Pad", midplane=True) == 2.0
