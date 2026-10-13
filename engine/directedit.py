"""Édition directe : tirer la face du bout d'une extrusion ou d'un
enlèvement pour en changer la profondeur.

``face_drag_info`` dit si une face cliquée se tire, et comment : la
fonction et sa cote, le point et la normale de la poignée, et le facteur
entre le déplacement de la face et la cote (−1 pour le fond d'un
enlèvement, 2 pour une extrusion symétrique). Les imports FreeCAD restent
dans les méthodes ; ``drag_factor`` est testée en CI.
"""


def drag_factor(face_normal_dot_sketch, cap_offset, kind, midplane=False):
    """Facteur cote / déplacement le long de la normale extérieure de la
    face. ``face_normal_dot_sketch`` : produit scalaire normale de face ·
    normale de l'esquisse ; ``cap_offset`` : distance signée de la face au
    plan de l'esquisse. Une face qui s'éloigne de l'esquisse en suivant sa
    normale allonge la cote."""
    away = face_normal_dot_sketch * (1 if cap_offset >= 0 else -1) > 0
    factor = 1.0 if away else -1.0
    return factor * (2.0 if midplane else 1.0)


class DirectEditMixin:
    """Ops : sketch_frame, face_drag_info."""

    def sketch_frame(self, sketch):
        """Centre (milieu de l'encombrement) et normale d'une esquisse :
        où poser la poignée de profondeur d'une extrusion."""
        sk = self._get_sketch(sketch)
        App = self._app()
        normal = sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        shape = getattr(sk, "Shape", None)
        center = (shape.BoundBox.Center if shape is not None
                  and not shape.isNull() and shape.Edges
                  else sk.Placement.Base)
        return {"center": [center.x, center.y, center.z],
                "normal": [normal.x, normal.y, normal.z]}

    def face_drag_info(self, face):
        """Comment tirer la face ``face`` du corps actif, ou
        ``{"drag": None}`` si elle ne pilote aucune cote simple."""
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        index = int(face)
        if shape is None or not 0 <= index < len(shape.Faces):
            return {"drag": None}
        target = shape.Faces[index]
        name = self._face_producers().get(index)
        obj = self._doc.getObject(name) if name else None
        obj = self._thin_owner(obj) if obj is not None else None
        if (obj is None or obj.TypeId not in ("PartDesign::Pad",
                                              "PartDesign::Pocket")
                or str(getattr(obj, "Type", "")) != "Length"
                or "Length" in dict(obj.ExpressionEngine or [])
                or target.Surface.TypeId != "Part::GeomPlane"):
            return {"drag": None}
        profile = getattr(obj, "Profile", None)
        sketch = profile[0] if profile else None
        if sketch is None:
            return {"drag": None}
        App = self._app()
        axis = sketch.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        u0, u1, v0, v1 = target.ParameterRange
        normal = target.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        dot = normal.dot(axis)
        if abs(abs(dot) - 1) > 1e-6:
            return {"drag": None}
        center = target.CenterOfMass
        offset = (center - sketch.Placement.Base).dot(axis)
        length = float(obj.Length.Value)
        midplane = bool(getattr(obj, "Midplane", False))
        expected = length / 2 if midplane else length
        if abs(abs(offset) - expected) > 1e-6 * max(1.0, expected):
            return {"drag": None}  # pas la face du bout
        return {"drag": {
            "feature": obj.Name, "label": obj.Label, "prop": "Length",
            "value": length,
            "point": [center.x, center.y, center.z],
            "normal": [normal.x, normal.y, normal.z],
            "factor": drag_factor(dot, offset, obj.TypeId, midplane),
        }}
