"""Références externes d'esquisse : arêtes de la pièce projetées et liées
(« convertir » associatif), courbe d'intersection du plan avec la pièce,
points de percée des courbes 3D.

FreeCAD range ces géométries hors de ``Geometry`` : ``ExternalGeo``, dont
les deux premières sont les axes H et V (GeoId -1, -2) ; la i-ème
référence ajoutée a le GeoId ``-3 - i``. Elles suivent la pièce à chaque
reconstruction. Une référence « définissante » entre dans le profil.
"""

#: GeoId de la première référence externe (après les axes H et V).
FIRST_EXTERNAL = -3


def geo_of(sk, gid):
    """La géométrie d'un GeoId : entité de l'esquisse (>= 0), axe ou
    référence externe (< 0)."""
    gid = int(gid)
    if gid >= 0:
        return sk.Geometry[gid]
    return sk.ExternalGeo[-gid - 1]


def external_count(sk):
    """Nombre de références externes (hors axes)."""
    return max(0, len(getattr(sk, "ExternalGeo", []) or []) - 2)


def is_geo(sk, gid):
    """Vrai si ``gid`` désigne une entité ou une référence existante."""
    gid = int(gid)
    if gid >= 0:
        return gid < len(sk.Geometry)
    return gid <= FIRST_EXTERNAL and -gid - 3 < external_count(sk)


class SketchRefMixin:
    """Ops de référence externe (voir le docstring du module)."""

    def _sketch_plane(self, sk):
        """Le plan de l'esquisse dans l'espace : (origine, normale)."""
        App = self._app()
        placement = sk.getGlobalPlacement() if hasattr(
            sk, "getGlobalPlacement") else sk.Placement
        return (placement.Base,
                placement.Rotation.multVec(App.Vector(0, 0, 1)))

    def _crosses_plane(self, shape, origin, normal, tolerance=1e-7):
        """La forme a des points des deux côtés du plan (ou dessus)."""
        sides = set()
        for vertex in shape.Vertexes:
            d = (vertex.Point - origin).dot(normal)
            sides.add(0 if abs(d) < tolerance else (1 if d > 0 else -1))
        if 0 in sides or (1 in sides and -1 in sides):
            return True
        # Courbe ou face qui revient : on échantillonne.
        try:
            points = shape.discretize(32) if hasattr(shape, "discretize") \
                else []
        except Exception:  # noqa: BLE001
            points = []
        signs = {1 if (p - origin).dot(normal) > 0 else -1 for p in points}
        return len(signs) > 1

    def _support_face(self, sk):
        """(objet, numéro de face) de la face porteuse, ou None."""
        support = (getattr(sk, "AttachmentSupport", None)
                   or getattr(sk, "Support", None))
        try:
            for obj, subs in list(support or ()):
                for sub in subs:
                    if str(sub).startswith("Face"):
                        return obj, int(str(sub)[4:])
        except Exception:  # noqa: BLE001
            pass
        return None

    def _pierce_binder(self, obj):
        """Lieur (dans le corps actif) qui suit la courbe ``obj`` ; un
        seul par courbe, réutilisé."""
        body = self._require_body()
        doc = self._require_doc()
        for other in body.Group:
            if other.TypeId == "PartDesign::SubShapeBinder" and getattr(
                    other, "FreeSolidPierce", "") == obj.Name:
                return other
        binder = body.newObject("PartDesign::SubShapeBinder", "Percee")
        binder.Support = [(obj, ("",))]
        binder.Visibility = False
        self._stamp(binder, pierce=obj.Name)
        self._mark_internal(binder)
        doc.recompute()
        return binder

    def sketch_reference(self, sketch, mode="edges", defining=True):
        """Ajoute des références liées à la pièce :

        - ``edges`` : les arêtes de la face porteuse, projetées (le
          « convertir » associatif : elles suivent la pièce) ;
        - ``intersection`` : la courbe où le plan coupe le solide ;
        - ``pierce`` : les points où les courbes 3D percent le plan.

        ``defining`` : les références entrent dans le profil (sinon, en
        construction). Renvoie l'état, avec ``referenced`` (le nombre)."""
        from engine.kernel import KernelError, _explain
        sk = self._get_sketch(sketch)
        doc = self._require_doc()
        before = external_count(sk)
        links = []
        if mode == "edges":
            found = self._support_face(sk)
            if found is None:
                raise KernelError("l'esquisse n'est pas posée sur une face "
                                  "de la pièce")
            obj, face_no = found
            face = obj.Shape.Faces[face_no - 1]
            for k, edge in enumerate(obj.Shape.Edges):
                if any(edge.isSame(e) for e in face.Edges):
                    links.append((obj.Name, "Edge%d" % (k + 1), False))
        elif mode == "intersection":
            body = self._require_body()
            tip = getattr(body, "Tip", None)
            if tip is None or not tip.Shape.Faces:
                raise KernelError("intersection : il faut un solide")
            origin, normal = self._sketch_plane(sk)
            for k, face in enumerate(tip.Shape.Faces):
                if self._crosses_plane(face, origin, normal):
                    links.append((tip.Name, "Face%d" % (k + 1), True))
        elif mode == "pierce":
            origin, normal = self._sketch_plane(sk)
            for obj in doc.Objects:
                if obj is sk or not hasattr(obj, "Shape") or \
                        obj.TypeId.startswith("Sketcher::"):
                    continue
                if self._curve_spec(obj) is None and \
                        obj.TypeId != "Part::Helix":
                    continue
                crossing = [k for k, edge in enumerate(obj.Shape.Edges)
                            if self._crosses_plane(edge, origin, normal)]
                if not crossing:
                    continue
                # Une esquisse de corps ne se lie pas hors de son corps :
                # un lieur dans le corps suit la courbe, on perce le lieur.
                binder = self._pierce_binder(obj)
                for k in crossing:
                    links.append((binder.Name, "Edge%d" % (k + 1), True))
        else:
            raise KernelError("référence inconnue : {}".format(mode))
        if not links:
            raise KernelError({
                "edges": "aucune arête sur la face porteuse",
                "intersection": "le plan de l'esquisse ne coupe pas le "
                                "solide",
                "pierce": "aucune courbe 3D ne perce le plan de "
                          "l'esquisse",
            }[mode])
        try:
            for name, sub, intersection in links:
                sk.addExternal(name, sub, bool(defining) and mode != "pierce",
                               intersection)
            doc.recompute()
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        state = self.sketch_state(sketch)
        state["referenced"] = external_count(sk) - before
        return state

    def sketch_silhouette(self, sketch):
        """Silhouette : les arêtes vues du solide, regardé de face depuis le
        plan de l'esquisse (contours apparents compris), projetées et
        bloquées dans l'esquisse."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        body = self._require_body()
        tip = getattr(body, "Tip", None)
        if tip is None or not tip.Shape.Solids:
            raise KernelError("silhouette : il faut un solide")
        try:
            import TechDraw
        except ImportError:
            raise KernelError("silhouette : module de projection "
                              "indisponible")
        App = self._app()
        placement = sk.getGlobalPlacement() if hasattr(
            sk, "getGlobalPlacement") else sk.Placement
        shape = tip.Shape.copy()
        shape.transformShape(placement.inverse().toMatrix())
        try:
            views = TechDraw.projectEx(shape, App.Vector(0, 0, 1))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        # 0 : arêtes vives vues ; 3 : contours apparents (silhouette).
        edges = [e for index in (0, 3) for e in views[index].Edges
                 if e.Length > 1e-6]
        if not edges:
            raise KernelError("silhouette : rien de visible depuis ce plan")
        added = []
        V = App.Vector
        try:
            for edge in edges:
                kind = type(edge.Curve).__name__
                a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
                if kind == "Line":
                    geo = Part.LineSegment(V(a.x, a.y, 0), V(b.x, b.y, 0))
                elif kind == "Circle" and edge.isClosed():
                    c = edge.Curve.Center
                    geo = Part.Circle(V(c.x, c.y, 0), V(0, 0, 1),
                                      edge.Curve.Radius)
                elif kind == "Circle":
                    m = edge.valueAt((edge.FirstParameter
                                      + edge.LastParameter) / 2)
                    p1, pm, p2 = (V(q.x, q.y, 0) for q in (a, m, b))
                    geo = Part.ArcOfCircle(p1, pm, p2)
                    if geo.Axis.z < 0:  # l'esquisse veut des arcs en +Z
                        geo = Part.ArcOfCircle(p2, pm, p1)
                else:
                    geo = edge.toNurbs().Edges[0].Curve
                added.append(sk.addGeometry(geo, False))
            for gid in added:
                sk.addConstraint(Sketcher.Constraint("Block", gid))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        state = self.sketch_state(sketch)
        state["referenced"] = len(added)
        return state
