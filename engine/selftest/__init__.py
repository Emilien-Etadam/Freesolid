"""Selftest de bout en bout, hors du code de production.

``Kernel`` en hérite. Le corps est le déplacement de l'ancienne méthode :
les noms définis dans ``kernel.py`` sont importés au début de l'appel,
pour ne pas charger ce module au démarrage du serveur.
"""

from types import SimpleNamespace


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
        from engine.selftest import assemblage, esquisse, mise_en_plan, noeuds, surfaces
        report = {"steps": []}
        etat = SimpleNamespace()

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

            esquisse.m2_rectangle_ligne_a_ligne(self, mark, report, etat)

            esquisse.m2_drag_suivi_solveur(self, mark, report, etat)

            esquisse.m2_cote_pilotante(self, mark, report, etat)

            esquisse.m2_extrusion_profil_dessine(self, mark, report, etat)

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

            etat.sk_name = sk_name
            esquisse.p1_geometrie_construction(self, mark, report, etat)

            esquisse.p1_esquisse_plan_nomme(self, mark, report, etat)

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

            esquisse.p7_relations(self, mark, report, etat)

            esquisse.p7_lister_supprimer_relation(self, mark, report, etat)

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

            assemblage.p10_deux_instances(self, mark, report, etat)

            assemblage.p10_contrainte_fixe(self, mark, report, etat)

            assemblage.p16_interferences(self, mark, report, etat)

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

            assemblage.spike_solveur_assemblage(self, mark, report, etat)

            surfaces.p12_extrusion_couture_epaississement(self, mark, report, etat)

            surfaces.p12_courbe_3d_balayage(self, mark, report, etat)

            surfaces.p30_barre_retour_surfaces(self, mark, report, etat)

            mise_en_plan.p13_mise_en_plan_dxf(self, mark, report, etat)

            esquisse.p14_convertir_entites(self, mark, report, etat)

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

            esquisse.p17_spline_ellipse_decalage(self, mark, report, etat)

            mark("p18: import STEP + export 3MF")
            tree = self.open_part(os.path.join(
                tempfile.gettempdir(), "freesolid-selftest.step"))
            report["p18_step_import_ok"] = (
                tree.get("imported_solids", 0) >= 1
                and len(self.tessellate()["groups"]) > 0)
            threemf = os.path.join(tempfile.gettempdir(),
                                   "freesolid-selftest.3mf")
            report["p18_3mf_ok"] = self.export_part(threemf)["size"] > 0

            esquisse.p3_arc_rainure_polygone(self, mark, report, etat)

            esquisse.p3_conge_esquisse(self, mark, report, etat)

            esquisse.p3_ajuster_trim(self, mark, report, etat)

            esquisse.p3_contraintes_manuelles(self, mark, report, etat)

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

            noeuds.n1_aretes_de_dependance(self, mark, report, etat)

            etat._volume = _volume
            noeuds.n4_fonction_graphe(self, mark, report, etat)

            etat._volume = _volume
            noeuds.n8_noeud_python(self, mark, report, etat)

            noeuds.n7_sous_elements_esquisse_attachee(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n9_repetition_groupe_fonctions(self, mark, report, etat)

            noeuds.n9_spike_rejeu_variable(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n10_repetition_variable(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n10_reedition(self, mark, report, etat)

            noeuds.n10_proprete(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n10_garde_topologique(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n10b_graphe_pilote(self, mark, report, etat)

            noeuds.n10b_seul_point_verite(self, mark, report, etat)

            noeuds.n10b_chaine_cotes(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n10b_garde_attache(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n11_helice_graphe_balayage(self, mark, report, etat)

            etat._close = _close
            noeuds.n11_neuf_noeuds(self, mark, report, etat)

            etat._close = _close
            etat._volume = _volume
            noeuds.n11_ligne_appariement_refus(self, mark, report, etat)

            noeuds.n11b_libelle_courbe_surface(self, mark, report, etat)

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

            esquisse.p40_profil_attache_origine(self, mark, report, etat)

            esquisse.p42_rectangle_par_centre(self, mark, report, etat)

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

            surfaces.p46_spline_3d_reeditable(self, mark, report, etat)

            surfaces.p46_remplissage_plane_decalee(self, mark, report, etat)

            surfaces.p47_couper_solide_surface(self, mark, report, etat)

            surfaces.p48_frontiere_reglee_composite(self, mark, report, etat)

            surfaces.p48_supprimer_faces_desajuster(self, mark, report, etat)

            surfaces.p49_supprimer_face_solide(self, mark, report, etat)

            surfaces.p49_remplacer_face_solide(self, mark, report, etat)

            surfaces.p50_courbe_helice_ressort(self, mark, report, etat)

            surfaces.p50_surface_radiee(self, mark, report, etat)

            surfaces.p50_surface_mediane_paroi(self, mark, report, etat)

            surfaces.p50_aplatir_surface_forme_libre(self, mark, report, etat)

            surfaces.p50_epaissir_en_enlevant(self, mark, report, etat)

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

            esquisse.p51_esquisse_traces_complementaires(self, mark, report, etat)

            esquisse.p51_esquisse_outils_edition(self, mark, report, etat)

            esquisse.p51_esquisse_relations_cotes(self, mark, report, etat)

            esquisse.p51_esquisse_references_liees(self, mark, report, etat)

            esquisse.p51_esquisse_texte_coin_equation(self, mark, report, etat)

            esquisse.p52_esquisse_partagee(self, mark, report, etat)

            esquisse.p52_calques_esquisse(self, mark, report, etat)

            mark("p53: commentaires, propriétés, historique")
            self.new_part("Pièce notes")

            def run(op, **params):
                out = dispatch(self, op, params)
                if not out["ok"]:
                    raise KernelError(out["error"])
                return out["result"]
            run("add_rect_sketch", width=30, height=20)
            run("add_pad", length=5)
            pad = self.get_tree()["features"][-1]["name"]
            noted = run("set_comment", feature=pad,
                        text="  épaisseur de la tôle  ")
            history = run("undo_history")
            run("rename", feature=pad, label="Plaque")  # puis deux pas défaits
            run("undo", steps=2)
            after = self.get_tree()
            props = run("set_document_properties", values={
                "author": "Atelier", "description": "Support",
                "custom": {"Référence": "FS-001", "Vide": ""}})
            report["p53_notes"] = (
                noted["features"][-1].get("comment") == "épaisseur de la tôle"
                and history["undo"][:2] == ["set_comment", "add_pad"]
                and history["redo"] == []
                and after["features"][-1]["label"] != "Plaque"
                and "comment" not in after["features"][-1]
                and run("undo_history")["redo"][:2] == ["set_comment",
                                                        "rename"]
                and props["author"] == "Atelier"
                and props["custom"] == {"Référence": "FS-001"})

            mark("p54: masquer un corps, une surface")
            self.new_part("Pièce masquée")
            self.add_rect_sketch(20, 20)
            self.add_pad(5)
            first = self._require_body().Name
            self.add_body()
            self.add_rect_sketch(10, 10)
            self.add_pad(30)
            second = self._require_body().Name
            self.set_hidden([first])
            hid_other = "other_bodies" not in self.tessellate()
            self.set_hidden([second])
            mesh = self.tessellate()
            hid_active = (not mesh["groups"]
                          and not self.tessellate_edges()["groups"])
            flags = {b["name"]: b["hidden"]
                     for b in self.get_tree()["bodies"]}
            self.set_hidden([first, second], hidden=False)
            back = self.tessellate()
            report["p54_masquer"] = (
                hid_other and hid_active
                and flags == {first: True, second: True}
                and bool(back["groups"]) and len(back["other_bodies"]) == 1)

            mark("p55: désactiver une fonction")
            self.new_part("Pièce désactivée")
            self.add_rect_sketch(20, 10)
            self.add_pad(10)
            whole = self._require_body().Shape.Volume
            self.add_fillet(2, edges=[0])
            rounded = self._require_body().Shape.Volume
            fillet = self.get_tree()["features"][-1]["name"]
            off = self.set_suppressed([fillet])
            plain = self._require_body().Shape.Volume
            self.set_suppressed([fillet], suppressed=False)
            report["p55_desactiver"] = (
                rounded < whole - 1
                and abs(plain - whole) < 1e-6
                and off["features"][-1].get("suppressed") is True
                and abs(self._require_body().Shape.Volume - rounded) < 1e-6
                and "suppressed" not in self.get_tree()["features"][-1])

            esquisse.p56_changer_plan_esquisse(self, mark, report, etat)

            mark("p57: chanfrein de sommet")
            self.new_part("Pièce coin")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            body = self._require_body()
            box = body.Shape.Volume
            corner = body.Shape.BoundBox
            self.add_vertex_chamfer([5], point=[corner.XMax, corner.YMax,
                                                corner.ZMax])
            equal = box - body.Shape.Volume
            cham = self.get_tree()["features"][-1]
            self.edit_vertex_chamfer(cham["name"], [2, 3, 4])
            three = box - body.Shape.Volume
            # La pièce grandit : le chanfrein suit la fonction d'avant.
            pad = self.get_tree()["features"][0]["name"]
            self.set_params(pad, {"Length": 20})
            grown = body.Shape.Volume
            report["p57_chanfrein_sommet"] = (
                abs(equal - 125 / 6) < 1e-6
                and abs(three - 24 / 6) < 1e-6
                and cham.get("vertex_chamfer", {}).get("distances")
                == [5.0, 5.0, 5.0]
                and abs(grown - (40 * 30 * 20 - 4)) < 1e-6)

            mark("p58: chaîne tangente, boucle")
            self.new_part("Pièce chaîne")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            body = self._require_body()
            upright = [i for i, e in enumerate(body.Shape.Edges)
                       if abs(e.BoundBox.ZLength - 10) < 1e-6]
            self.add_fillet(5, edges=upright)
            shape = body.Shape
            # Un bord droit du dessus : sa chaîne tangente fait le tour
            # (4 droites + 4 arcs) ; la boucle prend le dessus (8 arêtes)
            # ou le flanc (4 arêtes).
            line = next(i for i, e in enumerate(shape.Edges)
                        if abs(e.BoundBox.ZMin - 10) < 1e-6
                        and abs(e.BoundBox.ZMax - 10) < 1e-6
                        and e.Curve.TypeId == "Part::GeomLine")
            chain = self.edge_chain(line)["edges"]
            loop = self.edge_chain(line, mode="loop")
            other = self.edge_chain(line, mode="loop", face=1)
            report["p58_chaine"] = (
                len(upright) == 4 and len(chain) == 8
                and loop["faces"] == 2
                and sorted([len(loop["edges"]), len(other["edges"])]) == [4, 8]
                and line in loop["edges"] and line in other["edges"])

            mark("p59: matières, couleur de face")
            self.new_part("Pièce matière")
            self.add_rect_sketch(10, 10)
            self.add_pad(10)
            body = self._require_body()
            plain = self.mass_properties()["mass_g"]
            tree = self.set_body_material(body.Name, "steel")
            steel = self.mass_properties()
            self.set_body_color(body.Name, "#112233")
            self.set_body_material(body.Name, "custom", density=2.0)
            custom = self.mass_properties()["mass_g"]
            self.set_face_color([0, 2], "#ff0000")
            self.set_face_color([2], None)
            groups = self.tessellate()["groups"]
            tinted = [g["faceId"] for g in groups if g.get("color")]
            report["p59_matieres"] = (
                abs(plain - 1.24) < 1e-9
                and abs(steel["mass_g"] - 7.85) < 1e-9
                and tree["bodies"][0]["material"]["id"] == "steel"
                and tree["bodies"][0]["color"] == "#8c939b"
                and abs(custom - 2.0) < 1e-9
                and body.FreeSolidColor == "#112233"
                and tinted == [0])

            mark("p60: liste des erreurs")
            self.new_part("Pièce en erreur")
            self.add_rect_sketch(20, 10)
            self.add_pad(5)
            clean = self.rebuild_errors()["errors"]
            self.add_fillet(1, edges=[0])
            fillet = self.get_tree()["features"][-1]["name"]
            self._require_doc().getObject(fillet).Radius = 50  # trop grand
            self._require_doc().recompute()  # sans lever : l'erreur reste
            errors = self.rebuild_errors()["errors"]
            self._require_doc().getObject(fillet).Radius = 1
            self._require_doc().recompute()
            # Désactiver la fonction d'appui : le congé passe en erreur,
            # la désactivation est gardée.
            pad = self.get_tree()["features"][0]["name"]
            self.set_suppressed([pad])
            orphan = [e["name"] for e in self.rebuild_errors()["errors"]]
            kept = self.get_tree()["features"][0].get("suppressed") is True
            self.set_suppressed([pad], suppressed=False)
            report["p60_erreurs"] = (
                clean == [] and [e["name"] for e in errors] == [fillet]
                and bool(errors[0]["message"])
                and orphan == [fillet] and kept
                and self.rebuild_errors()["errors"] == [])

            mark("p61: axe, point, repère de référence")
            self.new_part("Pièce repères")
            self.add_rect_sketch(20, 10)
            self.add_pad(5)
            body = self._require_body()
            upright = next(i for i, e in enumerate(body.Shape.Edges)
                           if abs(e.BoundBox.ZLength - 5) < 1e-6)
            self.add_datum_axis(axis="X")
            self.add_datum_axis(edge=upright)
            self.add_datum_point(vertex=[10, 5, 5])
            self.add_datum_point(point=[1, 2, 3])
            tree = self.add_datum_cs(vertex=[-10, -5, 0])
            refs = [f for f in tree["features"] if f["type"] in (
                "PartDesign::Line", "PartDesign::Point",
                "PartDesign::CoordinateSystem")]
            doc = self._require_doc()

            def base(item):
                p = doc.getObject(item["name"]).Placement
                return [round(p.Base.x, 6), round(p.Base.y, 6),
                        round(p.Base.z, 6)]

            def along(item):
                v = doc.getObject(item["name"]).Placement.Rotation.multVec(
                    self._app().Vector(0, 0, 1))
                return [round(abs(v.x), 6), round(abs(v.y), 6),
                        round(abs(v.z), 6)]
            report["p61_reference"] = (
                [r["type"].split("::")[1] for r in refs]
                == ["Line", "Line", "Point", "Point", "CoordinateSystem"]
                and all(len(r.get("placement") or []) == 16 for r in refs)
                and along(refs[0]) == [1, 0, 0] and along(refs[1]) == [0, 0, 1]
                and base(refs[2]) == [10, 5, 5] and base(refs[3]) == [1, 2, 3]
                and base(refs[4]) == [-10, -5, 0]
                and refs[0]["kind"] == "Axe de référence")

            mark("p62: copier-coller une fonction")
            self.new_part("Pièce collée")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if f.normalAt(0, 0).z > 0.9)
            self.add_rect_sketch(10, 10, face=top)
            self.add_pad(5)
            boss = body.Tip.Name
            before = body.Shape.Volume
            bottom = next(i for i, f in enumerate(body.Shape.Faces)
                          if f.normalAt(0, 0).z < -0.9)
            tree = self.paste_feature(boss, face=bottom)
            pasted = tree["features"][-1]
            refused = False
            try:
                self.paste_feature(boss)
            except KernelError:
                refused = True
            report["p62_coller"] = (
                abs(body.Shape.Volume - before - 500) < 1e-6
                and pasted["type"] == "PartDesign::Pad"
                and pasted["name"] != boss
                and len(pasted.get("children") or []) == 1
                and body.Shape.BoundBox.ZMin < -4.9 and refused)

            mark("p63: répétition dans deux directions")
            self.new_part("Pièce quadrillée")
            self.add_rect_sketch(100, 100)
            self.add_pad(5)
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if f.normalAt(0, 0).z > 0.9)
            self.add_rect_sketch(10, 10, face=top)
            self.add_pad(5)
            tree = self.add_linear_pattern(20, 3, axis="X", spacing=True,
                                           length2=25, count2=2, axis2="Y")
            grid = tree["features"][-1]["name"]
            six = body.Shape.Volume
            self.set_params(grid, {"Occurrences2": 3})
            nine = body.Shape.Volume
            props = [p["prop"] for p in self.get_params(grid)["params"]]
            report["p63_deux_directions"] = (
                abs(six - (100 * 100 * 5 + 6 * 500)) < 1e-6
                and abs(nine - (100 * 100 * 5 + 9 * 500)) < 1e-6
                and "Occurrences2" in props)

            mark("p64: gabarits de pièce")
            import os
            import tempfile
            saved_dir = os.environ.get("FREESOLID_DATA_DIR")
            os.environ["FREESOLID_DATA_DIR"] = tempfile.mkdtemp(
                prefix="freesolid-gabarits-")
            try:
                self.new_part("Pièce gabarit")
                self.add_rect_sketch(30, 20)
                self.add_pad(4)
                self.set_body_material(self._require_body().Name, "aluminium")
                listed = self.save_template("Tôle alu")["templates"]
                self.new_part("Autre")
                out = dispatch(self, "new_from_template",
                               {"name": "Tôle alu"})
                tree = out["result"]
                bad = False
                try:
                    self.save_template("../évasion")
                except KernelError:
                    bad = True
                report["p64_gabarits"] = (
                    listed == ["Tôle alu"]
                    and len(tree["features"]) == 1
                    and tree["bodies"][0]["material"]["id"] == "aluminium"
                    and bad and not self._modified)
            finally:
                if saved_dir is None:
                    os.environ.pop("FREESOLID_DATA_DIR", None)
                else:
                    os.environ["FREESOLID_DATA_DIR"] = saved_dir

            esquisse.p65_contrainte_rapide(self, mark, report, etat)

            mark("p66: dossiers, parents et enfants")
            self.new_part("Pièce rangée")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            pad = self.get_tree()["features"][-1]
            self.add_fillet(2, edges=[0])
            fillet = self.get_tree()["features"][-1]["name"]
            tree = self.set_folder([pad["name"], fillet], "Base")
            folders = [f.get("folder") for f in tree["features"]]
            rel = self.feature_relations(pad["name"])
            renamed = self.rename_folder("Base", "Socle")
            gone = self.rename_folder("Socle", "")
            report["p66_dossiers"] = (
                folders == ["Base", "Base"]
                and [p["name"] for p in rel["parents"]]
                == [pad["children"][0]["name"]]
                and [c["name"] for c in rel["children"]] == [fillet]
                and renamed["features"][0].get("folder") == "Socle"
                and "folder" not in gone["features"][0])

            mark("p67: tirer la face du bout")
            self.new_part("Pièce tirée")
            self.add_rect_sketch(40, 30)
            self.add_pad(20)
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if f.normalAt(0, 0).z > 0.9)
            side = next(i for i, f in enumerate(body.Shape.Faces)
                        if abs(f.normalAt(0, 0).z) < 0.1)
            cap = self.face_drag_info(top)["drag"]
            wall = self.face_drag_info(side)["drag"]
            self.add_rect_sketch(10, 10, face=top)
            self.add_pocket(5)
            floor = next(i for i, f in enumerate(body.Shape.Faces)
                         if f.normalAt(0, 0).z > 0.9
                         and abs(f.CenterOfMass.z - 15) < 1e-6)
            hole = self.face_drag_info(floor)["drag"]
            report["p67_tirer_face"] = (
                cap is not None and cap["factor"] == 1 and cap["value"] == 20
                and wall is None
                and hole is not None and hole["factor"] == -1
                and abs(hole["value"] - 5) < 1e-9)

            mark("p68: configurations")
            import math
            self.new_part("Pièce configurée")
            self.add_rect_sketch(20, 10)
            self.add_pad(10)
            body = self._require_body()
            pad = self.get_tree()["features"][-1]["name"]
            st = self.sketch_start(plane="XY")
            self.sketch_add_circle(st["sketch"], 0, 0, 2)
            self.sketch_finish(st["sketch"])
            self.add_pocket(through=True, reversed=True,
                            sketch=st["sketch"])
            fillet = self.get_tree()["features"][-1]["name"]  # le trou
            self.add_configuration("Court")
            self.add_configuration("Long")
            self.set_params(pad, {"Length": 30})
            self.set_suppressed([fillet])
            long_volume = body.Shape.Volume
            self.activate_configuration("Court")
            short_volume = body.Shape.Volume
            short_fillet = self._require_doc().getObject(fillet).Suppressed
            tree = self.activate_configuration("Long")
            table = self.configuration_table()
            depth = next(r for r in table["rows"]
                         if r["key"] == "prop:%s.Length" % pad)
            self.set_configuration_values({"Court": {depth["key"]: 15}})
            court_after = self.configuration_table()
            report["p68_tableau"] = (
                depth["values"] == {"Court": 10.0, "Long": 30.0}
                and next(r for r in court_after["rows"]
                         if r["key"] == depth["key"])["values"]["Court"]
                == 15.0
                and abs(body.Shape.Volume - long_volume) < 1e-6)
            report["p68_configurations"] = (
                abs(long_volume - 20 * 10 * 30) < 1e-6
                and abs(short_volume - (2000 - math.pi * 4 * 10)) < 1e-6
                and not short_fillet
                and abs(body.Shape.Volume - long_volume) < 1e-6
                and tree["configurations"] == {"active": "Long",
                                               "names": ["Court", "Long"]})

            surfaces.p69_spline_3d_poignees_poles(self, mark, report, etat)

            esquisse.p70_esquisse_3d(self, mark, report, etat)

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
