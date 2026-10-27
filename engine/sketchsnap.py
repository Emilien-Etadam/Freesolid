"""Accrochages d'un tracé d'esquisse : ce que l'interface a accroché.

L'interface voit le curseur : c'est elle qui décide qu'un bout de ligne
tombe sur le centre d'un cercle. Elle le dit dans ``snaps`` ; le moteur
pose ces relations dans la même opération (un seul Ctrl+Z). Un point que
``snaps`` ne nomme pas coïncide encore avec un point existant exactement
au même endroit (la fin de la ligne précédente d'une chaîne), et une
ligne exactement horizontale ou verticale le reste : c'est le moteur qui
le voit, l'état de l'interface pouvant avoir un tracé de retard.

Pur Python — sans FreeCAD — pour être testé en CI : ce module vérifie la
forme de ``snaps`` ; les relations sont construites par ``sketch.py``.

Une cible est un point d'esquisse ``{"geo": n, "point": p}``, avec la
numérotation de Sketcher déjà employée par le protocole : 1 départ,
2 fin, 3 centre ; ``geo`` -1 et ``point`` 1 désignent l'origine, -3, -4…
les références externes.
"""

#: Rôles acceptés par chaque tracé : ``point`` (une cible) ou ``points``
#: (une liste de cibles posées sur la courbe).
ROLES = {
    "sketch_add_line": {"start": "point", "end": "point"},
    "sketch_add_point": {"at": "point"},
    "sketch_add_circle": {"center": "point", "on": "points"},
    "sketch_add_arc": {"center": "point", "start": "point", "end": "point",
                       "on": "points"},
    "sketch_add_rectangle": {"corner1": "point", "corner2": "point",
                             "center": "point"},
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


def snap_positions(type_id):
    """Points d'une géométrie qu'une cible peut nommer."""
    return _POSITIONS.get(type_id, (1, 2))


def _target(role, value):
    from engine.kernel import KernelError
    if not isinstance(value, dict) or set(value) != {"geo", "point"}:
        raise KernelError("accrochage « {} » : cible invalide".format(role))
    geo, point = value["geo"], value["point"]
    if (not all(isinstance(v, int) and not isinstance(v, bool)
                for v in (geo, point)) or point not in (1, 2, 3)):
        raise KernelError("accrochage « {} » : cible invalide".format(role))
    return geo, point


def parse_snaps(op, snaps):
    """``snaps`` vérifié : ``{rôle: (geo, point) | [(geo, point)…]}``.
    Un rôle absent ou ``None`` n'est pas accroché."""
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
        if kind == "point":
            parsed[role] = _target(role, value)
        else:
            if not isinstance(value, list):
                raise KernelError(
                    "accrochage « {} » : cible invalide".format(role))
            parsed[role] = [_target(role, item) for item in value]
    return parsed


def targets_of(parsed):
    """``(rôle, (geo, point))`` de chaque cible, dans l'ordre."""
    for role, value in parsed.items():
        for target in (value if isinstance(value, list) else [value]):
            yield role, target
