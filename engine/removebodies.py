"""Supprimer des corps : une fonction d'historique qui ôte des corps de la
pièce à partir de son rang, ou ne garde que ceux qu'on a choisis.

Les corps restent dans le document avec leur histoire : reculer la barre
au-dessus de la fonction les fait revenir, la supprimer aussi. Trois
sortes de cibles :

- un corps entier ou une surface : ni dessiné, ni dans les dossiers, ni
  visé, tant que la fonction n'est pas reculée ;
- un des solides d'un corps qui en garde plusieurs : une étape cachée
  dans ce corps, au rang de la fonction, l'ôte de la forme — les
  fonctions suivantes du corps ne le voient plus. Le solide y est reconnu
  à l'origine de ses faces (``engine/bodysolids.py``) ; l'étape est un
  booléen d'intersection avec une forme recalculée à chaque
  reconstruction, comme « Supprimer la face ».

La fonction est un objet de document (``App::DocumentObject``) qui porte
ses cibles en JSON (``FreeSolidRemoveBodies``).

Les fonctions du module se testent sans FreeCAD ; les méthodes du mixin
importent le noyau à l'appel.
"""

import json

REMOVE_PROP = "FreeSolidRemoveBodies"

#: Libellé de la fonction selon le mode.
REMOVE_LABELS = {False: "Supprimer des corps", True: "Garder des corps"}


def removal_plan(chosen, alive, keep=False):
    """Ce que la fonction ôte de la pièce.

    ``chosen`` : ``[{"name", "solid"?}]`` — un corps (entier, ou l'un de
    ses solides) ou une surface. ``alive`` : ``{"bodies": {nom: nombre de
    solides}, "surfaces": [noms]}``, ce qui existe au rang de la fonction.
    ``keep`` : ôter tout le reste. Retour : ``{"bodies": [...], "solids":
    {corps: [rangs]}, "surfaces": [...]}`` ; un corps dont tous les solides
    partent part en entier.
    """
    whole = set()
    parts = {}
    surfaces = set()
    for target in chosen:
        name = target["name"]
        if name in alive["bodies"]:
            if target.get("solid") is None:
                whole.add(name)
            else:
                parts.setdefault(name, set()).add(int(target["solid"]))
        else:
            surfaces.add(name)
    bodies = []
    solids = {}
    for name, count in alive["bodies"].items():
        if keep:
            gone = ([] if name in whole else
                    [i for i in range(count) if i not in parts.get(name, ())])
        else:
            gone = (list(range(count)) if name in whole
                    else sorted(parts.get(name, ())))
        if len(gone) >= count:
            bodies.append(name)
        elif gone:
            solids[name] = gone
    if keep:
        removed = [s for s in alive["surfaces"] if s not in surfaces]
    else:
        removed = [s for s in alive["surfaces"] if s in surfaces]
    return {"bodies": bodies, "solids": solids, "surfaces": removed}


def doomed_solids(origins, key_sets):
    """Rangs des solides qu'une étape cachée ôte : pour chaque solide
    retenu (ses origines), celui ou ceux qui en partagent le plus — les
    deux moitiés d'un solide coupé après coup partent ensemble."""
    doomed = set()
    for keys in key_sets:
        wanted = set(keys)
        scores = [len(wanted & found) for found in origins]
        best = max(scores, default=0)
        if best:
            doomed.update(i for i, score in enumerate(scores)
                          if score == best)
    return doomed


class RemoveBodiesMixin:
    """Op : supprimer des corps (fonction d'historique)."""

    def _removal_hosts(self):
        return [o for o in self._require_doc().Objects
                if REMOVE_PROP in o.PropertiesList]

    @staticmethod
    def _removal_spec(host):
        try:
            spec = json.loads(getattr(host, REMOVE_PROP, "") or "")
        except (TypeError, ValueError):
            return {}
        return spec if isinstance(spec, dict) else {}

    def _removed_names(self):
        """Corps et surfaces ôtés à la position de la barre : par une
        suppression, ou fondus dans un autre corps (``_absorbed_bodies``)."""
        names = set(self._absorbed_bodies())
        for host in self._removal_hosts():
            if self._is_rolled_back(host):
                continue
            spec = self._removal_spec(host)
            names.update(spec.get("bodies") or ())
            names.update(spec.get("surfaces") or ())
        return names

    def _removal_parts(self, host):
        """Étapes cachées d'une fonction, une par corps dont elle ôte des
        solides."""
        return [o for o in self._require_doc().Objects
                if getattr(o, "FreeSolidRemoveof", "") == host.Name]

    def _alive_inventory(self, removed=None):
        """Ce qui existe à la barre : ``{"bodies": {nom: solides},
        "surfaces": [noms], "tips": {nom: fonction}}``, dans l'ordre du
        document — ``tips`` : la fonction où chaque corps s'arrête."""
        removed = self._removed_names() if removed is None else removed
        tips = {body.Name: getattr(body, "Tip", None)
                for body in self._history_bodies()
                if body.Name not in removed}
        consumed = self._consumed_surfaces()
        surfaces = [o.Name for o in self._require_doc().Objects
                    if self._is_surface_obj(o)
                    and not self._is_internal_tool(o)
                    and not self._is_rolled_back(o)
                    and o.Name not in consumed and o.Name not in removed]
        return self._inventory(tips, surfaces)

    def _rank_inventory(self, host):
        """Ce qui existe juste avant ``host``, où que soit la barre :
        chaque corps arrêté à sa dernière fonction de rang inférieur, sans
        ce qu'ôtent les suppressions d'avant. Même forme que
        ``_alive_inventory``."""
        doc = self._require_doc()
        order_of = self._tree_order()
        rank = order_of.get(host.Name, -1)
        last = {}
        for row in self._history_rows(self._history_lines()):
            body = row.get("body")
            if (row["role"] == "feature" and body and row["order"] < rank
                    and row["order"] >= last.get(body, (-1, None))[0]):
                last[body] = (row["order"], row["name"])
        removed = set()
        for other in self._removal_hosts():
            if order_of.get(other.Name, -1) < rank:
                spec = self._removal_spec(other)
                removed.update(spec.get("bodies") or ())
                removed.update(spec.get("surfaces") or ())
        # Les corps fondus dans un autre avant ce rang (``_absorbed_bodies``
        # à la barre) : un combiner actif, outils lâchés sous la barre
        # compris.
        for body in self._history_bodies():
            for obj in body.Group:
                if (obj.TypeId == "PartDesign::Boolean"
                        and not getattr(obj, "Suppressed", False)
                        and order_of.get(obj.Name, -1) < rank):
                    removed.update(t.Name for t in self._boolean_tools(obj))
        tips = {body.Name: doc.getObject(last[body.Name][1])
                for body in self._history_bodies()
                if body.Name in last and body.Name not in removed}

        def before(obj):
            return order_of.get(obj.Name, -1) < rank

        consumed = self._consumed_surfaces(counts=before)
        surfaces = [o.Name for o in doc.Objects
                    if self._is_surface_obj(o)
                    and not self._is_internal_tool(o) and before(o)
                    and o.Name not in consumed and o.Name not in removed]
        return self._inventory(tips, surfaces)

    @staticmethod
    def _inventory(tips, surfaces):
        """Les corps qui ont de la matière à leur fonction ``tips``."""
        bodies = {}
        kept = {}
        for name, tip in tips.items():
            shape = getattr(tip, "Shape", None)
            if shape is None or shape.isNull() or not shape.Solids:
                continue
            bodies[name] = len(shape.Solids)
            kept[name] = tip
        return {"bodies": bodies, "surfaces": surfaces, "tips": kept}

    def _removal_host(self, feature):
        from engine.kernel import KernelError
        host = self._require_doc().getObject(str(feature))
        if host is None or REMOVE_PROP not in host.PropertiesList:
            raise KernelError("fonction inconnue : {}".format(feature))
        return host

    @staticmethod
    def _removal_chosen(targets, alive):
        """Cibles reçues → ``[{"name", "solid"?}]``, vérifiées contre ce
        qui existe (``alive``)."""
        from engine.kernel import KernelError
        if not isinstance(targets, (list, tuple)):
            raise KernelError("targets doit être une liste de corps")
        chosen = []
        for target in targets:
            name = str((target or {}).get("name") or "")
            solid = (target or {}).get("solid")
            if name not in alive["bodies"] and name not in alive["surfaces"]:
                raise KernelError(
                    "corps inconnu ou déjà supprimé : {}".format(name))
            if solid is not None and not (
                    name in alive["bodies"]
                    and 0 <= int(solid) < alive["bodies"][name]):
                raise KernelError("solide inconnu : {}".format(solid))
            chosen.append({"name": name} if solid is None
                          else {"name": name, "solid": int(solid)})
        if not chosen:
            raise KernelError("cochez au moins un corps à supprimer")
        return chosen

    @staticmethod
    def _checked_plan(chosen, alive, keep):
        from engine.kernel import KernelError
        plan = removal_plan(chosen, alive, bool(keep))
        if not (plan["bodies"] or plan["solids"] or plan["surfaces"]):
            raise KernelError("rien à supprimer : tous les corps sont gardés")
        if alive["bodies"] and not set(alive["bodies"]) - set(plan["bodies"]):
            raise KernelError("gardez au moins un corps volumique")
        return plan

    def add_remove_bodies(self, targets, keep=False):
        """Supprimer des corps de la pièce à partir d'ici (``keep`` : ne
        garder qu'eux). ``targets`` : ``[{"name": corps ou surface,
        "solid": rang?}]`` — ``solid`` vise un seul des solides d'un corps
        qui en garde plusieurs. Reculer la barre au-dessus de la fonction,
        ou la supprimer, les rend."""
        from engine.kernel import KernelError
        alive = self._alive_inventory()
        chosen = self._removal_chosen(targets, alive)
        plan = self._checked_plan(chosen, alive, keep)
        doc = self._require_doc()
        host = doc.addObject("App::DocumentObject", "RemoveBodies")
        host.Label = self._t(REMOVE_LABELS[bool(keep)])
        host.addProperty("App::PropertyString", REMOVE_PROP, "FreeSolid",
                         "Corps supprimés (JSON)")
        try:
            self._write_removal(host, chosen, plan, keep, alive["tips"])
            self._recompute()
        except KernelError:
            self._drop_removal(host)
            self._recompute()
            raise
        self._keep_active_body()
        return self.get_tree()

    def remove_bodies_info(self, feature):
        """Le panneau d'une suppression à rééditer : ce qui existe juste
        avant elle, une case par solide, corps ou surface, cochée selon
        ce qu'elle vise (``checked``), et son mode (``keep``)."""
        host = self._removal_host(feature)
        state = self._rank_inventory(host)
        spec = self._removal_spec(host)
        targets = [t for t in spec.get("targets") or ()
                   if isinstance(t, dict) and t.get("name")]
        doc = self._require_doc()
        candidates = []
        for name, count in state["bodies"].items():
            body, tip = doc.getObject(name), state["tips"][name]
            mine = [t for t in targets if t["name"] == name]
            whole = any(not t.get("keys") for t in mine)
            key_sets = [t["keys"] for t in mine if t.get("keys")]
            checked = (set(range(count)) if whole else doomed_solids(
                self._feature_solid_origins(tip), key_sets)
                if key_sets else set())
            if count < 2:
                candidates.append({"name": name, "checked": 0 in checked,
                                   "label": self._body_title(body, tip)})
                continue
            rows = self._body_solids(body, tip)
            for index in range(count):
                candidates.append({
                    "name": name, "solid": index, "checked": index in checked,
                    "label": rows[index]["label"] if index < len(rows)
                    else self._body_title(body, tip)})
        for name in state["surfaces"]:
            candidates.append({
                "name": name, "surface": True,
                "label": doc.getObject(name).Label,
                "checked": any(t["name"] == name for t in targets)})
        return {"feature": host.Name, "label": host.Label,
                "keep": bool(spec.get("keep")), "candidates": candidates}

    def edit_remove_bodies(self, feature, targets, keep=False):
        """Changer les cibles ou le mode d'une suppression, à son rang :
        les étapes cachées qui ne servent plus partent, celles qui
        manquent s'insèrent dans leur corps à la place de la fonction."""
        host = self._removal_host(feature)
        state = self._rank_inventory(host)
        chosen = self._removal_chosen(targets, state)
        plan = self._checked_plan(chosen, state, keep)
        before = bool(self._removal_spec(host).get("keep"))
        if host.Label in (REMOVE_LABELS[before],
                          self._t(REMOVE_LABELS[before])):
            # Nom par défaut : il suit le mode ; un nom choisi reste.
            host.Label = self._t(REMOVE_LABELS[bool(keep)])
        self._write_removal(host, chosen, plan, keep, state["tips"])
        self._recompute()
        self._keep_active_body()
        return self.get_tree()

    def _write_removal(self, host, chosen, plan, keep, tips):
        """Pose ce que ``host`` vise et ses étapes cachées : une par corps
        dont ``plan`` ôte des solides, insérée après la fonction où ce
        corps s'arrête (``tips``) ; celles qui ne servent plus partent.
        Un solide visé est retenu par l'origine de ses faces."""
        doc = self._require_doc()
        origins = {}

        def origins_of(name):
            if name not in origins:
                origins[name] = self._feature_solid_origins(tips[name])
            return origins[name]

        targets = [{"name": t["name"],
                    "keys": sorted(origins_of(t["name"])[t["solid"]])}
                   if "solid" in t else {"name": t["name"]} for t in chosen]
        setattr(host, REMOVE_PROP, json.dumps({
            "keep": bool(keep),
            "chosen": self._removal_target_labels(chosen, tips),
            "targets": targets,
            "bodies": plan["bodies"], "surfaces": plan["surfaces"]}))
        parts = {}
        for part in self._removal_parts(host):
            body = part.getParentGeoFeatureGroup()
            if body is None or body.Name not in plan["solids"]:
                self._drop_removal_part(part)
            else:
                parts[body.Name] = part
        for name, indices in plan["solids"].items():
            key_sets = [sorted(origins_of(name)[i]) for i in indices]
            if name in parts:
                for frozen in self._removal_frozen(parts[name]):
                    frozen.FreeSolidRemovekeys = json.dumps(key_sets)
            else:
                self._add_removal_part(host, doc.getObject(name), key_sets,
                                       tips[name])

    def _removal_target_labels(self, chosen, tips):
        """Les noms que la ligne de l'arbre rappelle : ceux du dossier au
        rang de la fonction."""
        doc = self._require_doc()
        labels = []
        for target in chosen:
            obj = doc.getObject(target["name"])
            tip = tips.get(target["name"])
            if "solid" in target:
                rows = self._body_solids(obj, tip)
                labels.append(rows[target["solid"]]["label"]
                              if target["solid"] < len(rows)
                              else self._body_title(obj, tip))
            elif obj.TypeId == "PartDesign::Body":
                labels.append(self._body_title(obj, tip))
            else:
                labels.append(obj.Label)
        return labels

    def _add_removal_part(self, host, body, key_sets, base):
        """L'étape cachée qui ôte de ``body`` les solides retenus par
        ``key_sets``, juste après ``base`` : la pointe y passe le temps de
        l'insertion — les fonctions suivantes du corps se rebranchent
        dessus — puis revient."""
        result = self._removal_result(base, key_sets)
        previous, tip = self._body, body.Tip
        self._body = body
        body.Tip = base
        try:
            self._commit_frozen(base, result,
                                {"removekeys": json.dumps(key_sets)},
                                REMOVE_LABELS[False], {"removeof": host.Name})
            part = body.Tip
        finally:
            self._body = previous
            if tip is not base:
                body.Tip = tip
        part.Label = "{} · {}".format(host.Label, body.Label)
        part.addProperty("App::PropertyBool", self._THIN_HELPER, "FreeSolid",
                         "Étape cachée d'une suppression de corps")
        setattr(part, self._THIN_HELPER, True)
        part.addProperty("App::PropertyString", "FreeSolidThinOwner",
                         "FreeSolid", "Fonction propriétaire")
        part.FreeSolidThinOwner = host.Name

    def _removal_result(self, base, key_sets):
        """La forme de ``base`` sans les solides retenus."""
        import Part
        from engine.kernel import KernelError
        origins = self._feature_solid_origins(base)
        doomed = doomed_solids(origins, key_sets)
        kept = [s for i, s in enumerate(base.Shape.Solids) if i not in doomed]
        if not kept:
            raise KernelError("le corps n'aurait plus de solide — "
                              "supprimez-le en entier")
        return kept[0] if len(kept) == 1 else Part.makeCompound(kept)

    @staticmethod
    def _removal_frozen(part):
        """Les formes calculées d'une étape cachée (corps outils)."""
        frozen = []
        for tool in getattr(part, "Group", None) or ():
            base = getattr(tool, "BaseFeature", None)
            if base is not None and "FreeSolidRemovekeys" in base.PropertiesList:
                frozen.append(base)
        return frozen

    @staticmethod
    def _solids_signature(shape):
        def one(solid):
            center = solid.CenterOfMass
            return tuple(round(v, 6) for v in (
                solid.Volume, solid.Area, center.x, center.y, center.z))
        return sorted(one(solid) for solid in shape.Solids)

    def _refresh_removals(self):
        """Après une reconstruction : la forme de chaque étape cachée suit
        ce que le corps a juste avant elle ; vrai si l'une a changé."""
        changed = False
        for part in self._require_doc().Objects:
            if not getattr(part, "FreeSolidRemoveof", ""):
                continue
            base = getattr(part, "BaseFeature", None)
            if base is None or getattr(base, "Shape", None) is None:
                continue
            for frozen in self._removal_frozen(part):
                try:
                    result = self._removal_result(
                        base, json.loads(frozen.FreeSolidRemovekeys or "[]"))
                except Exception:  # noqa: BLE001 — l'ancienne forme reste
                    continue
                old = frozen.Shape
                if (old.isNull() or self._solids_signature(old)
                        != self._solids_signature(result)):
                    frozen.Shape = result
                    changed = True
        return changed

    def _drop_removal_part(self, part):
        """Retire une étape cachée (booléen, forme et corps outil) ; le
        corps se rebranche sur ce qu'elle avait avant elle."""
        doc = self._require_doc()
        body = part.getParentGeoFeatureGroup()
        base = getattr(part, "BaseFeature", None)
        tools = list(getattr(part, "Group", None) or [])
        if body is not None and body.Tip is part:
            body.Tip = base
        self._relink_chain(body, [part], base)
        doc.removeObject(part.Name)
        for tool in tools:
            names = [o.Name for o in getattr(tool, "Group", None) or []]
            frozen = getattr(tool, "BaseFeature", None)
            if frozen is not None:
                names.append(frozen.Name)
            doc.removeObject(tool.Name)
            for name in names:
                if doc.getObject(name) is not None:
                    doc.removeObject(name)

    def _drop_removal(self, host):
        """Retire la fonction et ses étapes cachées."""
        for part in self._removal_parts(host):
            self._drop_removal_part(part)
        self._require_doc().removeObject(host.Name)

    def _keep_active_body(self):
        """Le corps actif n'est jamais un corps supprimé : on passe au
        corps où il est fondu, sinon au premier corps qui reste."""
        removed = self._removed_names()
        if self._body is None or self._body.Name not in removed:
            return
        absorbed = self._absorbed_bodies()
        host = absorbed.get(self._body.Name)
        seen = set()
        while (host is not None and host.Name in removed
               and host.Name not in seen):
            seen.add(host.Name)
            host = absorbed.get(host.Name)
        if host is not None and host.Name not in removed:
            self._body = host
            return
        for body in self._history_bodies():
            if body.Name not in removed:
                self._body = body
                return

    def _removal_rows(self, entry):
        """Lignes d'arbre des suppressions de corps, avec les noms qu'elles
        ôtent (``removes``) et leur mode (``keep``)."""
        rows = []
        for host in self._removal_hosts():
            spec = self._removal_spec(host)
            item = entry(host)
            item["kind"] = self._t(REMOVE_LABELS[bool(spec.get("keep"))])
            item["removes"] = list(spec.get("chosen") or ())
            item["keep"] = bool(spec.get("keep"))
            item["rolled_back"] = self._is_rolled_back(host)
            parts = self._removal_parts(host)
            if any("Invalid" in (part.State or ()) for part in parts):
                item["error"] = True
            rows.append(item)
        return rows
