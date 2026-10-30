"""Édition directe — partie pure."""
from engine.directedit import drag_factor, extrude_arrow


def test_pad_cap_lengthens_pocket_floor_shortens():
    assert drag_factor(1.0, 20.0, "PartDesign::Pad") == 1.0
    assert drag_factor(1.0, -5.0, "PartDesign::Pocket") == -1.0
    assert drag_factor(-1.0, -10.0, "PartDesign::Pad") == 1.0
    assert drag_factor(1.0, 10.0, "PartDesign::Pad", midplane=True) == 2.0


def test_arrow_sits_at_the_end_of_the_extrusion():
    up = [0.0, 0.0, 1.0]
    base = [1.0, 2.0, 0.0]
    assert extrude_arrow(base, up, 20.0) == ([1.0, 2.0, 20.0], up, 1.0)
    # L'enlèvement creuse sous l'esquisse ; inversé, il repart au-dessus.
    assert extrude_arrow(base, up, 5.0, pocket=True) == (
        [1.0, 2.0, -5.0], [0.0, 0.0, -1.0], 1.0)
    assert extrude_arrow(base, up, 5.0, pocket=True, reversed=True) == (
        [1.0, 2.0, 5.0], up, 1.0)
    # Plan milieu : la flèche à mi-profondeur, la cote au double.
    assert extrude_arrow(base, up, 8.0, symmetric=True) == (
        [1.0, 2.0, 4.0], up, 2.0)
    assert extrude_arrow(base, up, 8.0, reversed=True, symmetric=True) == (
        [1.0, 2.0, 4.0], up, 2.0)
