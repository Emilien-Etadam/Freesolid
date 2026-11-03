"""Fondre d'autres corps dans celui d'un volume ajouté.

Option « Fusionner » d'une extrusion, d'une révolution, d'un lissage ou
d'un balayage : sans liste, le volume fond les corps qu'il touche, comme
les modeleurs courants (``_touched_bodies``) ; ``bodies`` les choisit.

Un combiner caché (``PartDesign::Boolean`` Fuse), juste après la
fonction, tient les corps fondus : il la suit (désactiver, supprimer,
barre de retour) et ces corps quittent le dossier tant qu'il agit
(``_absorbed_bodies``). À la réédition, « Corps fondus » le règle
(``_set_fused_bodies``), et « Fusionner » d'une extrusion ou d'une
révolution se change (``_set_merge``) : décochée, la fonction sort de
son corps pour un corps neuf (``_detach_feature``).

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel.
"""


class BodyFuseMixin:
    #: Volumes ajoutés qui fondent d'autres corps (``bodies``).
    _FUSING_TYPES = ("PartDesign::Pad", "PartDesign::Revolution",
                     "PartDesign::AdditiveLoft", "PartDesign::AdditivePipe")
    #: Lissages et balayages, ajoutés ou ôtés.
    _SWEPT_TYPES = ("PartDesign::AdditiveLoft", "PartDesign::AdditivePipe",
                    "PartDesign::SubtractiveLoft",
                    "PartDesign::SubtractivePipe")

    # ---------- à la création ----------

    def _result_body(self, profiles, merge, body, conditions=None,
                     bodies=None):
        """Corps où ranger un volume (extrusion, révolution, lissage,
        balayage) : ``(corps, nouveau, corps à fondre)``.

        Fusionner : le corps actif, ou ``body`` ; ``bodies``, d'autres
        corps que la fonction y fond (``_fuse_bodies``) — sans l'un ni
        l'autre, ceux qu'elle touche (corps à fondre None,
        ``_fuse_result``). Sinon un nouveau corps — sauf si les esquisses
        sont seules dans le leur, qui le devient. Une face d'arrivée se
        clique sur le corps actif : elle ne vaut que là. ``conditions`` :
        celles d'une extrusion."""
        from engine.kernel import KernelError
        from engine.extrude import ExtrudeError, check_new_body
        conditions = conditions or {}
        doc = self._require_doc()
        active = self._require_body()
        if merge:
            target = active if body is None else self._listed_body(body)
            if target is not active and (
                    conditions.get("cond") == "face"
                    or conditions.get("cond2") == "face"):
                raise KernelError(
                    "jusqu'à la face : fusionnez avec le corps actif, "
                    "celui de la face cliquée")
            if bodies is None and body is None:
                return target, False, None
            fused = self._listed_bodies(bodies or [], target)
            for other in fused:
                self._refuse_unfusable(other, target)
            return target, False, fused
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
            return home, False, []
        return self._new_result_body(), True, []

    def _new_result_body(self):
        """Le corps neuf d'une fonction non fusionnée : il part avec sa
        dernière fonction (``_drop_emptied_body``)."""
        made = self._require_doc().addObject("PartDesign::Body", "Body")
        made.Label = self._t("Corps")
        made.addProperty("App::PropertyBool", "FreeSolidNewBody", "FreeSolid",
                         "Né d'une fonction non fusionnée")
        made.FreeSolidNewBody = True
        return made

    def _refuse_unfusable(self, other, body, own=None):
        """Refuse de fondre ``other`` dans ``body`` : un combiner autre que
        ``own`` le tient déjà, ou c'est une copie de réseau qui suit
        ``body`` — l'y fondre bouclerait le graphe."""
        from engine.kernel import KernelError
        self._refuse_held_body(other, own)
        if body in (other.OutListRecursive or ()):
            raise KernelError(
                "« {} » suit « {} » : il ne s'y fond pas".format(
                    self._body_title(other), self._body_title(body)))

    def _refuse_held_body(self, tool, own=None):
        """Refuse un corps qu'un combiner tient déjà, même sous la barre
        (où il reparaît) : FreeCAD l'ôterait sans bruit de ce combiner.
        ``own`` : le combiner qu'on règle."""
        from engine.kernel import KernelError
        host = self._holder_of(tool, own)
        if host is not None:
            raise KernelError(
                "« {} » est déjà fondu dans « {} » par une fonction "
                "plus bas : un corps ne se fond qu'une fois".format(
                    self._body_title(tool), self._body_title(host)))

    def _holder_of(self, tool, own=None):
        """Le corps dont un combiner (autre que ``own``) tient ``tool``,
        ou None."""
        for host in self._history_bodies():
            for obj in host.Group:
                if (obj.TypeId == "PartDesign::Boolean" and obj is not own
                        and tool in self._boolean_tools(obj)):
                    return host
        return None

    def _fuse_result(self, body, feature, fused):
        """Le combiner caché de ``feature`` ; ``fused`` None : les corps
        qu'elle touche, comme « Fusionner » le veut (``_touched_bodies``)
        — il faut d'abord sa forme, d'où un premier recalcul. Le premier
        volume d'un corps vide le fonde sans rien fondre : ce corps a été
        créé pour lui (bouton « Corps »)."""
        if fused is None:
            candidates = (self._merge_candidates(body)
                          if getattr(feature, "BaseFeature", None) is not None
                          else [])
            fused = []
            if candidates:
                self._recompute()
                fused = self._touched_bodies(body, feature, candidates)
        return self._fuse_bodies(body, feature, fused)

    def _merge_candidates(self, body):
        """Les corps que « Fusionner » peut fondre dans ``body`` : présents
        à la barre, libres (aucun combiner ne les tient), et qui ne
        suivent pas ``body`` (une copie de réseau bouclerait le graphe)."""
        return [other for other in self._other_bodies(body)
                if body not in (other.OutListRecursive or ())
                and self._holder_of(other) is None]

    def _touched_bodies(self, body, feature, candidates):
        """Parmi ``candidates``, les corps que touche le volume ajouté par
        ``feature`` : fondus ensemble, ils perdent un solide — un contact
        par une arête ou un point n'en est pas un. La cavité d'une paroi
        mince fermée n'est pas de la matière : un corps logé dedans n'est
        pas touché."""
        from engine.bodyscope import is_subtractive_type
        try:
            added = self._added_shape(body, feature)
            if added is None:
                return []
            for helper in self._thin_helpers(feature):
                if is_subtractive_type(helper.TypeId):
                    hollow = self._added_shape(body, helper)
                    if hollow is not None:
                        added = added.cut(hollow)
            box = added.BoundBox
            box.enlarge(1e-6)
            count = len(added.Solids)
        except Exception:  # noqa: BLE001 — OCCT : rien de sûr, rien de fondu
            return []
        touched = []
        for other in candidates:
            try:
                shape = other.Shape
                if (shape.isNull() or not shape.Solids
                        or not box.intersect(shape.BoundBox)):
                    continue
                joined = added.fuse(shape)
                if len(joined.Solids) < count + len(shape.Solids):
                    touched.append(other)
            except Exception:  # noqa: BLE001 — OCCT : pas de fusion, pas de contact
                continue
        return touched

    @staticmethod
    def _added_shape(body, feature):
        """La forme qu'ajoute ou ôte ``feature``, dans le repère global :
        ``AddSubShape`` est dans celui de la fonction (tourné pour une
        esquisse sur XZ), lui-même dans celui du corps. None si vide."""
        shape = getattr(feature, "AddSubShape", None)
        if shape is None or shape.isNull() or not shape.Solids:
            return None
        shape = shape.copy()
        shape.Placement = body.Placement.multiply(
            feature.Placement).multiply(shape.Placement)
        return shape

    def _fuse_bodies(self, body, feature, others):
        """Le combiner caché qui fond ``others`` dans ``body``, juste après
        ``feature`` : il la suit (désactiver, supprimer, barre de retour)
        et les corps fondus quittent le dossier tant qu'il agit
        (``_absorbed_bodies``)."""
        if not others:
            return []
        fuse = self._new_thin_helper(body, "PartDesign::Boolean",
                                     "MergeBodies", "Corps fondus")
        fuse.Type = "Fuse"
        self._set_boolean_tools(fuse, others)
        self._own_thin_helpers(feature, [fuse])
        # Posé à la réédition d'une fonction désactivée : désactivé aussi.
        fuse.Suppressed = bool(getattr(feature, "Suppressed", False))
        return [fuse]

    # ---------- à la réédition ----------

    def _fuse_helper(self, feature):
        """Le combiner caché d'un volume qui fond d'autres corps, ou None."""
        if getattr(feature, "TypeId", "") not in self._FUSING_TYPES:
            return None
        return next((h for h in self._thin_helpers(feature)
                     if h.TypeId == "PartDesign::Boolean"), None)

    def _fused_bodies_of(self, feature):
        """Les corps que ``feature`` fond dans le sien."""
        fuse = self._fuse_helper(feature)
        return self._boolean_tools(fuse) if fuse is not None else []

    def _set_fused_bodies(self, feature, names):
        """Réédition : les corps que ``feature`` fond dans le sien. Aucun,
        son combiner caché part ; un premier, il se pose juste après elle
        (et sa cavité). La liste est contrôlée avant tout changement."""
        from engine.kernel import KernelError
        if feature.TypeId not in self._FUSING_TYPES:
            raise KernelError("seul un volume ajouté fond d'autres corps")
        body = feature.getParentGeoFeatureGroup()
        fuse = self._fuse_helper(feature)
        # Les siens sont fondus : ``_listed_body`` les refuserait.
        others = self._listed_bodies(names, body,
                                     self._fused_bodies_of(feature))
        for other in others:
            self._refuse_unfusable(other, body, fuse)
        if fuse is None:
            if others:
                self._insert_fuse(body, feature, others)
            return
        if not others:
            base = getattr(fuse, "BaseFeature", None)
            if body.Tip is fuse:
                body.Tip = base
            self._relink_chain(body, [fuse], base)
            self._require_doc().removeObject(fuse.Name)
            return
        if self._PARKED_TOOLS in fuse.PropertiesList:
            setattr(fuse, self._PARKED_TOOLS, "")
        fuse.Group = []
        self._set_boolean_tools(fuse, others)

    def _insert_fuse(self, body, feature, others):
        """Le combiner caché d'une fonction rééditée, juste après elle : la
        pointe y passe le temps de l'insertion, les fonctions suivantes se
        rebranchent sur lui, puis elle revient."""
        anchor = self._tip_with_helpers(feature)
        tip = body.Tip
        previous = self._body
        self._body = body
        body.Tip = anchor
        try:
            self._fuse_bodies(body, feature, others)
        finally:
            self._body = previous
            if tip is not anchor:
                body.Tip = tip

    # ---------- « Fusionner », à la réédition ----------

    #: Volumes dont « Fusionner » se change à la réédition.
    _MERGE_EDIT_TYPES = ("PartDesign::Pad", "PartDesign::Revolution")

    def _merge_editable(self, obj):
        """Vrai si la réédition de ``obj`` montre « Fusionner »."""
        return (getattr(obj, "TypeId", "") in self._MERGE_EDIT_TYPES
                and "FreeSolidTextString" not in obj.PropertiesList)

    def _is_merged(self, feature):
        """« Fusionner » d'un volume : il part d'une fonction d'avant de son
        corps, ou il fond d'autres corps. Seul, le premier volume d'un
        corps l'a ouvert : il n'est pas fusionné."""
        return (getattr(feature, "BaseFeature", None) is not None
                or self._fuse_helper(feature) is not None)

    def _set_merge(self, feature, merge, bodies=None):
        """Réédition de « Fusionner », comme dans les modeleurs courants.
        Décochée : la fonction ne fond plus rien et, partie d'une fonction
        d'avant, elle sort de son corps pour un corps neuf
        (``_detach_feature``). Cochée sur le premier volume d'un corps :
        elle fond ``bodies`` ou, sans liste, les corps qu'elle touche
        (``_merge_touched``). Déjà fusionnée, ``bodies`` est la liste de
        tous les corps qu'elle fusionne, le sien compris
        (``_set_merged_bodies``)."""
        from engine.kernel import KernelError
        if not self._merge_editable(feature):
            raise KernelError("« Fusionner » ne se change que sur une "
                              "extrusion ou une révolution")
        if not isinstance(merge, bool):
            raise KernelError("merge : booléen attendu")
        if not merge and bodies:
            raise KernelError("sans « Fusionner », la fonction ne fond "
                              "aucun corps")
        merged = self._is_merged(feature)
        if merge and merged:
            if bodies is not None:
                self._set_merged_bodies(feature, bodies)
            return
        if merge == merged:
            return
        self._refuse_merge_change(feature)
        if merge:
            self._merge_touched(feature, bodies)
            return
        self._leave_body(feature, [])

    def _refuse_merge_change(self, feature):
        """Refuse de changer où se range une fonction sous la barre ou
        désactivée."""
        from engine.kernel import KernelError
        if feature.Name in self._features_after_tips():
            raise KernelError(
                "« {} » est sous la barre de retour : « Fusionner » se "
                "change au-dessus".format(feature.Label))
        if getattr(feature, "Suppressed", False):
            raise KernelError(
                "« {} » est désactivée : « Fusionner » se change sur une "
                "fonction active".format(feature.Label))

    def _set_merged_bodies(self, feature, names):
        """Les corps que fusionne une fonction déjà fusionnée, comme la zone
        d'action des modeleurs courants : le sien, si elle part d'une
        fonction d'avant, et ceux qu'elle fond. Le sien retiré, elle en
        sort pour un corps neuf qui fond les autres (``_leave_body``)."""
        from engine.kernel import KernelError
        if not isinstance(names, (list, tuple)):
            raise KernelError("bodies : une liste de corps attendue")
        body = feature.getParentGeoFeatureGroup()
        names = [str(name) for name in names]
        if (getattr(feature, "BaseFeature", None) is None
                or body.Name in names):
            self._set_fused_bodies(
                feature, [name for name in names if name != body.Name])
            return
        self._refuse_merge_change(feature)
        self._leave_body(feature, names)

    def _leave_body(self, feature, names):
        """``feature`` ne fond plus que ``names`` et, partie d'une fonction
        d'avant, sort de son corps pour un corps neuf
        (``_detach_feature``), qui les fond."""
        self._set_fused_bodies(feature, [])
        if getattr(feature, "BaseFeature", None) is not None:
            self._detach_feature(feature)
        if names:
            self._set_fused_bodies(feature, names)

    def _merge_touched(self, feature, bodies=None):
        """« Fusionner » coché sur le premier volume d'un corps : il fond
        ``bodies`` ou, comme à la création, les corps qu'il touche — parmi
        ceux qui existent déjà à son rang."""
        from engine.kernel import KernelError
        if bodies:
            self._set_fused_bodies(feature, bodies)
            return
        body = feature.getParentGeoFeatureGroup()
        candidates = [other for other in self._merge_candidates(body)
                      if self._born_before(other, feature)]
        touched = (self._touched_bodies(body, feature, candidates)
                   if candidates else [])
        if not touched:
            raise KernelError(
                "« {} » ne touche aucun autre corps à son rang : rien "
                "à fusionner".format(feature.Label))
        self._insert_fuse(body, feature, touched)

    def _born_before(self, other, feature):
        """Vrai si ``other`` a une fonction plus ancienne que ``feature`` :
        à son rang, ce corps existe déjà."""
        order_of = self._tree_order()
        rank = order_of.get(feature.Name, -1)
        return any(
            obj.isDerivedFrom("PartDesign::Feature") and order_of.get(
                self._hidden_cut_source(obj) or obj.Name, -1) < rank
            for obj in other.Group)

    def _detach_feature(self, feature):
        """« Fusionner » décoché : ``feature`` sort de son corps pour un corps
        neuf, avec ses objets cachés. Les fonctions d'après restent dans le
        sien et repartent de celle d'avant (FreeCAD les rebranche au
        retrait). L'esquisse ne bouge pas : le profil entre par un liant,
        et l'axe d'une révolution est repris dans le corps neuf, comme à la
        création dans un autre corps."""
        from engine.kernel import KernelError
        from engine.extrude import ExtrudeError, check_new_body
        if feature.TypeId == "PartDesign::Pad":
            state = self._extrude_state(feature)
            if state is None:
                raise KernelError(
                    "{} : conditions de fin que la réédition ne sait pas "
                    "changer".format(feature.Label))
            try:
                check_new_body(state["cond"], state["cond2"])
            except ExtrudeError as exc:
                raise KernelError(str(exc))
        body = feature.getParentGeoFeatureGroup()
        helpers = self._thin_helpers(feature)
        moving = [obj for obj in body.Group
                  if obj is feature or obj in helpers]
        token = (self._revolution_axis_token(feature)
                 if feature.TypeId == "PartDesign::Revolution" else None)
        sketch, subs = self._profile_of(feature)
        # Le profil est l'esquisse même, pas un liant (paroi mince, autre
        # corps) qui part avec la fonction.
        direct = (getattr(sketch, "TypeId", "") == "Sketcher::SketchObject"
                  and self._as_object(getattr(feature, "Profile", None))
                  is sketch)
        made = self._new_result_body()
        new = []
        if direct:
            # Un liant fait entrer l'esquisse dans le corps neuf.
            if token is None:
                new = self._profile_helpers(made, sketch, [])
            else:
                new = [self._profile_copy(made, sketch)]
        reference = (self._revolution_reference(sketch, token, made,
                                                feature=feature, made=new)
                     if token is not None else None)
        first = next(obj for obj in moving
                     if obj.isDerivedFrom("PartDesign::Feature"))
        base = first.BaseFeature
        if body.Tip in moving:
            body.Tip = base
        for obj in moving:
            body.removeObject(obj)
        for obj in moving:
            made.addObject(obj)
        if direct:
            copy = next(h for h in new
                        if h.TypeId == "PartDesign::SubShapeBinder")
            copy.Support = [(sketch, tuple(subs) or ("",))]
            if token is None:
                self._link_profile(feature, sketch, new)
            else:
                feature.Profile = copy
        if reference is not None:
            feature.ReferenceAxis = reference
        self._own_thin_helpers(feature, new)
        made.Tip = self._tip_with_helpers(feature)
