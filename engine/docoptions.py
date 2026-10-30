"""Propriétés du document : les réglages gardés dans le fichier, pour ce
document seulement (les options du système, elles, sont gardées par le
navigateur).

- ``length_decimals``, ``angle_decimals`` : décimales des cotes et des
  valeurs affichées (longueurs en mm, angles en degrés). L'unité reste le
  millimètre, le gramme et la seconde.
- ``grid_fixed``, ``grid_step`` : en esquisse, la grille d'accrochage suit
  le zoom, ou garde un pas fixe (mm).
- ``quality`` : la finesse des facettes affichées (l'écart de corde et
  l'angle entre facettes, ``QUALITY``) ; les arêtes prennent la moitié de
  l'écart.

Les réglages tiennent en JSON dans une propriété cachée du document
(``FreeSolidOptions``). Module pur : testé en CI sans FreeCAD.
"""

import json

#: Les réglages et leur valeur par défaut.
DEFAULTS = {
    "length_decimals": 2,
    "angle_decimals": 1,
    "grid_fixed": False,
    "grid_step": 10.0,
    "quality": "normal",
}

#: Qualité d'image -> (écart de corde des faces en mm, angle maximal entre
#: deux facettes en radians). Sur une courbure ordinaire, c'est l'angle qui
#: fixe le nombre de facettes. « normal » garde celui que le noyau prend de
#: lui-même (None, 0,1 rad) : ce maillage-là reste en cache dans la pièce.
QUALITY = {
    "coarse": (0.5, 0.5),
    "normal": (0.1, None),
    "fine": (0.05, 0.07),
    "finest": (0.02, 0.05),
}

#: Bornes des nombres : (min, max).
_RANGES = {
    "length_decimals": (0, 6),
    "angle_decimals": (0, 4),
    "grid_step": (0.01, 1000.0),
}


def _valid(key, value):
    """La valeur ``value`` de ``key`` telle qu'elle se garde, ou None si
    elle ne convient pas."""
    if key == "grid_fixed":
        return value if isinstance(value, bool) else None
    if key == "quality":
        return value if value in QUALITY else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    low, high = _RANGES[key]
    if not low <= value <= high:
        return None
    if key.endswith("_decimals"):
        return int(value) if float(value).is_integer() else None
    return float(value)


def normalize(raw):
    """Les réglages lus d'un fichier : chaque clé connue et valide, sinon
    sa valeur par défaut. ``raw`` : le JSON gardé, un dict ou rien."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raw = {}
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            value = _valid(key, raw[key])
            if value is not None:
                out[key] = value
    return out


def merge(current, values):
    """``current`` avec les réglages de ``values`` : une clé inconnue ou
    une valeur hors bornes est refusée (KernelError), rien n'est changé."""
    from engine.kernel import KernelError
    out = normalize(current)
    for key, value in (values or {}).items():
        if key not in DEFAULTS:
            raise KernelError("propriété du document inconnue : {}".format(key))
        checked = _valid(key, value)
        if checked is None:
            raise KernelError("valeur invalide pour {} : {}".format(key, value))
        out[key] = checked
    return out


def mesh_settings(options):
    """Ce que la qualité demande : (écart des faces, angle ou None, écart
    des arêtes)."""
    face, angle = QUALITY[normalize(options)["quality"]]
    return face, angle, face / 2
