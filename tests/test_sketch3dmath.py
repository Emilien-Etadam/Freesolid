"""Esquisse 3D — solveur pur (jumeau de app/sketch3dmath.js : les deux
lisent tests/sketch3d_cases.json)."""
import json
import math
import os

import pytest

from engine import sketch3dmath as m

CASES = json.load(open(os.path.join(os.path.dirname(__file__),
                                    "sketch3d_cases.json"), encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_solve_matches_reference(case):
    out = m.solve(case["spec"], case["fixed"])
    assert out["ok"] == case["expected"]["ok"]
    for p, q in zip(out["points"], case["expected"]["points"]):
        assert all(abs(a - b) < 1e-6 for a, b in zip(p, q))


def test_constraints_hold():
    spec = m.clean_spec(CASES[1]["spec"])
    out = m.solve(spec, [0])
    pts = out["points"]
    assert abs(m.measure(spec, pts, spec["dims"][0]) - 90) < 1e-6
    assert abs(m.measure(spec, pts, spec["dims"][1]) - 30) < 1e-6
    assert pts[0] == [0.0, 0.0, 0.0]


def test_clean_spec_drops_what_does_not_hold():
    spec = m.clean_spec({
        "points": [[0, 0, 0], [1, 2], "x"],
        "entities": [{"type": "line", "a": 0, "b": 0},
                     {"type": "line", "a": 0, "b": 1},
                     {"type": "spline", "pts": [0, 9]},
                     {"type": "point", "p": 2}, "junk"],
        "dims": [{"type": "length", "entity": 0, "value": 5},
                 {"type": "length", "entity": 1, "value": -1},
                 {"type": "angle", "e1": 0, "e2": 0, "value": 30}],
        "relations": [{"type": "axis", "entity": 0, "axis": "W"},
                      {"type": "axis", "entity": 0, "axis": "Y"}]})
    assert spec["points"] == [[0, 0, 0], [1, 2, 0], [0, 0, 0]]
    assert [e["type"] for e in spec["entities"]] == ["line", "point"]
    assert spec["dims"] == [{"type": "length", "entity": 0, "value": 5.0}]
    assert spec["relations"] == [{"type": "axis", "entity": 0, "axis": "Y"}]
    assert m.chains(spec) == [0]


def test_unconstrained_points_never_move():
    spec = {"points": [[0, 0, 0], [3, 4, 0], [7, 7, 7]],
            "entities": [{"type": "line", "a": 0, "b": 1},
                         {"type": "point", "p": 2}],
            "dims": [{"type": "length", "entity": 0, "value": 10}]}
    out = m.solve(spec, [0])
    assert out["points"][2] == [7, 7, 7]
    assert math.isclose(out["points"][1][0] / out["points"][1][1], 0.75,
                        rel_tol=1e-6)
