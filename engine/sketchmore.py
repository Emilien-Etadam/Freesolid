"""Esquisse — fonctions complémentaires : texte, coin, courbe par
équation, réparation, définition complète, outils de spline, blocs,
image de fond conservée.

Les imports FreeCAD restent dans les méthodes : le module se charge sans
FreeCAD (l'évaluateur d'équations est testé en CI).
"""

import ast
import json
import math

#: Ce qu'une équation de courbe peut utiliser : la variable t, des
#: constantes et des fonctions mathématiques — rien d'autre.
_EQ_NAMES = {"pi": math.pi, "e": math.e}
_EQ_FUNCS = {name: getattr(math, name) for name in (
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "sqrt", "exp", "log", "log10", "floor", "ceil")}
_EQ_FUNCS["abs"] = abs
_EQ_FUNCS["pow"] = pow
_EQ_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name,
             ast.Load, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div,
             ast.Pow, ast.Mod, ast.USub, ast.UAdd)


class EquationError(ValueError):
    """Équation refusée (syntaxe, nom inconnu, construction interdite)."""


def compile_equation(text):
    """Équation ``f(t)`` → fonction Python, après contrôle : seuls t,
    pi, e, les nombres, + - * / ** % et les fonctions mathématiques
    usuelles passent. Lève EquationError sinon."""
    source = str(text).replace("^", "**").strip()
    if not source:
        raise EquationError("équation vide")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError:
        raise EquationError("équation illisible : {}".format(text))
    for node in ast.walk(tree):
        if not isinstance(node, _EQ_NODES):
            raise EquationError("construction interdite dans l'équation : "
                                "{}".format(type(node).__name__))
        if isinstance(node, ast.Name) and node.id != "t" and \
                node.id not in _EQ_NAMES and node.id not in _EQ_FUNCS:
            raise EquationError("nom inconnu dans l'équation : {}".format(
                node.id))
        if isinstance(node, ast.Call) and not (
                isinstance(node.func, ast.Name)
                and node.func.id in _EQ_FUNCS):
            raise EquationError("fonction interdite dans l'équation")
        if isinstance(node, ast.Constant) and not isinstance(
                node.value, (int, float)):
            raise EquationError("seuls les nombres sont permis")
    code = compile(tree, "<équation>", "eval")
    scope = {"__builtins__": {}, **_EQ_NAMES, **_EQ_FUNCS}

    def evaluate(t):
        return float(eval(code, scope, {"t": float(t)}))  # noqa: S307

    return evaluate


def equation_points(x_expr, y_expr, t0, t1, count):
    """Points (x(t), y(t)) régulièrement espacés en t."""
    fx, fy = compile_equation(x_expr), compile_equation(y_expr)
    count = max(3, min(int(count), 400))
    points = []
    for i in range(count):
        t = float(t0) + (float(t1) - float(t0)) * i / (count - 1)
        try:
            x, y = fx(t), fy(t)
        except (ValueError, ZeroDivisionError, OverflowError):
            raise EquationError("l'équation n'est pas définie en t = "
                                "{}".format(round(t, 4)))
        if not (math.isfinite(x) and math.isfinite(y)):
            raise EquationError("l'équation n'est pas définie en t = "
                                "{}".format(round(t, 4)))
        points.append((x, y))
    return points


class SketchMoreMixin:
    """Ops complémentaires (voir le docstring du module)."""

    # ---------- texte ----------

    def sketch_add_text(self, sketch, text, x=0.0, y=0.0, size=8.0,
                        angle=0.0, font=None):
        """Texte d'esquisse : les contours des lettres deviennent de la
        géométrie (bloquée) — à extruder, graver ou découper."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        text = str(text)
        if not text.strip():
            raise KernelError("texte vide")
        if float(size) <= 0:
            raise KernelError("la hauteur doit être positive")
        App = self._app()
        try:
            chars = Part.makeWireString(text, self._find_font(font),
                                        float(size), 0)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        turn = App.Placement(App.Vector(float(x), float(y), 0),
                             App.Rotation(App.Vector(0, 0, 1), float(angle)))
        added = []
        try:
            for wires in chars:
                for wire in wires:
                    for edge in wire.Edges:
                        edge = edge.copy()
                        edge.transformShape(turn.toMatrix())
                        curve = edge.Curve
                        if type(curve).__name__ == "Line":
                            a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
                            if (a - b).Length < 1e-9:
                                continue
                            geo = Part.LineSegment(a, b)
                        else:
                            geo = edge.toNurbs().Edges[0].Curve
                        added.append(sk.addGeometry(geo, False))
            for gid in added:
                sk.addConstraint(Sketcher.Constraint("Block", gid))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        if not added:
            raise KernelError("la police n'a rien produit pour ce texte")
        return self.sketch_state(sketch)

    # ---------- coin ----------

    def sketch_corner(self, sketch, geo1, geo2, x1, y1, x2, y2):
        """Coin : deux lignes prolongées ou raccourcies jusqu'à leur
        croisement, et jointes (le bout le plus proche du clic reste)."""
        from engine.kernel import KernelError, _explain
        from engine.sketchedit import line_intersection
        import Sketcher
        sk = self._get_sketch(sketch)
        ids = (int(geo1), int(geo2))
        lines = []
        for gid in ids:
            if not 0 <= gid < len(sk.Geometry) or \
                    sk.Geometry[gid].TypeId != "Part::GeomLineSegment":
                raise KernelError("coin : cliquez deux lignes")
            lines.append(sk.Geometry[gid])
        pts = [(p.x, p.y) for g in lines for p in (g.StartPoint, g.EndPoint)]
        corner = line_intersection(pts[0], pts[1], pts[2], pts[3])
        if corner is None:
            raise KernelError("coin : les deux lignes sont parallèles")
        V = self._app().Vector
        target = V(corner[0], corner[1], 0)
        ends = []
        for gid, g, click in zip(ids, lines, ((x1, y1), (x2, y2))):
            # Le côté cliqué (par rapport au coin) est gardé ; le bout de
            # l'autre côté va au coin. Si la ligne n'atteint pas le coin,
            # c'est son bout le plus proche qui s'y prolonge.
            a, b = g.StartPoint, g.EndPoint
            d = b - a
            length2 = d.dot(d)

            def param(q, a=a, d=d, length2=length2):
                return (q - a).dot(d) / length2

            tp = param(target)
            tc = param(V(float(click[0]), float(click[1]), 0))
            a_kept = (0 - tp > 0) == (tc - tp > 0)
            b_kept = (1 - tp > 0) == (tc - tp > 0)
            if a_kept and b_kept:
                moving = 1 if abs(tp) < abs(1 - tp) else 2
            else:
                moving = 2 if a_kept else 1
            ends.append((gid, moving))
        try:
            for gid, pos in ends:
                try:
                    sk.delConstraintOnPoint(gid, pos)
                except Exception:  # noqa: BLE001
                    pass
            for gid, pos in ends:
                sk.moveGeometry(gid, pos, target, False)
            sk.addConstraint(Sketcher.Constraint(
                "Coincident", ends[0][0], ends[0][1], ends[1][0], ends[1][1]))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    # ---------- courbe par équation ----------

    def sketch_add_equation(self, sketch, x, y, t0, t1, count=48):
        """Courbe pilotée par équation : x(t), y(t) pour t de t0 à t1
        (``y`` seul avec ``x = "t"`` : une fonction y = f(x)). Spline
        passant par les points calculés, bloquée."""
        from engine.kernel import KernelError, _explain
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        if float(t1) <= float(t0):
            raise KernelError("t1 doit être plus grand que t0")
        try:
            pts = equation_points(x, y, t0, t1, count)
        except EquationError as exc:
            raise KernelError(str(exc))
        V = self._app().Vector
        vectors = []
        for px, py in pts:
            if vectors and (vectors[-1] - V(px, py, 0)).Length < 1e-9:
                continue
            vectors.append(V(px, py, 0))
        if len(vectors) < 2:
            raise KernelError("l'équation ne trace qu'un point")
        try:
            curve = Part.BSplineCurve()
            closed = (vectors[0] - vectors[-1]).Length < 1e-7
            if closed:
                vectors = vectors[:-1]
            curve.interpolate(vectors, PeriodicFlag=closed)
            gid = sk.addGeometry(curve, False)
            sk.addConstraint(Sketcher.Constraint("Block", gid))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    # ---------- réparation et définition ----------

    @staticmethod
    def _dof(sk):
        sk.solve()
        try:
            return int(sk.getLastDoF())
        except Exception:  # noqa: BLE001
            return int(getattr(sk, "DoF", 0))

    def sketch_repair(self, sketch):
        """Réparer : relations redondantes retirées, conflits levés (la
        plus récente des relations en conflit part, jusqu'à ce que
        l'esquisse se résolve), extrémités presque jointes coïncidées.
        L'état porte le bilan (``repair``)."""
        sk = self._get_sketch(sketch)
        sk.solve()
        redundant = len(list(sk.RedundantConstraints or []))
        if redundant:
            sk.autoRemoveRedundants(True)
        conflicts = 0
        for _ in range(64):
            sk.solve()
            conflicting = list(sk.ConflictingConstraints or [])
            if not conflicting:
                break
            # FreeCAD numérote ces relations à partir de 1.
            sk.delConstraint(max(conflicting) - 1)
            conflicts += 1
        joined = 0
        try:
            joined = int(sk.detectMissingPointOnPointConstraints(1e-3) or 0)
            if joined:
                sk.makeMissingPointOnPointCoincident(True)
        except Exception:  # noqa: BLE001
            joined = 0
        sk.solve()
        state = self.sketch_state(sketch)
        state["repair"] = {"redundant": redundant, "conflicts": conflicts,
                           "joined": joined}
        return state

    def _definition_candidates(self, sk):
        """Cotes qui peuvent fixer l'esquisse, des plus parlantes (tailles)
        aux positions par rapport à l'origine."""
        import Sketcher
        C = Sketcher.Constraint
        sizes, places, last = [], [], []
        for gid, g in enumerate(sk.Geometry):
            kind = g.TypeId
            if kind == "Part::GeomLineSegment":
                d = g.EndPoint - g.StartPoint
                sizes.append(C("Distance", gid, d.Length))
                sizes.append(C("Angle", gid, math.atan2(d.y, d.x)))
                for pos, p in ((1, g.StartPoint), (2, g.EndPoint)):
                    places.append(C("DistanceX", -1, 1, gid, pos, p.x))
                    places.append(C("DistanceY", -1, 1, gid, pos, p.y))
            elif kind == "Part::GeomCircle":
                sizes.append(C("Diameter", gid, 2 * g.Radius))
                places.append(C("DistanceX", -1, 1, gid, 3, g.Center.x))
                places.append(C("DistanceY", -1, 1, gid, 3, g.Center.y))
            elif kind == "Part::GeomArcOfCircle":
                sizes.append(C("Radius", gid, g.Radius))
                for pos, p in ((3, g.Center), (1, g.StartPoint),
                               (2, g.EndPoint)):
                    places.append(C("DistanceX", -1, 1, gid, pos, p.x))
                    places.append(C("DistanceY", -1, 1, gid, pos, p.y))
            elif kind == "Part::GeomPoint":
                places.append(C("DistanceX", -1, 1, gid, 1, g.X))
                places.append(C("DistanceY", -1, 1, gid, 1, g.Y))
            else:
                last.append(C("Block", gid))
        return sizes + places + last

    def sketch_fully_define(self, sketch):
        """Définir entièrement : des cotes s'ajoutent (tailles, puis
        positions depuis l'origine) tant qu'elles retirent un degré de
        liberté sans rien contredire. ``added`` : le nombre de cotes."""
        sk = self._get_sketch(sketch)
        dof = self._dof(sk)
        added = 0
        for candidate in self._definition_candidates(sk):
            if dof <= 0:
                break
            try:
                index = sk.addConstraint(candidate)
            except Exception:  # noqa: BLE001
                continue
            now = self._dof(sk)
            if (now < dof and not list(sk.RedundantConstraints or [])
                    and not list(sk.ConflictingConstraints or [])):
                dof = now
                added += 1
            else:
                sk.delConstraint(index)
                sk.solve()
        state = self.sketch_state(sketch)
        state["added"] = added
        return state

    # ---------- splines ----------

    def sketch_spline(self, sketch, geo, action, x=0.0, y=0.0):
        """Outils de spline : ``convert`` (l'entité devient une spline
        éditable), ``knot`` (un nœud de plus au point cliqué), ``degree``
        (un degré de plus)."""
        from engine.kernel import KernelError, _explain
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if not 0 <= gid < len(sk.Geometry):
            raise KernelError("spline : cliquez une entité")
        g = sk.Geometry[gid]
        is_spline = "BSpline" in g.TypeId
        try:
            if action == "convert":
                if is_spline:
                    raise KernelError("c'est déjà une spline")
                sk.convertToNURBS(gid)
            elif action == "knot":
                if not is_spline:
                    raise KernelError("insérer un nœud : cliquez une spline")
                u = g.parameter(self._app().Vector(float(x), float(y), 0))
                sk.insertBSplineKnot(gid, float(u), 1)
            elif action == "degree":
                if not is_spline:
                    raise KernelError("augmenter le degré : cliquez une "
                                      "spline")
                sk.increaseBSplineDegree(gid, 1)
            else:
                raise KernelError("outil de spline inconnu : {}".format(
                    action))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    @staticmethod
    def _signed_curvature(curve, u):
        """Courbure signée d'une courbe plane (z = 0) au paramètre u."""
        _p, d1, d2 = curve.getD2(u)
        speed = (d1.x ** 2 + d1.y ** 2) ** 1.5
        if speed < 1e-18:
            return 0.0
        return (d1.x * d2.y - d1.y * d2.x) / speed

    def sketch_match_curvature(self, sketch, geo1, point1, geo2, point2):
        """Égaliser la courbure (G2) au raccord de deux splines : la seconde
        est retouchée (ses trois pôles du côté du raccord) pour prolonger
        la première en position, en tangente et en courbure ; une relation
        de tangence tient ensuite le raccord. La seconde spline est
        remplacée (ses relations propres tombent)."""
        from engine.kernel import KernelError, _explain
        import Sketcher
        sk = self._get_sketch(sketch)
        g1, g2 = int(geo1), int(geo2)
        p1, p2 = int(point1), int(point2)
        if g1 == g2 or p1 not in (1, 2) or p2 not in (1, 2):
            raise KernelError("courbure : deux extrémités de splines "
                              "différentes")
        for g in (g1, g2):
            if not 0 <= g < len(sk.Geometry) or                     "BSpline" not in sk.Geometry[g].TypeId:
                raise KernelError("courbure : cliquez les bouts de deux "
                                  "splines")
        V = self._app().Vector
        a = sk.Geometry[g1].copy()
        b = sk.Geometry[g2].copy()
        # Parcours continu : A finit au raccord, B en part.
        if p1 == 1:
            a.reverse()
        if p2 == 2:
            b.reverse()
        if b.NbPoles < 3:
            b.increaseDegree(2)
        if b.NbPoles < 3:
            raise KernelError("courbure : la seconde spline n'a pas assez "
                              "de pôles")
        joint = a.value(a.LastParameter)
        tangent = a.tangent(a.LastParameter)[0]
        tangent.normalize()
        side = V(-tangent.y, tangent.x, 0)
        target = self._signed_curvature(a, a.LastParameter)
        p0, q1, q2 = b.getPole(1), b.getPole(2), b.getPole(3)
        reach = max((q1 - p0).Length, 1e-6)
        b.setPole(1, joint)
        first = joint + tangent * reach
        b.setPole(2, first)
        along = (q2 - q1).dot(tangent)
        if along <= 1e-9:
            along = reach

        def curvature_for(h):
            b.setPole(3, first + tangent * along + side * h)
            return self._signed_curvature(b, b.FirstParameter) - target

        h0 = (q2 - q1).dot(side)
        h1 = h0 + reach * 0.1 + 1e-3
        f0, f1 = curvature_for(h0), curvature_for(h1)
        for _ in range(60):
            if abs(f1) < 1e-10 or abs(f1 - f0) < 1e-15:
                break
            h0, h1 = h1, h1 - f1 * (h1 - h0) / (f1 - f0)
            f0, f1 = f1, curvature_for(h1)
        if abs(curvature_for(h1)) > 1e-6 * max(1.0, abs(target)):
            raise KernelError("courbure : impossible d'égaler la courbure "
                              "avec cette spline")
        if p2 == 2:
            b.reverse()
        try:
            construction = bool(sk.getConstruction(g2))
            sk.delGeometry(g2)
            first_id = g1 if g1 < g2 else g1 - 1
            new = sk.addGeometry(b, construction)
            sk.addConstraint(Sketcher.Constraint(
                "Tangent", first_id, p1, new, p2))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        state = self.sketch_state(sketch)
        state["curvature"] = target
        return state

    # ---------- blocs ----------

    def _block_sketches(self):
        doc = self._require_doc()
        return [o for o in doc.Objects
                if o.TypeId == "Sketcher::SketchObject"
                and getattr(o, "FreeSolidBlock", "")]

    def sketch_blocks(self):
        """Les blocs du document (nom, nombre d'entités)."""
        return {"blocks": [{"name": o.FreeSolidBlock,
                            "count": len(o.Geometry)}
                           for o in self._block_sketches()]}

    def sketch_block_save(self, sketch, geos, name):
        """Bloc : les entités choisies (et leurs relations internes) sont
        rangées sous un nom, ramenées autour de leur centre ; on les
        réinsère ensuite où l'on veut, autant de fois qu'on veut."""
        from engine.kernel import KernelError
        import FreeCAD as App
        sk = self._get_sketch(sketch)
        name = str(name).strip()
        if not name:
            raise KernelError("donnez un nom au bloc")
        ids = sorted({int(g) for g in (geos or ())})
        if not ids or any(not 0 <= g < len(sk.Geometry) for g in ids):
            raise KernelError("sélectionnez les entités du bloc")
        for old in self._block_sketches():
            if old.FreeSolidBlock == name:
                self._require_doc().removeObject(old.Name)
        box = None
        for gid in ids:
            b = sk.Geometry[gid].toShape().BoundBox
            box = b if box is None else box.united(b)
        center = App.Vector((box.XMin + box.XMax) / 2,
                            (box.YMin + box.YMax) / 2, 0)
        doc = self._require_doc()
        holder = doc.addObject("Sketcher::SketchObject", "Bloc")
        holder.Label = name
        self._stamp(holder, block=name)
        self._mark_internal(holder)
        holder.Visibility = False
        self._copy_between(sk, ids, holder,
                           lambda g: g.translate(center * -1), 0.0, 1.0)
        doc.recompute()
        return self.sketch_blocks()

    def sketch_block_insert(self, sketch, name, x, y, angle=0.0, scale=1.0):
        """Insère un bloc, son centre en (x, y), tourné et à l'échelle."""
        from engine.kernel import KernelError, _explain
        import FreeCAD as App
        sk = self._get_sketch(sketch)
        holder = next((o for o in self._block_sketches()
                       if o.FreeSolidBlock == str(name)), None)
        if holder is None:
            raise KernelError("bloc inconnu : {}".format(name))
        scale = float(scale)
        if scale <= 0:
            raise KernelError("l'échelle doit être positive")
        V = App.Vector
        theta = float(angle)

        def place(g):
            if abs(scale - 1) > 1e-12:
                g.scale(V(0, 0, 0), scale)
            if abs(theta) > 1e-12:
                g.rotate(App.Placement(V(0, 0, 0),
                                       App.Rotation(V(0, 0, 1), theta)))
            g.translate(V(float(x), float(y), 0))

        try:
            self._copy_between(holder, list(range(len(holder.Geometry))),
                               sk, place, math.radians(theta), scale)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _copy_between(self, src, ids, dst, transform, angle, scale):
        """Copie des entités ``ids`` de l'esquisse ``src`` vers ``dst``
        (transformées) avec les relations qui ne lient qu'elles."""
        import Sketcher
        from engine.sketchedit import copied_relation
        mapping = {}
        for gid in ids:
            g = src.Geometry[gid].copy()
            transform(g)
            construction = bool(src.getConstruction(gid))
            mapping[gid] = dst.addGeometry(g, construction)
        for c in list(src.Constraints):
            refs = [r for r in (c.First, c.Second, c.Third)
                    if r is not None and r > -2000]
            if not refs or any(r not in mapping for r in refs):
                continue
            keep, factor = copied_relation(c.Type, angle, scale)
            if not keep:
                continue
            pos = [int(getattr(p, "value", p) or 0)
                   for p in (c.FirstPos, c.SecondPos, c.ThirdPos)]
            geos = [mapping[r] for r in (c.First, c.Second, c.Third)
                    if r is not None and r > -2000]
            args = [c.Type]
            if len(geos) == 1:
                args += [geos[0]] + ([pos[0]] if pos[0] else [])
            elif len(geos) == 2:
                args += ([geos[0]] + ([pos[0]] if pos[0] else [])
                         + [geos[1]] + ([pos[1]] if pos[1] else []))
            else:
                args += ([geos[0], pos[0], geos[1], pos[1], geos[2]]
                         + ([pos[2]] if pos[2] else []))
            if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius",
                          "Diameter", "Angle"):
                args.append(float(c.Value) * factor)
            try:
                dst.addConstraint(Sketcher.Constraint(*args))
            except Exception:  # noqa: BLE001
                pass
        return mapping

    # ---------- image de fond ----------

    def sketch_picture(self, sketch, picture=None):
        """Image de fond de l'esquisse, gardée avec elle : ``picture``
        (dict : data, x, y, width, rotation, opacity) l'enregistre, ``{}``
        l'efface ; sans argument, la relit."""
        from engine.kernel import KernelError
        sk = self._get_sketch(sketch)
        if picture is not None:
            if picture and not str(picture.get("data", "")).startswith(
                    "data:image/"):
                raise KernelError("image invalide")
            if "FreeSolidPicture" not in sk.PropertiesList:
                sk.addProperty("App::PropertyString", "FreeSolidPicture",
                               "FreeSolid")
                sk.setEditorMode("FreeSolidPicture", 2)
            sk.FreeSolidPicture = json.dumps(picture) if picture else ""
        raw = getattr(sk, "FreeSolidPicture", "") or ""
        return {"picture": json.loads(raw) if raw else None}
