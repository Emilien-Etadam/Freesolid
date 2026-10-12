"""Chaîne tangente — partie pure."""
from engine.selectchain import aligned


def test_aligned_accepts_both_senses_only():
    assert aligned((1, 0, 0), (1, 0, 0))
    assert aligned((0, 0, 1), (0, 0, -1))
    assert not aligned((1, 0, 0), (0.7071, 0.7071, 0))
