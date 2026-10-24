"""Surfaces et solide : couper par une surface, supprimer ou remplacer une
face, surface médiane.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class SurfaceSolidMixin:
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
        if "vchamfer" in stamps:
            return self._vertex_chamfered(base_shape, stamps["vchamfer"])
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
