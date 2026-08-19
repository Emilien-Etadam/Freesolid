"""mass_properties — centre de gravité pondéré (compound)."""

from engine.kernel import weighted_center_of_mass


def test_weighted_center_of_mass_two_solids():
    com = weighted_center_of_mass([
        (100.0, (0.0, 0.0, 0.0)),
        (300.0, (10.0, 0.0, 0.0)),
    ])
    assert com == (7.5, 0.0, 0.0)


def test_weighted_center_of_mass_empty():
    assert weighted_center_of_mass([]) is None
    assert weighted_center_of_mass([(0.0, (1.0, 2.0, 3.0))]) is None
