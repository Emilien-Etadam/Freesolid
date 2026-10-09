"""État de définition des entités d'une esquisse — module pur.

Chaque entité est « sous-contrainte » (elle peut encore bouger),
« contrainte » (entièrement définie) ou « sur-contrainte » (une contrainte
qui la touche est redondante ou en conflit). Le client en tire la couleur.

Aucun import FreeCAD : kernel.py lit le solveur et passe les listes brutes.
"""

UNDER = "under"
FULL = "full"
OVER = "over"


def entity_status(geo_count, dependent, constraint_geos, conflicting,
                  redundant):
    """État de chaque géométrie 0..geo_count-1.

    dependent : [(geo, pos)] de getGeometryWithDependentParameters() —
        les géométries qui ont encore un paramètre libre.
    constraint_geos : pour chaque contrainte (index 0), la liste des
        géométries qu'elle touche (les négatives — axes, externes — sont
        ignorées).
    conflicting, redundant : numéros de contraintes **à partir de 1**,
        comme les rend Sketcher.
    """
    status = [FULL] * max(int(geo_count), 0)
    for item in dependent or ():
        geo = item[0] if isinstance(item, (tuple, list)) else item
        if 0 <= geo < len(status):
            status[geo] = UNDER
    bad = set(conflicting or ()) | set(redundant or ())
    for number in bad:
        index = int(number) - 1
        if not 0 <= index < len(constraint_geos):
            continue
        for geo in constraint_geos[index]:
            if geo is not None and 0 <= geo < len(status):
                status[geo] = OVER
    return status


def sketch_definition(status, solver_code=0):
    """Résumé de l'esquisse : over si le solveur se plaint ou si une entité
    est sur-contrainte, under si une entité est libre, full sinon."""
    if solver_code not in (0, None) or OVER in status:
        return OVER
    if UNDER in status:
        return UNDER
    return FULL
