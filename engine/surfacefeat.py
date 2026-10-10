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
        "Surface::Filling", "Surface::Extend",
        # Ajuster : la découpe (BOPTools) puis la pièce gardée
        # (CompoundTools) — fonctions Python livrées avec FreeCAD.
        "Part::FeaturePython",
    })

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

    def surface_fill(self, boundary):
        """Surface de remplissage : une peau tendue sur un contour fermé
        d'arêtes (bords de surfaces, courbes, esquisses, arêtes du solide)."""
        import Surface  # noqa: F401 — enregistre Surface::Filling
        links = self._boundary_links(boundary)

        def configure(obj):
            obj.BoundaryEdges = links

        return self._add_part_surface(
            "Surface::Filling", "Surface de remplissage", configure)

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
        if obj.TypeId == "Surface::Extend":
            face = getattr(obj, "Face", None)
            return {"kind": "extend",
                    "source": face[0].Name if face else None,
                    "distance": float(getattr(obj, "FreeSolidDistance", 0)),
                    "edge": (int(getattr(obj, "FreeSolidEdge", 0)) - 1
                             if getattr(obj, "FreeSolidEdge", 0) else None)}
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
            elif getattr(obj, "FreeSolidKind", "") == "trim":
                base = getattr(obj, "Base", None)
                if base is not None and getattr(base, "Base", None):
                    consumed.add(base.Base.Name)
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
            for name in str(getattr(obj, "FreeSolidSources", "")).split(";"):
                if name:
                    consumed.add(name)
        return consumed

    def _get_surface(self, name):
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(name))
        if obj is None or obj.TypeId not in self._SURFACE_TYPE_IDS:
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
