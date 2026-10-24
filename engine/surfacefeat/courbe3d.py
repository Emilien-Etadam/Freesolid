"""Courbe 3D : spline par points, règles (angle, longueur…), ancrages sur
la géométrie, aperçu.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class Curve3dMixin:
    def add_curve3d(self, points, spline=True, closed=False, rules=None,
                    links=None, tangents=None):
        """Spline 3D par points — l'esquisse 3D de FreeSolid : une
        trajectoire de balayage ou un bord de surface (B-spline qui passe
        par les points, ou polyligne). Les points restent rangés sur
        l'objet : la courbe se réédite (``edit_curve3d``). ``rules`` :
        une règle par segment, ``{"axis": "X"|"Y"|"Z"|"", "length": mm}``
        — appliquées en chaîne, elles restent attachées à la courbe.
        ``tangents`` : une poignée par point, None (pente libre) ou
        ``{"dir", "in", "out"}`` (voir ``splinemath``)."""
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        vectors, shape = self._curve_shape(points, spline, closed, tangents)
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Label = self._t("Spline 3D" if spline else "Polyligne 3D")
        self._store_curve(feature, vectors, spline, closed, rules, links,
                          tangents)
        feature.Shape = shape
        doc.recompute()
        return self.get_tree()

    def edit_curve3d(self, curve, points, spline=True, closed=False,
                     rules=None, links=None, tangents=None):
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
        if tangents is None and len(points) == len(spec["points"]):
            tangents = spec.get("tangents")
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        vectors, shape = self._curve_shape(points, spline, closed, tangents)
        self._store_curve(obj, vectors, spline, closed, rules, links,
                          tangents if tangents is not None else [])
        obj.Shape = shape
        for dependent in obj.InList:
            dependent.touch()
        self._recompute()
        return self.get_tree()

    def curve3d_preview(self, points, spline=True, closed=False,
                        rules=None, links=None, tangents=None):
        """Aperçu exact d'une spline 3D : la polyligne de la courbe que
        ``add_curve3d`` créerait, sans rien ajouter au document."""
        points, links = self._resolve_links(points, links)
        points = self.solve_curve_rules(
            points, rules, [i for i, l in enumerate(links) if l])
        _, shape = self._curve_shape(points, spline, closed, tangents)
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

    def _curve_shape(self, points, spline, closed, tangents=None):
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
        from engine import splinemath
        from engine.splineedit import build_bspline
        tangents = splinemath.clean_tangents(tangents, len(vectors))
        try:
            if spline and (len(vectors) >= 3 or any(tangents)):
                import Part
                # Courbe FreeSolid : points de passage et poignées.
                curve = build_bspline(points, bool(closed), tangents)
                shape = Part.Wire([curve.toShape()])
            else:
                shape = self._wire_through_points(
                    vectors, spline=False, closed=bool(closed))
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
                d = Curve3dMixin._turn_to_angle(prev, d, float(angle))
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
        return Curve3dMixin._relax_rules(pts, rules or [], fixed)

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
                    want = Curve3dMixin._turn_to_angle(prev, d,
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
                    want = Curve3dMixin._turn_to_angle(
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
                    and self._curve_spec(obj) is None
                    and self._sketch3d_spec(obj) is None):
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
                     links=None, tangents=None):
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
        if tangents is not None:
            import json
            from engine.splinemath import clean_tangents
            self._stamp(obj, tangents=json.dumps(
                clean_tangents(tangents, len(vectors))))

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
            "tangents": self._curve_tangents(obj),
        }

    def _curve_tangents(self, obj):
        import json
        from engine.splinemath import clean_tangents
        try:
            raw = json.loads(getattr(obj, "FreeSolidTangents", "") or "[]")
        except ValueError:
            raw = []
        count = len(getattr(obj, self._CURVE_POINTS))
        return clean_tangents(raw if isinstance(raw, list) else [], count)

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
