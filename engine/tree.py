"""Arbre de création, barre de retour et tessellation.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

#: Esquisse sortie de sa fonction par la barre de retour (propriété du corps).
_BAR_SKETCH_PROP = "FreeSolidBarSketch"
#: Corps nommé à la main : le dossier garde son nom (propriété du corps).
_NAMED_PROP = "FreeSolidNamed"
#: Rang de l'objet dans l'arbre, enregistré quand la barre bouge
#: (``_persist_ranks``, propriété de chaque objet).
_RANK_PROP = "FreeSolidRank"
#: Le changer ne relance aucun recalcul (Output | NoRecompute), et
#: l'éditeur de propriétés de FreeCAD ne le montre pas (Hidden).
_RANK_ATTR = 8 | 16 | 4


class TreeMixin:
    # -- arbre et tessellation --------------------------------------------

    def reorder_feature(self, feature, target, after=False):
        """Déplacer une fonction (avec ses esquisses) avant ou après une
        autre, par glisser-déposer dans l'arbre. Refusé si l'arbre ne se
        reconstruit plus (une fonction viendrait avant ce dont elle
        dépend) : la transaction est alors annulée."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        moved = doc.getObject(str(feature))
        anchor = doc.getObject(str(target))
        # L'arbre montre tous les corps : on réordonne dans celui de la
        # fonction déplacée, sans l'activer.
        body = self._history_body_of(moved) or self._require_body()
        members = list(body.Group)
        if moved not in members or anchor not in members:
            raise KernelError("réordonner : fonction inconnue dans ce corps")
        if moved is anchor:
            return self.get_tree()
        bar = self._bar_line()
        self._persist_ranks()
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
        tip_at_end = (body.Tip is not None
                      and body.Tip is self._last_body_feature(body))
        for obj in group:
            body.removeObject(obj)
        if after:
            for obj in reversed(group):
                body.insertObject(obj, anchor, True)
        else:
            for obj in group:
                body.insertObject(obj, anchor, False)
        if tip_at_end:
            last = self._last_body_feature(body)
            if last is not None:
                body.Tip = last
        # Le rang de la fonction a changé parmi les autres corps : les
        # étapes cachées des enlèvements suivent le leur.
        self._place_scope_cuts()
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
        try:
            # Les outils figés des étapes cachées suivent leur source.
            self._recompute()
        except KernelError:
            pass  # refusé ci-dessous, en nommant ce qui casse
        broken = [o.Label for b in self._history_bodies() for o in b.Group
                  if "Invalid" in (o.State or ())]
        if broken:
            raise KernelError(
                "réordonner : l'arbre ne se reconstruit plus ({}) — une "
                "fonction viendrait avant ce dont elle dépend".format(
                    ", ".join(broken)))
        if bar is not None:
            # La barre reste sous la même ligne : chaque corps s'arrête à
            # son rang, étapes cachées comprises.
            return self.set_tip(bar)
        self._persist_ranks()  # les rangs redistribués du corps
        return self.get_tree()

    def _last_body_feature(self, body=None):
        """Dernière fonction solide du corps (hors esquisses et plans)."""
        body = body or self._require_body()
        for obj in reversed(list(body.Group)):
            if obj.isDerivedFrom("PartDesign::Feature"):
                return obj
        return None

    def _history_bodies(self):
        """Corps dont l'histoire paraît dans l'arbre, dans l'ordre du
        document : tous, sauf les corps outils internes."""
        return [o for o in self._require_doc().Objects
                if o.TypeId == "PartDesign::Body"
                and not self._is_internal_tool(o)]

    def _history_body_of(self, obj):
        """Le corps de l'histoire qui contient ``obj``, ou None."""
        return next((b for b in self._history_bodies() if obj in b.Group),
                    None)

    @staticmethod
    def _is_pattern_base(obj):
        """Base d'une copie de réseau de corps : la ligne du réseau la
        représente, l'histoire ne la montre pas."""
        return bool(getattr(obj, "FreeSolidPatternOf", ""))

    def _consumed_sketches(self):
        """Esquisse → nom du parent (fonction PartDesign ou surface), dans
        tous les corps."""
        self._require_body()
        consumed = {}
        for obj in [o for b in self._history_bodies() for o in b.Group]:
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

    def _history_role(self, obj, consumed):
        """Rôle dans l'historique : ``feature`` / ``sketch`` / ``surface``
        / ``pattern`` (réseau de corps) / ``remove`` (suppression de corps),
        ou None si hors historique. Un code, pas un libellé : ``kind`` reste
        le nom affiché d'un objet."""
        if self._is_thin_helper(obj):
            return None
        if self._is_surface_obj(obj):
            return "surface"
        if "FreeSolidBodyPattern" in obj.PropertiesList:
            return "pattern"
        if "FreeSolidRemoveBodies" in obj.PropertiesList:
            return "remove"
        if obj.TypeId == "Sketcher::SketchObject":
            return None if obj.Name in consumed else "sketch"
        if obj.isDerivedFrom("PartDesign::Feature"):
            return "feature"
        return None

    def _base_order(self):
        """Rang de chaque objet avant le rangement par corps.

        Tant que la barre n'a jamais bougé (pièce neuve, fichier d'avant) :
        l'ordre de création. Dès qu'elle bouge, chaque objet garde le rang
        enregistré alors (``_persist_ranks``). Un objet né depuis vient où
        la barre était, comme dans les modeleurs courants : juste au-dessus
        des lignes reculées, en bas de l'arbre quand la barre y est. S'il
        suit dans son corps une fonction reculée (une étape d'une fonction
        rééditée sous la barre), il vient juste après elle. Rien ne change
        donc de place autour de lui.
        """
        objects = list(self._doc.Objects)
        ranked = {o.Name: getattr(o, _RANK_PROP) for o in objects
                  if _RANK_PROP in o.PropertiesList}
        if not ranked:
            return {obj.Name: i for i, obj in enumerate(objects)}
        fresh = [o for o in objects if o.Name not in ranked]
        if not fresh:
            return ranked
        # La barre passe entre les lignes reculées et les autres. Une étape
        # cachée compte au rang de sa source, pas au sien : elle n'y entre
        # pas.
        steps = {o.Name for o in objects if self._hidden_cut_source(o)}
        rows = {n: k for n, k in ranked.items() if n not in steps}
        rolled = self._rolled_names()
        below = [k for n, k in rows.items() if n in rolled]
        ceiling = min(below) if below else None
        above = [k for k in rows.values() if ceiling is None or k < ceiling]
        floor = (max(above) if above
                 else ceiling - 1 if ceiling is not None else -1)
        born = {o.Name for o in fresh}
        anchors = {}
        for body in self._history_bodies():
            last = None
            for obj in body.Group:
                if obj.Name in born:
                    anchors[obj.Name] = last
                elif obj.Name not in steps:
                    key = ranked.get(obj.Name)
                    last = (key if ceiling is not None and key is not None
                            and key >= ceiling else None)
        groups = {}
        for obj in fresh:  # dans l'ordre de création
            groups.setdefault(anchors.get(obj.Name), []).append(obj.Name)
        values = sorted(set(ranked.values()))
        order_of = dict(ranked)
        for anchor, names in groups.items():
            start = floor if anchor is None else anchor
            end = next((v for v in values if v > start), start + 1)
            step = (end - start) / (len(names) + 1)
            for index, name in enumerate(names, 1):
                order_of[name] = start + step * index
        return order_of

    def _rolled_names(self):
        """Ce que la barre recule, sans passer par l'ordre de l'arbre :
        fonctions après la pointe de leur corps, objets marqués reculés,
        réseaux de corps dont les copies n'existent pas encore."""
        rolled = set(self._features_after_tips())
        rolled.update(o.Name for o in self._doc.Objects
                      if self._is_rolled_back(o))
        rolled.update(host.Name for host in self._body_pattern_hosts()
                      if self._body_pattern_rolled_back(host))
        return rolled

    def _persist_ranks(self):
        """Enregistre le rang de chaque objet, tel que l'arbre le range,
        avant que la barre ne bouge : un objet né à la barre y reste quand
        elle repart. Des entiers, dans l'ordre ; deux objets de même rang
        gardent le même."""
        order_of = self._tree_order()
        dense = {v: i for i, v in enumerate(sorted(set(order_of.values())))}
        for obj in self._require_doc().Objects:
            rank = dense[order_of[obj.Name]]
            if _RANK_PROP not in obj.PropertiesList:
                obj.addProperty("App::PropertyInteger", _RANK_PROP,
                                "FreeSolid", "Rang dans l'arbre de création",
                                _RANK_ATTR)
            elif getattr(obj, _RANK_PROP) == rank:
                continue
            setattr(obj, _RANK_PROP, rank)

    @staticmethod
    def _unrank(obj):
        """Une copie (coller) naît où la barre est : sans le rang de sa
        source, que ``copyObject`` recopie."""
        if _RANK_PROP in obj.PropertiesList:
            obj.removeProperty(_RANK_PROP)

    def _tree_order(self):
        """Rang de chaque objet, celui que l'arbre affiche (``order``).

        Dans chaque corps, l'ordre du corps fait foi (réordonner le change
        sans toucher l'ordre de création) : on redistribue ses rangs selon
        body.Group, ce qui garde l'entrelacement avec les autres corps et
        les surfaces hors corps. Les rangs de départ : ``_base_order``.
        """
        self._require_body()
        order_of = self._base_order()
        for body in self._history_bodies():
            # Les étapes cachées d'un enlèvement prennent le rang de leur
            # source (``_history_rows``) : glissées dans la chaîne d'un
            # corps, elles n'y décalent pas les fonctions.
            members = [o for o in body.Group if o.Name in order_of
                       and not self._hidden_cut_source(o)]
            for slot, obj in zip(sorted(order_of[o.Name] for o in members),
                                 members):
                order_of[obj.Name] = slot
        for host in self._body_pattern_hosts():
            # Un réseau vient avant ses copies, même quand une annulation
            # l'a rendu en fin de document : au plus tôt de leurs bases.
            copies = self._body_pattern_copies(host).values()
            bases = [o.Name for copy in copies for o in copy.Group
                     if self._is_pattern_base(o)]
            order_of[host.Name] = min(
                [order_of[host.Name]]
                + [order_of[name] for name in bases if name in order_of])
        for host in self._removal_hosts():
            # De même, une suppression vient avant ses étapes cachées.
            order_of[host.Name] = min(
                [order_of[host.Name]]
                + [order_of[part.Name] for part in self._removal_parts(host)
                   if part.Name in order_of])
        return order_of

    def _history_lines(self):
        """Lignes d'historique top-niveau de toute la pièce, dans l'ordre
        de l'arbre : fonctions et esquisses libres de chaque corps,
        surfaces, réseaux de corps, suppressions de corps."""
        doc = self._require_doc()
        consumed = self._consumed_sketches()
        lines = []
        for body in self._history_bodies():
            for obj in body.Group:
                if self._is_pattern_base(obj):
                    continue
                role = self._history_role(obj, consumed)
                if role in ("feature", "sketch"):
                    lines.append(obj)
        for obj in doc.Objects:
            if (self._is_surface_obj(obj)
                    and not self._is_internal_tool(obj)):
                lines.append(obj)
        lines.extend(self._body_pattern_hosts())
        lines.extend(self._removal_hosts())
        order_of = self._tree_order()
        lines.sort(key=lambda o: order_of.get(o.Name, -1))
        return lines

    def _history_rows(self, lines=None):
        consumed = self._consumed_sketches()
        order_of = self._tree_order()
        owners = {o.Name: b.Name for b in self._history_bodies()
                  for o in b.Group}
        rows = []
        for obj in (lines if lines is not None else self._history_lines()):
            role = self._history_role(obj, consumed)
            if role is None:
                continue
            rows.append({
                "name": obj.Name,
                "order": order_of.get(obj.Name, -1),
                "role": role,
                "body": owners.get(obj.Name),
            })
            if role == "pattern":
                # Ses copies naissent avec lui : la base de chacune est sa
                # première fonction, au rang du réseau.
                for copy in self._body_pattern_copies(obj).values():
                    base = next((o for o in copy.Group
                                 if self._is_pattern_base(o)), None)
                    if base is not None:
                        rows.append({"name": base.Name,
                                     "order": order_of.get(obj.Name, -1),
                                     "role": "feature", "body": copy.Name})
            if role == "remove":
                # Ses étapes cachées ôtent des solides à son rang.
                for part in self._removal_parts(obj):
                    rows.append({"name": part.Name,
                                 "order": order_of.get(obj.Name, -1),
                                 "role": "feature",
                                 "body": owners.get(part.Name)})
        # Un enlèvement : ses étapes cachées creusent les autres corps à son
        # rang, mais jamais avant ce qui les précède dans leur corps (un
        # enlèvement remonté au-dessus de fonctions de ce corps).
        named = {row["name"] for row in rows}
        for body in self._history_bodies():
            reached = -1
            for obj in body.Group:
                source = self._hidden_cut_source(obj)
                if not source:
                    reached = max(reached, order_of.get(obj.Name, -1))
                    continue
                if source not in named:
                    continue
                reached = max(reached, order_of.get(source, -1))
                at = next((i for i, row in enumerate(rows)
                           if row["order"] > reached), len(rows))
                rows.insert(at, {"name": obj.Name, "order": reached,
                                 "role": "feature", "body": body.Name})
        return rows

    def _apply_tips(self, tips):
        """Pose le Tip de chaque corps (``rollback_tips``). Une copie de
        réseau s'arrête au moins à sa base sous le réseau, et n'existe pas
        au-dessus."""
        doc = self._require_doc()
        for body_name, tip_name in tips.items():
            body = doc.getObject(body_name or "")
            if body is None:
                continue
            body.Tip = (self._tip_with_helpers(doc.getObject(tip_name))
                        if tip_name else None)

    def _set_bar_sketches(self, name=""):
        """L'esquisse sortie de sa fonction par la barre, sur son corps ;
        vide sur tous les autres."""
        for body in self._history_bodies():
            owned = bool(name) and any(o.Name == name for o in body.Group)
            self._set_bar_sketch(body, name if owned else "")

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
        # Toutes les fonctions de la pièce : une esquisse prise par un
        # liant (paroi mince, fonction rangée dans un autre corps) compte.
        for obj in [o for b in self._history_bodies() for o in b.Group]:
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            _, source = self._thin_chain(obj)
            for named in (linked, source):
                if named is not None:
                    used.add(named.Name)
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

        *feature* peut aussi être l'esquisse rangée sous une fonction : la
        barre se pose entre les deux, l'esquisse sort de sa fonction
        (au-dessus, éditable) et la fonction passe dessous. Le corps garde
        cette position dans ``FreeSolidBarSketch``.
        """
        from engine.kernel import (
            KernelError,
            rollback_tips,
        )
        self._require_body()
        # Ce qui est né à la barre y reste quand elle repart.
        self._persist_ranks()
        history = self._history_lines()
        if feature is None or not str(feature).strip():
            flags, tips = rollback_tips(self._history_rows(history), None)
            self._apply_tips(tips)
            self._apply_rollback_flags(flags)
            self._set_bar_sketches()
            self._recompute()
            return self.get_tree()
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        rows = self._history_rows(history)
        absorbed = (obj.Name not in {line.Name for line in history}
                    and self._absorbing_feature(obj) is not None)
        if absorbed:
            # Ni flag ni Tip pour elle : sa place dans l'ordre suffit.
            rows.append({"name": obj.Name, "role": "absorbed",
                         "order": self._tree_order().get(obj.Name, -1),
                         "body": getattr(self._history_body_of(obj),
                                         "Name", None)})
            rows.sort(key=lambda row: row["order"])
        elif obj.Name not in {row["name"] for row in rows}:
            raise KernelError(
                "« {} » n'est pas une ligne d'historique — la barre de "
                "retour se pose sur une fonction, une esquisse libre ou "
                "une surface".format(obj.Label))
        flags, tips = rollback_tips(rows, obj.Name)
        self._apply_tips(tips)
        self._apply_rollback_flags(flags)
        self._set_bar_sketches(obj.Name if absorbed else "")
        self._recompute()
        return self.get_tree()

    def _bar_line(self):
        """La ligne sous laquelle passe la barre de retour : ``None`` quand
        elle est en bas de l'arbre, ``""`` tout en haut, l'esquisse quand
        elle passe entre une esquisse et sa fonction."""
        for body in self._history_bodies():
            sketch = getattr(body, _BAR_SKETCH_PROP, "")
            if sketch:
                return sketch
        rolled = {o.Name for o in self._rolled_back_objects()}
        if not rolled:
            return None
        last = ""
        for line in self._history_lines():
            if line.Name in rolled:
                break
            last = line.Name
        return last

    def _set_bar_sketch(self, body, name):
        """Esquisse au-dessus de laquelle passe la barre, sortie de sa
        fonction ; vide sinon. Rien d'ajouté au corps tant qu'il n'y en a
        jamais eu."""
        if _BAR_SKETCH_PROP not in body.PropertiesList:
            if not name:
                return
            body.addProperty("App::PropertyString", _BAR_SKETCH_PROP,
                             "FreeSolid",
                             "Esquisse sortie de sa fonction par la barre")
        setattr(body, _BAR_SKETCH_PROP, name)

    def _absorbing_feature(self, obj):
        """Fonction sous laquelle l'esquisse *obj* est rangée dans son
        corps, ou None (esquisse libre, de surface, autre objet)."""
        if (getattr(obj, "TypeId", "") != "Sketcher::SketchObject"
                or self._is_thin_helper(obj)):
            return None
        if self._history_body_of(obj) is None:
            return None
        # Sa fonction peut être dans un autre corps (profil par un liant).
        owner = self._doc.getObject(
            self._consumed_sketches().get(obj.Name) or "")
        if (owner is None or not owner.isDerivedFrom("PartDesign::Feature")
                or self._history_body_of(owner) is None):
            return None
        return owner

    def _features_after_tips(self):
        """Fonctions volumiques de toute la pièce sous la barre : après le
        Tip de leur corps."""
        rolled = set()
        for body in self._history_bodies():
            group = list(body.Group)
            tip = getattr(body, "Tip", None)
            tip_at = group.index(tip) if tip in group else -1
            rolled.update(o.Name for o in group[tip_at + 1:]
                          if o.isDerivedFrom("PartDesign::Feature"))
        return rolled

    def _unabsorbed_sketches(self):
        """Esquisses sorties de leur fonction par la barre de retour :
        elles sont au-dessus de la barre, leur fonction en dessous.

        La barre passe après le Tip, ou après l'esquisse posée par
        ``set_tip`` si elle vient plus loin. Une esquisse absorbée avant
        cette position, dont la fonction est après le Tip, en sort.
        """
        consumed = self._consumed_sketches()
        rolled = self._features_after_tips()
        out = []
        for body in self._history_bodies():
            group = list(body.Group)
            index = {o.Name: i for i, o in enumerate(group)}
            tip = getattr(body, "Tip", None)
            tip_at = index.get(tip.Name, -1) if tip is not None else -1
            bar_at = max(tip_at, index.get(
                getattr(body, _BAR_SKETCH_PROP, "") or "", -1))
            for obj in group[:bar_at + 1]:
                if (obj.TypeId != "Sketcher::SketchObject"
                        or self._is_thin_helper(obj)):
                    continue
                # Sa fonction, dans ce corps ou un autre, est sous la barre.
                if consumed.get(obj.Name) in rolled:
                    out.append(obj.Name)
        return out

    def _rolled_back_objects(self):
        """Tout ce qui est sous la barre de retour, dans l'ordre de l'arbre :
        fonctions après le Tip et leurs esquisses (sauf celles sorties
        au-dessus), esquisses libres, surfaces et réseaux de corps
        reculés."""
        consumed = self._consumed_sketches()
        above = set(self._unabsorbed_sketches())
        rolled = self._features_after_tips()
        features = {o.Name for b in self._history_bodies() for o in b.Group
                    if o.isDerivedFrom("PartDesign::Feature")}
        out = []
        for body in self._history_bodies():
            group = list(body.Group)
            index = {o.Name: i for i, o in enumerate(group)}
            tip = getattr(body, "Tip", None)
            tip_at = index.get(tip.Name, -1) if tip is not None else -1
            for i, obj in enumerate(group):
                if self._is_thin_helper(obj) or self._is_pattern_base(obj):
                    continue  # part avec sa fonction, ou avec la copie
                if obj.isDerivedFrom("PartDesign::Feature"):
                    if i > tip_at:
                        out.append(obj)
                elif (obj.TypeId == "Sketcher::SketchObject"
                        and obj.Name not in above):
                    # Sous sa fonction, même d'un autre corps : avec elle.
                    owner = consumed.get(obj.Name)
                    if owner in features:
                        if owner in rolled:
                            out.append(obj)
                    elif self._is_rolled_back(obj):
                        out.append(obj)
        for obj in self._doc.Objects:
            if (self._is_surface_obj(obj)
                    and not self._is_internal_tool(obj)
                    and self._is_rolled_back(obj)):
                out.append(obj)
        out.extend(host for host in self._body_pattern_hosts()
                   if self._body_pattern_rolled_back(host))
        out.extend(host for host in self._removal_hosts()
                   if self._is_rolled_back(host))
        order_of = self._tree_order()
        out.sort(key=lambda o: order_of.get(o.Name, -1))
        return out

    def delete_rolled_back(self):
        """Supprimer tout ce qui est sous la barre de retour, en une étape
        d'annulation : fonctions, leurs esquisses, esquisses libres et
        surfaces reculées. Une esquisse sortie au-dessus de la barre reste,
        libre."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        victims = [o.Name for o in self._rolled_back_objects()]
        if not victims:
            raise KernelError("rien sous la barre de retour")
        # De la fin vers le début : rien de ce qui reste ne dépend de ce
        # qui part.
        for name in reversed(victims):
            if doc.getObject(name) is not None:
                self.delete_feature(name)
        return self.get_tree()

    def tip_to_end(self):
        """Barre de retour en bout d'historique — l'état final."""
        from engine.kernel import (
            KernelError,
            rollback_tips,
        )
        self._require_body()
        self._persist_ranks()
        history = self._history_lines()
        if not history:
            raise KernelError("aucune fonction dans la pièce")
        flags, tips = rollback_tips(
            self._history_rows(history), history[-1].Name)
        self._apply_tips(tips)
        self._apply_rollback_flags(flags)
        self._set_bar_sketches()
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
        if "FreeSolidRemoveBodies" in obj.PropertiesList:
            # Les corps qu'elle supprimait reviennent.
            self._drop_removal(obj)
            self._recompute()
            return self._current_tree()
        # Réseau de corps, copie, corps concernés : leurs règles d'abord.
        handled = self._repetition_delete(obj)
        if handled is not None:
            return handled
        leftovers = self._scope_before_delete(obj)
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
        # Le solide d'avant la première fonction de la chaîne (un
        # auxiliaire peut précéder la fonction).
        chain = [o for o in [obj] + thin_helpers
                 if o.isDerivedFrom("PartDesign::Feature")]
        base = None
        if chain:
            first = min(chain, key=lambda o: order.get(o.Name, -1))
            base = getattr(first, "BaseFeature", None)
        if parent_body is not None and getattr(parent_body, "Tip", None) in (
                [obj] + thin_helpers):
            parent_body.Tip = base
        if chain:
            self._relink_chain(parent_body, chain, base)
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
        self._remove_named_parts(leftovers)
        # Un axe interne de révolution sans fonction ne garde pas le corps.
        self._drop_unused_axis_tools()
        self._drop_emptied_body(parent_body)
        try:
            if self._assembly:
                doc.recompute()
            else:
                self._recompute()
        except KernelError as exc:
            raise KernelError(
                "{} supprimé, mais l'aval casse : {}".format(label, exc))
        return self._current_tree()

    def _drop_emptied_body(self, body):
        """Un corps né d'une extrusion non fusionnée part avec sa dernière
        fonction : le corps n'était que son résultat."""
        if (body is None or not getattr(body, "FreeSolidNewBody", False)
                or list(body.Group)):
            return
        was_active = self._body is body
        self._require_doc().removeObject(body.Name)
        if was_active:
            self._body = self._body_of_newest()

    @staticmethod
    def _relink_chain(body, removed, base):
        """Rebranche sur ``base`` les fonctions qui partaient d'un objet
        supprimé. ``doc.removeObject`` leur laisse une base vide : une
        fonction retirée au milieu de la chaîne emportait tout l'amont."""
        for other in getattr(body, "Group", None) or ():
            if other in removed or not other.isDerivedFrom(
                    "PartDesign::Feature"):
                continue
            if getattr(other, "BaseFeature", None) in removed:
                other.BaseFeature = base

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
        # Tout le ``Group`` de chaque corps : ``get_tree`` émet chaque objet
        # — une esquisse consommée revient en ``children``, un plan ou un
        # axe de référence n'est pas un ``PartDesign::Feature`` mais reste
        # un nœud. Filtrer ici ferait diverger l'ensemble des cibles de ce
        # que le payload expose, et perdrait des arêtes réelles en silence.
        for obj in [o for b in self._history_bodies() for o in b.Group]:
            if (getattr(obj, "FreeSolidAxisTool", False)
                    or self._is_thin_helper(obj)
                    or self._is_pattern_base(obj)):   # hors arbre
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
            # Nœuds d'une section de plugin : le plugin les reconnaît,
            # le noyau ne connaît pas son métier.
            if self._plugins.run_tree_node(self, obj):
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

    def _body_tree_items(self, body, entry, consumed, unabsorbed):
        """Lignes d'arbre d'un corps, dans son ordre : chaque fonction avec
        ses esquisses en ``children``. ``entry`` : la ligne d'un objet."""
        users = self._sketch_consumers(body)
        labels = {o.Name: o.Label for o in body.Group}
        # Les esquisses du corps, puis celles d'autres corps qu'une
        # fonction d'ici prend par un liant : elles se rangent sous elle.
        sketches = [o for o in body.Group
                    if o.TypeId == "Sketcher::SketchObject"]
        for name, owner in consumed.items():
            other = self._doc.getObject(name)
            if (owner in labels and other is not None
                    and other.TypeId == "Sketcher::SketchObject"
                    and other.Name not in labels):
                sketches.append(other)
        items = []
        for obj in body.Group:
            if (getattr(obj, "FreeSolidAxisTool", False)
                    or getattr(obj, "FreeSolidPierce", "")
                    or self._is_pattern_base(obj)):
                # Axe, lieur de percée : outils ; base d'une copie : la
                # ligne du réseau la porte. Hors arbre.
                continue
            if (obj.TypeId == "Sketcher::SketchObject"
                    and obj.Name in consumed) or self._is_thin_helper(obj):
                continue
            item = entry(obj)
            children = []
            for o in sketches:
                owners = users.get(o.Name, [])
                if consumed.get(o.Name) != obj.Name and obj.Name not in owners:
                    continue
                child = entry(o)
                if o.Name in unabsorbed and consumed.get(o.Name) == obj.Name:
                    # Au-dessus de la barre, sa fonction en dessous.
                    child["unabsorbed"] = True
                if len(owners) > 1:
                    # Esquisse partagée : affichée sous chaque fonction.
                    child["shared"] = [labels.get(n, n) for n in owners
                                       if n != obj.Name]
                children.append(child)
            if children:
                item["children"] = children
            items.append(item)
        return items

    def _name_body(self, body, label):
        """Nommer un corps à la main : le dossier garde ce nom au lieu de
        celui de sa dernière fonction."""
        body.Label = label
        if _NAMED_PROP not in body.PropertiesList:
            body.addProperty("App::PropertyBool", _NAMED_PROP, "FreeSolid",
                             "Nommé à la main : le dossier garde ce nom")
        setattr(body, _NAMED_PROP, True)

    def _body_title(self, body, tip=None):
        """Nom d'un corps dans son dossier : celui de la dernière fonction
        qui l'a changé, comme dans les modeleurs courants. Une copie de
        réseau sans fonction à elle : « réseau[n] ». Le sien quand on l'a
        nommé, quand il est vide ou n'a qu'une forme importée. ``tip`` :
        le corps arrêté à cette fonction."""
        current = tip is None or tip is getattr(body, "Tip", None)
        tip = self._title_tip(body, tip)
        if tip is None:
            return body.Label
        if self._is_pattern_base(tip):
            host = self._body_pattern_host_of(tip)
            copies = list(self._body_pattern_copies(host).values()) \
                if host is not None else []
            if body in copies:
                return "{}[{}]".format(host.Label, copies.index(body) + 1)
            return body.Label
        if tip.TypeId == "PartDesign::FeatureBase":
            return body.Label
        owner = self._thin_owner(tip)
        if current and getattr(owner, "FreeSolidScope", ""):
            # Un enlèvement qui creuse d'autres corps les nomme tous :
            # numérotés, comme les solides d'un corps — sauf ceux qu'il a
            # vidés, qui ne sont plus au dossier.
            sharing = [other for other in self._history_bodies()
                       if self._title_owner(other) is owner
                       and self._body_has_solid(other)]
            if len(sharing) > 1 and body in sharing:
                return "{}[{}]".format(owner.Label, sharing.index(body) + 1)
        return owner.Label

    def _title_tip(self, body, tip=None):
        """La fonction où lire le nom du dossier de ``body`` : sa pointe, ou
        ``tip``. None s'il est nommé à la main ou vide."""
        tip = tip if tip is not None else getattr(body, "Tip", None)
        while getattr(tip, "FreeSolidRemoveof", ""):
            tip = tip.BaseFeature  # ôter un solide ne change pas les autres
        return None if getattr(body, _NAMED_PROP, False) else tip

    def _title_owner(self, body):
        """La fonction dont ``body`` porte le nom à sa pointe, ou None (nommé
        à la main, vide, base importée ou copie de réseau)."""
        tip = self._title_tip(body)
        if (tip is None or self._is_pattern_base(tip)
                or tip.TypeId == "PartDesign::FeatureBase"):
            return None
        return self._thin_owner(tip)

    def _mark_rolled_back(self, body, items):
        """``rolled_back`` sur les fonctions volumiques : vrai après le Tip
        de leur corps. La barre est commune à tous les corps, chacun
        s'arrête à son Tip."""
        index = {o.Name: i for i, o in enumerate(body.Group)}
        tip = getattr(body, "Tip", None)
        tip_at = index.get(tip.Name, -1) if tip is not None else -1
        for item in items:
            obj = self._doc.getObject(item["name"])
            if obj.Name in index and obj.isDerivedFrom("PartDesign::Feature"):
                item["rolled_back"] = index[obj.Name] > tip_at

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
        from engine.vocab import type_key_for
        self._keep_active_body()
        body = self._require_body()
        order_of = self._tree_order()
        consumed = self._consumed_sketches()
        unabsorbed = set(self._unabsorbed_sketches())
        known_names = self._tree_known_names(body)
        removed = self._removed_names()

        def entry(obj):
            item = {
                "name": obj.Name,
                "label": obj.Label,
                "kind": label_for_type(obj.TypeId, self.lang),
                "type": obj.TypeId,
                "type_key": type_key_for(obj.TypeId),
                "error": "Invalid" in (obj.State or ()),
                "order": order_of.get(obj.Name, -1),
                "has_params": self._has_params(obj),
                "suppressible": self._is_suppressible(obj),
            }
            if item["suppressible"] and obj.Suppressed:
                item["suppressed"] = True
            if self._merge_editable(obj):
                # « Fusionner » : la réédition le montre coché ou non ; la
                # fonction part de son corps, sauf le premier volume.
                item["merged"] = self._is_merged(obj)
                item["alone"] = getattr(obj, "BaseFeature", None) is None
            # Un lissage, un balayage n'ont pas de cote : leurs corps fondus
            # ou creusés viennent même vides, leur réédition s'y rouvre.
            sweeps = obj.TypeId in self._SWEPT_TYPES and bool(
                self._other_bodies(obj.getParentGeoFeatureGroup()))
            fused = self._fused_bodies_of(obj)
            if fused or (sweeps and obj.TypeId in self._FUSING_TYPES):
                # Les corps qu'elle fond : la réédition les décoche.
                item["fused"] = [{"name": b.Name, "label": self._body_title(b)}
                                 for b in fused]
            cut = self._cut_bodies_of(obj)
            if cut or (sweeps and self._is_cut_source(obj)) or (
                    self._is_scope_pattern(obj) and self._other_bodies(
                        obj.getParentGeoFeatureGroup())):
                # Et ceux qu'un enlèvement creuse. Une répétition
                # d'enlèvements les donne même vides : sa réédition les
                # propose, une symétrie sans cote s'y rouvre.
                item["cut"] = [{"name": b.Name, "label": self._body_title(b)}
                               for b in cut]
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
            extrude = (self._extrude_state(obj)
                       if "FreeSolidTextString" not in obj.PropertiesList
                       else None)
            if extrude is not None:
                # Conditions de fin : la réédition rouvre le panneau de la
                # création.
                item["extrude"] = extrude
            if obj.TypeId == "PartDesign::Thickness":
                item["shell"] = {"outward": not bool(obj.Reversed)}
            if obj.TypeId == "PartDesign::Hole":
                hole = self._hole_state(obj)
                if hole is not None:
                    item["hole"] = hole
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
            self._repetition_tree_fields(obj, item)
            self._annotate_tree_links(item, obj, known_names)
            return item

        items = self._body_tree_items(body, entry, consumed, unabsorbed)
        self._mark_rolled_back(body, items)
        # Réseaux de corps : chacun à son rang, reculé quand ses copies
        # n'existent pas encore.
        items.extend(self._body_pattern_rows(body, entry))
        # Suppressions de corps : des lignes de la pièce, à leur rang.
        items.extend(self._removal_rows(entry))
        # Un seul arbre : l'histoire des autres corps s'y range par rang.
        # ``features`` reste celle du corps actif, sur laquelle les
        # commandes agissent ; chaque ligne d'ici porte son corps.
        other_items = []
        for other in self._history_bodies():
            if other is body:
                continue
            rows = self._body_tree_items(other, entry, consumed, unabsorbed)
            self._mark_rolled_back(other, rows)
            rows.extend(self._body_pattern_rows(other, entry))
            for item in rows:
                item["body"] = other.Name
            other_items.extend(rows)

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
            if obj.Name in removed:
                continue  # supprimé par une fonction au-dessus de la barre
            info = {
                "name": obj.Name,
                "label": self._body_title(obj),
                "type_key": type_key_for(obj.TypeId),
                "active": obj is body,
                "count": len([o for o in obj.Group
                              if (o.isDerivedFrom("PartDesign::Feature")
                                  or o.TypeId == "Sketcher::SketchObject")
                              and not self._is_thin_helper(o)]),
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "has_solid": self._body_has_solid(obj),
                "hidden": self._is_hidden(obj),
                "material": self._material_of(obj),
            }
            # Plusieurs solides : un corps chacun dans le dossier, avec
            # son nom, sa couleur, son masquage (engine/bodysolids.py).
            solids = self._body_solids(obj)
            if solids:
                info["solids"] = solids
            bodies.append(info)
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
        self._annotate_comments(other_items)
        self._annotate_comments(surfaces)
        self._annotate_folders(items)
        self._annotate_folders(other_items)
        for entry in surfaces:
            if self._is_hidden(self._doc.getObject(entry["name"])):
                entry["hidden"] = True
            if entry["name"] in removed:
                entry["removed"] = True  # hors du dossier, pas de l'histoire
        tree = {"body": body.Label, "tip": tip, "bodies": bodies,
                "planes": planes, "features": items,
                "other_features": other_items,
                "surfaces": surfaces,
                "variables": self.list_variables()["variables"],
                "configurations": self.list_configurations(),
                "options": self.document_options()}
        self._plugins.contribute_tree(self, tree)
        return tree

    @staticmethod
    def _meshed(shape, deviation, angle):
        """La forme dont on lit les facettes (``face.tessellate``). Sans
        ``angle`` : elle-même, qui garde son maillage d'une fois sur
        l'autre. Avec : une copie sans maillage, maillée à cet écart et
        cet angle — ``tessellate`` ne règle pas l'angle, et OCCT garderait
        sur la pièce le maillage le plus fin déjà fait. La copie a les
        faces dans le même ordre."""
        if angle is None or not shape.Faces:
            return shape
        import MeshPart
        copy = shape.copy(True, False)
        MeshPart.meshFromShape(Shape=copy, LinearDeflection=float(deviation),
                               AngularDeflection=float(angle), Relative=False)
        return copy

    def _face_mesh(self, face, face_id, deviation):
        """Tessellation d'une face + normales exactes ``normalAt(u, v)``.

        Une face plane a la même normale en tout point : elle se calcule
        au premier sommet et se répète, sans reprojeter les suivants.
        """
        from engine.surfaces import (
            is_bspline_surface, is_plane_surface, surface_uv,
        )
        vertices, triangles = face.tessellate(float(deviation))
        points = [(v.x, v.y, v.z) for v in vertices]
        planar = is_plane_surface(face)
        normals = []
        for vertex in vertices:
            if planar and normals:
                normals.append(normals[0])
                continue
            try:
                u, v = surface_uv(face, vertex.x, vertex.y, vertex.z)
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

    @staticmethod
    def _mark_face_solid(group, solid_of):
        """``solid`` : le rang du solide de la face, quand son corps en
        garde plusieurs — « Supprimer des corps » en vise un seul."""
        face = group.get("faceId")
        if solid_of is not None and isinstance(face, int) \
                and 0 <= face < len(solid_of) and solid_of[face] is not None:
            group["solid"] = solid_of[face]

    def tessellate(self, deviation=None):
        """Per-face tessellation of the body's current shape.

        Face-by-face on purpose — see ``protocol.pack_mesh``: picking works
        by construction because each OCCT face is its own index group.
        Sans ``deviation``, celle de la qualité d'image du document.
        """
        from . import protocol
        body = self._require_body()
        removed = self._removed_names()
        angle = None
        edge_deviation = None
        if deviation is None:
            deviation, angle, edge_deviation = self._display_mesh()
        self._report_progress("Maillage")
        shape = getattr(body, "Shape", None)
        if self._is_hidden(body):
            shape = None  # masqué : ni dessiné, ni visé
        faces = []
        splines = []
        hidden_faces, _, solid_tints = (
            self._solid_display(body) if shape is not None
            else (set(), set(), {}))
        if shape is not None and shape.Faces:
            for i, face in enumerate(self._meshed(shape, deviation, angle).Faces):
                if i in hidden_faces:
                    continue  # solide masqué : les autres gardent leurs ids
                packed, spline = self._face_mesh(face, i, deviation)
                faces.append(packed)
                splines.append(spline)
        mesh = protocol.pack_mesh(faces)
        producers = self._face_producers()
        face_colors = self._face_colors(body)
        solid_of = self._face_solids(body) if shape is not None else None
        for group, spline in zip(mesh.get("groups") or [], splines):
            if spline:
                group["spline"] = True
            self._mark_face_solid(group, solid_of)
            tint = face_colors.get(str(group.get("faceId")))
            if tint:
                group["color"] = tint
            elif str(group.get("faceId")) in solid_tints:
                # La couleur de son solide : pas une couleur de face.
                group["color"] = solid_tints[str(group.get("faceId"))]
                group["solid_tint"] = True
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
        # Les autres corps s'affichent comme le corps actif, face par face
        # et arêtes comprises : le clic sur l'une d'elles active son corps
        # (picking.js). Les numéros sont ceux qu'il aura une fois actif.
        # ``others`` reste le buffer combiné pour la compatibilité
        # (selftest p9_others_shown).
        other_bodies = []
        for obj in self._doc.Objects:
            if (obj.TypeId != "PartDesign::Body" or obj is body
                    or getattr(obj, "Shape", None) is None
                    or self._is_internal_tool(obj)
                    or self._is_hidden(obj) or obj.Name in removed):
                continue
            hidden_faces, hidden_edges, solid_tints = \
                self._solid_display(obj)
            other_faces = [
                self._face_mesh(face, i, deviation)[0]
                for i, face in enumerate(
                    self._meshed(obj.Shape, deviation, angle).Faces)
                if i not in hidden_faces]
            if not other_faces:
                continue
            packed = protocol.pack_mesh(other_faces)
            tints = {**solid_tints, **self._face_colors(obj)}
            solid_of = self._face_solids(obj)
            for group in packed["groups"]:
                tint = tints.get(str(group.get("faceId")))
                if tint:
                    group["color"] = tint
                self._mark_face_solid(group, solid_of)
            other_bodies.append({
                "name": obj.Name,
                "label": self._body_title(obj),
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "positions": packed["positions"],
                "normals": packed.get("normals"),
                "indices": packed["indices"],
                "groups": packed["groups"],
                "edges": protocol.pack_edges(self._body_edge_lines(
                    obj.Shape, edge_deviation or float(deviation) / 2,
                    skip=hidden_edges)),
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
                    or obj.Name in consumed or self._is_hidden(obj)
                    or obj.Name in removed):
                continue
            shape = getattr(obj, "Shape", None)
            if shape is None:
                continue
            # Arêtes numérotées comme « EdgeN » : bords de remplissage,
            # bord à prolonger, trajectoire — choisis dans la vue.
            edges = protocol.pack_edges(self._object_edge_lines(shape))
            if shape.Faces:
                surface_faces = []
                for i, face in enumerate(self._meshed(shape, deviation, angle).Faces):
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
        # Une esquisse sortie de sa fonction par la barre se dessine, comme
        # une libre : on l'a sortie pour la voir et la modifier.
        unabsorbed = [self._doc.getObject(n)
                      for n in self._unabsorbed_sketches()]
        for sk in self._free_sketches() + unabsorbed:
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

    def tessellate_edges(self, deviation=None):
        """Per-edge polylines of the body's current shape.

        Edge-by-edge on purpose — see ``protocol.pack_edges``: a raycast
        hit maps to exactly one OCCT edge, same contract as ``tessellate``
        for faces. Ids are Edge indices, so ``Edge{id+1}`` server-side.
        Les arêtes de couture (la jointure interne d'un cylindre, d'un
        cône…) ne sont pas tracées : elles ne bordent rien à l'œil. Les
        ids des autres restent ceux du noyau. Sans ``deviation``, celle de
        la qualité d'image du document (la moitié de celle des faces).
        """
        from . import protocol
        body = self._require_body()
        if deviation is None:
            deviation = self._display_mesh()[2]
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Edges or self._is_hidden(body):
            return protocol.pack_edges([])
        return protocol.pack_edges(self._body_edge_lines(
            shape, deviation, skip=self._solid_display(body)[1]))

    def _body_edge_lines(self, shape, deviation, skip=()):
        """Polylignes des arêtes d'un corps, coutures omises — celles du
        corps actif comme celles des autres corps de la vue. ``skip`` :
        rangs à taire (arêtes d'un solide masqué)."""
        seams = self._seam_edge_ids(shape)
        lines = []
        for i, edge in enumerate(shape.Edges):
            if i in seams or i in skip:
                continue
            try:
                points = edge.discretize(QuasiDeflection=float(deviation))
            except Exception:
                try:
                    points = edge.discretize(Number=24)
                except Exception:
                    continue  # arête dégénérée : les ids restent justes
            lines.append((i, [(p.x, p.y, p.z) for p in points],
                          float(edge.Length), self._circle_center(edge)))
        return lines

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
