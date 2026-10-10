"""Surfaces et courbes : extrusion, révolution, lissage, couture, courbe 3D.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class SurfaceMixin:
    # -- surfaces et courbes ----------------------------------------------

    #: Objets document-level exposés dans la section Surfaces de l'arbre.
    #: Les PartDesign::* dérivent aussi de Part::Feature — filtre exact.
    _SURFACE_TYPE_IDS = frozenset({
        "Part::Feature", "Part::Extrusion", "Part::Revolution",
        "Part::Loft", "Part::Offset",
    })

    def _add_surface(self, shape, label):
        """Surface figée (Part::Feature) — couture, courbe 3D, legacy."""
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Shape = shape
        feature.Label = label
        doc.recompute()
        return self.get_tree()

    def _add_part_surface(self, type_id, label, configure):
        """Crée un objet Part paramétrique natif ; purge si le recompute
        échoue — pas d'entrée cassée dans l'arbre."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        doc = self._require_doc()
        obj = doc.addObject(type_id, "Surface")
        obj.Label = label
        try:
            configure(obj)
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(obj.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def _surface_source(self, sketch):
        from engine.kernel import KernelError
        sk = (self._get_sketch(sketch) if sketch is not None
              else self._latest_sketch())
        if not sk.Shape.Edges:
            raise KernelError("l'esquisse est vide")
        return sk

    def _surface_sketch_objects(self, obj):
        """Esquisses sources d'une surface paramétrique Part."""
        sketches = []
        if obj.TypeId == "Part::Extrusion":
            base = getattr(obj, "Base", None)
            if base is not None and base.TypeId == "Sketcher::SketchObject":
                sketches.append(base)
        elif obj.TypeId == "Part::Revolution":
            source = getattr(obj, "Source", None)
            if (source is not None
                    and source.TypeId == "Sketcher::SketchObject"):
                sketches.append(source)
        elif obj.TypeId == "Part::Loft":
            for section in getattr(obj, "Sections", None) or []:
                if (section is not None
                        and section.TypeId == "Sketcher::SketchObject"):
                    sketches.append(section)
        return sketches

    def _surface_tree_entry(self, obj, order_of=None, known_names=None):
        """Entrée d'arbre d'une surface.

        ``known_names`` : noms des nœuds dessinables du payload, pour
        filtrer les arêtes comme le fait ``entry()`` côté fonctions. Passé
        par l'appelant — ne pas le recalculer par surface.
        """
        from engine.kernel import label_for_type
        sketches = self._surface_sketch_objects(obj)
        order_of = order_of if order_of is not None else {}
        known_names = known_names if known_names is not None else set()

        def wire(item, source):
            return self._annotate_tree_links(item, source, known_names)

        entry = {
            "name": obj.Name,
            "label": obj.Label,
            "type": obj.TypeId,
            "sketches": [sk.Name for sk in sketches],
            "order": order_of.get(obj.Name, -1),
        }
        wire(entry, obj)
        # Couture / courbe / fichiers legacy : pas d'objet paramétrique.
        if obj.TypeId == "Part::Feature":
            entry["static"] = True
        graph = self._tree_graph_payload(obj)
        if graph is not None:
            entry["graph"] = graph
        if sketches:
            entry["children"] = [wire({
                "name": sk.Name,
                "label": sk.Label,
                "kind": label_for_type(sk.TypeId, self.lang),
                "type": sk.TypeId,
                "error": "Invalid" in (sk.State or ()),
                "order": order_of.get(sk.Name, -1),
                "definition": self._sketch_definition(sk),
            }, sk) for sk in sketches]
        entry["rolled_back"] = self._is_rolled_back(obj)
        return entry

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

    def _get_surface(self, name):
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(name))
        if obj is None or obj.TypeId not in self._SURFACE_TYPE_IDS:
            raise KernelError("surface inconnue : {}".format(name))
        return obj

    def surface_sew(self, surfaces):
        """Coudre des surfaces ; reste figé (pas d'objet Part paramétrique
        natif pour la couture). Si la peau est fermée, elle devient un
        solide — le geste « coudre puis solidifier » de SolidWorks."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        if not isinstance(surfaces, (list, tuple)) or len(surfaces) < 2:
            raise KernelError("coudre demande au moins deux surfaces")
        faces = []
        for name in surfaces:
            faces.extend(self._get_surface(name).Shape.Faces)
        if not faces:
            raise KernelError("aucune face à coudre")
        try:
            shell = Part.makeShell(faces)
            shell.sewShape()
            if shell.isClosed():
                return self._add_surface(Part.makeSolid(shell),
                                         "Solide cousu")
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self._add_surface(shell, "Surface cousue")

    def surface_thicken(self, surface, thickness):
        """Épaissir une surface en solide — Part::Offset paramétrique."""
        from engine.kernel import KernelError
        src = self._get_surface(surface)
        thickness = float(thickness)
        if thickness == 0:
            raise KernelError("l'épaisseur ne peut pas être nulle")

        def configure(obj):
            obj.Source = src
            obj.Value = thickness
            obj.Fill = True

        return self._add_part_surface(
            "Part::Offset", "Épaississement", configure)

    def add_curve3d(self, points, spline=True):
        """Courbe 3D par points — le repli esquisse 3D : une trajectoire
        pour le balayage (B-spline interpolée, ou polyligne)."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        App = self._app()
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            raise KernelError("une courbe demande au moins deux points")
        vectors = []
        for p in points:
            try:
                x, y, z = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            vectors.append(App.Vector(x, y, z))
        try:
            shape = self._wire_through_points(
                vectors, spline=bool(spline), closed=False)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self._add_surface(shape, "Courbe 3D")

    def _wire_through_points(self, vectors, *, spline=True, closed=False):
        """Fil 3D par des points — interpolation B-spline, ou polyligne.

        Un FIL, pas une arête nue : le balayage exige un TopoDS_Wire
        (vu sur 1.1.3). La courbe **passe par** les points.
        """
        import Part
        if closed:
            if spline and len(vectors) >= 3:
                curve = Part.BSplineCurve()
                curve.interpolate(vectors, PeriodicFlag=True)
                return Part.Wire([curve.toShape()])
            return Part.makePolygon(vectors, True)
        if spline and len(vectors) >= 3:
            curve = Part.BSplineCurve()
            curve.interpolate(vectors)
            return Part.Wire([curve.toShape()])
        return Part.makePolygon(vectors)

    def _ensure_wire(self, shape):
        from engine.kernel import KernelError
        import Part
        if getattr(shape, "ShapeType", None) == "Wire":
            return shape
        edges = list(getattr(shape, "Edges", ()) or [])
        if not edges:
            raise KernelError("la courbe n'a pas d'arête")
        return Part.Wire(edges)
