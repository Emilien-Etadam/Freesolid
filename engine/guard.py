"""Phrases claires pour les échecs géométriques connus.

``friendly_error`` reconnaît un fragment du message brut.
``failure_message`` construit la ligne montrée à l'utilisateur : la phrase
utile, et le texte brut entre parenthèses quand il aide au diagnostic —
jamais le générique « command not done », qui n'apprend rien.

Purs : aucun import du modeleur, testés sans lui.
"""

# (fragment en minuscules, gabarit « {} » = libellé de la fonction).
# Les fragments sont en anglais : c'est ainsi que le modeleur les écrit.
_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("multiple solids",
     "{} : Cette fonction créerait un volume séparé du reste de la pièce. "
     "Un corps ne contient qu'un seul solide d'un seul tenant. "
     "Créez un second corps pour le volume détaché, ou modifiez "
     "l'esquisse pour que les volumes se touchent."),
    ("out of the allowed scope",
     "{} : L'esquisse utilise une géométrie qui n'appartient pas à la "
     "pièce active. Importez d'abord cette géométrie dans la pièce, "
     "puis cotez sur cette copie."),
    ("failed to make thick solid",
     "{} : Le modeleur n'a pas pu creuser cette pièce. Cela arrive "
     "quand une arête passe d'un angle vif à une tangence (lissage "
     "d'un carré vers un rond) ou quand l'épaisseur dépasse un rayon. "
     "Essayez une épaisseur plus faible ou la coque vers l'extérieur —"
     " ou creusez par un enlèvement : lissage ou extrusion des profils"
     " décalés de l'épaisseur."),
    ("wire is not closed",
     "{} : Le contour de l'esquisse n'est pas fermé. Le profil doit "
     "former une boucle fermée pour produire un solide. Fermez le "
     "contour ou supprimez les segments en trop."),
)

# TypeId → gabarit. Premier {} = libellé, second {} = texte brut.
_OPAQUE_BY_KIND: dict[str, str] = {
    "PartDesign::Fillet":
        "{} : Le rayon est trop grand pour les arêtes choisies — réduisez le rayon. ({})",
    "PartDesign::Chamfer":
        "{} : La distance est trop grande pour les arêtes choisies — réduisez la distance. ({})",
    "PartDesign::Thickness":
        "{} : La coque est impossible : l'épaisseur est trop forte pour cette pièce — réduisez l'épaisseur. ({})",
    "PartDesign::Draft":
        "{} : La dépouille est impossible sur cette face — réduisez l'angle, ou choisissez une autre face ou un autre plan neutre. ({})",
    "PartDesign::Pad":
        "{} : Le profil ne produit aucun volume. ({})",
}

_RAW_SUFFIX = " ({})"
_LABEL_PREFIX = "{} : "


def _without_raw(template: str) -> str:
    if template.endswith(_RAW_SUFFIX):
        return template[: -len(_RAW_SUFFIX)]
    return template


def _explanation(template: str) -> str:
    body = _without_raw(template)
    if body.startswith(_LABEL_PREFIX):
        return body[len(_LABEL_PREFIX):]
    return body


def _fill(template: str, values) -> str:
    """Remplace les ``{}`` dans l'ordre, sans interpréter le texte brut."""
    out = template
    for value in values:
        out = out.replace("{}", str(value), 1)
    return out


def friendly_error(text: str) -> str | None:
    """Explication d'un message brut connu, ou ``None``.

    La recherche est insensible à la casse et porte sur un fragment, pour
    suivre les petites variations de formulation.
    """
    lowered = (text or "").lower()
    for fragment, template in _TRANSLATIONS:
        if fragment in lowered:
            return _explanation(template)
    return None


def _opaque(kind: str, raw: str, lowered: str) -> bool:
    if not raw or "command not done" in lowered:
        return True
    if kind == "PartDesign::Pad" and (
            "not a solid" in lowered or "no solid" in lowered
            or "empty" in lowered):
        return True
    return False


def failure_message(label: str, text: str, kind: str = "") -> str | None:
    """Ligne « libellé : explication », ou ``None`` si le texte brut reste plus clair."""
    label = "" if label is None else str(label)
    raw = (text or "").strip()
    lowered = raw.lower()
    for fragment, template in _TRANSLATIONS:
        if fragment in lowered:
            return _fill(template, (label,))
    template = _OPAQUE_BY_KIND.get(kind or "")
    if template is None or not _opaque(kind, raw, lowered):
        return None
    if raw and "command not done" not in lowered:
        return _fill(template, (label, raw))
    return _fill(_without_raw(template), (label,))


def shell_too_thick_message() -> str:
    """Coque acceptée par le modeleur mais sans enlèvement de matière."""
    return _explanation(_OPAQUE_BY_KIND["PartDesign::Thickness"])
