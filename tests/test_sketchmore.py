"""Courbe par équation : l'évaluateur n'accepte que des mathématiques."""
import math

import pytest

from engine.sketchmore import EquationError, compile_equation, equation_points


def test_equation_evaluates_math_of_t():
    f = compile_equation("10*sin(t) + t^2")
    assert math.isclose(f(math.pi / 2), 10 + (math.pi / 2) ** 2)
    assert compile_equation("pi*e")(0) == math.pi * math.e


@pytest.mark.parametrize("text", [
    "__import__('os')", "t.__class__", "open('x')", "[t for t in ()]",
    "lambda: 1", "x + 1", "'abc'", "",
])
def test_equation_refuses_anything_but_math(text):
    with pytest.raises(EquationError):
        compile_equation(text)


def test_equation_points_sample_t_and_refuse_undefined_values():
    pts = equation_points("t", "2*t", 0, 10, 3)
    assert pts == [(0.0, 0.0), (5.0, 10.0), (10.0, 20.0)]
    with pytest.raises(EquationError):
        equation_points("t", "1/t", 0, 1, 5)
    with pytest.raises(EquationError):
        equation_points("t", "sqrt(t)", -1, 1, 5)
