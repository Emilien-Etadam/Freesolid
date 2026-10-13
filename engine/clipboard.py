"""Copier-coller de fonctions : une fonction à esquisse (extrusion,
enlèvement, révolution, perçage…) ou une esquisse seule, recopiée avec sa
propre esquisse sur une autre face ou un autre plan. La copie est
indépendante : changer l'une ne change pas l'autre. Les imports FreeCAD
restent dans les méthodes.
"""


class ClipboardMixin:
    """Op : paste_feature."""

    def paste_feature(self, feature, face=None, plane=None, datum=None):
        """Colle une copie de ``feature`` sur la face ``face`` du solide,
        le plan d'origine ``plane`` ou le plan de référence ``datum`` —
        à la fin de l'historique."""
        from engine.kernel import KernelError, _explain
        doc = self._require_doc()
        body = self._require_body()
        source = doc.getObject(str(feature))
        if source is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if source.TypeId == "Sketcher::SketchObject":
            sketch, solid = source, None
        else:
            profile = getattr(source, "Profile", None)
            sketch = profile[0] if profile else None
            if sketch is None or sketch.TypeId != "Sketcher::SketchObject":
                raise KernelError("seules une esquisse ou une fonction à "
                                  "esquisse se collent")
            solid = source
        if face is None and plane is None and datum is None:
            raise KernelError("choisissez la face ou le plan où coller")
        try:
            copy = doc.copyObject(sketch, False)
            body.addObject(copy)
            if face is not None:
                self._attach_to_face(copy, face)
            elif datum is not None:
                target = doc.getObject(str(datum))
                if target is None or target.TypeId != "PartDesign::Plane":
                    raise KernelError(
                        "plan de référence inconnu : {}".format(datum))
                self._attach_to_support(copy, [(target, ("",))])
            else:
                role = self._PLANE_ROLES.get(str(plane).upper())
                if role is None:
                    raise KernelError("plan inconnu « {} » — attendu XY, XZ "
                                      "ou YZ".format(plane))
                self._attach_to_support(
                    copy, [(self._origin_feature(role), ("",))])
            if solid is not None:
                twin = doc.copyObject(solid, False)
                body.addObject(twin)
                twin.Profile = (copy, [""])
            self._recompute()
        except KernelError:
            raise  # la transaction de l'op défait la copie
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.get_tree()
