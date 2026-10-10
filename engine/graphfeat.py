"""Fonctions graphe et répétitions variables.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class GraphMixin:
    # -- fonctions graphe et répétitions ---------------------------------

    _GRAPH_PROPS = (
        ("FreeSolidGraphJson", "App::PropertyString"),
        ("FreeSolidGraphMode", "App::PropertyString"),
    )
    _REPEAT_PROPS = (
        ("FreeSolidRepeatJson", "App::PropertyString"),
        ("FreeSolidRepeatMode", "App::PropertyString"),
    )
    _GRAPH_JSON_MAX = 1_000_000

    def _mark_graph_tool(self, obj):
        """Artefact interne d'une fonction graphe : caché de l'arbre."""
        if "FreeSolidGraphTool" not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", "FreeSolidGraphTool",
                            "FreeSolid",
                            "Outil interne d'une fonction graphe")
        obj.FreeSolidGraphTool = True

    def _mark_repeat_tool(self, obj):
        """Artefact interne d'une répétition variable : caché de l'arbre."""
        if "FreeSolidRepeatTool" not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", "FreeSolidRepeatTool",
                            "FreeSolid",
                            "Outil interne d'une répétition variable")
        obj.FreeSolidRepeatTool = True

    def _is_internal_tool(self, obj):
        """Artefact interne (gravure, graphe, répétition, gabarit de
        pierre ou corps outil dérivé d'un semis) : hors de l'arbre.

        Un seul test, plusieurs propriétés. Deux prédicats parallèles
        divergeraient — c'est le défaut que N001b a dû corriger.
        """
        return bool(getattr(obj, "FreeSolidTextTool", False)
                    or getattr(obj, "FreeSolidGraphTool", False)
                    or getattr(obj, "FreeSolidRepeatTool", False)
                    or getattr(obj, "FreeSolidGemTool", False)
                    or getattr(obj, "FreeSolidGemBooleanTool", False)
                    or getattr(obj, "FreeSolidSurfaceTool", False))

    def _current_variables(self):
        return {item["name"]: item["value"]
                for item in self.list_variables()["variables"]}

    def _dump_json_payload(self, data, what):
        import json
        from engine.kernel import KernelError
        try:
            payload = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise KernelError(
                "{} non sérialisable : {}".format(what, exc))
        if len(payload) > self._GRAPH_JSON_MAX:
            raise KernelError(
                "{} trop volumineux ({} caractères, max. {})".format(
                    what, len(payload), self._GRAPH_JSON_MAX))
        return payload

    def _dump_graph_json(self, graph):
        from engine.kernel import migrate_graph
        return self._dump_json_payload(migrate_graph(graph), "graphe")

    def _evaluate_graph(self, graph):
        from engine.kernel import (
            GraphError,
            KernelError,
            evaluate_graph,
        )
        try:
            return evaluate_graph(
                graph, self._current_variables(),
                trusted=self._scripts_authorized)
        except GraphError as exc:
            raise KernelError(str(exc)) from exc

    def script_trust_status(self):
        """L'autorisation Python de cette session, pour ce document.

        Lecture seule. ``False`` après new_part / open_part — jamais lue
        dans le ``.FCStd``.
        """
        self._require_doc()
        return {"authorized": bool(self._scripts_authorized)}

    def authorize_scripts(self):
        """Consentement explicite : Python autorisé pour ce document,
        jusqu'à la fermeture. N'écrit rien dans le fichier.
        """
        self._require_doc()
        self._scripts_authorized = True
        return {"authorized": True}

    def _build_graph_solid(self, instructions):
        from engine.kernel import KernelError
        solids = []
        for inst in instructions:
            solid = self._shape_from_instruction(inst)
            solids.append(solid)
        if not solids:
            raise KernelError("le graphe ne produit aucune forme")
        result = solids[0]
        for extra in solids[1:]:
            result = result.fuse(extra)
        return result

    def _build_graph_surface(self, instructions):
        from engine.kernel import KernelError
        import Part
        shapes = [self._shape_from_instruction(inst) for inst in instructions]
        if not shapes:
            raise KernelError("le graphe ne produit aucune forme")
        if len(shapes) == 1:
            return shapes[0]
        return Part.makeCompound(shapes)

    def _vec(self, coords):
        App = self._app()
        return App.Vector(float(coords[0]), float(coords[1]), float(coords[2]))

    def _shape_from_instruction(self, inst):
        """Une instruction → une forme Part. Boîte et cylindre inchangés."""
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import Part
        App = self._app()
        kind = inst.get("shape")
        try:
            if kind == "cylindre":
                point = App.Vector(float(inst["x"]), float(inst["y"]),
                                   float(inst["z"]))
                return Part.makeCylinder(
                    float(inst["radius"]), float(inst["height"]), point)
            if kind == "boite":
                point = App.Vector(float(inst["x"]), float(inst["y"]),
                                   float(inst["z"]))
                return Part.makeBox(
                    float(inst["length"]), float(inst["width"]),
                    float(inst["height"]), point)
            if kind == "ligne":
                edge = Part.makeLine(
                    self._vec(inst["point1"]), self._vec(inst["point2"]))
                return self._ensure_wire(edge)
            if kind == "arc":
                edge = Part.makeCircle(
                    float(inst["rayon"]),
                    self._vec(inst["point"]),
                    self._vec(inst["direction"]),
                    float(inst["angle1"]),
                    float(inst["angle2"]))
                return self._ensure_wire(edge)
            if kind == "arc_3pts":
                arc = Part.Arc(
                    self._vec(inst["point1"]),
                    self._vec(inst["point2"]),
                    self._vec(inst["point3"]))
                return self._ensure_wire(arc.toShape())
            if kind == "cercle":
                edge = Part.makeCircle(
                    float(inst["rayon"]),
                    self._vec(inst["point"]),
                    self._vec(inst["direction"]))
                return self._ensure_wire(edge)
            if kind == "helice":
                edge = Part.makeHelix(
                    float(inst["pas_helice"]),
                    float(inst["hauteur"]),
                    float(inst["rayon"]),
                    float(inst["angle"]),
                    bool(inst.get("gauche")))
                return self._ensure_wire(edge)
            if kind == "polyligne":
                vectors = [self._vec(p) for p in inst["points"]]
                return self._wire_through_points(
                    vectors, spline=False, closed=bool(inst.get("ferme")))
            if kind == "bspline":
                vectors = [self._vec(p) for p in inst["points"]]
                return self._wire_through_points(
                    vectors, spline=True, closed=bool(inst.get("ferme")))
            if kind == "plan":
                return Part.makePlane(
                    float(inst["longueur"]),
                    float(inst["largeur"]),
                    self._vec(inst["point"]),
                    self._vec(inst["direction"]))
            if kind == "bspline_surface":
                grid = [
                    [self._vec(point) for point in row]
                    for row in inst["centres"]
                ]
                surf = Part.BSplineSurface()
                surf.interpolate(grid)
                return surf.toShape()
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        raise KernelError(
            "instruction de forme inconnue : {}".format(kind))

    def _graph_output_nature(self, instructions):
        from engine.kernel import (
            KernelError,
            classify_shape_instructions,
            mixed_output_message,
            output_nature,
        )
        solids, surfaces = classify_shape_instructions(instructions)
        if solids and surfaces:
            raise KernelError(mixed_output_message(solids, surfaces))
        nature = output_nature(instructions)
        if nature is None:
            raise KernelError("le graphe ne produit aucune forme")
        return nature

    def _is_graph_surface(self, obj):
        return (
            obj.TypeId == "Part::Feature"
            and "FreeSolidGraphJson" in obj.PropertiesList
        )

    def _tree_graph_payload(self, obj):
        import json
        if "FreeSolidGraphJson" not in obj.PropertiesList:
            return None
        try:
            parsed = json.loads(obj.FreeSolidGraphJson or "")
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _graph_tool_parts(self, obj):
        from engine.kernel import KernelError
        tool_body = next(
            (item for item in (getattr(obj, "Group", None) or [])
             if item.TypeId == "PartDesign::Body"), None)
        shape_feature = getattr(tool_body, "BaseFeature", None)
        if tool_body is None or shape_feature is None:
            raise KernelError(
                "fonction graphe incomplète — le corps outil est absent")
        return tool_body, shape_feature

    def _persist_graph(self, obj, graph, mode, label):
        payload = self._dump_graph_json(graph)
        for prop, prop_type in self._GRAPH_PROPS:
            if prop not in obj.PropertiesList:
                obj.addProperty(prop_type, prop, "FreeSolid",
                                "Paramètre de la fonction graphe")
        obj.FreeSolidGraphJson = payload
        obj.FreeSolidGraphMode = mode
        obj.Label = label

    def _graph_surface_label(self, instructions):
        from engine.kernel import graph_surface_kind
        return "Fonction graphe — {}".format(
            graph_surface_kind(instructions))

    def add_graph_feature(self, graph, mode=None):
        """Insère la forme d'un graphe dans l'arbre.

        Solide : route du corps outil (``mode`` fuse ou cut), comme la
        gravure. Courbe / surface : un seul ``Part::Feature``, comme une
        courbe 3D. Le graphe est évalué **avant** toute modification.
        """
        from engine.kernel import KernelError
        instructions = self._evaluate_graph(graph)
        nature = self._graph_output_nature(instructions)
        mode_text = "" if mode is None else str(mode)
        if nature == "solid":
            if mode_text not in ("fuse", "cut"):
                if mode_text:
                    raise KernelError(
                        "mode inconnu « {} » — attendu fuse ou cut".format(
                            mode_text))
                raise KernelError("un solide demande le mode fuse ou cut")
            return self._add_graph_solid(graph, instructions, mode_text)
        if mode_text in ("fuse", "cut"):
            raise KernelError(
                "fuse et cut ne s'appliquent pas à une courbe ou une "
                "surface — la ligne d'arbre n'est pas un enlèvement")
        if mode_text:
            raise KernelError(
                "mode inconnu « {} » — une courbe ou une surface n'a "
                "pas de mode fuse ou cut".format(mode_text))
        return self._add_graph_surface(graph, instructions)

    def _add_graph_solid(self, graph, instructions, mode):
        from engine.kernel import KernelError
        solid = self._build_graph_solid(instructions)
        body = self._require_body()
        doc = self._require_doc()
        shape_feature = doc.addObject("Part::Feature", "GraphShape")
        shape_feature.Shape = solid
        shape_feature.Label = self._t("Forme du graphe")
        self._mark_graph_tool(shape_feature)
        tool_body = doc.addObject("PartDesign::Body", "GraphBody")
        tool_body.Label = self._t("Corps graphe")
        tool_body.BaseFeature = shape_feature
        self._mark_graph_tool(tool_body)
        doc.recompute()
        try:
            self.add_boolean(tool=tool_body.Name, type=mode)
        except KernelError:
            for name in (tool_body.Name, shape_feature.Name):
                try:
                    doc.removeObject(name)
                except Exception:
                    pass
            doc.recompute()
            raise
        tip = getattr(body, "Tip", None)
        if tip is not None:
            self._persist_graph(
                tip, graph, mode,
                "Fonction graphe — Ajout" if mode == "fuse"
                else "Fonction graphe — Enlèvement")
        return self.get_tree()

    def _add_graph_surface(self, graph, instructions):
        shape = self._build_graph_surface(instructions)
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Shape = shape
        try:
            self._persist_graph(
                feature, graph, "",
                self._graph_surface_label(instructions))
            doc.recompute()
        except Exception:
            try:
                doc.removeObject(feature.Name)
            except Exception:
                pass
            raise
        return self.get_tree()

    def edit_graph_feature(self, feature, graph):
        """Réévalue une fonction graphe et remplace sa forme.

        Atomique : le graphe est évalué et la géométrie reconstruite
        **d'abord** ; si l'un ou l'autre échoue, la pièce n'est pas
        modifiée. Une ligne ne change pas de nature en silence.
        """
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if "FreeSolidGraphJson" not in obj.PropertiesList:
            raise KernelError("cette fonction n'est pas une fonction graphe")
        instructions = self._evaluate_graph(graph)
        nature = self._graph_output_nature(instructions)
        if self._is_graph_surface(obj):
            if nature != "surface":
                raise KernelError(
                    "cette fonction graphe est une courbe ou une surface ; "
                    "le graphe produit un solide — la pièce n'a pas été "
                    "modifiée")
            shape = self._build_graph_surface(instructions)
            old_shape = obj.Shape
            obj.Shape = shape
            try:
                self._recompute()
            except KernelError as exc:
                obj.Shape = old_shape
                try:
                    self._recompute()
                except KernelError:
                    pass
                raise KernelError(
                    "{} — la fonction graphe n'a pas été modifiée".format(
                        exc))
            self._persist_graph(
                obj, graph, "", self._graph_surface_label(instructions))
            return self.get_tree()
        if nature != "solid":
            raise KernelError(
                "cette fonction graphe est un enlèvement ou un bossage ; "
                "le graphe ne produit plus de solide — la pièce n'a pas "
                "été modifiée")
        solid = self._build_graph_solid(instructions)
        _, shape_feature = self._graph_tool_parts(obj)
        old_shape = shape_feature.Shape
        shape_feature.Shape = solid
        try:
            self._recompute()
        except KernelError as exc:
            shape_feature.Shape = old_shape
            try:
                self._recompute()
            except KernelError:
                pass
            raise KernelError(
                "{} — la fonction graphe n'a pas été modifiée".format(exc))
        mode = getattr(obj, "FreeSolidGraphMode", "") or "cut"
        self._persist_graph(
            obj, graph, mode,
            "Fonction graphe — Ajout" if mode == "fuse"
            else "Fonction graphe — Enlèvement")
        return self.get_tree()

    def get_graph_feature(self, feature):
        """Rend le graphe persisté sur la ligne d'arbre."""
        from engine.kernel import (
            KernelError,
            migrate_graph,
        )
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if "FreeSolidGraphJson" not in obj.PropertiesList:
            raise KernelError("cette fonction n'est pas une fonction graphe")
        parsed = self._tree_graph_payload(obj)
        if parsed is None:
            raise KernelError("graphe persisté illisible")
        stored = getattr(obj, "FreeSolidGraphMode", "") or ""
        if self._is_graph_surface(obj):
            mode = stored
        else:
            mode = stored or "cut"
        return {"graph": migrate_graph(parsed), "mode": mode}

    def _repeat_label(self, mode):
        return ("Réseau variable — Ajout" if mode == "fuse"
                else "Réseau variable — Enlèvement")

    def _repeat_tool_parts(self, obj):
        from engine.kernel import KernelError
        tool_body = next(
            (item for item in (getattr(obj, "Group", None) or [])
             if item.TypeId == "PartDesign::Body"), None)
        shape_feature = getattr(tool_body, "BaseFeature", None)
        if tool_body is None or shape_feature is None:
            raise KernelError(
                "répétition incomplète — le corps outil est absent")
        return tool_body, shape_feature

    def _load_repeat_json(self, obj):
        import json
        from engine.kernel import KernelError
        if "FreeSolidRepeatJson" not in obj.PropertiesList:
            raise KernelError(
                "cette fonction n'est pas une répétition variable")
        try:
            parsed = json.loads(obj.FreeSolidRepeatJson or "")
        except (TypeError, ValueError):
            raise KernelError("répétition persistée illisible")
        if not isinstance(parsed, dict):
            raise KernelError("répétition persistée illisible")
        mode = getattr(obj, "FreeSolidRepeatMode", "") or parsed.get("mode") or "fuse"
        features = parsed.get("features")
        if not isinstance(features, list):
            raise KernelError("répétition persistée illisible")
        from engine.replay import split_repeat_source
        kind, value = split_repeat_source(
            parsed.get("instances", None)
            if "instances" in parsed else None,
            parsed.get("graph", None) if "graph" in parsed else None,
        )
        loaded = {"features": features, "mode": mode}
        loaded[kind] = value
        return loaded

    def _persist_repeat(self, obj, payload, mode, label):
        dumped = self._dump_json_payload(payload, "répétition")
        for prop, prop_type in self._REPEAT_PROPS:
            if prop not in obj.PropertiesList:
                obj.addProperty(prop_type, prop, "FreeSolid",
                                "Paramètre de la répétition variable")
        obj.FreeSolidRepeatJson = dumped
        obj.FreeSolidRepeatMode = mode
        obj.Label = label

    def _repeat_solid(self, features, instances):
        """Rejoue le groupe, tout ou rien. Rend (solide, noms source)."""
        from engine.replay import capture_group, replay_instances
        captured = capture_group(self, features)
        solid = replay_instances(self, captured, instances)
        names = [feat["name"] for feat in captured["features"]]
        return solid, names

    def _resolve_repeat_instances(self, instances=None, graph=None):
        """Graphe ou liste — exactement un des deux. Rend les instances."""
        from engine.kernel import (
            GraphError,
            KernelError,
            evaluate_instances,
        )
        from engine.replay import split_repeat_source
        kind, value = split_repeat_source(instances, graph)
        if kind == "instances":
            return value
        try:
            return evaluate_instances(value, self._current_variables())
        except GraphError as exc:
            raise KernelError(str(exc)) from exc

    def add_repeat_feature(self, features, instances=None, graph=None,
                           mode="fuse"):
        """Insère une répétition variable : une ligne, un booléen.

        Le groupe est rejoué pour chaque instance **avant** toute
        modification de la pièce. Une instance refusée par la garde
        annule la répétition entière. ``graph`` ou ``instances`` :
        exactement un des deux ; les instances d'un graphe sont
        dérivées, jamais stockées à côté.
        """
        from engine.kernel import (
            KernelError,
            migrate_graph,
        )
        mode = str(mode)
        if mode not in ("fuse", "cut"):
            raise KernelError(
                "mode inconnu « {} » — attendu fuse ou cut".format(mode))
        if not isinstance(features, (list, tuple)):
            raise KernelError("features doit être une liste de noms")
        names = [str(name) for name in features]
        resolved = self._resolve_repeat_instances(instances, graph)
        solid, names = self._repeat_solid(names, resolved)
        payload = {"features": names, "mode": mode}
        if graph is not None:
            payload["graph"] = migrate_graph(graph)
        else:
            payload["instances"] = instances
        self._dump_json_payload(payload, "répétition")
        body = self._require_body()
        doc = self._require_doc()
        shape_feature = doc.addObject("Part::Feature", "RepeatShape")
        shape_feature.Shape = solid
        shape_feature.Label = self._t("Forme de la répétition")
        self._mark_repeat_tool(shape_feature)
        tool_body = doc.addObject("PartDesign::Body", "RepeatBody")
        tool_body.Label = self._t("Corps répétition")
        tool_body.BaseFeature = shape_feature
        self._mark_repeat_tool(tool_body)
        doc.recompute()
        try:
            self.add_boolean(tool=tool_body.Name, type=mode)
        except KernelError:
            for name in (tool_body.Name, shape_feature.Name):
                try:
                    doc.removeObject(name)
                except Exception:
                    pass
            doc.recompute()
            raise
        tip = getattr(body, "Tip", None)
        if tip is not None:
            self._persist_repeat(
                tip, payload, mode, self._repeat_label(mode))
        return self.get_tree()

    def edit_repeat_feature(self, feature, instances=None, graph=None):
        """Réédite une répétition variable (instances **ou** graphe).

        Atomique : le groupe est rejoué et la géométrie reconstruite
        **d'abord** ; si l'un ou l'autre échoue, la pièce n'est pas
        modifiée. Les empreintes se recalculent depuis les fonctions
        source, elles ne sont pas lues dans le JSON persisté.
        """
        from engine.kernel import (
            KernelError,
            migrate_graph,
        )
        doc = self._require_doc()
        obj = doc.getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        stored = self._load_repeat_json(obj)
        mode = stored["mode"]
        resolved = self._resolve_repeat_instances(instances, graph)
        solid, names = self._repeat_solid(stored["features"], resolved)
        payload = {"features": names, "mode": mode}
        if graph is not None:
            payload["graph"] = migrate_graph(graph)
        else:
            payload["instances"] = instances
        self._dump_json_payload(payload, "répétition")
        _, shape_feature = self._repeat_tool_parts(obj)
        old_shape = shape_feature.Shape
        shape_feature.Shape = solid
        try:
            self._recompute()
        except KernelError as exc:
            shape_feature.Shape = old_shape
            try:
                self._recompute()
            except KernelError:
                pass
            raise KernelError(
                "{} — la répétition n'a pas été modifiée".format(exc))
        self._persist_repeat(
            obj, payload, mode, self._repeat_label(mode))
        return self.get_tree()

    def get_repeat_feature(self, feature):
        """Rend le JSON persisté sur la ligne de répétition."""
        from engine.kernel import KernelError
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        return self._load_repeat_json(obj)

    def graph_vocabulary(self):
        """Types de nœuds de la fonction graphe, libellés et ports.

        Lecture seule, sans document. Le client n'en tient pas de copie.
        """
        from engine.nodegraph import vocabulary
        return vocabulary()
