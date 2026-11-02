"""Esquisses partagées et contours choisis.

Une esquisse peut servir à plusieurs fonctions (extrusion, enlèvement,
révolution…) : elle apparaît sous chacune dans l'arbre, et la modifier
les fait toutes suivre. Chaque fonction peut n'utiliser qu'une partie de
ses contours — le profil devient alors une liste d'arêtes de l'esquisse.

Les imports FreeCAD restent dans les méthodes : le module se charge sans
FreeCAD (``contour_groups`` est testée en CI).
"""

#: Fonctions à profil qui acceptent des contours choisis.
PROFILE_OPS = ("add_pad", "add_pocket", "add_revolution", "add_groove")


def contour_groups(wire_edges, used_edges):
    """Contours utilisés par une fonction : les index des fils dont toutes
    les arêtes figurent dans ``used_edges`` (noms « EdgeN »). Sans arête
    choisie, tous les contours le sont."""
    if not used_edges:
        return list(range(len(wire_edges)))
    used = set(used_edges)
    return [i for i, edges in enumerate(wire_edges)
            if edges and all(e in used for e in edges)]


class SketchShareMixin:
    """Contours d'esquisse et fonctions qui partagent une esquisse."""

    # ---------- contours ----------

    @staticmethod
    def _sketch_wires(sk):
        """Les contours (fils) de l'esquisse : pour chacun, ses arêtes
        (« EdgeN » dans la forme de l'esquisse), s'il est fermé, sa
        taille."""
        shape = sk.Shape
        edges = shape.Edges
        out = []
        for wire in shape.Wires:
            names = []
            for e in wire.Edges:
                k = next((i for i, x in enumerate(edges) if x.isSame(e)),
                         None)
                if k is not None:
                    names.append("Edge%d" % (k + 1))
            box = wire.BoundBox
            out.append({"edges": names, "closed": bool(wire.isClosed()),
                        "size": [round(box.XLength, 3),
                                 round(box.YLength, 3),
                                 round(box.ZLength, 3)]})
        return out

    def sketch_contours(self, sketch):
        """Contours de l'esquisse (lecture) : index, fermé, taille."""
        sk = self._get_sketch(sketch)
        wires = self._sketch_wires(sk)
        return {"contours": [{"index": i, "closed": w["closed"],
                              "edges": len(w["edges"]), "size": w["size"]}
                             for i, w in enumerate(wires)]}

    def _profile_of(self, feature):
        """(esquisse, arêtes choisies) du profil d'une fonction."""
        profile = getattr(feature, "Profile", None)
        if isinstance(profile, tuple):
            sk = profile[0]
            subs = [s for s in (profile[1] if len(profile) > 1 else ()) if s]
        else:
            sk, subs = profile, []
        return sk, list(subs)

    def _apply_contours(self, feature, contours):
        """Restreint le profil de ``feature`` aux contours ``contours``
        (index de fils) ; liste vide ou None : toute l'esquisse."""
        from engine.kernel import KernelError
        sk, _ = self._profile_of(feature)
        if sk is None or sk.TypeId != "Sketcher::SketchObject":
            raise KernelError("cette fonction n'a pas d'esquisse pour profil")
        wires = self._sketch_wires(sk)
        chosen = sorted({int(i) for i in (contours or [])})
        if any(not 0 <= i < len(wires) for i in chosen):
            raise KernelError("contour inconnu dans l'esquisse")
        if not chosen or len(chosen) == len(wires):
            feature.Profile = sk
            return
        names = [name for i in chosen for name in wires[i]["edges"]]
        feature.Profile = (sk, names)

    def set_profile_contours(self, feature, contours):
        """Réédition : les contours de l'esquisse qu'utilise la fonction."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        self._apply_contours(obj, contours)
        self._recompute()
        if "Invalid" in (obj.State or ()):
            raise KernelError("ces contours ne donnent pas de profil "
                              "valide pour cette fonction")
        return self.get_tree()

    def _profile_entry(self, obj):
        """Ligne d'arbre : l'esquisse du profil, ses contours, ceux pris."""
        sk, subs = self._profile_of(obj)
        if sk is None or getattr(sk, "TypeId", "") != \
                "Sketcher::SketchObject":
            return None
        try:
            wires = self._sketch_wires(sk)
        except Exception:  # noqa: BLE001
            return None
        return {"sketch": sk.Name, "count": len(wires),
                "used": contour_groups([w["edges"] for w in wires], subs),
                "sizes": [w["size"] for w in wires]}

    # ---------- création avec contours choisis ----------

    def _with_contours(self, method, contours, *args, **kwargs):
        tree = method(*args, **kwargs)
        if contours:
            tip = self._require_body().Tip
            self._apply_contours(tip, contours)
            self._recompute()
            tree = self.get_tree()
        return tree

    def add_pad(self, *args, contours=None, **kwargs):
        return self._with_contours(super().add_pad, contours, *args, **kwargs)

    def add_pocket(self, *args, contours=None, **kwargs):
        return self._with_contours(super().add_pocket, contours, *args,
                                   **kwargs)

    def add_revolution(self, *args, contours=None, **kwargs):
        return self._with_contours(super().add_revolution, contours, *args,
                                   **kwargs)

    def add_groove(self, *args, contours=None, **kwargs):
        return self._with_contours(super().add_groove, contours, *args,
                                   **kwargs)

    # ---------- qui utilise quelle esquisse ----------

    def _sketch_consumers(self, body=None):
        """Esquisse → toutes les fonctions qui la prennent pour profil,
        dans l'ordre du corps (la première « porte » l'esquisse)."""
        body = body or self._require_body()
        users = {}
        for obj in body.Group:
            if getattr(obj, "FreeSolidThinOwner", ""):
                continue
            sk, _ = self._profile_of(obj)
            if sk is not None and getattr(sk, "TypeId", "") == \
                    "Sketcher::SketchObject":
                users.setdefault(sk.Name, [])
                if obj.Name not in users[sk.Name]:
                    users[sk.Name].append(obj.Name)
        return users
