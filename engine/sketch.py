"""Esquisse : tracé, contraintes, cotes, conversion d'entités.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

#: Le point racine de Sketcher : l'origine de l'esquisse (point 1).
ROOT_GEO = -1

from engine.sketchref import geo_of, is_geo  # noqa: E402


class SketchMixin:
    # -- esquisse ---------------------------------------------------------

    #: Exact-match tolerance for auto-constraints. The client snaps and
    #: sends identical coordinates; this only recognizes that decision.
    _SNAP_TOL = 1e-7

    _CONSTRAINT_LABELS = {
        "Coincident": "Coïncidente", "Horizontal": "Horizontale",
        "Vertical": "Verticale", "Parallel": "Parallèle",
        "Perpendicular": "Perpendiculaire", "Tangent": "Tangente",
        "Equal": "Égale", "Symmetric": "Symétrique", "Block": "Fixe",
        "PointOnObject": "Sur l'entité", "Distance": "Cote (distance)",
        "DistanceX": "Cote (horizontale)", "DistanceY": "Cote (verticale)",
        "Radius": "Cote (rayon)", "Diameter": "Cote (diamètre)",
        "Angle": "Cote (angle)",
    }

    def _attach_to_support(self, sketch, support):
        try:
            sketch.AttachmentSupport = support
        except AttributeError:
            sketch.Support = support
        sketch.MapMode = "FlatFace"

    def _attach_to_face(self, sketch, face_id):
        """Map a sketch flat onto one of the current shape's faces.

        ``face_id`` is the tessellation index, so ``Face{id+1}`` on the Tip
        feature — the same numbering the viewport picked. The attachment
        property was renamed in 1.x, hence the two spellings.
        """
        from engine.kernel import KernelError
        body = self._require_body()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas encore de solide pour accueillir "
                              "une esquisse sur face")
        self._attach_to_support(
            sketch, [(tip, ("Face{}".format(int(face_id) + 1),))])

    def add_rect_sketch(self, width, height, face=None):
        """Centered, fully-constrained rectangle.

        On the XY plane by default; with ``face`` (a picked face id), mapped
        flat onto that face — the usual "click a face, sketch on it"
        gesture. Anchored by symmetry about the sketch origin, driven by
        DistanceX/DistanceY; the interactive part is M2's job.
        """
        from engine.kernel import KernelError
        import Part
        import Sketcher
        body = self._require_body()
        doc = self._require_doc()
        w, h = float(width), float(height)
        if w <= 0 or h <= 0:
            raise KernelError("largeur et hauteur doivent être positives")

        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = self._t("Esquisse")
        if face is not None:
            self._attach_to_face(sketch, face)
        else:
            # Plan XY d'origine : la docstring le promettait déjà, mais
            # sans AttachmentSupport l'esquisse n'avait pas d'arête dans
            # le graphe. Même geste que ``sketch_start(plane="XY")``.
            self._attach_to_support(
                sketch, [(self._origin_feature(self._PLANE_ROLES["XY"]),
                          ("",))])

        V = self._app().Vector
        x, y = w / 2.0, h / 2.0
        corners = [V(-x, -y, 0), V(x, -y, 0), V(x, y, 0), V(-x, y, 0)]
        for i in range(4):
            sketch.addGeometry(
                Part.LineSegment(corners[i], corners[(i + 1) % 4]), False)

        C = Sketcher.Constraint
        for i in range(4):
            sketch.addConstraint(C("Coincident", i, 2, (i + 1) % 4, 1))
        sketch.addConstraint(C("Horizontal", 0))
        sketch.addConstraint(C("Horizontal", 2))
        sketch.addConstraint(C("Vertical", 1))
        sketch.addConstraint(C("Vertical", 3))
        # Symmetry about the origin point pins the rectangle in space.
        sketch.addConstraint(C("Symmetric", 0, 1, 2, 1, -1, 1))
        sketch.addConstraint(C("DistanceX", 0, 1, 0, 2, w))
        sketch.addConstraint(C("DistanceY", 1, 1, 1, 2, h))

        self._recompute()
        return self.get_tree()

    def _coincident_2d(self, x1, y1, x2, y2):
        import math
        return math.hypot(float(x2) - float(x1),
                          float(y2) - float(y1)) < self._SNAP_TOL

    def _get_sketch(self, name):
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(name)
        if obj is None or obj.TypeId != "Sketcher::SketchObject":
            raise KernelError("esquisse inconnue : {}".format(name))
        return obj

    def sketch_start(self, face=None, plane=None, datum=None):
        """Open a new empty sketch — XY by default, a picked face, a
        named origin plane (XY/XZ/YZ), or a datum plane by name."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        # La transaction de sketch_start est ouverte, pas encore validée :
        # UndoCount est encore celui d'avant l'esquisse.
        mark = doc.UndoCount
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        self._sketch_session = {"sketch": sketch.Name, "mark": mark,
                                "snapshot": None}
        sketch.Label = self._t("Esquisse")
        if face is not None:
            self._attach_to_face(sketch, face)
        elif datum is not None:
            target = doc.getObject(str(datum))
            if target is None or target.TypeId != "PartDesign::Plane":
                raise KernelError(
                    "plan de référence inconnu : {}".format(datum))
            self._attach_to_support(sketch, [(target, ("",))])
        elif plane is not None:
            role = self._PLANE_ROLES.get(str(plane).upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
            self._attach_to_support(
                sketch, [(self._origin_feature(role), ("",))])
        doc.recompute()  # resolves the placement before the client reads it
        return self.sketch_state(sketch.Name)

    def sketch_set_plane(self, sketch, plane=None, datum=None, face=None):
        """Pose une esquisse existante sur un autre plan (origine, plan de
        référence ou face du solide) ; ses entités gardent leurs
        coordonnées dans l'esquisse, les fonctions qui l'utilisent suivent."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        sk = self._get_sketch(sketch)
        if face is not None:
            tip = getattr(self._require_body(), "Tip", None)
            if tip is not None and (tip is sk
                                    or sk in tip.OutListRecursive):
                raise KernelError(
                    "cette face dépend de l'esquisse elle-même — choisissez "
                    "un plan ou la face d'une fonction antérieure")
            self._attach_to_face(sk, face)
        elif datum is not None:
            target = doc.getObject(str(datum))
            if target is None or target.TypeId != "PartDesign::Plane":
                raise KernelError(
                    "plan de référence inconnu : {}".format(datum))
            self._attach_to_support(sk, [(target, ("",))])
        elif plane is not None:
            role = self._PLANE_ROLES.get(str(plane).upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
            self._attach_to_support(sk, [(self._origin_feature(role), ("",))])
        else:
            raise KernelError("choisissez le nouveau plan de l'esquisse")
        self._recompute()
        return self._current_tree()

    def sketch_edit(self, feature):
        """Re-enter an existing sketch."""
        sk = self._get_sketch(feature)
        doc = self._require_doc()
        self._sketch_session = {
            "sketch": sk.Name, "mark": doc.UndoCount,
            # Les glisser (sketch_move) ne passent pas par une transaction :
            # l'instantané les rattrape.
            "snapshot": (list(sk.Geometry), list(sk.Constraints)),
        }
        return self.sketch_state(sk.Name)

    def sketch_cancel(self, sketch):
        """Quitter l'esquisse sans garder les modifications.

        Défait les transactions ouvertes depuis l'entrée en esquisse —
        une esquisse neuve disparaît — puis restaure la géométrie et les
        contraintes d'une esquisse rééditée (les glisser n'ont pas de
        transaction)."""
        doc = self._require_doc()
        session = self._sketch_session
        self._sketch_session = None
        if not session or session["sketch"] != str(sketch):
            return self.get_tree()
        while doc.UndoCount > session["mark"] and doc.UndoNames:
            doc.undo()
        sk = doc.getObject(session["sketch"])
        if sk is not None and session["snapshot"] is not None:
            geometry, constraints = session["snapshot"]
            sk.Constraints = []
            sk.Geometry = geometry
            sk.Constraints = constraints
        doc.recompute()
        return self.get_tree()

    def sketch_state(self, sketch):
        """Everything the client needs to draw the sketch.

        Geometry in sketch-local 2D, dimensional constraints with values,
        degrees of freedom, and the placement matrix (row-major, which is
        what THREE.Matrix4.set expects) to position the plane in 3D.
        """
        sk = self._get_sketch(sketch)
        entities = []
        for gid, geo in enumerate(sk.Geometry):
            entity = self._entity_of(gid, geo)
            entity["construction"] = self._is_construction(sk, gid, geo)
            entities.append(entity)
        import re
        exprs = {}  # constraint index -> expression
        names = {c.Name: cid for cid, c in enumerate(sk.Constraints)
                 if c.Name}
        for path, expr in self._expression_map(sk).items():
            by_index = re.match(r"^Constraints\[(\d+)\]$", path)
            by_name = re.match(r"^Constraints\.(.+)$", path)
            if by_index:
                exprs[int(by_index.group(1))] = expr
            elif by_name and by_name.group(1) in names:
                exprs[names[by_name.group(1)]] = expr
        dims = []
        for cid, constraint in enumerate(sk.Constraints):
            if constraint.Type in ("Distance", "DistanceX", "DistanceY",
                                   "Radius", "Diameter", "Angle"):
                value = float(constraint.Value)
                if constraint.Type in ("DistanceX", "DistanceY"):
                    value = abs(value)  # le signe ne dit que le sens
                entry_offset = None
                label = (round(float(getattr(constraint, "LabelDistance",
                                             10.0)), 9),
                         round(float(getattr(constraint, "LabelPosition",
                                             0.0)), 9))
                if label != self._DEFAULT_LABEL:
                    entry_offset = label[0]
                second = getattr(constraint, "Second", -2000)
                single = second is None or second <= -2000
                kind = ""
                first = constraint.First
                on_arc = (0 <= first < len(sk.Geometry) and sk.Geometry[
                    first].TypeId == "Part::GeomArcOfCircle")
                if single and constraint.Type == "Distance" and on_arc:
                    kind = "arc_length"
                elif single and constraint.Type == "Angle":
                    kind = "axis_angle"
                dims.append({"id": cid, "type": constraint.Type,
                             "kind": kind,
                             "driving": bool(getattr(constraint, "Driving",
                                                     True)),
                             "offset": entry_offset,
                             "value": value,
                             "name": constraint.Name or "",
                             "expr": exprs.get(cid, ""),
                             "geo": constraint.First})
        constraints = []
        for cid, c in enumerate(sk.Constraints):
            geos, pos = [], []
            for geo_attr, pos_attr in (("First", "FirstPos"),
                                       ("Second", "SecondPos"),
                                       ("Third", "ThirdPos")):
                g = getattr(c, geo_attr, None)
                # -2000 = GeoUndef chez Sketcher : « pas de géométrie »
                geos.append(None if g is None or g <= -2000 else int(g))
                p = getattr(c, pos_attr, 0)
                pos.append(int(getattr(p, "value", p) or 0))
            constraints.append({
                "id": cid, "type": c.Type, "geos": geos, "pos": pos,
                "value": float(c.Value),
                "driving": bool(getattr(c, "Driving", True))})
        solver_code = 0
        try:
            solver_code = int(sk.solve())
        except Exception:
            pass
        # Bleu / blanc / rouge côté client : entité libre, définie, en trop.
        from engine.sketchstatus import entity_status, sketch_definition
        try:
            dependent = list(sk.getGeometryWithDependentParameters())
        except Exception:
            dependent = []
        status = entity_status(
            len(entities), dependent,
            [c["geos"] for c in constraints],
            list(getattr(sk, "ConflictingConstraints", []) or []),
            list(getattr(sk, "RedundantConstraints", []) or []))
        for entity, state in zip(entities, status):
            entity["status"] = state
        # Calques : le nom du calque de chaque entité qui en a un.
        layer_data = self._layer_data(sk)
        for entity in entities:
            name = self._layer_of(sk, layer_data, entity["id"])
            if name:
                entity["layer"] = name
        # Références externes (liées à la pièce) : GeoId -3, -4…
        from engine.sketchref import FIRST_EXTERNAL, external_count
        for k in range(external_count(sk)):
            gid = FIRST_EXTERNAL - k
            try:
                entity = self._entity_of(gid, sk.ExternalGeo[k + 2])
            except Exception:  # noqa: BLE001
                continue
            entity["external"] = True
            entity["construction"] = False
            entity["status"] = "full"
            entities.append(entity)
        dof = None
        try:
            dof = int(sk.getLastDoF())
        except Exception:
            pass
        if dof is None:
            # FreeCAD 1.0 : propriété DoF (getLastDoF a disparu).
            try:
                dof = int(sk.DoF)
            except Exception:
                pass
        matrix = sk.Placement.Matrix.A
        return {
            "sketch": sk.Name,
            "label": sk.Label,
            "support": self._sketch_support_label(sk),
            "entities": entities,
            "dims": dims,
            "constraints": constraints,
            "dof": dof,
            "fullyConstrained": bool(getattr(sk, "FullyConstrained", False)),
            "definition": sketch_definition(status, solver_code),
            "layers": layer_data["layers"],
            "placement": [float(v) for v in matrix],
        }

    def _entity_of(self, gid, geo):
        """Ce que le client dessine d'une géométrie (entité ou référence)."""
        if geo.TypeId == "Part::GeomPoint":
            # Point d'esquisse (coin gardé d'un congé…) : point 1.
            entity = {"id": gid, "type": "point",
                      "p1": [geo.X, geo.Y]}
        elif geo.TypeId == "Part::GeomLineSegment":
            entity = {
                "id": gid, "type": "line",
                "p1": [geo.StartPoint.x, geo.StartPoint.y],
                "p2": [geo.EndPoint.x, geo.EndPoint.y]}
        elif geo.TypeId == "Part::GeomCircle":
            entity = {
                "id": gid, "type": "circle",
                "c": [geo.Center.x, geo.Center.y],
                "r": float(geo.Radius)}
        elif geo.TypeId == "Part::GeomArcOfCircle":
            entity = {
                "id": gid, "type": "arc",
                "c": [geo.Center.x, geo.Center.y],
                "r": float(geo.Radius),
                "p1": [geo.StartPoint.x, geo.StartPoint.y],
                "p2": [geo.EndPoint.x, geo.EndPoint.y]}
        else:
            type_id = geo.TypeId
            entity = {"id": gid, "type": "other", "kind": type_id}
            try:
                # Splines, ellipses, coniques : une polyligne suffit
                # au client pour afficher et viser n'importe quelle
                # courbe.
                count = 24
                if "BSpline" in type_id:
                    # Une spline : assez de pas par arc pour rester lisse.
                    count = min(400, 24 * max(1, len(geo.getKnots()) - 1))
                points = geo.toShape().discretize(Number=count)
                entity["type"] = "poly"
                entity["points"] = [[p.x, p.y] for p in points]
            except Exception:
                pass
            self._enrich_poly_entity(entity, geo, type_id)
        return entity

    @staticmethod
    def _sketch_definition(sk):
        """under | full | over — préfixe (-) / (+) de l'arbre."""
        from engine.sketchstatus import definition_from_flags
        return definition_from_flags(
            bool(getattr(sk, "FullyConstrained", False)),
            getattr(sk, "ConflictingConstraints", []),
            getattr(sk, "RedundantConstraints", []),
            getattr(sk, "MalformedConstraints", []))

    def _sketch_support_label(self, sk):
        """Label du plan ou de la face d'appui — pour le panneau infos."""
        from engine.vocab import label_for_origin
        support = (getattr(sk, "AttachmentSupport", None)
                   or getattr(sk, "Support", None))
        try:
            for obj, subs in list(support or ()):
                if obj is None:
                    continue
                # Plan d'origine : le nom affiché (« Plan de
                # face ») via le Name interne ; sinon label utilisateur.
                name = getattr(obj, "Name", "") or ""
                label = label_for_origin(name, self.lang)
                if label == name:
                    label = obj.Label
                for sub in subs or ():
                    text = str(sub)
                    if text.startswith("Face"):
                        return "{} · {}".format(label, text)
                return label
        except Exception:
            pass
        return ""

    @staticmethod
    def _enrich_poly_entity(entity, geo, type_id):
        """Champs du panneau propriétés (P025) : ellipse, spline, polyligne."""
        if type_id in ("Part::GeomEllipse", "Part::GeomArcOfEllipse"):
            entity["kind"] = "ellipse"
            try:
                center = geo.Center
                entity["c"] = [float(center.x), float(center.y)]
                entity["rx"] = float(geo.MajorRadius)
                entity["ry"] = float(geo.MinorRadius)
            except Exception:
                pass
            return
        if "BSpline" in type_id or "Bezier" in type_id:
            entity["kind"] = "spline"
            npoints = None
            try:
                npoints = int(geo.NbPoles)
            except Exception:
                getter = getattr(geo, "getPoles", None)
                if callable(getter):
                    try:
                        npoints = len(getter())
                    except Exception:
                        pass
            if npoints is None and entity.get("points"):
                npoints = len(entity["points"])
            if npoints is not None:
                entity["npoints"] = npoints
            if "BSpline" in type_id:
                # Points de passage et poignées : l'édition dans la vue.
                from engine.splineedit import spec_from_bspline
                try:
                    spec = spec_from_bspline(geo)
                    entity["poles"] = [[p.x, p.y] for p in geo.getPoles()]
                except Exception:  # noqa: BLE001
                    spec = None
                if spec is not None:
                    points, closed, tangents = spec
                    entity["spline"] = {
                        "points": [[round(p[0], 9) + 0.0,
                                    round(p[1], 9) + 0.0] for p in points],
                        "closed": closed,
                        "tangents": [None if t is None else {
                            "dir": t["dir"][:2], "in": t["in"],
                            "out": t["out"]} for t in tangents]}
            return
        if entity.get("points"):
            entity["npoints"] = len(entity["points"])

    @staticmethod
    def _endpoints_of(geo):
        """(Sketcher pos, point) pairs a snap can land on — lines and arcs."""
        if geo.TypeId in ("Part::GeomLineSegment", "Part::GeomArcOfCircle"):
            return ((1, geo.StartPoint), (2, geo.EndPoint))
        return ()

    def _auto_constrain(self, sk, gid):
        """The usual reflexes: snap becomes coincident, near-axis
        becomes horizontal/vertical.

        The client decides (it snapped and sent exact coordinates); this
        turns that decision into constraints so the solver holds it.
        """
        import Sketcher
        C = Sketcher.Constraint
        geo = sk.Geometry[gid]
        origin = self._app().Vector(0, 0, 0)
        for pos, point in self._endpoints_of(geo):
            matched = False
            for other in range(len(sk.Geometry)):
                if other == gid:
                    continue
                for opos, opoint in self._endpoints_of(sk.Geometry[other]):
                    if point.distanceToPoint(opoint) < self._SNAP_TOL:
                        sk.addConstraint(C("Coincident", gid, pos,
                                           other, opos))
                        matched = True
                        break
                if matched:
                    break
            # Point posé sur l'origine : coïncident avec le point racine
            # (GeoId -1 = axe H, PosId 1 = son départ, l'origine).
            if not matched and point.distanceToPoint(origin) < self._SNAP_TOL:
                sk.addConstraint(C("Coincident", gid, pos, -1, 1))
        axis = self._axis_constraint(sk, gid)
        if axis is not None:
            sk.addConstraint(axis)

    def _axis_constraint(self, sk, gid):
        """Horizontale ou verticale d'une ligne exactement alignée sur un
        axe, sinon None."""
        import Sketcher
        geo = sk.Geometry[gid]
        if geo.TypeId != "Part::GeomLineSegment":
            return None
        dx = abs(geo.EndPoint.x - geo.StartPoint.x)
        dy = abs(geo.EndPoint.y - geo.StartPoint.y)
        if dx > self._SNAP_TOL or dy > self._SNAP_TOL:  # not degenerate
            if dy < self._SNAP_TOL:
                return Sketcher.Constraint("Horizontal", gid)
            if dx < self._SNAP_TOL:
                return Sketcher.Constraint("Vertical", gid)
        return None

    # -- accrochages (engine/sketchsnap.py) --------------------------------

    def _snap_targets(self, sk, op, snaps):
        """``snaps`` vérifié, chaque cible comprise : avant tout ajout,
        pour qu'un refus ne laisse rien."""
        from engine.kernel import KernelError
        from engine.sketchsnap import fits, geos_of, parse_snaps, targets_of
        parsed = parse_snaps(op, snaps)
        for role, target in targets_of(parsed):
            if target.kind == "point":
                if target.geo == ROOT_GEO:
                    found = target.point == 1
                else:
                    found = is_geo(sk, target.geo) and fits(
                        target, lambda g: geo_of(sk, g).TypeId)
                if not found:
                    raise KernelError(
                        "accrochage « {} » : point {}.{} introuvable".format(
                            role, target.geo, target.point))
                continue
            for geo in geos_of(target):
                if not is_geo(sk, geo):
                    raise KernelError(
                        "accrochage « {} » : géométrie {} introuvable".format(
                            role, geo))
            if not fits(target, lambda g: geo_of(sk, g).TypeId):
                raise KernelError(
                    "accrochage « {} » : la géométrie {} ne s'y prête "
                    "pas".format(role, target.geo))
        return parsed

    def _point_at(self, sk, where, skip):
        """Le point d'esquisse exactement en ``where`` : une ``Target``
        ou None. Entités (sauf ``skip``, le tracé lui-même), puis
        références, puis l'origine : extrémités, centres, points, bouts
        de spline — tout ce que l'interface accroche."""
        from engine.sketchref import FIRST_EXTERNAL, external_count
        from engine.sketchsnap import Target, snap_positions
        gids = [g for g in range(len(sk.Geometry)) if g not in skip]
        gids += [FIRST_EXTERNAL - k for k in range(external_count(sk))]
        for gid in gids:
            for pos in snap_positions(geo_of(sk, gid).TypeId):
                try:
                    there = sk.getPoint(gid, pos)
                except Exception:  # noqa: BLE001 - point absent
                    continue
                if where.distanceToPoint(there) < self._SNAP_TOL:
                    return Target("point", gid, point=pos)
        if where.distanceToPoint(self._app().Vector(0, 0, 0)) < self._SNAP_TOL:
            return Target("point", ROOT_GEO, point=1)
        return None

    def _snap_links(self, sk, parsed, points, skip):
        """Relations des points d'un tracé ``(rôle, geo, point)`` : vers
        la cible que ``snaps`` nomme, sinon une coïncidence avec le point
        existant exactement au même endroit (la ligne précédente d'une
        chaîne)."""
        return self._constraints(
            sk, self._snap_specs(sk, parsed, points, skip))

    def _snap_specs(self, sk, parsed, points, skip):
        """``_snap_links``, en arguments de ``Sketcher.Constraint``."""
        from engine.sketchsnap import relations
        specs = []
        for role, gid, pos in points:
            target = parsed.get(role) if role else None
            if target is None:
                target = self._point_at(sk, sk.getPoint(gid, pos), skip)
            if target is not None:
                specs += relations(
                    target, gid, pos, lambda g: geo_of(sk, g).TypeId)
        return specs

    @staticmethod
    def _constraints(sk, specs):
        import Sketcher
        return [Sketcher.Constraint(*spec) for spec in specs]

    @staticmethod
    def _add_snap_constraints(sk, constraints):
        """Pose les relations d'accrochage une à une. Celle qui rendrait
        l'esquisse redondante ou contradictoire est retirée : le tracé
        reste, sans la relation de trop."""
        def trouble():
            return (set(sk.ConflictingConstraints or [])
                    | set(sk.RedundantConstraints or []))
        sk.solve()
        for constraint in constraints:
            before = trouble()
            try:
                index = sk.addConstraint(constraint)
            except Exception:  # noqa: BLE001 - relation impossible : omise
                continue
            sk.solve()
            if trouble() - before:
                sk.delConstraint(index)
                sk.solve()

    def sketch_add_line(self, sketch, x1, y1, x2, y2, construction=False,
                        snaps=None):
        """Ligne. ``snaps`` (``start``, ``end``, ``direction``) : les points
        et la direction que l'interface a accrochés ; sans lui, le moteur
        déduit tout des coordonnées (``_auto_constrain``)."""
        from engine.kernel import KernelError
        import Part
        sk = self._get_sketch(sketch)
        if self._coincident_2d(x1, y1, x2, y2):
            raise KernelError(
                "segment de longueur nulle — les deux points coïncident")
        parsed = (None if snaps is None
                  else self._snap_targets(sk, "sketch_add_line", snaps))
        V = self._app().Vector
        gid = sk.addGeometry(Part.LineSegment(
            V(float(x1), float(y1), 0), V(float(x2), float(y2), 0)),
            bool(construction))
        if parsed is None:
            self._auto_constrain(sk, gid)
            return self.sketch_state(sketch)
        from engine.sketchsnap import with_direction
        specs = self._snap_specs(
            sk, parsed, (("start", gid, 1), ("end", gid, 2)), {gid})
        if "direction" in parsed:
            specs = with_direction(parsed["direction"], gid, specs)
        axis = self._axis_constraint(sk, gid)
        self._add_snap_constraints(
            sk, self._constraints(sk, specs) + ([axis] if axis else []))
        return self.sketch_state(sketch)

    def sketch_add_rectangle(self, sketch, x1, y1, x2, y2, center=False,
                             snaps=None):
        """Rectangle par deux coins opposés, en une opération (un seul
        Ctrl+Z). Les côtés s'enchaînent comme tracés à la main
        (coïncidences, horizontal/vertical, origine). ``center`` avec le
        milieu sur l'origine : les deux coins restent symétriques autour
        d'elle (ailleurs, le centre est libre de toute façon).

        ``snaps`` : ``corner1`` (x1, y1), ``corner2`` (x2, y2) et, par le
        centre, ``center`` — les deux coins restent alors symétriques
        autour du point visé, quel qu'il soit."""
        from engine.kernel import KernelError
        import Part
        import Sketcher
        x1, y1, x2, y2 = (float(v) for v in (x1, y1, x2, y2))
        if self._coincident_2d(x1, 0, x2, 0) or self._coincident_2d(0, y1, 0, y2):
            raise KernelError(
                "rectangle : les deux coins doivent être en diagonale")
        sk = self._get_sketch(sketch)
        parsed = (None if snaps is None
                  else self._snap_targets(sk, "sketch_add_rectangle", snaps))
        if parsed and "center" in parsed and not center:
            raise KernelError(
                "accrochage « center » : réservé au rectangle par le centre")
        V = self._app().Vector
        corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        first = None
        for i in range(4):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
            gid = sk.addGeometry(Part.LineSegment(
                V(ax, ay, 0), V(bx, by, 0)), False)
            first = gid if first is None else first
            if parsed is None:
                self._auto_constrain(sk, gid)
        C = Sketcher.Constraint
        if parsed is not None:
            # Les côtés : enchaînés, deux horizontaux, deux verticaux.
            for i in range(4):
                sk.addConstraint(C("Coincident", first + i, 2,
                                   first + (i + 1) % 4, 1))
                sk.addConstraint(C("Horizontal" if i % 2 == 0 else "Vertical",
                                   first + i))
            sides = set(range(first, first + 4))
            links = self._snap_links(sk, parsed, (
                ("corner1", first, 1), (None, first + 1, 1),
                ("corner2", first + 2, 1), (None, first + 3, 1)), sides)
            middle = parsed.get("center") if center else None
            if center and middle is None:
                middle = self._point_at(
                    sk, V((x1 + x2) / 2, (y1 + y2) / 2, 0), sides)
            if middle is not None:
                links.append(C("Symmetric", first, 1, first + 2, 1,
                               middle.geo, middle.point))
            self._add_snap_constraints(sk, links)
        elif center and self._coincident_2d((x1 + x2) / 2, (y1 + y2) / 2, 0, 0):
            # Coin (x1, y1) = départ du 1er côté ; (x2, y2) = départ du 3e ;
            # (-1, 1) = le point racine, l'origine.
            sk.addConstraint(C("Symmetric", first, 1, first + 2, 1, -1, 1))
        return self.sketch_state(sketch)

    def sketch_add_arc(self, sketch, cx, cy, r, a1, a2, snaps=None):
        """Arc de cercle — angles en radians, sens trigonométrique.
        ``snaps`` : ``center``, ``start`` (angle a1), ``end`` (angle a2)
        et ``on``, les points posés sur l'arc."""
        from engine.kernel import KernelError
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        parsed = (None if snaps is None
                  else self._snap_targets(sk, "sketch_add_arc", snaps))
        App = self._app()
        circle = Part.Circle(App.Vector(float(cx), float(cy), 0),
                             App.Vector(0, 0, 1), float(r))
        gid = sk.addGeometry(
            Part.ArcOfCircle(circle, float(a1), float(a2)), False)
        if parsed is None:
            self._auto_constrain(sk, gid)
        else:
            self._add_snap_constraints(sk, self._round_snap_links(
                sk, gid, parsed,
                (("center", gid, 3), ("start", gid, 1), ("end", gid, 2))))
        return self.sketch_state(sketch)

    def _round_snap_links(self, sk, gid, parsed, points):
        """Relations d'accrochage d'un cercle ou d'un arc : centre et bouts
        coïncidents, points posés sur la courbe (``on``)."""
        return self._snap_links(sk, parsed, points, {gid}) + self._constraints(
            sk, [("PointOnObject", on.geo, on.point, gid)
                 for on in parsed.get("on", [])])

    def sketch_add_spline(self, sketch, points):
        """Spline interpolée par les points cliqués."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        if not isinstance(points, (list, tuple)) or len(points) < 3:
            raise KernelError("une spline demande au moins trois points")
        vectors = []
        for p in points:
            try:
                x, y = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            if vectors and self._coincident_2d(
                    vectors[-1].x, vectors[-1].y, x, y):
                raise KernelError(
                    "segment de longueur nulle — deux points de contrôle "
                    "consécutifs coïncident")
            vectors.append(App.Vector(x, y, 0))
        try:
            # Même courbe que l'édition dans la vue (splinemath) : un nœud
            # par point cliqué, pentes libres.
            from engine.splineedit import build_bspline
            curve = build_bspline([[v.x, v.y, 0.0] for v in vectors])
            sk.addGeometry(curve, False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_ellipse(self, sketch, cx, cy, rx, ry, angle=0.0):
        """Ellipse par centre + rayons, inclinée de ``angle`` degrés."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import math
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        rx, ry = float(rx), float(ry)
        if rx <= 0 or ry <= 0:
            raise KernelError("les deux rayons doivent être positifs")
        tilt = float(angle)
        if ry > rx:
            rx, ry = ry, rx
            tilt += 90.0
        try:
            ellipse = Part.Ellipse(App.Vector(float(cx), float(cy), 0),
                                   rx, ry)
            try:
                ellipse.AngleXU = math.radians(tilt)
            except AttributeError:
                pass
            sk.addGeometry(ellipse, False)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_mirror(self, sketch, geos, axis):
        """Symétrie d'entités : copies miroir par rapport à une ligne."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        ids = [int(g) for g in (geos or ())]
        if not ids:
            raise KernelError("sélectionnez les entités à symétriser")
        axis_id = int(axis)
        if axis_id in ids:
            raise KernelError("l'axe ne peut pas faire partie de la "
                              "sélection")
        try:
            sk.addSymmetric(ids, axis_id)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_array(self, sketch, geos, dx, dy, cols, rows):
        """Réseau linéaire d'entités d'esquisse (grille cols × rows)."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        App = self._app()
        ids = [int(g) for g in (geos or ())]
        if not ids:
            raise KernelError("sélectionnez les entités à répéter")
        cols, rows = int(cols), int(rows)
        if cols < 1 or rows < 1 or cols * rows < 2:
            raise KernelError("au moins deux occurrences (cols × rows)")
        displacement = App.Vector(float(dx), float(dy), 0)
        try:
            sk.addRectangularArray(ids, displacement, False, cols, rows,
                                   True)
        except TypeError:
            sk.addRectangularArray(ids, displacement, False, cols, rows)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_offset(self, sketch, geos, distance, reversed=False,
                      construction=False):
        """Décalage d'entités : offset 2D non contraint (makeOffset2D).

        Le décalage paramétrique des modeleurs courants (contraintes d'égalité
        de distance) viendra plus tard — les copies restent libres.
        ``construction`` : les originaux passent en construction — le profil
        ne garde que la copie (arêtes projetées puis décalées).
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        ids = []
        seen = set()
        for raw in geos or ():
            try:
                gid = int(raw)
            except (TypeError, ValueError):
                raise KernelError(
                    "identifiant d'entité invalide : {}".format(raw))
            if gid in seen:
                continue
            seen.add(gid)
            if gid < 0 or gid >= len(sk.Geometry):
                raise KernelError("entité inconnue : {}".format(gid))
            ids.append(gid)
        if not ids:
            raise KernelError("sélectionnez les entités à décaler")
        offset_edges = self._offset_edges(sk, ids, distance, reversed)

        # Tout ou rien : convertir d'abord, n'injecter qu'ensuite.
        geoms = [self._geom_from_offset_edge(edge, Part, App)
                 for edge in offset_edges]
        for geom in geoms:
            sk.addGeometry(geom, False)
        if construction:
            for gid in ids:
                if not self._is_construction(sk, gid, sk.Geometry[gid]):
                    sk.toggleConstruction(gid)
        return self.sketch_state(sketch)

    def sketch_offset_preview(self, sketch, geos, distance, reversed=False):
        """Aperçu du décalage : la polyligne de la copie, sans rien
        ajouter à l'esquisse."""
        sk = self._get_sketch(sketch)
        ids = [int(g) for g in geos or ()]
        edges = self._offset_edges(sk, ids, distance, reversed)
        points = []
        for edge in edges:
            try:
                samples = edge.discretize(Deviation=0.05)
            except Exception:
                samples = edge.discretize(Number=48)
            pts = [[p.x, p.y] for p in samples]
            if points and pts and abs(points[-1][0] - pts[0][0]) < 1e-6 \
                    and abs(points[-1][1] - pts[0][1]) < 1e-6:
                pts = pts[1:]
            points.extend(pts)
        return {"points": points}

    def _offset_edges(self, sk, ids, distance, reversed):
        """Arêtes de la copie décalée. Un contour fermé part vers
        l'extérieur, ``reversed`` vers l'intérieur — quel que soit le sens
        de parcours de ses arêtes."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        for gid in ids:
            if gid < 0 or gid >= len(sk.Geometry):
                raise KernelError("entité inconnue : {}".format(gid))
        if not ids:
            raise KernelError("sélectionnez les entités à décaler")
        dist = float(distance)
        if dist <= 0:
            raise KernelError("la distance doit être positive")
        signed = -dist if reversed else dist

        edges = []
        for gid in ids:
            try:
                shape = sk.Geometry[gid].toShape()
            except Exception as exc:  # noqa: BLE001
                raise KernelError(_explain(exc))
            found = [shape] if shape.ShapeType == "Edge" else list(shape.Edges)
            if not found:
                raise KernelError(
                    "les entités à décaler doivent former une chaîne connexe")
            edges.extend(found)
        try:
            chains = Part.sortEdges(edges)
        except Exception:  # noqa: BLE001
            raise KernelError(
                "les entités à décaler doivent former une chaîne connexe")
        if len(chains) != 1:
            raise KernelError(
                "les entités à décaler doivent former une chaîne connexe")
        try:
            wire = Part.Wire(chains[0])
            offset_shape = wire.makeOffset2D(signed)
            if wire.isClosed():
                # Le signe suit le sens de parcours : on vérifie à l'aire.
                grows = (Part.Face(Part.Wire(offset_shape.Edges)).Area
                         > Part.Face(wire).Area)
                if grows == bool(reversed):
                    offset_shape = wire.makeOffset2D(-signed)
        except Exception as exc:  # noqa: BLE001
            raise KernelError("décalage impossible : {}".format(_explain(exc)))

        offset_edges = list(offset_shape.Edges)
        if not offset_edges:
            raise KernelError("décalage impossible : aucun contour produit")
        return offset_edges

    @staticmethod
    def _geom_from_offset_edge(edge, Part, App):
        """Arête d'offset → géométrie d'esquisse (ligne, arc ou cercle)."""
        from engine.kernel import KernelError
        import math
        curve = edge.Curve
        tid = curve.TypeId
        V = App.Vector
        if tid in ("Part::GeomLine", "Part::GeomLineSegment"):
            verts = edge.Vertexes
            if len(verts) != 2:
                raise KernelError("géométrie non décalable pour l'instant")
            return Part.LineSegment(
                V(verts[0].Point.x, verts[0].Point.y, 0),
                V(verts[1].Point.x, verts[1].Point.y, 0))
        if tid == "Part::GeomCircle":
            span = abs(edge.LastParameter - edge.FirstParameter)
            full = (bool(getattr(edge, "Closed", False))
                    or abs(span - 2 * math.pi) < 1e-4)
            if full:
                return Part.Circle(
                    V(curve.Center.x, curve.Center.y, 0),
                    V(0, 0, 1), float(curve.Radius))
            p1 = edge.valueAt(edge.FirstParameter)
            p2 = edge.valueAt(
                0.5 * (edge.FirstParameter + edge.LastParameter))
            p3 = edge.valueAt(edge.LastParameter)
            return Part.ArcOfCircle(
                V(p1.x, p1.y, 0), V(p2.x, p2.y, 0), V(p3.x, p3.y, 0))
        raise KernelError("géométrie non décalable pour l'instant")

    def sketch_add_slot(self, sketch, x1, y1, x2, y2, width):
        """Rainure droite : deux arcs + deux lignes, tangences et rayons
        égaux posés d'emblée — le contour reste une rainure sous le solveur.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import math
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        w = float(width)
        p1x, p1y, p2x, p2y = (float(v) for v in (x1, y1, x2, y2))
        if w <= 0:
            raise KernelError("la largeur doit être positive")
        if math.hypot(p2x - p1x, p2y - p1y) < 1e-9:
            raise KernelError("les deux centres de la rainure sont confondus")
        r = w / 2.0
        theta = math.atan2(p2y - p1y, p2x - p1x)
        ux, uy = math.cos(theta + math.pi / 2), math.sin(theta + math.pi / 2)
        V = self._app().Vector
        z_axis = V(0, 0, 1)
        base = len(sk.Geometry)
        # Cap at p2 (CCW through +direction), top line, cap at p1, bottom.
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p2x, p2y, 0), z_axis, r),
            theta - math.pi / 2, theta + math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p2x + r * ux, p2y + r * uy, 0),
            V(p1x + r * ux, p1y + r * uy, 0)), False)
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p1x, p1y, 0), z_axis, r),
            theta + math.pi / 2, theta + 3 * math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p1x - r * ux, p1y - r * uy, 0),
            V(p2x - r * ux, p2y - r * uy, 0)), False)
        C = Sketcher.Constraint
        try:
            # Endpoint-to-endpoint tangency implies coincidence: the
            # standard Sketcher slot recipe.
            sk.addConstraint(C("Tangent", base + 0, 2, base + 1, 1))
            sk.addConstraint(C("Tangent", base + 1, 2, base + 2, 1))
            sk.addConstraint(C("Tangent", base + 2, 2, base + 3, 1))
            sk.addConstraint(C("Tangent", base + 3, 2, base + 0, 1))
            sk.addConstraint(C("Equal", base + 0, base + 2))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_polygon(self, sketch, cx, cy, x, y, sides):
        """Polygone régulier (centre + un sommet), via l'outil Sketcher."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        n = int(sides)
        if n < 3:
            raise KernelError("un polygone a au moins 3 côtés")
        try:
            from ProfileLib import RegularPolygon
        except ImportError:
            raise KernelError("outil polygone indisponible sur cette "
                              "version de FreeCAD")
        V = self._app().Vector
        center = V(float(cx), float(cy), 0)
        corner = V(float(x), float(y), 0)
        try:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner, False)
        except TypeError:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_fillet(self, sketch, geo1, geo2, x1, y1, x2, y2, radius):
        """Congé d'esquisse entre deux lignes, aux points cliqués.

        Le coin disparu reste comme point de construction : les cotes des
        deux lignes s'y rattachent au lieu d'être perdues, et le rayon est
        coté — l'esquisse reste aussi définie qu'avant."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        if float(radius) <= 0:
            raise KernelError("le rayon doit être positif")
        V = self._app().Vector
        import Sketcher
        before = len(sk.Geometry)
        try:
            sk.fillet(int(geo1), int(geo2),
                      V(float(x1), float(y1), 0), V(float(x2), float(y2), 0),
                      float(radius), True, True)
            arcs = [gid for gid in range(before, len(sk.Geometry))
                    if sk.Geometry[gid].TypeId == "Part::GeomArcOfCircle"]
            if arcs:
                sk.addConstraint(Sketcher.Constraint(
                    "Radius", arcs[0], float(radius)))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_trim(self, sketch, geo, x, y):
        """Ajuster : supprime le tronçon cliqué jusqu'aux intersections."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        V = self._app().Vector
        try:
            sk.trim(int(geo), V(float(x), float(y), 0))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _constraint_for(self, sk, kind, geo1, point1, geo2, point2, geo3):
        """Build the Sketcher constraint for one designer-facing kind.

        The usual relation set maps onto Sketcher with a few
        translations: colinéaire = Tangent between lines, concentrique =
        Coincident of centers, milieu = Symmetric of the line's endpoints
        about the point, fixe = Block.
        """
        from engine.kernel import KernelError
        import Sketcher
        C = Sketcher.Constraint
        line = "Part::GeomLineSegment"
        round_types = ("Part::GeomCircle", "Part::GeomArcOfCircle")
        g1 = int(geo1)
        if kind in ("horizontal", "vertical"):
            if geo2 is not None:
                # Deux points (extrémités, centres ou l'origine) alignés.
                if point1 is None or point2 is None:
                    raise KernelError(
                        "{} : une ligne, ou deux points".format(kind))
                return C(kind.capitalize(), g1, int(point1),
                         int(geo2), int(point2))
            return C(kind.capitalize(), g1)
        if kind == "fixed":
            return C("Block", g1)
        if geo2 is None:
            raise KernelError(
                "{} : sélectionnez deux entités".format(kind))
        g2 = int(geo2)
        if kind == "coincident":
            if point1 is None or point2 is None:
                raise KernelError("coïncidence : cliquez deux points "
                                  "(extrémités ou centres)")
            return C("Coincident", g1, int(point1), g2, int(point2))
        if kind == "concentric":
            for g in (g1, g2):
                if geo_of(sk, g).TypeId not in round_types:
                    raise KernelError("concentrique : deux cercles ou arcs")
            return C("Coincident", g1, 3, g2, 3)
        if kind == "collinear":
            for g in (g1, g2):
                if geo_of(sk, g).TypeId != line:
                    raise KernelError("colinéaire : deux lignes")
            return C("Tangent", g1, g2)
        if kind == "midpoint":
            # point (souvent un centre) au milieu d'une ligne — dans un
            # ordre ou l'autre.
            if geo_of(sk, g1).TypeId == line and point2 is not None:
                return C("Symmetric", g1, 1, g1, 2, g2, int(point2))
            if geo_of(sk, g2).TypeId == line and point1 is not None:
                return C("Symmetric", g2, 1, g2, 2, g1, int(point1))
            raise KernelError("milieu : un point et une ligne")
        if kind == "symmetric":
            if geo3 is None or point1 is None or point2 is None:
                raise KernelError(
                    "symétrique : deux points puis la ligne d'axe")
            g3 = int(geo3)
            if geo_of(sk, g3).TypeId != line:
                raise KernelError("symétrique : le 3e élément doit être "
                                  "une ligne (l'axe)")
            return C("Symmetric", g1, int(point1), g2, int(point2), g3)
        if kind == "onobject":
            # Un point posé sur une courbe (ligne prolongée, cercle…).
            if point1 is not None and point2 is None:
                return C("PointOnObject", g1, int(point1), g2)
            if point2 is not None and point1 is None:
                return C("PointOnObject", g2, int(point2), g1)
            raise KernelError("sur l'entité : un point et une courbe")
        if kind == "coradial":
            for g in (g1, g2):
                if geo_of(sk, g).TypeId not in round_types:
                    raise KernelError("corradiale : deux cercles ou arcs")
            return [C("Coincident", g1, 3, g2, 3), C("Equal", g1, g2)]
        if kind == "intersection":
            if point1 is None or geo3 is None:
                raise KernelError("intersection : un point puis deux "
                                  "courbes")
            return [C("PointOnObject", g1, int(point1), g2),
                    C("PointOnObject", g1, int(point1), int(geo3))]
        if kind in ("parallel", "perpendicular", "equal", "tangent"):
            names = {"parallel": "Parallel", "perpendicular": "Perpendicular",
                     "equal": "Equal", "tangent": "Tangent"}
            return C(names[kind], g1, g2)
        raise KernelError("contrainte inconnue « {} » — attendu : {}".format(
            kind, "horizontal, vertical, coincident, parallel, perpendicular, "
            "equal, tangent, concentric, collinear, midpoint, symmetric, "
            "fixed, onobject, coradial, intersection"))

    def sketch_constrain(self, sketch, kind, geo1, point1=None,
                         geo2=None, point2=None, geo3=None):
        """Contrainte manuelle. Points au sens Sketcher : 1 départ, 2 fin,
        3 centre. ``symmetric`` prend trois entités (2 points + l'axe)."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        try:
            constraint = self._constraint_for(
                sk, str(kind), geo1, point1, geo2, point2, geo3)
            for item in (constraint if isinstance(constraint, list)
                         else [constraint]):
                sk.addConstraint(item)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_circle(self, sketch, cx, cy, r, snaps=None):
        """Cercle. ``snaps`` : ``center`` et ``on``, les points posés sur
        le cercle (le clic du rayon, ou les trois points)."""
        from engine.kernel import KernelError
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        parsed = (None if snaps is None
                  else self._snap_targets(sk, "sketch_add_circle", snaps))
        App = self._app()
        gid = sk.addGeometry(Part.Circle(
            App.Vector(float(cx), float(cy), 0),
            App.Vector(0, 0, 1), float(r)), False)
        if parsed is not None:
            self._add_snap_constraints(sk, self._round_snap_links(
                sk, gid, parsed, (("center", gid, 3),)))
        # Centre posé sur l'origine (le client y accroche) : coïncident.
        elif self._coincident_2d(cx, cy, 0, 0):
            import Sketcher
            sk.addConstraint(Sketcher.Constraint("Coincident", gid, 3, -1, 1))
        return self.sketch_state(sketch)

    def sketch_move(self, sketch, geo, point, x, y):
        """Drag: move one point, let the solver follow. ``point`` is the
        Sketcher convention — 1 start, 2 end, 3 center, 0 whole curve.

        The API was renamed across FreeCAD versions (movePoint →
        moveGeometry, plus a grouped moveGeometries), so this tries the
        known spellings in order — 1.1.3 has no ``movePoint`` at all,
        which the instrumented selftest caught on a real install.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        gid, pos = int(geo), int(point)
        target = self._app().Vector(float(x), float(y), 0)
        attempts = (
            ("moveGeometry", lambda fn: fn(gid, pos, target, 0)),
            ("movePoint", lambda fn: fn(gid, pos, target, 0)),
            ("moveGeometries", lambda fn: fn([(gid, pos)], target, False)),
        )
        tried = []
        for name, invoke in attempts:
            fn = getattr(sk, name, None)
            if fn is None:
                continue
            tried.append(name)
            try:
                invoke(fn)
                return self.sketch_state(sketch)
            except TypeError:
                continue  # exists but wants another signature: next spelling
            except Exception as exc:  # noqa: BLE001 - solver refusal
                raise KernelError(_explain(exc))
        raise KernelError(
            "aucune API de déplacement compatible sur cette version de "
            "FreeCAD (essayé : {})".format(", ".join(tried) or "aucune"))

    def sketch_drop(self, sketch, geo, point, x, y, snaps=None):
        """Lâcher d'un point glissé sur ce que l'interface a accroché
        (``snaps`` : ``at``, une cible de ``engine/sketchsnap.py``) : le
        point va en (x, y) et la relation qui l'y tient est posée. Une
        seule opération, un seul Ctrl+Z — le glisser lui-même
        (``sketch_move``) n'en a pas. Une relation qui rendrait l'esquisse
        redondante ou contradictoire n'est pas posée, le point reste où
        il est lâché."""
        from engine.kernel import KernelError
        from engine.sketchsnap import geos_of, relations, snap_positions
        sk = self._get_sketch(sketch)
        gid, pos = int(geo), int(point)
        if not (0 <= gid < len(sk.Geometry)
                and pos in snap_positions(sk.Geometry[gid].TypeId)):
            raise KernelError("point {}.{} introuvable".format(gid, pos))
        parsed = self._snap_targets(sk, "sketch_drop", snaps or {})
        target = parsed.get("at")
        if target is not None and gid in geos_of(target):
            raise KernelError(
                "accrochage « at » : un point ne s'accroche pas à son entité")
        self.sketch_move(sketch, gid, pos, x, y)
        if target is not None:
            self._add_snap_constraints(sk, self._constraints(sk, relations(
                target, gid, pos, lambda g: geo_of(sk, g).TypeId)))
        return self.sketch_state(sketch)

    @staticmethod
    def _point_of(geo, pos):
        """Sketcher point convention: 1 start, 2 end, 3 center.
        ``geo`` None : le point racine (l'origine de l'esquisse)."""
        if geo is None:
            import FreeCAD
            return FreeCAD.Vector(0, 0, 0)
        if pos == 3:
            return geo.Center
        if pos == 2:
            return geo.EndPoint
        return geo.StartPoint

    @staticmethod
    def _distance_point_line(p, a, b):
        import math
        abx, aby = b.x - a.x, b.y - a.y
        denominator = math.hypot(abx, aby)
        if denominator < 1e-12:
            return 0.0
        return abs(abx * (p.y - a.y) - aby * (p.x - a.x)) / denominator

    def _dim_two(self, sk, g1, g2, point, point2, value, axis=None):
        """Smart dimension between two entities — the pair decides the
        constraint, as under the cursor: two points → distance,
        point + line → distance, parallel lines → distance, otherwise angle
        (radians on the wire; the client displays degrees). Un cercle ou un
        arc compte par son centre face à un point, une ligne ou un autre
        cercle."""
        from engine.kernel import KernelError
        import math
        import Sketcher
        C = Sketcher.Constraint
        line = "Part::GeomLineSegment"
        round_types = ("Part::GeomCircle", "Part::GeomArcOfCircle")
        if g1 == ROOT_GEO:
            # L'origine en premier : on la met en second, la cote est la même.
            g1, g2, point, point2 = g2, g1, point2, point
        if g2 == ROOT_GEO:
            point2 = 1
        # Un cercle ou un arc coté contre un point se prend par son centre.
        if (point is None and point2 is not None
                and geo_of(sk, g1).TypeId in round_types):
            point = 3
        if (point2 is None and point is not None and g2 != ROOT_GEO
                and geo_of(sk, g2).TypeId in round_types):
            point2 = 3
        if point is None and point2 is None and g2 != ROOT_GEO:
            round1 = geo_of(sk, g1).TypeId in round_types
            round2 = geo_of(sk, g2).TypeId in round_types
            if round1 and round2:
                point = point2 = 3          # deux cercles : entre centres
            elif round1:
                point = 3                   # cercle + ligne : centre → ligne
            elif round2:
                point2 = 3
        if point is None and point2 is not None:
            # Normalize "line then point" to "point then line".
            g1, g2 = g2, g1
            point, point2 = point2, None
        e1 = geo_of(sk, g1)
        e2 = None if g2 == ROOT_GEO else geo_of(sk, g2)
        if point is not None and point2 is not None:
            v1 = self._point_of(e1, int(point))
            v2 = self._point_of(e2, int(point2))
            if axis in ("x", "y"):
                # Cote horizontale / verticale : de la plus petite coordonnée
                # à la plus grande, la valeur reste positive.
                along = (lambda v: v.x) if axis == "x" else (lambda v: v.y)
                if along(v2) < along(v1):
                    g1, g2, point, point2 = g2, g1, point2, point
                    v1, v2 = v2, v1
                distance = (abs(value) if value is not None
                            else along(v2) - along(v1))
                return C("DistanceX" if axis == "x" else "DistanceY",
                         g1, int(point), g2, int(point2), float(distance))
            distance = value if value is not None else v1.distanceToPoint(v2)
            return C("Distance", g1, int(point), g2, int(point2),
                     float(distance))
        if point is not None and e2 is not None and e2.TypeId == line:
            v1 = self._point_of(e1, int(point))
            distance = (value if value is not None else
                        self._distance_point_line(
                            v1, e2.StartPoint, e2.EndPoint))
            return C("Distance", g1, int(point), g2, float(distance))
        if e2 is not None and e1.TypeId == line and e2.TypeId == line:
            d1x = e1.EndPoint.x - e1.StartPoint.x
            d1y = e1.EndPoint.y - e1.StartPoint.y
            d2x = e2.EndPoint.x - e2.StartPoint.x
            d2y = e2.EndPoint.y - e2.StartPoint.y
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-7 * math.hypot(d1x, d1y) * math.hypot(d2x, d2y):
                distance = (value if value is not None else
                            self._distance_point_line(
                                e1.StartPoint, e2.StartPoint, e2.EndPoint))
                return C("Distance", g1, 1, g2, float(distance))
            # Sketcher compte l'angle de la 1re ligne vers la 2e, dans le
            # sens trigonométrique : on les ordonne ainsi, sinon la cote
            # ferait pivoter les lignes pour inverser l'angle.
            if cross < 0:
                g1, g2 = g2, g1
            angle = (value if value is not None else
                     abs(math.atan2(cross, d1x * d2x + d1y * d2y)))
            return C("Angle", g1, g2, float(angle))
        raise KernelError("cote non gérée entre ces deux entités — "
                          "deux points, un point et une ligne, ou deux "
                          "lignes")

    #: Position de cote par défaut de Sketcher : « jamais posée ».
    _DEFAULT_LABEL = (10.0, 0.0)

    def _place_dim(self, sk, index, at):
        """Retient où la cote a été posée : le décalage (signé, en mm) de
        sa ligne par rapport à son premier point — au-dessus pour une
        horizontale, à droite pour une verticale, sur la normale A→B pour
        une alignée. Stocké dans ``LabelDistance``, sauvé avec la pièce."""
        if at is None:
            return
        try:
            x, y = float(at[0]), float(at[1])
            c = sk.Constraints[index]
            if c.Type == "Angle":
                corner = self._angle_corner(sk, c)
                if corner is not None:
                    import math
                    self._set_dim_offset(
                        sk, index, math.hypot(x - corner.x, y - corner.y))
                return
            a, b = self._dim_ends(sk, c)
            if a is None:
                return
            if c.Type == "DistanceX":
                offset = y - a.y
            elif c.Type == "DistanceY":
                offset = x - a.x
            else:
                import math
                dx, dy = b.x - a.x, b.y - a.y
                length = math.hypot(dx, dy)
                if length < 1e-12:
                    return
                offset = ((x - a.x) * -dy + (y - a.y) * dx) / length
            self._set_dim_offset(sk, index, offset)
        except Exception:
            pass  # la cote reste, à sa place par défaut

    def _set_dim_offset(self, sk, index, offset):
        if (round(offset, 9), 0.0) == self._DEFAULT_LABEL:
            offset += 1e-6  # 10 tout rond voudrait dire « jamais posée »
        sk.setLabelDistance(index, float(offset))

    @staticmethod
    def _angle_corner(sk, c):
        """Point de rencontre des deux lignes d'une cote d'angle."""
        try:
            l1, l2 = geo_of(sk, c.First), geo_of(sk, c.Second)
            p, r = l1.StartPoint, l1.EndPoint - l1.StartPoint
            q, s = l2.StartPoint, l2.EndPoint - l2.StartPoint
            den = r.x * s.y - r.y * s.x
            if abs(den) < 1e-12:
                return None
            t = ((q.x - p.x) * s.y - (q.y - p.y) * s.x) / den
            return p + r * t
        except Exception:
            return None

    def _dim_ends(self, sk, c):
        """Les deux points mesurés d'une cote de distance (A, B)."""
        undefined = -2000
        first, second = c.First, c.Second
        pos1 = int(getattr(c.FirstPos, "value", c.FirstPos) or 0)
        pos2 = int(getattr(c.SecondPos, "value", c.SecondPos) or 0)
        geo1 = None if first == ROOT_GEO else geo_of(sk, first)
        if second is None or second <= undefined:
            if geo1 is None or geo1.TypeId != "Part::GeomLineSegment":
                return None, None
            return geo1.StartPoint, geo1.EndPoint
        if not pos1 or not pos2:
            return None, None
        geo2 = None if second == ROOT_GEO else geo_of(sk, second)
        return self._point_of(geo1, pos1), self._point_of(geo2, pos2)

    def sketch_dim(self, sketch, geo, value=None,
                   geo2=None, point=None, point2=None, axis=None, at=None,
                   radius=False, measure=None):
        """Smart dimension: length on a line, diameter on a circle,
        radius on an arc, distance/angle between two entities.

        Driving: dimension it and the geometry obeys. ``at`` : le point
        (x, y de l'esquisse) où la cote a été posée ; sa ligne y passe.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Sketcher
        sk = self._get_sketch(sketch)
        gid = int(geo)
        # L'origine (point racine) ne se cote que contre une autre entité.
        if not ((gid == ROOT_GEO and geo2 is not None)
                or (gid != ROOT_GEO and is_geo(sk, gid))):
            raise KernelError("géométrie inconnue : {}".format(geo))
        try:
            if geo2 is not None:
                g2 = int(geo2)
                # La même entité deux fois : seulement par deux de ses
                # points (longueur projetée d'une ligne).
                if ((g2 != ROOT_GEO and not is_geo(sk, g2))
                        or (g2 == gid and (point is None or point2 is None
                                           or point == point2))):
                    raise KernelError("géométrie inconnue : {}".format(geo2))
                index = sk.addConstraint(self._dim_two(
                    sk, gid, g2, point, point2, value,
                    axis=str(axis).lower() if axis else None))
                self._place_dim(sk, index, at)
                return self.sketch_state(sketch)
            target = geo_of(sk, gid)
            if measure:
                index = self._dim_measure(sk, gid, target, str(measure),
                                          value)
                self._place_dim(sk, index, at)
                return self.sketch_state(sketch)
            if target.TypeId == "Part::GeomLineSegment":
                length = (value if value is not None
                          else target.StartPoint.distanceToPoint(
                              target.EndPoint))
                index = sk.addConstraint(Sketcher.Constraint(
                    "Distance", gid, float(length)))
                self._place_dim(sk, index, at)
            elif target.TypeId == "Part::GeomCircle" and radius:
                # Cercle puis son centre : le rayon.
                value_r = value if value is not None else target.Radius
                sk.addConstraint(Sketcher.Constraint(
                    "Radius", gid, float(value_r)))
            elif target.TypeId == "Part::GeomCircle":
                # Un cercle se cote au diamètre, un arc au rayon.
                diameter = (value if value is not None
                            else 2 * target.Radius)
                sk.addConstraint(Sketcher.Constraint(
                    "Diameter", gid, float(diameter)))
            elif target.TypeId == "Part::GeomArcOfCircle":
                radius = value if value is not None else target.Radius
                sk.addConstraint(Sketcher.Constraint(
                    "Radius", gid, float(radius)))
            else:
                raise KernelError("cote non gérée sur ce type de géométrie")
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    @staticmethod
    def _dim_measure(sk, gid, target, measure, value):
        """Cotes à une entité au-delà de la cote « intelligente » :
        longueur d'arc, diamètre d'arc, angle d'une ligne à l'axe X."""
        from engine.kernel import KernelError
        import math
        import Sketcher
        C = Sketcher.Constraint
        if measure == "arc_length":
            if target.TypeId != "Part::GeomArcOfCircle":
                raise KernelError("longueur d'arc : cliquez un arc")
            length = (value if value is not None else target.Radius
                      * (target.LastParameter - target.FirstParameter))
            return sk.addConstraint(C("Distance", gid, float(length)))
        if measure == "diameter":
            if target.TypeId not in ("Part::GeomArcOfCircle",
                                     "Part::GeomCircle"):
                raise KernelError("diamètre : cliquez un cercle ou un arc")
            diameter = value if value is not None else 2 * target.Radius
            return sk.addConstraint(C("Diameter", gid, float(diameter)))
        if measure == "axis_angle":
            if target.TypeId != "Part::GeomLineSegment":
                raise KernelError("angle à l'axe : cliquez une ligne")
            d = target.EndPoint - target.StartPoint
            angle = value if value is not None else math.atan2(d.y, d.x)
            return sk.addConstraint(C("Angle", gid, float(angle)))
        raise KernelError("cote inconnue : {}".format(measure))

    def sketch_place_dim(self, sketch, dim, offset):
        """Déplace une cote posée : nouveau décalage de sa ligne (même
        convention que la pose, voir ``_place_dim``). La valeur ne change
        pas."""
        from engine.kernel import KernelError
        sk = self._get_sketch(sketch)
        idx = int(dim)
        if idx < 0 or idx >= len(sk.Constraints):
            raise KernelError("cote inconnue : {}".format(dim))
        self._set_dim_offset(sk, idx, float(offset))
        return self.sketch_state(sketch)

    def sketch_set_dim(self, sketch, dim, value=None, name=None, expr=None,
                       driving=None):
        """Edit a dimension — the double-click-a-dim gesture, complete:
        value, **name** (``largeur``) and **expression** (``largeur/2``).

        An expression takes over the value; setting a plain value clears
        any expression. Names make the equation workflow:
        name a dim, then reference it from any other dim or feature.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        idx = int(dim)
        if idx < 0 or idx >= len(sk.Constraints):
            raise KernelError("cote inconnue : {}".format(dim))
        try:
            if name is not None:
                name = str(name).strip()
                if name and not self._valid_identifier(name):
                    raise KernelError(
                        "nom invalide « {} » — lettres, chiffres et _ "
                        "seulement".format(name))
                sk.renameConstraint(idx, name)
            if driving is not None and bool(driving) != bool(
                    getattr(sk.Constraints[idx], "Driving", True)):
                # Cote de référence : elle mesure, elle ne pilote plus.
                sk.setDriving(idx, bool(driving))
            path = "Constraints[{}]".format(idx)
            if expr is not None and str(expr).strip():
                sk.setExpression(path, self._user_expression(expr))
            elif value is not None:
                try:
                    sk.setExpression(path, None)
                except Exception:
                    pass
                target = float(value)
                if (sk.Constraints[idx].Type in ("DistanceX", "DistanceY")
                        and sk.Constraints[idx].Value < 0):
                    # Cote affichée sans signe : le sens reste celui tracé.
                    target = -abs(target)
                sk.setDatum(idx, target)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        if self._assembly:
            self._require_doc().recompute()
        else:
            # _recompute passe aussi les crochets after_recompute des
            # plugins : sans lui, la cote change et l'écran ne suit pas.
            self._recompute()
        return self.sketch_state(sketch)

    #: Libellé français des types de contraintes, pour le panneau Relations.

    def sketch_constraints(self, sketch, geo=None):
        """Les relations de l'esquisse — filtrables par entité.

        C'est la sortie du mur des esquisses sur-contraintes : voir ce qui
        tient une entité, et pouvoir supprimer la relation de trop.
        """
        sk = self._get_sketch(sketch)
        undefined = -2000  # Sketcher.GeoUndef
        items = []
        for cid, constraint in enumerate(sk.Constraints):
            geos = [g for g in (constraint.First, constraint.Second,
                                constraint.Third)
                    if g is not None and g != undefined]
            if geo is not None and int(geo) not in geos:
                continue
            entry = {
                "id": cid,
                "type": constraint.Type,
                "label": self._CONSTRAINT_LABELS.get(
                    constraint.Type, constraint.Type),
                "geos": geos,
                "name": constraint.Name or "",
            }
            if constraint.Type in ("Distance", "DistanceX", "DistanceY",
                                   "Radius", "Diameter", "Angle"):
                entry["value"] = float(constraint.Value)
            items.append(entry)
        return {"constraints": items}

    def sketch_delete_constraint(self, sketch, constraint):
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        idx = int(constraint)
        if idx < 0 or idx >= len(sk.Constraints):
            raise KernelError("relation inconnue : {}".format(constraint))
        try:
            sk.delConstraint(idx)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _is_construction(self, sk, gid, geo):
        """Construction flag across API generations: attribute on old
        geometry objects, ``getConstruction`` on 1.x facades."""
        flag = getattr(geo, "Construction", None)
        if flag is not None:
            return bool(flag)
        getter = getattr(sk, "getConstruction", None)
        if getter is not None:
            try:
                return bool(getter(gid))
            except Exception:
                pass
        return False

    def sketch_toggle_construction(self, sketch, geo):
        """Basculer une entité en géométrie de construction, et retour."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        try:
            sk.toggleConstruction(int(geo))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_delete_geo(self, sketch, geo):
        from engine.kernel import (
            KernelError,
            _explain,
        )
        sk = self._get_sketch(sketch)
        try:
            if int(geo) <= -3:
                sk.delExternal(-int(geo) - 3)
                self._require_doc().recompute()
                return self.sketch_state(sketch)
            sk.delGeometry(int(geo))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_convert(self, sketch, face=None):
        """Convertir les entités : le contour d'une face devient de la
        géométrie d'esquisse réelle, bloquée (Block) — le geste usuel
        « esquisse sur face → convertir → décaler/modifier ».

        Sans ``face``, la face porteuse de l'esquisse est utilisée.
        Lignes, cercles et arcs parallèles au plan sont convertis ; le
        reste est compté dans ``skipped``.
        """
        from engine.kernel import KernelError
        import math
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        body = self._require_body()
        target = None
        if face is not None:
            faces = body.Shape.Faces
            index = int(face)
            if index < 0 or index >= len(faces):
                raise KernelError("face inconnue : {}".format(face))
            target = faces[index]
        else:
            support = (getattr(sk, "AttachmentSupport", None)
                       or getattr(sk, "Support", None))
            try:
                for obj, subs in list(support or ()):
                    for sub in subs:
                        if str(sub).startswith("Face"):
                            target = obj.Shape.Faces[int(str(sub)[4:]) - 1]
                            break
                    if target is not None:
                        break
            except Exception:
                target = None
            if target is None:
                raise KernelError(
                    "l'esquisse n'est pas posée sur une face — cliquez "
                    "d'abord une face, ou passez face=<id>")
        inverse = sk.Placement.inverse()
        V = self._app().Vector
        C = Sketcher.Constraint
        added = skipped = 0
        for edge in target.Edges:
            curve = edge.Curve
            kind = type(curve).__name__
            gid = None
            try:
                if kind == "Line":
                    p1 = inverse.multVec(edge.Vertexes[0].Point)
                    p2 = inverse.multVec(edge.Vertexes[-1].Point)
                    if p1.distanceToPoint(p2) < 1e-9:
                        skipped += 1
                        continue
                    gid = sk.addGeometry(Part.LineSegment(
                        V(p1.x, p1.y, 0), V(p2.x, p2.y, 0)), False)
                elif kind == "Circle":
                    axis_local = inverse.Rotation.multVec(curve.Axis)
                    if abs(axis_local.z) < 0.99:
                        skipped += 1
                        continue
                    center = inverse.multVec(curve.Center)
                    circle = Part.Circle(V(center.x, center.y, 0),
                                         V(0, 0, 1), curve.Radius)
                    if edge.isClosed():
                        gid = sk.addGeometry(circle, False)
                    else:
                        s = inverse.multVec(edge.Vertexes[0].Point)
                        e = inverse.multVec(edge.Vertexes[-1].Point)
                        m = inverse.multVec(edge.valueAt(
                            (edge.FirstParameter + edge.LastParameter) / 2))
                        a_s = math.atan2(s.y - center.y, s.x - center.x)
                        a_e = math.atan2(e.y - center.y, e.x - center.x)
                        a_m = math.atan2(m.y - center.y, m.x - center.x)

                        def onward(a, start):
                            return a + 2 * math.pi if a <= start else a
                        if onward(a_m, a_s) < onward(a_e, a_s):
                            a1, a2 = a_s, onward(a_e, a_s)
                        else:
                            a1, a2 = a_e, onward(a_s, a_e)
                        gid = sk.addGeometry(
                            Part.ArcOfCircle(circle, a1, a2), False)
                else:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            sk.addConstraint(C("Block", gid))
            added += 1
        if not added:
            raise KernelError("aucune arête convertible sur cette face "
                              "(lignes, cercles, arcs)")
        state = self.sketch_state(sketch)
        state["converted"] = added
        state["skipped"] = skipped
        return state

    def sketch_finish(self, sketch):
        """Close the sketch: recompute and hand back the feature tree."""
        self._get_sketch(sketch)
        self._sketch_session = None
        self._recompute()
        tree = self.get_tree()
        tree["open_profile"] = self._sketch_open_profile(sketch)
        return tree

    def _sketch_open_profile(self, sketch):
        """True si la géométrie réelle ne forme aucune boucle fermée.

        Esquisse vide ou 100 % construction : False — rien d'anormal,
        pas de message côté client. Au moins une boucle fermée : False.
        """
        import Part
        sk = self._get_sketch(sketch)
        edges = []
        for gid, geo in enumerate(sk.Geometry):
            if self._is_construction(sk, gid, geo):
                continue
            try:
                shape = geo.toShape()
            except Exception:
                continue
            if getattr(shape, "ShapeType", None) == "Edge":
                edges.append(shape)
            else:
                edges.extend(list(getattr(shape, "Edges", ()) or ()))
        if not edges:
            return False
        try:
            chains = Part.sortEdges(edges)
        except Exception:
            return True
        for chain in chains:
            try:
                if Part.Wire(chain).isClosed():
                    return False
            except Exception:
                continue
        if any(bool(getattr(edge, "Closed", False)) for edge in edges):
            return False
        return True

    def _top_face_id(self):
        """Index of the upward-facing face with the highest centroid.

        Used on the production path when a replayed sketch sits on a
        face: pick the current top rather than a stale face index.
        """
        from engine.kernel import (
            KernelError,
            UPWARD_Z,
        )
        body = self._require_body()
        best, best_z = None, None
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if normal.z <= UPWARD_Z:
                continue
            z = face.CenterOfMass.z
            if best_z is None or z > best_z:
                best, best_z = i, z
        if best is None:
            raise KernelError("aucune face orientée vers le haut")
        return best

    def _side_face_id(self):
        """Selftest helper: any vertical (side) face of the current shape."""
        from engine.kernel import KernelError
        body = self._require_body()
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if abs(normal.z) < 0.1:
                return i
        raise KernelError("aucune face latérale")
