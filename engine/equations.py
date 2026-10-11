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

    _VARSET_NAME = "Variables"


    def set_param(self, feature, prop, value):
        """Set one property on one feature by internal name, and recompute.

        This is the whole parametric promise in one operation: the UI edits
        ``Pad.Length`` and the part rebuilds. Même atomicité que
        ``set_params`` : un refus ne modifie pas la pièce.
        """
        return self.set_params(feature, {str(prop): value})

    def set_params(self, feature, values):
        """Set several properties at once, one recompute — the edit panel
        applies (and previews) its whole form atomically.

        A value may be a number, or a string: a numeric string is a
        number, anything else is an **expression** (``2*Largeur + 5``) —
        an equation, via the expression engine.
        """
        from engine.kernel import (
            KernelError,
            _explain,
            parse_user_number,
        )
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if not isinstance(values, dict):
            raise KernelError("values doit être un objet JSON")
        # Atomicité : une expression était stockée AVANT que le recompute
        # ne la valide — un identifiant inconnu (« _ ») laissait la pièce
        # Invalid pour toujours (barre bloquée, cascade « Tool shape is
        # null »). On mémorise l'état pour tout restaurer sur refus.
        exprs_before = dict(obj.ExpressionEngine or [])
        previous = []  # (prop, ancienne expression ou None, ancienne valeur)
        editable = self._EDITABLE_PROPS
        thin = self._thin_spec(obj) is not None
        revolved = obj.TypeId in (
            "PartDesign::Revolution", "PartDesign::Groove")
        if obj.TypeId == "PartDesign::Chamfer":
            editable = editable + ("Size2", "ChamferType", "FlipDirection")
        if revolved:
            editable = editable + ("Reversed", "Midplane", "axis")
        for prop, value in values.items():
            prop = str(prop)
            if prop not in editable:
                raise KernelError("propriété non éditable : {}".format(prop))
            if prop == "axis":
                profile = self._as_object(getattr(obj, "Profile", None))
                if profile is None:
                    self._restore_props(obj, previous)
                    raise KernelError("l'axe de révolution doit être une ligne")
                token = str(value).strip() if value is not None else ""
                try:
                    reference = self._revolution_reference(profile, token)
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
                    obj.Label, prop))
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
        if getattr(obj, "TypeId", "") != "PartDesign::Chamfer":
            return self._EDITABLE_PROPS
        kind = self._chamfer_kind(obj)
        if kind == "deux":
            return ("Size", "Size2")
        if kind == "angle":
            return ("Size", "Angle")
        return ("Size",)

    def get_params(self, feature):
        """Editable numeric properties of a feature, with current values."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        exprs = self._expression_map(obj)
        params = []
        for prop in self._editable_props(obj):
            if not hasattr(obj, prop):
                continue
            value = getattr(obj, prop)
            entry = {"prop": prop,
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
