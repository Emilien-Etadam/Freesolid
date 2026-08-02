"""Guardrail error translation — runs without FreeCAD."""

import pytest

from freesolid.guard import friendly_error


@pytest.mark.parametrize("raw,needle", [
    ("Result has multiple solids: enable 'Allow Compound'", "second corps"),
    ("RESULT HAS MULTIPLE SOLIDS", "second corps"),          # case-blind
    ("Links go out of the allowed scope", "ShapeBinder"),
    ("Wire is not closed", "fermé"),
])
def test_known_errors_get_an_explanation(raw, needle):
    explanation = friendly_error(raw)
    assert explanation is not None
    assert needle in explanation


def test_explanations_speak_solidworks(_=None):
    # The whole point: every message anchors to what SolidWorks would do.
    for raw in ("multiple solids", "out of the allowed scope",
                "wire is not closed"):
        assert "SolidWorks" in friendly_error(raw)


@pytest.mark.parametrize("raw", ["", None, "some other failure"])
def test_unknown_errors_stay_silent(raw):
    assert friendly_error(raw) is None
