"""Outils d'édition d'esquisse : géométrie pure (sans FreeCAD)."""
import math

from engine.sketchedit import copied_relation, line_intersection


def test_line_intersection_of_two_segments_extended():
    assert line_intersection((0, 0), (10, 0), (20, -5), (20, 5)) == (20, 0)
    assert line_intersection((0, 0), (10, 0), (0, 5), (10, 5)) is None


def test_copied_relations_drop_axis_ones_when_rotated():
    assert copied_relation("Horizontal", 0, 1) == (True, 1.0)
    assert copied_relation("Horizontal", math.pi / 2, 1) == (False, 1.0)
    assert copied_relation("Horizontal", 2 * math.pi, 1) == (True, 1.0)
    assert copied_relation("Coincident", math.pi / 3, 2) == (True, 1.0)


def test_copied_lengths_follow_the_scale_angles_do_not():
    assert copied_relation("Distance", 0, 2.5) == (True, 2.5)
    assert copied_relation("Radius", 0, 2.5) == (True, 2.5)
    assert copied_relation("Angle", 0, 2.5) == (True, 1.0)
    assert copied_relation("Block", 0, 1) == (False, 1.0)
