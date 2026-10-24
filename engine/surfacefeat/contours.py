"""Surfaces par contour : remplissage (et ses bouchons), frontière,
réglée.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class SurfaceBoundaryMixin:
    def _boundary_links(self, boundary):
        """``[(objet, "EdgeN"), …]`` d'un contour : arêtes de surface, de
        courbe ou du corps actif, et esquisses entières."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        links = []
        for item in boundary or ():
            if not isinstance(item, dict):
                raise KernelError("arête de contour invalide : {}".format(item))
            if item.get("body"):
                obj = self._require_body()
            else:
                obj = doc.getObject(str(item.get("name", "")))
            if obj is None or not getattr(obj, "Shape", None):
                raise KernelError("objet inconnu : {}".format(item.get("name")))
            count = len(obj.Shape.Edges)
            edge = item.get("edge")
            if edge is None:
                links.extend((obj, "Edge%d" % (i + 1)) for i in range(count))
                continue
            edge = int(edge)  # base 0, comme les arêtes de la vue
            if edge < 0 or edge >= count:
                raise KernelError("arête inconnue : {} de {}".format(
                    edge, obj.Label))
            links.append((obj, "Edge%d" % (edge + 1)))
        if not links:
            raise KernelError("sélectionnez les arêtes du contour")
        return links

    def surface_fill(self, boundary, tangent=False):
        """Surface de remplissage : une peau tendue sur un contour fermé
        d'arêtes (bords de surfaces, courbes, esquisses, arêtes du solide).
        ``tangent`` : la peau prolonge en tangence la face que borde chaque
        arête (bord libre d'une surface ou arête du solide)."""
        from engine.kernel import KernelError
        import Surface  # noqa: F401 — enregistre Surface::Filling
        links = self._boundary_links(boundary)
        faces = [self._adjacent_face(obj, sub) if tangent else ""
                 for obj, sub in links]
        triples = [(obj.Name, sub, face)
                   for (obj, sub), face in zip(links, faces)]
        closed = any(obj.Shape.Edges[int(sub[4:]) - 1].isClosed()
                     for obj, sub in links)
        if tangent and closed and all(faces):
            # Arête fermée + tangence : les demi-arêtes auxiliaires n'ont
            # pas de trace sur la face voisine, et le solveur plante dessus
            # (SIGSEGV dans GeomPlate sous OCCT 7.9). Bouchon tangent direct.
            return self._tangent_cap(triples)
        # Une arête fermée seule (bout de tube) : le noyau ne sait pas la
        # remplir. Un objet auxiliaire la coupe en deux moitiés,
        # recalculé avec sa source (tangence : voir plus haut).
        # Sans tangence sur les demi-arêtes : elles n'ont pas de trace sur
        # la face voisine.
        links, faces = self._split_closed_links(
            links, [""] * len(links) if closed else faces)

        def configure(obj):
            obj.BoundaryEdges = links
            if any(faces):
                obj.BoundaryFaces = faces
                obj.BoundaryOrder = [1 if face else 0 for face in faces]

        try:
            return self._add_part_surface(
                "Surface::Filling", "Surface de remplissage", configure)
        except KernelError:
            if not tangent or not all(face for _, _, face in triples):
                raise
        # Le solveur ne tient pas la tangence (faces voisines
        # perpendiculaires) : bouchon B-spline construit.
        return self._tangent_cap(triples)

    def _tangent_cap(self, triples):
        """Bouchon tangent par sa deuxième rangée de pôles, recalculé avec
        ses sources."""
        stamps = {"capedges": ";".join(":".join(t) for t in triples)}
        shape = self._cap_shape(stamps["capedges"])
        return self._add_frozen_surface(shape, "Surface de remplissage",
                                        stamps)

    def _cap_shape(self, spec):
        """Bouchon tangent sur un contour fermé : B-spline périodique dont
        la première rangée de pôles suit le contour et la deuxième part
        dans le prolongement de la face voisine (tangence exacte) ; elle se
        referme sur un sommet."""
        from engine.kernel import KernelError
        import FreeCAD as App
        import Part
        doc = self._require_doc()
        pairs = []
        for item in str(spec).split(";"):
            name, edge_name, face_name = item.split(":")
            obj = doc.getObject(name)
            if obj is None:
                raise KernelError("objet inconnu : {}".format(name))
            shape = obj.Shape
            pairs.append((shape.Edges[int(edge_name[4:]) - 1],
                          shape.Faces[int(face_name[4:]) - 1]))
        edges = [e for e, _ in pairs]
        try:
            wire = Part.Wire(Part.__sortEdges__(edges))
        except Exception:  # noqa: BLE001
            wire = None
        if wire is None or not wire.isClosed():
            raise KernelError("le contour doit être fermé")
        count = max(48, 16 * len(edges))
        points = wire.discretize(Number=count + 1)[:-1]
        curve = Part.BSplineCurve()
        curve.interpolate(points, PeriodicFlag=True)
        poles = curve.getPoles()

        def cross_dir(point):
            edge, face = min(pairs, key=lambda ef: ef[0].distToShape(
                Part.Vertex(point))[0])
            u, v = face.Surface.parameter(point)
            normal = face.normalAt(u, v)
            tangent = edge.tangentAt(edge.Curve.parameter(point))
            d = normal.cross(tangent)
            if d.Length < 1e-9:
                raise KernelError("bouchon tangent : arête dégénérée")
            d.normalize()
            # Vers l'extérieur de la face : un pas en arrière y reste.
            if face.distToShape(Part.Vertex(point - d * 0.01))[0] > 1e-4:
                d = d * -1
            return d

        feet = [curve.value(curve.parameter(q)) for q in poles]
        dirs = [cross_dir(p) for p in feet]
        center = sum(poles, App.Vector()) * (1.0 / len(poles))
        radius = max((q - center).Length for q in poles)
        axis = sum(dirs, App.Vector())
        if axis.Length < 1e-6:
            raise KernelError("bouchon tangent : le contour ne donne pas de "
                              "sens au bouchon")
        axis.normalize()
        row1 = [q + d * (0.35 * radius) for q, d in zip(poles, dirs)]
        row2 = [center + (q - center) * 0.55 + axis * (0.95 * radius)
                for q in poles]
        apex = center + axis * radius
        grid = [[poles[k], row1[k], row2[k], apex] for k in range(len(poles))]
        surface = Part.BSplineSurface()
        surface.buildFromPolesMultsKnots(
            grid, curve.getMultiplicities(), [4, 4], curve.getKnots(),
            [0.0, 1.0], True, False, curve.Degree, 3)
        cap = surface.toShape()
        if cap.isNull() or not cap.isValid():
            raise KernelError("bouchon tangent : surface invalide")
        return cap

    def _split_closed_links(self, links, faces):
        doc = self._require_doc()
        out_links, out_faces = [], []
        for (obj, sub), face in zip(links, faces):
            edge = obj.Shape.Edges[int(sub[4:]) - 1]
            if not edge.isClosed():
                out_links.append((obj, sub))
                out_faces.append(face)
                continue
            helper = doc.addObject("Part::Feature", "ClosedEdgeHalves")
            self._mark_internal(helper)
            self._stamp(helper, halvessource=obj.Name, halvesedge=sub,
                        halvesface=face)
            helper.Shape = self._halves_shape(obj.Shape, sub, face)
            out_links += [(helper, "Edge1"), (helper, "Edge2")]
            out_faces += ["Face1" if face else "", "Face1" if face else ""]
        return out_links, out_faces

    @staticmethod
    def _halves_shape(shape, sub, face):
        """Les deux moitiés d'une arête fermée, puis la face voisine."""
        import Part
        edge = shape.Edges[int(sub[4:]) - 1]
        first, last = edge.FirstParameter, edge.LastParameter
        middle = (first + last) / 2
        parts = [Part.Edge(edge.Curve, first, middle),
                 Part.Edge(edge.Curve, middle, last)]
        if face:
            parts.append(shape.Faces[int(face[4:]) - 1])
        return Part.Compound(parts)

    @staticmethod
    def _adjacent_face(obj, sub):
        """« FaceN » qui borde l'arête ``sub`` de ``obj`` (une seule face,
        sinon le contact n'est pas défini) — ou chaîne vide."""
        import Part
        shape = obj.Shape
        if not shape.Faces:
            return ""
        edge = shape.Edges[int(sub[4:]) - 1]
        owners = shape.ancestorsOfType(edge, Part.Face)
        if len(owners) < 1:
            return ""
        for i, face in enumerate(shape.Faces):
            if face.isSame(owners[0]):
                return "Face%d" % (i + 1)
        return ""

    def surface_boundary(self, boundary):
        """Surface frontière : deux à quatre courbes qui se touchent bout à
        bout (ou deux courbes opposées) — la peau passe par elles."""
        from engine.kernel import KernelError
        import Surface  # noqa: F401 — enregistre Surface::GeomFillSurface
        links = self._boundary_links(boundary)
        if not 2 <= len(links) <= 4:
            raise KernelError("une surface frontière demande deux à quatre "
                              "courbes")

        def configure(obj):
            obj.BoundaryList = links

        return self._add_part_surface(
            "Surface::GeomFillSurface", "Surface frontière", configure)

    def surface_ruled(self, boundary):
        """Surface réglée : des segments droits relient deux courbes."""
        from engine.kernel import KernelError
        links = self._boundary_links(boundary)
        if len(links) != 2:
            raise KernelError("une surface réglée relie exactement deux "
                              "courbes")

        def configure(obj):
            obj.Curve1 = (links[0][0], [links[0][1]])
            obj.Curve2 = (links[1][0], [links[1][1]])

        return self._add_part_surface(
            "Part::RuledSurface", "Surface réglée", configure)
