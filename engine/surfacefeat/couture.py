"""Coudre des surfaces, épaissir une surface.

Sous-mixin de ``SurfaceMixin`` (voir ``__init__.py``). Pas d'import
FreeCAD au niveau du module : les méthodes importent le noyau à l'appel.
"""


class SurfaceSewMixin:
    def surface_sew(self, surfaces):
        """Coudre des surfaces (pas d'objet Part paramétrique natif pour
        la couture : forme recalculée depuis ses sources à chaque
        reconstruction). Si la peau est fermée, elle devient un solide —
        le geste « coudre puis solidifier »."""
        from engine.kernel import KernelError
        if not isinstance(surfaces, (list, tuple)) or len(surfaces) < 2:
            raise KernelError("coudre demande au moins deux surfaces")
        shape = self._sew_shape([self._get_surface(name).Shape
                                 for name in surfaces])
        closed = bool(shape.Solids)
        tree = self._add_surface(
            shape, "Solide cousu" if closed else "Surface cousue")
        # Les surfaces cousues sont consommées : la couture les remplace.
        sewn = self._require_doc().getObject(tree["surfaces"][-1]["name"])
        self._stamp(sewn, sources=";".join(str(n) for n in surfaces))
        return self.get_tree()

    @staticmethod
    def _sew_shape(shapes):
        """Peau cousue des faces de ``shapes`` ; solide si elle est
        fermée."""
        from engine.kernel import KernelError, _explain
        import Part
        faces = [f for shape in shapes for f in shape.Faces]
        if not faces:
            raise KernelError("aucune face à coudre")
        try:
            shell = Part.makeShell(faces)
            shell.sewShape()
            return Part.makeSolid(shell) if shell.isClosed() else shell
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))

    def surface_thicken(self, surface, thickness):
        """Épaissir une surface en solide — Part::Offset paramétrique."""
        from engine.kernel import KernelError
        src = self._get_surface(surface)
        thickness = float(thickness)
        if thickness == 0:
            raise KernelError("l'épaisseur ne peut pas être nulle")

        def configure(obj):
            obj.Source = src
            obj.Value = thickness
            obj.Fill = True

        return self._add_part_surface(
            "Part::Offset", "Épaississement", configure)
