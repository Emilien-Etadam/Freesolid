"""Copier-coller de fonctions : une fonction à esquisse (extrusion,
enlèvement, révolution, perçage…) ou une esquisse seule, recopiée avec sa
propre esquisse sur une autre face ou un autre plan. La copie est
indépendante : changer l'une ne change pas l'autre. Les imports FreeCAD
restent dans les méthodes.
"""


class ClipboardMixin:
    """Op : paste_feature."""

    _MULTI_PROFILE_TYPES = frozenset({
        "PartDesign::AdditiveLoft", "PartDesign::SubtractiveLoft",
        "PartDesign::AdditivePipe", "PartDesign::SubtractivePipe",
    })

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
            if self._thin_spec(source) is not None:
                raise KernelError("une paroi mince ne se colle pas encore")
            if source.TypeId in self._MULTI_PROFILE_TYPES:
                # Ses sections ou sa trajectoire resteraient celles de la
                # source : la copie n'en serait pas une.
                raise KernelError("un lissage ou un balayage ne se colle "
                                  "pas encore")
            sketch, _ = self._profile_of(source)  # à travers un liant
            if sketch is None or sketch.TypeId != "Sketcher::SketchObject":
                raise KernelError("seules une esquisse ou une fonction à "
                                  "esquisse se collent")
            solid = source
        if face is None and plane is None and datum is None:
            raise KernelError("choisissez la face ou le plan où coller")
        try:
            copy = doc.copyObject(sketch, False)
            self._unrank(copy)
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
                self._unrank(twin)
                body.addObject(twin)
                twin.Profile = (copy, [""])
                axis = getattr(twin, "ReferenceAxis", None)
                token = getattr(axis[0], "FreeSolidSketchAxis", "") \
                    if axis is not None else ""
                if token:
                    # Révolution d'une esquisse d'un autre corps : l'axe
                    # de l'esquisse collée, qui est dans le corps.
                    twin.ReferenceAxis = (copy, [self._SKETCH_AXES[token]])
                elif axis is not None and self._is_thin_helper(axis[0]):
                    # L'esquisse collée est dans le corps : sa normale.
                    twin.ReferenceAxis = None
                elif axis is not None and axis[0] is sketch:
                    # Un axe de l'esquisse : celui de la copie.
                    twin.ReferenceAxis = (copy, list(axis[1]))
            self._recompute()
        except KernelError:
            raise  # la transaction de l'op défait la copie
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.get_tree()
