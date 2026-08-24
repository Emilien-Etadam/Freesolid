"""Utilitaires de surface — B-spline et projection ``(u, v)``.

Service du noyau, consommé par la tessellation (``Kernel._face_mesh``)
et par tout plugin qui ancre un objet sur une face. Pas d'import FreeCAD
au niveau module.
"""

from __future__ import annotations

_SPLINE_TYPE_IDS = frozenset({
    "Part::GeomBSplineSurface",
    "Part::GeomBezierSurface",
})


def is_bspline_surface(face) -> bool:
    """True si la face se re-paramétrise quand ses pôles bougent."""
    surface = getattr(face, "Surface", None)
    type_id = getattr(surface, "TypeId", "") if surface is not None else ""
    return type_id in _SPLINE_TYPE_IDS


def project_uv(face, x, y, z):
    """Point monde → ``(u, v, sur_domaine)``.

    ``Surface.parameter`` est la seule voie (sonde Q1) : les trois
    méthodes testées rendaient des ``(u, v)`` identiques.
    """
    point = _vector(face, x, y, z)
    u, v = face.Surface.parameter(point)
    on_domain = True
    checker = getattr(face, "isPartOfDomain", None)
    if checker is not None:
        try:
            on_domain = bool(checker(u, v))
        except TypeError:
            on_domain = bool(checker((u, v)))
    return float(u), float(v), on_domain


def _app():
    import FreeCAD as App
    return App


def _vector(face, x, y, z):
    App = _app()
    return App.Vector(float(x), float(y), float(z))
