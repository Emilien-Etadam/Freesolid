"""Géométrie de référence : axe, point, repère.

Comme le plan de référence, ils vivent dans le corps et suivent ce qui
les porte : un axe d'origine, une arête droite ou circulaire ; un sommet,
le centre d'un cercle ou des coordonnées ; un repère sur un sommet ou à
des coordonnées. Les imports FreeCAD restent dans les méthodes.
"""

_AXIS_ROLES = {"X": "X_Axis", "Y": "Y_Axis", "Z": "Z_Axis"}

#: Types de la géométrie de référence (l'arbre leur donne un placement).
REFERENCE_TYPES = frozenset({
    "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
    "PartDesign::CoordinateSystem",
})


class RefGeomMixin:
    """Ops : add_datum_axis, add_datum_point, add_datum_cs."""

    def _new_datum(self, type_id, name, label, support, mode, at=None):
        """Crée l'objet, l'attache (ou le pose à ``at``), le retire si la
        reconstruction échoue."""
        from engine.kernel import KernelError, _explain
        App = self._app()
        body = self._require_body()
        doc = self._require_doc()
        obj = body.newObject(type_id, name)
        try:
            if support:
                obj.AttachmentSupport = support
                obj.MapMode = mode
            else:
                obj.MapMode = "Deactivated"
                obj.Placement = App.Placement(
                    App.Vector(*[float(c) for c in at]), App.Rotation())
            obj.Label = self._t(label)
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(obj.Name)
            except Exception:  # noqa: BLE001
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def _edge_support(self, edge):
        """(appui, mode) d'une arête du solide : droite ou circulaire."""
        from engine.kernel import KernelError
        tip = self._solid_tip("un élément de référence sur une arête "
                              "demande un solide")
        edges = tip.Shape.Edges
        index = int(edge)
        if not 0 <= index < len(edges):
            raise KernelError("arête inconnue : {}".format(index))
        curve = edges[index].Curve.TypeId
        support = [(tip, "Edge{}".format(index + 1))]
        if curve == "Part::GeomLine":
            return support, "straight"
        if curve in ("Part::GeomCircle", "Part::GeomEllipse"):
            return support, "circle"
        raise KernelError("choisissez une arête droite ou circulaire")

    def _vertex_support(self, at):
        tip = self._solid_tip("un élément de référence sur un sommet "
                              "demande un solide")
        index = self._nearest_vertex(tip.Shape, at)
        return [(tip, "Vertex{}".format(index + 1))]

    def add_datum_axis(self, axis=None, edge=None):
        """Axe de référence : sur un axe d'origine (``axis`` X, Y ou Z), le
        long d'une arête droite, ou sur l'axe d'une arête circulaire."""
        from engine.kernel import KernelError
        if edge is not None:
            support, shape = self._edge_support(edge)
            mode = "TwoPointLine" if shape == "straight" else "AxisOfCurvature"
        else:
            role = _AXIS_ROLES.get(str(axis or "Z").upper())
            if role is None:
                raise KernelError("axe inconnu « {} » — attendu X, Y ou Z"
                                  .format(axis))
            support = [(self._origin_feature(role), "")]
            mode = "TwoPointLine"
        return self._new_datum("PartDesign::Line", "DatumLine",
                               "Axe de référence", support, mode)

    def add_datum_point(self, point=None, vertex=None, edge=None):
        """Point de référence : sur le sommet le plus proche de ``vertex``
        (coordonnées cliquées), au centre d'une arête circulaire, ou aux
        coordonnées ``point``."""
        from engine.kernel import KernelError
        if vertex is not None:
            return self._new_datum("PartDesign::Point", "DatumPoint",
                                   "Point de référence",
                                   self._vertex_support(vertex), "Vertex")
        if edge is not None:
            support, shape = self._edge_support(edge)
            if shape != "circle":
                raise KernelError("le centre demande une arête circulaire")
            return self._new_datum("PartDesign::Point", "DatumPoint",
                                   "Point de référence", support,
                                   "CenterOfCurvature")
        if point is None or len(point) != 3:
            raise KernelError("donnez un sommet, un cercle ou trois "
                              "coordonnées")
        return self._new_datum("PartDesign::Point", "DatumPoint",
                               "Point de référence", None, None, at=point)

    def add_datum_cs(self, point=None, vertex=None):
        """Repère : axes parallèles à ceux de l'origine, posé sur le
        sommet le plus proche de ``vertex`` ou aux coordonnées ``point``."""
        from engine.kernel import KernelError
        if vertex is not None:
            return self._new_datum("PartDesign::CoordinateSystem",
                                   "LocalCS", "Repère",
                                   self._vertex_support(vertex), "Translate")
        if point is None or len(point) != 3:
            raise KernelError("donnez un sommet ou trois coordonnées")
        return self._new_datum("PartDesign::CoordinateSystem", "LocalCS",
                               "Repère", None, None, at=point)
