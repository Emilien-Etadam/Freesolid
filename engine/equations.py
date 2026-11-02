"""Paramètres et équations : cotes d'une fonction, variables, expressions.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class EquationsMixin:
    # -- paramètres et équations ------------------------------------------

    #: Properties offered for editing, in display order. A whitelist rather
    #: than full introspection: Pad alone carries a dozen numeric properties
    #: and prompting through Offset/TaperAngle/Length2 buries the one that
    #: matters.
    _EDITABLE_PROPS = ("Length", "LengthFwd", "Radius", "Size", "Angle",
                       "Thickness", "Thickness2", "CapThickness", "Value",
                       "Occurrences",
                       "Diameter", "Depth", "HoleCutDiameter",
                       "HoleCutDepth", "Pitch", "Height")

    # Genres dont une propriété porte le nom d'une cote sans en être une :
    # la taille d'affichage d'un plan ou d'un axe de référence (l'interface
    # dessine le sien à la taille de la pièce), la hauteur d'une
    # projection, que le mode « Edges » n'emploie pas.
    _NO_DIMENSIONS = ("PartDesign::Plane", "PartDesign::Line",
                      "Part::ProjectOnSurface")

    _VARSET_NAME = "Variables"


    def set_param(self, feature, prop, value):
        """Set one dimension on one feature, and recompute.

        This is the whole parametric promise in one operation: the UI edits
        the ``length`` of a pad and the part rebuilds. ``prop`` is a neutral
        key (``PARAM_KEYS``), as in ``set_params``. Même atomicité que
        ``set_params`` : un refus ne modifie pas la pièce.
        """
        return self.set_params(feature, {str(prop): value})

    def set_params(self, feature, values):
        """Set several properties at once, one recompute — the edit panel
        applies (and previews) its whole form atomically.

        Keys are the neutral keys of ``get_params`` (``PARAM_KEYS`` in
        ``engine/vocab.py``) ; a FreeCAD property name the table knows is
        still accepted during the transition, any other key is refused.
        A value may be a number, or a string: a numeric string is a
        number, anything else is an **expression** (``2*Largeur + 5``) —
        an equation, via the expression engine.
        """
        from engine.kernel import (
            KernelError,
            _explain,
            parse_user_number,
            shell_too_thick_message,
        )
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if not isinstance(values, dict):
            raise KernelError("values doit être un objet JSON")
        # Les corps qu'un volume fond, ou qu'un enlèvement creuse : pas
        # une cote, ses objets cachés.
        values = dict(values)
        chosen = "bodies" in values
        bodies = values.pop("bodies", None)
        values, asked = self._props_from_keys(obj, values)
        if chosen and self._is_cut_source(obj):
            self._set_cut_bodies(obj, bodies)
        elif chosen:
            self._set_fused_bodies(obj, bodies)
        # Atomicité : une expression était stockée AVANT que le recompute
        # ne la valide — un identifiant inconnu (« _ ») laissait la pièce
        # Invalid pour toujours (barre bloquée, cascade « Tool shape is
        # null »). On mémorise l'état pour tout restaurer sur refus.
        exprs_before = dict(obj.ExpressionEngine or [])
        previous = []  # (prop, ancienne expression ou None, ancienne valeur)
        editable = (() if obj.TypeId in self._NO_DIMENSIONS
                    else self._EDITABLE_PROPS)
        thin = self._thin_spec(obj) is not None
        revolved = obj.TypeId in (
            "PartDesign::Revolution", "PartDesign::Groove")
        if obj.TypeId == "PartDesign::Chamfer":
            editable = editable + ("Size2", "ChamferType", "FlipDirection")
        if revolved:
            editable = editable + ("Reversed", "Midplane", "axis")
        shelled = obj.TypeId == "PartDesign::Thickness"
        if shelled:
            editable = editable + ("Reversed",)
        if obj.TypeId == "PartDesign::Hole":
            editable = editable + ("HoleCutType", "DepthType",
                                   "HoleCutCountersinkAngle")
            # Le type d'abord : FreeCAD y remet les cotes de tête à ses
            # valeurs, celles demandées passent après.
            first = ("HoleCutType", "DepthType")
            values = {**{p: values[p] for p in first if p in values},
                      **{p: v for p, v in values.items() if p not in first}}
        if obj.TypeId in self._EXTRUDE_KINDS:
            # Conditions de fin : posées ensemble, avant les cotes.
            editable = editable + ("Length2", "FreeSolidThinReversed")
            options = {prop: values[prop] for prop in values
                       if prop in self._EXTRUDE_OPTIONS}
            if options:
                values = {prop: value for prop, value in values.items()
                          if prop not in options}
                try:
                    self._set_extrude_options(obj, options, previous,
                                              exprs_before)
                except KernelError:
                    self._restore_props(obj, previous)
                    raise
        if "FreeSolidBodyPattern" in obj.PropertiesList:
            # Réseau de corps : ses cotes sont des propriétés de l'hôte.
            editable = editable + ("Length2", "Occurrences2")
        if obj.TypeId == "PartDesign::LinearPattern":
            editable = editable + ("Occurrences2",)
            pitch2 = float(getattr(obj, "FreeSolidPitch2", 0) or 0)
            if pitch2 and "Occurrences2" in values:
                try:
                    rows = int(float(values["Occurrences2"]))
                except (TypeError, ValueError):
                    rows = 0
                if rows > 1:
                    # Même pas, nouveau nombre : la longueur totale suit.
                    values = {**values, "Length2": pitch2 * (rows - 1)}
                    editable = editable + ("Length2",)
        for prop, value in values.items():
            prop = str(prop)
            if prop not in editable:
                raise KernelError("propriété non éditable : {}".format(
                    asked.get(prop, prop)))
            if prop == "axis":
                # L'esquisse, à travers le liant d'un autre corps ; l'axe
                # se range dans le corps de la fonction.
                profile, _ = self._profile_of(obj)
                if profile is None:
                    self._restore_props(obj, previous)
                    raise KernelError("l'axe de révolution doit être une ligne")
                token = str(value).strip() if value is not None else ""
                try:
                    reference = self._revolution_reference(
                        profile, token, obj.getParentGeoFeatureGroup(), obj)
                except KernelError:
                    self._restore_props(obj, previous)
                    raise
                previous.append(("ReferenceAxis", exprs_before.get("ReferenceAxis"),
                                 getattr(obj, "ReferenceAxis", None)))
                try:
                    obj.ReferenceAxis = reference
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop == "Reversed" and shelled:
                # Clé « outward » : vers l'extérieur, l'inverse de FreeCAD.
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError("sens de la coque : booléen attendu")
                previous.append((prop, None, getattr(obj, prop, None)))
                try:
                    obj.Reversed = not flag
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop in ("HoleCutType", "DepthType"):
                table = (self._HOLE_CUTS if prop == "HoleCutType"
                         else self._HOLE_DEPTHS)
                token = str(value).strip() if value is not None else ""
                if token not in table:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "perçage : « {} » inconnu — attendu : {}".format(
                            token, ", ".join(table)))
                if prop == "HoleCutType":
                    # FreeCAD recalcule les cotes de tête au changement de
                    # type : gardées ici, un refus les rend telles quelles,
                    # après le type (``_restore_props`` remonte la liste).
                    for head in ("HoleCutDiameter", "HoleCutDepth",
                                 "HoleCutCountersinkAngle"):
                        previous.append((head, exprs_before.get(head),
                                         getattr(obj, head, None)))
                previous.append((prop, None, getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, table[token])
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop in ("Reversed", "Midplane") and revolved:
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError("sens de révolution : booléen attendu")
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, flag)
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if not hasattr(obj, prop):
                raise KernelError("{} n'a pas de propriété {}".format(
                    obj.Label, asked.get(prop, prop)))
            if prop == "ChamferType":
                token = str(value).strip() if value is not None else ""
                if token not in self._CHAMFER_TYPES:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "type de chanfrein inconnu « {} » — attendu : {}"
                        .format(token, ", ".join(self._CHAMFER_TYPES)))
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, self._CHAMFER_TYPES[token])
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop == "FreeSolidThinReversed":
                # Le côté de la paroi : _sync_thin recopie les décalages.
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "côté de la paroi mince : booléen attendu")
                previous.append((prop, None, getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, flag)
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop == "FlipDirection":
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "inverser le chanfrein : booléen attendu")
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, flag)
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if (prop in ("Thickness", "Thickness2", "CapThickness") and thin
                    and isinstance(value, str)
                    and parse_user_number(value) is None):
                self._restore_props(obj, previous)
                raise KernelError(
                    "épaisseur de paroi : valeur numérique attendue")
            previous.append((prop, exprs_before.get(prop),
                             getattr(obj, prop, None)))
            if isinstance(value, str):
                number = parse_user_number(value)
                if number is not None:
                    value = number  # « 6,5 » est un nombre, pas une équation
                else:
                    text = self._user_expression(value.strip())
                    try:
                        obj.setExpression(prop, text)
                    except Exception as exc:  # noqa: BLE001
                        self._restore_props(obj, previous)
                        raise KernelError(_explain(exc))
                    continue
            # Valeur numérique : une expression existante reprendrait la
            # main au recompute — on la retire d'abord.
            try:
                obj.setExpression(prop, None)
            except Exception:
                pass
            current = getattr(obj, prop, None)
            if isinstance(current, int) and not isinstance(current, bool):
                value = int(value)
            try:
                setattr(obj, prop, value)
            except Exception as exc:  # noqa: BLE001
                self._restore_props(obj, previous)
                raise KernelError(_explain(exc))
        try:
            self._sync_thin(obj)
            self._recompute()
            if obj.TypeId in ("PartDesign::Fillet", "PartDesign::Chamfer"):
                # Rayon ou distance rééditée : même garde qu'à la création.
                invalid = self._invalid_dressup_message(obj)
                if invalid is not None:
                    raise KernelError(invalid)
            if shelled and self._shell_left_full(obj):
                raise KernelError(shell_too_thick_message())
        except KernelError as exc:
            self._restore_props(obj, previous)
            try:
                self._sync_thin(obj)
                self._recompute()
            except KernelError:
                pass  # l'état d'origine était déjà sain : ne pas masquer exc
            raise KernelError(
                "{} — la pièce n'a pas été modifiée".format(exc))
        self._drop_unused_axis_tools()
        return self.get_tree()

    @staticmethod
    def _shell_left_full(obj):
        """Coque vers l'intérieur qui n'évide rien : trop épaisse, FreeCAD
        l'accepte parfois sans rien retirer (garde de ``add_thickness``)."""
        base = getattr(obj, "BaseFeature", None)
        shape = getattr(base, "Shape", None)
        if (not getattr(obj, "Reversed", False) or shape is None
                or shape.isNull()):
            return False
        return float(obj.Shape.Volume) >= float(shape.Volume) - 1e-3

    @staticmethod
    def _props_from_keys(obj, values):
        """``{clé: valeur}`` -> ``({propriété FreeCAD: valeur},
        {propriété: clé demandée})``. Une clé neutre se traduit selon le
        genre de l'objet ; un nom de propriété que la table connaît passe
        tel quel (transition) ; toute autre clé est refusée, comme deux
        clés qui visent la même propriété (« length » et « Length »)."""
        from engine.kernel import KernelError
        from engine.vocab import param_prop_for, type_key_for
        type_key = type_key_for(getattr(obj, "TypeId", ""))
        props, asked = {}, {}
        for key, value in values.items():
            prop = param_prop_for(type_key, str(key))
            if prop is None:
                raise KernelError("propriété non éditable : {}".format(key))
            if prop in props:
                raise KernelError(
                    "clés en double pour la même cote : {}, {}".format(
                        asked[prop], key))
            props[prop] = value
            asked[prop] = str(key)
        return props, asked

    @staticmethod
    def _restore_props(obj, previous):
        """Défait ``set_params`` : remet liaisons et valeurs mémorisées."""
        for prop, old_expr, old_value in reversed(previous):
            try:
                obj.setExpression(prop, old_expr)  # None efface la liaison
            except Exception:
                pass
            if old_expr is None and old_value is not None:
                try:
                    setattr(obj, prop, old_value)
                except Exception:
                    pass

    def _editable_props(self, obj):
        """Cotes proposées à l'édition. Le chanfrein ne montre que celles
        du type en cours : une distance, deux distances, ou distance et angle."""
        if getattr(obj, "TypeId", "") in self._NO_DIMENSIONS:
            return ()
        if "FreeSolidBodyPattern" in getattr(obj, "PropertiesList", ()):
            # Réseau de corps : les cotes que l'hôte porte (get_params
            # saute celles qu'il n'a pas).
            return self._EDITABLE_PROPS + ("Length2", "Occurrences2")
        if getattr(obj, "TypeId", "") == "PartDesign::Hole":
            # Perçage : les cotes que son type et sa condition de fin
            # prennent.
            cut = str(getattr(obj, "HoleCutType", ""))
            blind = str(getattr(obj, "DepthType", "")) == "Dimension"
            return (("Diameter",) + (("Depth",) if blind else ())
                    + (("HoleCutDiameter",) if cut not in ("", "None")
                       else ())
                    + (("HoleCutDepth",) if cut == "Counterbore" else ())
                    + (("HoleCutCountersinkAngle",) if cut == "Countersink"
                       else ()))
        if getattr(obj, "TypeId", "") in self._EXTRUDE_KINDS:
            # Extrusion : la profondeur du côté 2 quand il existe.
            two = str(getattr(obj, "SideType", "")) == "Two sides"
            return self._EDITABLE_PROPS + (("Length2",) if two else ())
        if getattr(obj, "TypeId", "") == "PartDesign::LinearPattern":
            # La deuxième direction n'apparaît que si elle sert.
            two = int(getattr(obj, "Occurrences2", 1) or 1) > 1
            return self._EDITABLE_PROPS + (("Occurrences2",) if two else ())
        if getattr(obj, "TypeId", "") != "PartDesign::Chamfer":
            return self._EDITABLE_PROPS
        kind = self._chamfer_kind(obj)
        if kind == "deux":
            return ("Size", "Size2")
        if kind == "angle":
            return ("Size", "Angle")
        return ("Size",)

    def _has_params(self, obj):
        """Vrai quand ``get_params`` propose au moins une cote : l'arbre le
        dit (``has_params``), le menu « Modifier » le suit."""
        return any(hasattr(obj, prop) for prop in self._editable_props(obj))

    def get_params(self, feature):
        """Editable numeric properties of a feature, with current values.

        ``key`` is the neutral key the UI reads and sends back to
        ``set_params``; ``prop`` (the FreeCAD property) stays during the
        transition, for the engine and the plugins.
        """
        from engine.kernel import KernelError
        from engine.vocab import param_key_for, type_key_for
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        exprs = self._expression_map(obj)
        type_key = type_key_for(obj.TypeId)
        params = []
        for prop in self._editable_props(obj):
            if not hasattr(obj, prop):
                continue
            value = getattr(obj, prop)
            entry = {"key": param_key_for(type_key, prop) or prop,
                     "prop": prop,
                     "value": float(getattr(value, "Value", value))}
            if prop in exprs:
                entry["expr"] = exprs[prop]
            params.append(entry)
        return {"feature": feature, "label": obj.Label, "params": params}

    @staticmethod
    def _valid_identifier(name):
        import re
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)))

    def _varset(self, create=False):
        doc = self._require_doc()
        obj = doc.getObject(self._VARSET_NAME)
        if obj is not None and self._is_internal_tool(obj):
            obj = next((item for item in doc.Objects
                        if item.TypeId == "App::VarSet"
                        and not self._is_internal_tool(item)
                        and item.Label == "Équations"), None)
            if obj is None:
                obj = next((item for item in doc.Objects
                            if item.TypeId == "App::VarSet"
                            and not self._is_internal_tool(item)), None)
        if obj is None and create:
            obj = doc.addObject("App::VarSet", self._VARSET_NAME)
            obj.Label = self._t("Équations")
        return obj

    def _variable_names(self, varset):
        return [p for p in varset.PropertiesList
                if varset.getGroupOfProperty(p) == "Variables"]

    def list_variables(self):
        varset = self._varset()
        if varset is None:
            return {"variables": []}
        return {"variables": [
            {"name": name,
             "value": float(getattr(varset, name))}
            for name in self._variable_names(varset)]}

    def set_variable(self, name, value):
        """Créer ou modifier une variable globale — utilisable ensuite
        dans toute expression : ``Variables.Largeur * 2``."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        name = str(name).strip()
        if not self._valid_identifier(name):
            raise KernelError(
                "nom invalide « {} » — lettres, chiffres et _ seulement, "
                "sans commencer par un chiffre".format(name))
        varset = self._varset(create=True)
        if name not in varset.PropertiesList:
            varset.addProperty("App::PropertyFloat", name, "Variables")
        try:
            setattr(varset, name, float(value))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        self._require_doc().recompute()
        return self.list_variables()

    def delete_variable(self, name):
        from engine.kernel import (
            KernelError,
            _explain,
        )
        varset = self._varset()
        name = str(name).strip()
        if varset is None or name not in self._variable_names(varset):
            raise KernelError("variable inconnue : {}".format(name))
        try:
            varset.removeProperty(name)
        except Exception as exc:  # noqa: BLE001 - encore référencée
            raise KernelError(_explain(exc))
        self._require_doc().recompute()
        return self.list_variables()

    @staticmethod
    def _expression_map(obj):
        """{property path -> expression}, normalized without leading dot."""
        table = {}
        for path, expr in (getattr(obj, "ExpressionEngine", None) or ()):
            table[str(path).lstrip(".")] = str(expr)
        return table
