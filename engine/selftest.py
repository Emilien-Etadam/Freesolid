"""Selftest de bout en bout, hors du code de production.

``Kernel`` en hérite. Le corps est le déplacement de l'ancienne méthode :
les noms définis dans ``kernel.py`` sont importés au début de l'appel,
pour ne pas charger ce module au démarrage du serveur.
"""

class SelftestMixin:
    def selftest(self):
        """Run the whole flow end to end; return stats worth pasting back.

        Every step prints a live marker to the terminal and any failure
        names the step it died in — a silent selftest is worse than a
        failing one (learned when a user reported "the button does
        nothing").
        """
        import os
        from engine.kernel import (
            GraphError,
            KernelError,
            _explain,
            allow_from_environ,
            dangling_deps,
            dispatch,
            evaluate_instances,
            selftest_summary,
            version_status,
        )
        report = {"steps": []}

        def mark(name):
            report["steps"].append(name)
            print("selftest> {}".format(name), flush=True)

        try:
            mark("ping")
            report["ping"] = self.ping()
            platform = version_status(
                report["ping"]["freecad"],
                allow=allow_from_environ())
            report["freecad"] = platform["running"]
            report["freecad_reference"] = platform["reference"]
            banner = (
                "selftest> FreeCAD {} (référence {})".format(
                    platform["running"], platform["reference"]))
            if platform["override"]:
                report["freecad_override"] = True
                banner += " — REPLI EXPLICITE, mesures non comparables"
            print(banner, flush=True)
            if not platform["match"] and not platform["override"]:
                print("=" * 72, flush=True)
                print(platform["message"], flush=True)
                print("=" * 72, flush=True)
                report["freecad_plateforme"] = False
                raise KernelError(platform["message"])
            report["freecad_plateforme"] = True

            mark("m0: pièce + esquisse contrainte + bossage")
            tree = self.new_part("Pièce de test")
            report["m0_planes"] = [p["label"] for p in tree["planes"]]
            tree = self.add_rect_sketch(100, 60)
            sk_free = next(
                f["name"] for f in tree["features"]
                if f["type"] == "Sketcher::SketchObject")
            mesh = self.tessellate()
            found = next((s for s in mesh.get("sketches") or []
                          if s["name"] == sk_free), None)
            free_ok = bool(found and found.get("positions"))
            tree = self.add_pad(10)
            report["m0_body_solid"] = (
                bool(tree["bodies"])
                and tree["bodies"][0].get("has_solid") is True)
            mesh = self.tessellate()
            report["p3_free_sketch_in_mesh"] = (
                free_ok
                and not any(s["name"] == sk_free
                            for s in mesh.get("sketches") or []))
            report["m0_faces"] = len(mesh["groups"])
            match = getattr(self, "_face_match", None) or {}
            report["p038_face_producers"] = (
                report["m0_faces"] == 6
                and all(g.get("feature") for g in mesh["groups"])
                and match.get("matched") == 6
                and match.get("tip", 1) == 0
            )

            mark("m0: reparamétrage 10 → 25")
            pad = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            self.set_param(pad, "Length", 25.0)
            report["m0_reparam_ok"] = self.tessellate() != mesh

            mark("m1: esquisse sur face + enlèvement à travers tout + congé")
            top = self._top_face_id()
            report["m1_top_face"] = top
            self.add_rect_sketch(40, 20, face=top)
            self.add_pocket(through=True)
            report["m1_pocket_faces"] = len(self.tessellate()["groups"])
            tree = self.add_fillet(3, face=self._top_face_id())
            report["m1_fillet_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("m1.5: barre de retour aller-retour")
            pad_feature = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pad")
            faces_rolled = len(self.tessellate()["groups"])
            self.set_tip(pad_feature)
            report["m15_rollback_changes_shape"] = (
                len(self.tessellate()["groups"]) != faces_rolled)
            self.tip_to_end()

            mark("m1.5: enregistrer puis rouvrir")
            import tempfile
            path = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.FCStd")
            self.save_part(path)
            tree_before = self.get_tree()
            reopened = self.open_part(path)
            report["m15_roundtrip_ok"] = (
                [f["type"] for f in reopened["features"]]
                == [f["type"] for f in tree_before["features"]])

            mark("m2: rectangle dessiné ligne à ligne")
            state = self.sketch_start()
            name = state["sketch"]
            self.sketch_add_line(name, 0, 0, 80, 0)
            self.sketch_add_line(name, 80, 0, 80, 40)
            self.sketch_add_line(name, 80, 40, 0, 40)
            self.sketch_add_line(name, 0, 40, 0, 0)
            constraints = len(self._get_sketch(name).Constraints)
            # 4 snapped lines: 4 coincidents + 2 horizontal + 2 vertical.
            report["m2_autoconstraints"] = constraints
            report["m2_autoconstraints_ok"] = constraints >= 8

            mark("m2: drag suivi par le solveur")
            self.sketch_move(name, 1, 2, 85, 45)

            mark("m2: cote pilotante à 90")
            state = self.sketch_dim(name, 0)
            dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(name, dim, 90)
            report["m2_dim_drives"] = any(
                abs(d["value"] - 90) < 1e-6 for d in state["dims"])
            report["m2_dof"] = state["dof"]

            mark("m2: extrusion du profil dessiné")
            self.sketch_finish(name)
            tree = self.add_pad(8, sketch=name)
            report["m2_pad_on_drawn_sketch_ok"] = not any(
                f["error"] for f in tree["features"])
            # L'esquisse consommée doit être rangée SOUS son bossage.
            report["m2_sketch_nested_ok"] = any(
                child["name"] == name
                for f in tree["features"]
                for child in f.get("children", ()))

            mark("p1: annuler / rétablir via transactions")
            state = self.sketch_start()
            sk_name = state["sketch"]
            out = dispatch(self, "sketch_add_line",
                           {"sketch": sk_name,
                            "x1": 0, "y1": 0, "x2": 10, "y2": 0})
            if not out["ok"]:
                raise KernelError(out["error"])
            count = len(self._get_sketch(sk_name).Geometry)
            self.undo()
            report["p1_undo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count - 1)
            self.redo()
            report["p1_redo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count)

            mark("p1: géométrie de construction")
            state = self.sketch_toggle_construction(sk_name, 0)
            report["p1_construction_ok"] = bool(
                state["entities"][0].get("construction"))
            self.sketch_finish(sk_name)

            mark("p1: esquisse sur plan nommé (XZ = Plan de face)")
            state = self.sketch_start(plane="XZ")
            identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            report["p1_plane_ok"] = (
                [round(v, 6) for v in state["placement"]] != identity)
            self.sketch_finish(state["sketch"])

            mark("p1: export STL + STEP")
            stl = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest.stl")
            step = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.step")
            report["p1_export_stl_ok"] = self.export_part(stl)["size"] > 0
            report["p1_export_step_ok"] = self.export_part(step)["size"] > 0

            mark("p2: révolution (tube) + enlèvement avec révolution")
            self.new_part("Pièce révolution")
            state = self.sketch_start()
            rev_sk = state["sketch"]
            for line in ((10, 0, 30, 0), (30, 0, 30, 20),
                         (30, 20, 10, 20), (10, 20, 10, 0)):
                self.sketch_add_line(rev_sk, *line)
            self.sketch_finish(rev_sk)
            tree = self.add_revolution(360, sketch=rev_sk)
            report["p2_revolution_ok"] = not any(
                f["error"] for f in tree["features"])
            state = self.sketch_start()
            groove_sk = state["sketch"]
            for line in ((15, 8, 25, 8), (25, 8, 25, 12),
                         (25, 12, 15, 12), (15, 12, 15, 8)):
                self.sketch_add_line(groove_sk, *line)
            self.sketch_finish(groove_sk)
            tree = self.add_groove(360, sketch=groove_sk)
            report["p2_groove_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: révolution autour d'une ligne de construction")
            import math
            self.new_part("Pièce axe")
            state = self.sketch_start()
            axis_sk = state["sketch"]
            for line in ((10, 0, 20, 0), (20, 0, 20, 10),
                         (20, 10, 10, 10), (10, 10, 10, 0)):
                self.sketch_add_line(axis_sk, *line)
            state = self.sketch_add_line(axis_sk, 5, -2, 5, 12)
            axis_id = state["entities"][-1]["id"]
            self.sketch_toggle_construction(axis_sk, axis_id)
            self.sketch_finish(axis_sk)
            tree = self.add_revolution(
                360, sketch=axis_sk, axis="line:{}".format(axis_id))
            rev = next(f for f in tree["features"]
                       if f["type"] == "PartDesign::Revolution")
            sketch_child = rev["children"][0]
            tube = abs(float(self._require_body().Shape.Volume)
                       - 2000.0 * math.pi) < 1.0
            report["p2_revolution_axis_ok"] = (
                tube
                and rev.get("revolution", {}).get("axis") == "line:{}".format(axis_id)
                and any(line["id"] == axis_id and line["construction"]
                        for line in sketch_child.get("lines") or []))
            tree = self.set_params(rev["name"], {"axis": "vertical"})
            rev = next(f for f in tree["features"]
                       if f["type"] == "PartDesign::Revolution")
            report["p2_revolution_axis_edit_ok"] = (
                abs(float(self._require_body().Shape.Volume)
                    - 3000.0 * math.pi) < 1.0
                and rev.get("revolution", {}).get("axis") == "vertical")
            kept = float(self._require_body().Shape.Volume)
            refused = False
            try:
                self.set_params(rev["name"], {"axis": "sommet"})
            except KernelError:
                refused = True
            report["p2_revolution_axis_refused"] = (
                refused
                and abs(float(self._require_body().Shape.Volume) - kept) < 0.01)
            tree = self.set_params(rev["name"], {"Midplane": True})
            rev = next(f for f in tree["features"]
                       if f["type"] == "PartDesign::Revolution")
            report["p2_revolution_midplane_ok"] = (
                rev.get("revolution", {}).get("midplane") is True
                and not rev.get("error"))

            mark("p2: symétrie + répétition linéaire")
            self.new_part("Pièce symétrie")
            state = self.sketch_start()
            sym_sk = state["sketch"]
            for line in ((0, -10, 20, -10), (20, -10, 20, 10),
                         (20, 10, 0, 10), (0, 10, 0, -10)):
                self.sketch_add_line(sym_sk, *line)
            self.sketch_finish(sym_sk)
            self.add_pad(10, sketch=sym_sk)
            tree = self.add_mirror(plane="YZ")
            report["p2_mirror_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_linear_pattern(length=20, count=2, axis="Y")
            report["p2_linear_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: répétition circulaire (4 perçages)")
            self.new_part("Pièce répétition")
            self.add_rect_sketch(60, 60)
            self.add_pad(6)
            state = self.sketch_start(face=self._top_face_id())
            pat_sk = state["sketch"]
            self.sketch_add_circle(pat_sk, 20, 0, 4)
            self.sketch_finish(pat_sk)
            self.add_pocket(through=True)
            tree = self.add_polar_pattern(count=4)
            report["p2_polar_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: dépouille + coque")
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            top = self._top_face_id()
            try:
                self.add_draft(face=top, angle=5, neutral="XY")
                report["p2_draft_noop_refuse"] = False
            except KernelError:
                tree = self.get_tree()
                report["p2_draft_noop_refuse"] = not any(
                    f["type"] == "PartDesign::Draft" for f in tree["features"])
            vol_before = float(self._require_body().Shape.Volume)
            tree = self.add_draft(face=top, angle=5, neutral="XZ")
            report["p2_draft_neutral_ok"] = (
                not any(f["error"] for f in tree["features"])
                and abs(float(self._require_body().Shape.Volume)
                        - vol_before) > 1e-9)
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            tree = self.add_draft(face=self._side_face_id(), angle=5)
            report["p2_draft_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_thickness(self._top_face_id(), 2)
            report["p2_thickness_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p4: aperçu jaune (exécuté puis annulé)")
            # Sur sa propre géométrie saine : chanfreiner le bord d'une
            # coque dépouillée segfaultait ChFi3d dans OCCT 7.8 (SIGSEGV
            # vu sur 1.1.3) — un crash C++, ininterceptable en Python.
            self.new_part("Pièce aperçu")
            self.add_rect_sketch(30, 30)
            self.add_pad(10)
            count = len(self.get_tree()["features"])
            faces_now = len(self.tessellate()["groups"])
            ghost = self.preview(
                "add_chamfer", {"face": self._top_face_id(), "size": 2})
            report["p4_preview_changes_mesh"] = (
                len(ghost["groups"]) != faces_now)
            report["p4_preview_leaves_doc_intact"] = (
                len(self.get_tree()["features"]) == count
                and len(self.tessellate()["groups"]) == faces_now)
            vol_before = float(self._require_body().Shape.Volume)
            top_edges = [i for i, e in
                         enumerate(self._require_body().Shape.Edges)
                         if abs(e.CenterOfMass.z - 10) < 1e-6]
            tree = self.add_chamfer(size=2, edges=[top_edges[0]])
            vol_chamfered = float(self._require_body().Shape.Volume)
            report["p4_chamfer_commit_ok"] = (
                not any(f["error"] for f in tree["features"])
                and (vol_chamfered < vol_before - 1e-6
                     or len(self.tessellate()["groups"]) > faces_now))
            chamfer_name = next(f["name"] for f in tree["features"]
                                if f["type"] == "PartDesign::Chamfer")
            tree = self.delete_feature(chamfer_name)
            chamfer_gone = (
                not any(f["type"] == "PartDesign::Chamfer"
                        for f in tree["features"])
                and not any(f["error"] for f in tree["features"]))
            # delete_feature du Tip laisse Tip=None et Shape invalide
            # (constat P007, hors périmètre). Indicateur faux, l'étape
            # continue — p5 repart sur une pièce neuve.
            try:
                vol_restored = abs(
                    float(self._require_body().Shape.Volume)
                    - vol_before) < 1e-6
            except RuntimeError:
                vol_restored = False
            report["p4_delete_feature_ok"] = chamfer_gone and vol_restored

            mark("p4b: chanfrein deux distances, distance-angle, inversion")
            self.new_part("Pièce chanfrein")
            self.add_rect_sketch(40, 30)
            self.add_pad(20)

            def _verts():
                shape = self._require_body().Shape
                solids = list(getattr(shape, "Solids", None) or [])
                solid = solids[0] if solids else shape
                return tuple(sorted(
                    (round(float(v.Point.x), 3),
                     round(float(v.Point.y), 3),
                     round(float(v.Point.z), 3))
                    for v in solid.Vertexes))

            def _top_edge():
                return next(
                    i for i, item in
                    enumerate(self._require_body().Shape.Edges)
                    if abs(item.CenterOfMass.z - 20) < 1e-6)

            edge = _top_edge()
            tree = self.add_chamfer(size=2, edges=[edge])
            made = next(f for f in tree["features"]
                        if f["type"] == "PartDesign::Chamfer")
            equal_verts = _verts()
            report["p4_chamfer_equal_ok"] = (
                made.get("chamfer", {}).get("type") == "egale"
                and abs(made["chamfer"]["size"] - 2) < 1e-6
                and made["chamfer"]["flip"] is False
                and [p["prop"] for p in made.get("params") or []] == ["Size"]
                and not made.get("error"))
            tree = self.set_params(made["name"], {
                "ChamferType": "deux", "Size2": 5, "FlipDirection": False})
            made = next(f for f in tree["features"] if f["name"] == made["name"])
            two_verts = _verts()
            report["p4_chamfer_two_ok"] = (
                made["chamfer"]["type"] == "deux"
                and abs(made["chamfer"]["size2"] - 5) < 1e-6
                and two_verts != equal_verts
                and [p["prop"] for p in made.get("params") or []]
                == ["Size", "Size2"]
                and not made.get("error"))
            tree = self.set_params(made["name"], {"FlipDirection": True})
            made = next(f for f in tree["features"] if f["name"] == made["name"])
            report["p4_chamfer_flip_ok"] = (
                made["chamfer"]["flip"] is True
                and _verts() != two_verts
                and not made.get("error"))

            self.new_part("Pièce chanfrein angle")
            self.add_rect_sketch(40, 30)
            self.add_pad(20)
            edge = _top_edge()
            tree = self.add_chamfer(
                size=4, angle=30, chamfer_type="angle", flip=True, edges=[edge])
            made = next(f for f in tree["features"]
                        if f["type"] == "PartDesign::Chamfer")
            report["p4_chamfer_angle_ok"] = (
                made["chamfer"]["type"] == "angle"
                and abs(made["chamfer"]["angle"] - 30) < 1e-6
                and made["chamfer"]["flip"] is True
                and _verts() != equal_verts
                and [p["prop"] for p in made.get("params") or []]
                == ["Size", "Angle"]
                and not made.get("error"))
            before = len(tree["features"])
            try:
                self.add_chamfer(size=2, edges=[edge], chamfer_type="sommet")
                refused = False
            except KernelError as exc:
                refused = "type de chanfrein" in str(exc)
            report["p4_chamfer_type_refused"] = (
                refused and len(self.get_tree()["features"]) == before)

            mark("p5: congé sur arêtes")
            self.new_part("Pièce arêtes")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            edges_pack = self.tessellate_edges()
            report["p5_edges"] = len(edges_pack["groups"])
            top_edges = [i for i, e in
                         enumerate(self._require_body().Shape.Edges)
                         if abs(e.CenterOfMass.z - 10) < 1e-6]
            report["p5_top_edges"] = len(top_edges)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_fillet(radius=3, edges=top_edges)
            report["p5_edge_fillet_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("q1: congé trop grand et coque trop épaisse")
            self.new_part("Pièce refus")
            self.add_rect_sketch(40, 30)
            self.add_pad(12)
            edge = next(
                i for i, item in enumerate(self._require_body().Shape.Edges)
                if abs(item.CenterOfMass.z - 12) < 1e-6)
            try:
                self.add_fillet(100, edges=[edge])
                report["q1_conge_trop_grand"] = False
            except KernelError as exc:
                text = str(exc)
                tree = self.get_tree()
                report["q1_conge_trop_grand"] = (
                    "réduisez le rayon" in text
                    and "command not done" not in text
                    and "SolidWorks" not in text
                    and not any(f.get("error") for f in tree["features"]))
            try:
                self.add_thickness(self._top_face_id(), 30)
                report["q1_coque_trop_epaisse"] = False
            except KernelError as exc:
                text = str(exc)
                tree = self.get_tree()
                report["q1_coque_trop_epaisse"] = (
                    "épaisseur est trop forte" in text
                    and not any(f.get("error") for f in tree["features"]))
            tree = self.add_thickness(self._top_face_id(), 2)
            report["q1_coque_valide_apres_refus"] = (
                not any(f.get("error") for f in tree["features"])
                and abs(float(self._require_body().Shape.Volume) - 5040) < 1e-2)

            mark("p6: assistant de perçage (2 trous lamés)")
            self.new_part("Pièce perçages")
            self.add_rect_sketch(60, 40)
            self.add_pad(8)
            state = self.sketch_start(face=self._top_face_id())
            hole_sk = state["sketch"]
            self.sketch_add_circle(hole_sk, -15, 0, 3)
            self.sketch_add_circle(hole_sk, 15, 0, 3)
            self.sketch_finish(hole_sk)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_hole(diameter=6, through=True,
                                 cut="lamage", cut_diameter=11, cut_depth=3)
            report["p6_hole_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("p6: renommer + édition atomique")
            hole_name = next(f["name"] for f in tree["features"]
                             if f["type"] == "PartDesign::Hole")
            tree = self.rename(hole_name, "Perçages de fixation")
            report["p6_rename_ok"] = any(
                f["label"] == "Perçages de fixation"
                for f in tree["features"])
            self.set_params(hole_name, {"Diameter": 8.0})
            report["p6_set_params_ok"] = any(
                p["prop"] == "Diameter" and abs(p["value"] - 8.0) < 1e-9
                for p in self.get_params(hole_name)["params"])

            mark("p7: paramétrique — cote nommée, variable, équation")
            self.new_part("Pièce paramétrique")
            state = self.sketch_start()
            par = state["sketch"]
            self.sketch_add_line(par, 0, 0, 60, 0)     # géo 0 : largeur
            self.sketch_add_line(par, 60, 0, 60, 30)   # géo 1 : hauteur
            state = self.sketch_dim(par, 0)            # cote sur la largeur
            width_dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(par, width_dim,
                                        value=60, name="largeur")
            report["p7_named_dim_ok"] = any(
                d["id"] == width_dim and d["name"] == "largeur"
                for d in state["dims"])
            self.set_variable("coef", 2.0)
            state = self.sketch_dim(par, 1)            # cote sur la hauteur
            height_dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(
                par, height_dim,
                expr=".Constraints.largeur / Variables.coef")
            height = next(d for d in state["dims"] if d["id"] == height_dim)
            report["p7_equation_ok"] = abs(height["value"] - 30.0) < 1e-6
            report["p7_equation_shown"] = bool(height["expr"])
            listed = self.list_variables()
            report["p7_list_variables_ok"] = any(
                v["name"] == "coef" and abs(v["value"] - 2.0) < 1e-9
                for v in listed["variables"])
            tree = self.get_tree()
            report["p7_tree_variables"] = any(
                v["name"] == "coef" and abs(v["value"] - 2.0) < 1e-9
                for v in tree.get("variables", []))
            self.set_variable("jetable", 1.0)
            listed = self.list_variables()
            self.delete_variable("jetable")
            listed_after = self.list_variables()
            report["p7_delete_variable_ok"] = (
                any(v["name"] == "jetable" for v in listed["variables"])
                and not any(v["name"] == "jetable"
                            for v in listed_after["variables"]))

            mark("p7: expression sur une fonction (Length = largeur/10)")
            self.sketch_add_line(par, 60, 30, 0, 30)
            self.sketch_add_line(par, 0, 30, 0, 0)
            self.sketch_finish(par)
            tree = self.add_pad(10, sketch=par)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.set_params(pad_name, {
                "Length": "{}.Constraints.largeur / 10".format(par)})
            pad_length = next(
                p for p in self.get_params(pad_name)["params"]
                if p["prop"] == "Length")
            report["p7_feature_expr_ok"] = (
                abs(pad_length["value"] - 6.0) < 1e-6
                and bool(pad_length.get("expr")))

            mark("p7: relations — concentrique, colinéaire, milieu, fixe")
            state = self.sketch_start()
            rel = state["sketch"]
            self.sketch_add_circle(rel, 0, 0, 10)      # géo 0
            self.sketch_add_circle(rel, 5, 5, 4)       # géo 1
            state = self.sketch_constrain(rel, "concentric", 0, geo2=1)
            circles = [e for e in state["entities"] if e["type"] == "circle"]
            report["p7_concentric_ok"] = (
                abs(circles[0]["c"][0] - circles[1]["c"][0]) < 1e-6
                and abs(circles[0]["c"][1] - circles[1]["c"][1]) < 1e-6)
            self.sketch_add_line(rel, 20, 0, 40, 2)    # géo 2
            self.sketch_add_line(rel, 45, 3, 60, 5)    # géo 3
            self.sketch_constrain(rel, "collinear", 2, geo2=3)
            self.sketch_add_circle(rel, 25, 10, 2)     # géo 4
            state = self.sketch_constrain(rel, "midpoint", 2,
                                          geo2=4, point2=3)
            self.sketch_constrain(rel, "fixed", 3)
            report["p7_relations_ok"] = True

            mark("p7: lister et supprimer une relation")
            listed = self.sketch_constraints(rel, geo=2)
            report["p7_list_count"] = len(listed["constraints"])
            before = len(self._get_sketch(rel).Constraints)
            self.sketch_delete_constraint(
                rel, listed["constraints"][-1]["id"])
            report["p7_delete_constraint_ok"] = (
                len(self._get_sketch(rel).Constraints) == before - 1)
            self.sketch_finish(rel)

            mark("p8: plan de référence décalé + lissage")
            self.new_part("Pièce lissage")
            tree = self.add_datum_plane(base="XY", offset=30)
            datum = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Plane")
            report["p8_datum_has_placement"] = any(
                "placement" in f for f in tree["features"])
            self.add_rect_sketch(40, 40)
            base_sk = self._latest_sketch().Name
            state = self.sketch_start(datum=datum)
            top_sk = state["sketch"]
            for line in ((-10, -10, 10, -10), (10, -10, 10, 10),
                         (10, 10, -10, 10), (-10, 10, -10, -10)):
                self.sketch_add_line(top_sk, *line)
            self.sketch_finish(top_sk)
            tree = self.add_loft(sketches=[base_sk, top_sk])
            report["p8_loft_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > 0)

            mark("p8: balayage (profil + trajectoire)")
            self.new_part("Pièce balayage")
            state = self.sketch_start(plane="XZ")
            spine_sk = state["sketch"]
            self.sketch_add_line(spine_sk, 0, 0, 0, 30)
            self.sketch_add_line(spine_sk, 0, 30, 25, 30)
            self.sketch_finish(spine_sk)
            state = self.sketch_start()
            prof_sk = state["sketch"]
            self.sketch_add_circle(prof_sk, 0, 0, 4)
            self.sketch_finish(prof_sk)
            tree = self.add_sweep(profile=prof_sk, spine=spine_sk)
            report["p8_sweep_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p8: hélice (ressort)")
            self.new_part("Pièce hélice")
            state = self.sketch_start(plane="XZ")
            hel_sk = state["sketch"]
            self.sketch_add_circle(hel_sk, 15, 0, 2)
            self.sketch_finish(hel_sk)
            tree = self.add_helix(pitch=8, height=40, sketch=hel_sk)
            report["p8_helix_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p9: multi-corps + Combiner (soustraction)")
            self.new_part("Pièce multi-corps")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            first_body = self._require_body().Name
            tree = self.add_body("Corps outil")
            report["p9_two_bodies"] = (
                len(tree["bodies"]) == 2
                and any(b["active"] and b["label"] == "Corps outil"
                        for b in tree["bodies"]))
            state = self.sketch_start()
            tool_sk = state["sketch"]
            self.sketch_add_circle(tool_sk, 0, 0, 8)
            self.sketch_finish(tool_sk)
            self.add_pad(30)
            report["p9_others_shown"] = "others" in self.tessellate()
            tool_body = self._require_body().Name
            self.set_active_body(first_body)
            tree = self.set_body_color(first_body, "#cc5533")
            report["p9_color_ok"] = any(
                b["name"] == first_body and b.get("color") == "#cc5533"
                for b in tree["bodies"])
            try:
                self.set_body_color(first_body, "rouge")
                report["p9_color_invalid_ok"] = False
            except KernelError:
                report["p9_color_invalid_ok"] = True
            import tempfile
            color_path = os.path.join(tempfile.gettempdir(),
                                      "freesolid-selftest-color.FCStd")
            self.save_part(color_path)
            reopened = self.open_part(color_path)
            report["p9_color_persist_ok"] = any(
                b["name"] == first_body and b.get("color") == "#cc5533"
                for b in reopened["bodies"])
            self.set_active_body(first_body)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_boolean(tool=tool_body, type="cut")
            report["p9_boolean_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("p10: assemblage — deux instances d'une pièce")
            self.new_part("Pièce à assembler")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            asm_part = os.path.join(tempfile.gettempdir(),
                                    "freesolid-selftest-part.FCStd")
            self.save_part(asm_part)
            self.new_assembly()
            self.insert_component(asm_part)
            tree = self.insert_component(asm_part)
            report["p10_two_components"] = len(tree["components"]) == 2
            second = tree["components"][1]["name"]
            tree = self.move_component(second, x=30, z=10, yaw=45)
            moved = next(c for c in tree["components"]
                         if c["name"] == second)
            report["p10_move_ok"] = abs(moved["position"][0] - 30) < 1e-9
            meshes = self.tessellate_assembly()
            report["p10_assembly_meshes_ok"] = (
                len(meshes["components"]) == 2
                and all(c["mesh"]["indices"]
                        for c in meshes["components"]))

            mark("p10: contrainte fixe — le solveur déplace le composant")
            first_comp = tree["components"][0]["name"]
            report["p10_first_grounded"] = tree["components"][0]["grounded"]
            tree = self.add_joint(first_comp, second,
                                  type="fixe", sub1="Face1", sub2="Face1")
            report["p10_joints_listed"] = len(tree.get("joints", ())) >= 2
            comp2 = next(c for c in tree["components"]
                         if c["name"] == second)
            # Il était en (30, 0, 10) yaw 45 — la contrainte fixe doit
            # l'avoir ramené ailleurs.
            report["p10_joint_solved"] = (
                abs(comp2["position"][0] - 30) > 1e-6
                or abs(comp2["position"][2] - 10) > 1e-6
                or abs(comp2["rotation"][0] - 45) > 1e-6)
            asm = self.assembly_tree()
            report["p10_assembly_tree_ok"] = (
                len(asm["components"]) == 2
                and len(asm.get("joints", ())) >= 2)
            solved = self.solve_assembly()
            report["p10_solve_op_ok"] = (
                len(solved["components"]) == 2
                and "joints" in solved)
            # 2 existants + (3 - 1) copies du second = 4 composants.
            arrayed = self.array_component(second, count=3, dx=80)
            report["p10_array_ok"] = len(arrayed["components"]) == 4

            mark("p16: interférences (les instances se chevauchent)")
            inter = self.check_interference()
            report["p16_interference_found"] = (
                len(inter["interferences"]) >= 1)

            mark("p11: évaluer (masse PLA) + mesurer")
            self.new_part("Pièce évaluée")
            self.add_rect_sketch(10, 10)
            self.add_pad(10)
            props = self.mass_properties(density=1.24)
            report["p11_volume_ok"] = abs(props["volume_mm3"] - 1000.0) < 1e-6
            report["p11_mass_ok"] = abs(props["mass_g"] - 1.24) < 1e-9
            body_shape = self._require_body().Shape
            bottom = next(
                i for i, f in enumerate(body_shape.Faces)
                if f.normalAt(*[sum(f.ParameterRange[k:k + 2]) / 2
                                for k in (0, 2)]).z < -0.5)
            distance = self.measure(
                "face", self._top_face_id(), "face", bottom)["distance"]
            report["p11_measure_ok"] = abs(distance - 10.0) < 1e-6

            mark("spike: solveur d'assemblage headless (rapport)")
            report["spike_assembly"] = self.spike_assembly()
            import json
            print("selftest> spike assemblage : " + json.dumps(
                report["spike_assembly"], ensure_ascii=False), flush=True)

            mark("p12: surfacique — extrusion, couture, épaississement")
            self.new_part("Pièce surfaces")
            state = self.sketch_start()
            surf_sk1 = state["sketch"]
            self.sketch_add_line(surf_sk1, 0, 0, 40, 0)  # profil OUVERT
            self.sketch_finish(surf_sk1)
            tree = self.surface_extrude(20, sketch=surf_sk1)
            report["p12_surface_ok"] = len(tree["surfaces"]) == 1
            report["p12_body_not_solid"] = (
                bool(tree["bodies"])
                and tree["bodies"][0].get("has_solid") is False)
            surf = tree["surfaces"][0]
            mesh = self.tessellate()
            surf_meshes = mesh.get("surfaces") or []
            report["p12_surface_mesh"] = (
                isinstance(surf_meshes, list)
                and len(surf_meshes) == 1
                and surf_meshes[0].get("name") == surf["name"]
                and len(surf_meshes[0].get("positions") or []) > 0)
            sk_child = next(
                (c for c in surf.get("children") or []
                 if c.get("name") == surf_sk1),
                None)
            report["p12_surface_order"] = (
                isinstance(surf.get("order"), int)
                and sk_child is not None
                and isinstance(sk_child.get("order"), int)
                and surf["order"] > sk_child["order"])
            state = self.sketch_start()
            surf_sk2 = state["sketch"]
            self.sketch_add_line(surf_sk2, 0, 0, 0, 30)
            self.sketch_finish(surf_sk2)
            tree = self.surface_extrude(20, sketch=surf_sk2)
            names = [s["name"] for s in tree["surfaces"]]
            tree = self.surface_sew(names)
            report["p12_sew_ok"] = len(tree["surfaces"]) == 3
            tree = self.surface_thicken(names[0], 2)
            thick = self._require_doc().getObject(
                tree["surfaces"][-1]["name"])
            report["p12_thicken_solid_ok"] = bool(thick.Shape.Solids)
            state = self.sketch_start()
            rev_sk = state["sketch"]
            self.sketch_add_line(rev_sk, 20, 0, 20, 30)
            self.sketch_finish(rev_sk)
            n_surfaces = len(self.get_tree()["surfaces"])
            tree = self.surface_revolve(360, sketch=rev_sk)
            report["p12_surface_revolve_ok"] = (
                any(s["label"] == "Surface de révolution"
                    for s in tree["surfaces"])
                and len(tree["surfaces"]) > n_surfaces)
            state = self.sketch_start()
            loft_a = state["sketch"]
            self.sketch_add_line(loft_a, 0, 0, 40, 0)
            self.sketch_finish(loft_a)
            tree = self.add_datum_plane(base="XY", offset=25)
            datum = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Plane")
            state = self.sketch_start(datum=datum)
            loft_b = state["sketch"]
            self.sketch_add_line(loft_b, -10, -10, 10, 10)
            self.sketch_finish(loft_b)
            n_surfaces = len(self.get_tree()["surfaces"])
            tree = self.surface_loft([loft_a, loft_b])
            report["p12_surface_loft_ok"] = (
                any(s["label"] == "Surface lissée" for s in tree["surfaces"])
                and len(tree["surfaces"]) > n_surfaces)

            # Surfaces paramétriques : édition, suivi d'esquisse, expression,
            # persistance après save/open.
            self.new_part("Pièce surface edit")
            state = self.sketch_start()
            edit_sk = state["sketch"]
            self.sketch_add_line(edit_sk, 0, 0, 40, 0)
            self.sketch_finish(edit_sk)
            tree = self.surface_extrude(20, sketch=edit_sk)
            surf = tree["surfaces"][-1]
            surf_obj = self._require_doc().getObject(surf["name"])
            area_20 = float(surf_obj.Shape.Area)
            self.set_params(surf["name"], {"LengthFwd": 40.0})
            surf_obj = self._require_doc().getObject(surf["name"])
            area_40 = float(surf_obj.Shape.Area)
            report["p12_surface_edit_ok"] = (
                surf.get("type") == "Part::Extrusion"
                and edit_sk in (surf.get("sketches") or [])
                and abs(area_40 - 2.0 * area_20) < 1e-3)
            self.sketch_edit(edit_sk)
            self.sketch_move(edit_sk, 0, 2, 80, 0)
            self.sketch_finish(edit_sk)
            surf_obj = self._require_doc().getObject(surf["name"])
            area_follow = float(surf_obj.Shape.Area)
            report["p12_surface_follows_sketch_ok"] = (
                abs(area_follow - 2.0 * area_40) < 1e-2
                and "Invalid" not in (surf_obj.State or ()))
            self.set_params(surf["name"], {"LengthFwd": "15 * 2"})
            surf_obj = self._require_doc().getObject(surf["name"])
            length_expr = float(getattr(
                surf_obj.LengthFwd, "Value", surf_obj.LengthFwd))
            report["p12_surface_expr_ok"] = abs(length_expr - 30.0) < 1e-6
            surf_path = os.path.join(tempfile.gettempdir(),
                                     "freesolid-surface-edit.FCStd")
            self.save_part(surf_path)
            self.open_part(surf_path)
            tree = self.get_tree()
            reopened = next(
                (s for s in tree["surfaces"]
                 if s.get("type") == "Part::Extrusion"),
                None)
            if reopened is None:
                report["p12_surface_reopen_ok"] = False
            else:
                self.set_params(reopened["name"], {"LengthFwd": 25.0})
                reopened_obj = self._require_doc().getObject(reopened["name"])
                length_re = float(getattr(
                    reopened_obj.LengthFwd, "Value", reopened_obj.LengthFwd))
                report["p12_surface_reopen_ok"] = (
                    abs(length_re - 25.0) < 1e-6
                    and bool(reopened_obj.Shape.Faces)
                    and "Invalid" not in (reopened_obj.State or ()))

            mark("p12: courbe 3D + balayage dessus")
            curve_tree = self.add_curve3d(
                [[0, 0, 0], [0, 0, 30], [20, 0, 50]], spline=True)
            curve_name = curve_tree["surfaces"][-1]["name"]
            state = self.sketch_start()
            pipe_sk = state["sketch"]
            self.sketch_add_circle(pipe_sk, 0, 0, 3)
            self.sketch_finish(pipe_sk)
            tree = self.add_sweep(profile=pipe_sk, spine=curve_name)
            report["p12_sweep_on_curve_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p30: barre de retour — surfaces et esquisses libres")
            self.new_part("Pièce reprise P030")
            self.add_rect_sketch(40, 20)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            state = self.sketch_start()
            free_sk = state["sketch"]
            self.sketch_add_line(free_sk, 0, 0, 30, 0)
            self.sketch_finish(free_sk)
            state = self.sketch_start()
            surf_sk = state["sketch"]
            self.sketch_add_line(surf_sk, 0, 0, 20, 0)
            self.sketch_finish(surf_sk)
            tree = self.surface_extrude(15, sketch=surf_sk)
            surf_name = tree["surfaces"][-1]["name"]

            tree = self.set_tip(free_sk)
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_set_tip_on_sketch"] = (
                tree["tip"] == pad_name
                and free_entry.get("rolled_back") is not True
                and surf_entry.get("rolled_back") is True)
            mesh = self.tessellate()
            report["p30_rolled_surface_absent_mesh"] = not any(
                s.get("name") == surf_name
                for s in mesh.get("surfaces") or [])

            tree = self.set_tip(surf_name)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_set_tip_on_surface"] = (
                tree["tip"] == pad_name
                and surf_entry.get("rolled_back") is not True)

            tree = self.set_tip(pad_name)
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            mesh = self.tessellate()
            report["p30_rolled_sketch_absent_mesh"] = (
                free_entry.get("rolled_back") is True
                and not any(s.get("name") == free_sk
                            for s in mesh.get("sketches") or []))
            try:
                self.add_pad(5)
                report["p30_rolled_sketch_not_reusable"] = False
            except KernelError as exc:
                report["p30_rolled_sketch_not_reusable"] = (
                    "aucune esquisse disponible" in str(exc))

            tree = self.tip_to_end()
            mesh = self.tessellate()
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_tip_to_end_restores"] = (
                tree["tip"] == pad_name
                and free_entry.get("rolled_back") is not True
                and surf_entry.get("rolled_back") is not True
                and any(s.get("name") == surf_name
                        for s in mesh.get("surfaces") or [])
                and any(s.get("name") == free_sk
                        for s in mesh.get("sketches") or []))

            mark("p13: mise en plan DXF (3 vues, cotes, coupe)")
            self.new_part("Pièce plan")
            self.add_rect_sketch(30, 20)
            self.add_pad(10)
            dxf = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest.dxf")
            drawing = self.make_drawing(dxf, dims=True, section="Y")
            report["p13_drawing_ok"] = drawing["size"] > 0
            report["p13_dims_ok"] = drawing.get("dims_ok") is True
            report["p13_section_ok"] = drawing.get("section_ok") is True
            report["p13_drawing_clean_ok"] = not any(
                o.TypeId.startswith("TechDraw::")
                for o in self._require_doc().Objects)

            mark("p14: convertir les entités (contour de face)")
            self.new_part("Pièce conversion")
            self.add_rect_sketch(30, 20)
            self.add_pad(6)
            state = self.sketch_start(face=self._top_face_id())
            conv = state["sketch"]
            state = self.sketch_convert(conv)
            report["p14_convert_ok"] = (
                state["converted"] == 4 and state["skipped"] == 0)
            self.sketch_finish(conv)

            mark("p15: gravure de texte")
            self.new_part("Pièce gravée")
            self.add_rect_sketch(60, 20)
            self.add_pad(5)
            faces_now = len(self.tessellate()["groups"])
            tree = self.add_text("AB", face=self._top_face_id(),
                                 size=8, depth=1)
            # Volume et validité, pas seulement le compte de faces : la
            # gravure « AB » rendait un corps invalide de 17 mm³ (faces de
            # glyphes d'aire négative) sans que ce test le voie (P032).
            plate = self._require_body().Shape
            report["p15_text_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_now
                and plate.isValid()
                and 5900.0 < float(plate.Volume) < 5999.9)

            mark("p17: spline, ellipse, symétrie, répétition et décalage")
            self.new_part("Pièce esquisse confort")
            state = self.sketch_start()
            comfort = state["sketch"]
            state = self.sketch_add_spline(
                comfort, [[0, 0], [10, 8], [20, -4], [30, 6]])
            spline = next((e for e in state["entities"]
                           if e.get("kind") == "spline"), None)
            report["p17_spline_ok"] = (
                spline is not None
                and spline.get("type") == "poly"
                and (spline.get("npoints") or 0) >= 3)
            state = self.sketch_add_ellipse(comfort, 50, 0, 12, 6,
                                            angle=15)
            ellipse = next((e for e in state["entities"]
                            if e.get("kind") == "ellipse"), None)
            report["p17_ellipse_ok"] = (
                len(state["entities"]) == 2
                and ellipse is not None
                and abs(ellipse.get("rx", 0) - 12) < 1e-4
                and abs(ellipse.get("ry", 0) - 6) < 1e-4)
            self.sketch_add_line(comfort, 0, 20, 20, 30)   # géo 2
            self.sketch_add_line(comfort, 0, 40, 40, 40)   # géo 3 : axe
            state = self.sketch_mirror(comfort, [2], 3)
            report["p17_mirror_ok"] = len(state["entities"]) == 5
            state = self.sketch_array(comfort, [2], dx=15, dy=0,
                                      cols=3, rows=1)
            # 2 copies + 2 lignes de construction qui pilotent le pas
            # (comportement addRectangularArray, sondé sur 1.0.2).
            report["p17_array_ok"] = len(state["entities"]) == 9
            self.sketch_finish(comfort)

            state = self.sketch_start()
            offset_sk = state["sketch"]
            self.sketch_add_line(offset_sk, 0, 0, 40, 0)
            self.sketch_add_line(offset_sk, 40, 0, 40, 30)
            self.sketch_add_line(offset_sk, 40, 30, 0, 30)
            state = self.sketch_add_line(offset_sk, 0, 30, 0, 0)
            orig_lines = [e for e in state["entities"] if e["type"] == "line"]
            before = len(state["entities"])
            state = self.sketch_offset(offset_sk, [0, 1, 2, 3], 5.0)
            new_ents = state["entities"][before:]
            dist_ok = False
            for new_line in new_ents:
                if new_line["type"] != "line":
                    continue
                for orig in orig_lines:
                    oh = abs(orig["p1"][1] - orig["p2"][1]) < 1e-6
                    nh = abs(new_line["p1"][1] - new_line["p2"][1]) < 1e-6
                    if oh and nh:
                        gap = abs(orig["p1"][1] - new_line["p1"][1])
                        if abs(gap - 5.0) < 1e-4:
                            dist_ok = True
                    ov = abs(orig["p1"][0] - orig["p2"][0]) < 1e-6
                    nv = abs(new_line["p1"][0] - new_line["p2"][0]) < 1e-6
                    if ov and nv:
                        gap = abs(orig["p1"][0] - new_line["p1"][0])
                        if abs(gap - 5.0) < 1e-4:
                            dist_ok = True
            report["p17_offset_ok"] = len(new_ents) >= 4 and dist_ok

            state = self.sketch_add_circle(offset_sk, 80, 0, 10)
            circ = next(e for e in state["entities"] if e["type"] == "circle")
            known = {e["id"] for e in state["entities"]}
            state = self.sketch_offset(offset_sk, [circ["id"]], 5.0,
                                       construction=True)
            original = next(e for e in state["entities"]
                            if e["id"] == circ["id"])
            report["p17_offset_originaux_construction"] = bool(
                original["construction"])
            # Contour fermé : extérieur par défaut, intérieur si inversé,
            # et l'aperçu ne touche pas à l'esquisse.
            count = len(state["entities"])
            outer = self.sketch_offset_preview(offset_sk, [circ["id"]], 2.0)
            inner = self.sketch_offset_preview(offset_sk, [circ["id"]], 2.0,
                                               reversed=True)
            radius = lambda pts: max(math.hypot(x - 80, y)  # noqa: E731
                                     for x, y in pts)
            # Congé d'esquisse : les cotes des lignes restent (coin gardé)
            # et le rayon est coté.
            name = self.sketch_start()["sketch"]
            self.sketch_add_line(name, 0, 50, 0, 90)
            self.sketch_add_line(name, 0, 90, 50, 90)
            self.sketch_dim(name, 0, value=40)
            self.sketch_dim(name, 1, value=50)
            filleted = self.sketch_fillet(name, 0, 1, 0, 80, 10, 90, 20)
            kept = sorted(d["type"] for d in filleted["dims"])
            report["p17_conge_garde_cotes"] = (
                kept == ["Distance", "Distance", "Radius"]
                and any(e["type"] == "point" for e in filleted["entities"]))
            report["p17_offset_sens"] = (
                abs(radius(outer["points"]) - 12) < 0.1
                and abs(radius(inner["points"]) - 8) < 0.1
                and len(self.sketch_state(offset_sk)["entities"]) == count)
            report["p17_offset_circle_ok"] = any(
                e["type"] == "circle" and e["id"] not in known
                and (abs(e["r"] - 15.0) < 1e-4 or abs(e["r"] - 5.0) < 1e-4)
                for e in state["entities"])

            state = self.sketch_add_line(offset_sk, 200, 0, 220, 0)
            id_a = state["entities"][-1]["id"]
            state = self.sketch_add_line(offset_sk, 200, 30, 220, 30)
            id_b = state["entities"][-1]["id"]
            disjoint_ok = False
            try:
                self.sketch_offset(offset_sk, [id_a, id_b], 5.0)
            except KernelError as exc:
                disjoint_ok = "chaîne connexe" in str(exc)
            report["p17_offset_disjoint_ok"] = disjoint_ok
            self.sketch_finish(offset_sk)

            mark("p18: import STEP + export 3MF")
            tree = self.open_part(os.path.join(
                tempfile.gettempdir(), "freesolid-selftest.step"))
            report["p18_step_import_ok"] = (
                tree.get("imported_solids", 0) >= 1
                and len(self.tessellate()["groups"]) > 0)
            threemf = os.path.join(tempfile.gettempdir(),
                                   "freesolid-selftest.3mf")
            report["p18_3mf_ok"] = self.export_part(threemf)["size"] > 0

            mark("p3: arc, rainure, polygone")
            import math
            self.new_part("Pièce esquisse avancée")

            state = self.sketch_start()
            zero_sk = state["sketch"]
            n_before = len(state["entities"])
            refused = False
            try:
                self.sketch_add_line(zero_sk, 17.8, -15.1, 17.8, -15.1)
            except KernelError as exc:
                refused = "longueur nulle" in str(exc)
            n_after = len(self.sketch_state(zero_sk)["entities"])
            report["p3_zero_line_refused"] = refused and n_after == n_before

            self.sketch_add_line(zero_sk, 0, 0, 40, 0)
            open_tree = self.sketch_finish(zero_sk)
            state = self.sketch_start()
            rect_sk = state["sketch"]
            self.sketch_add_line(rect_sk, 0, 0, 80, 0)
            self.sketch_add_line(rect_sk, 80, 0, 80, 40)
            self.sketch_add_line(rect_sk, 80, 40, 0, 40)
            self.sketch_add_line(rect_sk, 0, 40, 0, 0)
            closed_tree = self.sketch_finish(rect_sk)
            report["p3_open_profile_flag"] = (
                open_tree.get("open_profile") is True
                and closed_tree.get("open_profile") is False)

            state = self.sketch_start()
            adv = state["sketch"]
            state = self.sketch_add_arc(adv, 0, 0, 20, 0, math.pi / 2)
            report["p3_arc_ok"] = state["entities"][-1]["type"] == "arc"
            before = len(state["entities"])
            state = self.sketch_add_slot(adv, 0, -30, 40, -30, 10)
            report["p3_slot_ok"] = len(state["entities"]) == before + 4
            before = len(state["entities"])
            state = self.sketch_add_polygon(adv, 80, 0, 90, 0, 6)
            report["p3_polygon_ok"] = len(state["entities"]) >= before + 6
            self.sketch_finish(adv)
            edited = self.sketch_edit(adv)
            self.sketch_state(adv)
            report["p3_sketch_edit_ok"] = (
                any(e["type"] == "arc" for e in edited["entities"])
                and len(edited["entities"]) >= 1 + 4 + 6)
            n_geo = len(edited["entities"])
            state = self.sketch_add_line(adv, 200, 200, 210, 200)
            added = state["entities"][-1]["id"]
            state = self.sketch_delete_geo(adv, added)
            report["p3_delete_geo_ok"] = len(state["entities"]) == n_geo

            mark("p3: congé d'esquisse")
            state = self.sketch_start()
            fil = state["sketch"]
            self.sketch_add_line(fil, 0, 0, 40, 0)
            self.sketch_add_line(fil, 40, 0, 40, 30)
            state = self.sketch_fillet(fil, 0, 1, 30, 0, 40, 20, 5)
            report["p3_sketch_fillet_ok"] = any(
                e["type"] == "arc" for e in state["entities"])
            self.sketch_finish(fil)

            mark("p3: ajuster (trim)")
            state = self.sketch_start()
            trm = state["sketch"]
            self.sketch_add_line(trm, 0, 0, 40, 0)      # géo 0
            self.sketch_add_line(trm, 20, -10, 20, 10)  # géo 1, croise en (20,0)
            state = self.sketch_trim(trm, 1, 20, 8)     # coupe la branche haute
            top_ys = [max(e["p1"][1], e["p2"][1])
                      for e in state["entities"] if e["type"] == "line"]
            report["p3_trim_ok"] = all(y < 5 for y in top_ys)
            self.sketch_finish(trm)

            mark("p3: contraintes manuelles + cote à 2 entités")
            state = self.sketch_start()
            con = state["sketch"]
            self.sketch_add_line(con, 0, 0, 30, 2)
            self.sketch_add_line(con, 0, 10, 30, 14)
            self.sketch_constrain(con, "horizontal", 0)
            state = self.sketch_constrain(con, "parallel", 0, geo2=1)
            line0 = next(e for e in state["entities"] if e["id"] == 0)
            report["p3_constrain_ok"] = (
                abs(line0["p1"][1] - line0["p2"][1]) < 1e-6)
            state = self.sketch_dim(con, 0, geo2=1)  # parallèles → distance
            report["p3_dim_distance_ok"] = any(
                d["type"] == "Distance" for d in state["dims"])
            self.sketch_add_line(con, 50, 0, 80, 0)   # géo 2
            self.sketch_add_line(con, 50, 0, 80, 20)  # géo 3, snap en (50,0)
            state = self.sketch_dim(con, 2, geo2=3)   # sécantes → angle
            report["p3_dim_angle_ok"] = any(
                d["type"] == "Angle" for d in state["dims"])
            # M3 : l'état expose les contraintes brutes (geos/pos/value/
            # driving) — c'est ce que le solveur local planegcs consomme.
            report["p3_constraints_export_ok"] = (
                any(c["type"] == "Parallel" and c["geos"][:2] == [0, 1]
                    for c in state["constraints"])
                and all(set(c) >= {"id", "type", "geos", "pos", "value",
                                   "driving"}
                        for c in state["constraints"]))
            self.sketch_finish(con)

            mark("cycle de vie: open_part sans Body + UndoLimit")
            App = self._app()
            empty = App.newDocument("EmptyLifecycle")
            empty_path = os.path.join(
                tempfile.gettempdir(),
                "freesolid-lifecycle-empty.FCStd")
            empty.saveAs(empty_path)
            App.closeDocument(empty.Name)
            docs_before = len(App.listDocuments())
            orphan_raised = False
            try:
                self.open_part(empty_path)
            except KernelError:
                orphan_raised = True
            report["lifecycle_orphan_ok"] = (
                orphan_raised
                and len(App.listDocuments()) <= docs_before
                and self._doc is None)
            self.new_part("Pièce lifecycle")
            limit = self._undo_limit(self._doc)
            if limit is not None:
                report["lifecycle_undo_limit_ok"] = limit == 80
            else:
                # FreeCAD 1.0.x : pas d'API ; la pile C++ plafonne déjà
                # (défaut 20). On prouve la borne comportementale ≤ 80.
                body = self._body
                for i in range(100):
                    self._doc.openTransaction("lim{}".format(i))
                    body.Label = "Lim{}".format(i)
                    self._doc.commitTransaction()
                report["lifecycle_undo_limit_ok"] = (
                    self._doc.UndoMode == 1
                    and 0 < self._doc.UndoCount <= 80)

            def _refused(action, needle):
                try:
                    action()
                    return False
                except KernelError as exc:
                    return needle in str(exc)

            def _close(actual, expected, tol=1e-6):
                scale = abs(float(expected)) or 1.0
                return abs(float(actual) - float(expected)) <= tol * scale

            def _volume():
                return float(self._require_body().Shape.Volume)

            def _dispatch(op, **params):
                out = dispatch(self, op, params)
                if not out["ok"]:
                    raise KernelError(out["error"])
                return out["result"]

            mark("p31: gardes — les refus parlent français")
            self.new_part("Pièce gardes P031")
            body_name = self._require_body().Name
            report["p31_refus_sans_esquisse"] = _refused(
                lambda: self.add_pad(10), "aucune esquisse disponible")
            report["p31_refus_dernier_corps"] = _refused(
                lambda: self.delete_feature(body_name),
                "impossible de supprimer le dernier")
            report["p31_refus_tip_hors_historique"] = _refused(
                lambda: self.set_tip(body_name), "ligne d'historique")
            report["p31_refus_delete_inconnue"] = _refused(
                lambda: self.delete_feature("PasUneFonction"),
                "fonction inconnue")
            report["p31_refus_param_inconnue"] = _refused(
                lambda: self.set_param("PasUneFonction", "Length", 1),
                "fonction inconnue")
            report["p31_refus_rename_inconnue"] = _refused(
                lambda: self.rename("PasUneFonction", "x"),
                "fonction inconnue")
            report["p31_refus_esquisse_inconnue"] = _refused(
                lambda: self.sketch_state("PasUneEsquisse"),
                "esquisse inconnue")
            missing = os.path.join(tempfile.gettempdir(),
                                   "freesolid-absent-p31.FCStd")
            if os.path.isfile(missing):
                os.remove(missing)
            report["p31_refus_open_inexistant"] = _refused(
                lambda: self.open_part(missing), "fichier introuvable")
            report["p31_refus_combiner"] = _refused(
                lambda: self.add_boolean(tool="PasUnCorps"),
                "corps outil inconnu")
            report["p31_refus_nom_vide"] = _refused(
                lambda: self.rename(body_name, "   "),
                "le nom ne peut pas être vide")
            report["p31_refus_cote_nulle"] = _refused(
                lambda: self.add_rect_sketch(0, 10),
                "largeur et hauteur doivent être positives")
            report["p31_refus_plan_esquisse"] = _refused(
                lambda: self.sketch_start(plane="AB"),
                "plan inconnu")

            mark("p31: vérités géométriques")
            self.new_part("Pièce volumes P031")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            report["p31_volume_pad"] = _close(_volume(), 12000.0)
            report["p31_faces_pad"] = len(self.tessellate()["groups"]) == 6
            self.add_rect_sketch(10, 10, face=self._top_face_id())
            self.add_pocket(through=True)
            report["p31_volume_pocket"] = _close(_volume(), 11000.0)
            producers = self._face_producers()
            report["p038_face_producers_historique"] = (
                "Pad" in producers.values() and "Pocket" in producers.values()
            )

            self.new_part("Pièce miroir P031")
            state = self.sketch_start()
            mir_sk = state["sketch"]
            # 20×20 à cheval sur YZ (x=-5..15) : un Body n'a qu'un solide,
            # les copies disjointes sont jetées — le chevauchement fusionne.
            for line in ((-5, -10, 15, -10), (15, -10, 15, 10),
                         (15, 10, -5, 10), (-5, 10, -5, -10)):
                self.sketch_add_line(mir_sk, *line)
            self.sketch_finish(mir_sk)
            self.add_pad(10, sketch=mir_sk)
            vol_before_mirror = _volume()
            self.add_mirror(plane="YZ")
            report["p31_volume_miroir"] = _close(
                _volume(), vol_before_mirror * 1.5)

            self.new_part("Pièce répétition P031")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            vol_before_pattern = _volume()
            self.add_linear_pattern(length=10, count=2, axis="X")
            report["p31_volume_repetition"] = _close(
                _volume(), vol_before_pattern * 1.5)

            self.new_part("Pièce combiner P031")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            first_body = self._require_body().Name
            vol_host = _volume()
            self.add_body("Corps outil")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            tool_body = self._require_body().Name
            vol_tool = _volume()
            self.set_active_body(first_body)
            self.add_boolean(tool=tool_body, type="cut")
            report["p31_volume_combiner"] = _close(
                _volume(), vol_host - vol_tool)

            mark("p31: aller-retour complet")
            self.new_part("Pièce roundtrip P031")
            self.set_variable("hauteur", 10.0)
            self.add_rect_sketch(40, 30)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.set_params(pad_name, {"Length": "Variables.hauteur"})
            tree = self.rename(pad_name, "Bossage principal")
            body_name = self._require_body().Name
            tree = self.set_body_color(body_name, "#336699")
            state = self.sketch_start()
            free_sk = state["sketch"]
            self.sketch_add_line(free_sk, 0, 0, 25, 0)
            self.sketch_finish(free_sk)
            state = self.sketch_start()
            surf_sk = state["sketch"]
            self.sketch_add_line(surf_sk, 0, 0, 18, 0)
            self.sketch_finish(surf_sk)
            tree = self.surface_extrude(12, sketch=surf_sk)
            surf_name = tree["surfaces"][-1]["name"]
            tree = self.set_tip(pad_name)
            vol_before_save = _volume()
            round_path = os.path.join(tempfile.gettempdir(),
                                      "freesolid-selftest-p31.FCStd")
            self.save_part(round_path)
            reopened = self.open_part(round_path)
            report["p31_reopen_variables"] = any(
                v["name"] == "hauteur" and abs(v["value"] - 10.0) < 1e-9
                for v in reopened.get("variables", []))
            report["p31_reopen_label"] = any(
                f["name"] == pad_name and f["label"] == "Bossage principal"
                for f in reopened["features"])
            report["p31_reopen_couleur"] = any(
                b["name"] == body_name and b.get("color") == "#336699"
                for b in reopened["bodies"])
            free_entry = next(f for f in reopened["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in reopened["surfaces"]
                              if s["name"] == surf_name)
            report["p31_reopen_rolled_back"] = (
                free_entry.get("rolled_back") is True
                and surf_entry.get("rolled_back") is True)
            report["p31_reopen_tip"] = reopened.get("tip") == pad_name
            report["p31_reopen_volume"] = _close(_volume(), vol_before_save)

            mark("p31: aller-retour STEP")
            self.new_part("Pièce STEP P031")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            vol_step = _volume()
            step_path = os.path.join(tempfile.gettempdir(),
                                     "freesolid-selftest-p31.step")
            self.export_part(step_path)
            self.open_part(step_path)
            report["p31_step_roundtrip"] = _close(
                _volume(), vol_step, tol=0.001)

            mark("p31: annuler en chaîne")
            self.new_part("Pièce undo P031")
            _dispatch("add_rect_sketch", width=30, height=20)
            _dispatch("add_pad", length=10)
            tree = _dispatch("add_fillet", radius=2, face=self._top_face_id())
            vol_chain = _volume()
            sig_chain = [(f["type"], f["name"], f["label"])
                         for f in tree["features"]]
            self.undo()
            self.undo()
            self.undo()
            self.redo()
            self.redo()
            tree = self.redo()
            report["p31_undo_chain"] = (
                _close(_volume(), vol_chain)
                and [(f["type"], f["name"], f["label"])
                     for f in tree["features"]] == sig_chain)

            mark("p31: pièce vitrine")
            # Chaque fonction est testée sur une pièce jetable : sans cette
            # étape, l'Autotest finissait sur la pièce la plus banale
            # (plaque m1.5). Une seule pièce enchaîne ici des fonctions
            # visibles ; le bilan la rouvre pour le viewport. Le chanfrein
            # est écarté exprès : sur coque/dépouille, ChFi3d a déjà
            # segfaulté (voir p4).
            self.new_part("Pièce vitrine")
            self.add_rect_sketch(80, 80)
            self.add_pad(14)
            self.add_draft(face=self._side_face_id(), angle=5)
            self.add_fillet(3, face=self._top_face_id())
            self.add_rect_sketch(40, 40, face=self._top_face_id())
            self.add_pocket(6)
            state = self.sketch_start(face=self._top_face_id())
            vitrine_sk = state["sketch"]
            self.sketch_add_circle(vitrine_sk, 28, 28, 3)
            self.sketch_finish(vitrine_sk)
            self.add_hole(diameter=6, through=True, cut="lamage",
                          cut_diameter=11, cut_depth=3)
            self.add_polar_pattern(count=4, angle=360.0, axis="Z")
            tree = self.add_text("FS", face=self._top_face_id(),
                                 size=8, depth=1, x=0, y=-30)
            vitrine_path = os.path.join(tempfile.gettempdir(),
                                        "freesolid-selftest-vitrine.FCStd")
            self.save_part(vitrine_path)
            report["p31_vitrine_ok"] = (
                not any(f["error"] for f in tree["features"])
                and tree["bodies"][0].get("has_solid") is True
                and _volume() > 0
                and len(self.tessellate()["groups"]) >= 20)

            mark("p32: refus atomique, virgule, gravure rééditable")
            vitrine_pp = next(f["name"] for f in tree["features"]
                              if f["type"] == "PartDesign::PolarPattern")
            vitrine_pad = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pad")
            # Une expression inconnue est refusée SANS corrompre la pièce
            # (avant P032 : liaison stockée, pièce Invalid, barre bloquée).
            try:
                self.set_params(vitrine_pp, {"Occurrences": "inconnu_p32"})
                report["p32_expr_refus_atomique"] = False
            except KernelError:
                obj = self._require_doc().getObject(vitrine_pp)
                intact = not dict(obj.ExpressionEngine or [])
                self.set_tip(vitrine_pad)     # la barre bouge encore
                tree = self.tip_to_end()
                report["p32_expr_refus_atomique"] = (
                    intact and not any(f["error"]
                                       for f in tree["features"]))
            # « 15,5 » est un nombre (virgule française), pas une équation.
            self.set_params(vitrine_pad, {"Length": "15,5"})
            obj = self._require_doc().getObject(vitrine_pad)
            report["p32_virgule_nombre"] = (
                not dict(obj.ExpressionEngine or [])
                and abs(float(obj.Length) - 15.5) < 1e-9)
            self.set_params(vitrine_pad, {"Length": 14})
            # La gravure se réédite : autre texte -> autre géométrie.
            gravure = next(f["name"] for f in self.get_tree()["features"]
                           if f["type"] == "PartDesign::Boolean")
            tris_before = len(self.tessellate()["indices"])
            vol_before_edit = _volume()
            tree = self.edit_text(gravure, text="OK")
            vitrine_shape = self._require_body().Shape
            report["p32_gravure_editable"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["indices"]) != tris_before
                and any(f.get("text", {}).get("text") == "OK"
                        for f in tree["features"])
                # volume sain : la pièce entière, pas le texte seul
                and vitrine_shape.isValid()
                and abs(_volume() - vol_before_edit) < 100.0)
            tree = self.edit_text(gravure, text="FS")
            # Les artefacts internes de la gravure restent hors de l'arbre.
            report["p32_forme_texte_cachee"] = (
                not any(s["label"] == "Forme du texte"
                        for s in tree["surfaces"])
                and not any(b["label"] == "Corps texte"
                            for b in tree["bodies"]))
            # L'état vitrine (14, « FS ») est restauré : re-sauver pour
            # que le bilan rouvre exactement la pièce attendue.
            self.save_part(vitrine_path)

            # Filet permanent : sur la pièce vitrine, qui exerce le plus
            # de fonctions (gravure comprise, dont les artefacts sont
            # masqués), aucune arête ne doit désigner un nœud absent du
            # payload. Toute fonction future qui l'oublierait tombe ici.
            report["n1b_aucune_arete_pendante"] = not dangling_deps(
                self.get_tree())

            mark("n1: arêtes de dépendance dans get_tree")
            self.new_part("Pièce nœuds N001")
            tree = self.add_rect_sketch(80, 50)
            sketch_name = next(
                f["name"] for f in tree["features"]
                if f["type"] == "Sketcher::SketchObject")
            tree = self.add_pad(12)
            pad = next(f for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            report["n1_deps_pad_sketch"] = (
                sketch_name in pad.get("deps", []))
            self.set_params(pad["name"], {"Length": "12 + 3"})
            pad = next(f for f in self.get_tree()["features"]
                       if f["type"] == "PartDesign::Pad")
            report["n1_driven_ok"] = "Length" in pad.get("driven", {})
            # Un plan de référence n'est désignable que par son ``name`` :
            # ``id`` reste « XZ » là où le nom prend un suffixe en
            # multi-corps. Sans ce champ, l'arête était pendante.
            tree = self.add_datum_plane(base="XZ")
            xz_name = next(pl["name"] for pl in tree["planes"]
                           if pl["id"] == "XZ")
            datum = next(f for f in tree["features"]
                         if f["type"] == "PartDesign::Plane")
            report["n1b_deps_plan_origine"] = (
                bool(xz_name) and xz_name in datum.get("deps", []))
            report["n1b_arbre_coherent"] = not dangling_deps(tree)

            mark("n4: fonction graphe — perçage, réédition, refus atomique")
            import math

            def _n4_node(ident, kind, **fields):
                node = {"id": ident, "type": kind}
                node.update(fields)
                return node

            def _n4_grid(cols, rows):
                # Grille écrite à la main : série en X diffusée sur une
                # série en Y (appariement récursif), cylindres en cut.
                return {
                    "nodes": [
                        _n4_node("ny", "nombre", value=rows),
                        _n4_node("one", "nombre", value=1),
                        _n4_node("zero", "nombre", value=0),
                        _n4_node("x0", "nombre", value=-20),
                        _n4_node("dx", "nombre", value=20),
                        _n4_node("nx", "nombre", value=cols),
                        _n4_node("y0", "nombre", value=-10),
                        _n4_node("dy", "nombre", value=20),
                        _n4_node("z", "nombre", value=-6),
                        _n4_node("ones", "serie"),
                        _n4_node("zeros", "multiplication"),
                        _n4_node("xstart", "addition"),
                        _n4_node("xs", "serie"),
                        _n4_node("ys", "serie"),
                        _n4_node("pts", "vecteur"),
                        _n4_node("cyl", "cylindre", rayon=3, hauteur=20),
                    ],
                    "edges": [
                        {"from": "one", "to": "ones", "input": "depart"},
                        {"from": "one", "to": "ones", "input": "pas"},
                        {"from": "ny", "to": "ones", "input": "nombre"},
                        {"from": "zero", "to": "zeros", "input": "a"},
                        {"from": "ones", "to": "zeros", "input": "b"},
                        {"from": "x0", "to": "xstart", "input": "a"},
                        {"from": "zeros", "to": "xstart", "input": "b"},
                        {"from": "xstart", "to": "xs", "input": "depart"},
                        {"from": "dx", "to": "xs", "input": "pas"},
                        {"from": "nx", "to": "xs", "input": "nombre"},
                        {"from": "y0", "to": "ys", "input": "depart"},
                        {"from": "dy", "to": "ys", "input": "pas"},
                        {"from": "ny", "to": "ys", "input": "nombre"},
                        {"from": "xs", "to": "pts", "input": "x"},
                        {"from": "ys", "to": "pts", "input": "y"},
                        {"from": "z", "to": "pts", "input": "z"},
                        {"from": "pts", "to": "cyl", "input": "ancrage"},
                    ],
                    "output": "cyl",
                }

            self.new_part("Pièce graphe N004")
            self.add_rect_sketch(80, 50)
            self.add_pad(8)
            vol_plaque = _volume()
            hole_vol = math.pi * 3.0 * 3.0 * 8.0
            tree = self.add_graph_feature(_n4_grid(3, 2), mode="cut")
            graphe = next(f for f in tree["features"] if f.get("graph"))
            vol_perce = _volume()
            shape = self._require_body().Shape
            report["n4_graphe_perce"] = (
                not any(f["error"] for f in tree["features"])
                and shape.isValid()
                and abs((vol_plaque - vol_perce) - 6 * hole_vol) < 25.0)
            stored = self.get_graph_feature(graphe["name"])
            report["n4_graphe_persiste"] = (
                stored.get("mode") == "cut"
                and stored.get("graph", {}).get("output") == "cyl")

            tree = self.edit_graph_feature(graphe["name"], _n4_grid(2, 2))
            vol_reedite = _volume()
            report["n4_graphe_reedite"] = (
                not any(f["error"] for f in tree["features"])
                and self._require_body().Shape.isValid()
                and abs((vol_plaque - vol_reedite) - 4 * hole_vol) < 25.0
                and abs(vol_reedite - vol_perce) > 50.0)

            invalid = _n4_grid(2, 2)
            invalid["output"] = "fantome"
            try:
                self.edit_graph_feature(graphe["name"], invalid)
                report["n4_graphe_refus_atomique"] = False
            except KernelError:
                report["n4_graphe_refus_atomique"] = (
                    abs(_volume() - vol_reedite) < 1e-6
                    and not any(f["error"]
                                for f in self.get_tree()["features"]))

            tree = self.get_tree()
            report["n4_arbre_propre"] = (
                not any(s["label"] == "Forme du graphe"
                        for s in tree["surfaces"])
                and not any(b["label"] == "Corps graphe"
                            for b in tree["bodies"])
                and not dangling_deps(tree)
                and any(f.get("graph") for f in tree["features"]))

            mark("n8: nœud Python — refus sans confiance, valeur une fois autorisé")
            self.new_part("Pièce graphe N008")
            self.add_rect_sketch(80, 50)
            self.add_pad(8)
            vol_n8 = _volume()

            def _n8_script_graph():
                return {
                    "nodes": [
                        _n4_node("py", "script",
                                 code="return [0.0, 20.0, 40.0]"),
                        _n4_node("y", "nombre", value=0),
                        _n4_node("z", "nombre", value=-6),
                        _n4_node("pts", "vecteur"),
                        _n4_node("cyl", "cylindre", rayon=3, hauteur=20),
                    ],
                    "edges": [
                        {"from": "py", "to": "pts", "input": "x"},
                        {"from": "y", "to": "pts", "input": "y"},
                        {"from": "z", "to": "pts", "input": "z"},
                        {"from": "pts", "to": "cyl", "input": "ancrage"},
                    ],
                    "output": "cyl",
                }

            try:
                self.add_graph_feature(_n8_script_graph(), mode="cut")
                report["n8_script_refuse_sans_confiance"] = False
            except KernelError as exc:
                message = str(exc)
                report["n8_script_refuse_sans_confiance"] = (
                    "py" in message
                    and ("autoris" in message or "Python" in message))
            report["n8_script_piece_intacte"] = (
                abs(_volume() - vol_n8) < 1e-3)
            stored_before = [
                f.get("graph") for f in self.get_tree()["features"]
                if f.get("graph")]
            report["n8_script_pas_dans_fcstd"] = not stored_before
            self.authorize_scripts()
            tree = self.add_graph_feature(_n8_script_graph(), mode="cut")
            vol_n8_cut = _volume()
            graphe_n8 = next(
                (f for f in tree["features"] if f.get("graph")), None)
            persisted = (graphe_n8 or {}).get("graph") or {}
            persisted_text = json.dumps(persisted)
            report["n8_script_valeur"] = (
                vol_n8_cut < vol_n8 - 1
                and not any(f["error"] for f in tree["features"])
                and "authorized" not in persisted_text
                and "trusted" not in persisted_text)
            self.new_part("Pièce graphe N008 reset")
            try:
                self.add_graph_feature(_n8_script_graph(), mode="cut")
                report["n8_script_reset_document"] = False
            except KernelError:
                report["n8_script_reset_document"] = True

            mark("n7: sous-éléments et esquisse attachée")
            self.new_part("Pièce nœuds N007")
            tree = self.add_rect_sketch(80, 50)
            xy_name = next(pl["name"] for pl in tree["planes"]
                           if pl["id"] == "XY")
            tree = self.add_pad(12)
            sketch = next(
                child for feat in tree["features"]
                for child in feat.get("children", ())
                if child["type"] == "Sketcher::SketchObject")
            coherent = not dangling_deps(tree)
            report["n7_esquisse_attachee"] = (
                bool(xy_name) and xy_name in sketch.get("deps", [])
                and coherent)
            top_edges = [i for i, edge in
                         enumerate(self._require_body().Shape.Edges)
                         if abs(edge.CenterOfMass.z - 12) < 1e-6]
            fillet_edges = top_edges[:2] if len(top_edges) >= 2 else top_edges
            tree = self.add_fillet(radius=2, edges=fillet_edges)
            fillet = next(f for f in tree["features"]
                          if f["type"] == "PartDesign::Fillet")
            fillet_subs = [
                name for names in (fillet.get("dep_subs") or {}).values()
                for name in names]
            # Dépouille sur une boîte neuve : après congé, la face
            # latérale n'est plus dépouillable (constat n7).
            self.new_part("Pièce nœuds N007 dépouille")
            self.add_rect_sketch(80, 50)
            self.add_pad(12)
            tree = self.add_draft(face=self._side_face_id(), angle=5)
            draft = next(f for f in tree["features"]
                         if f["type"] == "PartDesign::Draft")
            draft_subs = [
                name for names in (draft.get("dep_subs") or {}).values()
                for name in names]
            report["n7_sous_elements"] = (
                any(str(name).startswith("Edge") for name in fillet_subs)
                and any(str(name).startswith("Face") for name in draft_subs)
                and not dangling_deps(tree))

            mark("n9: répétition d'un groupe de fonctions")
            self.new_part("Pièce répétition groupe N009")
            self.add_rect_sketch(40, 40)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.add_rect_sketch(10, 10, face=self._top_face_id())
            tree = self.add_pocket(through=True)
            pocket_name = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pocket")
            tree = self.add_linear_pattern(
                length=30, count=2, axis="X",
                features=[pad_name, pocket_name])
            # 40×40×10 × 2, recouvrement 10 mm, deux perçages 10×10.
            report["n9_repetition_groupe"] = (
                not any(f["error"] for f in tree["features"])
                and _close(_volume(), 26000.0, tol=1e-4))

            mark("n9: spike rejeu variable")
            from engine.replay import run_spike_report
            spike = run_spike_report(self)
            report["n9_spike_variable"] = bool(spike["minimal"]["ok"])
            report["n9_spike_rapport"] = {
                "fused_volume": spike["minimal"]["fused_volume"],
                "expected_fused": spike["minimal"]["expected_fused"],
                "cut_volume": spike["minimal"]["cut_volume"],
                "expected_cut": spike["minimal"]["expected_cut"],
                "failed_instance_cleaned": spike["minimal"][
                    "failed_instance_cleaned"],
                "tool_absorbed": spike["minimal"].get("tool_absorbed"),
                "habillage": spike["dressup"],
                "indice_perime": spike["stale_index"],
                "cout_s": {k: v for k, v in spike["cost"].items()
                           if k != "cleanup_ok"},
                "cout_proprete": spike["cost"].get("cleanup_ok"),
                "reconstitution": {
                    "replayable": sorted(spike["reconstitution"][
                        "replayable"]),
                    "unreplayable": sorted(spike["reconstitution"][
                        "unreplayable"]),
                },
            }

            mark("n10: répétition variable")
            from engine.replay import _temp_bodies_left
            self.new_part("Pièce répétition variable N010")
            self.add_rect_sketch(20, 20)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.add_rect_sketch(8, 8, face=self._top_face_id())
            tree = self.add_pocket(through=True)
            pocket_name = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pocket")
            n_before = len(tree["features"])
            # Source : 20×20×10 − 8×8×10 = 3360.
            # Trois instances qui se touchent (pas de 20 mm = largeur),
            # L = 10, 20, 30 : 336 × 60 = 20160. Total fuse = 23520.
            # Un Body n'accepte qu'un solide : des copies disjointes
            # (pas de 40 mm) feraient échouer le booléen.
            tree = self.add_repeat_feature(
                [pad_name, pocket_name],
                [
                    {"offset": [20, 0, 0],
                     "params": {pad_name: {"Length": 10}}},
                    {"offset": [40, 0, 0],
                     "params": {pad_name: {"Length": 20}}},
                    {"offset": [60, 0, 0],
                     "params": {pad_name: {"Length": 30}}},
                ],
                mode="fuse",
            )
            repeat_line = next(f for f in tree["features"] if f.get("repeat"))
            report["n10_repetition_variable"] = (
                not any(f["error"] for f in tree["features"])
                and len(tree["features"]) == n_before + 1
                and _close(_volume(), 23520.0, tol=1e-4)
                and pad_name in (repeat_line.get("deps") or [])
                and pocket_name in (repeat_line.get("deps") or [])
                and not dangling_deps(tree))

            mark("n10: réédition")
            # 3360 (source) + 336 × (15+25+35) = 3360 + 25200 = 28560.
            tree = self.edit_repeat_feature(
                repeat_line["name"],
                [
                    {"offset": [20, 0, 0],
                     "params": {pad_name: {"Length": 15}}},
                    {"offset": [40, 0, 0],
                     "params": {pad_name: {"Length": 25}}},
                    {"offset": [60, 0, 0],
                     "params": {pad_name: {"Length": 35}}},
                ],
            )
            stored = self.get_repeat_feature(repeat_line["name"])
            n_repeat = sum(1 for f in tree["features"] if f.get("repeat"))
            report["n10_reedition"] = (
                not any(f["error"] for f in tree["features"])
                and n_repeat == 1
                and _close(_volume(), 28560.0, tol=1e-4)
                and stored.get("mode") == "fuse"
                and stored.get("features") == [pad_name, pocket_name]
                and len(stored.get("instances") or []) == 3)

            mark("n10: propreté")
            leftover = _temp_bodies_left(self)
            tree = self.get_tree()
            report["n10_proprete"] = (
                leftover == []
                and not any(s["label"] == "Forme de la répétition"
                            for s in tree["surfaces"])
                and not any(b["label"] == "Corps répétition"
                            for b in tree["bodies"])
                and not dangling_deps(tree))

            mark("n10: garde topologique — tout ou rien")
            self.new_part("Pièce garde N010")
            self.add_rect_sketch(20, 20)
            tree = self.add_pad(20)
            pad_g = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Pad")
            self.add_rect_sketch(8, 8, face=self._top_face_id())
            tree = self.add_pocket(length=5)
            pocket_g = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pocket")
            tree = self.add_fillet(radius=1, edges=[2])
            fillet_g = next(f for f in tree["features"]
                            if f["type"] == "PartDesign::Fillet")
            vol_garde = _volume()
            n_garde = len(self.get_tree()["features"])
            try:
                self.add_repeat_feature(
                    [pad_g, pocket_g, fillet_g["name"]],
                    [
                        {"offset": [40, 0, 0],
                         "params": {pocket_g: {"Length": 5}}},
                        {"offset": [80, 0, 0],
                         "params": {pocket_g: {"Length": 25}}},
                    ],
                    mode="fuse",
                )
                report["n10_garde_refuse"] = False
            except KernelError as exc:
                garde_msg = str(exc)
                report["n10_garde_refuse"] = (
                    "n° 2 sur 2" in garde_msg
                    and fillet_g["label"] in garde_msg
                    and _close(_volume(), vol_garde)
                    and len(self.get_tree()["features"]) == n_garde
                    and _temp_bodies_left(self) == [])

            mark("n10b: le graphe pilote")
            # Source : 20×20×10 − 8×8×10 = 3360.
            # serie(20, 20, 3) → décalage X = 20, 40, 60
            # serie(10, 10, 3) → Length = 10, 20, 30
            # 336 × (10+20+30) = 20160 ; total fuse = 3360 + 20160 = 23520.
            self.new_part("Pièce graphe N010b")
            self.add_rect_sketch(20, 20)
            tree = self.add_pad(10)
            pad_b = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Pad")
            self.add_rect_sketch(8, 8, face=self._top_face_id())
            tree = self.add_pocket(through=True)
            pocket_b = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pocket")
            n_before_b = len(tree["features"])
            graph_b = {
                "nodes": [
                    {"id": "sx", "type": "serie",
                     "depart": 20, "pas": 20, "nombre": 3},
                    {"id": "vx", "type": "vecteur", "y": 0, "z": 0},
                    {"id": "sl", "type": "serie",
                     "depart": 10, "pas": 10, "nombre": 3},
                    {"id": "c", "type": "cote",
                     "feature": pad_b, "prop": "Length"},
                    {"id": "i", "type": "instance"},
                ],
                "edges": [
                    {"from": "sx", "to": "vx", "input": "x"},
                    {"from": "vx", "to": "i", "input": "decalage"},
                    {"from": "sl", "to": "c", "input": "valeur"},
                    {"from": "c", "to": "i", "input": "cotes"},
                ],
                "output": "i",
            }
            tree = self.add_repeat_feature(
                [pad_b, pocket_b], graph=graph_b, mode="fuse")
            repeat_b = next(f for f in tree["features"] if f.get("repeat"))
            report["n10b_graphe_pilote"] = (
                not any(f["error"] for f in tree["features"])
                and len(tree["features"]) == n_before_b + 1
                and _close(_volume(), 23520.0, tol=1e-4)
                and pad_b in (repeat_b.get("deps") or [])
                and pocket_b in (repeat_b.get("deps") or [])
                and not dangling_deps(tree))

            mark("n10b: un seul point de vérité")
            stored_b = self.get_repeat_feature(repeat_b["name"])
            report["n10b_un_seul_point"] = (
                isinstance(stored_b.get("graph"), dict)
                and "instances" not in stored_b
                and stored_b.get("features") == [pad_b, pocket_b])

            mark("n10b: chaîne de cotes")
            chain = {
                "nodes": [
                    {"id": "v", "type": "serie",
                     "depart": 10, "pas": 5, "nombre": 2},
                    {"id": "d", "type": "vecteur", "x": 0, "y": 0, "z": 0},
                    {"id": "c1", "type": "cote",
                     "feature": "Pad", "prop": "Length"},
                    {"id": "c2", "type": "cote",
                     "feature": "Pocket", "prop": "Diameter"},
                    {"id": "i", "type": "instance"},
                ],
                "edges": [
                    {"from": "v", "to": "c1", "input": "valeur"},
                    {"from": "c1", "to": "c2", "input": "suite"},
                    {"from": "v", "to": "c2", "input": "valeur"},
                    {"from": "d", "to": "i", "input": "decalage"},
                    {"from": "c2", "to": "i", "input": "cotes"},
                ],
                "output": "i",
            }
            chained = evaluate_instances(chain, {})
            dup = {
                "nodes": [
                    {"id": "v", "type": "nombre", "value": 10},
                    {"id": "c1", "type": "cote",
                     "feature": "Pad", "prop": "Length"},
                    {"id": "c2", "type": "cote",
                     "feature": "Pad", "prop": "Length"},
                    {"id": "i", "type": "instance",
                     "decalage": {"x": 0, "y": 0, "z": 0}},
                ],
                "edges": [
                    {"from": "v", "to": "c1", "input": "valeur"},
                    {"from": "v", "to": "c2", "input": "valeur"},
                    {"from": "c1", "to": "c2", "input": "suite"},
                    {"from": "c2", "to": "i", "input": "cotes"},
                ],
                "output": "i",
            }
            dup_named = False
            try:
                evaluate_instances(dup, {})
            except GraphError as exc:
                dup_named = "Pad.Length" in str(exc)
            report["n10b_chaine_cotes"] = (
                len(chained) == 2
                and all("Length" in (item["params"].get("Pad") or {})
                        for item in chained)
                and all("Diameter" in (item["params"].get("Pocket") or {})
                        for item in chained)
                and dup_named)

            mark("n10b: garde d'attache")
            self.new_part("Pièce attache N010b")
            self.add_rect_sketch(20, 20)
            tree = self.add_pad(10)
            pad_a = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Pad")
            self.add_rect_sketch(8, 8, face=self._top_face_id())
            tree = self.add_pocket(length=5)
            pocket_a = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pocket")
            tree = self.add_rect_sketch(6, 6, face=self._top_face_id())
            attach_sk = next(
                f for f in reversed(tree["features"])
                if f["type"] == "Sketcher::SketchObject")
            tree = self.add_pad(2)
            pads_a = [f["name"] for f in tree["features"]
                      if f["type"] == "PartDesign::Pad"]
            small_a = pads_a[-1]
            vol_attache = _volume()
            n_attache = len(self.get_tree()["features"])
            try:
                self.add_repeat_feature(
                    [pad_a, pocket_a, small_a],
                    [
                        {"offset": [40, 0, 0],
                         "params": {pocket_a: {"Length": 5}}},
                        {"offset": [80, 0, 0],
                         "params": {pocket_a: {"Length": 20}}},
                    ],
                    mode="fuse",
                )
                report["n10b_attache_refuse"] = False
            except KernelError as exc:
                attache_msg = str(exc)
                report["n10b_attache_refuse"] = (
                    "n° 2" in attache_msg
                    and attach_sk["label"] in attache_msg
                    and _close(_volume(), vol_attache)
                    and len(self.get_tree()["features"]) == n_attache
                    and _temp_bodies_left(self) == [])

            mark("n11: hélice graphe + balayage — le chemin complet")
            # Hélice cylindrique : pas=10, hauteur=20, rayon=10 → 2 tours.
            # Longueur = 2 * sqrt((2π·10)² + 10²) = 2√(400π²+100) ≈ 127.245.
            # Profil Ø4 → aire π·2² ; volume ≈ 4π × 127.245 ≈ 1599.15.
            self.new_part("Pièce graphe N011")
            helix_graph = {
                "nodes": [
                    _n4_node("h", "helice", pas_helice=10, hauteur=20,
                             rayon=10, angle=0, gauche=0),
                ],
                "edges": [],
                "output": "h",
            }
            tree = self.add_graph_feature(helix_graph)
            helix_surf = next(
                (s for s in tree["surfaces"] if s.get("graph")), None)
            helix_ok = (
                helix_surf is not None
                and sum(1 for s in tree["surfaces"] if s.get("graph")) == 1)
            # Profil dans le plan XZ, centré au départ de l'hélice (10, 0, 0) :
            # la tangente initiale est ≈ +Y, normale du plan XZ.
            state = self.sketch_start(plane="XZ")
            pipe_sk = state["sketch"]
            self.sketch_add_circle(pipe_sk, 10, 0, 2)
            self.sketch_finish(pipe_sk)
            try:
                tree = self.add_sweep(
                    profile=pipe_sk, spine=helix_surf["name"])
                helix_len = 2.0 * math.sqrt((2.0 * math.pi * 10.0) ** 2 + 10.0 ** 2)
                expected_vol = (math.pi * 2.0 * 2.0) * helix_len
                vol = _volume()
                report["n11_helice_balayage"] = (
                    helix_ok
                    and not any(f["error"] for f in tree["features"])
                    and vol > 0
                    and self._require_body().Shape.isValid()
                    and _close(vol, expected_vol, tol=0.05))
            except KernelError:
                report["n11_helice_balayage"] = False

            mark("n11: neuf nœuds — chacun sa forme")
            origin = {"x": 0, "y": 0, "z": 0}
            zdir = {"x": 0, "y": 0, "z": 1}

            def _n11_last_shape():
                surf = self.get_tree()["surfaces"][-1]
                return self._require_doc().getObject(surf["name"]).Shape

            def _n11_add(graph):
                n_before = len(self.get_tree()["surfaces"])
                tree = self.add_graph_feature(graph)
                return (
                    len(tree["surfaces"]) == n_before + 1
                    and bool(tree["surfaces"][-1].get("graph")))

            n11_nodes = {}
            n11_nodes["ligne"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "ligne",
                        point1=origin, point2={"x": 10, "y": 0, "z": 0})],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Length, 10.0, tol=1e-6))
            n11_nodes["cercle"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "cercle", rayon=10, point=origin,
                        direction=zdir)],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Length, 2 * math.pi * 10,
                              tol=1e-4))
            # Arc 90° rayon 10 : longueur = 10·π/2.
            n11_nodes["arc"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "arc", rayon=10, point=origin, direction=zdir,
                        angle1=0, angle2=90)],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Length, 10 * math.pi / 2,
                              tol=1e-4))
            # Arc 3 pts : (10,0,0), (0,10,0), (-10,0,0) → demi-cercle r=10.
            n11_nodes["arc_3pts"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "arc_3pts",
                        point1={"x": 10, "y": 0, "z": 0},
                        point2={"x": 0, "y": 10, "z": 0},
                        point3={"x": -10, "y": 0, "z": 0})],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Length, math.pi * 10,
                              tol=1e-4))
            n11_nodes["polyligne"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "polyligne", ferme=0,
                        point=[origin, {"x": 10, "y": 0, "z": 0},
                               {"x": 10, "y": 10, "z": 0}])],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Length, 20.0, tol=1e-6))
            spline_shape_ok = False
            if _n11_add({
                "nodes": [_n4_node(
                    "n", "bspline", ferme=0,
                    centres=[origin, {"x": 10, "y": 0, "z": 0},
                             {"x": 10, "y": 10, "z": 0}])],
                "edges": [], "output": "n",
            }):
                shp = _n11_last_shape()
                verts = list(shp.Vertexes)
                spline_shape_ok = (
                    len(verts) >= 2
                    and _close(verts[0].Point.distanceToPoint(
                        self._app().Vector(0, 0, 0)), 0.0, tol=1e-4)
                    and _close(verts[-1].Point.distanceToPoint(
                        self._app().Vector(10, 10, 0)), 0.0, tol=1e-4))
            n11_nodes["bspline"] = spline_shape_ok
            n11_nodes["helice"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "helice", pas_helice=10, hauteur=20,
                        rayon=10, angle=0, gauche=0)],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().BoundBox.ZLength, 20.0,
                              tol=1e-3))
            n11_nodes["plan"] = (
                _n11_add({
                    "nodes": [_n4_node(
                        "n", "plan", longueur=20, largeur=10,
                        point=origin, direction=zdir)],
                    "edges": [], "output": "n",
                }) and _close(_n11_last_shape().Area, 200.0, tol=1e-4))
            grid = [
                [origin, {"x": 10, "y": 0, "z": 0}],
                [{"x": 0, "y": 10, "z": 0}, {"x": 10, "y": 10, "z": 0}],
            ]
            n11_nodes["bspline_surface"] = (
                _n11_add({
                    "nodes": [_n4_node("n", "bspline_surface", centres=grid)],
                    "edges": [], "output": "n",
                }) and bool(_n11_last_shape().Faces)
                and _close(_n11_last_shape().Area, 100.0, tol=0.05))
            report["n11_neuf_noeuds"] = all(n11_nodes.values())
            report["n11_neuf_detail"] = n11_nodes

            mark("n11: une ligne, appariement, trois refus")
            self.new_part("Pièce graphe N011 ligne")
            five = {
                "nodes": [
                    _n4_node("s", "serie", depart=5, pas=5, nombre=5),
                    _n4_node("c", "cercle", point=origin, direction=zdir),
                ],
                "edges": [{"from": "s", "to": "c", "input": "rayon"}],
                "output": "c",
            }
            tree = self.add_graph_feature(five)
            graphs = [s for s in tree["surfaces"] if s.get("graph")]
            five_obj = (self._require_doc().getObject(graphs[-1]["name"])
                        if graphs else None)
            stored = (self.get_graph_feature(graphs[-1]["name"])
                      if graphs else {})
            report["n11_une_ligne"] = (
                len(graphs) == 1
                and stored.get("graph", {}).get("output") == "c"
                and stored.get("graph", {}).get("nodes") == five["nodes"])
            report["n11_appariement"] = (
                five_obj is not None
                and len(five_obj.Shape.Edges) == 5)

            mixed = {
                "nodes": [
                    _n4_node("mix", "option_liste", op="flatten", liste=[
                        {"shape": "boite", "length": 10, "width": 10,
                         "height": 10, "x": 0, "y": 0, "z": 0},
                        {"shape": "ligne",
                         "point1": [0, 0, 0], "point2": [10, 0, 0]},
                    ]),
                ],
                "edges": [],
                "output": "mix",
            }
            n_surf = len(self.get_tree()["surfaces"])
            n_feat = len(self.get_tree()["features"])
            try:
                self.add_graph_feature(mixed)
                report["n11_refus_mixte"] = False
            except KernelError as exc:
                msg = str(exc)
                report["n11_refus_mixte"] = (
                    "Boîte" in msg and "Ligne" in msg
                    and len(self.get_tree()["surfaces"]) == n_surf
                    and len(self.get_tree()["features"]) == n_feat)

            circle = {
                "nodes": [_n4_node(
                    "c", "cercle", rayon=5, point=origin, direction=zdir)],
                "edges": [], "output": "c",
            }
            n_surf = len(self.get_tree()["surfaces"])
            try:
                self.add_graph_feature(circle, mode="cut")
                report["n11_refus_mode"] = False
            except KernelError as exc:
                report["n11_refus_mode"] = (
                    "fuse" in str(exc) and "cut" in str(exc)
                    and len(self.get_tree()["surfaces"]) == n_surf)

            self.new_part("Pièce graphe N011 nature")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            vol_nature = _volume()
            box_graph = {
                "nodes": [_n4_node(
                    "b", "boite", longueur=8, largeur=8, hauteur=8,
                    ancrage={"x": -4, "y": -4, "z": -1})],
                "edges": [], "output": "b",
            }
            tree = self.add_graph_feature(box_graph, mode="cut")
            graphe_bool = next(f for f in tree["features"] if f.get("graph"))
            vol_cut = _volume()
            line_graph = {
                "nodes": [_n4_node(
                    "l", "ligne", point1=origin,
                    point2={"x": 10, "y": 0, "z": 0})],
                "edges": [], "output": "l",
            }
            try:
                self.edit_graph_feature(graphe_bool["name"], line_graph)
                report["n11_refus_nature"] = False
            except KernelError as exc:
                report["n11_refus_nature"] = (
                    "solide" in str(exc)
                    and _close(_volume(), vol_cut)
                    and abs(_volume() - vol_nature) > 1.0)

            mark("n11b: libellé Courbe / Surface, et la réédition le met à jour")
            self.new_part("Pièce graphe N011b")
            circle_graph = {
                "nodes": [_n4_node(
                    "c", "cercle", rayon=10, point=origin, direction=zdir)],
                "edges": [], "output": "c",
            }
            plane_graph = {
                "nodes": [_n4_node(
                    "p", "plan", longueur=20, largeur=10,
                    point=origin, direction=zdir)],
                "edges": [], "output": "p",
            }
            tree = self.add_graph_feature(circle_graph)
            curve_line = next(s for s in tree["surfaces"] if s.get("graph"))
            tree = self.edit_graph_feature(curve_line["name"], plane_graph)
            edited = next(
                s for s in tree["surfaces"] if s["name"] == curve_line["name"])
            self.new_part("Pièce graphe N011b surface")
            tree = self.add_graph_feature(plane_graph)
            surf_line = next(s for s in tree["surfaces"] if s.get("graph"))
            report["n11b_libelle"] = (
                curve_line["label"] == "Fonction graphe — Courbe"
                and edited["label"] == "Fonction graphe — Surface"
                and edited["label"] != curve_line["label"]
                and surf_line["label"] == "Fonction graphe — Surface")

            mark("p19: paroi mince — profil fermé, ouvert, réédition")
            self.new_part("Pièce paroi mince")
            self.add_rect_sketch(40, 20)
            tree = self.add_pad(10, thin={"type": "un", "thickness": 2})
            thin_pad = tree["features"][-1]
            volume = self._require_body().Shape.Volume
            closed_ok = (abs(volume - (44 * 24 - 40 * 20) * 10) < 1e-3
                         and len(tree["features"]) == 1
                         and len(thin_pad.get("children") or []) == 1
                         and thin_pad.get("thin", {}).get("thickness") == 2
                         and thin_pad.get("deps") == [
                             thin_pad["children"][0]["name"]])
            self.set_params(thin_pad["name"], {"Thickness": 1})
            volume = self._require_body().Shape.Volume
            edit_ok = abs(volume - (42 * 22 - 40 * 20) * 10) < 1e-3
            state = self.sketch_start()
            self.sketch_add_line(state["sketch"], 0, 50, 30, 50)
            self.sketch_add_line(state["sketch"], 30, 50, 30, 70)
            before = self._require_body().Shape.Volume
            tree = self.add_pad(5, sketch=state["sketch"],
                                thin={"type": "milieu", "thickness": 2})
            open_ok = abs(self._require_body().Shape.Volume - before
                          - 2 * 50 * 5) < 1e-3
            last = tree["features"][-1]["name"]
            self.delete_feature(last)
            helpers = [o for o in self._require_body().Group
                       if self._is_thin_helper(o)]
            report["p19_paroi_mince"] = (closed_ok and edit_ok and open_ok
                                         and len(helpers) == 1)
            try:
                self.add_pad(5, thin={"type": "deux", "thickness": 1})
                report["p19_paroi_mince_refus"] = False
            except KernelError:
                report["p19_paroi_mince_refus"] = (
                    len([o for o in self._require_body().Group
                         if self._is_thin_helper(o)]) == 1)

            mark("p38: coque sur plusieurs faces, vers l'extérieur")
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 20)
            self.add_pad(10)
            body = self._require_body()
            faces = body.Shape.Faces
            top = next(i for i, f in enumerate(faces)
                       if abs(f.CenterOfMass.z - 10) < 1e-6)
            side = next(i for i, f in enumerate(faces)
                        if abs(f.CenterOfMass.x - 20) < 1e-6)
            tree = self.add_thickness(faces=[top, side], thickness=1)
            inward = body.Shape.Volume
            self.delete_feature(tree["features"][-1]["name"])
            self.add_thickness(faces=[top, side], thickness=1, outward=True)
            bb = body.Shape.BoundBox
            report["p38_coque_multi"] = (
                abs(inward - (8000 - 39 * 18 * 9)) < 1e-3
                and abs(bb.XMin + 21) < 1e-6 and abs(bb.XMax - 20) < 1e-6
                and abs(bb.ZMax - 10) < 1e-6)
            try:
                self.add_thickness(faces=[], thickness=1)
                report["p38_coque_refus"] = False
            except KernelError:
                report["p38_coque_refus"] = True

            mark("p40: un profil démarré sur l'origine y reste attaché")
            self.new_part("Pièce origine")
            name = self.sketch_start()["sketch"]
            self.sketch_add_line(name, 0, 0, 30, 0)
            self.sketch_add_line(name, 30, 0, 30, 10)
            state = self.sketch_add_circle(name, 0, 0, 5)
            rooted = [c for c in self._get_sketch(name).Constraints
                      if c.Type == "Coincident" and c.Second == -1]
            report["p40_origine"] = (
                len(rooted) == 2
                and {c.FirstPos for c in rooted} == {1, 3}
                and state["dof"] == 3)  # deux longueurs, un rayon

            mark("p42: rectangle en une opération, tenu par son centre")
            self.new_part("Pièce rectangle")
            name = self.sketch_start()["sketch"]
            state = self.sketch_add_rectangle(name, -50, -30, 50, 30,
                                              center=True)
            cons = self._get_sketch(name).Constraints
            report["p42_rectangle_centre"] = (
                len(state["entities"]) == 4
                and state["dof"] == 2  # largeur et hauteur seulement
                and any(c.Type == "Symmetric" and c.Third == -1 for c in cons))

            mark("p43: arêtes de couture non tracées")
            self.new_part("Pièce cylindre")
            name = self.sketch_start()["sketch"]
            self.sketch_add_circle(name, 0, 0, 10)
            self.sketch_finish(name)
            self.add_pad(20)
            shape = self._require_body().Shape
            drawn = {g["edgeId"] for g in self.tessellate_edges()["groups"]}
            # Un cylindre : deux cercles tracés, la couture (droite) omise.
            report["p43_coutures"] = (
                len(shape.Edges) == 3 and len(drawn) == 2
                and all(shape.Edges[i].Curve.__class__.__name__ == "Circle"
                        for i in drawn))
            # Leurs centres partent avec elles : un clic de position s'y
            # aimante (perçage au centre d'un moyeu).
            centers = sorted(round(g["center"][2], 6)
                             for g in self.tessellate_edges()["groups"]
                             if "center" in g)
            report["p43_centres"] = centers == [0.0, 20.0]

            mark("p44: trou placé par cote depuis l'origine et verticale")
            self.new_part("Pièce cercle de perçage")
            name = self.sketch_start()["sketch"]
            self.sketch_add_circle(name, 2, -28, 4)
            # Cercle + origine : la distance de son centre à l'origine.
            self.sketch_dim(name, 0, value=30, geo2=-1, point2=1)
            state = self.sketch_constrain(name, "vertical", 0, point1=3,
                                          geo2=-1, point2=1)
            circle = state["entities"][0]
            report["p44_cote_origine"] = (
                abs(circle["c"][0]) < 1e-6 and abs(circle["c"][1] + 30) < 1e-6
                and state["dof"] == 1)  # reste le rayon
            # Cotes horizontale / verticale d'un point depuis l'origine :
            # un sommet de nervure posé en (20, 12), valeurs positives même
            # tracé de l'autre côté.
            name = self.sketch_start()["sketch"]
            self.sketch_add_line(name, 18, 10, 36, 10)
            self.sketch_dim(name, -1, geo2=0, point=1, point2=1, axis="x")
            state = self.sketch_dim(name, 0, geo2=-1, point=1, point2=1,
                                    axis="y")
            dims = state["dims"]
            for dim, target in zip(dims, (20, 12)):
                self.sketch_set_dim(name, dim["id"], value=target)
            line = self.sketch_state(name)["entities"][0]
            # Posée sous le segment : la cote garde ce décalage (sauvé).
            placed = self.sketch_dim(name, 0, at=[27, 3])["dims"][-1]
            moved = self.sketch_place_dim(name, placed["id"], 5)
            moved = next(d for d in moved["dims"] if d["id"] == placed["id"])
            report["p44_cote_posee"] = (
                placed["offset"] is not None
                and abs(placed["offset"] + 9) < 1e-6
                and abs(moved["offset"] - 5) < 1e-6
                and abs(moved["value"] - placed["value"]) < 1e-9)
            # Cotation intelligente : rayon d'un cercle, cercle + ligne,
            # deux cercles, longueur projetée d'une ligne oblique.
            name = self.sketch_start()["sketch"]
            self.sketch_add_circle(name, 0, 0, 5)                   # 0
            self.sketch_add_line(name, 20, -10, 20, 10)             # 1
            self.sketch_add_circle(name, 0, 30, 3)                  # 2
            self.sketch_add_line(name, 40, 0, 50, 6)                # 3
            kinds = []
            for params in ({"geo": 0, "radius": True},
                           {"geo": 0, "geo2": 1},
                           {"geo": 0, "geo2": 2},
                           {"geo": 3, "geo2": 3, "point": 1, "point2": 2,
                            "axis": "x"}):
                last = self.sketch_dim(name, **params)["dims"][-1]
                kinds.append((last["type"], round(last["value"], 6)))
            # Angle posé : l'arc passe là où on a cliqué (rayon retenu).
            self.sketch_add_line(name, 60, 0, 80, 0)                # 4
            self.sketch_add_line(name, 60, 10, 80, 30)              # 5
            # Les lignes 5 puis 4 tournent dans le sens horaire : la cote ne
            # doit pas les faire pivoter.
            before = [e for e in self.sketch_state(name)["entities"]
                      if e["id"] in (4, 5)]
            state = self.sketch_dim(name, 5, geo2=4, at=[50, 50])
            angle = state["dims"][-1]
            after = [e for e in state["entities"] if e["id"] in (4, 5)]
            unmoved = all(abs(u - v) < 1e-6
                          for e1, e2 in zip(before, after)
                          for key in ("p1", "p2")
                          for u, v in zip(e1[key], e2[key]))
            corner_ok = (angle["type"] == "Angle" and angle["offset"] is not None
                         and abs(angle["offset"] - 50) < 1e-6)
            report["p44_cotation_intelligente"] = corner_ok and unmoved and kinds == [
                ("Radius", 5.0), ("Distance", 20.0), ("Distance", 30.0),
                ("DistanceX", 10.0)]
            report["p44_cotes_hv"] = (
                [d["type"] for d in dims] == ["DistanceX", "DistanceY"]
                and all(d["value"] > 0 for d in dims)
                and abs(line["p1"][0] - 20) < 1e-6
                and abs(line["p1"][1] - 12) < 1e-6)

            mark("p45: aperçu du plan de référence, sans le créer")
            self.new_part("Pièce plan")
            before = len(self._require_doc().Objects)
            shown = self.preview("add_datum_plane",
                                 {"base": "XY", "offset": 50})
            matrix = shown.get("plane") or []
            report["p45_apercu_plan"] = (
                len(matrix) == 16 and abs(matrix[11] - 50) < 1e-6
                and len(self._require_doc().Objects) == before)

            mark("p46: spline 3D rééditable, balayage qui suit")
            import math
            import os
            import tempfile
            self.new_part("Pièce surfaces avancées")
            tree = self.add_curve3d([[0, 0, 0], [0, 20, 20], [0, 40, 20]])
            curve = tree["surfaces"][-1]
            spec = curve.get("curve") or {}
            report["p46_spline_points"] = (
                spec.get("spline") is True and spec.get("closed") is False
                and spec.get("points") == [[0, 0, 0], [0, 20, 20], [0, 40, 20]])
            state = self.sketch_start(plane="XZ")
            prof = state["sketch"]
            self.sketch_add_line(prof, -5, 0, 5, 0)
            self.sketch_finish(prof)
            tree = self.surface_sweep(prof, curve["name"])
            swept = self._require_doc().getObject(tree["surfaces"][-1]["name"])
            area_before = swept.Shape.Area
            self.edit_curve3d(curve["name"],
                              [[0, 0, 0], [0, 20, 20], [0, 60, 20]])
            report["p46_balayage_suit_spline"] = (
                swept.TypeId == "Part::Sweep" and not swept.Shape.Solids
                and swept.Shape.Area > area_before + 50)
            closed = self.add_curve3d(
                [[0, 0, 0], [30, 0, 5], [30, 30, 0], [0, 30, 5]],
                spline=False, closed=True)["surfaces"][-1]
            report["p46_polyligne_fermee"] = (
                self._require_doc().getObject(closed["name"]).Shape.isClosed())
            mesh = self.tessellate()
            curves = mesh.get("curves") or []
            report["p46_courbes_cliquables"] = (
                {c["name"] for c in curves} >= {curve["name"], closed["name"]}
                and all(c["edges"]["groups"] for c in curves))

            mark("p46: remplissage, plane, décalée, prolongée, ajustée")
            tree = self.surface_fill([{"name": closed["name"]}])
            filled = self._require_doc().getObject(tree["surfaces"][-1]["name"])
            report["p46_remplissage_courbe"] = (
                filled.TypeId == "Surface::Filling"
                and filled.Shape.Area > 800)
            state = self.sketch_start(plane="XY")
            square = state["sketch"]
            self.sketch_add_rectangle(square, 0, 0, 40, 40)
            self.sketch_finish(square)
            tree = self.surface_planar(sketch=square)
            plane = tree["surfaces"][-1]
            report["p46_surface_plane"] = abs(
                self._require_doc().getObject(plane["name"]).Shape.Area
                - 1600) < 1e-6
            tree = self.surface_offset(plane["name"], 10)
            offset = self._require_doc().getObject(tree["surfaces"][-1]["name"])
            report["p46_surface_decalee"] = (
                not offset.Shape.Solids
                and abs(abs(offset.Shape.BoundBox.ZMin) - 10) < 1e-6)
            # Prolonger le carré de 10 mm au-delà d'un seul bord.
            edges = next(s for s in self.tessellate().get("surfaces") or []
                         if s["name"] == plane["name"])["edges"]["groups"]
            edge = edges[0]["edgeId"]
            tree = self.surface_extend(plane["name"], 10, edge=edge)
            extended = tree["surfaces"][-1]
            ext_obj = self._require_doc().getObject(extended["name"])
            spec = extended.get("surface") or {}
            report["p46_prolonger_un_bord"] = (
                abs(ext_obj.Shape.Area - 2000) < 1
                and spec.get("kind") == "extend"
                and spec.get("distance") == 10 and spec.get("edge") == edge)
            self.edit_surface_extend(extended["name"], 5)
            report["p46_prolonger_tous_bords"] = abs(
                ext_obj.Shape.Area - 2500) < 1
            # Ajuster le carré par une surface verticale en x = 10.
            state = self.sketch_start(plane="XY")
            wall = state["sketch"]
            self.sketch_add_line(wall, 10, -10, 10, 50)
            self.sketch_finish(wall)
            App = self._app()
            self._require_doc().getObject(wall).AttachmentOffset = (
                App.Placement(App.Vector(0, 0, -10), App.Rotation()))
            self._recompute()
            tree = self.surface_extrude(30, sketch=wall)
            cutter = tree["surfaces"][-1]["name"]
            names_before = {s["name"] for s in tree["surfaces"]}
            tree = self.surface_trim(plane["name"], cutter, point=[30, 20, 0])
            trimmed = tree["surfaces"][-1]
            trim_obj = self._require_doc().getObject(trimmed["name"])
            hidden = [s["name"] for s in tree["surfaces"]
                      if s["name"] not in names_before
                      and s["name"] != trimmed["name"]]
            shown = {s["name"] for s in self.tessellate().get("surfaces") or []}
            source_entry = next(s for s in tree["surfaces"]
                                if s["name"] == plane["name"])
            report["p46_ajuster_garde_le_cote"] = (
                abs(trim_obj.Shape.Area - 1200) < 1e-3
                and (trimmed.get("surface") or {}).get("kind") == "trim"
                and not hidden
                and plane["name"] not in shown and cutter in shown
                and source_entry.get("consumed") is True)
            self.edit_surface_trim(trimmed["name"], [5, 20, 0])
            near_ok = abs(trim_obj.Shape.Area - 400) < 1e-3
            self.edit_surface_trim(trimmed["name"])
            report["p46_ajuster_change_de_cote"] = near_ok and abs(
                trim_obj.Shape.Area - 1200) < 1e-3
            path = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest-surfaces.FCStd")
            self.save_part(path)
            reopened = self.open_part(path)
            kinds = [(s.get("surface") or {}).get("kind")
                     for s in reopened["surfaces"]]
            report["p46_reouverture"] = (
                "trim" in kinds and "extend" in kinds
                and any(s.get("curve") for s in reopened["surfaces"])
                and not any("Invalid" in (o.State or ())
                            for o in self._require_doc().Objects))
            # Remplir le dessus d'un bloc par ses arêtes.
            self.new_part("Pièce remplissage")
            self.add_rect_sketch(20, 20)
            self.add_pad(5)
            body = self._require_body()
            top = [i for i, e in enumerate(body.Shape.Edges)
                   if abs(e.CenterOfMass.z - 5) < 1e-6]
            tree = self.surface_fill([{"body": True, "edge": i} for i in top])
            report["p46_remplissage_aretes_solide"] = abs(
                self._require_doc().getObject(
                    tree["surfaces"][-1]["name"]).Shape.Area - 400) < 1e-3

            mark("p47: couper le solide avec une surface")
            self.new_part("Pièce coupe surface")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            body = self._require_body()
            state = self.sketch_start(plane="XY")
            line = state["sketch"]
            self.sketch_add_line(line, -40, -40, 40, 40)
            self.sketch_finish(line)
            App = self._app()
            self._require_doc().getObject(line).AttachmentOffset = (
                App.Placement(App.Vector(0, 0, -10), App.Rotation()))
            self._recompute()
            tree = self.surface_extrude(40, sketch=line)
            wall = tree["surfaces"][-1]["name"]
            shown = self.preview("add_surface_cut", {"surface": wall})
            report["p47_apercu_coupe"] = (
                bool(shown.get("positions"))
                and abs(body.Shape.Volume - 32000) < 1e-3)
            tree = self.add_surface_cut(wall)
            cut = tree["features"][-1]
            half_volume = body.Shape.Volume
            entry = next(s for s in tree["surfaces"] if s["name"] == wall)
            mesh = self.tessellate()
            report["p47_coupe_par_surface"] = (
                abs(half_volume - 16000) < 1e-3
                and cut.get("surface_cut") == {"surface": wall,
                                               "flip": False}
                and entry.get("consumed") is True
                and not any(s["name"] == wall
                            for s in mesh.get("surfaces") or [])
                and len(tree["bodies"]) == 1)
            kept_x = body.Shape.Solids[0].CenterOfMass.x
            self.edit_surface_cut(cut["name"], True)
            report["p47_coupe_autre_cote"] = (
                abs(body.Shape.Volume - 16000) < 1e-3
                and (body.Shape.Solids[0].CenterOfMass.x > 0) != (kept_x > 0))
            # La surface bouge : la coupe suit (cote paramétrique).
            line_obj = self._require_doc().getObject(line)
            line_obj.AttachmentOffset = App.Placement(
                App.Vector(10, 0, -10), App.Rotation())
            self._recompute()
            report["p47_coupe_suit_surface"] = abs(
                body.Shape.Volume - 16000) > 100
            try:
                state = self.sketch_start(plane="XY")
                far = state["sketch"]
                self.sketch_add_line(far, 100, -40, 100, 40)
                self.sketch_finish(far)
                tree = self.surface_extrude(40, sketch=far)
                count = len(self.get_tree()["features"])
                self.add_surface_cut(tree["surfaces"][-1]["name"])
                report["p47_coupe_sans_effet_refusee"] = False
            except KernelError as exc:
                report["p47_coupe_sans_effet_refusee"] = (
                    ("ne coupe pas" in str(exc) or "enlève tout" in str(exc))
                    and len(self.get_tree()["features"]) == count)

            mark("p48: frontière, réglée, composite, projetée, intersection")
            import math
            self.new_part("Pièce surfacique complète")
            doc = self._require_doc()
            App = self._app()
            obj_of = lambda tree: doc.getObject(  # noqa: E731
                tree["surfaces"][-1]["name"])
            curves = []
            for pts in ([[0, 0, 0], [15, 0, 5], [30, 0, 0]],
                        [[30, 0, 0], [32, 15, 4], [30, 30, 0]],
                        [[30, 30, 0], [15, 30, 6], [0, 30, 0]],
                        [[0, 30, 0], [-2, 15, 3], [0, 0, 0]]):
                curves.append(self.add_curve3d(pts)["surfaces"][-1]["name"])
            bump = obj_of(self.surface_boundary(
                [{"name": c} for c in curves]))
            two = obj_of(self.surface_boundary(
                [{"name": curves[0]}, {"name": curves[2]}]))
            report["p48_surface_frontiere"] = (
                bump.TypeId == "Surface::GeomFillSurface"
                and bump.Shape.Area > 900 and two.Shape.Area > 600)
            ruled = obj_of(self.surface_ruled(
                [{"name": curves[0], "edge": 0}, {"name": curves[2]}]))
            report["p48_surface_reglee"] = (
                ruled.TypeId == "Part::RuledSurface"
                and ruled.Shape.Area > 900)
            composite = obj_of(self.curve_composite(
                [{"name": c} for c in curves[:3]]))
            state = self.sketch_start(plane="YZ")
            prof = state["sketch"]
            self.sketch_add_line(prof, -3, 0, 3, 0)
            self.sketch_finish(prof)
            swept = obj_of(self.surface_sweep(prof, composite.Name))
            report["p48_courbe_composite"] = (
                len(composite.Shape.Edges) == 3
                and composite.Name in {s["name"] for s
                                       in self.get_tree()["surfaces"]}
                and bool(swept.Shape.Faces))
            state = self.sketch_start(plane="XY")
            proj_sk = state["sketch"]
            self.sketch_add_circle(proj_sk, 15, 15, 5)
            self.sketch_finish(proj_sk)
            doc.getObject(proj_sk).AttachmentOffset = App.Placement(
                App.Vector(0, 0, 30), App.Rotation())
            self._recompute()
            projected = obj_of(self.curve_project(proj_sk, bump.Name))
            report["p48_courbe_projetee"] = (
                bool(projected.Shape.Edges)
                and projected.Shape.distToShape(bump.Shape)[0] < 1e-3)
            # Trou dans la bosse : un tube ajuste la surface.
            state = self.sketch_start(plane="XY")
            tube_sk = state["sketch"]
            self.sketch_add_circle(tube_sk, 15, 15, 5)
            self.sketch_finish(tube_sk)
            doc.getObject(tube_sk).AttachmentOffset = App.Placement(
                App.Vector(0, 0, -10), App.Rotation())
            self._recompute()
            tube = obj_of(self.surface_extrude(30, sketch=tube_sk))
            section = obj_of(self.curve_intersection(bump.Name, tube.Name))
            report["p48_courbe_intersection"] = (
                section.TypeId == "Part::Section"
                and abs(section.Shape.Length - 2 * math.pi * 5) < 1.0)
            holed = obj_of(self.surface_trim(bump.Name, tube.Name,
                                             point=[2, 15, 1]))
            inner = [i for i, e in enumerate(holed.Shape.Edges)
                     if math.hypot(e.CenterOfMass.x - 15,
                                   e.CenterOfMass.y - 15) < 6]
            edges = [{"name": holed.Name, "edge": i} for i in inner]
            flat = obj_of(self.surface_fill(edges))
            smooth = obj_of(self.surface_fill(edges, tangent=True))
            # Tangent : la pièce épouse la bosse qu'elle rebouche (son
            # centre retombe sur la surface d'origine), mieux que le contact.
            def gap(patch):
                center = patch.Shape.Faces[0].CenterOfMass
                import Part
                return Part.Vertex(center).distToShape(bump.Shape)[0]
            report["p48_remplissage_tangent"] = (
                bool(inner) and "Invalid" not in smooth.State
                and list(smooth.BoundaryOrder) == [1] * len(inner)
                and gap(smooth) < 0.3 and gap(smooth) < gap(flat))

            mark("p48: supprimer des faces, désajuster, congé de surface")
            state = self.sketch_start(plane="XY")
            corner = state["sketch"]
            self.sketch_add_line(corner, 0, 0, 20, 0)
            self.sketch_add_line(corner, 20, 0, 20, 20)
            self.sketch_finish(corner)
            angle = obj_of(self.surface_extrude(10, sketch=corner))
            import Part
            shared = [i for i, e in enumerate(angle.Shape.Edges)
                      if len(angle.Shape.ancestorsOfType(e, Part.Face)) == 2]
            rounded = obj_of(self.surface_fillet(angle.Name, shared, 3))
            report["p48_conge_surface"] = (
                len(shared) == 1 and len(rounded.Shape.Faces) == 3
                and rounded.Shape.Area < angle.Shape.Area)
            area3 = rounded.Shape.Area
            self.edit_surface_fillet(rounded.Name, 6)
            report["p48_conge_surface"] = (report["p48_conge_surface"]
                                           and rounded.Shape.Area < area3)
            tree = self.surface_delete_faces(angle.Name, [0])
            pruned = obj_of(tree)
            entry = next(s for s in tree["surfaces"]
                         if s["name"] == angle.Name)
            # Une forme composée (le congé) se prête aussi à la suppression.
            pruned_fillet = obj_of(self.surface_delete_faces(rounded.Name,
                                                             [0]))
            report["p48_supprimer_faces"] = (
                len(pruned.Shape.Faces) == 1
                and entry.get("consumed") is True
                and len(pruned_fillet.Shape.Faces) == 2)
            state = self.sketch_start(plane="XY")
            plate = state["sketch"]
            self.sketch_add_rectangle(plate, 0, 0, 40, 40)
            self.sketch_add_circle(plate, 20, 20, 5)
            self.sketch_finish(plate)
            holed_plate = obj_of(self.surface_planar(sketch=plate))
            mesh = self.tessellate()
            plate_mesh = next(s for s in mesh.get("surfaces") or []
                              if s["name"] == holed_plate.Name)
            untrimmed = obj_of(self.surface_untrim(holed_plate.Name))
            report["p48_desajuster"] = (
                abs(holed_plate.Shape.Area - (1600 - math.pi * 25)) < 0.1
                and abs(untrimmed.Shape.Area - 1600) < 0.1
                and len(plate_mesh.get("groups") or []) == 1)

            # Ligne de séparation puis suppression d'un morceau.
            cut_line = self.add_curve3d([[10, -5, 0], [10, 45, 0]],
                                        spline=False)["surfaces"][-1]["name"]
            plain = obj_of(self.surface_untrim(holed_plate.Name))
            split = obj_of(self.surface_split(plain.Name, cut_line))
            areas = sorted(round(f.Area) for f in split.Shape.Faces)
            small = next(i for i, f in enumerate(split.Shape.Faces)
                         if round(f.Area) == 400)
            rest = obj_of(self.surface_delete_faces(split.Name, [small]))
            report["p48_ligne_separation"] = (
                areas == [400, 1200] and abs(rest.Shape.Area - 1200) < 0.1)

            mark("p49: supprimer la face d'un solide")
            self.new_part("Pièce défeaturing")
            self.add_rect_sketch(40, 40)
            tree = self.add_pad(10)
            pad = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if abs(f.CenterOfMass.z - 10) < 1e-6)
            self.add_hole(6, through=True, face=top, points=[[0, 0, 10]])
            holed = body.Shape.Volume
            cyl = [i for i, f in enumerate(body.Shape.Faces)
                   if f.Surface.TypeId == "Part::GeomCylinder"]
            shown = self.preview("add_delete_face", {"faces": cyl})
            tree = self.add_delete_face(cyl)
            last = tree["features"][-1]
            report["p49_supprimer_face_solide"] = (
                bool(shown.get("positions"))
                and holed < 16000 - 1
                and abs(body.Shape.Volume - 16000) < 1e-3
                and last.get("delete_face") == {"faces": cyl}
                and len(tree["bodies"]) == 1)
            # Le bloc s'épaissit : la face supprimée suit.
            self.set_params(pad, {"Length": 20.0})
            report["p49_suit_les_fonctions"] = abs(
                body.Shape.Volume - 32000) < 1e-3

            mark("p49: remplacer la face d'un solide par une surface")
            self.new_part("Pièce remplacer face")
            self.add_rect_sketch(40, 40)
            tree = self.add_pad(10)
            pad = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            body = self._require_body()
            state = self.sketch_start(plane="XZ")
            roof = state["sketch"]
            self.sketch_add_line(roof, -40, 6, 0, 16)
            self.sketch_add_line(roof, 0, 16, 40, 6)
            self.sketch_finish(roof)
            doc = self._require_doc()
            App = self._app()
            doc.getObject(roof).AttachmentOffset = App.Placement(
                App.Vector(0, 0, -40), App.Rotation())
            self._recompute()
            tree = self.surface_extrude(80, sketch=roof)
            roof_surface = tree["surfaces"][-1]["name"]
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if abs(f.CenterOfMass.z - 10) < 1e-6)
            tree = self.add_replace_face(top, roof_surface)
            volume = body.Shape.Volume
            # Toit 6 → 16 → 6 sur x ∈ [-40, 40] : sur le bloc (±20),
            # hauteur moyenne 16 - 5 = 11 → 40 × 40 × 13,5 / ... calcul :
            # z(x) = 16 - |x|/4 ; moyenne sur [0, 20] = 16 - 2,5 = 13,5.
            report["p49_remplacer_face"] = (
                abs(volume - 1600 * 13.5) < 1
                and not any(s["name"] == roof_surface for s
                            in self.tessellate().get("surfaces") or [])
                and tree["features"][-1].get("replace_face", {}).get(
                    "surface") == roof_surface)
            self.set_params(pad, {"Length": 4.0})
            report["p49_remplacer_suit"] = abs(
                body.Shape.Volume - 1600 * 13.5) < 1
            # Toit qui coupe le bloc : ajout ET retrait, deux booléens.
            self.new_part("Pièce remplacer mixte")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            body = self._require_body()
            state = self.sketch_start(plane="XZ")
            slope = state["sketch"]
            self.sketch_add_line(slope, -40, 4, 40, 16)
            self.sketch_finish(slope)
            self._require_doc().getObject(slope).AttachmentOffset = (
                App.Placement(App.Vector(0, 0, -40), App.Rotation()))
            self._recompute()
            tree = self.surface_extrude(80, sketch=slope)
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if abs(f.CenterOfMass.z - 10) < 1e-6)
            tree = self.add_replace_face(top, tree["surfaces"][-1]["name"])
            report["p49_remplacer_mixte"] = (
                abs(body.Shape.Volume - 1600 * 10) < 1
                and abs(body.Shape.BoundBox.ZMax - 13) < 1e-6
                and [f["label"] for f in tree["features"]][-2:]
                == ["Remplacer la face — ajout", "Remplacer la face"])

            mark("p41: perçage par centres cliqués sur une face")
            self.new_part("Pièce perçage")
            self.add_rect_sketch(60, 40)
            self.add_pad(8)
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if abs(f.CenterOfMass.z - 8) < 1e-6)
            before = body.Shape.Volume
            tree = self.add_hole(6, through=True, face=top,
                                 points=[[-15, 0, 8], [15, 5, 8]])
            import math
            removed = before - body.Shape.Volume
            report["p41_percage_points"] = (
                abs(removed - 2 * math.pi * 9 * 8) < 1e-2
                and tree["features"][-1]["type"] == "PartDesign::Hole"
                and len(tree["features"]) == 2)

            mark("p19b: paroi mince à extrémités fermées")
            self.new_part("Pièce paroi fermée")
            self.add_rect_sketch(40, 20)
            body = self._require_body()
            tree = self.add_pad(10, thin={"type": "un", "thickness": 2,
                                          "caps": 1})
            capped = tree["features"][-1]["name"]
            def near(expected):
                return abs(body.Shape.Volume - expected) < 1e-3
            ok = (near(44 * 24 * 10 - 40 * 20 * 8)
                  and len(body.Shape.Solids) == 1
                  and len(tree["features"]) == 1
                  and tree["tip"] == capped
                  and tree["features"][0]["thin"]["caps"] == 1
                  and len(tree["features"][0].get("children") or []) == 1)
            self.set_params(capped, {"Length": 20})
            ok = ok and near(44 * 24 * 20 - 40 * 20 * 18)
            self.set_params(capped, {"CapThickness": 2})
            ok = ok and near(44 * 24 * 20 - 40 * 20 * 16)
            try:
                self.set_params(capped, {"CapThickness": 10})
                ok = False
            except KernelError:
                ok = ok and near(44 * 24 * 20 - 40 * 20 * 16)
            mesh = self.tessellate()
            ok = ok and all(g.get("feature") == capped
                            for g in mesh["groups"])
            tree = self.set_tip(capped)
            ok = (ok and tree["tip"] == capped
                  and self._is_thin_helper(body.Tip)
                  and near(44 * 24 * 20 - 40 * 20 * 16))
            self.delete_feature(capped)
            ok = ok and not [o for o in body.Group
                             if self._is_thin_helper(o)]
            self.add_pad(20, midplane=True, thin={
                "type": "milieu", "thickness": 2, "caps": 1})
            bb = body.Shape.BoundBox
            ok = (ok and near(42 * 22 * 20 - 38 * 18 * 18)
                  and abs(bb.ZMin + 10) < 1e-6 and abs(bb.ZMax - 10) < 1e-6)
            report["p19b_extremites_fermees"] = ok
            refused = 0
            for call_refused in (
                    lambda: self.add_pad(cond="suivant", thin={
                        "type": "un", "thickness": 1, "caps": 1}),
                    lambda: self.add_pocket(5, thin={
                        "type": "un", "thickness": 1, "caps": 1})):
                try:
                    call_refused()
                except KernelError:
                    refused += 1
            report["p19b_extremites_refus"] = (
                refused == 2 and len([o for o in body.Group
                                      if self._is_thin_helper(o)]) == 3)

            self._plugins.run_selftest(self, mark, report)

            mark("bilan")
            # Rouvrir la pièce vitrine : le viewport finit sur une pièce
            # qui montre ce que l'Autotest a testé, pas sur la plaque m1.5.
            self.open_part(vitrine_path)
            mark("n4e: mass_properties après ouverture pièce gravure")
            eval_mp = self.mass_properties()
            report["n4e_evaluer_apres_ouverture"] = (
                eval_mp["volume_mm3"] > 0
                and len(eval_mp.get("center_of_mass") or []) == 3
                and all(math.isfinite(x)
                        for x in eval_mp["center_of_mass"]))
            report["tree_after_pad"] = self.get_tree()
            mesh = self.tessellate()
            report["mesh_faces"] = len(mesh["groups"])
            report["mesh_triangles"] = len(mesh["indices"]) // 3
            report["bilan"] = selftest_summary(report)
            return report
        except KernelError as exc:
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], exc))
        except Exception as exc:  # noqa: BLE001 - name the step, always
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], _explain(exc)))
