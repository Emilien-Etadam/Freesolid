"""Correspondance des erreurs géométriques — sans modeleur."""

import pytest

from engine.guard import failure_message, friendly_error, shell_too_thick_message
from engine.i18n import translate

_FORBIDDEN = (
    "solidworks", "freecad", "opencascade", "dassault", "shapebinder", "catia",
)


@pytest.mark.parametrize("raw,needle", [
    ("Result has multiple solids: enable 'Allow Compound'", "second corps"),
    ("RESULT HAS MULTIPLE SOLIDS", "second corps"),
    ("Links go out of the allowed scope", "pièce active"),
    ("Wire is not closed", "fermé"),
    ("Failed to make thick solid", "profils décalés"),
])
def test_known_errors_get_an_explanation(raw, needle):
    explanation = friendly_error(raw)
    assert explanation is not None
    assert needle in explanation


def test_explanations_name_no_other_software():
    samples = [
        friendly_error("multiple solids"),
        friendly_error("out of the allowed scope"),
        friendly_error("wire is not closed"),
        shell_too_thick_message(),
        failure_message("Congé", "", "PartDesign::Fillet"),
        failure_message("Chanfrein", "", "PartDesign::Chamfer"),
        failure_message("Dépouille", "", "PartDesign::Draft"),
        failure_message("Extrusion", "", "PartDesign::Pad"),
    ]
    for text in samples:
        lowered = text.lower()
        for word in _FORBIDDEN:
            assert word not in lowered


@pytest.mark.parametrize("raw", ["", None, "some other failure"])
def test_unknown_errors_stay_silent(raw):
    assert friendly_error(raw) is None


@pytest.mark.parametrize("kind,needle", [
    ("PartDesign::Fillet", "réduisez le rayon"),
    ("PartDesign::Chamfer", "réduisez la distance"),
    ("PartDesign::Thickness", "épaisseur est trop forte"),
    ("PartDesign::Draft", "dépouille est impossible"),
    ("PartDesign::Pad", "ne produit aucun volume"),
])
def test_opaque_failure_follows_the_feature(kind, needle):
    raw = "BRep_API: command not done"
    message = failure_message("Pièce", raw, kind)
    assert needle in message
    # Le générique du modeleur n'apprend rien : il n'est pas recopié.
    assert "command not done" not in message
    assert message.startswith("Pièce : ")


def test_specific_raw_text_stays_in_parentheses():
    message = failure_message("Pièce", "Profile is empty", "PartDesign::Pad")
    assert message.endswith("(Profile is empty)")


def test_empty_status_omits_the_raw_complement():
    message = failure_message("Dépouille", "", "PartDesign::Draft")
    assert message == (
        "Dépouille : La dépouille est impossible sur cette face — "
        "réduisez l'angle, ou choisissez une autre face ou un autre "
        "plan neutre.")
    assert "()" not in message


def test_specific_fragment_wins_over_the_feature_phrase():
    message = failure_message(
        "Extrusion", "Wire is not closed", "PartDesign::Pad")
    assert "n'est pas fermé" in message
    assert "ne produit aucun volume" not in message


def test_unexplained_status_is_left_alone():
    assert failure_message(
        "Congé", "Base feature's TopoShape is invalid",
        "PartDesign::Fillet") is None
    assert failure_message(
        "Autre", "BRep_API: command not done", "Part::Box") is None


def test_pad_empty_shape_is_explained():
    message = failure_message(
        "Extrusion", "Resulting shape is not a solid", "PartDesign::Pad")
    assert "ne produit aucun volume" in message
    assert "Resulting shape is not a solid" in message


def test_shell_refusal_is_the_thickness_sentence():
    assert shell_too_thick_message() == (
        "La coque est impossible : l'épaisseur est trop forte pour "
        "cette pièce — réduisez l'épaisseur.")


def test_messages_translate_to_english():
    fillet = failure_message(
        "Congé", "BRep_API: command not done", "PartDesign::Fillet")
    assert translate(fillet, "en") == (
        "Fillet: The radius is too large for the selected edges — "
        "reduce the radius.")
    assert translate(shell_too_thick_message(), "en") == (
        "The shell is impossible: the thickness is too large for this "
        "part — reduce the thickness.")
    closed = failure_message(
        "Extrusion", "Wire is not closed", "PartDesign::Pad")
    assert translate(closed, "en") == (
        "Extrude: The sketch outline is not closed. The profile must "
        "form a closed loop to produce a solid. Close the outline or "
        "delete the extra segments.")
    assert translate("attente : rien", "en") == "attente : rien"
