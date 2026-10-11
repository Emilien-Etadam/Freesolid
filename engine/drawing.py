"""Mise en plan : vues, cotes d'encombrement, coupe, export.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class DrawingMixin:
    # -- mise en plan ----------------------------------------------------

    @staticmethod
    def _drawing_visible_edges(view):
        try:
            return list(view.getVisibleEdges() or [])
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _drawing_apply_scale(view, scale):
        if scale:
            view.ScaleType = "Custom"
            view.Scale = float(scale)

    @staticmethod
    def _drawing_extreme_edge_ids(edges):
        """Indices gauche / droite / bas / haut (centres des BoundBox 2D)."""
        if len(edges) < 2:
            return None
        indexed = list(enumerate(edges))

        def cx(item):
            box = item[1].BoundBox
            return (box.XMin + box.XMax) / 2.0

        def cy(item):
            box = item[1].BoundBox
            return (box.YMin + box.YMax) / 2.0

        left = min(indexed, key=cx)[0]
        right = max(indexed, key=cx)[0]
        bottom = min(indexed, key=cy)[0]
        top = max(indexed, key=cy)[0]
        if left == right or bottom == top:
            return None
        return left, right, bottom, top

    def _drawing_add_extent_dims(self, doc, page, view, created):
        """Cotes d'encombrement DistanceX/DistanceY sur la vue de face.

        Les arêtes 2D doivent déjà être peuplées (CoarseView posé à la
        création de la vue — trop tard ensuite). Retourne False plutôt
        que d'échouer : le DXF muet reste meilleur que pas de DXF.
        """
        edges = self._drawing_visible_edges(view)
        ids = self._drawing_extreme_edge_ids(edges)
        if ids is None:
            return False
        left, right, bottom, top = ids
        dims = []
        for name, dtype, a, b in (
                ("DimLargeur", "DistanceX", left, right),
                ("DimHauteur", "DistanceY", bottom, top)):
            dim = doc.addObject("TechDraw::DrawViewDimension", name)
            created.append(dim)
            dims.append(dim)
            page.addView(dim)
            dim.Type = dtype
            dim.References2D = [
                (view, "Edge{}".format(a)),
                (view, "Edge{}".format(b)),
            ]
        doc.recompute()
        for dim in dims:
            if "Up-to-date" not in getattr(dim, "State", []):
                return False
            if hasattr(dim, "getRawValue"):
                try:
                    if not (dim.getRawValue() > 0):
                        return False
                except Exception:  # noqa: BLE001
                    return False
        return True

    def _drawing_add_section(self, doc, page, body, views, axis, scale,
                             created):
        """Vue en coupe (DrawViewSection) — normale selon X/Y/Z.

        La vue de base doit avoir une Direction non parallèle à la
        normale, sinon TechDraw n'arrive pas à construire le CS
        (getSectionCS) et le cut async peut SIGSEGV. Origine = (0,0,0).
        Hachures : défaut SvgHatch (CutSurfaceDisplay=Hide SIGSEGV en
        1.0.0 headless). La géométrie 2D de la coupe reste souvent vide
        headless (même thread HLR) — l'objet est quand même exporté.
        """
        App = self._app()
        normals = {"X": (1.0, 0.0, 0.0),
                   "Y": (0.0, 1.0, 0.0),
                   "Z": (0.0, 0.0, 1.0)}
        nx, ny, nz = normals[axis]
        nlen = (nx * nx + ny * ny + nz * nz) ** 0.5
        base = views[0]
        for view in views:
            direction = view.Direction
            length = direction.Length or 1.0
            aligned = abs(direction.x * nx + direction.y * ny
                          + direction.z * nz) / (length * nlen)
            if aligned < 0.95:
                base = view
                break
        section = doc.addObject("TechDraw::DrawViewSection", "Coupe" + axis)
        created.append(section)
        page.addView(section)
        section.Source = [body]
        section.BaseView = base
        section.SectionNormal = App.Vector(nx, ny, nz)
        section.SectionOrigin = App.Vector(0, 0, 0)
        section.Direction = App.Vector(nx, ny, nz)
        self._drawing_apply_scale(section, scale)
        section.X = float(base.X) + 80
        section.Y = float(base.Y)
        doc.recompute()
        return "Up-to-date" in getattr(section, "State", [])

    def make_drawing(self, path, scale=None, dims=True, section=None):
        """Mise en plan : Face / Dessus / Isométrique sur une page
        TechDraw, exportée en DXF (le seul export fiable headless).

        ``dims`` (défaut True) : cotes d'encombrement sur la vue de
        face. ``section`` : ``"X"|"Y"|"Z"`` pour une vue en coupe
        optionnelle. La page est retirée du document après l'export.
        """
        import os
        from engine.kernel import (
            KernelError,
            _explain,
        )
        doc = self._require_doc()
        body = self._require_body()
        App = self._app()
        path = str(path)
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        path = self._user_path(path, (".dxf",), must_exist=False)
        want_dims = True if dims is None else bool(dims)
        axis = None
        if section not in (None, "", False):
            axis = str(section).strip().upper()
            if axis not in ("X", "Y", "Z"):
                raise KernelError("coupe : axe X, Y ou Z attendu")
        created = []
        cleanup_errors = []
        original = None
        dims_ok = None
        section_ok = None
        try:
            page = doc.addObject("TechDraw::DrawPage", "Page")
            created.append(page)
            template = doc.addObject("TechDraw::DrawSVGTemplate",
                                     "Template")
            created.append(template)
            template_path = os.path.join(
                App.getResourceDir(), "Mod", "TechDraw", "Templates",
                "A4_LandscapeTD.svg")
            if os.path.exists(template_path):
                template.Template = template_path
            page.Template = template
            placements = (("Face", (0, -1, 0), 70, 60),
                          ("Dessus", (0, 0, 1), 70, 150),
                          ("Iso", (1, -1, 1), 210, 105))
            views = []
            for name, direction, x, y in placements:
                view = doc.addObject("TechDraw::DrawViewPart",
                                     "View" + name)
                created.append(view)
                view.Source = [body]
                view.Direction = App.Vector(*direction)
                # Headless 1.0.x : le HLR Qt ne peuple pas les arêtes 2D.
                # CoarseView doit être posé AVANT le premier recompute.
                if want_dims:
                    view.CoarseView = True
                self._drawing_apply_scale(view, scale)
                page.addView(view)
                view.X = x
                view.Y = y
                views.append(view)
            doc.recompute()
            if want_dims:
                try:
                    dims_ok = self._drawing_add_extent_dims(
                        doc, page, views[0], created)
                except Exception:  # noqa: BLE001
                    dims_ok = False
            if axis is not None:
                try:
                    section_ok = self._drawing_add_section(
                        doc, page, body, views, axis, scale, created)
                except Exception:  # noqa: BLE001
                    section_ok = False
            import TechDraw
            TechDraw.writeDXFPage(page, path)
        except KernelError as exc:
            original = exc
            raise
        except Exception as exc:  # noqa: BLE001
            original = KernelError(_explain(exc))
            raise original
        finally:
            for obj in reversed(created):
                try:
                    doc.removeObject(obj.Name)
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append("{} ({})".format(
                        getattr(obj, "Name", "?"), _explain(exc)))
            try:
                doc.recompute()
            except Exception:
                pass
            if cleanup_errors:
                note = "mise en plan : nettoyage incomplet — {}".format(
                    " ; ".join(cleanup_errors))
                if original is None:
                    raise KernelError(note)
                original.args = (original.args[0] + " — " + note,)
        if not os.path.exists(path):
            raise KernelError("l'export DXF n'a rien produit")
        result = {"path": path, "size": os.path.getsize(path)}
        if dims_ok is not None:
            result["dims_ok"] = bool(dims_ok)
        if section_ok is not None:
            result["section_ok"] = bool(section_ok)
        return result
