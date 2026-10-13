"""Organisation de l'arbre : dossiers de fonctions et liens parents /
enfants.

Un dossier range des fonctions qui se suivent sous un nom ; l'arbre le
replie. Il est rangé sur le corps (``FreeSolidFolders``, JSON
{fonction: dossier}) et n'agit pas sur la reconstruction. Les parents
d'une fonction sont ce sur quoi elle s'appuie (esquisse, arêtes, plans…),
ses enfants ce qui s'appuie sur elle — sans compter la simple suite de
l'historique. Les imports FreeCAD restent dans les méthodes ;
``clean_folder_name`` est testée en CI.
"""

import json

#: Liens qui ne disent rien de la conception : la suite de l'historique
#: et l'appartenance au corps.
_CHAIN_PROPS = frozenset({"BaseFeature", "_Body", "Group", "Origin",
                          "Tip", "ExpressionEngine"})


def clean_folder_name(name):
    """Nom de dossier nettoyé (1 à 60 caractères), ou "" pour aucun."""
    return str(name or "").strip()[:60]


def _linked(value):
    """Objets d'une valeur de propriété de lien (seuls, en liste, avec
    sous-éléments)."""
    out = []
    items = value if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if isinstance(item, (list, tuple)):
            out.extend(_linked(item[0] if item else None))
        elif hasattr(item, "TypeId") and hasattr(item, "Name"):
            out.append(item)
    return out


class TreeOrgMixin:
    """Ops : set_folder, feature_relations."""

    def _folders(self, body):
        raw = getattr(body, "FreeSolidFolders", "") or ""
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        return {str(k): str(v) for k, v in data.items() if v}

    def _annotate_folders(self, items):
        folders = self._folders(self._require_body())
        for item in items or ():
            folder = folders.get(item.get("name", ""))
            if folder:
                item["folder"] = folder

    def set_folder(self, features, folder=""):
        """Range des fonctions dans le dossier ``folder`` (``""`` : les
        sort de leur dossier)."""
        from engine.kernel import KernelError
        body = self._require_body()
        doc = self._require_doc()
        names = [str(n) for n in features or ()]
        if not names or any(doc.getObject(n) is None for n in names):
            raise KernelError("choisissez les fonctions à ranger")
        folder = clean_folder_name(folder)
        folders = self._folders(body)
        for name in names:
            if folder:
                folders[name] = folder
            else:
                folders.pop(name, None)
        if "FreeSolidFolders" not in body.PropertiesList:
            body.addProperty("App::PropertyString", "FreeSolidFolders",
                             "FreeSolid")
            body.setEditorMode("FreeSolidFolders", 2)
        body.FreeSolidFolders = json.dumps(folders)
        return self.get_tree()

    def rename_folder(self, folder, name=""):
        """Renomme un dossier ; un nom vide le défait (ses fonctions
        reviennent à la racine)."""
        body = self._require_body()
        old = clean_folder_name(folder)
        new = clean_folder_name(name)
        folders = {k: (new if v == old else v)
                   for k, v in self._folders(body).items()}
        folders = {k: v for k, v in folders.items() if v}
        if "FreeSolidFolders" in body.PropertiesList:
            body.FreeSolidFolders = json.dumps(folders)
        return self.get_tree()

    def _links_of(self, obj):
        found = []
        for prop in obj.PropertiesList:
            if prop in _CHAIN_PROPS:
                continue
            if "Link" not in obj.getTypeIdOfProperty(prop):
                continue
            try:
                found.extend(_linked(getattr(obj, prop)))
            except Exception:  # noqa: BLE001
                continue
        return found

    def feature_relations(self, feature):
        """Parents et enfants d'une fonction, dans l'ordre du document."""
        from engine.kernel import KernelError
        from engine.vocab import label_for_type
        doc = self._require_doc()
        obj = doc.getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        known = self._tree_known_names(self._require_body())
        order = {o.Name: i for i, o in enumerate(doc.Objects)}

        def entry(other):
            return {"name": other.Name, "label": other.Label,
                    "kind": label_for_type(other.TypeId, self.lang)}

        parents = {o.Name: o for o in self._links_of(obj)
                   if o.Name in known and o is not obj}
        children = {o.Name: o for o in obj.InList
                    if o.Name in known and o is not obj
                    and obj in self._links_of(o)}
        by_order = lambda objs: sorted(objs, key=lambda o: order.get(o.Name, 0))  # noqa: E731
        return {"parents": [entry(o) for o in by_order(parents.values())],
                "children": [entry(o) for o in by_order(children.values())]}
