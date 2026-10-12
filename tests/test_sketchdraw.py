"""Tracés d'esquisse complémentaires : géométrie pure (sans FreeCAD)."""
import math

from engine.sketchdraw import conic_weight, rect3_corners, tangent_arc


def test_tangent_arc_turns_left_from_a_horizontal_line_end():
    cx, cy, r, a1, a2, pos = tangent_arc((10, 0), (1, 0), (10, 20))
    assert (round(cx, 9), round(cy, 9), round(r, 9)) == (10, 10, 10)
    assert pos == 1
    assert math.isclose(a1, -math.pi / 2) and math.isclose(a2, math.pi / 2)


def test_tangent_arc_turning_right_is_stored_from_its_far_end():
    cx, cy, r, a1, a2, pos = tangent_arc((10, 0), (1, 0), (10, -20))
    assert (round(cx, 9), round(cy, 9), round(r, 9)) == (10, -10, 10)
    assert pos == 2 and a1 < a2


def test_tangent_arc_refuses_a_point_on_the_tangent():
    assert tangent_arc((0, 0), (1, 0), (30, 0)) is None


def test_rect3_squares_the_third_point_and_parallelogram_keeps_it():
    assert rect3_corners((0, 0), (10, 0), (13, 5)) == [
        (0, 0), (10, 0), (10, 5), (0, 5)]
    assert rect3_corners((0, 0), (10, 0), (13, 5), True) == [
        (0, 0), (10, 0), (13, 5), (3, 5)]
    assert rect3_corners((0, 0), (10, 0), (20, 0)) is None


def test_conic_weight_follows_rho():
    assert conic_weight(0.5) == 1.0
    assert conic_weight(0.25) < 1 < conic_weight(0.75)
    assert conic_weight(0) is None and conic_weight(1) is None
