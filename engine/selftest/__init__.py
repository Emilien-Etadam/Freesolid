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
        from engine.selftest import assemblage, esquisse, fonctions, mise_en_plan, noeuds, surfaces
        import tempfile
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

            fonctions.m0_piece_esquisse_bossage(self, mark, report, etat)

            fonctions.m0_reparametrage(self, mark, report, etat)

            fonctions.m1_enlevement_et_conge(self, mark, report, etat)
            tree = etat.tree

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

            fonctions.p2_revolution_tube(self, mark, report, etat)

            fonctions.p2_revolution_autour_ligne_construction(self, mark, report, etat)

            fonctions.p2_symetrie_repetition_lineaire(self, mark, report, etat)

            fonctions.p2_repetition_circulaire(self, mark, report, etat)

            fonctions.p2_depouille_coque(self, mark, report, etat)

            fonctions.p4_apercu_jaune(self, mark, report, etat)

            fonctions.p4b_chanfrein(self, mark, report, etat)

            fonctions.p5_conge_aretes(self, mark, report, etat)

            fonctions.q1_conge_coque_trop_grands(self, mark, report, etat)

            fonctions.p6_assistant_percage(self, mark, report, etat)
            tree = etat.tree

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

            fonctions.p8_plan_decale_lissage(self, mark, report, etat)

            fonctions.p8_balayage(self, mark, report, etat)

            fonctions.p8_helice_ressort(self, mark, report, etat)

            fonctions.p9_multi_corps_combiner(self, mark, report, etat)

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

            fonctions.p15_gravure_texte(self, mark, report, etat)

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

            etat._close = _close
            etat._volume = _volume
            fonctions.p31_verites_geometriques(self, mark, report, etat)

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

            fonctions.p19_paroi_mince(self, mark, report, etat)

            fonctions.p38_coque_plusieurs_faces(self, mark, report, etat)

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

            fonctions.p44_trou_place_par_cote(self, mark, report, etat)

            fonctions.p45_apercu_plan_reference(self, mark, report, etat)

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

            fonctions.p41_percage_centres_cliques(self, mark, report, etat)

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

            fonctions.p57_chanfrein_sommet(self, mark, report, etat)

            fonctions.p58_chaine_tangente_boucle(self, mark, report, etat)

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

            fonctions.p61_axe_point_repere(self, mark, report, etat)

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

            fonctions.p63_repetition_deux_directions(self, mark, report, etat)

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

            fonctions.p67_tirer_face_bout(self, mark, report, etat)

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

            fonctions.p19b_paroi_mince_extremites_fermees(self, mark, report, etat)

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
