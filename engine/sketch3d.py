"""Esquisse 3D : un objet du document (Part::Feature) qui garde sa
définition (``sketch3dmath``) et dont la forme est faite de ses lignes et
splines — des fils, utilisables comme trajectoire de balayage, guide ou
bord de surface. Les points liés à la pièce la suivent : le solveur est
relancé quand elle change.

Les imports FreeCAD restent dans les méthodes.
"""

import json

from engine import sketch3dmath as sm3


class Sketch3dMixin:
    """Ops : add_sketch3d, edit_sketch3d."""

    _SK3D = "FreeSolidSketch3d"

    def _sketch3d_spec(self, obj):
        """Définition d'une esquisse 3D, ou None."""
        raw = getattr(obj, self._SK3D, None) if self._SK3D in getattr(
            obj, "PropertiesList", ()) else None
        if not raw:
            return None
        try:
            return sm3.clean_spec(json.loads(raw))
        except ValueError:
            return None

    def _sketch3d_solved(self, spec):
        """Liens résolus (points sur la pièce), cotes et relations tenues."""
        from engine.kernel import KernelError
        spec = sm3.clean_spec(spec)
        points, links = self._resolve_links(spec["points"], spec["links"])
        spec = dict(spec, points=points, links=links)
        out = sm3.solve(spec)
        if not out["ok"]:
            raise KernelError("esquisse 3D : des cotes ou des relations se "
                              "contredisent (écart {} mm)".format(
                                  round(out["residual"], 4)))
        return dict(spec, points=[[round(v, 9) + 0.0 for v in p]
                                  for p in out["points"]])

    def _sketch3d_shape(self, spec):
        """Fils des lignes et splines (hors construction), plus les points
        seuls ; un composé."""
        from engine.kernel import KernelError
        from engine.splineedit import build_bspline
        import FreeCAD as App
        import Part
        pts = spec["points"]
        edges = []
        for i in sm3.chains(spec):
            e = spec["entities"][i]
            if e["type"] == "line":
                a, b = App.Vector(*pts[e["a"]]), App.Vector(*pts[e["b"]])
                if (a - b).Length < 1e-7:
                    raise KernelError("esquisse 3D : une ligne a une "
                                      "longueur nulle")
                edges.append(Part.LineSegment(a, b).toShape())
            else:
                try:
                    curve = build_bspline([pts[p] for p in e["pts"]],
                                          e["closed"], e["tangents"])
                except ValueError as exc:
                    raise KernelError("esquisse 3D : " + str(exc))
                edges.append(curve.toShape())
        shapes = []
        if edges:
            try:
                groups = Part.sortEdges(edges)
            except Exception:  # noqa: BLE001
                groups = [[e] for e in edges]
            for group in groups:
                try:
                    shapes.append(Part.Wire(group))
                except Exception:  # noqa: BLE001
                    shapes.extend(group)
        for e in spec["entities"]:
            if e["type"] == "point":
                shapes.append(Part.Vertex(App.Vector(*pts[e["p"]])))
        if not shapes:
            raise KernelError("esquisse 3D vide : tracez au moins une "
                              "ligne, une spline ou un point")
        if len(shapes) == 1 and shapes[0].ShapeType == "Wire":
            return shapes[0]
        return Part.Compound(shapes)

    def _store_sketch3d(self, obj, spec):
        if self._SK3D not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", self._SK3D, "FreeSolid")
            obj.setEditorMode(self._SK3D, 2)
        setattr(obj, self._SK3D, json.dumps(spec))

    def add_sketch3d(self, spec):
        """Nouvelle esquisse 3D (voir ``sketch3dmath`` pour la définition)."""
        solved = self._sketch3d_solved(spec)
        shape = self._sketch3d_shape(solved)
        doc = self._require_doc()
        obj = doc.addObject("Part::Feature", "Esquisse3D")
        obj.Label = self._t("Esquisse 3D")
        self._store_sketch3d(obj, solved)
        obj.Shape = shape
        doc.recompute()
        return self.get_tree()

    def edit_sketch3d(self, sketch3d, spec):
        """Rééditer une esquisse 3D : les balayages et surfaces qui
        l'utilisent suivent."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(sketch3d))
        if obj is None or self._sketch3d_spec(obj) is None:
            raise KernelError("esquisse 3D inconnue : {}".format(sketch3d))
        solved = self._sketch3d_solved(spec)
        shape = self._sketch3d_shape(solved)
        self._store_sketch3d(obj, solved)
        obj.Shape = shape
        for dependent in obj.InList:
            dependent.touch()
        self._recompute()
        return self.get_tree()

    def _refresh_sketch3d(self, obj):
        """Points liés : la pièce a bougé, l'esquisse suit. Vrai si la
        forme a changé."""
        spec = self._sketch3d_spec(obj)
        if spec is None or not any(spec["links"]):
            return False
        try:
            solved = self._sketch3d_solved(spec)
            shape = self._sketch3d_shape(solved)
        except Exception:  # noqa: BLE001 — l'esquisse garde sa forme
            return False
        if all(abs(a - b) < 1e-9 for p, q in zip(solved["points"],
                                                 spec["points"])
               for a, b in zip(p, q)):
            return False
        self._store_sketch3d(obj, solved)
        obj.Shape = shape
        return True
