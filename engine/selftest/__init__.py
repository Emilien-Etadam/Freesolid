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
        from engine.selftest import assemblage, mise_en_plan, noeuds, surfaces
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

            mark("p51: esquisse — tracés complémentaires")
            import math
            self.new_part("Pièce tracés")
            st = self.sketch_start(plane="XY")
            sk_name = st["sketch"]
            self.sketch_add_point(sk_name, 5, 5)
            self.sketch_add_line(sk_name, -30, 0, -30, 30, construction=True)
            self.sketch_add_line(sk_name, 0, 0, 20, 0)
            line_id = len(self.sketch_state(sk_name)["entities"]) - 1
            state = self.sketch_add_tangent_arc(sk_name, line_id, 2, 20, 20)
            arc = state["entities"][-1]
            tangent_ok = any(c["type"] == "Tangent" and line_id in c["geos"]
                             for c in state["constraints"])
            state = self.sketch_add_ellipse_arc(sk_name, 60, 0, 10, 5, 0,
                                                math.pi / 2)
            ell = state["entities"][-1]
            state = self.sketch_add_parabola(sk_name, 0, 50, 0, 55,
                                             -10, 60, 10, 60)
            par = state["entities"][-1]["points"]
            state = self.sketch_add_conic(sk_name, 40, 40, 60, 40, 50, 50,
                                          rho=0.4)
            con = state["entities"][-1]["points"]
            state = self.sketch_add_spline_poles(
                sk_name, [[80, 0], [90, 10], [100, 0], [110, 10]])
            spl = state["entities"][-1]
            ents = state["entities"]
            report["p51_traces"] = (
                ents[0]["type"] == "point"
                and ents[1]["construction"] is True
                and arc["type"] == "arc" and abs(arc["r"] - 10) < 1e-6
                and tangent_ok
                and ell.get("kind") == "ellipse"
                and abs(ell["points"][0][0] - 70) < 1e-6
                and abs(ell["points"][-1][1] - 5) < 1e-6
                and sorted(round(p[0], 6) for p in (par[0], par[-1]))
                == [-10, 10] and abs(par[0][1] - 55) < 1e-6
                and abs(con[0][0] - 40) < 1e-6 and abs(con[-1][0] - 60) < 1e-6
                and spl.get("kind") == "spline" and spl.get("npoints") == 4
                and state["definition"] != "over")
            self.sketch_finish(sk_name)
            # Contours fermés extrudés : l'aire dit que la forme est juste.
            areas = {}
            for key, draw in (
                    ("rect3", lambda n: self.sketch_add_rect3(
                        n, 0, 0, 30, 40, 14, 52)),
                    ("para", lambda n: self.sketch_add_rect3(
                        n, 0, 0, 30, 0, 40, 20, parallelogram=True)),
                    ("slot", lambda n: self.sketch_add_arc_slot(
                        n, 0, 0, 20, 0, math.pi / 2, 4))):
                self.new_part("Pièce " + key)
                st = self.sketch_start(plane="XY")
                draw(st["sketch"])
                definition = self.sketch_state(st["sketch"])["definition"]
                self.sketch_finish(st["sketch"])
                self.add_pad(5, sketch=st["sketch"])
                areas[key] = (self._require_body().Shape.Volume / 5,
                              definition)
            report["p51_contours"] = (
                abs(areas["rect3"][0] - 1000) < 1e-3
                and abs(areas["para"][0] - 600) < 1e-3
                and abs(areas["slot"][0] - 44 * math.pi) < 1e-3
                and all(d != "over" for _, d in areas.values()))

            mark("p51: esquisse — outils d'édition")
            import math
            self.new_part("Pièce édition")
            st = self.sketch_start(plane="XY")
            sk_name = st["sketch"]
            sko = self._get_sketch(sk_name)
            self.sketch_add_rectangle(sk_name, 0, 0, 40, 30)
            state = self.sketch_chamfer(sk_name, 0, 1, 35, 0, 40, 5, 5)
            bevel = state["entities"][-1]
            chamfer_ok = (bevel["type"] == "line"
                          and abs(math.dist(bevel["p1"], bevel["p2"])
                                  - 5 * math.sqrt(2)) < 1e-6
                          and state["definition"] != "over")
            self.sketch_add_line(sk_name, 0, 50, 10, 50)
            self.sketch_add_line(sk_name, 30, 40, 30, 70)
            lid = len(self.sketch_state(sk_name)["entities"]) - 2
            state = self.sketch_extend(sk_name, lid, 9, 50)
            extend_ok = state["entities"][lid]["p2"] == [30.0, 50.0]
            count = len(state["entities"])
            state = self.sketch_split(sk_name, lid + 1, 30, 55)
            split_ok = len(state["entities"]) == count + 1
            self.sketch_add_circle(sk_name, 60, 0, 5)
            cid = len(self.sketch_state(sk_name)["entities"]) - 1
            state = self.sketch_transform(sk_name, [cid], dx=10)
            move_ok = state["entities"][cid]["c"] == [70.0, 0.0]
            state = self.sketch_transform(sk_name, [cid], angle=90, copy=True)
            rot = state["entities"][-1]["c"]
            state = self.sketch_polar_array(sk_name, [cid], 0, 0, 4)
            polar = [e["c"] for e in state["entities"][-3:]]
            state = self.sketch_transform(sk_name, [cid], scale=2, cx=70,
                                          cy=0)
            scaled = state["entities"][-1]
            report["p51_edition"] = (
                chamfer_ok and extend_ok and split_ok and move_ok
                and abs(rot[0]) < 1e-6 and abs(rot[1] - 70) < 1e-6
                and abs(polar[1][0] + 70) < 1e-6
                and scaled["type"] == "circle" and abs(scaled["r"] - 10) < 1e-6
                and not list(sko.ConflictingConstraints)
                and not list(sko.RedundantConstraints))
            self.sketch_finish(sk_name)

            mark("p51: esquisse — relations et cotes")
            import math
            self.new_part("Pièce relations")
            st = self.sketch_start(plane="XY")
            sk_name = st["sketch"]
            sko = self._get_sketch(sk_name)
            self.sketch_add_line(sk_name, 0, 0, 40, 0)
            self.sketch_add_line(sk_name, 0, 0, 30, 30)
            self.sketch_add_point(sk_name, 20, 5)
            # Point sur la première ligne, puis à l'intersection des deux.
            self.sketch_constrain(sk_name, "onobject", 2, point1=1, geo2=0)
            on_line = abs(self.sketch_state(sk_name)["entities"][2]["p1"][1]) < 1e-6
            self.sketch_add_point(sk_name, 3, 4)
            state = self.sketch_constrain(sk_name, "intersection", 3,
                                          point1=1, geo2=0, geo3=1)
            crossing = state["entities"][3]["p1"]
            self.sketch_add_circle(sk_name, 80, 0, 5)
            self.sketch_add_circle(sk_name, 90, 10, 8)
            state = self.sketch_constrain(sk_name, "coradial", 4, geo2=5)
            c4, c5 = state["entities"][4], state["entities"][5]
            coradial_ok = (abs(c4["r"] - c5["r"]) < 1e-6
                           and math.dist(c4["c"], c5["c"]) < 1e-6)
            # Cotes : longueur d'arc, angle à l'axe, diamètre d'arc,
            # ordonnée, puis une cote de référence qui ne pilote plus.
            self.sketch_add_arc(sk_name, 0, 60, 10, 0, math.pi / 2)
            arc_id = len(self.sketch_state(sk_name)["entities"]) - 1
            state = self.sketch_dim(sk_name, arc_id, value=20,
                                    measure="arc_length")
            arc = state["entities"][arc_id]
            a1 = math.atan2(arc["p1"][1] - arc["c"][1], arc["p1"][0] - arc["c"][0])
            a2 = math.atan2(arc["p2"][1] - arc["c"][1], arc["p2"][0] - arc["c"][0])
            sweep = (a2 - a1) % (2 * math.pi)
            arc_len_ok = (abs(arc["r"] * sweep - 20) < 1e-4
                          and state["dims"][-1]["kind"] == "arc_length")
            state = self.sketch_dim(sk_name, 1, value=math.radians(30),
                                    measure="axis_angle")
            l1 = state["entities"][1]
            axis_ok = abs(math.degrees(math.atan2(
                l1["p2"][1] - l1["p1"][1], l1["p2"][0] - l1["p1"][0])) - 30) < 1e-6
            state = self.sketch_dim(sk_name, arc_id, value=30,
                                    measure="diameter")
            dia_ok = abs(state["entities"][arc_id]["r"] - 15) < 1e-6
            state = self.sketch_dim(sk_name, 0, point=1, geo2=0, point2=2,
                                    axis="x")
            ordinate = state["dims"][-1]
            state = self.sketch_set_dim(sk_name, ordinate["id"],
                                        driving=False)
            driven = next(d for d in state["dims"]
                          if d["id"] == ordinate["id"])
            report["p51_relations_cotes"] = (
                on_line and abs(crossing[0]) < 1e-6 and abs(crossing[1]) < 1e-6
                and coradial_ok and arc_len_ok and axis_ok and dia_ok
                and ordinate["type"] == "DistanceX"
                and driven["driving"] is False
                and not list(sko.ConflictingConstraints)
                and not list(sko.RedundantConstraints))
            self.sketch_finish(sk_name)

            mark("p51: esquisse — références liées à la pièce")
            self.new_part("Pièce références")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            body = self._require_body()
            top = next(i for i, f in enumerate(body.Shape.Faces)
                       if abs(f.CenterOfMass.z - 10) < 1e-6)
            st = self.sketch_start(face=top)
            ref_sk = st["sketch"]
            state = self.sketch_reference(ref_sk, mode="edges")
            refs = [e for e in state["entities"] if e.get("external")]
            self.sketch_finish(ref_sk)
            # Le contour lié suit la pièce : le profil de base passe à 50.
            base_sk = next(o for o in body.Group
                           if o.TypeId == "Sketcher::SketchObject")
            width = next(i for i, c in enumerate(base_sk.Constraints)
                         if c.Type in ("DistanceX", "Distance")
                         and abs(c.Value - 40) < 1e-6)
            base_sk.setDatum(width, 50)
            self._recompute()
            state = self.sketch_state(ref_sk)
            xs = [abs(p[0]) for e in state["entities"] if e.get("external")
                  for p in (e["p1"], e["p2"])]
            follows = abs(max(xs) - 25) < 1e-6
            st = self.sketch_start(plane="XZ")
            cut_sk = st["sketch"]
            inter = self.sketch_reference(cut_sk, mode="intersection")
            self.sketch_finish(cut_sk)
            self.curve_helix(5, 20, 10)
            st = self.sketch_start(plane="XY")
            pierce_sk = st["sketch"]
            pierced = self.sketch_reference(pierce_sk, mode="pierce")
            pts = [e for e in pierced["entities"] if e.get("external")]
            state = self.sketch_delete_geo(pierce_sk, pts[0]["id"])
            self.sketch_finish(pierce_sk)
            st = self.sketch_start(plane="XZ")
            sil = self.sketch_silhouette(st["sketch"])
            sil_pts = [p for e in sil["entities"] if e["type"] == "line"
                       for p in (e["p1"], e["p2"])]
            silhouette_ok = (abs(max(p[0] for p in sil_pts)
                                 - min(p[0] for p in sil_pts) - 50) < 1e-6
                             and abs(max(p[1] for p in sil_pts) - 10) < 1e-6)
            self.sketch_finish(st["sketch"])
            report["p51_references"] = (
                silhouette_ok
                and len(refs) == 4 and follows and inter["referenced"] == 4
                and pierced["referenced"] >= 1 and pts[0]["type"] == "point"
                and not any(e.get("external") for e in state["entities"])
                and "Percee" not in [f["label"] for f
                                     in self.get_tree()["features"]])

            mark("p51: esquisse — texte, coin, équation, blocs, définition")
            import math
            self.new_part("Pièce compléments")
            st = self.sketch_start(plane="XY")
            sk_name = st["sketch"]
            sko = self._get_sketch(sk_name)
            state = self.sketch_add_text(sk_name, "Ab", 0, 50, 10)
            text_ok = len(state["entities"]) > 4 and all(
                any(c["type"] == "Block" and c["geos"][0] == e["id"]
                    for c in state["constraints"]) for e in state["entities"])
            self.sketch_add_line(sk_name, 0, 0, 20, 0)
            self.sketch_add_line(sk_name, 30, 5, 30, 30)
            nb = len(self.sketch_state(sk_name)["entities"])
            state = self.sketch_corner(sk_name, nb - 2, nb - 1, 10, 0, 30, 20)
            corner_ok = (state["entities"][nb - 2]["p2"] == [30.0, 0.0]
                         and state["entities"][nb - 1]["p1"] == [30.0, 0.0])
            state = self.sketch_add_equation(sk_name, "t", "10*sin(t)", 0,
                                             2 * math.pi)
            wave = state["entities"][-1]["points"]
            equation_ok = (abs(max(p[1] for p in wave) - 10) < 0.5
                           and abs(wave[-1][0] - 2 * math.pi) < 1e-6)
            try:
                self.sketch_add_equation(sk_name, "t", "__import__('os')", 0, 1)
                equation_ok = False
            except KernelError:
                pass
            self.sketch_add_circle(sk_name, 80, 0, 5)
            cid = len(self.sketch_state(sk_name)["entities"]) - 1
            self.sketch_spline(sk_name, cid, "convert")
            state = self.sketch_spline(sk_name, cid, "degree")
            spline_ok = state["entities"][cid].get("kind") == "spline"
            self.sketch_block_save(sk_name, [cid], "rond")
            count = len(self.sketch_state(sk_name)["entities"])
            state = self.sketch_block_insert(sk_name, "rond", 100, 0, scale=2)
            inserted = state["entities"][-1]
            block_ok = (len(state["entities"]) == count + 1
                        and abs(max(p[0] for p in inserted["points"]) - 110)
                        < 0.2)
            self.sketch_picture(sk_name, {"data": "data:image/png;base64,AA",
                                          "x": 1, "y": 2, "width": 50})
            picture_ok = self.sketch_picture(sk_name)["picture"]["width"] == 50
            self.sketch_finish(sk_name)
            st = self.sketch_start(plane="XY")
            def_sk = st["sketch"]
            self.sketch_add_rectangle(def_sk, 10, 10, 50, 40)
            self.sketch_add_circle(def_sk, 30, 25, 5)
            defined = self.sketch_fully_define(def_sk)
            self.sketch_add_line(def_sk, 60, 0, 70, 0)
            self.sketch_add_line(def_sk, 70.0005, 0, 80, 10)
            repaired = self.sketch_repair(def_sk)
            self.sketch_finish(def_sk)
            st = self.sketch_start(plane="XY")
            g2_sk = st["sketch"]
            self.sketch_add_spline_poles(g2_sk, [[0, 0], [10, 10], [20, 10],
                                                 [30, 0]])
            self.sketch_add_spline_poles(g2_sk, [[30, 0], [40, -5], [50, 5],
                                                 [60, 0]])
            self.sketch_match_curvature(g2_sk, 0, 2, 1, 1)
            g2o = self._get_sketch(g2_sk)
            sa, sb = g2o.Geometry[0], g2o.Geometry[1]
            g2_ok = (abs(self._signed_curvature(sa, sa.LastParameter)
                         - self._signed_curvature(sb, sb.FirstParameter))
                     < 1e-6
                     and (sa.value(sa.LastParameter)
                          - sb.value(sb.FirstParameter)).Length < 1e-7
                     and not list(g2o.ConflictingConstraints))
            self.sketch_finish(g2_sk)
            report["p51_complements"] = g2_ok and (
                text_ok and corner_ok and equation_ok and spline_ok
                and block_ok and picture_ok
                and defined["definition"] == "full" and defined["added"] == 7
                and repaired["repair"]["joined"] == 1
                and "Bloc" not in [f["label"] for f
                                   in self.get_tree()["features"]])

            mark("p52: esquisse partagée, contours choisis")
            import math
            self.new_part("Pièce partage")
            st = self.sketch_start(plane="XY")
            shared = st["sketch"]
            self.sketch_add_rectangle(shared, -20, -15, 20, 15)
            self.sketch_add_circle(shared, 0, 0, 5)
            self.sketch_add_circle(shared, 40, 0, 4)
            self.sketch_finish(shared)
            body = self._require_body()
            self.add_pad(10, sketch=shared, contours=[0, 1])
            plate = body.Shape.Volume
            self.add_pad(20, sketch=shared, contours=[2])
            boss = body.Shape.Volume - plate
            tree = self.get_tree()
            pads = [f for f in tree["features"]
                    if f["type"] == "PartDesign::Pad"]
            under = [[c["name"] for c in f.get("children", [])] for f in pads]
            self.set_profile_contours(pads[0]["name"], [0])
            filled = body.Shape.Volume
            # L'esquisse change : les deux fonctions suivent.
            self.sketch_dim(shared, 5, value=12)  # le petit cercle : Ø 12
            self._recompute()
            grown = body.Shape.Volume
            report["p52_esquisse_partagee"] = (
                abs(plate - (40 * 30 * 10 - math.pi * 25 * 10)) < 1e-3
                and abs(boss - math.pi * 16 * 20) < 1e-3
                and under == [[shared], [shared]]
                and pads[0]["profile"]["used"] == [0, 1]
                and pads[1]["profile"]["used"] == [2]
                and abs(filled - (12000 + math.pi * 16 * 20)) < 1e-3
                and abs(grown - (12000 + math.pi * 36 * 20)) < 1e-3)

            mark("p52: calques d'esquisse")
            self.new_part("Pièce calques")
            st = self.sketch_start(plane="XY")
            lay = st["sketch"]
            self.sketch_add_line(lay, -30, 40, 30, 40)       # 0 : à supprimer
            self.sketch_add_rectangle(lay, -20, -15, 20, 15)  # 1..4
            self.sketch_add_line(lay, 0, -30, 0, 30, construction=True)
            self.sketch_layers(lay, [{"name": "Profil", "color": "#5288e0"},
                                     {"name": "Axes", "visible": False}])
            self.sketch_set_layer(lay, [1, 2, 3, 4], "Profil")
            self.sketch_set_layer(lay, [5], "Axes")
            # Une suppression décale les numéros : le calque suit l'entité.
            self.sketch_delete_geo(lay, 0)
            state = self.sketch_layers(lay, [
                {"name": "Contour", "color": "#5288e0", "rename": "Profil"},
                {"name": "Axes", "visible": False}])
            on = {e["id"]: e.get("layer", "") for e in state["entities"]}
            self.sketch_finish(lay)
            self.add_pad(5, sketch=lay)
            report["p52_calques"] = (
                on == {0: "Contour", 1: "Contour", 2: "Contour", 3: "Contour",
                       4: "Axes"}
                and [l["name"] for l in state["layers"]] == ["Contour", "Axes"]
                and state["layers"][1]["visible"] is False
                and abs(self._require_body().Shape.Volume - 40 * 30 * 5)
                < 1e-6)

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

            mark("p56: changer le plan d'une esquisse")
            self.new_part("Pièce replacée")
            st = self.sketch_start(plane="XY")
            moved = st["sketch"]
            self.sketch_add_rectangle(moved, -20, -15, 20, 15)
            self.sketch_finish(moved)
            self.add_pad(10, sketch=moved)
            body = self._require_body()
            flat = body.Shape.BoundBox
            self.sketch_set_plane(moved, plane="XZ")
            upright = body.Shape.BoundBox
            refused = False
            try:
                self.sketch_set_plane(moved, face=0)
            except KernelError:
                refused = True
            report["p56_plan_esquisse"] = (
                abs(flat.ZLength - 10) < 1e-6 and abs(flat.YLength - 30) < 1e-6
                and abs(upright.ZLength - 30) < 1e-6
                and abs(upright.YLength - 10) < 1e-6
                and abs(body.Shape.Volume - 40 * 30 * 10) < 1e-6
                and refused)

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

            mark("p65: contrainte rapide (type auto)")
            import os
            import tempfile
            self.new_part("Goupille")
            st = self.sketch_start(plane="XY")
            self.sketch_add_circle(st["sketch"], 0, 0, 4)
            self.sketch_finish(st["sketch"])
            self.add_pad(20)
            faces = self._require_body().Shape.Faces
            side = next(i for i, f in enumerate(faces)
                        if f.Surface.TypeId == "Part::GeomCylinder")
            flat = next(i for i, f in enumerate(faces)
                        if f.Surface.TypeId == "Part::GeomPlane")
            pin = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest-pin.FCStd")
            self.save_part(pin)
            self.new_assembly()
            self.insert_component(pin)
            tree = self.insert_component(pin)
            a, b = [c["name"] for c in tree["components"]]
            round_ = self.add_joint(a, b, type="auto",
                                    sub1="Face%d" % (side + 1),
                                    sub2="Face%d" % (side + 1))
            plain = self.add_joint(a, b, type="auto",
                                   sub1="Face%d" % (flat + 1),
                                   sub2="Face%d" % (flat + 1))
            types = [j["type"] for j in plain.get("joints", ())]
            report["p65_contrainte_rapide"] = (
                "Cylindrical" in [j["type"] for j in round_["joints"]]
                and "Distance" in types)

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

            mark("p70: esquisse 3D — lignes, spline, cotes, relations")
            self.new_part("Pièce esquisse 3D")
            App = self._app()
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            body = self._require_body()
            corner = next(v.Point for v in body.Shape.Vertexes
                          if v.Point.z > 9 and v.Point.x > 9
                          and v.Point.y > 9)
            line = lambda a, b: {"type": "line", "a": a, "b": b}
            spec = {
                "points": [[corner.x, corner.y, corner.z], [40, 11, 9],
                           [41, 10, 35], [41, 30, 36], [60, 40, 40]],
                "links": [True, None, None, None, None],
                "entities": [line(0, 1), line(1, 2),
                             {"type": "spline", "pts": [2, 3, 4]},
                             {"type": "point", "p": 4}],
                "relations": [{"type": "axis", "entity": 0, "axis": "X"},
                              {"type": "axis", "entity": 1, "axis": "Z"}],
                "dims": [{"type": "length", "entity": 0, "value": 30},
                         {"type": "length", "entity": 1, "value": 25}],
            }
            tree = self.add_sketch3d(spec)
            entry = tree["surfaces"][-1]
            obj = self._require_doc().getObject(entry["name"])
            stored = entry.get("sketch3d") or {}
            p0, p1, p2 = (App.Vector(*stored["points"][i]) for i in range(3))
            report["p70_esquisse3d"] = (
                stored["links"][0] is not None
                and (p0 - corner).Length < 1e-6
                and abs((p1 - p0).Length - 30) < 1e-6
                and abs(p1.y - p0.y) < 1e-6 and abs(p1.z - p0.z) < 1e-6
                and abs((p2 - p1).Length - 25) < 1e-6
                and abs(p2.x - p1.x) < 1e-6 and abs(p2.y - p1.y) < 1e-6
                and len(obj.Shape.Wires) == 1
                and len(obj.Shape.Edges) == 3
                and len(obj.Shape.Vertexes) >= 4)
            # La pièce grandit : le point lié suit, la chaîne avec lui.
            pad = self.get_tree()["features"][-1]["name"]
            self.set_params(pad, {"Length": 16})
            moved = self._sketch3d_spec(obj)["points"][0]
            # Une cote en conflit est refusée, l'esquisse reste telle quelle.
            bad = dict(stored, dims=stored["dims"] + [
                {"type": "length", "entity": 0, "value": 12}])
            try:
                self.edit_sketch3d(entry["name"], bad)
                refused = False
            except KernelError:
                refused = True
            # Balayage le long de l'esquisse 3D.
            st = self.sketch_start(plane="YZ")
            self.sketch_add_circle(st["sketch"], 0, 0, 1)
            self.sketch_finish(st["sketch"])
            swept = self.surface_sweep(st["sketch"], entry["name"])
            sweep_obj = self._require_doc().getObject(
                swept["surfaces"][-1]["name"])
            report["p70_suit_et_balaie"] = (
                abs(moved[2] - 16) < 1e-6 and refused
                and len(self._sketch3d_spec(obj)["dims"]) == 2
                and sweep_obj.Shape.Area > 0)

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
