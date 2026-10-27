"""Tracés d'esquisse complémentaires : point, arc tangent, rectangle 3
points et parallélogramme, arc d'ellipse, parabole, conique, spline par
pôles, rainure en arc.

Chaque op ajoute la géométrie et les relations qui la tiennent (comme un
tracé à la main), puis renvoie l'état de l'esquisse. Les imports FreeCAD
restent dans les méthodes : le module se charge sans FreeCAD.
"""

import math


def tangent_arc(start, direction, end):
    """Arc tangent à ``direction`` en ``start`` qui passe par ``end``.

    Renvoie ``(cx, cy, r, a1, a2, start_pos)`` — angles en radians, sens
    trigonométrique (a1 < a2), ``start_pos`` = 1 si ``start`` est le départ
    de l'arc stocké, 2 si c'est son arrivée (arc tourné vers la droite).
    None si ``end`` est dans l'axe de la tangente (pas d'arc).
    """
    tx, ty = direction
    norm = math.hypot(tx, ty)
    if norm < 1e-12:
        return None
    tx, ty = tx / norm, ty / norm
    nx, ny = -ty, tx  # à gauche de la tangente
    dx, dy = end[0] - start[0], end[1] - start[1]
    side = dx * nx + dy * ny
    if abs(side) < 1e-9:
        return None
    r = (dx * dx + dy * dy) / (2.0 * side)
    cx, cy = start[0] + nx * r, start[1] + ny * r
    a_start = math.atan2(start[1] - cy, start[0] - cx)
    a_end = math.atan2(end[1] - cy, end[0] - cx)
    if r > 0:  # tourne à gauche : départ → arrivée en sens trigo
        a1, a2, pos = a_start, a_end, 1
    else:      # tourne à droite : stocké de l'arrivée vers le départ
        a1, a2, pos = a_end, a_start, 2
    while a2 <= a1:
        a2 += 2 * math.pi
    return cx, cy, abs(r), a1, a2, pos


def rect3_corners(p1, p2, p3, parallelogram=False):
    """Quatre coins d'un rectangle (ou parallélogramme) donné par un côté
    ``p1``→``p2`` et un troisième point qui fixe l'autre côté."""
    ux, uy = p2[0] - p1[0], p2[1] - p1[1]
    hx, hy = p3[0] - p2[0], p3[1] - p2[1]
    if not parallelogram:
        length2 = ux * ux + uy * uy
        if length2 < 1e-18:
            return None
        along = (hx * ux + hy * uy) / length2
        hx, hy = hx - along * ux, hy - along * uy
    if abs(ux * hy - uy * hx) < 1e-9:
        return None
    return [tuple(p1), tuple(p2), (p2[0] + hx, p2[1] + hy),
            (p1[0] + hx, p1[1] + hy)]


def conic_weight(rho):
    """Poids du pôle d'angle d'une conique de paramètre ``rho`` :
    < 0,5 ellipse, 0,5 parabole, > 0,5 hyperbole."""
    rho = float(rho)
    if not 0 < rho < 1:
        return None
    return rho / (1.0 - rho)


class SketchDrawMixin:
    """Ops de tracé complémentaires (voir le docstring du module)."""

    def _add_closed_chain(self, sk, corners):
        """Lignes fermées par des coïncidences ; renvoie le premier id."""
        import Part
        import Sketcher
        V = self._app().Vector
        first = len(sk.Geometry)
        n = len(corners)
        for i in range(n):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % n]
            sk.addGeometry(Part.LineSegment(V(ax, ay, 0), V(bx, by, 0)),
                           False)
        for i in range(n):
            sk.addConstraint(Sketcher.Constraint(
                "Coincident", first + i, 2, first + (i + 1) % n, 1))
        return first

    def sketch_add_point(self, sketch, x, y, snaps=None):
        """Point d'esquisse — repère pour une cote, un perçage, un axe.
        ``snaps`` : ``at``, le point d'esquisse sur lequel il est posé."""
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        parsed = (None if snaps is None
                  else self._snap_targets(sk, "sketch_add_point", snaps))
        gid = sk.addGeometry(Part.Point(self._app().Vector(
            float(x), float(y), 0)), False)
        if parsed is not None:
            self._add_snap_constraints(
                sk, self._snap_links(sk, parsed, (("at", gid, 1),), {gid}))
        elif self._coincident_2d(x, y, 0, 0):
            sk.addConstraint(Sketcher.Constraint("Coincident", gid, 1, -1, 1))
        return self.sketch_state(sketch)

    def sketch_add_tangent_arc(self, sketch, geo, point, x, y):
        """Arc qui part tangent d'une extrémité de ligne ou d'arc et passe
        par (x, y) ; la tangence (qui vaut coïncidence) est posée."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        gid, pos = int(geo), int(point)
        if not 0 <= gid < len(sk.Geometry) or pos not in (1, 2):
            raise KernelError("arc tangent : partez de l'extrémité d'une "
                              "ligne ou d'un arc")
        base = sk.Geometry[gid]
        if base.TypeId == "Part::GeomLineSegment":
            a, b = base.StartPoint, base.EndPoint
            start = b if pos == 2 else a
            d = (b - a) if pos == 2 else (a - b)
        elif base.TypeId == "Part::GeomArcOfCircle":
            start = base.EndPoint if pos == 2 else base.StartPoint
            c = base.Center
            radial = start - c
            # Sens trigo : la tangente en un point est le rayon tourné de
            # +90° ; on la suit à l'arrivée, on la remonte au départ.
            d = self._app().Vector(-radial.y, radial.x, 0)
            if pos == 1:
                d = d * -1
        else:
            raise KernelError("arc tangent : partez de l'extrémité d'une "
                              "ligne ou d'un arc")
        arc = tangent_arc((start.x, start.y), (d.x, d.y),
                          (float(x), float(y)))
        if arc is None:
            raise KernelError("arc tangent : le point d'arrivée est dans "
                              "l'axe de la tangente — tracez une ligne")
        cx, cy, r, a1, a2, start_pos = arc
        V = self._app().Vector
        try:
            new = sk.addGeometry(Part.ArcOfCircle(
                Part.Circle(V(cx, cy, 0), V(0, 0, 1), r), a1, a2), False)
            sk.addConstraint(Sketcher.Constraint(
                "Tangent", gid, pos, new, start_pos))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_rect3(self, sketch, x1, y1, x2, y2, x3, y3,
                         parallelogram=False):
        """Rectangle incliné (un côté, puis la largeur) ou parallélogramme
        (deux côtés) ; côtés opposés parallèles, angle droit tenu pour le
        rectangle."""
        from engine.kernel import KernelError, _explain
        import Sketcher
        sk = self._get_sketch(sketch)
        corners = rect3_corners((float(x1), float(y1)),
                                (float(x2), float(y2)),
                                (float(x3), float(y3)), bool(parallelogram))
        if corners is None:
            raise KernelError("les trois points sont alignés")
        C = Sketcher.Constraint
        try:
            first = self._add_closed_chain(sk, corners)
            sk.addConstraint(C("Parallel", first, first + 2))
            sk.addConstraint(C("Parallel", first + 1, first + 3))
            if not parallelogram:
                sk.addConstraint(C("Perpendicular", first, first + 1))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_ellipse_arc(self, sketch, cx, cy, rx, ry, a1, a2,
                               angle=0.0):
        """Arc d'ellipse : centre, rayons, inclinaison (degrés) ; ``a1`` →
        ``a2`` en paramètre d'ellipse (radians, sens trigo)."""
        from engine.kernel import KernelError, _explain
        import Part
        sk = self._get_sketch(sketch)
        rx, ry = float(rx), float(ry)
        if rx <= 0 or ry <= 0:
            raise KernelError("les deux rayons doivent être positifs")
        a1, a2 = float(a1), float(a2)
        tilt = math.radians(float(angle))
        if ry > rx:
            # Le grand axe devient l'axe X de l'ellipse : paramètres
            # décalés d'un quart de tour.
            rx, ry = ry, rx
            tilt += math.pi / 2
            a1, a2 = a1 - math.pi / 2, a2 - math.pi / 2
        while a2 <= a1:
            a2 += 2 * math.pi
        try:
            ellipse = Part.Ellipse(self._app().Vector(float(cx), float(cy),
                                                      0), rx, ry)
            ellipse.AngleXU = tilt
            sk.addGeometry(Part.ArcOfEllipse(ellipse, a1, a2), False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_parabola(self, sketch, vx, vy, fx, fy, x1, y1, x2, y2):
        """Arc de parabole : sommet, foyer, puis les deux bouts (leur
        projection sur la tangente au sommet)."""
        from engine.kernel import KernelError, _explain
        import Part
        sk = self._get_sketch(sketch)
        vx, vy, fx, fy = (float(v) for v in (vx, vy, fx, fy))
        focal = math.hypot(fx - vx, fy - vy)
        if focal < 1e-9:
            raise KernelError("parabole : le foyer est sur le sommet")
        ax, ay = (fx - vx) / focal, (fy - vy) / focal
        bx, by = -ay, ax
        u1 = (float(x1) - vx) * bx + (float(y1) - vy) * by
        u2 = (float(x2) - vx) * bx + (float(y2) - vy) * by
        if abs(u2 - u1) < 1e-9:
            raise KernelError("parabole : les deux bouts sont confondus")
        try:
            parabola = Part.Parabola()
            parabola.Focal = focal
            parabola.Center = self._app().Vector(vx, vy, 0)
            parabola.AngleXU = math.atan2(ay, ax)
            sk.addGeometry(Part.ArcOfParabola(
                parabola, min(u1, u2), max(u1, u2)), False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_conic(self, sketch, x1, y1, x2, y2, ax, ay, rho=0.5):
        """Conique : deux bouts, le sommet où se croisent leurs tangentes,
        et ``rho`` (galbe : < 0,5 ellipse, 0,5 parabole, > 0,5
        hyperbole) — une B-spline rationnelle de degré 2."""
        from engine.kernel import KernelError, _explain
        import Part
        sk = self._get_sketch(sketch)
        weight = conic_weight(rho)
        if weight is None:
            raise KernelError("conique : rho doit être entre 0 et 1")
        p0 = (float(x1), float(y1))
        p2 = (float(x2), float(y2))
        apex = (float(ax), float(ay))
        if abs((p2[0] - p0[0]) * (apex[1] - p0[1])
               - (p2[1] - p0[1]) * (apex[0] - p0[0])) < 1e-9:
            raise KernelError("conique : le sommet est aligné avec les "
                              "deux bouts")
        V = self._app().Vector
        try:
            curve = Part.BSplineCurve()
            curve.buildFromPolesMultsKnots(
                [V(p0[0], p0[1], 0), V(apex[0], apex[1], 0),
                 V(p2[0], p2[1], 0)],
                [3, 3], [0.0, 1.0], False, 2, [1.0, weight, 1.0])
            sk.addGeometry(curve, False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_spline_poles(self, sketch, points):
        """Spline par points de contrôle (pôles) : la courbe est tirée vers
        eux sans y passer — degré 3 (moins avec 2 ou 3 pôles)."""
        from engine.kernel import KernelError, _explain
        import Part
        sk = self._get_sketch(sketch)
        if not isinstance(points, (list, tuple)) or len(points) < 3:
            raise KernelError("une spline demande au moins trois points")
        V = self._app().Vector
        poles = []
        for p in points:
            try:
                px, py = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            poles.append(V(px, py, 0))
        try:
            curve = Part.BSplineCurve()
            curve.buildFromPoles(poles, False, min(3, len(poles) - 1))
            sk.addGeometry(curve, False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_arc_slot(self, sketch, cx, cy, r, a1, a2, width):
        """Rainure en arc : l'arc médian (centre, rayon, angles) épaissi de
        ``width`` — deux arcs concentriques, deux bouts ronds."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        r, w = float(r), float(width)
        a1, a2 = float(a1), float(a2)
        while a2 <= a1:
            a2 += 2 * math.pi
        if w <= 0:
            raise KernelError("la largeur doit être positive")
        if r - w / 2.0 <= 1e-9:
            raise KernelError("rainure en arc : la largeur dépasse le "
                              "diamètre de l'arc")
        if a2 - a1 >= 2 * math.pi - 1e-6:
            raise KernelError("rainure en arc : l'arc doit rester ouvert")
        V = self._app().Vector
        z = V(0, 0, 1)
        center = V(float(cx), float(cy), 0)
        half = w / 2.0

        def at(angle):
            return V(center.x + r * math.cos(angle),
                     center.y + r * math.sin(angle), 0)

        base = len(sk.Geometry)
        C = Sketcher.Constraint
        try:
            sk.addGeometry(Part.ArcOfCircle(
                Part.Circle(center, z, r + half), a1, a2), False)
            sk.addGeometry(Part.ArcOfCircle(
                Part.Circle(at(a2), z, half), a2, a2 + math.pi), False)
            sk.addGeometry(Part.ArcOfCircle(
                Part.Circle(center, z, r - half), a1, a2), False)
            sk.addGeometry(Part.ArcOfCircle(
                Part.Circle(at(a1), z, half), a1 + math.pi,
                a1 + 2 * math.pi), False)
            sk.addConstraint(C("Tangent", base, 2, base + 1, 1))
            sk.addConstraint(C("Tangent", base + 1, 2, base + 2, 2))
            sk.addConstraint(C("Tangent", base + 2, 1, base + 3, 1))
            sk.addConstraint(C("Tangent", base + 3, 2, base, 1))
            # Bouts tangents aux deux arcs concentriques : leurs rayons
            # sont égaux d'office (une relation « égale » serait en trop).
            sk.addConstraint(C("Coincident", base, 3, base + 2, 3))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)
