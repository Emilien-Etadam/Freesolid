"""Prolonger et ajuster une surface, et leur réédition.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


def Part_Face():  # noqa: N802 — le type Part.Face, importé à l'appel
    import Part
    return Part.Face


class SurfaceExtendMixin:
    @staticmethod
    def _extend_sides(face, edge_shape):
        """Côtés (u−, u+, v−, v+) d'une face que touche une arête — tous
        si ``edge_shape`` est None."""
        sides = ("UNeg", "UPos", "VNeg", "VPos")
        if edge_shape is None:
            return sides
        u0, u1, v0, v1 = face.ParameterRange
        mid = edge_shape.valueAt(
            (edge_shape.FirstParameter + edge_shape.LastParameter) / 2)
        u, v = face.Surface.parameter(mid)
        gaps = (abs(u - u0), abs(u - u1), abs(v - v0), abs(v - v1))
        return (sides[gaps.index(min(gaps))],)

    @staticmethod
    def _extend_ratios(face, distance, sides):
        """Distance en mm → fractions de l'étendue paramétrique, mesurées
        sur l'isocourbe du milieu (ce que ``Surface::Extend`` attend)."""
        u0, u1, v0, v1 = face.ParameterRange
        along_u = face.Surface.vIso((v0 + v1) / 2).length(u0, u1)
        along_v = face.Surface.uIso((u0 + u1) / 2).length(v0, v1)
        ratios = {}
        for side in sides:
            span = along_u if side.startswith("U") else along_v
            ratios[side] = distance / span if span > 1e-9 else 0.0
        return ratios

    def surface_extend(self, surface, distance, edge=None):
        """Prolonger une surface d'une distance — au-delà d'un bord choisi,
        ou de tous ses bords."""
        from engine.kernel import KernelError
        import Surface  # noqa: F401 — enregistre Surface::Extend
        src = self._get_surface(surface)
        faces = src.Shape.Faces
        if not faces:
            raise KernelError("prolonger demande une surface, pas une courbe")
        distance = float(distance)
        if distance <= 0:
            raise KernelError("la distance doit être positive")
        face_index, edge_shape = 0, None
        if edge is not None:
            edge = int(edge)  # base 0, comme les arêtes de la vue
            if edge < 0 or edge >= len(src.Shape.Edges):
                raise KernelError("arête inconnue : {}".format(edge))
            edge_shape = src.Shape.Edges[edge]
            owners = src.Shape.ancestorsOfType(edge_shape, Part_Face())
            for i, face in enumerate(faces):
                if any(face.isSame(owner) for owner in owners):
                    face_index = i
                    break
        face = faces[face_index]
        sides = self._extend_sides(face, edge_shape)
        ratios = self._extend_ratios(face, distance, sides)

        def configure(obj):
            obj.Face = (src, ["Face%d" % (face_index + 1)])
            obj.ExtendUSymetric = False
            obj.ExtendVSymetric = False
            for side in ("UNeg", "UPos", "VNeg", "VPos"):
                setattr(obj, "Extend" + side, ratios.get(side, 0.0))
            # Stocké en base 1 : 0 veut dire « tous les bords ».
            self._stamp(obj, distance=distance,
                        edge=0 if edge is None else edge + 1)

        return self._add_part_surface(
            "Surface::Extend", "Surface prolongée", configure)

    def surface_trim(self, surface, tool, point=None, tool_point=None):
        """Ajuster une surface par une autre : la découpe garde la partie
        la plus proche du point cliqué (la plus grande sans point).
        ``tool_point`` : ajustement mutuel — l'outil est aussi coupé par la
        surface, la partie la plus proche de ce point est gardée."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        doc = self._require_doc()
        src = self._get_surface(surface)
        cutter = self._get_surface(tool)
        if src.Name == cutter.Name:
            raise KernelError("la surface et l'outil doivent être différents")
        if not src.Shape.Faces or not cutter.Shape.Faces:
            raise KernelError("ajuster demande deux surfaces")
        jobs = [(src, cutter, point)]
        if tool_point is not None:
            jobs.append((cutter, src, tool_point))
        plans = []
        for base, knife, at in jobs:
            pieces = self._trim_pieces(base.Shape, knife.Shape)
            if len(pieces) < 2:
                raise KernelError("l'outil ne coupe pas la surface"
                                  if base is src else
                                  "la surface ne coupe pas l'outil")
            plans.append((base, knife, self._nearest_piece(pieces, at)))
        created = []
        try:
            for base, knife, keep in plans:
                created += self._trim_objects(base, knife, keep)
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            for obj in reversed(created):
                try:
                    doc.removeObject(obj.Name)
                except Exception:
                    pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def _trim_objects(self, base, knife, keep):
        """Découpe (interne) + partie gardée, sans recalcul."""
        import BOPTools.SplitFeatures as split_features
        import CompoundTools.CompoundFilter as compound_filter
        slicer = split_features.makeSlice("Decoupe")
        slicer.Base = base
        slicer.Tools = [knife]
        slicer.Mode = "Split"
        self._mark_internal(slicer)
        kept = compound_filter.makeCompoundFilter("Surface")
        kept.Base = slicer
        kept.FilterType = "specific items"
        kept.items = str(keep)
        kept.Label = self._t("Surface ajustée")
        self._stamp(kept, kind="trim")
        return [slicer, kept]

    @staticmethod
    def _trim_pieces(shape, tool_shape):
        from BOPTools import SplitAPI
        return SplitAPI.slice(shape, [tool_shape], "Split").childShapes()

    @staticmethod
    def _nearest_piece(pieces, point):
        if point is None:
            areas = [p.Area for p in pieces]
            return areas.index(max(areas))
        import FreeCAD as App
        import Part
        x, y, z = (float(v) for v in point)
        vertex = Part.Vertex(App.Vector(x, y, z))
        gaps = [p.distToShape(vertex)[0] for p in pieces]
        return gaps.index(min(gaps))

    def edit_surface_extend(self, surface, distance, edge=None):
        """Rééditer un prolongement : distance (et bord) recalculés."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(surface))
        if obj is None or obj.TypeId != "Surface::Extend":
            raise KernelError("prolongement inconnu : {}".format(surface))
        src = obj.Face[0]
        distance = float(distance)
        if distance <= 0:
            raise KernelError("la distance doit être positive")
        face = src.Shape.Faces[int(obj.Face[1][0][4:]) - 1]
        edge_shape = (src.Shape.Edges[int(edge)]
                      if edge is not None else None)
        ratios = self._extend_ratios(
            face, distance, self._extend_sides(face, edge_shape))
        for side in ("UNeg", "UPos", "VNeg", "VPos"):
            setattr(obj, "Extend" + side, ratios.get(side, 0.0))
        self._stamp(obj, distance=distance,
                    edge=0 if edge is None else int(edge) + 1)
        self._recompute()
        return self.get_tree()

    def edit_surface_trim(self, surface, point=None):
        """Ajuster : changer la partie gardée — la plus proche d'un point,
        ou, sans point, la partie suivante (« garder l'autre partie »)."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(surface))
        if obj is None or getattr(obj, "FreeSolidKind", "") != "trim":
            raise KernelError("ajustement inconnu : {}".format(surface))
        pieces = obj.Base.Shape.childShapes()
        if point is not None:
            keep = self._nearest_piece(pieces, point)
        else:
            current = int(str(obj.items).split(";")[0] or 0)
            keep = (current + 1) % max(len(pieces), 1)
        obj.items = str(keep)
        self._recompute()
        return self.get_tree()
