"""Solides d'un corps : chacun est un corps dans le dossier.

FreeCAD garde dans un seul corps les solides qu'une fonction laisse
séparés — deux contours disjoints extrudés, un enlèvement qui coupe le
corps en deux. Le dossier en montre un par solide, comme les modeleurs
courants, et chacun garde sa couleur, son nom et son masquage.

Un solide n'a pas de nom stable : son rang change avec la forme. On le
reconnaît à l'origine de ses faces, remontée par l'historique
topologique de FreeCAD jusqu'à l'élément qui les a créées — le plus
souvent un trait d'esquisse. Elle survit à une cote changée et à un
congé ; les deux moitiés d'un solide coupé en deux en héritent. Deux
solides nés de contours différents n'ont aucune origine commune.

Les réglages vivent sur le corps (``FreeSolidSolids``, JSON) : une
entrée par solide réglé, avec ses origines. Ils ne valent que tant que
le corps garde plusieurs solides ; d'un seul, ce sont ceux du corps.

Les fonctions du module se testent sans FreeCAD ; les méthodes du mixin
importent le noyau à l'appel.
"""

import json

SOLIDS_PROP = "FreeSolidSolids"

#: Réglages d'un solide, et la valeur qui veut dire « aucun ».
_SETTINGS = ("label", "color", "hidden")


def match_entries(origins, entries):
    """Pour chaque solide (ensemble d'origines), l'indice de l'entrée qui
    en partage le plus — la plus récente à égalité — ou ``None`` quand
    aucune n'en partage."""
    matched = []
    for keys in origins:
        best, best_score = None, 0
        for index, entry in enumerate(entries):
            score = len(keys & set(entry.get("keys") or ()))
            if score and score >= best_score:
                best, best_score = index, score
        matched.append(best)
    return matched


def solid_rows(titles, entries, matched):
    """Ce que le dossier montre de chaque solide : ``label``, ``color``,
    ``hidden``. Le nom est celui qu'on lui a donné, sinon ``titles`` (la
    dernière fonction qui l'a changé) ; deux solides du même nom — deux
    contours d'une extrusion, les moitiés d'un solide coupé — se
    numérotent entre crochets."""
    rows = []
    for title, index in zip(titles, matched):
        entry = entries[index] if index is not None else {}
        rows.append({
            "label": entry.get("label") or title,
            "color": entry.get("color") or None,
            "hidden": bool(entry.get("hidden")),
        })
    names = [row["label"] for row in rows]
    seen = {}
    for row in rows:
        if names.count(row["label"]) > 1:
            name = row["label"]
            seen[name] = seen.get(name, 0) + 1
            row["label"] = "{}[{}]".format(name, seen[name])
    return rows


def set_entry(entries, matched, solid, keys, **changes):
    """Règle un solide. Son entrée prend ses origines du moment ; quand
    elle vaut aussi pour un autre solide (deux moitiés), le solide en
    reçoit une à lui, copie de la partagée. Un réglage vide (``None``,
    ``""``, ``False``) s'efface ; une entrée sans réglage disparaît.
    Renvoie la nouvelle liste."""
    entries = [dict(entry) for entry in entries]
    index = matched[solid]
    if index is None or matched.count(index) > 1:
        entry = dict(entries[index]) if index is not None else {}
        entries.append(entry)
    else:
        entry = entries[index]
    entry["keys"] = sorted(keys)
    for name, value in changes.items():
        if value in (None, "", False):
            entry.pop(name, None)
        else:
            entry[name] = value
    return [e for e in entries if any(e.get(name) for name in _SETTINGS)]


class BodySolidsMixin:
    def _stored_solids(self, body):
        raw = getattr(body, SOLIDS_PROP, "") or ""
        try:
            entries = json.loads(raw) if raw else []
        except ValueError:
            return []
        return [e for e in entries if isinstance(e, dict)] \
            if isinstance(entries, list) else []

    def _solid_origins(self, body):
        """Origines des faces de chaque solide, dans l'ordre de
        ``Shape.Solids`` : « objet|nom » de l'élément d'où la face vient.
        Vide pour un corps d'un seul solide."""
        shape = getattr(body, "Shape", None)
        tip = getattr(body, "Tip", None)
        if shape is None or tip is None or len(shape.Solids) < 2:
            return []
        reverse = shape.ElementReverseMap
        index_of = {}
        for i, face in enumerate(shape.Faces):
            index_of.setdefault(face.hashCode(), i)
        origins = []
        for solid in shape.Solids:
            keys = set()
            for face in solid.Faces:
                i = index_of.get(face.hashCode())
                if i is None:
                    i = next((j for j, other in enumerate(shape.Faces)
                              if other.isSame(face)), None)
                indexed = "Face{}".format(i + 1 if i is not None else "?")
                mapped = reverse.get(indexed)
                history = []
                if mapped:
                    try:
                        history = tip.getElementHistory(mapped)
                    except Exception:  # noqa: BLE001
                        history = []
                if history:
                    source, name = history[-1][0], history[-1][1]
                    keys.add("{}|{}".format(source.Name, name))
                else:
                    keys.add("{}|{}".format(tip.Name, mapped or indexed))
            origins.append(keys)
        return origins

    def _solid_authors(self, body):
        """Pour chaque solide, la dernière fonction qui l'a changé, comme
        le nom d'un corps dans les modeleurs courants. On remonte
        l'historique tant que la forme d'avant garde un solide identique
        (volume, aire, centre)."""
        def signature(solid):
            center = solid.CenterOfMass
            return tuple(round(v, 6) for v in (
                solid.Volume, solid.Area, center.x, center.y, center.z))

        tip = body.Tip
        pending = {i: signature(solid)
                   for i, solid in enumerate(tip.Shape.Solids)}
        authors = [tip] * len(pending)
        feature = tip
        while pending and feature is not None:
            base = getattr(feature, "BaseFeature", None)
            shape = getattr(base, "Shape", None) if base is not None else None
            before = ({signature(solid) for solid in shape.Solids}
                      if shape is not None else set())
            for i, sig in list(pending.items()):
                if sig not in before:
                    authors[i] = feature
                    del pending[i]
            feature = base
        return authors

    def _body_solids(self, body):
        """Les solides d'un corps qui en garde plusieurs, tels que le
        dossier les montre (``solid_rows``) ; vide pour un seul. Un corps
        nommé à la main, ou à la base importée, donne son nom à tous."""
        origins = self._solid_origins(body)
        if not origins:
            return []
        titles = []
        for feature in self._solid_authors(body):
            if (feature is body.Tip
                    or getattr(body, "FreeSolidNamed", False)
                    or feature.TypeId == "PartDesign::FeatureBase"):
                titles.append(self._body_title(body))
            else:
                titles.append(self._thin_owner(feature).Label)
        entries = self._stored_solids(body)
        return solid_rows(titles, entries, match_entries(origins, entries))

    def _set_solid(self, body, solid, **changes):
        """Règle le solide ``solid`` (rang dans ``Shape.Solids``)."""
        from engine.kernel import KernelError
        origins = self._solid_origins(body)
        if not 0 <= int(solid) < len(origins):
            raise KernelError("solide inconnu : {}".format(solid))
        entries = self._stored_solids(body)
        updated = set_entry(entries, match_entries(origins, entries),
                            int(solid), origins[int(solid)], **changes)
        if SOLIDS_PROP not in body.PropertiesList:
            body.addProperty("App::PropertyString", SOLIDS_PROP, "FreeSolid",
                             "Réglages de chaque solide du corps")
            body.setEditorMode(SOLIDS_PROP, 2)
        setattr(body, SOLIDS_PROP, json.dumps(updated))

    def _solid_face_edges(self, body):
        """Rang du solide de chaque face et de chaque arête du corps."""
        shape = body.Shape
        face_of = {}
        edge_of = {}
        for position, solid in enumerate(shape.Solids):
            for face in solid.Faces:
                face_of.setdefault(face.hashCode(), position)
            for edge in solid.Edges:
                edge_of.setdefault(edge.hashCode(), position)
        faces = [face_of.get(f.hashCode()) for f in shape.Faces]
        edges = [edge_of.get(e.hashCode()) for e in shape.Edges]
        return faces, edges

    def _solid_display(self, body):
        """Ce que la vue retire et teinte d'un corps à plusieurs solides :
        ``(faces masquées, arêtes masquées, {face: couleur})``, en rangs
        de face et d'arête du corps."""
        rows = self._body_solids(body)
        if not any(row["hidden"] or row["color"] for row in rows):
            return set(), set(), {}
        faces, edges = self._solid_face_edges(body)
        hidden = {i for i, row in enumerate(rows) if row["hidden"]}
        tints = {i: row["color"] for i, row in enumerate(rows)
                 if row["color"]}
        return ({i for i, s in enumerate(faces) if s in hidden},
                {i for i, s in enumerate(edges) if s in hidden},
                {str(i): tints[s] for i, s in enumerate(faces)
                 if s in tints})
