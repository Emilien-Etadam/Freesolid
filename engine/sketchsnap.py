"""Accrochages d'un tracé d'esquisse : ce que l'interface a accroché.

L'interface voit le curseur : c'est elle qui décide qu'un bout de ligne
tombe sur le centre d'un cercle. Elle le dit dans ``snaps`` ; le moteur
pose ces relations dans la même opération (un seul Ctrl+Z). Un point que
``snaps`` ne nomme pas coïncide encore avec un point existant exactement
au même endroit (la fin de la ligne précédente d'une chaîne), et une
ligne exactement horizontale ou verticale le reste : c'est le moteur qui
le voit, l'état de l'interface pouvant avoir un tracé de retard.

Pur Python — sans FreeCAD — pour être testé en CI : ce module vérifie la
forme de ``snaps`` et dit quelles relations posent un point sur sa
cible ; ``sketch.py`` les crée.

Une cible, avec la numérotation de Sketcher déjà employée par le
protocole (1 départ, 2 fin, 3 centre ; ``geo`` -1 et ``point`` 1
l'origine, -3, -4… les références externes) :

- ``{"geo": n, "point": p}`` : un point d'esquisse (coïncidence) ;
- ``{"kind": "midpoint", "geo": n}`` : le milieu d'une ligne ou d'un arc ;
- ``{"kind": "quadrant", "geo": n, "quadrant": q}`` : un quadrant d'un
  cercle ou d'un arc, 0 à droite du centre puis dans le sens trigo ;
- ``{"kind": "on", "geo": n}`` : n'importe où sur une courbe ;
- ``{"kind": "intersection", "geos": [a, b]}`` : le croisement de deux
  courbes.
"""

from collections import namedtuple

#: Rôles acceptés par chaque tracé : ``target`` (une cible), ``point``
#: (un point d'esquisse seulement) ou ``points`` (une liste de points
#: d'esquisse posés sur la courbe tracée).
ROLES = {
    "sketch_add_line": {"start": "target", "end": "target"},
    "sketch_add_point": {"at": "target"},
    "sketch_add_circle": {"center": "target", "on": "points"},
    "sketch_add_arc": {"center": "target", "start": "target",
                       "end": "target", "on": "points"},
    "sketch_add_rectangle": {"corner1": "target", "corner2": "target",
                             "center": "point"},
}

#: Une cible vérifiée. ``geo`` : la géométrie visée (la première des deux
#: d'une intersection, ``other`` la seconde) ; ``point`` pour un point
#: d'esquisse, ``quadrant`` pour un quadrant.
Target = namedtuple("Target", "kind geo point quadrant other",
                    defaults=(None, None, None))

#: Clés de chaque forme de cible, ``kind`` compris.
_KEYS = {
    "midpoint": {"kind", "geo"},
    "quadrant": {"kind", "geo", "quadrant"},
    "on": {"kind", "geo"},
    "intersection": {"kind", "geos"},
}

#: Points qu'un accrochage peut viser, par type de géométrie ; les
#: autres courbes (splines, coniques) n'offrent que leurs deux bouts.
_POSITIONS = {
    "Part::GeomPoint": (1,),
    "Part::GeomLineSegment": (1, 2),
    "Part::GeomCircle": (3,),
    "Part::GeomArcOfCircle": (1, 2, 3),
    "Part::GeomEllipse": (3,),
    "Part::GeomArcOfEllipse": (1, 2, 3),
}

_LINE = "Part::GeomLineSegment"
_ARC = "Part::GeomArcOfCircle"
_ROUND = ("Part::GeomCircle", _ARC)


def snap_positions(type_id):
    """Points d'une géométrie qu'une cible peut nommer."""
    return _POSITIONS.get(type_id, (1, 2))


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _target(role, value, points_only):
    from engine.kernel import KernelError

    def invalid():
        return KernelError("accrochage « {} » : cible invalide".format(role))

    if not isinstance(value, dict):
        raise invalid()
    if set(value) == {"geo", "point"}:
        if not (_int(value["geo"]) and value["point"] in (1, 2, 3)
                and _int(value["point"])):
            raise invalid()
        return Target("point", value["geo"], point=value["point"])
    kind = value.get("kind")
    if points_only or kind not in _KEYS or set(value) != _KEYS[kind]:
        raise invalid()
    if kind == "intersection":
        geos = value["geos"]
        if (not isinstance(geos, list) or len(geos) != 2
                or not all(_int(g) for g in geos) or geos[0] == geos[1]):
            raise invalid()
        return Target(kind, geos[0], other=geos[1])
    if not _int(value["geo"]):
        raise invalid()
    if kind == "quadrant":
        if value["quadrant"] not in (0, 1, 2, 3) or not _int(value["quadrant"]):
            raise invalid()
        return Target(kind, value["geo"], quadrant=value["quadrant"])
    return Target(kind, value["geo"])


def parse_snaps(op, snaps):
    """``snaps`` vérifié : ``{rôle: Target | [Target…]}``. Un rôle absent
    ou ``None`` n'est pas accroché. Les rôles ``point`` et ``points``
    veulent un point d'esquisse : le centre d'un rectangle est tenu
    symétrique autour de lui, un point posé sur la courbe tracée en est
    un — un milieu ou un croisement n'a pas de point."""
    from engine.kernel import KernelError
    roles = ROLES[op]
    if not isinstance(snaps, dict):
        raise KernelError("accrochage inconnu : {}".format(snaps))
    parsed = {}
    for role, value in snaps.items():
        kind = roles.get(role)
        if kind is None:
            raise KernelError("accrochage inconnu : {}".format(role))
        if value is None:
            continue
        if kind != "points":
            parsed[role] = _target(role, value, kind == "point")
        else:
            if not isinstance(value, list):
                raise KernelError(
                    "accrochage « {} » : cible invalide".format(role))
            parsed[role] = [_target(role, item, True) for item in value]
    return parsed


def targets_of(parsed):
    """``(rôle, Target)`` de chaque cible, dans l'ordre."""
    for role, value in parsed.items():
        for target in (value if isinstance(value, list) else [value]):
            yield role, target


def geos_of(target):
    """Les géométries qu'une cible vise."""
    if target.kind == "intersection":
        return (target.geo, target.other)
    return (target.geo,)


def fits(target, type_of):
    """La cible convient-elle à ce qu'elle vise ? ``type_of(geo)`` : le
    TypeId d'une géométrie. Un point nomme un point qu'elle a ; un milieu,
    une ligne ou un arc ; un quadrant, un cercle ou un arc ; « sur » et
    un croisement, des courbes."""
    if target.kind == "point":
        return target.point in snap_positions(type_of(target.geo))
    if target.kind == "midpoint":
        return type_of(target.geo) in (_LINE, _ARC)
    if target.kind == "quadrant":
        return type_of(target.geo) in _ROUND
    return all(type_of(g) != "Part::GeomPoint" for g in geos_of(target))


def relations(target, gid, pos, type_of):
    """Les relations qui posent le point ``(gid, pos)`` sur ``target`` :
    les arguments de ``Sketcher.Constraint``, une relation par tuple.

    Le milieu d'un arc n'a pas de relation dans Sketcher : le point est
    seulement posé sur l'arc."""
    if target.kind == "point":
        return [("Coincident", gid, pos, target.geo, target.point)]
    if target.kind == "midpoint" and type_of(target.geo) == _LINE:
        return [("Symmetric", target.geo, 1, target.geo, 2, gid, pos)]
    if target.kind == "quadrant":
        axis = "Horizontal" if target.quadrant % 2 == 0 else "Vertical"
        return [("PointOnObject", gid, pos, target.geo),
                (axis, gid, pos, target.geo, 3)]
    return [("PointOnObject", gid, pos, g) for g in geos_of(target)]
