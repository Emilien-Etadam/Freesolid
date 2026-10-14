"""Spline par points de passage — partie pure (jumelle de
app/splinemath.js : les deux lisent tests/splinemath_cases.json)."""
import json
import os

import pytest

from engine import splinemath as sm

CASES = json.load(open(os.path.join(os.path.dirname(__file__),
                                    "splinemath_cases.json"),
                       encoding="utf-8"))


def _close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_controls_match_reference(case):
    got = sm.controls(case["points"], case["closed"], case["tangents"])
    assert len(got) == len(case["controls"])
    for span, ref in zip(got, case["controls"]):
        for p, q in zip(span, ref):
            assert _close(p, q)


def test_curve_passes_through_points():
    case = CASES[3]
    spans = sm.controls(case["points"], False, None)
    for i, span in enumerate(spans):
        assert _close(span[0], case["points"][i])
        assert _close(span[3], case["points"][i + 1])


def test_two_points_make_a_segment():
    spans = sm.controls([[0, 0, 0], [9, 0, 0]])
    assert _close(spans[0][1], [3, 0, 0]) and _close(spans[0][2], [6, 0, 0])


def test_four_free_points_are_one_cubic():
    """Règle « pas de nœud » : comme l'interpolation de FreeCAD, quatre
    points donnent une seule cubique (dérivée troisième constante)."""
    pts = CASES[2]["points"]
    h = sm.chords(pts, False)
    d3 = [[(s[3][k] - 3 * s[2][k] + 3 * s[1][k] - s[0][k]) / hh ** 3
           for k in range(3)] for s, hh in zip(sm.controls(pts), h)]
    assert _close(d3[0], d3[1], 1e-9) and _close(d3[1], d3[2], 1e-9)


def test_piloted_tangent_is_respected():
    case = CASES[5]
    m_in, m_out = sm.solve(case["points"], False, case["tangents"])
    d = 1 / 2 ** 0.5
    assert _close(m_in[2], [0.5 * d, 0.5 * d, 0])
    assert _close(m_out[2], [2 * d, 2 * d, 0])


def test_round_trip_through_beziers_frees_what_it_can():
    case = CASES[5]
    spans = sm.controls(case["points"], False, case["tangents"])
    points, tangents = sm.from_beziers(spans)
    assert all(_close(p, q) for p, q in zip(points, case["points"]))
    assert [t is not None for t in tangents] == [False, False, True,
                                                 False, False]
    assert _close([tangents[2]["in"], tangents[2]["out"]], [0.5, 2.0], 1e-6)


def test_closed_curve_round_trip():
    case = CASES[4]
    spans = sm.controls(case["points"], True, None)
    points, tangents = sm.from_beziers(spans, closed=True)
    assert len(points) == 4 and not any(tangents)


def test_bad_input():
    with pytest.raises(ValueError):
        sm.solve([[0, 0, 0], [0, 0, 0], [1, 0, 0]])
    assert sm.clean_tangents([{"dir": [0, 0, 0]}, "x", None], 3) == [
        None, None, None]
    assert sm.knots([[0, 0], [3, 4], [3, 0]]) == [0.0, 5.0, 9.0]


def test_drag_tip_keeps_direction_shared():
    pts = CASES[3]["points"]
    tip_in, tip_out = sm.handle_tips(pts, False, None, 2)
    target = [tip_out[0], tip_out[1] + 2, tip_out[2]]
    both = sm.drag_tip(pts, False, None, 2, "out", target)
    alone = sm.drag_tip(pts, False, None, 2, "out", target, alone=True)
    assert _close(both[2]["dir"], alone[2]["dir"])
    assert abs(both[2]["out"] - alone[2]["out"]) < 1e-12
    assert _close(sm.handle_tips(pts, False, alone, 2)[1], target, 1e-9)
    assert sm.handle_tips(pts, False, None, 0)[0] is None
