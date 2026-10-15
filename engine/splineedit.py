"""Splines éditables : de la définition FreeSolid (points de passage et
poignées de tangente, ``splinemath``) à la B-spline FreeCAD, et retour.

La B-spline a un nœud à chaque point de passage : les points se relisent
sur n'importe quelle spline cubique (ou de degré moindre), même retouchée
par le solveur d'esquisse ou par le glisser d'un pôle. Le polygone de
contrôle est celui de la B-spline réduite (nœuds simples là où la courbe
est lisse) ; tirer un pôle redonne des points et des poignées.

Les imports FreeCAD restent dans les fonctions.
"""

from engine import splinemath as sm


def _reduce(curve, scale):
    """Multiplicité minimale à chaque nœud intérieur (forme inchangée) :
    les nœuds restent, ils marquent les points de passage."""
    tol = 1e-9 * max(1.0, scale)
    index = 2
    while index < len(curve.getKnots()):
        for target in (2, 1):
            if curve.getMultiplicity(index) > target:
                try:
                    curve.removeKnot(index, target, tol)
                except Exception:  # noqa: BLE001
                    break
        index += 1
    return curve


def build_bspline(points, closed=False, tangents=None):
    """B-spline cubique FreeCAD qui passe par ``points`` (pentes
    ``tangents``)."""
    import FreeCAD
    import Part
    pts = sm.as_points(points)
    spans = sm.controls(pts, closed, tangents)
    poles = [FreeCAD.Vector(*spans[0][0])]
    for span in spans:
        poles.extend(FreeCAD.Vector(*p) for p in span[1:])
    knots = sm.knots(pts, closed)
    mults = [4] + [3] * (len(knots) - 2) + [4]
    curve = Part.BSplineCurve()
    curve.buildFromPolesMultsKnots(poles, mults, knots, False, 3)
    scale = max((abs(c) for p in pts for c in p), default=1.0)
    return _reduce(curve, scale)


def spec_from_bspline(curve):
    """``(points, closed, tangents)`` d'une B-spline de degré ≤ 3, ou None
    (degré plus haut : seuls ses pôles se déplacent)."""
    c = curve.copy()
    if c.isPeriodic():
        c.setNotPeriodic()
    if c.Degree > 3:
        return None
    if c.Degree < 3:
        c.increaseDegree(3)
    if c.isRational():
        weights = c.getWeights()
        if max(weights) - min(weights) > 1e-9:
            return None
    knots = c.getKnots()
    for u in knots[1:-1]:
        c.insertKnot(u, 3, 1e-12)
    poles = [[p.x, p.y, p.z] for p in c.getPoles()]
    spans = [poles[3 * i:3 * i + 4] for i in range((len(poles) - 1) // 3)]
    first, last = poles[0], poles[-1]
    closed = all(abs(a - b) < 1e-7 for a, b in zip(first, last)) \
        and len(spans) >= 3
    try:
        points, tangents = sm.from_beziers(spans, closed)
    except ValueError:
        return None
    return points, closed, tangents


def _tip_of_joint(curve, points, closed, tangents, index):
    """``(point, côté, seul)`` si le pôle ``index`` est le bout d'une
    poignée en un point où la courbe n'est que tangente (nœud multiple,
    ou départ d'une courbe fermée) ; sinon None."""
    pts = sm.as_points(points)
    n = len(pts)
    pole = curve.getPole(index + 1)
    mults = curve.getMultiplicities()
    for i in range(n):
        if closed and i == 0:
            joint, alone = True, None
        elif 0 < i < n - 1 or (closed and i < n):
            mult = mults[i] if i < len(mults) else 1
            joint, alone = mult >= 2, mult >= 3
        else:
            joint, alone = False, False
        if not joint:
            continue
        tip_in, tip_out = sm.handle_tips(pts, closed, tangents, i)
        for side, tip in (("in", tip_in), ("out", tip_out)):
            if tip is None:
                continue
            gap = ((pole.x - tip[0]) ** 2 + (pole.y - tip[1]) ** 2
                   + (pole.z - tip[2]) ** 2) ** 0.5
            if gap < 1e-7 * max(1.0, abs(tip[0]), abs(tip[1]), abs(tip[2])):
                if alone is None:
                    m_in, m_out = sm.solve(pts, closed, tangents)
                    alone = abs(sm._norm(m_in[i]) - sm._norm(m_out[i])) > 1e-9
                return i, side, alone
    return None


class SplineEditMixin:
    """Ops sans état : curve_poles, curve_move_pole — le client garde la
    définition pendant l'édition et l'envoie à l'OK. Esquisse :
    sketch_set_spline remplace une spline par ses points et poignées."""

    def sketch_set_spline(self, sketch, geo, points, tangents=None,
                          closed=False):
        """Redessine la spline ``geo`` d'une esquisse par ses points de
        passage (2D) et ses poignées. La géométrie est remplacée à sa
        place : ses relations (extrémités coïncidentes, tangences…) restent
        et le solveur les tient."""
        from engine.kernel import KernelError, _explain
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if not 0 <= gid < len(sk.Geometry)                 or "BSpline" not in sk.Geometry[gid].TypeId:
            raise KernelError("spline : cliquez une spline")
        pts = [[float(p[0]), float(p[1]), 0.0] for p in points or ()]
        if len(pts) < 2:
            raise KernelError("une spline garde au moins deux points")
        flat = []
        for spec in sm.clean_tangents(tangents, len(pts)):
            if spec is not None:
                spec = dict(spec, dir=[spec["dir"][0], spec["dir"][1], 0.0])
            flat.append(spec)
        try:
            curve = build_bspline(pts, bool(closed), flat)
            construction = bool(sk.getConstruction(gid))
            geometry = sk.Geometry
            geometry[gid] = curve
            sk.Geometry = geometry
            if construction:
                sk.setConstruction(gid, True)
            sk.solve()
            sk.recompute()
        except ValueError as exc:
            raise KernelError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def curve_poles(self, points, closed=False, tangents=None):
        """Polygone de contrôle de la spline."""
        from engine.kernel import KernelError, _explain
        try:
            curve = build_bspline(points, bool(closed), tangents)
        except ValueError as exc:
            raise KernelError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return {"poles": [[p.x, p.y, p.z] for p in curve.getPoles()]}

    def curve_move_pole(self, points, index, point, closed=False,
                        tangents=None):
        """Tire le pôle ``index`` en ``point`` : rend les points et les
        poignées de la courbe obtenue."""
        from engine.kernel import KernelError, _explain
        import FreeCAD
        try:
            curve = build_bspline(points, bool(closed), tangents)
            count = curve.NbPoles
            i = int(index)
            if not 0 <= i < count:
                raise KernelError("pôle inconnu : {}".format(index))
            target = sm.as_points([point])[0]
            tip = _tip_of_joint(curve, points, bool(closed), tangents, i)
            if tip is not None:
                # Pôle = bout d'une poignée à un raccord seulement tangent :
                # le tirer seul casserait la tangence, on tire la poignée.
                at, side, alone = tip
                new_tangents = sm.drag_tip(points, bool(closed), tangents,
                                           at, side, target, alone)
                pts = sm.as_points(points)
                rebuilt = build_bspline(pts, bool(closed), new_tangents)
                return {"points": pts, "closed": bool(closed),
                        "tangents": new_tangents,
                        "poles": [[p.x, p.y, p.z]
                                  for p in rebuilt.getPoles()]}
            curve.setPole(i + 1, FreeCAD.Vector(*target))
            if closed and i in (0, count - 1):
                # Courbe fermée : le premier et le dernier pôle ne font qu'un.
                curve.setPole(count - i if i else count,
                              FreeCAD.Vector(*target))
            spec = spec_from_bspline(curve)
        except KernelError:
            raise
        except ValueError as exc:
            raise KernelError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        if spec is None:
            raise KernelError("ce pôle ne se déplace pas")
        new_points, new_closed, new_tangents = spec
        return {"points": new_points, "closed": bool(closed),
                "tangents": new_tangents,
                "poles": [[p.x, p.y, p.z] for p in curve.getPoles()]}
