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
        Les fonctions suivantes s'empilent dans ce corps. Un nom donné
        (autre que « Corps ») reste dans le dossier des corps ; sinon le
        corps y prend celui de sa dernière fonction.
        """
        doc = self._require_doc()
        body = doc.addObject("PartDesign::Body", "Body")
        name = str(name or "").strip()
        if name and name not in ("Corps", self._t("Corps")):
            self._name_body(body, name)
        else:
            body.Label = self._t("Corps")
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
        if obj.Name in self._removed_names():
            raise KernelError("{} est supprimé par une fonction — reculez "
                              "la barre au-dessus d'elle".format(obj.Label))
        self._body = obj
        return self.get_tree()

    def set_body_color(self, body, color, solid=None):
        """Couleur d'affichage d'un corps, persistée dans le .FCStd.

        Headless : pas de ViewObject. Propriété custom ``FreeSolidColor``.
        ``color`` = ``#rrggbb``, ou ``None`` / ``""`` pour le défaut.
        ``solid`` : un seul des solides d'un corps qui en garde plusieurs.
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
        if solid is not None:
            self._set_solid(obj, solid, color=value)
            return self.get_tree()
        if "FreeSolidColor" not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", "FreeSolidColor",
                            "FreeSolid", "Couleur d'affichage")
        obj.FreeSolidColor = value
        if "FreeSolidTinted" in obj.PropertiesList:
            obj.FreeSolidTinted = False  # choisie : la matière n'y touche plus
        return self.get_tree()

    def add_boolean(self, tool, type="cut"):
        """Combiner deux corps — Soustraire / Ajouter / Intersection.

        S'applique au corps actif. Un ``PartDesign::Body`` outil est
        absorbé (comportement PartDesign). Un outil qu'un plugin réclame
        (``boolean_tool``) ne l'est pas : le plugin rend un corps outil
        dérivé, qu'il tient à jour lui-même.
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
        if body in (tool_obj.OutListRecursive or ()):
            # Une copie de réseau de corps suit sa source : l'absorber
            # dans la source bouclerait le graphe, sans erreur visible.
            raise KernelError(
                "« {} » suit le corps actif : les combiner ici le ferait "
                "dépendre de lui-même — activez « {} » et prenez ce corps "
                "comme outil".format(tool_obj.Label, tool_obj.Label))
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
                midplane=False, thin=None, merge=True, body=None,
                **conditions):
        """Extrusion. ``conditions`` : voir ``engine.extrude`` —
        cond, face, offset, taper, cond2, length2, face2, offset2, taper2.
        ``thin`` : paroi mince, voir ``engine.extrude.thin_settings``.
        ``merge`` faux : un nouveau corps ; ``body`` : le corps où
        fusionner, le corps actif par défaut (``_result_body``)."""
        from engine.kernel import KernelError
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            profile = self._latest_sketch()
        body, made = self._result_body([profile], merge, body, conditions)
        tip = body.Tip  # les faces visées appartiennent à l'état d'avant
        helpers = []
        pad = None
        try:
            spec, helpers = self._thin_profile(body, profile, thin)
            helpers += self._profile_helpers(body, profile, helpers)
            pad = body.newObject("PartDesign::Pad", "Pad")
            self._link_profile(pad, profile, helpers)
            self._apply_extrude(pad, "pad", tip, length=length,
                                reversed=reversed, midplane=midplane,
                                **conditions)
            pad.Label = self._t("Extrusion")
            if spec is not None:
                self._mark_thin(pad, spec)
            self._own_thin_helpers(pad, helpers)
            if spec is not None and spec["caps"]:
                helpers += self._thin_cavity(body, pad, profile, spec)
            self._recompute()
        except KernelError:
            # Le corps neuf part en dernier, vidé d'abord.
            self._remove_all(([body] if made else [])
                             + ([pad] if pad is not None else []) + helpers)
            raise
        self._body = body
        return self.get_tree()

    def _result_body(self, profiles, merge, body, conditions=None):
        """Corps où ranger un volume (extrusion, révolution, lissage,
        balayage) : ``(corps, nouveau)``.

        Fusionner : le corps actif, ou ``body``. Sinon un nouveau corps —
        sauf si les esquisses sont seules dans le leur, qui le devient.
        Une face d'arrivée se clique sur le corps actif : elle ne vaut que
        là. ``conditions`` : celles d'une extrusion."""
        from engine.kernel import KernelError
        from engine.extrude import ExtrudeError, check_new_body
        conditions = conditions or {}
        doc = self._require_doc()
        active = self._require_body()
        if merge:
            if body is None:
                return active, False
            target = doc.getObject(str(body))
            if (target is None or target.TypeId != "PartDesign::Body"
                    or self._is_internal_tool(target)):
                raise KernelError("corps inconnu : {}".format(body))
            if target.Name in self._removed_names():
                raise KernelError("{} est supprimé par une fonction — "
                                  "reculez la barre au-dessus d'elle"
                                  .format(target.Label))
            if target is not active and (
                    conditions.get("cond") == "face"
                    or conditions.get("cond2") == "face"):
                raise KernelError(
                    "jusqu'à la face : fusionnez avec le corps actif, "
                    "celui de la face cliquée")
            return target, False
        try:
            check_new_body(conditions.get("cond"), conditions.get("cond2"))
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        homes = {getattr(p.getParentGeoFeatureGroup(), "Name", None)
                 for p in profiles}
        name = homes.pop() if len(homes) == 1 else None
        home = doc.getObject(name) if name else None
        if (getattr(home, "TypeId", "") == "PartDesign::Body"
                and not any(o.isDerivedFrom("PartDesign::Feature")
                            for o in home.Group)):
            return home, False
        made = doc.addObject("PartDesign::Body", "Body")
        made.Label = self._t("Corps")
        made.addProperty("App::PropertyBool", "FreeSolidNewBody", "FreeSolid",
                         "Né d'une fonction non fusionnée")
        made.FreeSolidNewBody = True
        return made, True

    def _profile_helpers(self, body, profile, helpers):
        """Objets cachés d'un profil rangé hors de son esquisse :

        - une esquisse d'un autre corps entre par un liant (l'esquisse
          reste où elle est, avec son appui et ses autres fonctions) ;
        - un profil par liant (paroi mince comprise) prend sa direction
          sur un axe qui suit la normale de l'esquisse : FreeCAD prendrait
          celle du plan du liant, parfois à l'opposé.

        ``helpers`` : les liants de paroi mince déjà faits."""
        made = []
        copy = None if helpers else self._profile_copy(body, profile)
        if copy is not None:
            made.append(copy)
        if helpers or made:
            axis = self._new_thin_helper(body, "PartDesign::Line",
                                         "SketchNormal",
                                         "Normale de l'esquisse")
            axis.AttachmentSupport = [(profile, "")]
            axis.MapMode = "ObjectZ"
            axis.Visibility = False
            made.insert(0, axis)
        return made

    def _profile_copy(self, body, sketch, label="Profil lié"):
        """Le liant caché qui fait entrer dans ``body`` une esquisse d'un
        autre corps, ou None si elle y est déjà."""
        if sketch.getParentGeoFeatureGroup() is body:
            return None
        binder = self._new_thin_binder(body, sketch, 0.0, False, label)
        binder.addProperty("App::PropertyBool", "FreeSolidProfileCopy",
                           "FreeSolid", "Copie liée d'une esquisse")
        binder.FreeSolidProfileCopy = True
        return binder

    def _link_profile(self, feature, profile, helpers):
        """Profil et direction d'une extrusion : l'esquisse, ou le dernier
        liant de ``helpers`` le long de l'axe de normale."""
        binders = [h for h in helpers
                   if h.TypeId == "PartDesign::SubShapeBinder"]
        feature.Profile = binders[-1] if binders else profile
        axis = self._sketch_normal_axis(helpers)
        if axis is not None:
            feature.ReferenceAxis = (axis, [""])

    @staticmethod
    def _sketch_normal_axis(helpers):
        return next((h for h in helpers if h.TypeId == "PartDesign::Line"),
                    None)

    def _profile_copy_of(self, feature):
        """Le liant d'une esquisse d'un autre corps, profil de ``feature``."""
        profile = getattr(feature, "Profile", None)
        linked = profile[0] if isinstance(profile, tuple) else profile
        if getattr(linked, "FreeSolidProfileCopy", False):
            return linked
        return None

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
        from engine.extrude import ExtrudeError, thin_cap_offsets
        self._check_caps_conditions(feature)
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
            axis = getattr(feature, "ReferenceAxis", None)
            if axis and axis[0] is not None:
                cavity.ReferenceAxis = axis   # la direction de la fonction
            self._plan_cavity(feature, cavity)
        except Exception as exc:  # noqa: BLE001
            self._remove_all(helpers)
            raise KernelError(_explain(exc))
        return helpers

    def _check_caps_conditions(self, feature):
        """Extrémités fermées : la cavité se règle sur des profondeurs
        borgnes, sans dépouille."""
        from engine.kernel import KernelError
        side = str(getattr(feature, "SideType", "One side"))
        borgne = (feature.Type == "Length"
                  and (side != "Two sides" or feature.Type2 == "Length"))
        tapered = any(abs(float(getattr(feature, prop, 0) or 0)) > 1e-9
                      for prop in ("TaperAngle", "TaperAngle2"))
        if not borgne or tapered:
            raise KernelError(
                "extrémités fermées : profondeur borgne, sans dépouille")

    def _plan_cavity(self, feature, cavity):
        """Cavité d'une paroi fermée : ses côtés, son sens et ses
        profondeurs suivent la fonction (``cavity_plan``)."""
        from engine.extrude import cavity_plan
        plan = cavity_plan(str(getattr(feature, "SideType", "One side")),
                           feature.Name)
        cavity.SideType = plan["SideType"]
        # L'enlèvement part à l'opposé de l'extrusion.
        cavity.Reversed = not feature.Reversed
        for prop in ("Length", "Length2"):
            cavity.setExpression(prop, plan.get(prop))

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
        features = [h for h in self._thin_helpers(obj) + [obj]
                    if h.isDerivedFrom("PartDesign::Feature")]
        if not features:
            return obj
        # La dernière dans le corps — un auxiliaire peut précéder sa
        # fonction (ajout d'un remplacement de face mixte).
        order = {o.Name: i for i, o in enumerate(
            getattr(obj.getParentGeoFeatureGroup(), "Group", None) or [])}
        return max(features, key=lambda o: order.get(o.Name, -1))

    def _sync_thin(self, obj):
        """Recopie les épaisseurs de la fonction dans ses liants, et ses
        conditions de fin dans sa cavité."""
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
                self._check_caps_conditions(obj)
                self._check_cavity(obj)
                outer, inner = thin_cap_offsets(spec)
                binders = [h for h in self._thin_helpers(obj)
                           if h.TypeId == "PartDesign::SubShapeBinder"]
                steps = [(outer, False), (inner, False)]
                chain = binders
                # Conditions rééditées : la cavité suit les côtés et le sens.
                for cavity in self._thin_helpers(obj):
                    if cavity.TypeId == "PartDesign::Pocket":
                        self._plan_cavity(obj, cavity)
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

    #: Conditions d'une extrusion que ``set_params`` réédite : propriété
    #: (``Type`` et ``Type2`` reçoivent la condition de la création) ->
    #: paramètre de ``engine.extrude.extrude_options``.
    _EXTRUDE_OPTIONS = {"Type": "cond", "Type2": "cond2",
                        "Midplane": "midplane", "Reversed": "reversed",
                        "TaperAngle": "taper", "TaperAngle2": "taper2",
                        "Offset": "offset"}
    _EXTRUDE_KINDS = {"PartDesign::Pad": "pad", "PartDesign::Pocket": "pocket"}

    def _extrude_state(self, obj):
        """Conditions de fin d'une extrusion ou d'un enlèvement, dans les
        mots de la création (``engine.extrude.extrude_state``), plus
        ``face`` : la face d'arrivée existe. None sinon."""
        from engine.extrude import extrude_state
        kind = self._EXTRUDE_KINDS.get(getattr(obj, "TypeId", ""))
        if kind is None:
            return None
        props = {}
        for prop in ("SideType", "Type", "Type2", "Reversed", "TaperAngle",
                     "TaperAngle2", "Offset"):
            value = getattr(obj, prop, None)
            props[prop] = getattr(value, "Value", value)
        if "SideType" not in obj.PropertiesList:
            # FreeCAD 1.0 : un booléen pour le plan milieu.
            props["SideType"] = ("Symmetric" if getattr(obj, "Midplane", False)
                                 else "One side")
        state = extrude_state(kind, props)
        if state is not None:
            state["face"] = bool(getattr(obj, "UpToFace", None))
            # Premier volume de son corps : aucun « jusqu'à » ne l'arrête.
            state["alone"] = getattr(obj, "BaseFeature", None) is None
        return state

    def _set_extrude_options(self, obj, options, previous, exprs_before):
        """Pose les conditions rééditées (``options`` : propriété de
        ``_EXTRUDE_OPTIONS`` -> valeur) par-dessus celles de la fonction.
        ``previous`` reçoit de quoi tout défaire (``set_params``)."""
        from engine.kernel import KernelError, _explain, parse_user_number
        from engine.extrude import ExtrudeError, extrude_options
        state = self._extrude_state(obj)
        if state is None:
            raise KernelError(
                "{} : conditions de fin que la réédition ne sait pas "
                "changer".format(obj.Label))
        state.pop("face")
        state.pop("alone")
        for prop, value in options.items():
            name = self._EXTRUDE_OPTIONS[prop]
            if name in ("midplane", "reversed"):
                if not isinstance(value, bool) and not (
                        type(value) is int and value in (0, 1)):
                    raise KernelError("sens de l'extrusion : booléen attendu")
                value = bool(value)
            elif name in ("taper", "taper2", "offset"):
                number = (parse_user_number(value) if isinstance(value, str)
                          else value)
                if isinstance(number, bool) or not isinstance(
                        number, (int, float)):
                    raise KernelError(
                        "{} : valeur numérique attendue".format(name))
                value = float(number)
            elif name == "cond2":
                value = str(value) if value else None
            else:
                value = str(value)
            state[name] = value
        try:
            props = extrude_options(
                self._EXTRUDE_KINDS[obj.TypeId], **state)
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        for prop, face in (("Type", "UpToFace"), ("Type2", "UpToFace2")):
            if props.get(prop) == "UpToFace" and not getattr(obj, face, None):
                raise KernelError(
                    "jusqu'à la face : la fonction n'a pas de face d'arrivée")
        side = props.pop("SideType")
        if "SideType" in obj.PropertiesList:
            props = {"SideType": side, **props}
        elif side == "Two sides":
            raise KernelError(
                "deuxième direction : FreeCAD {} requis".format("1.1"))
        else:
            props["Midplane"] = side == "Symmetric"
        for prop, value in props.items():
            previous.append((prop, exprs_before.get(prop),
                             getattr(obj, prop, None)))
            try:
                obj.setExpression(prop, None)
            except Exception:  # noqa: BLE001
                pass
            try:
                setattr(obj, prop, value)
            except Exception as exc:  # noqa: BLE001
                raise KernelError(_explain(exc))

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
        try:
            helpers += self._profile_helpers(body, profile, helpers)
        except Exception:
            self._remove_all(helpers)
            raise
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        self._link_profile(pocket, profile, helpers)
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
                 closed=False, merge=True, body=None):
        """Lissage (ou enlèvement) entre plusieurs profils —
        typiquement des esquisses posées sur des plans de référence.
        ``merge``, ``body`` : comme l'extrusion (``_result_body``) ; un
        enlèvement creuse le corps actif."""
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        active = self._require_body()
        if not isinstance(sketches, (list, tuple)) or len(sketches) < 2:
            raise KernelError("un lissage demande au moins deux profils")
        profiles = [self._get_sketch(str(n)) for n in sketches]
        if subtractive:
            body, made = active, False
        else:
            body, made = self._result_body(profiles, merge, body)
        type_id = ("PartDesign::SubtractiveLoft" if subtractive
                   else "PartDesign::AdditiveLoft")
        helpers = []
        loft = None
        try:
            # Une esquisse d'un autre corps entre par un liant caché.
            links = []
            for sketch in profiles:
                copy = self._profile_copy(body, sketch)
                if copy is not None:
                    helpers.append(copy)
                links.append(copy or sketch)
            loft = body.newObject(type_id, type_id.split("::")[-1])
            loft.Profile = links[0]
            try:
                loft.Sections = links[1:]
            except TypeError:
                loft.Sections = [(p, ("",)) for p in links[1:]]
            loft.Ruled = bool(ruled)
            loft.Closed = bool(closed)
            loft.Label = label_for_type(type_id, self.lang)
            self._own_thin_helpers(loft, helpers)
            self._recompute()
        except Exception:
            self._remove_all(([body] if made else []) + helpers
                             + ([loft] if loft is not None else []))
            raise
        self._body = body
        return self.get_tree()

    def add_sweep(self, profile, spine, subtractive=False, merge=True,
                  body=None):
        """Balayage (ou enlèvement) : un profil suit une
        trajectoire — deux esquisses, souvent sur des plans différents.
        ``merge``, ``body`` : comme l'extrusion (``_result_body``) ; un
        enlèvement creuse le corps actif."""
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        active = self._require_body()
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
        sketches = [section] + ([path] if path.TypeId == "Sketcher::"
                                "SketchObject" else [])
        if subtractive:
            body, made = active, False
        else:
            body, made = self._result_body(sketches, merge, body)
        type_id = ("PartDesign::SubtractivePipe" if subtractive
                   else "PartDesign::AdditivePipe")
        binder = None
        helpers = []
        pipe = None
        try:
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
            else:
                # Esquisse d'un autre corps : un liant caché, comme le profil.
                copy = self._profile_copy(body, path, "Trajectoire liée")
                if copy is not None:
                    helpers.append(copy)
                    path = copy
            copy = self._profile_copy(body, section)
            if copy is not None:
                helpers.insert(0, copy)
                # FreeCAD ne prend en entier que le profil d'une esquisse ;
                # d'un liant, une seule face : le profil doit être d'un
                # seul tenant, ou une partie serait perdue.
                doc.recompute()
                if len(copy.Shape.Faces) != 1:
                    raise KernelError(
                        "balayage dans un autre corps : le profil doit "
                        "être d'un seul tenant")
            pipe = body.newObject(type_id, type_id.split("::")[-1])
            pipe.Profile = (copy, ["Face1"]) if copy is not None else section
            try:
                pipe.Spine = path
            except TypeError:
                pipe.Spine = (path, ("",))
            pipe.Label = label_for_type(type_id, self.lang)
            # Les liants partent avec le balayage, celui de la courbe 3D
            # compris : un corps neuf n'en garde rien.
            self._own_thin_helpers(
                pipe, helpers + ([binder] if binder is not None else []))
            self._recompute()
        except Exception:
            self._remove_all(([body] if made else [])
                             + ([binder] if binder is not None else [])
                             + helpers
                             + ([pipe] if pipe is not None else []))
            raise
        self._body = body
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

    def _revolution_reference(self, profile, axis, body=None,
                              feature=None, made=None):
        """Référence d'axe : axe d'esquisse, ligne, ou axe d'origine — dans
        ``body`` (le corps actif par défaut). Une esquisse d'un autre corps
        n'y est pas : son axe passe par une ligne cachée accrochée à elle
        (``made`` reçoit les nouvelles, ``feature`` garde la sienne)."""
        from engine.kernel import KernelError
        body = body or self._require_body()
        linked = profile.getParentGeoFeatureGroup() is not body
        token = str(axis or "vertical").strip() or "vertical"
        if token in self._SKETCH_AXES:
            if linked:
                return (self._sketch_axis_line(body, profile, token,
                                               feature, made), [""])
            return (profile, [self._SKETCH_AXES[token]])
        if token.upper() in self._AXIS_ROLES:
            return (self._origin_axis(token, body), [""])
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
            # l'esquisse, ni l'esquisse dans un autre corps : une ligne de
            # référence, cachée, la porte.
            if linked or self._is_construction(profile, gid, geo):
                return (self._axis_datum(profile, gid, body), [""])
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

    def _sketch_axis_line(self, body, profile, token, feature=None,
                          made=None):
        """L'axe vertical ou horizontal d'une esquisse d'un autre corps :
        une ligne cachée accrochée à elle, qui suit sa fonction. Celle de
        ``feature`` resert à la réédition."""
        line = next((h for h in (self._thin_helpers(feature)
                                 if feature is not None else [])
                     if getattr(h, "FreeSolidSketchAxis", "")), None)
        if line is None:
            line = self._new_thin_helper(body, "PartDesign::Line",
                                         "SketchAxis", "Axe de l'esquisse")
            line.addProperty("App::PropertyString", "FreeSolidSketchAxis",
                             "FreeSolid", "Axe d'esquisse porté")
            line.Visibility = False
            if feature is not None:
                self._own_thin_helpers(feature, [line])
            if made is not None:
                made.append(line)
        line.AttachmentSupport = [(profile, "")]
        line.MapMode = "ObjectY" if token == "vertical" else "ObjectX"
        # « ObjectY » pose la ligne vers -Y de l'esquisse : retournée, elle
        # suit son axe vertical, et la révolution tourne du même côté.
        line.MapReversed = token == "vertical"
        line.FreeSolidSketchAxis = token
        return line

    def _axis_datum(self, profile, gid, body=None):
        """Ligne de référence cachée, calée sur une ligne de l'esquisse."""
        body = body or self._require_body()
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
        if getattr(target, "FreeSolidSketchAxis", ""):
            return str(target.FreeSolidSketchAxis)
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
        profile, _ = self._profile_of(obj)   # à travers un liant
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
                  reversed=False, midplane=False, merge=True, body=None):
        """Révolution ou gorge : même axe, ajout ou enlèvement.

        Sans axe, l'axe vertical de l'esquisse — le profil se dessine à
        côté. ``axis`` peut être ``horizontal``, ``line:<id>`` (une ligne
        de l'esquisse, de construction de préférence) ou ``X``, ``Y``, ``Z``.
        ``merge``, ``body`` : comme l'extrusion (``_result_body``) ; une
        gorge creuse le corps actif.
        """
        from engine.kernel import (
            KernelError,
            label_for_type,
        )
        active = self._require_body()
        try:
            degrees = float(angle)
        except (TypeError, ValueError):
            raise KernelError("angle de révolution invalide")
        if not (degrees > 0 and degrees <= 360):
            raise KernelError("angle de révolution invalide")
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        if type_id == "PartDesign::Revolution":
            body, made = self._result_body([profile], merge, body)
        else:
            body, made = active, False
        helpers = []
        feature = None
        try:
            copy = self._profile_copy(body, profile)
            if copy is not None:
                helpers.append(copy)
            reference = self._revolution_reference(profile, axis, body,
                                                   made=helpers)
            feature = body.newObject(type_id, type_id.split("::")[-1])
            feature.Profile = copy or profile
            feature.ReferenceAxis = reference
            feature.Angle = degrees
            if reversed:
                feature.Reversed = True
            if midplane:
                feature.Midplane = True
            feature.Label = label_for_type(type_id, self.lang)
            self._own_thin_helpers(feature, helpers)
            self._drop_unused_axis_tools()
            self._recompute()
        except Exception:
            self._remove_all(([body] if made else []) + helpers
                             + ([feature] if feature is not None else []))
            self._drop_unused_axis_tools()
            raise
        self._body = body
        return self.get_tree()

    def add_revolution(self, angle=360.0, sketch=None, axis=None,
                       reversed=False, midplane=False, merge=True,
                       body=None):
        """Révolution. ``merge`` faux : un nouveau corps ; ``body`` : le
        corps où fusionner."""
        return self._revolved(
            "PartDesign::Revolution", angle, sketch, axis=axis,
            reversed=reversed, midplane=midplane, merge=merge, body=body)

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

    def _transform(self, type_id, configure, features=None, scope=None):
        """Répétition ou symétrie des fonctions ``features`` du corps
        actif. ``scope`` : autres corps que ses enlèvements de matière
        creusent aussi (``engine/bodypattern.py``)."""
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
        previous = body.Tip
        body.Tip = feature
        try:
            self._recompute()
            if scope:
                self._attach_pattern_scope(feature, scope)
                self._recompute()
        except KernelError:
            # Refusée : la pointe revient où elle était, sinon le corps
            # resterait sans solide.
            self._drop_pattern_scope(feature)
            body.Tip = previous
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_mirror(self, plane="YZ", features=None, scope=None):
        """Symétrie d'une ou plusieurs fonctions par rapport à un plan
        d'origine (XY/XZ/YZ = Dessus/Face/Droite).

        ``features`` : noms des fonctions à symétriser. Absent : la
        dernière fonction additive ou soustractive du corps actif.
        ``scope`` : corps concernés, voir ``_transform``.
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
                               features=features, scope=scope)

    def _origin_axis(self, axis, body=None):
        from engine.kernel import KernelError
        role = self._AXIS_ROLES.get(str(axis).upper())
        if role is None:
            raise KernelError(
                "axe inconnu « {} » — attendu X, Y ou Z".format(axis))
        return self._origin_feature(role, body)

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
                           edge=None, spacing=False, reversed=False,
                           length2=None, count2=None, axis2=None, edge2=None,
                           reversed2=False, scope=None):
        """Réseau linéaire d'une ou plusieurs fonctions le long d'un axe
        ou d'une arête droite — et, avec ``count2``, d'une deuxième
        direction (``axis2`` ou ``edge2``, ``length2``) : un quadrillage.

        ``length`` : longueur totale (par défaut) ou, avec ``spacing``,
        pas entre deux occurrences (de même pour ``length2``).
        ``features`` : noms des fonctions à répéter. Absent : la dernière
        fonction additive ou soustractive. ``scope`` : corps concernés,
        voir ``_transform``.
        """
        from engine.kernel import KernelError
        direction = self._pattern_direction(axis, edge)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")
        second = None
        if count2 is not None and int(count2) > 1:
            if length2 is None or float(length2) <= 0:
                raise KernelError("indiquez la distance de la direction 2")
            second = (self._pattern_direction(axis2 or "Y", edge2),
                      int(count2), float(length2))

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
            if second is not None:
                link, count_2, extent = second
                feature.Direction2 = link
                # Longueur totale toujours : en mode « pas », FreeCAD ne
                # recalcule pas la liste des écarts quand le nombre change
                # par script (une rangée se superpose). Le pas est gardé
                # pour la réédition du nombre.
                feature.Occurrences2 = count_2
                if spacing:
                    feature.Length2 = extent * (count_2 - 1)
                    self._stamp(feature, pitch2=extent)
                else:
                    feature.Length2 = extent
                if reversed2:
                    feature.Reversed2 = True
        return self._transform("PartDesign::LinearPattern", configure,
                               features=features, scope=scope)

    def add_polar_pattern(self, count, angle=360.0, axis="Z", features=None,
                          edge=None, reversed=False, scope=None):
        """Réseau circulaire d'une ou plusieurs fonctions autour d'un
        axe d'origine ou d'une arête droite.

        ``features`` : noms des fonctions à répéter. Absent : la dernière
        fonction additive ou soustractive du corps actif. ``scope`` :
        corps concernés, voir ``_transform``.
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
                               features=features, scope=scope)

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

    def _draft_neutral_token(self, obj):
        """Plan neutre relu sur la dépouille : ``XY``, ``XZ`` ou ``YZ``.

        ``add_draft`` y pose un plan d'origine, ou une face du Tip
        parallèle au plan choisi : on relit le rôle du plan, ou l'axe de la
        normale de la face. ``XY`` par défaut, comme ``add_draft``.
        """
        ref = getattr(obj, "NeutralPlane", None)
        try:
            target, subs = ref[0], ref[1]
        except Exception:
            return "XY"
        for token, role in self._PLANE_ROLES.items():
            if getattr(target, "Role", "") == role:
                return token
        try:
            sub = str(list(subs)[0]) if subs else ""
            face = target.Shape.getElement(sub)
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        except Exception:
            return "XY"
        for token, component in (("XY", normal.z), ("XZ", normal.y),
                                 ("YZ", normal.x)):
            if abs(component) > 0.9:
                return token
        return "XY"

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

    def _dressup(self, type_id, prop, value, face=None, edges=None):
        """Fillet/chamfer share everything but the property they drive.

        The dress-up references the picked face or edges on the Tip
        feature — the shape the viewport tessellated, so the numbering
        matches by construction. A face means every edge of that face;
        an edge list is the precise edge selection.
        """
        from engine.kernel import KernelError, label_for_type
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
        feature.Label = label_for_type(type_id, self.lang)
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, tip)
            raise
        self._refuse_invalid_dressup(body, doc, feature, tip)
        return self.get_tree()

    def _invalid_dressup_message(self, feature):
        """Refus d'un congé ou d'un chanfrein de forme invalide, ou None.

        Le modeleur peut marquer la fonction à jour avec une forme cassée
        (fil qui se recoupe, volume faux) : ``isValid()`` le voit, l'état
        non.
        """
        from engine.guard import invalid_dressup_message
        shape = feature.Shape
        if not shape.isNull() and shape.isValid():
            return None
        base, subs = feature.Base
        return invalid_dressup_message(
            feature.TypeId, self._dressup_flush(base, subs))

    def _dressup_flush(self, base, subs):
        """Une arête choisie, arc ou cercle, bute-t-elle sur un cylindre de
        même cercle porteur qui affleure ? Sert au message, rien d'autre."""
        from engine.guard import flush_cylinder
        try:
            shape = base.Shape
            edges = [edge for sub in subs
                     for edge in shape.getElement(str(sub)).Edges]
            cylinders = []
            for face in shape.Faces:
                surface = face.Surface
                if surface.TypeId != "Part::GeomCylinder":
                    continue
                v0, v1 = face.ParameterRange[2:]  # le long de l'axe
                cylinders.append((tuple(surface.Center + surface.Axis * v0),
                                  tuple(surface.Center + surface.Axis * v1),
                                  surface.Radius))
            return any(
                flush_cylinder(tuple(edge.Curve.Center),
                               tuple(edge.Curve.Axis), edge.Curve.Radius,
                               cylinders)
                for edge in edges if edge.Curve.TypeId == "Part::GeomCircle")
        except Exception:  # noqa: BLE001 - l'indice ne masque pas le refus
            return False

    def _refuse_invalid_dressup(self, body, doc, feature, tip):
        """Retire et refuse un congé ou un chanfrein de forme invalide."""
        from engine.kernel import KernelError
        message = self._invalid_dressup_message(feature)
        if message is None:
            return
        # Sous aperçu, l'abort de la transaction restaure tout (voir
        # add_draft) : pas de removeObject d'une fonction recalculée.
        if not getattr(self, "_previewing", False):
            self._drop_failed_feature(body, doc, feature, tip)
            self._recompute()
        raise KernelError(message)

    def add_fillet(self, radius, face=None, edges=None):
        return self._dressup("PartDesign::Fillet",
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

    #: Condition de fin d'un perçage : mot de la création -> ``DepthType``.
    _HOLE_DEPTHS = {"travers": "ThroughAll", "borgne": "Dimension"}

    def _hole_state(self, obj):
        """Perçage relu pour la réédition, dans les mots de la création :
        ``{cut, cond, depth, cutDiameter, cutDepth, cutAngle}`` — une cote
        que le type ne prend pas vaut None. None pour un perçage taraudé
        ou d'un type que le panneau n'a pas."""
        cuts = {value: word for word, value in self._HOLE_CUTS.items()}
        depths = {value: word for word, value in self._HOLE_DEPTHS.items()}
        cut = cuts.get(str(getattr(obj, "HoleCutType", "")))
        cond = depths.get(str(getattr(obj, "DepthType", "")))
        if cut is None or cond is None or getattr(obj, "Threaded", False):
            return None
        def size(prop, wanted):
            value = self._prop_float(obj, prop) if wanted else 0.0
            return value if value > 0 else None
        return {
            "cut": cut, "cond": cond,
            "depth": size("Depth", cond == "borgne"),
            "cutDiameter": size("HoleCutDiameter", cut != "none"),
            "cutDepth": size("HoleCutDepth", cut == "lamage"),
            "cutAngle": size("HoleCutCountersinkAngle", cut == "fraisage"),
        }

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
        self._refuse_invalid_dressup(body, doc, feature, tip)
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
