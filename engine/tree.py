"""Arbre de création, barre de retour et tessellation.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class TreeMixin:
    # -- arbre et tessellation --------------------------------------------

    def reorder_feature(self, feature, target, after=False):
        """Déplacer une fonction (avec ses esquisses) avant ou après une
        autre, par glisser-déposer dans l'arbre. Refusé si l'arbre ne se
        reconstruit plus (une fonction viendrait avant ce dont elle
        dépend) : la transaction est alors annulée."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        moved = doc.getObject(str(feature))
        anchor = doc.getObject(str(target))
        members = list(body.Group)
        if moved not in members or anchor not in members:
            raise KernelError("réordonner : fonction inconnue dans ce corps")
        if moved is anchor:
            return self.get_tree()
        consumed = self._consumed_sketches()
        # La fonction voyage avec ses esquisses ; « avant » une fonction,
        # c'est avant ses esquisses à elle aussi.
        # Une paroi mince fermée a sa cavité *après* elle : le groupe garde
        # l'ordre du corps, et « après » une fonction, c'est après sa cavité.
        group = [o for o in members if consumed.get(o.Name) == moved.Name
                 or o is moved]
        if anchor in group:
            return self.get_tree()
        anchor_group = [o for o in members
                        if consumed.get(o.Name) == anchor.Name or o is anchor]
        anchor = anchor_group[-1] if after else anchor_group[0]
        tip_at_end = body.Tip is not None and body.Tip is self._last_body_feature()
        for obj in group:
            body.removeObject(obj)
        if after:
            for obj in reversed(group):
                body.insertObject(obj, anchor, True)
        else:
            for obj in group:
                body.insertObject(obj, anchor, False)
        if tip_at_end:
            last = self._last_body_feature()
            if last is not None:
                body.Tip = last
        # Chaque objet doit venir après ce qu'il référence dans le corps
        # (esquisse posée sur une face, habillage sur des arêtes…). Le
        # chaînage BaseFeature, lui, est refait par FreeCAD.
        order = {o.Name: i for i, o in enumerate(body.Group)}
        for obj in body.Group:
            base = getattr(obj, "BaseFeature", None)
            for dep in getattr(obj, "OutList", ()):
                if dep is base or dep.Name not in order:
                    continue
                if order[dep.Name] > order[obj.Name]:
                    raise KernelError(
                        "réordonner : « {} » dépend de « {} », qui viendrait "
                        "après".format(obj.Label, dep.Label))
        doc.recompute()
        broken = [o.Label for o in body.Group if "Invalid" in (o.State or ())]
        if broken:
            raise KernelError(
                "réordonner : l'arbre ne se reconstruit plus ({}) — une "
                "fonction viendrait avant ce dont elle dépend".format(
                    ", ".join(broken)))
        return self.get_tree()

    def _last_body_feature(self):
        """Dernière fonction solide du corps (hors esquisses et plans)."""
        body = self._require_body()
        for obj in reversed(list(body.Group)):
            if obj.isDerivedFrom("PartDesign::Feature"):
                return obj
        return None

    def _consumed_sketches(self):
        """Esquisse → nom du parent (fonction PartDesign ou surface)."""
        body = self._require_body()
        consumed = {}
        for obj in body.Group:
            owner = getattr(obj, "FreeSolidThinOwner", "")
            if owner:
                # Objet caché de paroi mince : il voyage avec sa fonction ;
                # la cavité (un enlèvement) ne consomme pas l'esquisse.
                consumed[obj.Name] = owner
                continue
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            chain, source = self._thin_chain(obj)
            for helper in chain:   # voyagent avec la fonction (réordonner)
                consumed[helper.Name] = obj.Name
            if source is not None:
                linked = source
            if linked is not None:
                # Esquisse partagée : elle voyage avec sa première fonction.
                consumed.setdefault(linked.Name, obj.Name)
        for obj in self._doc.Objects:
            if not self._is_surface_obj(obj):
                continue
            for sk in self._surface_sketch_objects(obj):
                consumed.setdefault(sk.Name, obj.Name)
        return consumed

    def _is_rolled_back(self, obj):
        from engine.kernel import _ROLLED_BACK_PROP
        return bool(getattr(obj, _ROLLED_BACK_PROP, False))

    def _set_rolled_back(self, obj, rolled):
        """Pose le flag (source de vérité) et miroir ``Visibility``."""
        from engine.kernel import _ROLLED_BACK_PROP
        rolled = bool(rolled)
        if _ROLLED_BACK_PROP not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", _ROLLED_BACK_PROP,
                            "FreeSolid", "Reculé par la barre de retour")
        setattr(obj, _ROLLED_BACK_PROP, rolled)
        if hasattr(obj, "Visibility"):
            obj.Visibility = not rolled

    def _history_kind(self, obj, consumed):
        """``feature`` / ``sketch`` / ``surface``, ou None si hors historique."""
        if self._is_thin_helper(obj):
            return None
        if self._is_surface_obj(obj):
            return "surface"
        if obj.TypeId == "Sketcher::SketchObject":
            return None if obj.Name in consumed else "sketch"
        if obj.isDerivedFrom("PartDesign::Feature"):
            return "feature"
        return None

    def _history_lines(self):
        """Lignes d'historique top-niveau, triées par index dans le document."""
        doc = self._require_doc()
        body = self._require_body()
        consumed = self._consumed_sketches()
        lines = []
        for obj in body.Group:
            kind = self._history_kind(obj, consumed)
            if kind in ("feature", "sketch"):
                lines.append(obj)
        for obj in doc.Objects:
            if (self._is_surface_obj(obj)
                    and not self._is_internal_tool(obj)):
                lines.append(obj)
        order_of = {o.Name: i for i, o in enumerate(doc.Objects)}
        lines.sort(key=lambda o: order_of.get(o.Name, -1))
        return lines

    def _history_rows(self, lines=None):
        doc = self._require_doc()
        consumed = self._consumed_sketches()
        order_of = {o.Name: i for i, o in enumerate(doc.Objects)}
        rows = []
        for obj in (lines if lines is not None else self._history_lines()):
            kind = self._history_kind(obj, consumed)
            if kind is None:
                continue
            rows.append({
                "name": obj.Name,
                "order": order_of.get(obj.Name, -1),
                "kind": kind,
            })
        return rows

    def _apply_rollback_flags(self, flags):
        """Applique ``flags`` (nom → reculé) aux surfaces, esquisses libres
        et esquisses sources des surfaces reculées."""
        doc = self._require_doc()
        for name, rolled in flags.items():
            obj = doc.getObject(name)
            if obj is None:
                continue
            self._set_rolled_back(obj, rolled)
            if self._is_surface_obj(obj):
                for sk in self._surface_sketch_objects(obj):
                    self._set_rolled_back(sk, rolled)

    def _free_sketches(self):
        """Esquisses du corps actif non consommées par une fonction.

        Mêmes candidates que ``_latest_sketch`` : une esquisse dont le
        ``Profile`` d'une fonction pointe dessus est repliée, comme
        les modeleurs courants la rangent sous le bossage. Les esquisses reculées par
        la barre de retour sont exclues — on ne référence pas ce qui
        est sous la barre.
        """
        body = self._require_body()
        used = set()
        for obj in body.Group:
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            if linked is not None:
                used.add(linked.Name)
        return [o for o in body.Group
                if o.TypeId == "Sketcher::SketchObject"
                and o.Name not in used
                and not self._is_rolled_back(o)]

    def _latest_sketch(self):
        """The newest sketch not yet consumed by a feature.

        Root cause of the "passage esquisse → extrusion" confusion: reusing
        an already-extruded profile fails downstream with a cryptic error.
        A profile is used once; the next feature takes the next fresh
        sketch, as in the usual modeller.
        """
        from engine.kernel import KernelError
        sketches = self._free_sketches()
        if not sketches:
            raise KernelError(
                "aucune esquisse disponible — les esquisses existantes "
                "sont déjà utilisées par des fonctions, dessinez-en une "
                "nouvelle")
        return sketches[-1]

    def set_tip(self, feature=None):
        """Déplace la barre de retour : l'historique se reconstruit
        jusqu'à cette ligne (fonction, esquisse libre ou surface).

        Sans *feature* (ou nom vide), la barre se pose avant la première
        ligne — tout est reculé, comme un glisser tout en haut de
        l'arbre de création. ``body.Tip`` ne couvre que la chaîne PartDesign ;
        les surfaces et esquisses libres portent ``FreeSolidRolledBack``.
        """
        from engine.kernel import (
            KernelError,
            rollback_plan,
        )
        body = self._require_body()
        history = self._history_lines()
        if feature is None or not str(feature).strip():
            flags, tip_name = rollback_plan(self._history_rows(history), None)
            body.Tip = None
            self._apply_rollback_flags(flags)
            self._recompute()
            return self.get_tree()
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        names = {line.Name for line in history}
        if obj.Name not in names:
            raise KernelError(
                "« {} » n'est pas une ligne d'historique — la barre de "
                "retour se pose sur une fonction, une esquisse libre ou "
                "une surface".format(obj.Label))
        flags, tip_name = rollback_plan(
            self._history_rows(history), obj.Name)
        if tip_name is None:
            body.Tip = None
        else:
            tip_obj = self._require_doc().getObject(tip_name)
            body.Tip = self._tip_with_helpers(tip_obj)
        self._apply_rollback_flags(flags)
        self._recompute()
        return self.get_tree()

    def tip_to_end(self):
        """Barre de retour en bout d'historique — l'état final."""
        from engine.kernel import (
            KernelError,
            rollback_plan,
        )
        body = self._require_body()
        history = self._history_lines()
        if not history:
            raise KernelError("aucune fonction dans la pièce")
        flags, tip_name = rollback_plan(
            self._history_rows(history), history[-1].Name)
        if tip_name is None:
            body.Tip = None
        else:
            body.Tip = self._tip_with_helpers(
                self._require_doc().getObject(tip_name))
        self._apply_rollback_flags(flags)
        self._recompute()
        return self.get_tree()

    def delete_feature(self, feature):
        """Remove one feature. Its sketch stays — deleting it too would be
        a second, separate decision, as in the usual modeller. Deleting a
        body removes its whole contents; the last body is protected."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if self._plugins.run_deletes_feature(self, obj):
            return self._current_tree()
        label = obj.Label
        if obj.TypeId == "PartDesign::Body":
            bodies = [o for o in doc.Objects
                      if o.TypeId == "PartDesign::Body"]
            if len(bodies) <= 1:
                raise KernelError("impossible de supprimer le dernier "
                                  "corps de la pièce")
            for child in list(obj.Group):
                try:
                    doc.removeObject(child.Name)
                except Exception:
                    pass
            if self._body is obj:
                self._body = next(b for b in bodies if b is not obj)
        # Supprimer le Tip laissait Body.Tip = None et une Shape invalide
        # (attrapé par le selftest P007) : le Tip recule d'abord sur la
        # fonction précédente de la chaîne (None si c'était la seule —
        # corps vide légitime).
        parent_body = obj.getParentGeoFeatureGroup()
        thin_helpers = self._thin_helpers(obj)
        order = {o.Name: i for i, o in enumerate(
            getattr(parent_body, "Group", None) or [])}
        if parent_body is not None and getattr(parent_body, "Tip", None) in (
                [obj] + thin_helpers):
            # Le solide d'avant la première fonction de la chaîne (un
            # auxiliaire peut précéder la fonction).
            chain = [o for o in [obj] + thin_helpers
                     if o.isDerivedFrom("PartDesign::Feature")]
            first = min(chain, key=lambda o: order.get(o.Name, -1))
            parent_body.Tip = getattr(first, "BaseFeature", None)
        # Paroi mince : la cavité (après la fonction) part avant elle, les
        # profils décalés (avant) après.
        rank = order.get(obj.Name, -1)
        later = [o for o in thin_helpers if order.get(o.Name, -1) > rank]
        earlier = [o.Name for o in thin_helpers if o not in later]
        self._remove_all(later)
        doc.removeObject(obj.Name)
        for name in reversed(earlier):
            if doc.getObject(name) is not None:
                doc.removeObject(name)
        try:
            if self._assembly:
                doc.recompute()
            else:
                self._recompute()
        except KernelError as exc:
            raise KernelError(
                "{} supprimé, mais l'aval casse : {}".format(label, exc))
        return self._current_tree()

    def _body_has_solid(self, body):
        """Vrai si le corps porte un solide OCCT réel (état affiché)."""
        shape = getattr(body, "Shape", None)
        if shape is None:
            return False
        try:
            if shape.isNull():
                return False
            solids = shape.Solids
        except Exception:  # noqa: BLE001 — Shape OCCT parfois inaccessible
            return False
        return bool(solids)

    def _tree_known_names(self, body):
        """Noms des nœuds dessinables du payload ``get_tree``.

        Fonction, esquisse, plan de référence, surface ou corps déjà
        présents dans la réponse — pas l'Origin, le VarSet, ni les
        artefacts internes (gravure, fonction graphe, répétition).
        """
        names = set()
        origin = getattr(body, "Origin", None)
        for feature in getattr(origin, "OriginFeatures", None) or ():
            role = getattr(feature, "Role", "")
            if role in self._PLANE_ROLES.values():
                names.add(feature.Name)
        # Tout ``body.Group`` : ``get_tree`` émet chaque objet du corps —
        # une esquisse consommée revient en ``children``, un plan ou un axe
        # de référence n'est pas un ``PartDesign::Feature`` mais reste un
        # nœud. Filtrer ici ferait diverger l'ensemble des cibles de ce que
        # le payload expose, et perdrait des arêtes réelles en silence.
        for obj in body.Group:
            if (getattr(obj, "FreeSolidAxisTool", False)
                    or self._is_thin_helper(obj)):   # hors arbre
                continue
            names.add(obj.Name)
        for obj in self._doc.Objects:
            if obj.TypeId == "PartDesign::Body" and not self._is_internal_tool(obj):
                names.add(obj.Name)
            if (self._is_surface_obj(obj)
                    and not self._is_internal_tool(obj)):
                names.add(obj.Name)
                for sketch in self._surface_sketch_objects(obj):
                    names.add(sketch.Name)
        for obj in self._doc.Objects:
            # Semis : App::Link marqué. Même discipline que
            # ``_is_internal_tool`` — le noyau reconnaît une propriété,
            # il n'appelle plus le métier bijouterie.
            if (getattr(obj, "TypeId", "") == "App::Link"
                    and "FreeSolidGemFace" in getattr(
                        obj, "PropertiesList", ())):
                names.add(obj.Name)
        return names

    @staticmethod
    def _is_sub_names(value):
        """Vrai si ``value`` est un nom de sous-élément ou une liste de noms."""
        if isinstance(value, str):
            return True
        if not isinstance(value, (list, tuple)):
            return False
        return all(isinstance(item, str) for item in value)

    @staticmethod
    def _iter_link_subs(value):
        """Paires ``(objet, [sous-éléments])`` d'un Link, LinkSub ou LinkSubList.

        ``Base`` (habillage, dépouille) a la forme ``(objet, [noms])`` ;
        ``AttachmentSupport`` (esquisse sur face) est une liste de telles
        paires. Un objet nu (``Profile`` d'un bossage) n'a pas de sous-élément.
        """
        from engine.kernel import Kernel
        if value is None:
            return
        if isinstance(value, (list, tuple)):
            if (len(value) == 2
                    and getattr(value[0], "Name", None)
                    and Kernel._is_sub_names(value[1])):
                subs = ([value[1]] if isinstance(value[1], str)
                        else list(value[1]))
                yield value[0], subs
                return
            for item in value:
                for pair in Kernel._iter_link_subs(item):
                    yield pair
            return
        if getattr(value, "Name", None):
            yield value, []
            return
        try:
            items = list(value)
        except TypeError:
            return
        for item in items:
            for pair in Kernel._iter_link_subs(item):
                yield pair

    def _object_dep_subs(self, obj):
        """``{cible: [sous-éléments]}`` lus sur ``Base`` et l'appui d'esquisse.

        Les sous-éléments vides (attache à l'objet entier) sont omis : ils
        n'ajoutent rien à ``deps``. Le filtrage des cibles hors payload
        est ``visible_dep_subs``.
        """
        raw = {}
        for prop in ("Base", "AttachmentSupport", "Support"):
            if not hasattr(obj, prop):
                continue
            try:
                value = getattr(obj, prop)
            except Exception:  # noqa: BLE001 — propriété FreeCAD parfois cassée
                continue
            for target, subs in self._iter_link_subs(value):
                name = getattr(target, "Name", "") or ""
                if not name:
                    continue
                existing = raw.setdefault(name, [])
                for sub in subs:
                    if not isinstance(sub, str) or not sub or sub in existing:
                        continue
                    existing.append(sub)
        return raw

    def _repeat_source_names(self, obj):
        """Noms des fonctions source d'une répétition variable, ou [].

        Les copies rejouées n'existent plus dans l'OutList : le lien
        se lit dans le JSON persisté.
        """
        import json
        if "FreeSolidRepeatJson" not in getattr(obj, "PropertiesList", ()):
            return []
        try:
            parsed = json.loads(obj.FreeSolidRepeatJson or "")
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed, dict):
            return []
        names = []
        for name in parsed.get("features") or ():
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def _annotate_tree_links(self, item, obj, known_names):
        """Pose ``deps``, ``dep_subs``, ``driven`` et ``params`` s'ils existent.

        ``params`` réutilise ``get_params`` — pas de seconde boucle sur
        ``_EDITABLE_PROPS``. Champs omis quand vides.
        """
        from engine.kernel import (
            visible_dep_subs,
            visible_deps,
        )
        outs = [o.Name for o in (getattr(obj, "OutList", None) or ())]
        _, source = self._thin_chain(obj)
        if source is not None:
            # Paroi mince : l'arête va à l'esquisse, pas au profil caché.
            outs = [source.Name] + outs
        deps = visible_deps(outs + self._repeat_source_names(obj),
                            known_names)
        if deps:
            item["deps"] = deps
        dep_subs = visible_dep_subs(self._object_dep_subs(obj), known_names)
        if dep_subs:
            item["dep_subs"] = dep_subs
        driven = self._expression_map(obj)
        if driven:
            item["driven"] = driven
        params = self.get_params(obj.Name).get("params") or []
        if params:
            item["params"] = params
        return item

    def get_tree(self):
        """Arbre de fonctions, vocabulaire du concepteur.

        Comme dans les modeleurs courants : les trois plans de référence
        d'abord, et une esquisse consommée par une fonction se range
        dessous en ``children`` plutôt que de polluer le premier niveau.

        Chaque entrée — fonction du corps, esquisse imbriquée, surface et
        esquisse de surface — peut porter quatre champs, omis quand ils
        sont vides :

        - ``deps`` — noms internes des nœuds dont elle dépend
          (``OutList`` filtré). Une arête n'est émise que si sa cible
          est elle-même un nœud du même payload : fonction, esquisse,
          plan de référence, surface ou corps. Aucune arête pendante.
        - ``dep_subs`` — ``{cible: [sous-éléments]}`` lus sur ``Base``
          et ``AttachmentSupport``. Les noms de face ou d'arête que
          ``OutList`` jette. Même filtre que ``deps`` : une cible hors
          payload n'émet pas de sous-élément.
        - ``driven`` — ``{chemin de propriété: expression}``, les
          propriétés pilotées. Chaîne brute, sans parsing des variables.
        - ``params`` — cotes éditables, même forme que ``get_params``.

        Les plans de référence sont adressables : chaque entrée de
        ``planes`` porte le ``name`` de l'objet, seule adresse par
        laquelle une arête peut les désigner — ``id`` reste ``"XZ"`` quand
        le nom prend un suffixe en multi-corps.

        La cohérence de l'ensemble se vérifie par
        ``protocol.dangling_deps`` : elle confronte chaque arête à ce que
        le payload expose vraiment, et non à l'ensemble de noms qui a
        servi à la filtrer. Le selftest la passe sur la pièce vitrine.
        """
        import json
        from engine.kernel import label_for_type
        body = self._require_body()
        order_of = {obj.Name: i for i, obj in enumerate(self._doc.Objects)}
        # Dans le corps, l'ordre fait foi (réordonner le change sans toucher
        # l'ordre de création) : on redistribue ses rangs selon body.Group,
        # ce qui garde l'entrelacement avec les surfaces hors corps.
        members = [o for o in body.Group if o.Name in order_of]
        for slot, obj in zip(sorted(order_of[o.Name] for o in members),
                             members):
            order_of[obj.Name] = slot

        consumed = self._consumed_sketches()
        known_names = self._tree_known_names(body)

        def entry(obj):
            item = {
                "name": obj.Name,
                "label": obj.Label,
                "kind": label_for_type(obj.TypeId, self.lang),
                "type": obj.TypeId,
                "error": "Invalid" in (obj.State or ()),
                "order": order_of.get(obj.Name, -1),
            }
            if getattr(obj, "Suppressed", False):
                item["suppressed"] = True
            if obj.TypeId in ("PartDesign::Plane", "PartDesign::Line",
                              "PartDesign::Point",
                              "PartDesign::CoordinateSystem"):
                # Le client dessine la géométrie de référence dans la vue.
                item["placement"] = [
                    float(v) for v in obj.Placement.Matrix.A]
                item["rolled_back"] = self._is_rolled_back(obj)
            if obj.TypeId == "Sketcher::SketchObject":
                item["rolled_back"] = self._is_rolled_back(obj)
                item["definition"] = self._sketch_definition(obj)
                try:
                    wires = self._sketch_wires(obj)
                except Exception:  # noqa: BLE001
                    wires = []
                if len(wires) > 1:
                    # Plusieurs contours : une fonction peut n'en prendre
                    # qu'une partie.
                    item["contours"] = [w["size"] for w in wires]
                lines = self._sketch_line_axes(obj)
                if lines:
                    item["lines"] = lines
            if obj.TypeId == "PartDesign::Chamfer":
                item["chamfer"] = self._chamfer_state(obj)
            thin = self._thin_spec(obj)
            if thin is not None:
                item["thin"] = thin
            if obj.TypeId in ("PartDesign::Revolution", "PartDesign::Groove"):
                item["revolution"] = self._revolution_state(obj)
            if obj.TypeId in ("PartDesign::Pad", "PartDesign::Pocket",
                              "PartDesign::Revolution", "PartDesign::Groove"):
                profile = self._profile_entry(obj)
                if profile is not None:
                    item["profile"] = profile
            if "FreeSolidTextString" in obj.PropertiesList:
                # Gravure rééditable : le panneau client édite ces valeurs.
                item["text"] = {
                    "text": obj.FreeSolidTextString,
                    "size": float(obj.FreeSolidTextSize),
                    "depth": float(obj.FreeSolidTextDepth),
                    "x": float(obj.FreeSolidTextX),
                    "y": float(obj.FreeSolidTextY),
                }
            vchamfer = getattr(obj, "FreeSolidVchamferspec", "")
            if vchamfer:
                from engine.vertexchamfer import parse_spec
                vertex, distances = parse_spec(vchamfer)
                item["vertex_chamfer"] = {"vertex": vertex,
                                          "distances": distances}
            deleted = getattr(obj, "FreeSolidDeletefaces", "")
            if deleted:
                item["delete_face"] = {"faces": [
                    int(f) for f in str(deleted).split(";") if f != ""]}
            replaced = getattr(obj, "FreeSolidReplacedby", "")
            if replaced:
                item["replace_face"] = {
                    "face": int(obj.FreeSolidReplacedface) - 1,
                    "surface": replaced}
            cut = self._surface_cut_spec(obj)
            if cut is not None:
                item["surface_cut"] = cut
            if "FreeSolidGraphJson" in obj.PropertiesList:
                graph = self._tree_graph_payload(obj)
                if graph is not None:
                    item["graph"] = graph
            if "FreeSolidRepeatJson" in obj.PropertiesList:
                try:
                    parsed = json.loads(obj.FreeSolidRepeatJson or "")
                except (TypeError, ValueError):
                    parsed = None
                if isinstance(parsed, dict):
                    item["repeat"] = parsed
            self._annotate_tree_links(item, obj, known_names)
            return item

        users = self._sketch_consumers()
        labels = {o.Name: o.Label for o in body.Group}
        items = []
        for obj in body.Group:
            if (getattr(obj, "FreeSolidAxisTool", False)
                    or getattr(obj, "FreeSolidPierce", "")):
                continue  # axe, lieur de percée : outils, hors arbre
            if (obj.TypeId == "Sketcher::SketchObject"
                    and obj.Name in consumed) or self._is_thin_helper(obj):
                continue
            item = entry(obj)
            children = []
            for o in body.Group:
                if o.TypeId != "Sketcher::SketchObject":
                    continue
                owners = users.get(o.Name, [])
                if consumed.get(o.Name) != obj.Name and obj.Name not in owners:
                    continue
                child = entry(o)
                if len(owners) > 1:
                    # Esquisse partagée : affichée sous chaque fonction.
                    child["shared"] = [labels.get(n, n) for n in owners
                                       if n != obj.Name]
                children.append(child)
            if children:
                item["children"] = children
            items.append(item)

        from engine.vocab import label_for_origin
        # L'ordre d'affichage : Plan de face, Plan de dessus, Plan de droite.
        # ``name`` : le nom d'objet réel, seule adresse par laquelle une
        # arête peut désigner un plan de référence (``id`` ne suffit pas —
        # en multi-corps FreeCAD suffixe le nom, « XZ_Plane001 »).
        planes = []
        for wire in ("XZ", "XY", "YZ"):
            role = self._PLANE_ROLES[wire]
            feature = self._origin_feature_or_none(role)
            planes.append({
                "id": wire,
                "label": label_for_origin(role, self.lang),
                "name": feature.Name if feature is not None else "",
            })
        bodies = []
        for obj in self._doc.Objects:
            if obj.TypeId != "PartDesign::Body":
                continue
            if self._is_internal_tool(obj):
                continue  # corps outil interne : artefact hors arbre
            bodies.append({
                "name": obj.Name,
                "label": obj.Label,
                "active": obj is body,
                "count": len([o for o in obj.Group
                              if (o.isDerivedFrom("PartDesign::Feature")
                                  or o.TypeId == "Sketcher::SketchObject")
                              and not self._is_thin_helper(o)]),
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "has_solid": self._body_has_solid(obj),
                "hidden": self._is_hidden(obj),
                "material": self._material_of(obj),
            })
        consumed = self._consumed_surfaces()
        surfaces = [self._surface_tree_entry(o, order_of, known_names,
                                             consumed)
                    for o in self._doc.Objects
                    if self._is_surface_obj(o)
                    and not self._is_internal_tool(o)]
        tip = (self._thin_owner(body.Tip).Name
               if getattr(body, "Tip", None) else None)
        # Variables dans le même appel : l'arbre de création affiche le
        # dossier Équations sans round-trip list_variables.
        self._annotate_comments(items)
        self._annotate_comments(surfaces)
        self._annotate_folders(items)
        for entry in surfaces:
            if self._is_hidden(self._doc.getObject(entry["name"])):
                entry["hidden"] = True
        tree = {"body": body.Label, "tip": tip, "bodies": bodies,
                "planes": planes, "features": items,
                "surfaces": surfaces,
                "variables": self.list_variables()["variables"]}
        self._plugins.contribute_tree(self, tree)
        return tree

    def _face_mesh(self, face, face_id, deviation):
        """Tessellation d'une face + normales exactes ``normalAt(u, v)``."""
        from engine.surfaces import is_bspline_surface, project_uv
        vertices, triangles = face.tessellate(float(deviation))
        points = [(v.x, v.y, v.z) for v in vertices]
        normals = []
        for vertex in vertices:
            try:
                u, v, _on = project_uv(face, vertex.x, vertex.y, vertex.z)
                normal = face.normalAt(u, v)
                if hasattr(normal, "normalize"):
                    normal = normal.normalize()
                length = float(getattr(normal, "Length", 0) or 0)
                if length < 1e-12:
                    normals.append((0.0, 0.0, 1.0))
                else:
                    normals.append((float(normal.x), float(normal.y),
                                    float(normal.z)))
            except Exception:
                normals.append((0.0, 0.0, 1.0))
        return (face_id, points, triangles, normals), is_bspline_surface(face)

    def tessellate(self, deviation=0.1):
        """Per-face tessellation of the body's current shape.

        Face-by-face on purpose — see ``protocol.pack_mesh``: picking works
        by construction because each OCCT face is its own index group.
        """
        from . import protocol
        body = self._require_body()
        self._report_progress("Maillage")
        shape = getattr(body, "Shape", None)
        if self._is_hidden(body):
            shape = None  # masqué : ni dessiné, ni visé
        faces = []
        splines = []
        if shape is not None and shape.Faces:
            for i, face in enumerate(shape.Faces):
                packed, spline = self._face_mesh(face, i, deviation)
                faces.append(packed)
                splines.append(spline)
        mesh = protocol.pack_mesh(faces)
        producers = self._face_producers()
        face_colors = self._face_colors(body)
        for group, spline in zip(mesh.get("groups") or [], splines):
            if spline:
                group["spline"] = True
            tint = face_colors.get(str(group.get("faceId")))
            if tint:
                group["color"] = tint
            feature = producers.get(group.get("faceId"))
            if feature:
                group["feature"] = self._thin_owner(
                    self._doc.getObject(feature)).Name
        match = getattr(self, "_face_match", None) or {}
        mesh["face_match"] = {
            "matched": int(match.get("matched") or 0),
            "faces": int(match.get("faces") or 0),
        }
        mesh["color"] = getattr(body, "FreeSolidColor", "") or None
        # Les autres corps s'affichent estompés, non sélectionnables :
        # on travaille sur le corps actif, on voit la pièce entière.
        # Un maillage par corps (couleur propre) ; ``others`` reste le
        # buffer combiné pour la compatibilité (selftest p9_others_shown).
        other_bodies = []
        for obj in self._doc.Objects:
            if (obj.TypeId != "PartDesign::Body" or obj is body
                    or getattr(obj, "Shape", None) is None
                    or self._is_internal_tool(obj)
                    or self._is_hidden(obj)):
                continue
            other_faces = []
            for face in obj.Shape.Faces:
                vertices, triangles = face.tessellate(float(deviation))
                other_faces.append(
                    (0, [(v.x, v.y, v.z) for v in vertices], triangles))
            if not other_faces:
                continue
            packed = protocol.pack_mesh(other_faces)
            other_bodies.append({
                "name": obj.Name,
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "positions": packed["positions"],
                "indices": packed["indices"],
            })
        if other_bodies:
            mesh["other_bodies"] = other_bodies
            positions = []
            indices = []
            vertex_base = 0
            for extra in other_bodies:
                positions.extend(extra["positions"])
                indices.extend(i + vertex_base for i in extra["indices"])
                vertex_base += len(extra["positions"]) // 3
            mesh["others"] = {"positions": positions, "indices": indices}
        # Surfaces (Part::*) : un maillage par objet, comme les esquisses
        # libres — le client les rend opaques et sélectionnables. Les
        # courbes 3D (pas de Faces) : un jeu d'arêtes par objet.
        surfaces_out = []
        curve_objects = []
        consumed = self._consumed_surfaces()
        for obj in self._doc.Objects:
            if not self._is_surface_obj(obj):
                continue
            if (self._is_rolled_back(obj) or self._is_internal_tool(obj)
                    or obj.Name in consumed or self._is_hidden(obj)):
                continue
            shape = getattr(obj, "Shape", None)
            if shape is None:
                continue
            # Arêtes numérotées comme « EdgeN » : bords de remplissage,
            # bord à prolonger, trajectoire — choisis dans la vue.
            edges = protocol.pack_edges(self._object_edge_lines(shape))
            if shape.Faces:
                surface_faces = []
                for i, face in enumerate(shape.Faces):
                    vertices, triangles = face.tessellate(float(deviation))
                    surface_faces.append(
                        (i, [(v.x, v.y, v.z) for v in vertices], triangles))
                packed = protocol.pack_mesh(surface_faces)
                if packed["positions"]:
                    surfaces_out.append({
                        "name": obj.Name,
                        "label": obj.Label,
                        "positions": packed["positions"],
                        "indices": packed["indices"],
                        # Une face de surface se clique (supprimer,
                        # projeter, désajuster) : groupes par face.
                        "groups": packed["groups"],
                        "edges": edges,
                    })
            elif edges["indices"]:
                curve_objects.append({
                    "name": obj.Name,
                    "label": obj.Label,
                    "edges": edges,
                })
        if surfaces_out:
            mesh["surfaces"] = surfaces_out
        if curve_objects:
            mesh["curves"] = curve_objects
        # Esquisses libres : polylignes 3D pour le viewport. Le Shape
        # d'un SketchObject est déjà posé dans l'espace et n'inclut pas
        # la géométrie de construction (Construction / getConstruction).
        sketches_out = []
        # Une esquisse absorbée par une surface ne se dessine plus : ses
        # traits masqueraient les bords de la surface au clic.
        absorbed = {sk.Name for obj in self._doc.Objects
                    if self._is_surface_obj(obj)
                    and not self._is_rolled_back(obj)
                    for sk in self._surface_sketch_objects(obj)}
        for sk in self._free_sketches():
            if sk.Name in absorbed:
                continue
            shape = getattr(sk, "Shape", None)
            if shape is None or not shape.Edges:
                continue
            lines = []
            for i, edge in enumerate(shape.Edges):
                try:
                    # Deviation= est rejeté sur les arêtes d'esquisse
                    # (keyword OCCT : Deflection).
                    points = edge.discretize(Deflection=0.1)
                except Exception:
                    try:
                        points = edge.discretize(Number=24)
                    except Exception:
                        continue
                lines.append((i, [(p.x, p.y, p.z) for p in points]))
            packed = protocol.pack_edges(lines)
            if not packed["positions"]:
                continue
            sketches_out.append({
                "name": sk.Name,
                "label": sk.Label,
                "positions": packed["positions"],
                "indices": packed["indices"],
            })
        if sketches_out:
            mesh["sketches"] = sketches_out
        self._plugins.contribute_mesh(self, mesh, deviation)
        return mesh

    def tessellate_edges(self, deviation=0.05):
        """Per-edge polylines of the body's current shape.

        Edge-by-edge on purpose — see ``protocol.pack_edges``: a raycast
        hit maps to exactly one OCCT edge, same contract as ``tessellate``
        for faces. Ids are Edge indices, so ``Edge{id+1}`` server-side.
        Les arêtes de couture (la jointure interne d'un cylindre, d'un
        cône…) ne sont pas tracées : elles ne bordent rien à l'œil. Les
        ids des autres restent ceux du noyau.
        """
        from . import protocol
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Edges or self._is_hidden(body):
            return protocol.pack_edges([])
        seams = self._seam_edge_ids(shape)
        lines = []
        for i, edge in enumerate(shape.Edges):
            if i in seams:
                continue
            try:
                points = edge.discretize(Deviation=float(deviation))
            except Exception:
                try:
                    points = edge.discretize(Number=24)
                except Exception:
                    continue  # arête dégénérée : les ids restent justes
            lines.append((i, [(p.x, p.y, p.z) for p in points],
                          float(edge.Length), self._circle_center(edge)))
        return protocol.pack_edges(lines)

    def _object_edge_lines(self, shape):
        """Polylignes des arêtes d'une surface ou d'une courbe, en base 0
        comme les arêtes du corps (« EdgeN+1 ») ; les coutures sont omises."""
        seams = self._seam_edge_ids(shape) if shape.Faces else set()
        lines = []
        for i, edge in enumerate(shape.Edges):
            if i in seams:
                continue
            try:
                points = edge.discretize(Deflection=0.05)
            except Exception:
                try:
                    points = edge.discretize(Number=48)
                except Exception:
                    continue  # arête dégénérée : les ids restent justes
            lines.append((i, [(p.x, p.y, p.z) for p in points],
                          edge.Length, self._circle_center(edge)))
        return lines

    @staticmethod
    def _circle_center(edge):
        """Centre d'une arête circulaire (cercle ou arc), sinon None."""
        try:
            curve = edge.Curve
            if curve.TypeId != "Part::GeomCircle":
                return None
            c = curve.Center
            return (c.x, c.y, c.z)
        except Exception:
            return None

    @staticmethod
    def _seam_edge_ids(shape):
        """Indices (dans ``shape.Edges``) des arêtes de couture."""
        index = {}
        for i, edge in enumerate(shape.Edges):
            index.setdefault(edge.hashCode(), []).append((i, edge))
        seams = set()
        for face in shape.Faces:
            for edge in face.Edges:
                try:
                    if not edge.isSeam(face):
                        continue
                except Exception:
                    continue
                for i, candidate in index.get(edge.hashCode(), ()):
                    if candidate.isSame(edge):
                        seams.add(i)
        return seams
