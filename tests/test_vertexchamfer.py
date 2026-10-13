"""Chanfrein de sommet — parties pures."""
from engine.vertexchamfer import check_distances, format_spec, parse_spec


def test_spec_round_trip_and_equal_distance():
    assert parse_spec(format_spec(7, [2, 3, 4.5])) == (7, [2.0, 3.0, 4.5])
    assert parse_spec(format_spec(0, [5])) == (0, [5.0, 5.0, 5.0])


def test_check_distances():
    assert check_distances([2]) is None
    assert check_distances([1, 2, 3]) is None
    assert check_distances([1, 2]) is not None
    assert check_distances([0]) is not None
    assert check_distances([]) is not None
