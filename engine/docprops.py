"""Commentaires des fonctions, propriétés du fichier, historique
d'annulation.

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

    def undo_history(self):
        """Ce que Ctrl+Z et Ctrl+Y défont, du plus proche au plus loin."""
        doc = self._require_doc()
        return {"undo": undo_steps(doc.UndoNames),
                "redo": undo_steps(doc.RedoNames)}
