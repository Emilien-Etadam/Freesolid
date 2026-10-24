"""Surfaces depuis une esquisse : extrusion, révolution, lissage, plane,
balayage, décalage.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class SurfaceSketchMixin:
    def surface_extrude(self, length, sketch=None):
        """Surface extrudée paramétrique — profil ouvert OK."""
        sk = self._surface_source(sketch)
        App = self._app()
        normal = sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        length = float(length)

        def configure(obj):
            obj.Base = sk
            obj.DirMode = "Custom"
            obj.Dir = normal
            obj.LengthFwd = length
            obj.Solid = False

        return self._add_part_surface(
            "Part::Extrusion", "Surface extrudée", configure)

    def surface_revolve(self, angle=360.0, sketch=None):
        """Surface de révolution paramétrique — axe vertical d'esquisse."""
        sk = self._surface_source(sketch)
        App = self._app()
        base = sk.Placement.Base
        axis = sk.Placement.Rotation.multVec(App.Vector(0, 1, 0))
        angle = float(angle)

        def configure(obj):
            obj.Source = sk
            obj.Axis = axis
            obj.Base = base
            obj.Angle = angle
            obj.Solid = False

        return self._add_part_surface(
            "Part::Revolution", "Surface de révolution", configure)

    def surface_loft(self, sketches):
        """Surface lissée paramétrique entre plusieurs profils."""
        from engine.kernel import KernelError
        if not isinstance(sketches, (list, tuple)) or len(sketches) < 2:
            raise KernelError("une surface lissée demande au moins deux "
                              "profils")
        sections = []
        for name in sketches:
            sk = self._get_sketch(str(name))
            if not sk.Shape.Edges:
                raise KernelError("esquisse vide : {}".format(name))
            sections.append(sk)

        def configure(obj):
            obj.Sections = sections
            obj.Solid = False
            obj.Ruled = False

        return self._add_part_surface(
            "Part::Loft", "Surface lissée", configure)

    def surface_planar(self, sketch=None):
        """Surface plane bornée par un contour fermé d'esquisse."""
        sk = self._surface_source(sketch)

        def configure(obj):
            obj.Sources = [sk]

        return self._add_part_surface("Part::Face", "Surface plane", configure)

    def surface_sweep(self, profile, spine):
        """Surface balayée : un profil (ouvert ou fermé) suit une
        trajectoire — esquisse ou spline 3D."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        section = self._get_sketch(str(profile))
        path = doc.getObject(str(spine))
        if (path is None or not getattr(path, "Shape", None)
                or not path.Shape.Edges or path.Shape.Faces):
            raise KernelError(
                "trajectoire inconnue : {} (esquisse ou courbe 3D)".format(
                    spine))
        if section.Name == path.Name:
            raise KernelError("profil et trajectoire doivent être "
                              "différents")

        def configure(obj):
            obj.Sections = [section]
            obj.Spine = (path, ["Edge%d" % (i + 1)
                                for i in range(len(path.Shape.Edges))])
            obj.Solid = False
            obj.Frenet = True

        return self._add_part_surface(
            "Part::Sweep", "Surface balayée", configure)

    def surface_offset(self, surface, distance):
        """Surface décalée — la peau recopiée à distance, sans remplir."""
        from engine.kernel import KernelError
        src = self._get_surface(surface)
        if not src.Shape.Faces:
            raise KernelError("décaler demande une surface, pas une courbe")
        distance = float(distance)

        def configure(obj):
            obj.Source = src
            obj.Value = distance
            obj.Fill = False

        label = "Surface décalée" if distance else "Copie de surface"
        return self._add_part_surface("Part::Offset", label, configure)
