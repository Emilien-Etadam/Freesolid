"""Guardrail: translate PartDesign's cryptic failures into designer terms.

FreeCAD's most disorienting errors are correct but unexplained — the classic
being the multiple-solids refusal, where SolidWorks would silently create a
multibody part. This module maps the known error texts to explanations
phrased in the designer's vocabulary.

``friendly_error`` is pure and unit-tested. The Qt document observer that
used to live beside it was part of the retired addon and is not needed by
the headless engine.
"""

#: (lowercase fragment of the FreeCAD error, explanation shown to the user).
#: Fragments are matched case-insensitively against whatever error text the
#: build exposes. English fragments: FreeCAD logs errors untranslated.
_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("multiple solids",
     "Cette fonction créerait un volume séparé du reste de la pièce. "
     "SolidWorks en ferait une pièce multicorps ; ici, un Body ne contient "
     "qu'un seul solide d'un seul tenant. Créez un second corps "
     "(« Nouvelle pièce ») pour le volume détaché, ou modifiez l'esquisse "
     "pour que les volumes se touchent."),
    ("out of the allowed scope",
     "L'esquisse référence de la géométrie extérieure à la pièce active. "
     "Dans SolidWorks vous référenceriez l'autre pièce directement ; ici il "
     "faut d'abord importer la géométrie dans la pièce via une référence "
     "externe (ShapeBinder), puis coter sur cette référence."),
    ("wire is not closed",
     "Le contour de l'esquisse n'est pas fermé. Comme pour un bossage "
     "SolidWorks : le profil doit être une boucle fermée pour produire un "
     "solide. Fermez le contour ou supprimez les segments en trop."),
)


def friendly_error(text: str) -> str | None:
    """Explanation for a known FreeCAD error text, or ``None``.

    Matching is case-insensitive and fragment-based, so it survives the
    wording drift between FreeCAD versions as long as the key phrase stays.
    """
    lowered = (text or "").lower()
    for fragment, explanation in _TRANSLATIONS:
        if fragment in lowered:
            return explanation
    return None
