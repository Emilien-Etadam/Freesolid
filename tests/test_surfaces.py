"""Utilitaires de surface du noyau — pur Python, sans FreeCAD."""

from engine import surfaces


class _Surf:
    def __init__(self, type_id=""):
        self.TypeId = type_id


class _Face:
    def __init__(self, type_id="", domain=True):
        self.Surface = _Surf(type_id)
        self._domain = domain

    def isPartOfDomain(self, u, v):
        return self._domain


def test_is_bspline_surface_by_typeid():
    assert surfaces.is_bspline_surface(_Face("Part::GeomBSplineSurface"))
    assert surfaces.is_bspline_surface(_Face("Part::GeomBezierSurface"))
    assert not surfaces.is_bspline_surface(_Face("Part::GeomCylinder"))
    assert not surfaces.is_bspline_surface(_Face(""))

    class _NoSurf:
        Surface = None

    assert not surfaces.is_bspline_surface(_NoSurf())
    assert not surfaces.is_bspline_surface(None)


def test_project_uv_returns_parameter_and_domain(monkeypatch):
    class _ParamSurf:
        def parameter(self, point):
            assert point == (1.0, 2.0, 3.0)
            return (0.25, 0.75)

    class _ParamFace:
        Surface = _ParamSurf()

        def isPartOfDomain(self, u, v):
            return u == 0.25 and v == 0.75

    monkeypatch.setattr(
        surfaces, "_vector", lambda face, x, y, z: (x, y, z))
    u, v, on_domain = surfaces.project_uv(_ParamFace(), 1.0, 2.0, 3.0)
    assert (u, v, on_domain) == (0.25, 0.75, True)


def test_project_uv_outside_domain(monkeypatch):
    class _ParamSurf:
        def parameter(self, point):
            return (9.0, 9.0)

    class _ParamFace:
        Surface = _ParamSurf()

        def isPartOfDomain(self, u, v):
            return False

    monkeypatch.setattr(
        surfaces, "_vector", lambda face, x, y, z: (x, y, z))
    _u, _v, on_domain = surfaces.project_uv(_ParamFace(), 0.0, 0.0, 0.0)
    assert on_domain is False
