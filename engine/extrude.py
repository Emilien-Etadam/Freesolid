"""Conditions de fin d'une extrusion (bossage, enlèvement) — module pur.

Le client parle en conditions de modeleur : borgne, jusqu'au suivant,
jusqu'au dernier / à travers tout, jusqu'à une face (avec décalage),
plan milieu, deuxième direction, dépouille. Ce module les traduit en
propriétés de ``PartDesign::Pad`` / ``PartDesign::Pocket`` (FreeCAD ≥ 1.1 :
``SideType`` et un jeu de propriétés par côté). Il ne touche pas FreeCAD :
les faces restent des numéros, kernel.py les résout en références.
"""

#: Condition client → valeur de ``Type`` selon la fonction.
_TYPES = {
    "pad": {
        "borgne": "Length", "suivant": "UpToFirst", "dernier": "UpToLast",
        "travers": "UpToLast", "face": "UpToFace",
    },
    "pocket": {
        "borgne": "Length", "suivant": "UpToFirst", "dernier": "ThroughAll",
        "travers": "ThroughAll", "face": "UpToFace",
    },
}


class ExtrudeError(ValueError):
    """Paramètres d'extrusion incohérents — message pour l'utilisateur."""


def _side(kind, cond, length, face, offset, taper, suffix):
    """Propriétés d'un côté (``suffix`` = "" ou "2")."""
    cond = cond or "borgne"
    types = _TYPES[kind]
    if cond not in types:
        raise ExtrudeError("condition de fin inconnue : {}".format(cond))
    props = {"Type" + suffix: types[cond]}
    if cond == "borgne":
        if length is None or float(length) <= 0:
            raise ExtrudeError("profondeur invalide")
        props["Length" + suffix] = float(length)
    if cond == "face":
        if face is None:
            raise ExtrudeError(
                "jusqu'à la face : cliquez la face d'arrivée")
        props["UpToFace" + suffix] = int(face)   # résolu par le noyau
        props["Offset" + suffix] = float(offset or 0)
    if taper:
        # Angle positif = dépouille vers l'intérieur (la section se
        # resserre) ; FreeCAD compte l'inverse.
        props["TaperAngle" + suffix] = -float(taper)
    return props


def extrude_settings(kind, cond="borgne", length=None, face=None,
                     offset=0.0, taper=0.0, midplane=False, reversed=False,
                     cond2=None, length2=None, face2=None, offset2=0.0,
                     taper2=0.0):
    """Propriétés à poser, dans l'ordre ; ``UpToFace``/``UpToFace2`` sont
    des numéros de face (0-based) à résoudre en ``(tip, ["FaceN"])``.

    ``cond2`` non nul ouvre la deuxième direction ; ``midplane`` est
    exclusif avec elle (plan milieu = même profondeur des deux côtés).
    """
    if kind not in _TYPES:
        raise ExtrudeError("fonction inconnue : {}".format(kind))
    if midplane and cond2:
        raise ExtrudeError(
            "plan milieu et deuxième direction s'excluent")
    props = {}
    if midplane:
        props["SideType"] = "Symmetric"
    elif cond2:
        props["SideType"] = "Two sides"
    else:
        props["SideType"] = "One side"
    props.update(_side(kind, cond, length, face, offset, taper, ""))
    if cond2:
        props.update(_side(kind, cond2, length2, face2, offset2, taper2, "2"))
    props["Reversed"] = bool(reversed)
    return props


#: Paroi mince : un côté, plan milieu, deux côtés (épaisseurs distinctes).
THIN_TYPES = ("un", "milieu", "deux")


def thin_settings(type="un", thickness=None, thickness2=None,
                  reversed=False):
    """Paroi mince validée : ``{type, thickness, thickness2, reversed}``.

    ``thickness`` s'applique vers l'extérieur d'un profil fermé (à droite
    du sens de tracé d'un profil ouvert) ; ``reversed`` change de côté.
    En « deux côtés », ``thickness2`` est l'épaisseur de l'autre côté.
    """
    if type not in THIN_TYPES:
        raise ExtrudeError("paroi mince : type inconnu : {}".format(type))
    if thickness is None or float(thickness) <= 0:
        raise ExtrudeError("épaisseur de paroi invalide")
    spec = {"type": type, "thickness": float(thickness),
            "thickness2": 0.0, "reversed": bool(reversed)}
    if type == "deux":
        if thickness2 is None or float(thickness2) <= 0:
            raise ExtrudeError("épaisseur de paroi (côté 2) invalide")
        spec["thickness2"] = float(thickness2)
    return spec


def thin_offsets(spec):
    """Décalages 2D successifs du profil : ``[(décalage, remplir), …]``.

    Un seul décalage rempli donne la bande entre le profil et son
    décalé ; pour une bande à cheval sur le profil, on décale d'abord
    (sans remplir) vers l'intérieur, puis on remplit sur toute la largeur.
    """
    t, t2 = spec["thickness"], spec["thickness2"]
    if spec["type"] == "un":
        return [(-t if spec["reversed"] else t, True)]
    if spec["type"] == "milieu":
        return [(-t / 2, False), (t, True)]
    outer, inner = (t2, t) if spec["reversed"] else (t, t2)
    return [(-inner, False), (outer + inner, True)]
