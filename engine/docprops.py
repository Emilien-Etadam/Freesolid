"""Commentaires des fonctions, propriétés du fichier, historique
d'annulation, corps et surfaces masqués, fonctions désactivées, liste
des erreurs de reconstruction.

Un commentaire est une note libre posée sur une fonction (propriété
cachée ``FreeSolidComment``) : l'arbre la montre en infobulle. Les
propriétés du fichier reprennent celles du document FreeCAD (auteur,
société, description) et ses propriétés libres (``Meta``) ; elles
partent avec le .FCStd. Les imports FreeCAD restent dans les méthodes ;
``undo_steps`` et ``clean_meta`` sont testées en CI.
"""

#: Préfixe des transactions ouvertes par ``dispatch`` (kernel.py).
_PREFIX = "freesolid-"


def undo_steps(names):
    """Noms de transactions → noms d'ops, du plus récent au plus ancien
    (l'ordre de FreeCAD). Une transaction étrangère garde son nom."""
    return [name[len(_PREFIX):] if name.startswith(_PREFIX) else name
            for name in names or ()]


def clean_meta(meta):
    """Propriétés libres valides : noms non vides, sans doublon ; une
    valeur vide retire la propriété."""
    out = {}
    for key, value in (meta or {}).items():
        key = str(key).strip()
        value = str(value if value is not None else "").strip()
        if key and value:
            out[key] = value
    return out


#: Champs fixes du panneau → propriété du document FreeCAD.
_DOC_FIELDS = {"author": "CreatedBy", "company": "Company",
               "description": "Comment"}


class DocPropsMixin:
    """Ops : commentaires, propriétés du fichier, historique."""

    def set_comment(self, feature, text=""):
        """Pose (ou retire, texte vide) le commentaire d'une fonction."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        text = str(text or "").strip()
        if "FreeSolidComment" not in obj.PropertiesList:
            if not text:
                return self._current_tree()
            obj.addProperty("App::PropertyString", "FreeSolidComment",
                            "FreeSolid")
            obj.setEditorMode("FreeSolidComment", 2)
        obj.FreeSolidComment = text
        return self._current_tree()

    def _annotate_comments(self, items):
        """Ajoute ``comment`` aux lignes d'arbre (et à leurs enfants)."""
        for item in items or ():
            obj = self._doc.getObject(item.get("name", ""))
            text = getattr(obj, "FreeSolidComment", "") if obj else ""
            if text:
                item["comment"] = text
            self._annotate_comments(item.get("children"))

    def document_properties(self):
        """Propriétés du fichier : champs fixes et propriétés libres."""
        doc = self._require_doc()
        out = {key: str(getattr(doc, prop, "") or "")
               for key, prop in _DOC_FIELDS.items()}
        out["custom"] = dict(getattr(doc, "Meta", {}) or {})
        return out

    def set_document_properties(self, values):
        """Remplace les propriétés du fichier : ``values`` porte les
        champs fixes (absents : inchangés) et ``custom`` (toutes les
        propriétés libres)."""
        doc = self._require_doc()
        for key, prop in _DOC_FIELDS.items():
            if key in values:
                setattr(doc, prop, str(values[key] or "").strip())
        if "custom" in values:
            doc.Meta = clean_meta(values["custom"])
        return self.document_properties()

    @staticmethod
    def _is_hidden(obj):
        return bool(getattr(obj, "FreeSolidHidden", False))

    def set_hidden(self, objects, hidden=True):
        """Masque (ou affiche) des corps ou des surfaces : ils restent dans
        la pièce et dans l'arbre, la vue ne les dessine plus. Enregistré
        dans le fichier."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        targets = []
        for name in objects or ():
            obj = doc.getObject(str(name))
            if obj is None or not (obj.TypeId == "PartDesign::Body"
                                   or self._is_surface_obj(obj)):
                raise KernelError("corps ou surface inconnu : {}".format(name))
            targets.append(obj)
        if not targets:
            raise KernelError("choisissez un corps ou une surface")
        for obj in targets:
            if "FreeSolidHidden" not in obj.PropertiesList:
                if not hidden:
                    continue
                obj.addProperty("App::PropertyBool", "FreeSolidHidden",
                                "FreeSolid")
                obj.setEditorMode("FreeSolidHidden", 2)
            obj.FreeSolidHidden = bool(hidden)
        return self._current_tree()

    def set_suppressed(self, features, suppressed=True):
        """Désactive (ou réactive) des fonctions : elles restent dans
        l'arbre avec leurs réglages, la pièce se calcule sans elles. Une
        fonction qui s'appuyait sur une fonction désactivée passe en
        erreur jusqu'à sa réactivation."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        targets = []
        for name in features or ():
            obj = doc.getObject(str(name))
            if obj is None or "Suppressed" not in obj.PropertiesList:
                raise KernelError(
                    "seule une fonction de volume se désactive : {}".format(
                        getattr(obj, "Label", name)))
            targets.append(obj)
        if not targets:
            raise KernelError("choisissez une fonction")
        from engine.kernel import KernelError as _Broken
        for obj in targets:
            obj.Suppressed = bool(suppressed)
        for _ in range(2):
            try:
                self._recompute()
                break
            except _Broken:
                # Les fonctions qui en dépendaient restent en erreur, sauf
                # si elles ont seulement perdu leurs arêtes ou faces le
                # temps de la désactivation : on les leur rend.
                if suppressed or not self._heal_missing_links(doc):
                    break
        return self._current_tree()

    @staticmethod
    def _heal_missing_links(doc):
        """Sous-éléments marqués manquants (« ?Edge1 ») pendant qu'une
        fonction d'appui était désactivée : rendus à leur nom (« Edge1 »).
        Vrai si un lien a été réparé."""
        healed = False
        for obj in doc.Objects:
            for prop in obj.PropertiesList:
                kind = obj.getTypeIdOfProperty(prop)
                if kind == "App::PropertyLinkSub":
                    value = getattr(obj, prop)
                    if value and any(str(s).startswith("?") for s in value[1]):
                        setattr(obj, prop, (value[0], [str(s).lstrip("?")
                                                       for s in value[1]]))
                        healed = True
                elif kind == "App::PropertyLinkSubList":
                    value = getattr(obj, prop) or []
                    if any(str(s).startswith("?") for _, subs in value
                           for s in (subs if isinstance(subs, (list, tuple))
                                     else [subs])):
                        setattr(obj, prop, [
                            (o, [str(s).lstrip("?") for s in (
                                subs if isinstance(subs, (list, tuple))
                                else [subs])])
                            for o, subs in value])
                        healed = True
        return healed

    def rebuild_errors(self):
        """Fonctions en erreur après la reconstruction, dans l'ordre du
        document, avec le message du modeleur (traduit quand il est
        connu)."""
        doc = self._require_doc()
        out = []
        for obj in doc.Objects:
            state = obj.State or ()
            if "Invalid" not in state and "Error" not in state:
                continue
            if self._is_internal_tool(obj):
                continue
            # « Fonction : ce qui ne va pas », traduit comme à la
            # reconstruction.
            message = self._broken_message(obj)
            out.append({"name": obj.Name, "label": obj.Label,
                        "kind": self._t_kind(obj), "message": message})
        return {"errors": out}

    def _t_kind(self, obj):
        from engine.vocab import label_for_type
        return label_for_type(obj.TypeId, self.lang)

    def undo_history(self):
        """Ce que Ctrl+Z et Ctrl+Y défont, du plus proche au plus loin."""
        doc = self._require_doc()
        return {"undo": undo_steps(doc.UndoNames),
                "redo": undo_steps(doc.RedoNames)}
