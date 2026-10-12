"""Outils d'édition d'esquisse : chanfrein, prolonger, scinder, déplacer /
copier / tourner / mettre à l'échelle, répétition circulaire.

Les imports FreeCAD restent dans les méthodes : le module se charge sans
FreeCAD (les fonctions pures sont testées en CI).
"""

import math

#: Relations recopiées quand une sélection est tournée ou mise à
#: l'échelle : celles qui ne dépendent pas des axes de l'esquisse.
_FREE_RELATIONS = frozenset({
    "Coincident", "Tangent", "Parallel", "Perpendicular", "Equal",
    "PointOnObject", "Symmetric", "Angle", "Distance", "Radius", "Diameter",
})
#: Relations liées aux axes : gardées seulement sans rotation.
_AXIS_RELATIONS = frozenset({"Horizontal", "Vertical", "DistanceX",
                             "DistanceY"})
#: Cotes mises à l'échelle avec la sélection.
_LENGTHS = frozenset({"Distance", "DistanceX", "DistanceY", "Radius",
                      "Diameter"})


def line_intersection(a1, a2, b1, b2):
    """Croisement des droites (a1 a2) et (b1 b2), ou None si parallèles."""
    dax, day = a2[0] - a1[0], a2[1] - a1[1]
    dbx, dby = b2[0] - b1[0], b2[1] - b1[1]
    den = dax * dby - day * dbx
    if abs(den) < 1e-12:
        return None
    t = ((b1[0] - a1[0]) * dby - (b1[1] - a1[1]) * dbx) / den
    return (a1[0] + t * dax, a1[1] + t * day)


def copied_relation(kind, angle, scale):
    """Une relation entre entités copiées : à garder (et sa valeur à
    multiplier par ``scale`` pour une longueur) ? ``(keep, factor)``."""
    rotated = abs(math.remainder(angle, 2 * math.pi)) > 1e-12
    if kind in _AXIS_RELATIONS and rotated:
        return False, 1.0
    if kind not in _FREE_RELATIONS | _AXIS_RELATIONS:
        return False, 1.0
    return True, (scale if kind in _LENGTHS else 1.0)


class SketchEditMixin:
    """Ops d'édition (voir le docstring du module)."""

    def sketch_chamfer(self, sketch, geo1, geo2, x1, y1, x2, y2, distance,
                       distance2=None):
        """Chanfrein entre deux lignes : chacune est raccourcie de sa
        distance depuis le coin, un segment les relie. Le coin reste comme
        point de construction, les deux distances sont cotées."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        d1 = float(distance)
        d2 = float(distance2) if distance2 not in (None, "") else d1
        if d1 <= 0 or d2 <= 0:
            raise KernelError("la distance doit être positive")
        ids = (int(geo1), int(geo2))
        lines = []
        for gid in ids:
            if not 0 <= gid < len(sk.Geometry) or \
                    sk.Geometry[gid].TypeId != "Part::GeomLineSegment":
                raise KernelError("chanfrein : cliquez deux lignes")
            lines.append(sk.Geometry[gid])
        pts = [(p.x, p.y) for g in lines for p in (g.StartPoint, g.EndPoint)]
        corner = line_intersection(pts[0], pts[1], pts[2], pts[3])
        if corner is None:
            raise KernelError("chanfrein : les deux lignes sont parallèles")
        V = self._app().Vector
        C = Sketcher.Constraint
        ends = []
        for gid, g, d in zip(ids, lines, (d1, d2)):
            a, b = g.StartPoint, g.EndPoint
            near_end = 1 if (math.hypot(a.x - corner[0], a.y - corner[1])
                             < math.hypot(b.x - corner[0], b.y - corner[1])) else 2
            far = b if near_end == 1 else a
            length = math.hypot(far.x - corner[0], far.y - corner[1])
            if d >= length - 1e-9:
                raise KernelError("chanfrein : la distance dépasse la ligne")
            ux, uy = (far.x - corner[0]) / length, (far.y - corner[1]) / length
            ends.append((gid, near_end,
                         V(corner[0] + d * ux, corner[1] + d * uy, 0)))
        try:
            for gid, pos, _ in ends:
                # La coïncidence du coin est partagée : la première
                # suppression emporte aussi celle de l'autre ligne.
                try:
                    sk.delConstraintOnPoint(gid, pos)
                except Exception:  # noqa: BLE001
                    pass
            for gid, pos, target in ends:
                sk.moveGeometry(gid, pos, target, False)
            point = sk.addGeometry(Part.Point(V(corner[0], corner[1], 0)),
                                   True)
            bevel = sk.addGeometry(Part.LineSegment(ends[0][2], ends[1][2]),
                                   False)
            sk.addConstraint(C("Coincident", bevel, 1, ends[0][0], ends[0][1]))
            sk.addConstraint(C("Coincident", bevel, 2, ends[1][0], ends[1][1]))
            for gid, pos, _ in ends:
                sk.addConstraint(C("PointOnObject", point, 1, gid))
            sk.addConstraint(C("Distance", point, 1, ends[0][0], ends[0][1], d1))
            sk.addConstraint(C("Distance", point, 1, ends[1][0], ends[1][1], d2))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_extend(self, sketch, geo, x, y):
        """Prolonger : le bout de la ligne ou de l'arc le plus proche du
        clic va jusqu'à la première entité qu'il rencontre."""
        from engine.kernel import KernelError, _explain
        import Part
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if not 0 <= gid < len(sk.Geometry):
            raise KernelError("prolonger : cliquez une ligne ou un arc")
        g = sk.Geometry[gid]
        V = self._app().Vector
        click = V(float(x), float(y), 0)
        if g.TypeId not in ("Part::GeomLineSegment", "Part::GeomArcOfCircle"):
            raise KernelError("prolonger : cliquez une ligne ou un arc")
        pos = 1 if (g.StartPoint - click).Length < (g.EndPoint - click).Length \
            else 2
        end = g.StartPoint if pos == 1 else g.EndPoint
        if g.TypeId == "Part::GeomLineSegment":
            other = g.EndPoint if pos == 1 else g.StartPoint
            carrier = Part.Line(other, end)
            direction = end - other
            direction.normalize()
        else:
            carrier = Part.Circle(g.Center, V(0, 0, 1), g.Radius)
        best = None
        for oid, og in enumerate(sk.Geometry):
            if oid == gid or og.TypeId == "Part::GeomPoint":
                continue
            try:
                hits = carrier.intersectCC(og, 1e-7)
            except Exception:  # noqa: BLE001
                hits = []
            edge = og.toShape()
            for hit in hits:
                p = V(hit.X, hit.Y, 0)
                if edge.distToShape(Part.Vertex(p))[0] > 1e-6:
                    continue
                if g.TypeId == "Part::GeomLineSegment":
                    gain = (p - end).dot(direction)
                else:
                    angle = math.atan2(p.y - g.Center.y, p.x - g.Center.x)
                    if pos == 2:
                        gain = (angle - g.LastParameter) % (2 * math.pi)
                    else:
                        gain = (g.FirstParameter - angle) % (2 * math.pi)
                    span = g.LastParameter - g.FirstParameter
                    if gain >= 2 * math.pi - span - 1e-9:
                        continue
                if gain > 1e-7 and (best is None or gain < best):
                    best = gain
        if best is None:
            raise KernelError("prolonger : rien à rejoindre dans ce sens")
        try:
            sk.extend(gid, float(best), pos)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_split(self, sketch, geo, x, y):
        """Scinder une entité au point cliqué (deux morceaux coïncidents)."""
        from engine.kernel import KernelError, _explain
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if not 0 <= gid < len(sk.Geometry):
            raise KernelError("scinder : cliquez une entité")
        try:
            sk.split(gid, self._app().Vector(float(x), float(y), 0))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _copy_transformed(self, sk, ids, matrix_fn, angle, scale):
        """Ajoute une copie transformée des entités ``ids`` et des
        relations qui ne lient qu'elles ; renvoie {ancien: nouveau}."""
        import Sketcher
        mapping = {}
        for gid in ids:
            g = sk.Geometry[gid].copy()
            matrix_fn(g)
            mapping[gid] = sk.addGeometry(
                g, bool(sk.getConstruction(gid)))
        for c in list(sk.Constraints):
            refs = [r for r in (c.First, c.Second, c.Third)
                    if r is not None and r > -2000]
            if not refs or any(r not in mapping for r in refs):
                continue
            keep, factor = copied_relation(c.Type, angle, scale)
            if not keep:
                continue
            args = [c.Type]
            pos = [int(getattr(p, "value", p) or 0)
                   for p in (c.FirstPos, c.SecondPos, c.ThirdPos)]
            # Recompose la relation sur les copies, selon sa forme.
            geos = [mapping[r] for r in (c.First, c.Second, c.Third)
                    if r is not None and r > -2000]
            if len(geos) == 1:
                args += [geos[0]] + ([pos[0]] if pos[0] else [])
            elif len(geos) == 2:
                args += [geos[0]] + ([pos[0]] if pos[0] else []) \
                    + [geos[1]] + ([pos[1]] if pos[1] else [])
            else:
                args += [geos[0], pos[0], geos[1], pos[1], geos[2]] \
                    + ([pos[2]] if pos[2] else [])
            if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius",
                          "Diameter", "Angle"):
                args.append(float(c.Value) * factor)
            try:
                new = sk.addConstraint(Sketcher.Constraint(*args))
                if not getattr(c, "Driving", True):
                    sk.setDriving(new, False)
            except Exception:  # noqa: BLE001 — forme rare : on la saute
                pass
        return mapping

    def sketch_transform(self, sketch, geos, dx=0.0, dy=0.0, angle=0.0,
                         cx=0.0, cy=0.0, scale=1.0, copy=False):
        """Déplacer, tourner (``angle`` en degrés autour de cx, cy) ou
        mettre à l'échelle des entités — ou les copier ainsi
        (``copy``). Sans copie, les entités sont remplacées par leur image
        et gardent leurs relations internes ; les relations vers le reste
        de l'esquisse tombent (sauf pour une simple translation)."""
        from engine.kernel import KernelError, _explain
        import FreeCAD as App
        sk = self._get_sketch(sketch)
        ids = sorted({int(g) for g in (geos or ())})
        if not ids or any(not 0 <= g < len(sk.Geometry) for g in ids):
            raise KernelError("sélectionnez les entités à transformer")
        scale = float(scale)
        if scale <= 0:
            raise KernelError("l'échelle doit être positive")
        theta = math.radians(float(angle))
        V = App.Vector
        center = V(float(cx), float(cy), 0)
        shift = V(float(dx), float(dy), 0)
        try:
            if not copy and abs(theta) < 1e-12 and abs(scale - 1) < 1e-12:
                sk.addMove(ids, shift)
                return self.sketch_state(sketch)

            def apply(g):
                if abs(scale - 1) > 1e-12:
                    g.scale(center, scale)
                if abs(theta) > 1e-12:
                    g.rotate(App.Placement(
                        V(0, 0, 0),
                        App.Rotation(V(0, 0, 1), math.degrees(theta)),
                        center))
                if shift.Length > 0:
                    g.translate(shift)

            self._copy_transformed(sk, ids, apply, theta, scale)
            if not copy:
                sk.delGeometries(ids)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_polar_array(self, sketch, geos, cx, cy, count, angle=360.0):
        """Répétition circulaire : ``count`` exemplaires (l'original
        compris) répartis sur ``angle`` degrés autour de (cx, cy)."""
        from engine.kernel import KernelError, _explain
        import FreeCAD as App
        sk = self._get_sketch(sketch)
        ids = sorted({int(g) for g in (geos or ())})
        if not ids or any(not 0 <= g < len(sk.Geometry) for g in ids):
            raise KernelError("sélectionnez les entités à répéter")
        count = int(count)
        if count < 2:
            raise KernelError("au moins deux exemplaires")
        span = float(angle)
        step = span / count if abs(abs(span) - 360) < 1e-9 \
            else span / (count - 1)
        V = App.Vector
        center = V(float(cx), float(cy), 0)
        try:
            for k in range(1, count):
                turn = step * k

                def apply(g, turn=turn):
                    g.rotate(App.Placement(
                        V(0, 0, 0), App.Rotation(V(0, 0, 1), turn), center))

                self._copy_transformed(sk, ids, apply, math.radians(turn), 1)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)
