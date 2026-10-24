"""Retouches d'une surface : supprimer des faces, découper, détourer,
congé (et sa réédition).

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class SurfaceRetouchMixin:
    def surface_delete_faces(self, surface, faces):
        """Supprimer des faces d'une surface : un lieur de forme garde les
        autres (paramétrique) ; le trou se bouche ensuite par un
        remplissage si besoin."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import PartDesign  # noqa: F401 — enregistre le lieur de forme
        doc = self._require_doc()
        src = self._get_surface(surface)
        count = len(src.Shape.Faces)
        drop = {int(f) for f in faces or ()}
        if not drop:
            raise KernelError("cliquez les faces à supprimer")
        if any(f < 0 or f >= count for f in drop):
            raise KernelError("face inconnue : {}".format(sorted(drop)))
        keep = ["Face%d" % (i + 1) for i in range(count) if i not in drop]
        if not keep:
            raise KernelError("toutes les faces seraient supprimées")
        kept = doc.addObject("PartDesign::SubShapeBinder", "Surface")
        try:
            self._stamp(kept, kind="deleteface")
            kept.Support = [(src, tuple(keep))]
            kept.Label = self._t("Faces supprimées")
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(kept.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def surface_split(self, surface, tool):
        """Ligne de séparation : une courbe posée sur la surface (projetée,
        d'intersection, spline) scinde ses faces — chaque morceau se
        supprime ou se remplit ensuite à part."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import BOPTools.SplitFeatures as split_features
        doc = self._require_doc()
        src = self._get_surface(surface)
        cutter = doc.getObject(str(tool))
        if cutter is None or not getattr(cutter, "Shape", None):
            raise KernelError("objet inconnu : {}".format(tool))
        if cutter.Name == src.Name:
            raise KernelError("la surface et l'outil doivent être différents")
        before = len(src.Shape.Faces)
        if not before:
            raise KernelError("scinder demande une surface, pas une courbe")
        split = split_features.makeSlice("Surface")
        try:
            split.Base = src
            split.Tools = [cutter]
            split.Mode = "Standard"
            split.Label = self._t("Surface scindée")
            self._stamp(split, kind="split")
            self._recompute()
            if len(split.Shape.Faces) <= before:
                raise KernelError("la courbe ne scinde pas la surface — "
                                  "elle doit être posée dessus, d'un bord à "
                                  "l'autre ou fermée")
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(split.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def surface_untrim(self, surface, face=0):
        """Désajuster : la face retrouve les bords naturels de sa surface
        porteuse — trous bouchés, contour d'origine."""
        from engine.kernel import KernelError
        import Surface  # noqa: F401 — enregistre Surface::Extend
        src = self._get_surface(surface)
        faces = src.Shape.Faces
        if not faces:
            raise KernelError("désajuster demande une surface, pas une "
                              "courbe")
        face = int(face)
        if face < 0 or face >= len(faces):
            raise KernelError("face inconnue : {}".format(face))

        def configure(obj):
            obj.Face = (src, ["Face%d" % (face + 1)])
            obj.ExtendUSymetric = False
            obj.ExtendVSymetric = False
            for side in ("UNeg", "UPos", "VNeg", "VPos"):
                setattr(obj, "Extend" + side, 0.0)
            self._stamp(obj, untrim=1)

        return self._add_part_surface(
            "Surface::Extend", "Surface désajustée", configure)

    def surface_fillet(self, surface, edges, radius):
        """Congé entre faces d'une surface : sur les arêtes partagées par
        deux faces (cousez d'abord deux surfaces séparées)."""
        from engine.kernel import KernelError
        import Part
        src = self._get_surface(surface)
        shape = src.Shape
        radius = float(radius)
        if radius <= 0:
            raise KernelError("le rayon doit être positif")
        picked = []
        for edge in edges or ():
            edge = int(edge)
            if edge < 0 or edge >= len(shape.Edges):
                raise KernelError("arête inconnue : {}".format(edge))
            if len(shape.ancestorsOfType(shape.Edges[edge], Part.Face)) != 2:
                raise KernelError("le congé se pose sur une arête entre deux "
                                  "faces — cousez d'abord les surfaces")
            picked.append(edge)
        if not picked:
            raise KernelError("cliquez les arêtes à arrondir")

        def configure(obj):
            obj.Base = src
            obj.Edges = [(e + 1, radius, radius) for e in picked]

        return self._add_part_surface(
            "Part::Fillet", "Congé de surface", configure)

    def edit_surface_fillet(self, surface, radius):
        """Rééditer le rayon d'un congé de surface."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(surface))
        if obj is None or obj.TypeId != "Part::Fillet":
            raise KernelError("congé de surface inconnu : {}".format(surface))
        radius = float(radius)
        if radius <= 0:
            raise KernelError("le rayon doit être positif")
        obj.Edges = [(edge[0], radius, radius) for edge in obj.Edges]
        self._recompute()
        return self.get_tree()
