"""Fichiers : ouvrir, enregistrer, importer, exporter.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class FilesMixin:
    # -- fichiers ---------------------------------------------------------

    def export_part(self, path):
        """Export STL (impression 3D) ou STEP (échange CAO), par extension.

        Exports the body's current shape — what the viewport shows is what
        the printer gets.
        """
        import os
        from engine.kernel import (
            KernelError,
            _explain,
        )
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Solids:
            raise KernelError("rien à exporter — la pièce n'a pas de solide")
        path = self._user_path(
            path, (".stl", ".step", ".3mf"), must_exist=False)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".stl":
                shape.exportStl(path)
            elif ext == ".step":
                shape.exportStep(path)
            elif ext == ".3mf":
                import Mesh
                Mesh.export([body], path)
            else:
                raise KernelError("format inconnu « {} » — utilisez .stl, "
                                  ".step ou .3mf".format(
                                      ext or "aucune extension"))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return {"path": path, "size": os.path.getsize(path)}

    #: Wire names for the body's origin planes — Dessus/Face/Droite in the
    #: client, following vocab.ORIGIN_PLANES (FreeCAD is Z-up).

    def list_dir(self, path=None):
        """Liste un dossier de la prison de chemins. Lecture seule.

        ``path`` absent : le dossier personnel. Même règles que
        l'ouverture et l'enregistrement (``protocol.list_user_dir``).
        """
        from engine.kernel import KernelError
        from . import protocol
        try:
            return protocol.list_user_dir(path)
        except protocol.ProtocolError as exc:
            raise KernelError(str(exc))

    def open_part(self, path):
        """Open an existing .FCStd — the user's real files, not our demos.

        M1 scope: single active Body. A multi-body file opens on its first
        Body and says so; a file with none (Part-workbench models, meshes)
        is refused with the reason.
        """
        from engine import foreign
        from engine.kernel import KernelError
        App = self._app()
        path = self._user_path(
            path, (".FCStd", ".step", ".stp", ".iges", ".igs")
            + foreign.EXTENSIONS, must_exist=True)
        if foreign.is_foreign(path):
            return self._import_foreign(path)
        if path.lower().endswith((".step", ".stp", ".iges", ".igs")):
            return self._import_cad(path)
        self._close_current()
        doc = App.openDocument(path)
        self._setup_doc(doc)
        bodies = [
            o for o in doc.Objects
            if o.TypeId == "PartDesign::Body"
            and not self._is_internal_tool(o)
        ]
        if not bodies:
            bodies = [o for o in doc.Objects
                      if o.TypeId == "PartDesign::Body"]
        if not bodies:
            links = [o for o in doc.Objects if o.TypeId == "App::Link"]
            if links:
                # C'est un assemblage enregistré par nous : on le rouvre
                # dans le mode qui va avec.
                self._doc, self._body = doc, None
                self._assembly = True
                return self.assembly_tree()
            # Document ouvert ici mais non adopté : le fermer pour ne
            # pas laisser d'orphelin dans App.listDocuments().
            try:
                App.closeDocument(doc.Name)
            except Exception:
                pass
            self._doc = self._body = None
            raise KernelError(
                "aucun corps PartDesign dans ce fichier — il vient "
                "probablement de l'atelier Part (booléennes sans historique "
                "de fonctions), que cette interface ne couvre pas encore")
        self._doc, self._body = doc, bodies[0]
        tree = self.get_tree()
        tree["bodies_in_file"] = len(bodies)
        return tree

    def _import_foreign(self, path):
        """.sldprt / .x_t / .x_b : le lecteur d'OpenSW (``engine/foreign.py``)
        en écrit un STEP, importé ensuite comme un STEP. La géométrie
        seule — l'arbre de fonctions du fichier n'est pas rejoué. La pièce
        ouverte reste en place si la lecture échoue."""
        import os
        import shutil
        import tempfile
        from engine import foreign
        from engine.kernel import KernelError
        work = tempfile.mkdtemp(prefix="freesolid-lecture-")
        try:
            self._report_progress("Lecture de la pièce par OpenSW")
            step = os.path.join(work, "piece.step")
            try:
                report = foreign.convert(path, step)
            except foreign.ForeignError as exc:
                raise KernelError(str(exc)) from None
            self._report_progress("Import de la géométrie")
            label = os.path.splitext(os.path.basename(path))[0]
            tree = self._import_cad(step, label=label)
            tree["converted_from"] = os.path.splitext(path)[1].lower()
            # Corps que le lecteur n'a pas su écrire : le dire, pas les taire.
            tree["skipped_bodies"] = int(getattr(report, "skipped_bodies", 0) or 0)
            return tree
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _import_cad(self, path, label=None):
        """Import STEP/IGES : chaque solide arrive comme base de son propre
        corps — toutes les fonctions s'appliquent ensuite dessus."""
        import os
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolid")
        self._setup_doc(self._doc)
        shape = Part.Shape()
        try:
            shape.read(path)
            label = label or os.path.splitext(os.path.basename(path))[0]
            solids = shape.Solids
            parts = solids or [shape]
            for index, part in enumerate(parts, start=1):
                body = self._doc.addObject("PartDesign::Body", "Body")
                body.Label = (label if len(parts) == 1
                              else "{} ({})".format(label, index))
                if self._body is None:
                    self._body = body
                base = self._doc.addObject("Part::Feature", "Imported")
                base.Shape = part
                if not solids:
                    # Que des surfaces : elles restent visibles dans la
                    # section Surfaces, le corps attend une première fonction.
                    base.Label = self._t("Import — {}").format(body.Label)
                    continue
                base.Label = self._t("Forme importée — {}").format(body.Label)
                body.BaseFeature = base
                # FreeCAD enveloppe la forme dans un PartDesign::FeatureBase
                # nommé « BaseFeature » : c'est lui que l'arbre montre.
                for wrapper in body.Group:
                    if wrapper.TypeId == "PartDesign::FeatureBase":
                        wrapper.Label = self._t("Import — {}").format(body.Label)
            self._doc.recompute()
            tree = self.get_tree()
            tree["imported_solids"] = len(solids)
            return tree
        except KernelError:
            self._close_current()
            raise
        except Exception as exc:  # noqa: BLE001
            self._close_current()
            raise KernelError(_explain(exc))

    def save_part(self, path):
        """Save as a standard .FCStd — openable in stock FreeCAD.

        The exit door stays open by design: nothing this app produces is
        locked into it.
        """
        doc = self._require_doc()
        path = str(path)
        if not path.endswith(".FCStd"):
            path += ".FCStd"
        path = self._user_path(path, (".FCStd",), must_exist=False)
        doc.saveAs(path)
        return {"path": path}
