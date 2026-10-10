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
        import Surface  # noqa: F401 — enregistre Surface::Filling
        links = self._boundary_links(boundary)
        faces = [self._adjacent_face(obj, sub) if tangent else ""
                 for obj, sub in links]

        def configure(obj):
            obj.BoundaryEdges = links
            if any(faces):
                obj.BoundaryFaces = faces
                obj.BoundaryOrder = [1 if face else 0 for face in faces]

        return self._add_part_surface(
            "Surface::Filling", "Surface de remplissage", configure)

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
            try:
                Part.Wire(Part.__sortEdges__(edges))
            except Exception:  # noqa: BLE001
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

    def surface_trim(self, surface, tool, point=None):
        """Ajuster une surface par une autre : la découpe garde la partie
        la plus proche du point cliqué (la plus grande sans point)."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import BOPTools.SplitFeatures as split_features
        import CompoundTools.CompoundFilter as compound_filter
        doc = self._require_doc()
        src = self._get_surface(surface)
        cutter = self._get_surface(tool)
        if src.Name == cutter.Name:
            raise KernelError("la surface et l'outil doivent être différents")
        if not src.Shape.Faces or not cutter.Shape.Faces:
            raise KernelError("ajuster demande deux surfaces")
        pieces = self._trim_pieces(src.Shape, cutter.Shape)
        if len(pieces) < 2:
            raise KernelError("l'outil ne coupe pas la surface")
        keep = self._nearest_piece(pieces, point)
        slicer = split_features.makeSlice("Decoupe")
        slicer.Base = src
        slicer.Tools = [cutter]
        slicer.Mode = "Split"
        self._mark_internal(slicer)
        try:
            kept = compound_filter.makeCompoundFilter("Surface")
            kept.Base = slicer
            kept.FilterType = "specific items"
            kept.items = str(keep)
            kept.Label = self._t("Surface ajustée")
            self._stamp(kept, kind="trim")
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            for obj in [o for o in (locals().get("kept"), slicer) if o]:
                try:
                    doc.removeObject(obj.Name)
                except Exception:
                    pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

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

    def add_surface_cut(self, surface, flip=False):
        """Couper le solide avec une surface : tout ce qui est du côté de
        la normale (ou de l'autre, ``flip``) part. La surface balaie un
        demi-espace (extrusion paramétrique), combiné en soustraction dans
        l'historique — la coupe suit la surface quand elle change."""
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
            problem = ("la surface ne coupe pas le solide — elle doit le "
                       "traverser de part en part")
        elif after < 1e-6 * before:
            problem = ("la surface enlève tout le solide — inversez le côté")
        if problem:
            self._drop_failed_feature(body, doc, tip, tip.BaseFeature)
            discard()
            self._recompute()
            raise KernelError(problem)
        tip.Label = self._t("Couper avec une surface")
        self._stamp(tip, cutsurface=src.Name, cutflip=int(bool(flip)))
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
        for i, feature in enumerate(features):
            last = i == len(features) - 1
            feature.Label = self._t(label if last else label + " — ajout")
            self._stamp(feature, **feature_stamps)
        return self.get_tree()

    def _refresh_frozen_shapes(self):
        """Recalcule les formes figées qui dépendent d'une fonction du
        corps (supprimer, remplacer une face) ; vrai si l'une a changé."""
        doc = self._require_doc()
        changed = False
        for obj in doc.Objects:
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

    def edit_surface_cut(self, feature, flip):
        """Rééditer une coupe par surface : garder l'autre côté."""
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
        if flip != bool(obj.FreeSolidCutflip):
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
        return {"surface": name, "flip": bool(obj.FreeSolidCutflip)}

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
            elif obj.TypeId == "Part::Offset" and getattr(obj, "Fill", False):
                source = getattr(obj, "Source", None)
                if source is not None:
                    consumed.add(source.Name)
            if (obj.TypeId == "Part::Extrusion"
                    and getattr(obj, "FreeSolidSurfaceTool", False)):
                # Demi-espace d'une coupe par surface : la surface a servi.
                base = getattr(obj, "Base", None)
                if base is not None:
                    consumed.add(base.Name)
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
        """Coudre des surfaces ; reste figé (pas d'objet Part paramétrique
        natif pour la couture). Si la peau est fermée, elle devient un
        solide — le geste « coudre puis solidifier »."""
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
            closed = shell.isClosed()
            shape = Part.makeSolid(shell) if closed else shell
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        tree = self._add_surface(
            shape, "Solide cousu" if closed else "Surface cousue")
        # Les surfaces cousues sont consommées : la couture les remplace.
        sewn = self._require_doc().getObject(tree["surfaces"][-1]["name"])
        self._stamp(sewn, sources=";".join(str(n) for n in surfaces))
        return self.get_tree()

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

    def add_curve3d(self, points, spline=True, closed=False):
        """Spline 3D par points — l'esquisse 3D de FreeSolid : une
        trajectoire de balayage ou un bord de surface (B-spline qui passe
        par les points, ou polyligne). Les points restent rangés sur
        l'objet : la courbe se réédite (``edit_curve3d``)."""
        vectors, shape = self._curve_shape(points, spline, closed)
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Label = self._t("Spline 3D" if spline else "Polyligne 3D")
        self._store_curve(feature, vectors, spline, closed)
        feature.Shape = shape
        doc.recompute()
        return self.get_tree()

    def edit_curve3d(self, curve, points, spline=True, closed=False):
        """Rééditer une spline 3D : nouveaux points, les surfaces et
        balayages qui l'utilisent suivent."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(curve))
        if obj is None or self._curve_spec(obj) is None:
            raise KernelError("courbe 3D inconnue : {}".format(curve))
        vectors, shape = self._curve_shape(points, spline, closed)
        self._store_curve(obj, vectors, spline, closed)
        obj.Shape = shape
        for dependent in obj.InList:
            dependent.touch()
        self._recompute()
        return self.get_tree()

    def curve3d_preview(self, points, spline=True, closed=False):
        """Aperçu exact d'une spline 3D : la polyligne de la courbe que
        ``add_curve3d`` créerait, sans rien ajouter au document."""
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

    def _store_curve(self, obj, vectors, spline, closed):
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

    def _curve_spec(self, obj):
        """Points d'une spline 3D FreeSolid, ou None."""
        if self._CURVE_POINTS not in getattr(obj, "PropertiesList", ()):
            return None
        return {
            "points": [[round(v.x, 6), round(v.y, 6), round(v.z, 6)]
                       for v in getattr(obj, self._CURVE_POINTS)],
            "spline": bool(obj.FreeSolidSpline),
            "closed": bool(obj.FreeSolidClosed),
        }

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
