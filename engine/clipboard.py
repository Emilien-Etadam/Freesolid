"""Copier-coller de fonctions : une fonction à esquisse (extrusion,
enlèvement, révolution, perçage, lissage, balayage…) ou une esquisse
seule, recopiée avec sa propre esquisse sur une autre face ou un autre
plan. Les autres esquisses d'un lissage ou d'un balayage (sections,
trajectoire) sont recopiées aussi et suivent le profil collé, à la même
place par rapport à lui. La copie est indépendante : changer l'une ne
change pas l'autre. Les imports FreeCAD restent dans les méthodes.
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
            sketch, _ = self._profile_of(source)  # à travers un liant
            if sketch is None or sketch.TypeId != "Sketcher::SketchObject":
                raise KernelError("seules une esquisse ou une fonction à "
                                  "esquisse se collent")
            solid = source
        # Sections et trajectoire : contrôlées avant tout changement.
        followers = self._paste_followers(source) if solid is not None \
            else []
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
                self._paste_follow(twin, copy, sketch, followers)
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

    def _paste_followers(self, source):
        """Les autres esquisses d'un lissage ou d'un balayage :
        ``[(propriété, esquisse, sous-éléments)]``, à travers le liant
        d'une esquisse d'un autre corps. Refusé : ce qui n'est pas une
        esquisse (une courbe 3D), un balayage guidé par une seconde
        trajectoire."""
        from engine.kernel import KernelError
        if source.TypeId not in self._MULTI_PROFILE_TYPES:
            return []

        def sketch_of(link, refusal):
            obj = self._as_object(link)
            subs = [s for s in (link[1] if isinstance(link, (list, tuple))
                                and len(link) > 1 else ()) if s]
            if getattr(obj, "FreeSolidProfileCopy", False):
                support = list(getattr(obj, "Support", None) or [])
                obj = support[0][0] if support else None
                subs = [s for s in (support[0][1] if support else ()) if s]
            if getattr(obj, "TypeId", "") != "Sketcher::SketchObject":
                raise KernelError(refusal)
            return obj, subs

        followers = []
        for link in list(getattr(source, "Sections", None) or ()):
            obj, subs = sketch_of(link, "une section n'est pas une "
                                  "esquisse : la fonction ne se colle pas")
            followers.append(("Sections", obj, subs))
        if source.TypeId in ("PartDesign::AdditivePipe",
                             "PartDesign::SubtractivePipe"):
            if str(getattr(source, "Mode", "")) == "Auxiliary":
                raise KernelError("un balayage guidé par une seconde "
                                  "trajectoire ne se colle pas encore")
            obj, subs = sketch_of(source.Spine, "un balayage le long d'une "
                                  "courbe 3D ne se colle pas encore")
            followers.append(("Spine", obj, subs))
        return followers

    def _paste_follow(self, twin, copy, profile, followers):
        """Recopie les sections et la trajectoire de ``twin`` : chacune
        s'attache au profil collé ``copy``, à la place qu'elle avait par
        rapport au profil ``profile`` de la source — la copie suit la
        face ou le plan où elle a été collée."""
        doc = self._require_doc()
        body = copy.getParentGeoFeatureGroup()
        frame = profile.getGlobalPlacement().inverse()
        sections = []
        for prop, sketch, subs in followers:
            dup = doc.copyObject(sketch, False)
            self._unrank(dup)
            body.addObject(dup)
            self._attach_to_support(dup, [(copy, ("",))])
            dup.MapMode = "ObjectXY"
            dup.AttachmentOffset = frame.multiply(sketch.getGlobalPlacement())
            if prop == "Sections":
                sections.append(dup)
            else:
                twin.Spine = (dup, subs or [""])
        if sections or getattr(twin, "Sections", None):
            self._set_link(twin, "Sections", sections)

