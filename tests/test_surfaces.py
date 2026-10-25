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


def test_is_plane_surface_by_typeid():
    assert surfaces.is_plane_surface(_Face("Part::GeomPlane"))
    assert not surfaces.is_plane_surface(_Face("Part::GeomCylinder"))
    assert not surfaces.is_plane_surface(_Face("Part::GeomBSplineSurface"))
    assert not surfaces.is_plane_surface(None)


def test_surface_uv_skips_domain_check(monkeypatch):
    class _ParamSurf:
        def parameter(self, point):
            return (0.25, 0.75)

    class _ParamFace:
        Surface = _ParamSurf()

        def isPartOfDomain(self, u, v):
            raise AssertionError("la tessellation ne teste pas le domaine")

    monkeypatch.setattr(
        surfaces, "_vector", lambda face, x, y, z: (x, y, z))
    assert surfaces.surface_uv(_ParamFace(), 1.0, 2.0, 3.0) == (0.25, 0.75)


class _Vec:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.Length = (x * x + y * y + z * z) ** 0.5

    def normalize(self):
        return _Vec(self.x / self.Length, self.y / self.Length,
                    self.z / self.Length)


class _MeshFace:
    """Trois sommets ; la normale dépend de u (faux cylindre) sauf plan."""

    def __init__(self, type_id):
        self.Surface = _MeshSurf(type_id)
        self.normal_calls = 0

    def tessellate(self, deviation):
        return [_Vec(0, 0, 0), _Vec(1, 0, 0), _Vec(0, 1, 0)], [(0, 1, 2)]

    def normalAt(self, u, v):
        self.normal_calls += 1
        if self.Surface.TypeId == "Part::GeomPlane":
            return _Vec(0, 0, 2)
        return _Vec(1, u, 0)

    def isPartOfDomain(self, u, v):
        raise AssertionError("la tessellation ne teste pas le domaine")


class _MeshSurf(_Surf):
    def parameter(self, point):
        return (float(point[0]), float(point[1]))


def test_face_mesh_plane_normal_once(monkeypatch):
    from engine.kernel import Kernel

    monkeypatch.setattr(
        surfaces, "_vector", lambda face, x, y, z: (x, y, z))
    plane = _MeshFace("Part::GeomPlane")
    (face_id, points, triangles, normals), spline = Kernel._face_mesh(
        None, plane, 4, 0.1)
    assert (face_id, triangles, spline) == (4, [(0, 1, 2)], False)
    assert normals == [(0.0, 0.0, 1.0)] * 3
    assert plane.normal_calls == 1

    other = _MeshFace("Part::GeomCylinder")
    (_id, _pts, _tri, normals), _spline = Kernel._face_mesh(
        None, other, 0, 0.1)
    assert other.normal_calls == 3
    tilted = _Vec(1, 1, 0).normalize()
    assert normals[0] == (1.0, 0.0, 0.0)
    assert normals[1] == (tilted.x, tilted.y, 0.0)
