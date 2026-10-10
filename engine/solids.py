"""Fonctions volumiques : corps, extrusions, révolutions, habillages.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class SolidsMixin:
    # -- fonctions volumiques ---------------------------------------------

    _THIN_HELPER = "FreeSolidThinHelper"
    _SKETCH_AXES = {"vertical": "V_Axis", "horizontal": "H_Axis"}
    _AXIS_ROLES = {"X": "X_Axis", "Y": "Y_Axis", "Z": "Z_Axis"}
    _CHAMFER_TYPES = {
        "egale": "Equal distance",
        "deux": "Two distances",
        "angle": "Distance and Angle",
    }
    #: Correspondance panneau -> énumération FreeCAD du type de lamage.
    _HOLE_CUTS = {"none": "None", "lamage": "Counterbore",
                  "fraisage": "Countersink"}

    def add_body(self, name=None):
        """Nouveau corps dans la pièce — il devient le corps actif.

        Un corps regroupe ses fonctions, matérialisé ici par un Body.
        Les fonctions suivantes s'empilent dans ce corps.
        """
        doc = self._require_doc()
        body = doc.addObject("PartDesign::Body", "Body")
        body.Label = str(name).strip() if name else self._t("Corps")
        self._body = body
        doc.recompute()
        return self.get_tree()

    def set_active_body(self, body):
        """Changer de corps actif — les fonctions s'appliquent à lui."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(str(body))
        if obj is None or obj.TypeId != "PartDesign::Body":
            raise KernelError("corps inconnu : {}".format(body))
        self._body = obj
        return self.get_tree()

    def set_body_color(self, body, color):
        """Couleur d'affichage d'un corps, persistée dans le .FCStd.

        Headless : pas de ViewObject. Propriété custom ``FreeSolidColor``.
        ``color`` = ``#rrggbb``, ou ``None`` / ``""`` pour le défaut.
        """
        from engine.kernel import (
            KernelError,
            parse_body_color,
        )
        doc = self._require_doc()
        obj = doc.getObject(str(body))
        if obj is None or obj.TypeId != "PartDesign::Body":
            raise KernelError("corps inconnu : {}".format(body))
        value = parse_body_color(color)
        if "FreeSolidColor" not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", "FreeSolidColor",
                            "FreeSolid", "Couleur d'affichage")
        obj.FreeSolidColor = value
        return self.get_tree()

    def add_boolean(self, tool, type="cut"):
        """Combiner deux corps — Soustraire / Ajouter / Intersection.

        S'applique au corps actif. Un ``PartDesign::Body`` outil est
        absorbé (comportement PartDesign). Un semis de pierres n'est
        pas absorbé : le corps outil est dérivé, le compound se relit
        depuis ``PlacementList`` à chaque recompute.
        """
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        tool_obj = doc.getObject(str(tool))
        derived_names = []
        hooked = self._plugins.run_boolean_tool(self, tool_obj)
        if hooked is not None:
            tool_obj = hooked
            derived_names.append(tool_obj.Name)
            base = getattr(tool_obj, "BaseFeature", None)
            if base is not None:
                derived_names.append(base.Name)
        elif tool_obj is None or tool_obj.TypeId != "PartDesign::Body":
            raise KernelError("corps outil inconnu : {}".format(tool))
        if tool_obj is body:
            raise KernelError(
                "un corps ne se combine pas avec lui-même — choisissez "
                "un autre corps outil")
        types = {"cut": "Cut", "fuse": "Fuse", "common": "Common"}
        labels = {"cut": self._t("Combiner — Soustraire"),
                  "fuse": self._t("Combiner — Ajouter"),
                  "common": self._t("Combiner — Intersection")}
        boolean_type = types.get(str(type))
        if boolean_type is None:
            raise KernelError(
                "opération inconnue « {} » — attendu cut, fuse ou "
                "common".format(type))
        feature = body.newObject("PartDesign::Boolean", "Boolean")
        feature.Type = boolean_type
        # L'API d'ajout du corps outil a changé selon les versions.
        try:
            feature.addObjects([tool_obj])
        except AttributeError:
            try:
                feature.addObject(tool_obj)
            except AttributeError:
                feature.Group = [tool_obj]
        feature.Label = labels[str(type)]
        boolean_phases = {
            "cut": "Soustraire",
            "fuse": "Ajouter",
            "common": "Intersection",
        }
        self._report_progress(boolean_phases[str(type)])
        try:
            self._recompute()
        except KernelError:
            try:
                doc.removeObject(feature.Name)
            except Exception:
                pass
            for name in derived_names:
                try:
                    doc.removeObject(name)
                except Exception:
                    pass
            raise
        return self.get_tree()

    def add_pad(self, length=None, sketch=None, reversed=False,
                midplane=False, thin=None, **conditions):
        """Extrusion. ``conditions`` : voir ``engine.extrude`` —
        cond, face, offset, taper, cond2, length2, face2, offset2, taper2.
        ``thin`` : paroi mince, voir ``engine.extrude.thin_settings``."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            profile = self._latest_sketch()
        tip = body.Tip  # les faces visées appartiennent à l'état d'avant
        spec, helpers = self._thin_profile(body, profile, thin)
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = helpers[-1] if helpers else profile
        try:
            self._apply_extrude(pad, "pad", tip, length=length,
                                reversed=reversed, midplane=midplane,
                                **conditions)
            pad.Label = self._t("Extrusion")
            if spec is not None:
                self._mark_thin(pad, spec)
                self._own_thin_helpers(pad, helpers)
                if spec["caps"]:
                    helpers += self._thin_cavity(body, pad, profile, spec)
            self._recompute()
        except KernelError:
            self._remove_all([pad] + helpers)
            raise
        return self.get_tree()

    #: Objets d'une paroi mince : hors arbre, ils suivent leur fonction
    #: (``FreeSolidThinOwner`` = son nom ; une chaîne, pas un lien — un lien
    #: de la fonction vers sa cavité, placée après elle, ferait un cycle).

    def _is_thin_helper(self, obj):
        return bool(getattr(obj, self._THIN_HELPER, False))

    def _new_thin_helper(self, body, type_id, name, label):
        obj = body.newObject(type_id, name)
        obj.addProperty("App::PropertyBool", self._THIN_HELPER,
                        "FreeSolid", "Objet de paroi mince")
        setattr(obj, self._THIN_HELPER, True)
        obj.Label = self._t(label)
        return obj

    def _new_thin_binder(self, body, source, offset, fill, label):
        binder = self._new_thin_helper(
            body, "PartDesign::SubShapeBinder", "ThinProfile", label)
        try:
            binder.Support = [(source, ("",))]
        except TypeError:
            binder.Support = (source, [""])
        binder.OffsetJoinType = "Intersection"  # coins vifs
        binder.OffsetOpenResult = True  # profil ouvert : un côté
        binder.OffsetFill = fill
        binder.Offset = offset
        binder.Visibility = False
        return binder

    def _own_thin_helpers(self, feature, helpers):
        for helper in helpers:
            if "FreeSolidThinOwner" not in helper.PropertiesList:
                helper.addProperty("App::PropertyString",
                                   "FreeSolidThinOwner", "FreeSolid",
                                   "Fonction de cette paroi mince")
            helper.FreeSolidThinOwner = feature.Name

    def _thin_profile(self, body, profile, thin):
        """Paroi mince : le profil devient une bande d'épaisseur constante.

        Un ou deux ``SubShapeBinder`` décalés (objets natifs, recalculés
        quand l'esquisse change) tiennent la bande dans le corps ; la
        fonction l'extrude comme n'importe quel profil, avec toutes ses
        conditions de fin. Extrémités fermées : le profil est le contour
        extérieur plein, la cavité vient après (``_thin_cavity``).
        Renvoie ``(spec, liants)`` — ``(None, [])`` sans paroi mince.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        if not thin:
            return None, []
        from engine.extrude import (
            ExtrudeError, thin_cap_offsets, thin_offsets, thin_settings)
        if not isinstance(thin, dict):
            raise KernelError("paroi mince : objet attendu")
        try:
            spec = thin_settings(**thin)
        except (ExtrudeError, TypeError, ValueError) as exc:
            raise KernelError(str(exc))
        if spec["caps"]:
            profile.recompute()   # une esquisse tout juste tracée
            wires = getattr(profile.Shape, "Wires", None) or []
            if not wires or not all(w.isClosed() for w in wires):
                raise KernelError(
                    "extrémités fermées : le profil doit être fermé")
            steps = [(thin_cap_offsets(spec)[0], False)]
        else:
            steps = thin_offsets(spec)
        doc = self._require_doc()
        helpers = []
        source = profile
        try:
            for offset, fill in steps:
                source = self._new_thin_binder(
                    body, source, offset, fill, "Profil de paroi mince")
                helpers.append(source)
            doc.recompute()
        except Exception as exc:  # noqa: BLE001
            self._remove_all(helpers)
            raise KernelError(_explain(exc))
        return spec, helpers

    def _thin_cavity(self, body, feature, profile, spec):
        """Extrémités fermées : la cavité, un enlèvement caché entre les
        deux bouts, dont les profondeurs suivent la fonction."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        from engine.extrude import ExtrudeError, cavity_plan, thin_cap_offsets
        side = str(getattr(feature, "SideType", "One side"))
        borgne = (feature.Type == "Length"
                  and (side != "Two sides" or feature.Type2 == "Length"))
        tapered = any(abs(float(getattr(feature, prop, 0) or 0)) > 1e-9
                      for prop in ("TaperAngle", "TaperAngle2"))
        if not borgne or tapered:
            raise KernelError(
                "extrémités fermées : profondeur borgne, sans dépouille")
        try:
            self._check_cavity(feature)
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        helpers = []
        try:
            binder = self._new_thin_binder(
                body, profile, thin_cap_offsets(spec)[1], False,
                "Profil de paroi mince")
            helpers.append(binder)
            cavity = self._new_thin_helper(
                body, "PartDesign::Pocket", "ThinCavity",
                "Cavité de paroi mince")
            helpers.append(cavity)
            self._own_thin_helpers(feature, helpers)
            cavity.Profile = binder
            plan = cavity_plan(side, feature.Name)
            cavity.SideType = plan.pop("SideType")
            # L'enlèvement part à l'opposé de l'extrusion.
            cavity.Reversed = not feature.Reversed
            for prop, expr in plan.items():
                cavity.setExpression(prop, expr)
        except Exception as exc:  # noqa: BLE001
            self._remove_all(helpers)
            raise KernelError(_explain(exc))
        return helpers

    def _check_cavity(self, feature):
        from engine.extrude import check_cavity
        def mm(prop):
            value = getattr(feature, prop, 0.0)
            return float(getattr(value, "Value", value))
        check_cavity(str(getattr(feature, "SideType", "One side")),
                     mm("Length"), mm("Length2"), mm("CapThickness"))

    def _mark_thin(self, feature, spec):
        """Épaisseurs sur la fonction : rééditables par ``set_params``."""
        props = [("FreeSolidThinType", "App::PropertyString"),
                 ("FreeSolidThinReversed", "App::PropertyBool"),
                 ("Thickness", "App::PropertyLength")]
        if spec["type"] == "deux":
            props.append(("Thickness2", "App::PropertyLength"))
        if spec["caps"]:
            props.append(("CapThickness", "App::PropertyLength"))
        for prop, prop_type in props:
            if prop not in feature.PropertiesList:
                feature.addProperty(prop_type, prop, "FreeSolid",
                                    "Paroi mince")
        feature.FreeSolidThinType = spec["type"]
        feature.FreeSolidThinReversed = spec["reversed"]
        feature.Thickness = spec["thickness"]
        if spec["type"] == "deux":
            feature.Thickness2 = spec["thickness2"]
        if spec["caps"]:
            feature.CapThickness = spec["caps"]

    def _thin_spec(self, obj):
        """Paroi mince d'une fonction (dict de ``thin_settings``) ou None."""
        kind = getattr(obj, "FreeSolidThinType", "")
        if not kind:
            return None
        def mm(prop):
            value = getattr(obj, prop, 0.0)
            return float(getattr(value, "Value", value))
        return {"type": kind, "thickness": mm("Thickness"),
                "thickness2": mm("Thickness2") if kind == "deux" else 0.0,
                "reversed": bool(getattr(obj, "FreeSolidThinReversed",
                                         False)),
                "caps": mm("CapThickness")}

    def _thin_chain(self, obj):
        """Liants de paroi mince d'une fonction (du premier au dernier) et
        l'esquisse source : ``([], None)`` pour une fonction pleine."""
        profile = getattr(obj, "Profile", None)
        linked = profile[0] if isinstance(profile, tuple) else profile
        chain = []
        while linked is not None and self._is_thin_helper(linked):
            chain.insert(0, linked)
            support = getattr(linked, "Support", None) or []
            linked = support[0][0] if support else None
        return chain, (linked if chain else None)

    def _thin_helpers(self, obj):
        """Tous les objets cachés d'une paroi mince, dans l'ordre du corps."""
        chain, _ = self._thin_chain(obj)
        group = getattr(obj.getParentGeoFeatureGroup(), "Group", None) or []
        return [o for o in group
                if o in chain or getattr(o, "FreeSolidThinOwner", "") == obj.Name]

    def _thin_owner(self, obj):
        """La fonction d'un objet caché de paroi mince, sinon l'objet."""
        owner = getattr(obj, "FreeSolidThinOwner", "") if obj else ""
        found = self._doc.getObject(owner) if owner else None
        return found or obj

    def _tip_with_helpers(self, obj):
        """Barre de retour sur une fonction : après sa cavité éventuelle."""
        features = [h for h in self._thin_helpers(obj)
                    if h.isDerivedFrom("PartDesign::Feature")]
        return features[-1] if features else obj

    def _sync_thin(self, obj):
        """Recopie les épaisseurs de la fonction dans ses liants."""
        from engine.kernel import KernelError
        from engine.extrude import (
            ExtrudeError, thin_cap_offsets, thin_offsets, thin_settings)
        spec = self._thin_spec(obj)
        chain, _ = self._thin_chain(obj)
        if spec is None or not chain:
            return
        try:
            spec = thin_settings(**spec)
            if spec["caps"]:
                self._check_cavity(obj)
                outer, inner = thin_cap_offsets(spec)
                binders = [h for h in self._thin_helpers(obj)
                           if h.TypeId == "PartDesign::SubShapeBinder"]
                steps = [(outer, False), (inner, False)]
                chain = binders
            else:
                steps = thin_offsets(spec)
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        if len(steps) != len(chain):
            raise KernelError("paroi mince incomplète : profil décalé absent")
        for binder, (offset, fill) in zip(chain, steps):
            binder.OffsetFill = fill
            binder.Offset = offset

    def _remove_all(self, objects):
        doc = self._require_doc()
        for obj in reversed(objects):
            try:
                doc.removeObject(obj.Name)
            except Exception:
                pass

    def _apply_extrude(self, obj, kind, tip, **params):
        """Pose les propriétés calculées par ``engine.extrude``."""
        from engine.kernel import KernelError
        from engine.extrude import ExtrudeError, extrude_settings
        try:
            props = extrude_settings(kind, **params)
        except (ExtrudeError, TypeError, ValueError) as exc:
            raise KernelError(str(exc))
        side = props.pop("SideType")
        if "SideType" in obj.PropertiesList:
            obj.SideType = side
        elif side == "Symmetric":
            obj.Midplane = True          # FreeCAD 1.0 : pas de SideType
        elif side == "Two sides":
            raise KernelError(
                "deuxième direction : FreeCAD {} requis".format("1.1"))
        for name, value in props.items():
            if name.startswith("UpToFace"):
                if tip is None:
                    raise KernelError(
                        "jusqu'à la face : la pièce n'a pas encore de face")
                value = (tip, ["Face{}".format(int(value) + 1)])
            setattr(obj, name, value)

    def add_pocket(self, length=None, through=False, reversed=False,
                   sketch=None, midplane=False, cond=None, thin=None,
                   **conditions):
        """Cut with the latest sketch — an extruded cut.

        No length (or ``through``) means « À travers tout » — the option
        chosen by default on a cut. ``cond`` and the
        other conditions: see ``engine.extrude``.
        """
        from engine.kernel import KernelError
        body = self._require_body()
        tip = body.Tip
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        if isinstance(thin, dict) and thin.get("caps"):
            raise KernelError(
                "extrémités fermées : réservées à l'extrusion")
        spec, helpers = self._thin_profile(body, profile, thin)
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = helpers[-1] if helpers else profile
        if cond is None:
            cond = "travers" if (through or length is None) else "borgne"
        try:
            self._apply_extrude(pocket, "pocket", tip, cond=cond,
                                length=length, reversed=reversed,
                                midplane=midplane, **conditions)
        except KernelError:
            self._remove_all([pocket] + helpers)
            raise
        pocket.Label = self._t("Enlèvement extrudé")
        if spec is not None:
            self._mark_thin(pocket, spec)
            self._own_thin_helpers(pocket, helpers)
        try:
            self._recompute()
        except KernelError:
            self._remove_all([pocket] + helpers)
            raise
        return self.get_tree()

    #: Ops the yellow ghost preview may run speculatively.

    def add_datum_plane(self, base=None, face=None, offset=0.0, angle=0.0):
        """Plan de référence : décalé (et incliné) d'un plan d'origine ou
        d'une face — le prérequis des pièces qui ne s'empilent pas sur
        les trois plans."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        App = self._app()
        plane = body.newObject("PartDesign::Plane", "DatumPlane")
        if face is not None:
            tip = getattr(body, "Tip", None)
            if tip is None:
                raise KernelError("pas de solide pour porter ce plan")
            support = [(tip, ("Face{}".format(int(face) + 1),))]
        else:
            role = self._PLANE_ROLES.get(str(base or "XY").upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(base))
            support = [(self._origin_feature(role), ("",))]
        try:
            plane.AttachmentSupport = support
        except AttributeError:
            plane.Support = support
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(
            App.Vector(0, 0, float(offset)),
            App.Rotation(App.Vector(1, 0, 0), float(angle)))
        plane.Label = self._t("Plan de référence")
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(plane.Name)
            raise
        return self.get_tree()

    def add_loft(self, sketches, subtractive=False, ruled=False,
                 closed=False):
        """Lissage (ou enlèvement) entre plusieurs profils —
        typiquement des esquisses posées sur des plans de référence."""
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        body = self._require_body()
        doc = self._require_doc()
        if not isinstance(sketches, (list, tuple)) or len(sketches) < 2:
            raise KernelError("un lissage demande au moins deux profils")
        profiles = [self._get_sketch(str(n)) for n in sketches]
        type_id = ("PartDesign::SubtractiveLoft" if subtractive
                   else "PartDesign::AdditiveLoft")
        loft = body.newObject(type_id, type_id.split("::")[-1])
        loft.Profile = profiles[0]
        try:
            loft.Sections = profiles[1:]
        except TypeError:
            loft.Sections = [(p, ("",)) for p in profiles[1:]]
        loft.Ruled = bool(ruled)
        loft.Closed = bool(closed)
        loft.Label = label_for_type(type_id, self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(loft.Name)
            raise
        return self.get_tree()

    def add_sweep(self, profile, spine, subtractive=False):
        """Balayage (ou enlèvement) : un profil suit une
        trajectoire — deux esquisses, souvent sur des plans différents."""
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        body = self._require_body()
        doc = self._require_doc()
        section = self._get_sketch(str(profile))
        # La trajectoire : une esquisse OU une courbe 3D (Part::Feature).
        path = doc.getObject(str(spine))
        if (path is None
                or path.TypeId not in ("Sketcher::SketchObject",
                                       "Part::Feature")
                or not getattr(path, "Shape", None)
                or not path.Shape.Edges):
            raise KernelError(
                "trajectoire inconnue : {} (esquisse ou courbe 3D)".format(
                    spine))
        if section.Name == path.Name:
            raise KernelError("profil et trajectoire doivent être "
                              "différents")
        binder = None
        if path.TypeId == "Part::Feature":
            # PartDesign n'accepte que des liens internes au corps
            # (« out of the allowed scope » sinon) : un SubShapeBinder
            # importe la courbe 3D dans le corps.
            binder = body.newObject("PartDesign::SubShapeBinder",
                                    "SpineBinder")
            try:
                binder.Support = [(path, ("",))]
            except TypeError:
                binder.Support = (path, [""])
            binder.Label = self._t("Trajectoire — {}").format(path.Label)
            doc.recompute()
            path = binder
        type_id = ("PartDesign::SubtractivePipe" if subtractive
                   else "PartDesign::AdditivePipe")
        pipe = body.newObject(type_id, type_id.split("::")[-1])
        pipe.Profile = section
        try:
            pipe.Spine = path
        except TypeError:
            pipe.Spine = (path, ("",))
        pipe.Label = label_for_type(type_id, self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pipe.Name)
            if binder is not None:
                try:
                    doc.removeObject(binder.Name)
                except Exception:
                    pass
            raise
        return self.get_tree()

    def add_helix(self, pitch, height, sketch=None):
        """Hélice additive (ressort, filet réel) — le profil tourne autour
        de l'axe vertical de son esquisse, comme la révolution."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        if float(pitch) <= 0 or float(height) <= 0:
            raise KernelError("pas et hauteur doivent être positifs")
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        helix = body.newObject("PartDesign::AdditiveHelix", "AdditiveHelix")
        helix.Profile = profile
        helix.ReferenceAxis = (profile, ["V_Axis"])
        helix.Pitch = float(pitch)
        helix.Height = float(height)
        helix.Label = self._t("Hélice")
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(helix.Name)
            raise
        return self.get_tree()

    def _revolution_reference(self, profile, axis):
        """Référence d'axe : axe d'esquisse, ligne, ou axe d'origine."""
        from engine.kernel import KernelError
        token = str(axis or "vertical").strip() or "vertical"
        if token in self._SKETCH_AXES:
            return (profile, [self._SKETCH_AXES[token]])
        if token.upper() in self._AXIS_ROLES:
            return (self._origin_axis(token), [""])
        if token.startswith("line:"):
            try:
                gid = int(token.split(":", 1)[1])
            except ValueError:
                gid = -1
            geometry = list(getattr(profile, "Geometry", []) or [])
            if gid < 0 or gid >= len(geometry):
                raise KernelError("l'axe de révolution doit être une ligne")
            geo = geometry[gid]
            if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
                raise KernelError("l'axe de révolution doit être une ligne")
            # La géométrie de construction n'est pas dans la forme de
            # l'esquisse : une ligne de référence, cachée, la porte.
            if self._is_construction(profile, gid, geo):
                return (self._axis_datum(profile, gid), [""])
            edge = 0
            for index, item in enumerate(geometry):
                if self._is_construction(profile, index, item):
                    continue
                edge += 1
                if index == gid:
                    return (profile, ["Edge{}".format(edge)])
            raise KernelError("l'axe de révolution doit être une ligne")
        raise KernelError(
            "axe de révolution inconnu « {} »".format(token))

    def _axis_datum(self, profile, gid):
        """Ligne de référence cachée, calée sur une ligne de construction."""
        body = self._require_body()
        for obj in body.Group:
            if not getattr(obj, "FreeSolidAxisTool", False):
                continue
            if (getattr(obj, "AxisSketch", None) == profile
                    and int(getattr(obj, "AxisGeo", -1)) == int(gid)):
                self._place_axis_datum(obj, profile, gid)
                return obj
        tip = getattr(body, "Tip", None)
        datum = body.newObject("PartDesign::Line", "AxisLine")
        if "FreeSolidAxisTool" not in datum.PropertiesList:
            datum.addProperty("App::PropertyBool", "FreeSolidAxisTool",
                              "FreeSolid", "Axe interne d'une révolution")
            datum.addProperty("App::PropertyLink", "AxisSketch",
                              "FreeSolid", "Esquisse portée")
            datum.addProperty("App::PropertyInteger", "AxisGeo",
                              "FreeSolid", "Géométrie d'axe")
        datum.FreeSolidAxisTool = True
        datum.AxisSketch = profile
        datum.AxisGeo = int(gid)
        datum.MapMode = "Deactivated"
        try:
            datum.Visibility = False
        except Exception:
            pass
        self._place_axis_datum(datum, profile, gid)
        if tip is not None and getattr(body, "Tip", None) is not tip:
            body.Tip = tip
        return datum

    def _place_axis_datum(self, datum, profile, gid):
        from engine.kernel import KernelError
        geometry = list(getattr(profile, "Geometry", []) or [])
        if gid < 0 or gid >= len(geometry):
            raise KernelError("l'axe de révolution doit être une ligne")
        geo = geometry[gid]
        if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
            raise KernelError("l'axe de révolution doit être une ligne")
        p1 = profile.Placement.multVec(geo.StartPoint)
        p2 = profile.Placement.multVec(geo.EndPoint)
        direction = p2.sub(p1)
        if float(direction.Length) < 1e-9:
            raise KernelError("l'axe de révolution doit être une ligne")
        app = self._app()
        datum.MapMode = "Deactivated"
        datum.Placement = app.Placement(
            p1, app.Rotation(app.Vector(0, 0, 1), direction))

    def _sync_revolution_axes(self):
        """Recale les axes internes avant le recalcul du solide."""
        doc = getattr(self, "_doc", None)
        if doc is None:
            return
        for obj in list(doc.Objects):
            if not getattr(obj, "FreeSolidAxisTool", False):
                continue
            sketch = getattr(obj, "AxisSketch", None)
            if sketch is None:
                continue
            self._place_axis_datum(obj, sketch, int(getattr(obj, "AxisGeo", -1)))

    def _drop_unused_axis_tools(self):
        doc = self._require_doc()
        used = set()
        for obj in doc.Objects:
            ref = getattr(obj, "ReferenceAxis", None)
            try:
                target = ref[0]
            except Exception:
                continue
            if getattr(target, "FreeSolidAxisTool", False):
                used.add(target.Name)
        for obj in list(doc.Objects):
            if getattr(obj, "FreeSolidAxisTool", False) and obj.Name not in used:
                try:
                    doc.removeObject(obj.Name)
                except Exception:
                    pass

    @staticmethod
    def _as_object(link):
        """Lien simple ou sous-lien ``(objet, [sous])`` → l'objet."""
        if isinstance(link, (list, tuple)) and link:
            return link[0]
        return link

    def _revolution_axis_token(self, obj):
        """Jeton d'axe relu sur la fonction (vertical par défaut)."""
        profile = self._as_object(getattr(obj, "Profile", None))
        ref = getattr(obj, "ReferenceAxis", None)
        try:
            target, subs = ref[0], ref[1]
        except Exception:
            return "vertical"
        sub = ""
        try:
            sub = str(list(subs)[0]) if subs else ""
        except Exception:
            sub = ""
        profile_name = getattr(profile, "Name", "") or ""
        target_name = getattr(target, "Name", "") or ""
        if getattr(target, "FreeSolidAxisTool", False):
            return "line:{}".format(int(getattr(target, "AxisGeo", -1)))
        if target_name and target_name == profile_name:
            if sub == "H_Axis":
                return "horizontal"
            if sub.startswith("Edge"):
                try:
                    wanted = int(sub[4:])
                except ValueError:
                    return "vertical"
                edge = 0
                for index, geo in enumerate(getattr(profile, "Geometry", []) or []):
                    if self._is_construction(profile, index, geo):
                        continue
                    edge += 1
                    if edge == wanted:
                        return "line:{}".format(index)
                return "vertical"
            return "vertical"
        for token, role in self._AXIS_ROLES.items():
            if target_name == role or target_name.startswith(role):
                return token
        return "vertical"

    def _revolution_state(self, obj):
        profile = self._as_object(getattr(obj, "Profile", None))
        return {
            "axis": self._revolution_axis_token(obj),
            "angle": self._prop_float(obj, "Angle"),
            "reversed": bool(getattr(obj, "Reversed", False)),
            "midplane": bool(getattr(obj, "Midplane", False)),
            "profile": getattr(profile, "Name", "") or "",
        }

    def _sketch_line_axes(self, sk):
        """Lignes de l'esquisse proposées comme axe de révolution."""
        lines = []
        try:
            geometry = list(sk.Geometry)
        except Exception:
            return lines
        for gid, geo in enumerate(geometry):
            if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
                continue
            lines.append({
                "id": int(gid),
                "construction": bool(self._is_construction(sk, gid, geo)),
                "x1": round(float(geo.StartPoint.x), 2),
                "y1": round(float(geo.StartPoint.y), 2),
                "x2": round(float(geo.EndPoint.x), 2),
                "y2": round(float(geo.EndPoint.y), 2),
            })
        return lines

    def _revolved(self, type_id, angle, sketch, axis=None,
                  reversed=False, midplane=False):
        """Révolution ou gorge : même axe, ajout ou enlèvement.

        Sans axe, l'axe vertical de l'esquisse — le profil se dessine à
        côté. ``axis`` peut être ``horizontal``, ``line:<id>`` (une ligne
        de l'esquisse, de construction de préférence) ou ``X``, ``Y``, ``Z``.
        """
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        body = self._require_body()
        doc = self._require_doc()
        try:
            degrees = float(angle)
        except (TypeError, ValueError):
            raise KernelError("angle de révolution invalide")
        if not (degrees > 0 and degrees <= 360):
            raise KernelError("angle de révolution invalide")
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        reference = self._revolution_reference(profile, axis)
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Profile = profile
        feature.ReferenceAxis = reference
        feature.Angle = degrees
        if reversed:
            feature.Reversed = True
        if midplane:
            feature.Midplane = True
        feature.Label = label_for_type(type_id, self.lang)
        self._drop_unused_axis_tools()
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            self._drop_unused_axis_tools()
            raise
        return self.get_tree()

    def add_revolution(self, angle=360.0, sketch=None, axis=None,
                       reversed=False, midplane=False):
        """Révolution."""
        return self._revolved(
            "PartDesign::Revolution", angle, sketch, axis=axis,
            reversed=reversed, midplane=midplane)

    def add_groove(self, angle=360.0, sketch=None, axis=None,
                   reversed=False, midplane=False):
        """Enlèvement par révolution."""
        return self._revolved(
            "PartDesign::Groove", angle, sketch, axis=axis,
            reversed=reversed, midplane=midplane)

    def _last_solid_feature(self):
        """The feature a pattern/mirror duplicates: the latest add/sub one.

        Dress-ups and other transforms don't qualify — PartDesign patterns
        transform additive/subtractive features.
        """
        from engine.kernel import KernelError
        body = self._require_body()
        features = [o for o in body.Group
                    if o.isDerivedFrom("PartDesign::FeatureAddSub")]
        if not features:
            raise KernelError("aucune fonction à répéter — créez d'abord "
                              "un bossage ou un enlèvement de matière")
        return features[-1]

    def _pattern_catalog(self):
        """Catalogue {nom: {in_body, is_addsub, label}} du document."""
        body = self._require_body()
        doc = self._require_doc()
        in_body = {o.Name for o in body.Group}
        catalog = {}
        for obj in doc.Objects:
            is_addsub = False
            try:
                is_addsub = bool(
                    obj.isDerivedFrom("PartDesign::FeatureAddSub"))
            except Exception:
                is_addsub = False
            catalog[obj.Name] = {
                "in_body": obj.Name in in_body,
                "is_addsub": is_addsub,
                "label": obj.Label,
            }
        return catalog

    def _pattern_originals(self, features):
        """Fonctions à répéter : ``features`` ou la dernière additive."""
        from engine.kernel import resolve_pattern_originals
        if features is None:
            return [self._last_solid_feature()]
        names = resolve_pattern_originals(features, self._pattern_catalog())
        doc = self._require_doc()
        return [doc.getObject(name) for name in names]

    def _transform(self, type_id, configure, features=None):
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        body = self._require_body()
        doc = self._require_doc()
        originals = self._pattern_originals(features)
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Originals = originals
        configure(feature)
        feature.Label = label_for_type(type_id, self.lang)
        # FreeCAD 1.0 laisse le Tip sur l'original après newObject d'un
        # Transformed : la répétition existe alors sans devenir le solide
        # du corps (volume inchangé). Un Body n'a qu'un solide — les copies
        # disjointes sont jetées ; on pose le Tip pour que la fusion compte.
        body.Tip = feature
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_mirror(self, plane="YZ", features=None):
        """Symétrie d'une ou plusieurs fonctions par rapport à un plan
        d'origine (XY/XZ/YZ = Dessus/Face/Droite).

        ``features`` : noms des fonctions à symétriser. Absent : la
        dernière fonction additive ou soustractive du corps actif.
        """
        from engine.kernel import KernelError
        role = self._PLANE_ROLES.get(str(plane).upper())
        if role is None:
            raise KernelError(
                "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
        plane_obj = self._origin_feature(role)

        def configure(feature):
            feature.MirrorPlane = (plane_obj, [""])
        return self._transform("PartDesign::Mirrored", configure,
                               features=features)

    def _origin_axis(self, axis):
        from engine.kernel import KernelError
        role = self._AXIS_ROLES.get(str(axis).upper())
        if role is None:
            raise KernelError(
                "axe inconnu « {} » — attendu X, Y ou Z".format(axis))
        return self._origin_feature(role)

    def _pattern_direction(self, axis, edge):
        """Direction d'une répétition : arête droite de la pièce (numéro
        d'arête 0-based), sinon axe d'origine."""
        from engine.kernel import KernelError
        if edge is not None:
            tip = self._require_body().Tip
            if tip is None:
                raise KernelError("aucune arête : la pièce est vide")
            return (tip, ["Edge{}".format(int(edge) + 1)])
        return (self._origin_axis(axis), [""])

    def add_linear_pattern(self, length, count, axis="X", features=None,
                           edge=None, spacing=False, reversed=False):
        """Réseau linéaire d'une ou plusieurs fonctions le long d'un axe
        ou d'une arête droite.

        ``length`` : longueur totale (par défaut) ou, avec ``spacing``,
        pas entre deux occurrences. ``features`` : noms des fonctions à
        répéter. Absent : la dernière fonction additive ou soustractive.
        """
        from engine.kernel import KernelError
        direction = self._pattern_direction(axis, edge)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Direction = direction
            if spacing and "Mode" in feature.PropertiesList:
                feature.Mode = "Spacing"
                feature.Offset = float(length)
            elif spacing:
                feature.Length = float(length) * (occurrences - 1)
            else:
                feature.Length = float(length)
            feature.Occurrences = occurrences
            if reversed:
                feature.Reversed = True
        return self._transform("PartDesign::LinearPattern", configure,
                               features=features)

    def add_polar_pattern(self, count, angle=360.0, axis="Z", features=None,
                          edge=None, reversed=False):
        """Réseau circulaire d'une ou plusieurs fonctions autour d'un
        axe d'origine ou d'une arête droite.

        ``features`` : noms des fonctions à répéter. Absent : la dernière
        fonction additive ou soustractive du corps actif.
        """
        from engine.kernel import KernelError
        axis_ref = self._pattern_direction(axis, edge)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Axis = axis_ref
            if reversed:
                feature.Reversed = True
            feature.Angle = float(angle)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::PolarPattern", configure,
                               features=features)

    def add_thickness(self, face=None, thickness=None, faces=None,
                      outward=False):
        """Coque : évide la pièce, les faces choisies deviennent des
        ouvertures. Vers l'intérieur par défaut ; ``outward`` ajoute
        l'épaisseur à l'extérieur (la pièce d'origine devient le vide)."""
        from engine.kernel import (
            KernelError,
            label_for_type,
            shell_too_thick_message,
        )
        picked = [int(f) for f in (faces or [])]
        if not picked and face is not None:
            picked = [int(face)]
        if not picked:
            raise KernelError(
                "coque : cliquez au moins une face à ouvrir")
        if thickness is None or float(thickness) <= 0:
            raise KernelError("coque : épaisseur invalide")
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        previous_tip = tip
        volume_before = float(body.Shape.Volume)
        feature = body.newObject("PartDesign::Thickness", "Thickness")
        feature.Base = (tip, ["Face{}".format(f + 1) for f in picked])
        feature.Value = float(thickness)
        feature.Reversed = not outward   # FreeCAD : Reversed = vers l'intérieur
        feature.Label = label_for_type("PartDesign::Thickness", self.lang)
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, previous_tip)
            raise
        # Une épaisseur supérieure à la pièce est parfois acceptée sans
        # rien évider (le volume ne baisse pas). On refuse, comme un échec.
        if (not outward
                and float(body.Shape.Volume) >= volume_before - 1e-3):
            if not getattr(self, "_previewing", False):
                self._drop_failed_feature(body, doc, feature, previous_tip)
                self._recompute()
            raise KernelError(shell_too_thick_message())
        return self.get_tree()

    def _tip_face_parallel_to(self, tip, plane, exclude_face=None):
        """Face de ``tip`` parallèle à XY/XZ/YZ, hors ``exclude_face``.

        PartDesign::Draft (FreeCAD 1.0 / OCCT) ignore souvent un plan
        d'origine XZ/YZ comme plan neutre pour une face de calotte ; une
        face du solide de même orientation fonctionne. Repli : plan
        d'origine via ``_origin_feature``.
        """
        shape = getattr(tip, "Shape", None)
        if shape is None or shape.isNull():
            return None
        axis = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
        exclude = None if exclude_face is None else int(exclude_face)
        for index, face in enumerate(shape.Faces):
            if exclude is not None and index == exclude:
                continue
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            component = (normal.x, normal.y, normal.z)[axis]
            if abs(component) > 0.9:
                return (tip, ["Face{}".format(index + 1)])
        return None

    def add_draft(self, face, angle, neutral="XY"):
        """Dépouille de la face cliquée ; plan neutre XY/XZ/YZ."""
        from engine.kernel import (
            KernelError,
            label_for_type,
            parse_neutral_plane,
        )
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à dépouiller")
        plane = parse_neutral_plane(neutral)
        # XY : plan d'origine (comportement historique, OK pour les parois).
        # XZ/YZ : une face du Tip parallèle — les plans d'origine XZ/YZ sont
        # un no-op OCCT sur les faces de calotte (FreeCAD 1.0).
        if plane == "XY":
            neutral_ref = (self._origin_feature(self._PLANE_ROLES[plane]), [""])
        else:
            neutral_ref = self._tip_face_parallel_to(
                tip, plane, exclude_face=face)
            if neutral_ref is None:
                neutral_ref = (
                    self._origin_feature(self._PLANE_ROLES[plane]), [""])
        volume_before = float(body.Shape.Volume)
        previous_tip = tip
        feature = body.newObject("PartDesign::Draft", "Draft")
        feature.Base = (tip, ["Face{}".format(int(face) + 1)])
        feature.Angle = float(angle)
        feature.NeutralPlane = neutral_ref
        feature.Label = label_for_type("PartDesign::Draft", self.lang)
        try:
            self._recompute()
        except KernelError:
            if getattr(body, "Tip", None) is feature or body.Tip is None:
                body.Tip = previous_tip
            doc.removeObject(feature.Name)
            raise
        volume_after = float(body.Shape.Volume)
        if abs(volume_after - volume_before) < 1e-9:
            # Sous aperçu, l'abort de la transaction restaure tout ; un
            # removeObject d'une fonction aboutie DANS la transaction
            # serait rejoué par l'abort — double-nettoyage qui peut
            # ressusciter des objets (doublons observés dans l'arbre).
            if not getattr(self, "_previewing", False):
                body.Tip = previous_tip
                doc.removeObject(feature.Name)
                self._recompute()
            raise KernelError(
                "cette face ne peut pas être dépouillée par rapport à ce "
                "plan neutre — choisissez un autre plan neutre ou une autre face")
        return self.get_tree()

    def _dressup(self, type_id, label, prop, value, face=None, edges=None):
        """Fillet/chamfer share everything but the property they drive.

        The dress-up references the picked face or edges on the Tip
        feature — the shape the viewport tessellated, so the numbering
        matches by construction. A face means every edge of that face;
        an edge list is the precise edge selection.
        """
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        if edges:
            subs = ["Edge{}".format(int(e) + 1) for e in edges]
        elif face is not None:
            subs = ["Face{}".format(int(face) + 1)]
        else:
            raise KernelError(
                "sélectionnez des arêtes ou une face de la pièce")
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Base = (tip, subs)
        setattr(feature, prop, float(value))
        feature.Label = label
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, tip)
            raise
        return self.get_tree()

    def add_fillet(self, radius, face=None, edges=None):
        return self._dressup("PartDesign::Fillet", "Congé",
                             "Radius", radius, face=face, edges=edges)

    #: Jeton du panneau → énumération FreeCAD ``ChamferType``.

    def _chamfer_kind(self, obj):
        """``egale``, ``deux`` ou ``angle`` — ``egale`` si la propriété manque."""
        current = str(getattr(obj, "ChamferType", "") or "")
        for token, label in self._CHAMFER_TYPES.items():
            if current == label:
                return token
        return "egale"

    @staticmethod
    def _prop_float(obj, name):
        value = getattr(obj, name, 0)
        return float(getattr(value, "Value", value))

    def _chamfer_state(self, obj):
        """État relu pour l'arbre et la réédition."""
        return {
            "type": self._chamfer_kind(obj),
            "size": self._prop_float(obj, "Size"),
            "size2": self._prop_float(obj, "Size2"),
            "angle": self._prop_float(obj, "Angle"),
            "flip": bool(getattr(obj, "FlipDirection", False)),
        }

    def add_chamfer(self, size, face=None, edges=None,
                    size2=None, angle=None, chamfer_type="egale", flip=False):
        """Chanfrein : distance égale, deux distances, ou distance et angle.

        ``chamfer_type`` vaut ``egale`` (défaut, le geste historique),
        ``deux`` (``size`` et ``size2``) ou ``angle`` (``size`` et ``angle``
        en degrés, strictement entre 0 et 90). ``flip`` échange les deux
        côtés — sans effet quand les deux côtés sont égaux.
        """
        from engine.kernel import KernelError
        kind = str(chamfer_type or "egale")
        if kind not in self._CHAMFER_TYPES:
            raise KernelError(
                "type de chanfrein inconnu « {} » — attendu : {}".format(
                    kind, ", ".join(self._CHAMFER_TYPES)))
        try:
            distance = float(size)
        except (TypeError, ValueError):
            raise KernelError("distance de chanfrein invalide")
        if distance <= 0:
            raise KernelError("distance de chanfrein invalide")
        second = None
        degrees = None
        if kind == "deux":
            try:
                second = float(size2)
            except (TypeError, ValueError):
                raise KernelError("seconde distance de chanfrein invalide")
            if second <= 0:
                raise KernelError("seconde distance de chanfrein invalide")
        elif kind == "angle":
            try:
                degrees = float(angle)
            except (TypeError, ValueError):
                degrees = None
            if degrees is None or not (0 < degrees < 90):
                raise KernelError(
                    "angle de chanfrein invalide — entre 0 et 90 degrés, exclus")
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        if edges:
            subs = ["Edge{}".format(int(e) + 1) for e in edges]
        elif face is not None:
            subs = ["Face{}".format(int(face) + 1)]
        else:
            raise KernelError(
                "sélectionnez des arêtes ou une face de la pièce")
        feature = body.newObject("PartDesign::Chamfer", "Chamfer")
        feature.Base = (tip, subs)
        feature.ChamferType = self._CHAMFER_TYPES[kind]
        feature.Size = distance
        if second is not None:
            feature.Size2 = second
        if degrees is not None:
            feature.Angle = degrees
        feature.FlipDirection = bool(flip) and kind != "egale"
        feature.Label = self._t("Chanfrein")
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, tip)
            raise
        return self.get_tree()

    def add_hole(self, diameter, depth=None, through=False, cut="none",
                 cut_diameter=None, cut_depth=None, cut_angle=None,
                 face=None, points=None):
        """Perçage.

        Avec ``face`` et ``points`` (les centres cliqués sur la face, en
        coordonnées monde) : une esquisse est posée sur la face, un cercle
        par point, et le perçage la consomme — le geste « face, clics,
        OK ». Sinon le profil est la dernière esquisse non utilisée : ses
        cercles positionnent les trous. Dans les deux cas le diamètre
        saisi remplace celui des cercles. Borgne ou à travers tout,
        lamage ou fraisage optionnel.
        """
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        body = self._require_body()
        doc = self._require_doc()
        cut_type = self._HOLE_CUTS.get(str(cut))
        if cut_type is None:
            raise KernelError(
                "type inconnu « {} » — attendu : none, lamage ou "
                "fraisage".format(cut))
        if float(diameter) <= 0:
            raise KernelError("le diamètre doit être positif")
        if points:
            if face is None:
                raise KernelError("perçage : la face des positions manque")
            profile = self._hole_positions_sketch(face, points, diameter)
        else:
            profile = self._latest_sketch()
        hole = body.newObject("PartDesign::Hole", "Hole")
        hole.Profile = profile
        hole.Threaded = False
        hole.Diameter = float(diameter)
        if through or depth is None:
            hole.DepthType = "ThroughAll"
        else:
            hole.DepthType = "Dimension"
            hole.Depth = float(depth)
        hole.HoleCutType = cut_type
        if cut_type != "None" and cut_diameter:
            hole.HoleCutDiameter = float(cut_diameter)
        if cut_type == "Counterbore" and cut_depth:
            hole.HoleCutDepth = float(cut_depth)
        if cut_type == "Countersink" and cut_angle:
            try:
                hole.HoleCutCountersinkAngle = float(cut_angle)
            except AttributeError:
                pass  # renommée selon les versions ; l'angle par défaut sert
        hole.Label = label_for_type("PartDesign::Hole", self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(hole.Name)
            if points:
                doc.removeObject(profile.Name)
            raise
        return self.get_tree()

    def _hole_positions_sketch(self, face, points, diameter):
        """Esquisse sur ``face`` avec un cercle par point (monde → plan)."""
        from engine.kernel import KernelError
        import Part
        body = self._require_body()
        doc = self._require_doc()
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = self._t("Esquisse")
        self._attach_to_face(sketch, face)
        sketch.recompute()
        V = self._app().Vector
        to_local = sketch.getGlobalPlacement().inverse()
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                doc.removeObject(sketch.Name)
                raise KernelError("perçage : une position est [x, y, z]")
            local = to_local.multVec(V(*(float(c) for c in point)))
            sketch.addGeometry(Part.Circle(
                V(local.x, local.y, 0), V(0, 0, 1), float(diameter) / 2), False)
        return sketch
