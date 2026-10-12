"""Chanfrein de sommet : le coin où se rejoignent trois arêtes est coupé
par le plan qui passe à une distance donnée sur chacune d'elles (une
distance égale, ou une par arête).

La forme est calculée à part puis rangée dans l'historique comme la
suppression de face (``_commit_frozen``) : elle est recalculée à chaque
reconstruction à partir de la fonction d'avant. Le sommet est repéré par
son numéro dans cette forme. Les imports FreeCAD restent dans les
méthodes ; ``parse_spec`` et ``format_spec`` sont testées en CI.
"""


def format_spec(vertex, distances):
    """« sommet;d1;d2;d3 » — rangé sur la forme figée et la fonction."""
    return "%d;%s" % (int(vertex), ";".join("%.9g" % float(d)
                                             for d in distances))


def parse_spec(spec):
    """(sommet, [d1, d2, d3]) ; une seule distance vaut pour les trois."""
    parts = [p for p in str(spec).split(";") if p != ""]
    vertex = int(parts[0])
    distances = [float(p) for p in parts[1:]]
    if len(distances) == 1:
        distances *= 3
    return vertex, distances


def check_distances(distances):
    """Une distance (égale) ou trois, toutes positives ; sinon un message."""
    values = [float(d) for d in distances or ()]
    if len(values) not in (1, 3):
        return "donnez une distance, ou une par arête (trois)"
    if any(d <= 0 for d in values):
        return "distance de chanfrein invalide"
    return None


class VertexChamferMixin:
    """Ops : chanfrein de sommet (création, réédition)."""

    def _vertex_chamfered(self, base_shape, spec):
        """Le solide dont le coin ``spec`` est coupé."""
        from engine.kernel import KernelError
        import FreeCAD
        import Part
        vertex, distances = parse_spec(spec)
        if not 0 <= vertex < len(base_shape.Vertexes):
            raise KernelError("sommet inconnu : {}".format(vertex))
        corner = base_shape.Vertexes[vertex]
        edges = []
        for edge in base_shape.ancestorsOfType(corner, Part.Edge):
            if not any(edge.isSame(other) for other in edges):
                edges.append(edge)
        if len(edges) != 3:
            raise KernelError("un chanfrein de sommet demande un coin où se "
                              "rejoignent trois arêtes")

        def index_of(edge):
            return next(i for i, e in enumerate(base_shape.Edges)
                        if e.isSame(edge))
        edges.sort(key=index_of)
        points = []
        for edge, distance in zip(edges, distances):
            if distance >= edge.Length - 1e-9:
                raise KernelError("la distance {} mm dépasse l'arête".format(
                    "%g" % distance))
            start = edge.valueAt(edge.FirstParameter)
            along = (distance if (start - corner.Point).Length < 1e-6
                     else edge.Length - distance)
            points.append(edge.valueAt(edge.getParameterByLength(along)))
        p1, p2, p3 = points
        normal = (p2 - p1).cross(p3 - p1)
        if normal.Length < 1e-12:
            raise KernelError("ces distances ne définissent pas de plan")
        normal.normalize()
        side = (corner.Point - p1).dot(normal)
        if abs(side) < 1e-9:
            raise KernelError("ce sommet n'est pas un coin saillant")
        if side < 0:
            normal = normal * -1
        # Outil : la boule autour du coin, du côté du coin par rapport au
        # plan. Le coin est dans la boule ; le reste de la pièce n'y entre
        # pas tant que les distances restent sous la longueur des arêtes.
        reach = max((p - corner.Point).Length for p in points) * 1.0001
        ball = Part.makeSphere(reach, corner.Point)
        u = p2 - p1
        u.normalize()
        w = normal.cross(u)
        size = 3 * reach
        box = Part.makeBox(2 * size, 2 * size, size)
        box.transformShape(FreeCAD.Matrix(
            u.x, w.x, normal.x, 0, u.y, w.y, normal.y, 0,
            u.z, w.z, normal.z, 0, 0, 0, 0, 1))
        box.translate(p1 - u * size - w * size)
        try:
            result = base_shape.cut(ball.common(box)).removeSplitter()
        except Exception:  # noqa: BLE001
            result = None
        if (result is None or result.isNull() or not result.Solids
                or not result.isValid()):
            raise KernelError("le coin ne se laisse pas chanfreiner")
        if base_shape.Volume - result.Volume < 1e-9:
            raise KernelError("ce sommet n'est pas un coin saillant")
        if len(result.Solids) > 1:
            result = max(result.Solids, key=lambda solid: solid.Volume)
        return result

    def _nearest_vertex(self, shape, point):
        """Numéro du sommet le plus proche d'un point cliqué."""
        from engine.kernel import KernelError
        import FreeCAD
        at = FreeCAD.Vector(*[float(c) for c in point])
        best = min(range(len(shape.Vertexes)),
                   key=lambda i: (shape.Vertexes[i].Point - at).Length,
                   default=None)
        tolerance = max(0.5, 0.02 * shape.BoundBox.DiagonalLength)
        if best is None or (shape.Vertexes[best].Point - at).Length > tolerance:
            raise KernelError("cliquez un coin de la pièce")
        return best

    def add_vertex_chamfer(self, distances, point=None, vertex=None):
        """Chanfrein du coin cliqué (``point``, aimanté au sommet le plus
        proche) ou du sommet numéro ``vertex``."""
        from engine.kernel import KernelError
        problem = check_distances(distances)
        if problem:
            raise KernelError(problem)
        tip = self._solid_tip("un chanfrein de sommet demande un solide")
        if vertex is None:
            if point is None:
                raise KernelError("cliquez un coin de la pièce")
            vertex = self._nearest_vertex(tip.Shape, point)
        spec = format_spec(vertex, distances)
        stamps = {"vchamferbase": tip.Name, "vchamfer": spec}
        result = self._frozen_result(stamps, tip.Shape)
        return self._commit_frozen(tip, result, stamps, "Chanfrein de sommet",
                                   {"vchamferspec": spec})

    def edit_vertex_chamfer(self, feature, distances):
        """Nouvelles distances d'un chanfrein de sommet."""
        from engine.kernel import KernelError
        problem = check_distances(distances)
        if problem:
            raise KernelError(problem)
        doc = self._require_doc()
        owner = doc.getObject(str(feature))
        if owner is None or not getattr(owner, "FreeSolidVchamferspec", ""):
            raise KernelError("chanfrein de sommet inconnu : {}".format(
                feature))
        frozen = None
        for obj in getattr(owner, "Group", None) or ():
            base = getattr(obj, "BaseFeature", None)
            if getattr(base, "FreeSolidVchamferbase", ""):
                frozen = base
        if frozen is None:
            raise KernelError("chanfrein incomplet — la forme est absente")
        vertex, _ = parse_spec(frozen.FreeSolidVchamfer)
        spec = format_spec(vertex, distances)
        source = doc.getObject(frozen.FreeSolidVchamferbase)
        frozen.Shape = self._vertex_chamfered(source.Shape, spec)
        frozen.FreeSolidVchamfer = spec
        owner.FreeSolidVchamferspec = spec
        self._recompute()
        return self.get_tree()
