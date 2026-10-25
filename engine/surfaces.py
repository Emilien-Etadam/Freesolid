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


def _surface_type(face) -> str:
    surface = getattr(face, "Surface", None)
    return getattr(surface, "TypeId", "") if surface is not None else ""


def is_bspline_surface(face) -> bool:
    """True si la face se re-paramétrise quand ses pôles bougent."""
    return _surface_type(face) in _SPLINE_TYPE_IDS


def is_plane_surface(face) -> bool:
    """True si la face porte un plan : sa normale est la même partout."""
    return _surface_type(face) == "Part::GeomPlane"


def surface_uv(face, x, y, z):
    """Point monde → ``(u, v)`` sur la surface porteuse, sans dire s'il
    tombe dans le domaine de la face.

    Pour la tessellation : un sommet du maillage est déjà sur la face, et
    ``isPartOfDomain`` coûtait les deux tiers du calcul des normales.
    ``Surface.parameter`` est la seule voie (sonde Q1) : les trois
    méthodes testées rendaient des ``(u, v)`` identiques.
    """
    point = _vector(face, x, y, z)
    u, v = face.Surface.parameter(point)
    return float(u), float(v)


def project_uv(face, x, y, z):
    """Point monde → ``(u, v, sur_domaine)`` (voir ``surface_uv``)."""
    u, v = surface_uv(face, x, y, z)
    on_domain = True
    checker = getattr(face, "isPartOfDomain", None)
    if checker is not None:
        try:
            on_domain = bool(checker(u, v))
        except TypeError:
            on_domain = bool(checker((u, v)))
    return u, v, on_domain


def _app():
    import FreeCAD as App
    return App


def _vector(face, x, y, z):
    App = _app()
    return App.Vector(float(x), float(y), float(z))
