"""Surfaces et courbes : extrusion, révolution, lissage, balayage, plane,
remplissage, décalage, prolongement, ajustement, couture, spline 3D.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

def Part_Face():  # noqa: N802 — le type Part.Face, importé à l'appel
    import Part
    return Part.Face


class SurfaceMixin:
    # -- surfaces et courbes ----------------------------------------------

    #: Objets document-level exposés dans la section Surfaces de l'arbre.
    #: Les PartDesign::* dérivent aussi de Part::Feature — filtre exact.
    _SURFACE_TYPE_IDS = frozenset({
        "Part::Feature", "Part::Extrusion", "Part::Revolution",
        "Part::Loft", "Part::Offset", "Part::Face", "Part::Sweep",
        "Surface::Filling", "Surface::Extend", "Surface::GeomFillSurface",
        "Part::RuledSurface", "Part::Fillet", "Part::Section",
        "Part::ProjectOnSurface", "Part::Helix", "Part::Offset2D",
        # Ajuster : la découpe (BOPTools) puis la pièce gardée
        # (CompoundTools) — fonctions Python livrées avec FreeCAD.
        "Part::FeaturePython",
    })

    def _is_surface_obj(self, obj):
        """Surface ou courbe FreeSolid (section Surfaces de l'arbre). Un
        lieur de forme n'en est une que s'il est une courbe composite ou
        une suppression de faces —
        ceux des balayages vivent dans le corps."""
        type_id = getattr(obj, "TypeId", "")
        if type_id == "PartDesign::SubShapeBinder":
            return bool(getattr(obj, "FreeSolidComposite", False)
                        or getattr(obj, "FreeSolidKind", "") == "deleteface")
        return type_id in self._SURFACE_TYPE_IDS

    #: Propriétés FreeSolid d'une spline 3D (points, interpolée, fermée).
    _CURVE_POINTS = "FreeSolidPoints"

    def _add_surface(self, shape, label):
        """Surface figée (Part::Feature) — couture, courbe 3D, legacy."""
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Shape = shape
        feature.Label = self._t(label)
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
        obj.Label = self._t(label)
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
        elif obj.TypeId in ("Part::Loft", "Part::Sweep"):
            for section in getattr(obj, "Sections", None) or []:
                if (section is not None
                        and section.TypeId == "Sketcher::SketchObject"):
                    sketches.append(section)
            spine = None
            if obj.TypeId == "Part::Sweep":
                spine = getattr(obj, "Spine", None)
            if isinstance(spine, tuple):
                spine = spine[0]
            if (spine is not None
                    and spine.TypeId == "Sketcher::SketchObject"):
                sketches.append(spine)
        elif obj.TypeId == "Part::ProjectOnSurface":
            for source in getattr(obj, "Projection", None) or []:
                if isinstance(source, tuple):  # lien (objet, éléments)
                    source = source[0]
                if (source is not None
                        and source.TypeId == "Sketcher::SketchObject"):
                    sketches.append(source)
        elif obj.TypeId == "Part::Face":
            for source in getattr(obj, "Sources", None) or []:
                if (source is not None
                        and source.TypeId == "Sketcher::SketchObject"):
                    sketches.append(source)
        return sketches

    def _surface_tree_entry(self, obj, order_of=None, known_names=None,
                            consumed=None):
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
        curve = self._curve_spec(obj)
        if curve is not None:
            # Spline 3D : figée pour set_params, rééditable par ses points.
            entry["curve"] = curve
        spec = self._surface_spec(obj)
        if spec is not None:
            entry["surface"] = spec
        if consumed is not None and obj.Name in consumed:
            entry["consumed"] = True
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

    def surface_delete_faces(self, surface, faces):
        """Supprimer des faces d'une surface : un lieur de forme garde les
        autres (paramétrique) ; le trou se bouche ensuite par un
        remplissage si besoin."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import PartDesign  # noqa: F401 — enregistre le lieur de forme
        doc = self._require_doc()
        src = self._get_surface(surface)
        count = len(src.Shape.Faces)
        drop = {int(f) for f in faces or ()}
        if not drop:
            raise KernelError("cliquez les faces à supprimer")
        if any(f < 0 or f >= count for f in drop):
            raise KernelError("face inconnue : {}".format(sorted(drop)))
        keep = ["Face%d" % (i + 1) for i in range(count) if i not in drop]
        if not keep:
            raise KernelError("toutes les faces seraient supprimées")
        kept = doc.addObject("PartDesign::SubShapeBinder", "Surface")
        try:
            self._stamp(kept, kind="deleteface")
            kept.Support = [(src, tuple(keep))]
            kept.Label = self._t("Faces supprimées")
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(kept.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def surface_split(self, surface, tool):
        """Ligne de séparation : une courbe posée sur la surface (projetée,
        d'intersection, spline) scinde ses faces — chaque morceau se
        supprime ou se remplit ensuite à part."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import BOPTools.SplitFeatures as split_features
        doc = self._require_doc()
        src = self._get_surface(surface)
        cutter = doc.getObject(str(tool))
        if cutter is None or not getattr(cutter, "Shape", None):
            raise KernelError("objet inconnu : {}".format(tool))
        if cutter.Name == src.Name:
            raise KernelError("la surface et l'outil doivent être différents")
        before = len(src.Shape.Faces)
        if not before:
            raise KernelError("scinder demande une surface, pas une courbe")
        split = split_features.makeSlice("Surface")
        try:
            split.Base = src
            split.Tools = [cutter]
            split.Mode = "Standard"
            split.Label = self._t("Surface scindée")
            self._stamp(split, kind="split")
            self._recompute()
            if len(split.Shape.Faces) <= before:
                raise KernelError("la courbe ne scinde pas la surface — "
                                  "elle doit être posée dessus, d'un bord à "
                                  "l'autre ou fermée")
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(split.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def surface_untrim(self, surface, face=0):
        """Désajuster : la face retrouve les bords naturels de sa surface
        porteuse — trous bouchés, contour d'origine."""
        from engine.kernel import KernelError
        import Surface  # noqa: F401 — enregistre Surface::Extend
        src = self._get_surface(surface)
        faces = src.Shape.Faces
        if not faces:
            raise KernelError("désajuster demande une surface, pas une "
                              "courbe")
        face = int(face)
        if face < 0 or face >= len(faces):
            raise KernelError("face inconnue : {}".format(face))

        def configure(obj):
            obj.Face = (src, ["Face%d" % (face + 1)])
            obj.ExtendUSymetric = False
            obj.ExtendVSymetric = False
            for side in ("UNeg", "UPos", "VNeg", "VPos"):
                setattr(obj, "Extend" + side, 0.0)
            self._stamp(obj, untrim=1)

        return self._add_part_surface(
            "Surface::Extend", "Surface désajustée", configure)

    def surface_fillet(self, surface, edges, radius):
        """Congé entre faces d'une surface : sur les arêtes partagées par
        deux faces (cousez d'abord deux surfaces séparées)."""
        from engine.kernel import KernelError
        import Part
        src = self._get_surface(surface)
        shape = src.Shape
        radius = float(radius)
        if radius <= 0:
            raise KernelError("le rayon doit être positif")
        picked = []
        for edge in edges or ():
            edge = int(edge)
            if edge < 0 or edge >= len(shape.Edges):
                raise KernelError("arête inconnue : {}".format(edge))
            if len(shape.ancestorsOfType(shape.Edges[edge], Part.Face)) != 2:
                raise KernelError("le congé se pose sur une arête entre deux "
                                  "faces — cousez d'abord les surfaces")
            picked.append(edge)
        if not picked:
            raise KernelError("cliquez les arêtes à arrondir")

        def configure(obj):
            obj.Base = src
            obj.Edges = [(e + 1, radius, radius) for e in picked]

        return self._add_part_surface(
            "Part::Fillet", "Congé de surface", configure)

    def edit_surface_fillet(self, surface, radius):
        """Rééditer le rayon d'un congé de surface."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(surface))
        if obj is None or obj.TypeId != "Part::Fillet":
            raise KernelError("congé de surface inconnu : {}".format(surface))
        radius = float(radius)
        if radius <= 0:
            raise KernelError("le rayon doit être positif")
        obj.Edges = [(edge[0], radius, radius) for edge in obj.Edges]
        self._recompute()
        return self.get_tree()

    def curve_intersection(self, first, second=None, body=False):
        """Courbe d'intersection de deux surfaces — ou d'une surface et du
        solide (``body``)."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        base = self._get_surface(first)
        if body:
            tool = self._require_body()
            if not getattr(tool, "Shape", None) or not tool.Shape.Solids:
                raise KernelError("le corps n'a pas encore de solide")
        else:
            if second is None:
                raise KernelError("choisissez une seconde surface")
            tool = self._get_surface(second)
            if tool.Name == base.Name:
                raise KernelError("choisissez deux surfaces différentes")

        def configure(obj):
            obj.Base = base
            obj.Tool = tool
            obj.Approximation = False
            doc.recompute()
            if not obj.Shape.Edges:
                raise KernelError("les deux formes ne se coupent pas")

        return self._add_part_surface(
            "Part::Section", "Courbe d'intersection", configure)

    def curve_project(self, sketch, surface, face=0):
        """Courbe projetée : les traits d'une esquisse projetés sur une
        face de surface, selon la normale de l'esquisse."""
        from engine.kernel import KernelError
        sk = self._get_sketch(str(sketch))
        src = self._get_surface(surface)
        faces = src.Shape.Faces
        face = int(face)
        if not faces:
            raise KernelError("projeter demande une surface, pas une courbe")
        if face < 0 or face >= len(faces):
            raise KernelError("face inconnue : {}".format(face))
        App = self._app()
        normal = sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))

        def configure(obj):
            obj.SupportFace = (src, ["Face%d" % (face + 1)])
            obj.Projection = [sk]
            obj.Mode = "Edges"
            obj.Direction = normal * -1
            self._recompute()
            if not obj.Shape.Edges:
                raise KernelError("la projection ne touche pas la face")

        return self._add_part_surface(
            "Part::ProjectOnSurface", "Courbe projetée", configure)

    def surface_radiate(self, boundary, distance):
        """Surface radiée : une bande plane qui part d'un contour plan (bords
        du solide, d'une surface, une esquisse), dans son plan."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import PartDesign  # noqa: F401 — enregistre le lieur de forme
        doc = self._require_doc()
        distance = float(distance)
        if distance == 0:
            raise KernelError("la distance ne peut pas être nulle")
        links = self._boundary_links(boundary)
        groups, order = {}, []
        for obj, sub in links:
            if obj.Name not in groups:
                groups[obj.Name] = (obj, [])
                order.append(obj.Name)
            groups[obj.Name][1].append(sub)
        binder = doc.addObject("PartDesign::SubShapeBinder", "RadiateEdges")
        self._mark_internal(binder)
        try:
            binder.Support = [(groups[n][0], tuple(groups[n][1]))
                              for n in order]

            def configure(obj):
                obj.Source = binder
                obj.Value = distance
                obj.Join = "Intersection"
                obj.Fill = True

            return self._add_part_surface(
                "Part::Offset2D", "Surface radiée", configure)
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(binder.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise KernelError("{} — le contour doit être plan".format(exc))
            raise KernelError(_explain(exc))

    _HELIX_AXES = {"Z": ((0, 0, 0), 0), "Y": ((1, 0, 0), -90),
                   "X": ((0, 1, 0), 90)}

    def curve_helix(self, pitch, height, radius, angle=0.0, left=False,
                    axis="Z"):
        """Hélice (ou spirale conique avec ``angle``) autour d'un axe
        d'origine — trajectoire de balayage, ressort, filet."""
        from engine.kernel import KernelError
        App = self._app()
        pitch, height, radius = float(pitch), float(height), float(radius)
        if pitch <= 0 or height <= 0 or radius <= 0:
            raise KernelError("pas, hauteur et rayon doivent être positifs")
        if str(axis) not in self._HELIX_AXES:
            raise KernelError("axe inconnu : {}".format(axis))
        turn_axis, degrees = self._HELIX_AXES[str(axis)]

        def configure(obj):
            obj.Pitch = pitch
            obj.Height = height
            obj.Radius = radius
            obj.Angle = float(angle)
            obj.LocalCoord = "Left-handed" if left else "Right-handed"
            obj.Placement = App.Placement(
                App.Vector(0, 0, 0),
                App.Rotation(App.Vector(*turn_axis), degrees))

        return self._add_part_surface("Part::Helix", "Hélice", configure)

    def curve_composite(self, boundary):
        """Courbe composite : des arêtes et courbes bout à bout réunies en
        une seule trajectoire (lieur de forme paramétrique)."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        import PartDesign  # noqa: F401 — enregistre le lieur de forme
        doc = self._require_doc()
        links = self._boundary_links(boundary)
        groups = {}
        order = []
        for obj, sub in links:
            if obj.Name not in groups:
                groups[obj.Name] = (obj, [])
                order.append(obj.Name)
            groups[obj.Name][1].append(sub)
        binder = doc.addObject("PartDesign::SubShapeBinder", "Surface")
        try:
            binder.addProperty("App::PropertyBool", "FreeSolidComposite",
                               "FreeSolid")
            binder.setEditorMode("FreeSolidComposite", 2)
            binder.FreeSolidComposite = True
            binder.Support = [(groups[n][0], tuple(groups[n][1]))
                              for n in order]
            binder.Label = self._t("Courbe composite")
            self._recompute()
            edges = binder.Shape.Edges
            if not edges:
                raise KernelError("aucune arête retenue")
            # Une seule chaîne connexe, sinon ce n'est pas une trajectoire.
            if len(Part.sortEdges(list(edges))) != 1:
                raise KernelError("les arêtes ne se suivent pas bout à "
                                  "bout")
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(binder.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

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

    def _stamp(self, obj, **values):
        """Paramètres FreeSolid rangés sur l'objet (relecture, réédition)."""
        for key, value in values.items():
            prop = "FreeSolid" + key.capitalize()
            if prop not in obj.PropertiesList:
                kind = ("App::PropertyFloat" if isinstance(value, float)
                        else "App::PropertyInteger" if isinstance(value, int)
                        else "App::PropertyString")
                obj.addProperty(kind, prop, "FreeSolid")
                obj.setEditorMode(prop, 2)
            setattr(obj, prop, value)

    @staticmethod
    def _mark_internal(obj):
        """Objet de service (découpe d'un ajustement, demi-espace d'une
        coupe par surface) : hors arbre."""
        obj.addProperty("App::PropertyBool", "FreeSolidSurfaceTool",
                        "FreeSolid")
        obj.setEditorMode("FreeSolidSurfaceTool", 2)
        obj.FreeSolidSurfaceTool = True

    def _surface_spec(self, obj):
        """Paramètres rééditables des surfaces FreeSolid à panneau dédié."""
        if obj.TypeId == "Surface::Extend" and getattr(
                obj, "FreeSolidUntrim", 0):
            return {"kind": "untrim"}
        if obj.TypeId == "Part::Fillet":
            edges = list(getattr(obj, "Edges", ()) or ())
            return {"kind": "fillet",
                    "radius": float(edges[0][1]) if edges else 0.0}
        if obj.TypeId == "Surface::Extend":
            face = getattr(obj, "Face", None)
            return {"kind": "extend",
                    "source": face[0].Name if face else None,
                    "distance": float(getattr(obj, "FreeSolidDistance", 0)),
                    "edge": (int(getattr(obj, "FreeSolidEdge", 0)) - 1
                             if getattr(obj, "FreeSolidEdge", 0) else None)}
        if getattr(obj, "FreeSolidKind", "") in ("deleteface", "split"):
            return {"kind": obj.FreeSolidKind}
        if getattr(obj, "FreeSolidKind", "") == "trim":
            base = getattr(obj, "Base", None)
            return {"kind": "trim",
                    "source": base.Base.Name if base is not None else None,
                    "tool": (base.Tools[0].Name
                             if base is not None and base.Tools else None)}
        if getattr(obj, "FreeSolidCapedges", ""):
            return {"kind": "fill", "cap": True}
        if getattr(obj, "FreeSolidFreemoves", ""):
            moves = self._free_moves(self._frozen_stamps(obj))
            return {"kind": "freeform", "moves": moves,
                    "grid": int(getattr(obj, "FreeSolidFreegrid", 6)),
                    "source": str(getattr(obj, "FreeSolidFreesource", "")),
                    "face": int(getattr(obj, "FreeSolidFreeface", 0))}
        if getattr(obj, "FreeSolidFreesource", ""):
            pushes = self._free_pushes(self._frozen_stamps(obj))
            return {"kind": "freeform", "pushes": pushes,
                    "height": pushes[0][3],
                    "radius": float(obj.FreeSolidFreeradius),
                    "keep_edges": bool(getattr(obj, "FreeSolidFreeedges", 0))}
        if getattr(obj, "FreeSolidFlatsource", ""):
            return {"kind": "flatten"}
        if obj.TypeId == "Part::Offset" and not getattr(obj, "Fill", True):
            value = getattr(obj, "Value", 0.0)
            return {"kind": "offset",
                    "distance": float(getattr(value, "Value", value))}
        if obj.TypeId == "Surface::Filling":
            return {"kind": "fill",
                    "edges": len(getattr(obj, "BoundaryEdges", ()) or ())}
        return None

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

    @staticmethod
    def _surface_normal(shape):
        """Normale moyenne d'une peau (pondérée par l'aire des faces)."""
        import FreeCAD as App
        total = App.Vector(0, 0, 0)
        for face in shape.Faces:
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            total = total + normal * face.Area
        return total

    def add_surface_cut(self, surface, flip=False, thickness=None):
        """Couper le solide avec une surface : tout ce qui est du côté de
        la normale (ou de l'autre, ``flip``) part. La surface balaie un
        demi-espace (extrusion paramétrique), combiné en soustraction dans
        l'historique — la coupe suit la surface quand elle change.
        ``thickness`` : seule une bande de cette épaisseur part (la surface
        épaissie, ``Part::Offset`` rempli) — épaissir en enlevant."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Solids:
            raise KernelError("couper avec une surface demande un solide")
        src = self._get_surface(surface)
        if not src.Shape.Faces:
            raise KernelError("couper demande une surface, pas une courbe")
        normal = self._surface_normal(src.Shape)
        if normal.Length < 1e-9:
            raise KernelError("la surface n'a pas de côté défini — elle se "
                              "referme sur elle-même")
        normal.normalize()
        if flip:
            normal = normal * -1
        reach = max(1000.0, 4 * shape.BoundBox.DiagonalLength
                    + 4 * src.Shape.BoundBox.DiagonalLength)
        before = shape.Volume
        if thickness is not None:
            thickness = abs(float(thickness))
            if thickness < 1e-9:
                raise KernelError("l'épaisseur ne peut pas être nulle")
            half = doc.addObject("Part::Offset", "SurfaceCutThick")
            self._mark_internal(half)
            half.Source = src
            half.Value = -thickness if flip else thickness
            half.Fill = True
        else:
            half = doc.addObject("Part::Extrusion", "SurfaceCutHalf")
            self._mark_internal(half)
            half.Base = src
            half.DirMode = "Custom"
            half.Dir = normal
            half.LengthFwd = reach
            half.Solid = True
        tool_body = doc.addObject("PartDesign::Body", "SurfaceCutBody")
        self._mark_internal(tool_body)
        tool_body.BaseFeature = half

        def discard():
            # Le corps outil range un « BaseFeature » interne : le retirer
            # aussi, sinon il reste orphelin et invalide.
            names = [o.Name for o in (getattr(tool_body, "Group", None)
                                      or [])]
            for name in names + [tool_body.Name, half.Name]:
                try:
                    doc.removeObject(name)
                except Exception:
                    pass

        try:
            doc.recompute()
            self.add_boolean(tool=tool_body.Name, type="cut")
        except KernelError:
            discard()
            raise
        tip = body.Tip
        after = body.Shape.Volume if body.Shape.Solids else 0.0
        problem = None
        if abs(after - before) < 1e-6 * max(before, 1.0):
            problem = ("la surface épaissie ne touche pas le solide"
                       if thickness is not None else
                       "la surface ne coupe pas le solide — elle doit le "
                       "traverser de part en part")
        elif after < 1e-6 * before:
            problem = ("la surface enlève tout le solide — inversez le côté")
        if problem:
            self._drop_failed_feature(body, doc, tip, tip.BaseFeature)
            discard()
            self._recompute()
            raise KernelError(problem)
        tip.Label = self._t("Épaissir en enlevant" if thickness is not None
                            else "Couper avec une surface")
        self._stamp(tip, cutsurface=src.Name, cutflip=int(bool(flip)),
                    cutthick=float(thickness or 0.0))
        return self.get_tree()

    @staticmethod
    def _defeatured(base_shape, faces):
        """Le solide sans ses faces ``faces`` (indices base 0) — les faces
        voisines se prolongent pour refermer la matière."""
        from engine.kernel import KernelError
        picked = []
        for face in faces:
            if face < 0 or face >= len(base_shape.Faces):
                raise KernelError("face inconnue : {}".format(face))
            picked.append(base_shape.Faces[face])
        try:
            result = base_shape.defeaturing(picked)
        except Exception:  # noqa: BLE001
            result = None
        if (result is None or result.isNull() or not result.Solids
                or not result.isValid()):
            raise KernelError("le modeleur ne sait pas retirer ces faces "
                              "— essayez-les une par une, ou une face qui "
                              "touche moins de voisines")
        return result

    def add_delete_face(self, faces):
        """Supprimer des faces du solide : le trou se referme par les faces
        voisines (perçage, congé, bossage retirés). La forme suit les
        fonctions d'avant : elle est recalculée à chaque reconstruction."""
        from engine.kernel import KernelError
        tip = self._solid_tip("supprimer une face demande un solide")
        indices = sorted({int(f) for f in faces or ()})
        if not indices:
            raise KernelError("cliquez les faces à supprimer")
        stamps = {"defeatbase": tip.Name,
                  "defeatfaces": ";".join(str(i) for i in indices)}
        result = self._frozen_result(stamps, tip.Shape)
        return self._commit_frozen(
            tip, result, stamps, "Supprimer la face",
            {"deletefaces": stamps["defeatfaces"]})

    def add_replace_face(self, face, surface):
        """Remplacer une face du solide par une surface : la matière
        s'étend ou se retire jusqu'à la surface, qui doit couvrir la face."""
        tip = self._solid_tip("remplacer une face demande un solide")
        src = self._get_surface(surface)
        stamps = {"replacebase": tip.Name, "replaceface": int(face),
                  "replacesurface": src.Name}
        result = self._frozen_result(stamps, tip.Shape)
        return self._commit_frozen(
            tip, result, stamps, "Remplacer la face",
            {"replacedface": int(face) + 1, "replacedby": src.Name})

    def _solid_tip(self, message):
        from engine.kernel import KernelError
        body = self._require_body()
        tip = body.Tip
        shape = getattr(body, "Shape", None)
        if tip is None or shape is None or not shape.Solids:
            raise KernelError(message)
        return tip

    def _frozen_result(self, stamps, base_shape):
        """Forme calculée d'une suppression ou d'un remplacement de face."""
        from engine.kernel import KernelError
        if "defeatfaces" in stamps:
            faces = [int(f) for f in str(stamps["defeatfaces"]).split(";")
                     if f != ""]
            return self._defeatured(base_shape, faces)
        face = int(stamps["replaceface"])
        if face < 0 or face >= len(base_shape.Faces):
            raise KernelError("face inconnue : {}".format(face))
        src = self._require_doc().getObject(str(stamps["replacesurface"]))
        if src is None or not src.Shape.Faces:
            raise KernelError("surface inconnue : {}".format(
                stamps["replacesurface"]))
        return self._replaced(base_shape, face, src.Shape)

    @staticmethod
    def _replaced(base_shape, face_index, surface_shape):
        """Le solide dont la face part jusqu'à la surface : la face est
        prolongée en prisme le long de sa normale, puis la surface coupe ce
        qui la dépasse."""
        from engine.kernel import KernelError
        face = base_shape.Faces[face_index]
        u0, u1, v0, v1 = face.ParameterRange
        normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        reach = max(1000.0, 4 * (base_shape.BoundBox.DiagonalLength
                                 + surface_shape.BoundBox.DiagonalLength))
        try:
            grown = base_shape.fuse(face.extrude(normal * reach))
            half = surface_shape.extrude(normal * reach)
            result = grown.cut(half).removeSplitter()
        except Exception:  # noqa: BLE001
            result = None
        if (result is None or result.isNull() or not result.Solids
                or not result.isValid()):
            raise KernelError("la surface ne remplace pas cette face — elle "
                              "doit couvrir toute la face")
        if len(result.Solids) > 1:
            result = max(result.Solids, key=lambda solid: solid.Volume)
        return result

    def _commit_frozen(self, tip, result, stamps, label, feature_stamps):
        """Range une forme calculée dans l'historique : un booléen d'ajout
        (la matière ne fait que croître), d'intersection (elle ne fait que
        diminuer) — ou les deux à la suite, quand elle fait les deux."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        before = tip.Shape
        tolerance = 1e-6 * max(before.Volume, 1.0)
        if before.cut(result).Volume < tolerance:
            steps = ["fuse"]
        elif result.cut(before).Volume < tolerance:
            steps = ["common"]
        else:
            steps = ["fuse", "common"]
        created = []
        features = []

        def discard():
            for feature in reversed(features):
                try:
                    self._drop_failed_feature(body, doc, feature,
                                              feature.BaseFeature)
                except Exception:
                    pass
            for obj in reversed(created):
                names = [o.Name for o in (getattr(obj, "Group", None) or [])]
                for name in names + [obj.Name]:
                    try:
                        doc.removeObject(name)
                    except Exception:
                        pass

        try:
            for step in steps:
                frozen = doc.addObject("Part::Feature", "FrozenShape")
                self._mark_internal(frozen)
                frozen.Shape = result
                self._stamp(frozen, **stamps)
                tool_body = doc.addObject("PartDesign::Body", "FrozenBody")
                self._mark_internal(tool_body)
                tool_body.BaseFeature = frozen
                created += [frozen, tool_body]
                doc.recompute()
                self.add_boolean(tool=tool_body.Name, type=step)
                features.append(body.Tip)
        except KernelError:
            discard()
            self._recompute()
            raise
        if abs(body.Shape.Volume - result.Volume) > tolerance:
            discard()
            self._recompute()
            raise KernelError("le modeleur n'a pas pu ranger cette forme dans "
                              "l'historique")
        owner = features[-1]
        owner.Label = self._t(label)
        self._stamp(owner, **feature_stamps)
        for helper in features[:-1]:
            # L'ajout d'un cas mixte : auxiliaire caché de la fonction,
            # une seule ligne dans l'arbre.
            helper.Label = self._t(label + " — ajout")
            helper.addProperty("App::PropertyBool", self._THIN_HELPER,
                               "FreeSolid", "Objet auxiliaire")
            setattr(helper, self._THIN_HELPER, True)
            helper.addProperty("App::PropertyString", "FreeSolidThinOwner",
                               "FreeSolid", "Fonction propriétaire")
            helper.FreeSolidThinOwner = owner.Name
        return self.get_tree()

    def surface_mid(self, faces=None, thickness=None):
        """Surface médiane d'une paroi. Deux faces cliquées en vis-à-vis :
        planes parallèles et cylindres concentriques exacts, faces
        quelconques par une surface interpolée sur les points milieux.
        Sans faces : toutes les paires de la pièce plus proches que
        ``thickness`` (paroi mince). Recalculée à chaque reconstruction."""
        from engine.kernel import KernelError
        tip = self._solid_tip("une surface médiane demande un solide")
        pair = [int(f) for f in faces or ()]
        if pair:
            if len(pair) != 2 or pair[0] == pair[1]:
                raise KernelError("cliquez les deux faces en vis-à-vis de "
                                  "la paroi")
            spec = "%d;%d" % tuple(pair)
        else:
            if thickness is None or float(thickness) <= 0:
                raise KernelError("indiquez l'épaisseur de paroi maximale")
            spec = "auto:%.9g" % float(thickness)
        stamps = {"midbase": tip.Name, "midfaces": spec}
        shape = self._mid_from_spec(tip.Shape, spec)
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Label = self._t("Surface médiane")
        feature.Shape = shape
        self._stamp(feature, **stamps)
        doc.recompute()
        return self.get_tree()

    def _mid_from_spec(self, base_shape, spec):
        from engine.kernel import KernelError
        import Part
        spec = str(spec)
        if not spec.startswith("auto:"):
            return self._mid_shape(base_shape,
                                   [int(f) for f in spec.split(";")])
        limit = float(spec[5:])
        pairs = self._mid_pairs(base_shape, limit)
        if not pairs:
            raise KernelError("aucune paire de faces en vis-à-vis plus "
                              "proche que l'épaisseur indiquée")
        return Part.Compound([self._mid_shape(base_shape, list(p))
                              for p in pairs])

    @staticmethod
    def _mid_pairs(base_shape, limit):
        """Paires de faces d'une paroi mince : plans antiparallèles qui se
        recouvrent, cylindres coaxiaux — écart au plus ``limit``."""
        faces = base_shape.Faces
        pairs = []
        used = set()
        for i, a in enumerate(faces):
            for j in range(i + 1, len(faces)):
                if i in used or j in used:
                    continue
                b = faces[j]
                ta, tb = a.Surface.TypeId, b.Surface.TypeId
                if ta != tb or ta not in ("Part::GeomPlane",
                                          "Part::GeomCylinder"):
                    continue
                gap = a.distToShape(b)[0]
                if gap < 1e-6 or gap > limit + 1e-9:
                    continue
                if ta == "Part::GeomPlane":
                    na = a.normalAt(*a.Surface.parameter(a.CenterOfMass))
                    nb = b.normalAt(*b.Surface.parameter(b.CenterOfMass))
                    if na.dot(nb) > -0.999:
                        continue
                    # L'écart des plans égale l'écart des faces : elles se
                    # font face (pas seulement voisines par un coin).
                    plane_gap = abs((b.CenterOfMass - a.CenterOfMass).dot(na))
                    if abs(plane_gap - gap) > 1e-6:
                        continue
                else:
                    ca, cb = a.Surface, b.Surface
                    if (abs(abs(ca.Axis.dot(cb.Axis)) - 1) > 1e-6
                            or (cb.Center - ca.Center).cross(ca.Axis).Length
                            > 1e-6):
                        continue
                pairs.append((i, j))
                used.update((i, j))
        return pairs

    @classmethod
    def _mid_shape(cls, base_shape, pair):
        """Peau à mi-chemin de deux faces : décalage exact pour des plans
        parallèles ou des cylindres concentriques, sinon surface interpolée
        sur les milieux d'une grille de points."""
        from engine.kernel import KernelError
        for f in pair:
            if f < 0 or f >= len(base_shape.Faces):
                raise KernelError("face inconnue : {}".format(f))
        first, second = (base_shape.Faces[f] for f in pair)
        gap = first.distToShape(second)[0]
        if gap < 1e-6:
            raise KernelError("les deux faces se touchent — choisissez les "
                              "deux côtés d'une paroi")
        if cls._offset_pair(first, second):
            for value in (-gap / 2, gap / 2):
                try:
                    candidate = first.makeOffsetShape(value, 1e-6)
                except Exception:  # noqa: BLE001
                    continue
                if (candidate.Faces and abs(candidate.distToShape(second)[0]
                                            - gap / 2)
                        < 1e-3 * max(gap, 1.0)):
                    return candidate
        return cls._mid_general(first, second)

    @staticmethod
    def _offset_pair(first, second):
        """Vrai si une face est un décalé de l'autre : plans parallèles,
        cylindres coaxiaux."""
        ta, tb = first.Surface.TypeId, second.Surface.TypeId
        if ta != tb:
            return False
        if ta == "Part::GeomPlane":
            return abs(abs(first.Surface.Axis.dot(second.Surface.Axis))
                       - 1) < 1e-9
        if ta == "Part::GeomCylinder":
            ca, cb = first.Surface, second.Surface
            return (abs(abs(ca.Axis.dot(cb.Axis)) - 1) < 1e-9
                    and (cb.Center - ca.Center).cross(ca.Axis).Length < 1e-6)
        return False

    @staticmethod
    def _mid_general(first, second, count=9):
        """Milieux de la grille de la première face et de leurs projetés
        sur la seconde, interpolés en B-spline."""
        from engine.kernel import KernelError
        import Part
        u0, u1, v0, v1 = first.ParameterRange
        grid = []
        try:
            for i in range(count):
                row = []
                for j in range(count):
                    u = u0 + (u1 - u0) * i / (count - 1)
                    v = v0 + (v1 - v0) * j / (count - 1)
                    point = first.valueAt(u, v)
                    vertex = Part.Vertex(point)
                    other = vertex.distToShape(second)[1][0][1]
                    row.append((point + other) * 0.5)
                grid.append(row)
            surface = Part.BSplineSurface()
            surface.interpolate(grid)
            result = surface.toShape()
        except Exception:  # noqa: BLE001
            result = None
        if result is None or result.isNull() or not result.isValid():
            raise KernelError("surface médiane : le modeleur ne sait pas "
                              "suivre ces deux faces")
        return result

    def surface_flatten(self, surface, face=0):
        """Aplatir une face de surface : son patron à plat (déroulé par
        moindres carrés conformes), posé sur le plan de dessus à côté de la
        pièce — gabarit de découpe, développé de tôle mince."""
        src = self._get_surface(surface)
        stamps = {"flatsource": src.Name, "flatface": int(face)}
        shape = self._flat_shape(src.Shape, int(face))
        return self._add_frozen_surface(shape, "Surface aplatie", stamps)

    def surface_freeform(self, surface, radius=None, pushes=None,
                         point=None, height=None, face=0, keep_edges=False,
                         moves=None, grid=6):
        """Forme libre : la surface est poussée en un ou plusieurs points
        ``pushes`` = [[x, y, z, hauteur], …] (ou ``point`` + ``height``),
        selon sa normale, chaque effet s'éteignant en douceur à
        ``radius`` mm ; ``keep_edges`` garde les bords en place.
        Rééditable, et suit la surface d'origine."""
        from engine.kernel import KernelError
        src = self._get_surface(surface)
        if moves:
            # Points de contrôle déplacés un à un : [[i, j, dx, dy, dz], …]
            # sur une grille de ``grid`` × ``grid`` pôles.
            stamps = {"freesource": src.Name, "freeface": int(face),
                      "freemoves": self._moves_text(moves, int(face)),
                      "freegrid": int(grid), "freeradius": 0.0}
            shape = self._free_shape(src.Shape, stamps)
            return self._add_frozen_surface(shape, "Forme libre", stamps)
        if radius is None:
            raise KernelError("le rayon d'influence doit être positif")
        if not pushes:
            if point is None or height is None:
                raise KernelError("cliquez au moins un point à pousser")
            pushes = [list(point) + [height]]
        stamps = {"freesource": src.Name, "freeface": int(face),
                  "freepushes": self._pushes_text(pushes),
                  "freeradius": float(radius),
                  "freeedges": int(bool(keep_edges))}
        shape = self._free_shape(src.Shape, stamps)
        return self._add_frozen_surface(shape, "Forme libre", stamps)

    def edit_surface_freeform(self, surface, radius=None, pushes=None,
                              height=None, keep_edges=None, moves=None,
                              grid=None):
        """Rééditer une forme libre : points poussés et leurs hauteurs (ou
        une hauteur commune), rayon d'influence, bords fixes."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(surface))
        if obj is None or not getattr(obj, "FreeSolidFreesource", ""):
            raise KernelError("forme libre inconnue : {}".format(surface))
        stamps = self._frozen_stamps(obj)
        if stamps.get("freemoves"):
            src = self._get_surface(stamps["freesource"])
            old_grid = int(stamps.get("freegrid", 6))
            new_grid = int(grid) if grid is not None else old_grid
            if moves is not None:
                # Indices donnés pour la grille demandée.
                stamps["freemoves"] = self._moves_text(
                    moves, int(stamps["freeface"]))
            elif new_grid != old_grid:
                # Seule la grille change : chaque pôle réglé suit sa place.
                stamps["freemoves"] = self._moves_text(self._remap_moves(
                    src.Shape, self._free_moves(stamps), old_grid, new_grid))
            stamps["freegrid"] = new_grid
            obj.Shape = self._free_shape(src.Shape, stamps)
            self._stamp(obj, freemoves=stamps["freemoves"],
                        freegrid=new_grid)
            self._recompute()
            return self.get_tree()
        if radius is None:
            raise KernelError("le rayon d'influence doit être positif")
        current = self._free_pushes(stamps)
        if pushes is None:
            pushes = [p[:3] + [float(height) if height is not None else p[3]]
                      for p in current]
        stamps["freepushes"] = self._pushes_text(pushes)
        stamps["freeradius"] = float(radius)
        if keep_edges is not None:
            stamps["freeedges"] = int(bool(keep_edges))
        src = self._get_surface(stamps["freesource"])
        obj.Shape = self._free_shape(src.Shape, stamps)
        self._stamp(obj, freepushes=stamps["freepushes"],
                    freeradius=float(radius),
                    freeedges=int(stamps.get("freeedges", 0)))
        self._recompute()
        return self.get_tree()

    @staticmethod
    def _moves_text(moves, face=0):
        """``[[face, i, j, dx, dy, dz]…]`` — ou ``[i, j, dx, dy, dz]`` sur
        la face ``face`` — en texte rangé sur l'objet."""
        from engine.kernel import KernelError
        rows = []
        for move in moves:
            try:
                move = list(move)
                if len(move) == 5:
                    move = [face] + move
                if len(move) != 6:
                    raise ValueError
                f, i, j = int(move[0]), int(move[1]), int(move[2])
                dx, dy, dz = (float(v) for v in move[3:6])
            except Exception:
                raise KernelError("point de contrôle invalide : {}".format(
                    move))
            rows.append("%d,%d,%d,%.9g,%.9g,%.9g" % (f, i, j, dx, dy, dz))
        if not rows:
            raise KernelError("choisissez au moins un point de contrôle")
        return ";".join(rows)

    @staticmethod
    def _control_surface(face, grid):
        """B-spline de la face, montée au degré 3 et affinée jusqu'à
        ``grid`` × ``grid`` pôles (au moins) — la grille de contrôle."""
        surface = face.toNurbs().Faces[0].Surface
        surface.increaseDegree(max(3, surface.UDegree),
                               max(3, surface.VDegree))
        u0, u1, v0, v1 = surface.bounds()
        grid = max(4, min(int(grid), 16))
        for direction in ("U", "V"):
            count = getattr(surface, "Nb%sPoles" % direction)
            lo, hi = (u0, u1) if direction == "U" else (v0, v1)
            missing = grid - count
            insert = getattr(surface, "insert%sKnot" % direction)
            for k in range(1, missing + 1):
                insert(lo + (hi - lo) * k / (missing + 1.0), 1, 1e-9)
        return surface

    def surface_control_points(self, surface, face=None, grid=6):
        """Grilles de contrôle d'une surface (lecture seule) : les pôles
        que la forme libre peut déplacer un par un. ``faces`` : une grille
        par face ; ``grid``/``poles`` : celle de ``face`` (0 par défaut)."""
        src = self._get_surface(surface)
        grids = []
        for k, target in enumerate(src.Shape.Faces):
            control = self._control_surface(target, grid)
            grids.append({
                "face": k, "grid": [control.NbUPoles, control.NbVPoles],
                "poles": [[[p.x, p.y, p.z]
                           for p in [control.getPole(i, j) for j in
                                     range(1, control.NbVPoles + 1)]]
                          for i in range(1, control.NbUPoles + 1)]})
        self._source_face(src.Shape, int(face or 0))
        chosen = grids[int(face or 0)]
        return {"grid": chosen["grid"], "poles": chosen["poles"],
                "faces": grids}

    @staticmethod
    def _free_moves(stamps):
        """Déplacements rangés : ``[[face, i, j, dx, dy, dz]…]`` (l'ancien
        format à 5 valeurs vise la face de la fonction)."""
        default = int(stamps.get("freeface", 0) or 0)
        moves = []
        for row in str(stamps.get("freemoves", "")).split(";"):
            if not row:
                continue
            parts = row.split(",")
            if len(parts) == 5:
                parts = [default] + parts
            moves.append([int(parts[0]), int(parts[1]), int(parts[2])]
                         + [float(v) for v in parts[3:6]])
        return moves

    def _remap_moves(self, shape, moves, old_grid, new_grid):
        """Indices des pôles réglés reportés sur une grille plus fine ou
        plus grossière : même place relative sur la face."""
        import math
        counts = {}
        out = []
        for f, i, j, dx, dy, dz in moves:
            if f not in counts:
                face = self._source_face(shape, f)
                old = self._control_surface(face, old_grid)
                new = self._control_surface(face, new_grid)
                counts[f] = (old.NbUPoles, old.NbVPoles,
                             new.NbUPoles, new.NbVPoles)
            ou, ov, nu, nv = counts[f]
            # Arrondi au plus proche, moitiés vers le haut (comme l'aperçu).
            ni = 1 + int(math.floor((i - 1) * (nu - 1)
                                    / float(max(ou - 1, 1)) + 0.5))
            nj = 1 + int(math.floor((j - 1) * (nv - 1)
                                    / float(max(ov - 1, 1)) + 0.5))
            if any(m[:3] == [f, ni, nj] for m in out):
                continue
            out.append([f, ni, nj, dx, dy, dz])
        return out

    @staticmethod
    def _pushes_text(pushes):
        from engine.kernel import KernelError
        rows = []
        for push in pushes:
            try:
                x, y, z, h = (float(v) for v in push)
            except Exception:
                raise KernelError("point à pousser invalide : {}".format(push))
            rows.append("%.9g,%.9g,%.9g,%.9g" % (x, y, z, h))
        if not rows:
            raise KernelError("cliquez au moins un point à pousser")
        return ";".join(rows)

    @staticmethod
    def _free_pushes(stamps):
        """[[x, y, z, h], …] — format multi-points, ou l'ancien point seul."""
        text = str(stamps.get("freepushes", "") or "")
        if text:
            return [[float(v) for v in row.split(",")]
                    for row in text.split(";") if row]
        x, y, z = (float(v) for v in str(stamps["freepoint"]).split(";"))
        return [[x, y, z, float(stamps["freeheight"])]]

    def _add_frozen_surface(self, shape, label, stamps):
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Label = self._t(label)
        feature.Shape = shape
        self._stamp(feature, **stamps)
        doc.recompute()
        return self.get_tree()

    @staticmethod
    def _frozen_stamps(obj):
        prefix = "FreeSolid"
        return {name[len(prefix):].lower(): getattr(obj, name)
                for name in obj.PropertiesList
                if name.startswith(prefix + "Free")
                or name.startswith(prefix + "Flat")}

    @staticmethod
    def _source_face(shape, face):
        from engine.kernel import KernelError
        if face < 0 or face >= len(shape.Faces):
            raise KernelError("face inconnue : {}".format(face))
        return shape.Faces[face]

    def _flat_shape(self, shape, face_index):
        from engine.kernel import KernelError
        import FreeCAD as App
        import Part
        face = self._source_face(shape, face_index).copy()
        try:
            import flatmesh
            face.tessellate(0.05)
            unwrapper = flatmesh.FaceUnwrapper(face)
            unwrapper.findFlatNodes(5, 0.95)
            loops = unwrapper.getFlatBoundaryNodes()
            wires = []
            for loop in loops:
                points = []
                for node in loop:
                    vec = App.Vector(float(node[0]), float(node[1]), 0)
                    if not points or (vec - points[-1]).Length > 1e-7:
                        points.append(vec)
                if (points[0] - points[-1]).Length > 1e-7:
                    points.append(points[0])
                wires.append(Part.makePolygon(points))
            wires.sort(key=lambda w: Part.Face(w).Area, reverse=True)
            flat = Part.Face(wires)
        except Exception:  # noqa: BLE001
            raise KernelError("aplatir : le modeleur ne sait pas dérouler "
                              "cette face")
        if flat.isNull() or not flat.isValid():
            raise KernelError("aplatir : le modeleur ne sait pas dérouler "
                              "cette face")
        # Posé à droite de toute la scène (pièce et surfaces), sur le plan
        # de dessus : il ne chevauche rien.
        box = self._scene_box(shape)
        flat.translate(App.Vector(box.XMax + 10 - flat.BoundBox.XMin,
                                  box.YMin - flat.BoundBox.YMin,
                                  -flat.BoundBox.ZMin))
        return flat

    def _scene_box(self, fallback):
        """Encombrement du corps actif et des surfaces affichées, hors
        patrons à plat."""
        box = fallback.BoundBox
        shapes = []
        body = self._body
        shape = getattr(body, "Shape", None) if body is not None else None
        if shape is not None and not shape.isNull():
            shapes.append(shape)
        consumed = self._consumed_surfaces()
        for obj in self._require_doc().Objects:
            if (not self._is_surface_obj(obj) or obj.Name in consumed
                    or self._is_internal_tool(obj)
                    or getattr(obj, "FreeSolidFlatsource", "")):
                continue
            shape = getattr(obj, "Shape", None)
            if shape is not None and not shape.isNull():
                shapes.append(shape)
        for shape in shapes:
            try:
                box.add(shape.BoundBox)
            except Exception:  # noqa: BLE001
                pass
        return box

    def _free_shape(self, shape, stamps):
        """Les faces déformées — pôles déplacés face par face, ou points
        poussés rangés sur la face la plus proche — et les autres faces
        telles quelles, recousues quand elles se touchent encore."""
        import Part
        default = int(stamps["freeface"])
        changed = {}
        if stamps.get("freemoves"):
            groups = {}
            for f, i, j, dx, dy, dz in self._free_moves(stamps):
                groups.setdefault(f, []).append((i, j, dx, dy, dz))
            for f, rows in sorted(groups.items()):
                changed[f] = self._moved_shape(
                    self._source_face(shape, f), rows,
                    int(stamps.get("freegrid", 6)))
        else:
            groups = {}
            for push in self._free_pushes(stamps):
                f = default
                if len(shape.Faces) > 1:
                    point = Part.Vertex(*push[:3])
                    f = min(range(len(shape.Faces)), key=lambda k: shape
                            .Faces[k].distToShape(point)[0])
                groups.setdefault(f, []).append(push)
            for f, pushes in sorted(groups.items()):
                changed[f] = self._free_face_shape(
                    self._source_face(shape, f), pushes, stamps)
        faces = []
        for k, face in enumerate(shape.Faces):
            faces.extend(changed[k].Faces if k in changed else [face.copy()])
        if len(faces) == 1:
            return faces[0]
        try:
            shell = Part.makeShell(faces)
            shell.sewShape()
            if shell.isValid() and len(shell.Faces) == len(faces):
                return shell
        except Exception:  # noqa: BLE001
            pass
        return Part.makeCompound(faces)

    def _free_face_shape(self, face, pushes, stamps):
        """Pôles de la face déplacés selon la normale, avec une cloche
        qui s'éteint au rayon d'influence (mesuré sur la surface)."""
        from engine.kernel import KernelError
        import math
        import FreeCAD as App
        keep_edges = bool(int(stamps.get("freeedges", 0) or 0))
        radius = float(stamps["freeradius"])
        if radius <= 0:
            raise KernelError("le rayon d'influence doit être positif")
        u0, u1, v0, v1 = face.ParameterRange
        surface = face.toNurbs().Faces[0].Surface
        nu0, nu1, nv0, nv1 = surface.bounds()
        # De la finesse pour que la bosse soit ronde : des nœuds en plus.
        for _ in range(3):
            if surface.NbUPoles >= 16:
                break
            for k in range(1, 4):
                surface.insertUKnot(nu0 + (nu1 - nu0) * k / 4.0, 1, 1e-9)
        for _ in range(3):
            if surface.NbVPoles >= 16:
                break
            for k in range(1, 4):
                surface.insertVKnot(nv0 + (nv1 - nv0) * k / 4.0, 1, 1e-9)
        centers = []
        for x, y, z, height in pushes:
            center = App.Vector(x, y, z)
            cu, cv = surface.parameter(center)
            centers.append((center, surface.normal(cu, cv), height))
        poles = {(i, j): surface.getPole(i, j)
                 for i in range(1, surface.NbUPoles + 1)
                 for j in range(1, surface.NbVPoles + 1)}
        moved = False
        for (i, j), pole in poles.items():
            if keep_edges and (i in (1, surface.NbUPoles)
                               or j in (1, surface.NbVPoles)):
                continue
            shift = App.Vector(0, 0, 0)
            for center, normal, height in centers:
                gap = (pole - center).Length
                if gap >= radius:
                    continue
                weight = 0.5 * (1 + math.cos(math.pi * gap / radius))
                shift = shift + normal * (height * weight)
            if shift.Length > 0:
                surface.setPole(i, j, pole + shift)
                moved = True
        if not moved:
            raise KernelError("forme libre : aucun point de contrôle dans le "
                              "rayon — agrandissez-le")
        # Bornes de la face d'origine, sinon celles de la surface entière.
        try:
            result = surface.toShape(u0, u1, v0, v1)
        except Exception:  # noqa: BLE001
            result = surface.toShape(nu0, nu1, nv0, nv1)
        if result.isNull() or not result.isValid():
            raise KernelError("forme libre : la surface poussée est invalide "
                              "— réduisez la hauteur")
        return result

    def _moved_shape(self, face, rows, grid):
        """Pôles de la grille de contrôle déplacés de leur vecteur."""
        from engine.kernel import KernelError
        import FreeCAD as App
        control = self._control_surface(face, grid)
        for i, j, dx, dy, dz in rows:
            if not (1 <= i <= control.NbUPoles and 1 <= j <= control.NbVPoles):
                raise KernelError("point de contrôle hors de la grille : "
                                  "{} {}".format(i, j))
            control.setPole(i, j, control.getPole(i, j)
                            + App.Vector(float(dx), float(dy), float(dz)))
        result = control.toShape()
        if result.isNull() or not result.isValid():
            raise KernelError("forme libre : la surface déformée est "
                              "invalide")
        return result

    def _refresh_frozen_shapes(self):
        """Recalcule les formes figées qui dépendent d'une fonction du
        corps (supprimer, remplacer une face) ; vrai si l'une a changé."""
        doc = self._require_doc()
        changed = False
        for obj in doc.Objects:
            curve = self._curve_spec(obj)
            if curve is not None and any(curve.get("links") or ()):
                try:
                    points, links = self._resolve_links(curve["points"],
                                                        curve["links"])
                    points = self.solve_curve_rules(
                        points, curve.get("rules"),
                        [i for i, l in enumerate(links) if l])
                except Exception:  # noqa: BLE001
                    continue
                if any(abs(a - b) > 1e-9 for p, q in zip(points,
                                                           curve["points"])
                       for a, b in zip(p, q)):
                    vectors, shape = self._curve_shape(
                        points, curve["spline"], curve["closed"])
                    self._store_curve(obj, vectors, curve["spline"],
                                      curve["closed"])
                    obj.Shape = shape
                    changed = True
                continue
            sew_sources = getattr(obj, "FreeSolidSources", "")
            if sew_sources:
                sources = [doc.getObject(n) for n in
                           str(sew_sources).split(";") if n]
                if any(s is None or not getattr(s, "Shape", None)
                       for s in sources):
                    continue
                try:
                    result = self._sew_shape([s.Shape for s in sources])
                except Exception:  # noqa: BLE001
                    continue
                old = obj.Shape
                if (old.isNull() or abs(old.Area - result.Area) > 1e-9
                        or (old.BoundBox.Center - result.BoundBox.Center)
                        .Length > 1e-9):
                    obj.Shape = result
                    changed = True
                continue
            cap_spec = getattr(obj, "FreeSolidCapedges", "")
            if cap_spec:
                try:
                    result = self._cap_shape(cap_spec)
                except Exception:  # noqa: BLE001
                    continue
                old = obj.Shape
                if (old.isNull() or abs(old.Area - result.Area) > 1e-9
                        or (old.BoundBox.Center - result.BoundBox.Center)
                        .Length > 1e-9):
                    obj.Shape = result
                    changed = True
                continue
            halves = getattr(obj, "FreeSolidHalvessource", "")
            if halves:
                src = doc.getObject(halves)
                if src is None or not getattr(src, "Shape", None):
                    continue
                try:
                    result = self._halves_shape(src.Shape,
                                                obj.FreeSolidHalvesedge,
                                                obj.FreeSolidHalvesface)
                except Exception:  # noqa: BLE001
                    continue
                old = obj.Shape
                if (old.isNull() or abs(old.Length - result.Length) > 1e-9
                        or (old.BoundBox.Center - result.BoundBox.Center)
                        .Length > 1e-9):
                    obj.Shape = result
                    changed = True
                continue
            free_src = (getattr(obj, "FreeSolidFlatsource", "")
                        or getattr(obj, "FreeSolidFreesource", ""))
            if free_src:
                src = doc.getObject(free_src)
                if src is None or not getattr(src, "Shape", None):
                    continue
                try:
                    if getattr(obj, "FreeSolidFlatsource", ""):
                        result = self._flat_shape(src.Shape,
                                                  int(obj.FreeSolidFlatface))
                    else:
                        result = self._free_shape(src.Shape,
                                                  self._frozen_stamps(obj))
                except Exception:  # noqa: BLE001
                    continue
                old = obj.Shape
                if (old.isNull() or abs(old.Area - result.Area) > 1e-6
                        or (old.BoundBox.Center - result.BoundBox.Center)
                        .Length > 1e-6):
                    obj.Shape = result
                    changed = True
                continue
            mid_base = getattr(obj, "FreeSolidMidbase", "")
            if mid_base:
                base = doc.getObject(mid_base)
                if base is None or not getattr(base, "Shape", None):
                    continue
                try:
                    result = self._mid_from_spec(base.Shape,
                                                 obj.FreeSolidMidfaces)
                except Exception:  # noqa: BLE001
                    continue
                old = obj.Shape
                if (old.isNull() or abs(old.Area - result.Area) > 1e-9
                        or (old.BoundBox.Center - result.BoundBox.Center)
                        .Length > 1e-9):
                    obj.Shape = result
                    changed = True
                continue
            base_name = (getattr(obj, "FreeSolidDefeatbase", "")
                         or getattr(obj, "FreeSolidReplacebase", ""))
            if not base_name:
                continue
            base = doc.getObject(base_name)
            if base is None or not getattr(base, "Shape", None):
                continue
            if getattr(obj, "FreeSolidDefeatbase", ""):
                stamps = {"defeatfaces": obj.FreeSolidDefeatfaces}
            else:
                stamps = {"replaceface": obj.FreeSolidReplaceface,
                          "replacesurface": obj.FreeSolidReplacesurface}
            try:
                result = self._frozen_result(stamps, base.Shape)
            except Exception:  # noqa: BLE001
                continue  # l'ancienne forme reste ; l'erreur se verra
            old = obj.Shape
            if (old.isNull() or len(old.Faces) != len(result.Faces)
                    or abs(old.Volume - result.Volume) > 1e-9
                    or abs(old.Area - result.Area) > 1e-9):
                obj.Shape = result
                changed = True
        return changed

    def edit_surface_cut(self, feature, flip, thickness=None):
        """Rééditer une coupe par surface : garder l'autre côté ; pour une
        surface épaissie, son épaisseur."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(feature))
        if obj is None or not getattr(obj, "FreeSolidCutsurface", ""):
            raise KernelError("coupe par surface inconnue : {}".format(
                feature))
        tool_body = next((o for o in (getattr(obj, "Group", None) or [])
                          if o.TypeId == "PartDesign::Body"), None)
        half = getattr(tool_body, "BaseFeature", None)
        if half is None:
            raise KernelError("coupe incomplète — le corps outil est absent")
        flip = bool(flip)
        if half.TypeId == "Part::Offset":
            value = abs(float(thickness if thickness is not None
                              else half.Value))
            if value < 1e-9:
                raise KernelError("l'épaisseur ne peut pas être nulle")
            half.Value = -value if flip else value
            obj.FreeSolidCutflip = int(flip)
            obj.FreeSolidCutthick = value
        elif flip != bool(obj.FreeSolidCutflip):
            half.Dir = half.Dir * -1
            obj.FreeSolidCutflip = int(flip)
        self._recompute()
        return self.get_tree()

    @staticmethod
    def _surface_cut_spec(obj):
        """Paramètres d'une coupe par surface (ligne d'arbre), ou None."""
        name = getattr(obj, "FreeSolidCutsurface", "")
        if not name:
            return None
        spec = {"surface": name, "flip": bool(obj.FreeSolidCutflip)}
        thick = float(getattr(obj, "FreeSolidCutthick", 0.0) or 0.0)
        if thick > 0:
            spec["thickness"] = thick
        return spec

    def _consumed_surfaces(self):
        """Noms des surfaces remplacées par une autre : source d'un
        ajustement, d'un prolongement, d'un épaississement ou d'une
        couture. Elles restent dans l'historique, plus dans la vue."""
        consumed = set()
        for obj in self._require_doc().Objects:
            if self._is_rolled_back(obj):
                continue
            if obj.TypeId == "Surface::Extend":
                face = getattr(obj, "Face", None)
                if face:
                    consumed.add(face[0].Name)
            elif obj.TypeId == "Part::Fillet":
                base = getattr(obj, "Base", None)
                if base is not None:
                    consumed.add(base.Name)
            elif getattr(obj, "FreeSolidKind", "") == "deleteface":
                for link in getattr(obj, "Support", None) or []:
                    consumed.add(link[0].Name)
            elif getattr(obj, "FreeSolidKind", "") == "trim":
                base = getattr(obj, "Base", None)
                if base is not None and getattr(base, "Base", None):
                    consumed.add(base.Base.Name)
            elif getattr(obj, "FreeSolidKind", "") == "split":
                base = getattr(obj, "Base", None)
                if base is not None:
                    consumed.add(base.Name)
            elif (obj.TypeId == "Part::Offset" and getattr(obj, "Fill", False)
                  and not getattr(obj, "FreeSolidSurfaceTool", False)):
                source = getattr(obj, "Source", None)
                if source is not None:
                    consumed.add(source.Name)
            if (obj.TypeId == "Part::Extrusion"
                    and getattr(obj, "FreeSolidSurfaceTool", False)):
                # Demi-espace d'une coupe par surface : la surface a servi.
                base = getattr(obj, "Base", None)
                if base is not None:
                    consumed.add(base.Name)
            pushed = getattr(obj, "FreeSolidFreesource", "")
            if pushed:
                consumed.add(pushed)
            replacing = getattr(obj, "FreeSolidReplacesurface", "")
            if replacing:
                # Surface d'un remplacement de face : la pièce la porte.
                consumed.add(replacing)
            for name in str(getattr(obj, "FreeSolidSources", "")).split(";"):
                if name:
                    consumed.add(name)
        return consumed

    def _get_surface(self, name):
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(name))
        if obj is None or not self._is_surface_obj(obj):
            raise KernelError("surface inconnue : {}".format(name))
        return obj

    def surface_sew(self, surfaces):
        """Coudre des surfaces (pas d'objet Part paramétrique natif pour
        la couture : forme recalculée depuis ses sources à chaque
        reconstruction). Si la peau est fermée, elle devient un solide —
        le geste « coudre puis solidifier »."""
        from engine.kernel import KernelError
        if not isinstance(surfaces, (list, tuple)) or len(surfaces) < 2:
            raise KernelError("coudre demande au moins deux surfaces")
        shape = self._sew_shape([self._get_surface(name).Shape
                                 for name in surfaces])
        closed = bool(shape.Solids)
        tree = self._add_surface(
            shape, "Solide cousu" if closed else "Surface cousue")
        # Les surfaces cousues sont consommées : la couture les remplace.
        sewn = self._require_doc().getObject(tree["surfaces"][-1]["name"])
        self._stamp(sewn, sources=";".join(str(n) for n in surfaces))
        return self.get_tree()

    @staticmethod
    def _sew_shape(shapes):
        """Peau cousue des faces de ``shapes`` ; solide si elle est
        fermée."""
        from engine.kernel import KernelError, _explain
        import Part
        faces = [f for shape in shapes for f in shape.Faces]
        if not faces:
            raise KernelError("aucune face à coudre")
        try:
            shell = Part.makeShell(faces)
            shell.sewShape()
            return Part.makeSolid(shell) if shell.isClosed() else shell
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))

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

    def add_curve3d(self, points, spline=True, closed=False, rules=None,
                    links=None):
        """Spline 3D par points — l'esquisse 3D de FreeSolid : une
        trajectoire de balayage ou un bord de surface (B-spline qui passe
        par les points, ou polyligne). Les points restent rangés sur
        l'objet : la courbe se réédite (``edit_curve3d``). ``rules`` :
        une règle par segment, ``{"axis": "X"|"Y"|"Z"|"", "length": mm}``
        — appliquées en chaîne, elles restent attachées à la courbe."""
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        vectors, shape = self._curve_shape(points, spline, closed)
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Label = self._t("Spline 3D" if spline else "Polyligne 3D")
        self._store_curve(feature, vectors, spline, closed, rules, links)
        feature.Shape = shape
        doc.recompute()
        return self.get_tree()

    def edit_curve3d(self, curve, points, spline=True, closed=False,
                     rules=None, links=None):
        """Rééditer une spline 3D : nouveaux points, les surfaces et
        balayages qui l'utilisent suivent."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(curve))
        if obj is None or self._curve_spec(obj) is None:
            raise KernelError("courbe 3D inconnue : {}".format(curve))
        spec = self._curve_spec(obj)
        if rules is None:
            rules = spec.get("rules")
        if links is None:
            links = spec.get("links")
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        vectors, shape = self._curve_shape(points, spline, closed)
        self._store_curve(obj, vectors, spline, closed, rules, links)
        obj.Shape = shape
        for dependent in obj.InList:
            dependent.touch()
        self._recompute()
        return self.get_tree()

    def curve3d_preview(self, points, spline=True, closed=False,
                        rules=None, links=None):
        """Aperçu exact d'une spline 3D : la polyligne de la courbe que
        ``add_curve3d`` créerait, sans rien ajouter au document."""
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        _, shape = self._curve_shape(points, spline, closed)
        out = []
        for edge in shape.Edges:
            try:
                pts = edge.discretize(Deflection=0.05)
            except Exception:  # noqa: BLE001
                pts = edge.discretize(Number=64)
            pts = [[p.x, p.y, p.z] for p in pts]
            if out and pts and all(abs(a - b) < 1e-9
                                   for a, b in zip(out[-1], pts[0])):
                pts = pts[1:]
            out.extend(pts)
        return {"points": out}

    def _curve_shape(self, points, spline, closed):
        from engine.kernel import (
            KernelError,
            _explain,
        )
        App = self._app()
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            raise KernelError("une courbe demande au moins deux points")
        if closed and len(points) < 3:
            raise KernelError("une courbe fermée demande au moins trois "
                              "points")
        vectors = []
        for p in points:
            try:
                x, y, z = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            vectors.append(App.Vector(x, y, z))
        for a, b in zip(vectors, vectors[1:]):
            if (a - b).Length < 1e-6:
                raise KernelError("deux points consécutifs sont confondus")
        try:
            shape = self._wire_through_points(
                vectors, spline=bool(spline), closed=bool(closed))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return vectors, shape

    @staticmethod
    def solve_curve_rules(points, rules, fixed=()):
        """Applique les règles segment par segment : le segment i garde sa
        direction (ramenée sur l'axe imposé, ou tournée pour faire
        l'angle voulu avec le segment d'avant) et prend sa longueur
        cotée ; la suite de la courbe suit en bloc, jusqu'au prochain
        point lié (``fixed`` : indices des points liés, qui ne bougent
        pas — une règle qui voudrait les déplacer est ignorée)."""
        from engine.kernel import KernelError
        import math
        pts = [[float(v) for v in p] for p in points or ()]
        fixed = set(fixed or ())
        for i, rule in enumerate(rules or ()):
            if i + 1 >= len(pts) or not isinstance(rule, dict):
                continue
            if i + 1 in fixed:
                continue
            axis = str(rule.get("axis") or "")
            length = rule.get("length")
            angle = rule.get("angle")
            a, b = pts[i], pts[i + 1]
            d = [b[k] - a[k] for k in range(3)]
            if axis in ("X", "Y", "Z"):
                k = "XYZ".index(axis)
                d = [d[k] if n == k else 0.0 for n in range(3)]
                if abs(d[k]) < 1e-9:
                    d[k] = 1.0
            elif angle not in (None, "") and i >= 1:
                prev = [a[k] - pts[i - 1][k] for k in range(3)]
                d = SurfaceMixin._turn_to_angle(prev, d, float(angle))
            if length not in (None, ""):
                length = float(length)
                if length <= 0:
                    raise KernelError("une longueur de segment doit être "
                                      "positive")
                size = math.sqrt(sum(c * c for c in d))
                if size < 1e-9:
                    raise KernelError("segment sans direction : déplacez un "
                                      "de ses points")
                d = [c * length / size for c in d]
            target = [a[k] + d[k] for k in range(3)]
            shift = [target[k] - b[k] for k in range(3)]
            for j in range(i + 1, len(pts)):
                if j in fixed:
                    break
                pts[j] = [pts[j][k] + shift[k] for k in range(3)]
        # Passe globale : les règles qu'un point lié a empêchées en chaîne
        # se règlent ensemble, par relaxation.
        return SurfaceMixin._relax_rules(pts, rules or [], fixed)

    @staticmethod
    def _relax_rules(pts, rules, fixed, rounds=4000, tolerance=1e-7):
        """Relaxation par projections successives : chaque règle déplace
        les extrémités libres de son segment (les points liés ne bougent
        pas ; sans point lié, le premier sert d'ancre). Refus si les
        règles ne peuvent pas tenir ensemble."""
        from engine.kernel import KernelError
        import math
        if len(pts) < 2 or not any(isinstance(r, dict) and any(
                r.get(k) not in (None, "") for k in ("axis", "length",
                                                    "angle"))
                for r in rules):
            return pts
        locked = set(fixed) if fixed else {0}

        def free(i):
            return 0.0 if i in locked else 1.0

        def residual():
            worst = 0.0
            for i, rule in enumerate(rules):
                if i + 1 >= len(pts) or not isinstance(rule, dict):
                    continue
                d = [pts[i + 1][k] - pts[i][k] for k in range(3)]
                axis = str(rule.get("axis") or "")
                if axis in ("X", "Y", "Z"):
                    k = "XYZ".index(axis)
                    worst = max(worst, math.sqrt(sum(
                        d[n] ** 2 for n in range(3) if n != k)))
                elif rule.get("angle") not in (None, "") and i >= 1:
                    prev = [pts[i][k] - pts[i - 1][k] for k in range(3)]
                    want = SurfaceMixin._turn_to_angle(prev, d,
                                                       float(rule["angle"]))
                    worst = max(worst, math.sqrt(sum(
                        (want[k] - d[k]) ** 2 for k in range(3))))
                if rule.get("length") not in (None, ""):
                    size = math.sqrt(sum(c * c for c in d))
                    worst = max(worst, abs(size - float(rule["length"])))
            return worst

        def move(i, j, delta):
            """Répartit ``delta`` (à appliquer à j − i) entre i et j."""
            wi, wj = free(i), free(j)
            total = wi + wj
            if total == 0:
                return
            for k in range(3):
                pts[i][k] -= delta[k] * wi / total
                pts[j][k] += delta[k] * wj / total

        for _ in range(rounds):
            if residual() < tolerance:
                return pts
            for i, rule in enumerate(rules):
                if i + 1 >= len(pts) or not isinstance(rule, dict):
                    continue
                d = [pts[i + 1][k] - pts[i][k] for k in range(3)]
                axis = str(rule.get("axis") or "")
                if axis in ("X", "Y", "Z"):
                    k = "XYZ".index(axis)
                    move(i, i + 1, [0.0 if n == k else -d[n]
                                    for n in range(3)])
                elif rule.get("angle") not in (None, "") and i >= 1:
                    prev = [pts[i][k] - pts[i - 1][k] for k in range(3)]
                    want = SurfaceMixin._turn_to_angle(
                        prev, d, float(rule["angle"]))
                    move(i, i + 1, [want[k] - d[k] for k in range(3)])
                length = rule.get("length")
                if length not in (None, ""):
                    d = [pts[i + 1][k] - pts[i][k] for k in range(3)]
                    size = math.sqrt(sum(c * c for c in d))
                    if size > 1e-12:
                        grow = (float(length) - size) / size
                        move(i, i + 1, [c * grow for c in d])
        if residual() < 1e-5:
            return pts
        raise KernelError("règles d'esquisse 3D incompatibles : les points "
                          "liés, axes, angles et longueurs ne peuvent pas "
                          "tenir ensemble")

    @staticmethod
    def _turn_to_angle(prev, d, degrees):
        """``d`` tourné dans le plan (prev, d) pour faire ``degrees`` avec
        ``prev`` — sa longueur est gardée."""
        import math

        def norm(v):
            return math.sqrt(sum(c * c for c in v))

        size, base = norm(d), norm(prev)
        if size < 1e-9 or base < 1e-9:
            return d
        e1 = [c / base for c in prev]
        # Le plan : d ôté de sa composante sur prev ; s'ils sont alignés,
        # un axe quelconque perpendiculaire.
        side = [d[k] - sum(d[n] * e1[n] for n in range(3)) * e1[k]
                for k in range(3)]
        if norm(side) < 1e-9:
            helper = [0.0, 0.0, 1.0] if abs(e1[2]) < 0.9 else [1.0, 0.0, 0.0]
            side = [helper[k] - sum(helper[n] * e1[n] for n in range(3))
                    * e1[k] for k in range(3)]
        e2 = [c / norm(side) for c in side]
        t = math.radians(degrees)
        return [size * (math.cos(t) * e1[k] + math.sin(t) * e2[k])
                for k in range(3)]

    def _resolve_links(self, points, links):
        """Points liés : chaque lien ``{"object", "kind", "index"}`` donne
        la position du sommet ou du centre de cercle ; un lien ``True``
        (nouveau) se cherche au point cliqué. Rend (points, liens)."""
        pts = [list(p) for p in points]
        resolved = []
        for i, link in enumerate(list(links or ()) + [None] * len(pts)):
            if i >= len(pts):
                break
            if link is True:
                link = self._find_anchor(pts[i])
            if isinstance(link, dict):
                where = self._anchor_point(link)
                if where is None:
                    link = None
                else:
                    pts[i] = where
            resolved.append(link if isinstance(link, dict) else None)
        return pts, resolved

    def _anchor_shapes(self):
        """(nom, forme) des objets auxquels un point peut se lier : le
        corps actif et les surfaces et courbes affichées."""
        out = []
        body = self._body
        shape = getattr(body, "Shape", None) if body is not None else None
        if shape is not None and not shape.isNull():
            out.append((body.Name, shape))
        for obj in self._require_doc().Objects:
            if (self._is_surface_obj(obj) and not self._is_internal_tool(obj)
                    and self._curve_spec(obj) is None):
                shape = getattr(obj, "Shape", None)
                if shape is not None and not shape.isNull():
                    out.append((obj.Name, shape))
        return out

    def _find_anchor(self, point, tolerance=1e-3):
        import FreeCAD as App
        target = App.Vector(*point)
        for name, shape in self._anchor_shapes():
            for i, vertex in enumerate(shape.Vertexes):
                if (vertex.Point - target).Length < tolerance:
                    return {"object": name, "kind": "vertex", "index": i}
            for i, edge in enumerate(shape.Edges):
                center = self._circle_center(edge)
                if center is not None and (App.Vector(*center) - target
                                           ).Length < tolerance:
                    return {"object": name, "kind": "center", "index": i}
        return None

    def _anchor_point(self, link):
        obj = self._require_doc().getObject(str(link.get("object", "")))
        if obj is None or getattr(obj, "Shape", None) is None:
            return None
        shape, index = obj.Shape, int(link.get("index", -1))
        try:
            if link.get("kind") == "vertex":
                p = shape.Vertexes[index].Point
                return [p.x, p.y, p.z]
            center = self._circle_center(shape.Edges[index])
            return list(center) if center is not None else None
        except IndexError:
            return None

    def _store_curve(self, obj, vectors, spline, closed, rules=None,
                     links=None):
        if self._CURVE_POINTS not in obj.PropertiesList:
            obj.addProperty("App::PropertyVectorList", self._CURVE_POINTS,
                            "FreeSolid")
            obj.addProperty("App::PropertyBool", "FreeSolidSpline",
                            "FreeSolid")
            obj.addProperty("App::PropertyBool", "FreeSolidClosed",
                            "FreeSolid")
        setattr(obj, self._CURVE_POINTS, vectors)
        obj.FreeSolidSpline = bool(spline)
        obj.FreeSolidClosed = bool(closed)
        if rules is not None:
            import json
            clean = [{"axis": str((r or {}).get("axis") or ""),
                      "length": (r or {}).get("length"),
                      "angle": (r or {}).get("angle")}
                     for r in rules]
            self._stamp(obj, rules=json.dumps(clean))
        if links is not None:
            import json
            self._stamp(obj, links=json.dumps(
                [l if isinstance(l, dict) else None for l in links]))

    def _curve_spec(self, obj):
        """Points d'une spline 3D FreeSolid, ou None."""
        if self._CURVE_POINTS not in getattr(obj, "PropertiesList", ()):
            return None
        return {
            "points": [[round(v.x, 6), round(v.y, 6), round(v.z, 6)]
                       for v in getattr(obj, self._CURVE_POINTS)],
            "spline": bool(obj.FreeSolidSpline),
            "closed": bool(obj.FreeSolidClosed),
            "rules": self._curve_rules(obj),
            "links": self._curve_links(obj),
        }

    @staticmethod
    def _curve_links(obj):
        import json
        try:
            links = json.loads(getattr(obj, "FreeSolidLinks", "") or "[]")
        except ValueError:
            return []
        return links if isinstance(links, list) else []

    @staticmethod
    def _curve_rules(obj):
        import json
        try:
            rules = json.loads(getattr(obj, "FreeSolidRules", "") or "[]")
        except ValueError:
            return []
        return rules if isinstance(rules, list) else []

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
