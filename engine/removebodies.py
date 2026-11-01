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
        """Corps et surfaces ôtés à la position de la barre."""
        names = set()
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
        "surfaces": [noms]}``, dans l'ordre du document."""
        removed = self._removed_names() if removed is None else removed
        bodies = {}
        for body in self._history_bodies():
            shape = getattr(body, "Shape", None)
            if (body.Name in removed or getattr(body, "Tip", None) is None
                    or shape is None or shape.isNull() or not shape.Solids):
                continue
            bodies[body.Name] = len(shape.Solids)
        consumed = self._consumed_surfaces()
        surfaces = [o.Name for o in self._require_doc().Objects
                    if self._is_surface_obj(o)
                    and not self._is_internal_tool(o)
                    and not self._is_rolled_back(o)
                    and o.Name not in consumed and o.Name not in removed]
        return {"bodies": bodies, "surfaces": surfaces}

    def add_remove_bodies(self, targets, keep=False):
        """Supprimer des corps de la pièce à partir d'ici (``keep`` : ne
        garder qu'eux). ``targets`` : ``[{"name": corps ou surface,
        "solid": rang?}]`` — ``solid`` vise un seul des solides d'un corps
        qui en garde plusieurs. Reculer la barre au-dessus de la fonction,
        ou la supprimer, les rend."""
        from engine.kernel import KernelError
        if not isinstance(targets, (list, tuple)):
            raise KernelError("targets doit être une liste de corps")
        alive = self._alive_inventory()
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
        plan = removal_plan(chosen, alive, bool(keep))
        if not (plan["bodies"] or plan["solids"] or plan["surfaces"]):
            raise KernelError("rien à supprimer : tous les corps sont gardés")
        if alive["bodies"] and not set(alive["bodies"]) - set(plan["bodies"]):
            raise KernelError("gardez au moins un corps volumique")
        doc = self._require_doc()
        host = doc.addObject("App::DocumentObject", "RemoveBodies")
        host.Label = self._t(REMOVE_LABELS[bool(keep)])
        labels = self._removal_target_labels(chosen)
        host.addProperty("App::PropertyString", REMOVE_PROP, "FreeSolid",
                         "Corps supprimés (JSON)")
        setattr(host, REMOVE_PROP, json.dumps({
            "keep": bool(keep), "chosen": labels,
            "bodies": plan["bodies"], "surfaces": plan["surfaces"]}))
        try:
            for name, indices in plan["solids"].items():
                self._add_removal_part(host, doc.getObject(name), indices)
            self._recompute()
        except KernelError:
            self._drop_removal(host)
            self._recompute()
            raise
        self._keep_active_body()
        return self.get_tree()

    def _removal_target_labels(self, chosen):
        """Les noms que la ligne de l'arbre rappelle : ceux du dossier."""
        doc = self._require_doc()
        labels = []
        for target in chosen:
            obj = doc.getObject(target["name"])
            if "solid" in target:
                rows = self._body_solids(obj)
                labels.append(rows[target["solid"]]["label"]
                              if target["solid"] < len(rows)
                              else self._body_title(obj))
            elif obj.TypeId == "PartDesign::Body":
                labels.append(self._body_title(obj))
            else:
                labels.append(obj.Label)
        return labels

    def _add_removal_part(self, host, body, indices):
        """L'étape cachée qui ôte ``indices`` (rangs de solides) de
        ``body``, après sa pointe."""
        origins = self._solid_origins(body)
        key_sets = [sorted(origins[i]) for i in indices]
        tip = body.Tip
        result = self._removal_result(tip, key_sets)
        stamps = {"removebase": tip.Name, "removekeys": json.dumps(key_sets)}
        previous = self._body
        self._body = body
        try:
            self._commit_frozen(tip, result, stamps, REMOVE_LABELS[False],
                                {"removeof": host.Name})
        finally:
            self._body = previous
        part = body.Tip
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

    def _refresh_removals(self):
        """Après une reconstruction : la forme de chaque étape cachée suit
        sa base ; vrai si l'une a changé."""
        doc = self._require_doc()
        changed = False
        for obj in doc.Objects:
            base_name = getattr(obj, "FreeSolidRemovebase", "")
            if not base_name:
                continue
            base = doc.getObject(base_name)
            if base is None or getattr(base, "Shape", None) is None:
                continue
            try:
                result = self._removal_result(
                    base, json.loads(obj.FreeSolidRemovekeys or "[]"))
            except Exception:  # noqa: BLE001 — l'ancienne forme reste
                continue
            old = obj.Shape
            if (old.isNull() or len(old.Solids) != len(result.Solids)
                    or abs(old.Volume - result.Volume) > 1e-9
                    or abs(old.Area - result.Area) > 1e-9):
                obj.Shape = result
                changed = True
        return changed

    def _drop_removal(self, host):
        """Retire la fonction et ses étapes cachées (booléen, forme et
        corps outil)."""
        doc = self._require_doc()
        for part in self._removal_parts(host):
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
        doc.removeObject(host.Name)

    def _keep_active_body(self):
        """Le corps actif n'est jamais un corps supprimé : on passe au
        premier corps qui reste."""
        removed = self._removed_names()
        if self._body is None or self._body.Name not in removed:
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
