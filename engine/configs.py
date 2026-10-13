"""Configurations : plusieurs variantes d'une même pièce (cotes, fonctions
désactivées, variables des équations), dont une est active.

Une configuration est un relevé de l'état : la valeur de chaque cote
modifiable (celles sans équation), l'état désactivé de chaque fonction et
la valeur de chaque variable. Passer à une autre configuration enregistre
d'abord l'état courant dans la configuration active, puis applique
l'autre : ce qu'on modifie pendant qu'une configuration est active lui
appartient. Une fonction ajoutée plus tard existe dans toutes, telle
qu'elle est jusqu'à ce qu'une configuration l'enregistre.

Rangées en JSON sur le premier corps (``FreeSolidConfigs``). Les imports
FreeCAD restent dans les méthodes ; ``clean_config_name`` et
``apply_order`` sont testées en CI.
"""

import json


def clean_config_name(name):
    """Nom de configuration nettoyé (1 à 40 caractères), ou None."""
    text = str(name or "").strip()[:40]
    return text or None


def apply_order(snapshot):
    """Clés du relevé dans l'ordre d'application : les variables d'abord
    (les cotes calculées en dépendent), puis les cotes, puis les états
    désactivés."""
    variables = sorted(k for k in snapshot if k.startswith("var:"))
    values = sorted(k for k in snapshot if k.startswith("prop:"))
    flags = sorted(k for k in snapshot if k.startswith("suppressed:"))
    return variables + values + flags


class ConfigsMixin:
    """Ops : list_configurations, add_configuration, activate_configuration,
    rename_configuration, delete_configuration."""

    def _config_holder(self):
        from engine.kernel import KernelError
        doc = self._require_doc()
        for obj in doc.Objects:
            if (obj.TypeId == "PartDesign::Body"
                    and not self._is_internal_tool(obj)):
                return obj
        raise KernelError("les configurations demandent une pièce")

    def _config_data(self):
        raw = getattr(self._config_holder(), "FreeSolidConfigs", "") or ""
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        return {"active": data.get("active"),
                "configs": dict(data.get("configs") or {}),
                "order": list(data.get("order") or [])}

    def _store_configs(self, data):
        holder = self._config_holder()
        if "FreeSolidConfigs" not in holder.PropertiesList:
            holder.addProperty("App::PropertyString", "FreeSolidConfigs",
                               "FreeSolid")
            holder.setEditorMode("FreeSolidConfigs", 2)
        holder.FreeSolidConfigs = json.dumps(data)

    def _snapshot(self):
        """Relevé de l'état courant (voir le docstring du module)."""
        doc = self._require_doc()
        snap = {}
        for obj in doc.Objects:
            if self._is_internal_tool(obj):
                continue
            exprs = dict(obj.ExpressionEngine or [])
            for prop in self._EDITABLE_PROPS:
                if prop not in obj.PropertiesList or prop in exprs:
                    continue
                value = getattr(obj, prop)
                value = getattr(value, "Value", value)
                if isinstance(value, (int, float)) and not isinstance(
                        value, bool):
                    snap["prop:%s.%s" % (obj.Name, prop)] = float(value)
            if "Suppressed" in obj.PropertiesList:
                snap["suppressed:" + obj.Name] = bool(obj.Suppressed)
        for var in self.list_variables()["variables"]:
            snap["var:" + var["name"]] = float(var["value"])
        return snap

    def _apply_snapshot(self, snap):
        doc = self._require_doc()
        varset = self._varset()
        for key in apply_order(snap):
            value = snap[key]
            if key.startswith("var:"):
                name = key[4:]
                if varset is not None and name in varset.PropertiesList:
                    setattr(varset, name, float(value))
                continue
            if key.startswith("suppressed:"):
                obj = doc.getObject(key[len("suppressed:"):])
                if obj is not None and "Suppressed" in obj.PropertiesList:
                    obj.Suppressed = bool(value)
                continue
            name, prop = key[len("prop:"):].rsplit(".", 1)
            obj = doc.getObject(name)
            if (obj is None or prop not in obj.PropertiesList
                    or prop in dict(obj.ExpressionEngine or [])):
                continue
            current = getattr(obj, prop)
            if isinstance(current, int) and not isinstance(current, bool):
                setattr(obj, prop, int(round(value)))
            else:
                setattr(obj, prop, float(value))

    def list_configurations(self):
        data = self._config_data()
        return {"active": data["active"], "names": data["order"]}

    def add_configuration(self, name):
        """Nouvelle configuration, relevée sur l'état courant ; elle devient
        active (l'état courant reste aussi celui de l'ancienne active)."""
        from engine.kernel import KernelError
        clean = clean_config_name(name)
        if clean is None:
            raise KernelError("donnez un nom à la configuration")
        data = self._config_data()
        if clean in data["configs"]:
            raise KernelError("la configuration « {} » existe déjà".format(
                clean))
        snap = self._snapshot()
        if data["active"] in data["configs"]:
            data["configs"][data["active"]] = snap
        data["configs"][clean] = snap
        data["order"].append(clean)
        data["active"] = clean
        self._store_configs(data)
        return self._current_tree()

    def activate_configuration(self, name):
        """Passe à la configuration ``name`` : l'état courant est d'abord
        enregistré dans la configuration active."""
        from engine.kernel import KernelError
        data = self._config_data()
        if name not in data["configs"]:
            raise KernelError("configuration inconnue : {}".format(name))
        if data["active"] in data["configs"]:
            data["configs"][data["active"]] = self._snapshot()
        data["active"] = name
        self._store_configs(data)
        self._apply_snapshot(data["configs"][name])
        try:
            self._recompute()
        except KernelError:
            pass  # les erreurs restent visibles dans l'arbre
        return self._current_tree()

    def rename_configuration(self, name, new_name):
        from engine.kernel import KernelError
        clean = clean_config_name(new_name)
        data = self._config_data()
        if name not in data["configs"] or clean is None:
            raise KernelError("configuration inconnue : {}".format(name))
        if clean != name and clean in data["configs"]:
            raise KernelError("la configuration « {} » existe déjà".format(
                clean))
        data["configs"][clean] = data["configs"].pop(name)
        data["order"] = [clean if n == name else n for n in data["order"]]
        if data["active"] == name:
            data["active"] = clean
        self._store_configs(data)
        return self._current_tree()

    def configuration_table(self):
        """Tableau des cotes par configuration : une ligne par cote
        relevée (et par variable), une valeur par configuration. L'état
        courant compte pour la configuration active."""
        from engine.vocab import label_for_type
        doc = self._require_doc()
        data = self._config_data()
        configs = dict(data["configs"])
        if data["active"] in configs:
            configs[data["active"]] = self._snapshot()
        keys = []
        for name in data["order"]:
            for key in configs[name]:
                if not key.startswith("suppressed:") and key not in keys:
                    keys.append(key)
        rows = []
        for key in keys:
            prop = None
            if key.startswith("var:"):
                label = key[4:]
            else:
                obj_name, prop = key[len("prop:"):].rsplit(".", 1)
                obj = doc.getObject(obj_name)
                if obj is None:
                    continue
                label = obj.Label
            rows.append({"key": key, "label": label, "prop": prop,
                         "values": {n: configs[n].get(key)
                                    for n in data["order"]}})
        return {"names": data["order"], "active": data["active"],
                "rows": rows}

    def set_configuration_values(self, values):
        """Modifie le tableau : ``values`` = {configuration: {clé: valeur}}.
        La configuration active est appliquée tout de suite."""
        from engine.kernel import KernelError
        data = self._config_data()
        if data["active"] in data["configs"]:
            data["configs"][data["active"]] = self._snapshot()
        for name, changes in (values or {}).items():
            if name not in data["configs"]:
                raise KernelError("configuration inconnue : {}".format(name))
            for key, value in (changes or {}).items():
                if key not in data["configs"][name]:
                    raise KernelError("cote inconnue : {}".format(key))
                data["configs"][name][key] = float(value)
        self._store_configs(data)
        if data["active"] in data["configs"]:
            self._apply_snapshot(data["configs"][data["active"]])
            self._recompute()
        return self._current_tree()

    def delete_configuration(self, name):
        """Retire une configuration ; la pièce garde son état courant."""
        from engine.kernel import KernelError
        data = self._config_data()
        if name not in data["configs"]:
            raise KernelError("configuration inconnue : {}".format(name))
        del data["configs"][name]
        data["order"] = [n for n in data["order"] if n != name]
        if data["active"] == name:
            # Aucune active : le prochain changement n'écrase personne.
            data["active"] = None
        self._store_configs(data)
        return self._current_tree()
