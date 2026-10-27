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

    # -- arêtes de la pièce visées par un accrochage ------------------------

    @staticmethod
    def _same_edge(a, b, tolerance=1e-6):
        """Deux arêtes de formes différentes sont-elles la même courbe ?
        Même longueur, mêmes bouts (dans un sens ou l'autre), et le milieu
        de l'une sur l'autre."""
        import Part
        if abs(a.Length - b.Length) > tolerance * max(1.0, a.Length):
            return False
        ends_a = [a.valueAt(a.FirstParameter), a.valueAt(a.LastParameter)]
        ends_b = [b.valueAt(b.FirstParameter), b.valueAt(b.LastParameter)]
        if not any(all(p.distanceToPoint(q) < tolerance
                       for p, q in zip(ends_a, order))
                   for order in (ends_b, ends_b[::-1])):
            return False
        mid = a.valueAt((a.FirstParameter + a.LastParameter) / 2)
        return b.distToShape(Part.Vertex(mid))[0] < tolerance

    def _model_edge_link(self, sk, edge):
        """(objet, « EdgeN ») : une fonction du corps qui porte l'arête
        ``edge`` de la pièce et ne dépend pas de l'esquisse — le dernier
        volume si l'esquisse vient après lui, sinon le dernier avant elle.
        None si aucune ne la porte (une arête faite après l'esquisse
        qu'on réédite)."""
        body = self._require_body()
        group = list(body.Group)
        before = group[:group.index(sk)] if sk in group else group
        tip = getattr(body, "Tip", None)
        for obj in [tip] + before[::-1]:
            if (obj is None or obj is sk
                    or not obj.isDerivedFrom("PartDesign::Feature")
                    or sk in (obj.OutListRecursive or [])):
                continue
            shape = getattr(obj, "Shape", None)
            for j, other in enumerate(getattr(shape, "Edges", None) or []):
                if self._same_edge(edge, other):
                    return obj, "Edge%d" % (j + 1)
        return None

    def _edge_points(self, sk, edge):
        """Les points d'une arête de la pièce dans l'esquisse : 1 son
        départ, 2 sa fin, 3 son centre (cercle, arc)."""
        placement = sk.getGlobalPlacement() if hasattr(
            sk, "getGlobalPlacement") else sk.Placement
        inverse = placement.inverse()
        points = {1: edge.valueAt(edge.FirstParameter),
                  2: edge.valueAt(edge.LastParameter)}
        center = getattr(edge.Curve, "Center", None)
        if center is not None:
            points[3] = center
        return {p: inverse.multVec(v) for p, v in points.items()}

    def _external_points(self, sk, gid, points, tolerance=1e-5):
        """Le point de la référence ``gid`` sur chacun des ``points``
        (``{point de l'arête: Vector}``) qu'elle a : ``{p: pos}``."""
        from engine.sketchsnap import snap_positions
        App = self._app()
        out = {}
        for p, where in points.items():
            flat = App.Vector(where.x, where.y, 0)
            for pos in snap_positions(geo_of(sk, gid).TypeId):
                try:
                    there = sk.getPoint(gid, pos)
                except Exception:  # noqa: BLE001 - point absent
                    continue
                if flat.distanceToPoint(there) < tolerance:
                    out[p] = pos
                    break
        return out

    def _external_of_edge(self, sk, edge, points):
        """La référence déjà dans l'esquisse qui reproduit l'arête : ses
        points tombent sur ceux de l'arête (un cercle : son centre et son
        rayon). None s'il n'y en a pas."""
        from engine.sketchsnap import snap_positions
        for k in range(external_count(sk)):
            gid = FIRST_EXTERNAL - k
            geo = geo_of(sk, gid)
            found = self._external_points(sk, gid, points)
            if geo.TypeId == "Part::GeomCircle":
                radius = getattr(edge.Curve, "Radius", None)
                if (3 in found and radius is not None and edge.isClosed()
                        and abs(geo.Radius - radius) < 1e-6):
                    return gid
            # Les deux bouts, et un centre des deux côtés ou d'aucun : une
            # ligne n'est pas l'arc qui a les mêmes bouts.
            elif ({1, 2} <= set(found) and found[1] != found[2]
                  and (3 in snap_positions(geo.TypeId)) == (3 in points)
                  and (3 not in points or 3 in found)):
                return gid
        return None

    def _model_edge_refs(self, sk, edges):
        """Chaque arête ``k`` de la pièce qu'un accrochage nomme : la
        référence qui la reproduit dans l'esquisse — déjà là, ou ajoutée,
        liée à la fonction qui la porte et hors du profil — avec le point
        de la référence pour chaque point de l'arête. None : l'esquisse ne
        peut pas la lier, l'accrochage tombe (voir with_model_edges)."""
        from engine.kernel import KernelError
        shape = getattr(self._require_body(), "Shape", None)
        count = len(shape.Edges) if shape is not None else 0
        for k in edges:
            if not 0 <= k < count:
                raise KernelError(
                    "accrochage : arête {} de la pièce introuvable".format(k))
        refs = {}
        for k in sorted(edges):
            edge = shape.Edges[k]
            points = self._edge_points(sk, edge)
            gid = self._external_of_edge(sk, edge, points)
            if gid is None:
                link = self._model_edge_link(sk, edge)
                before = external_count(sk)
                if link is not None:
                    try:
                        sk.addExternal(link[0].Name, link[1], False, False)
                    except Exception:  # noqa: BLE001 - refusée : sans relation
                        pass
                if external_count(sk) > before:
                    gid = FIRST_EXTERNAL - before
            refs[k] = None if gid is None else {
                "geo": gid, "points": self._external_points(sk, gid, points)}
        return refs

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
