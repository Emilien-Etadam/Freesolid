"""Selftest de bout en bout, hors du code de production.

``Kernel`` en hérite. Les étapes sont rangées par domaine dans ce paquet
(``document``, ``fonctions``, ``esquisse``, ``surfaces``, ``noeuds``,
``assemblage``, ``mise_en_plan``) : une fonction par étape, appelée avec
le noyau, ``mark``, ``report`` et ``etat``.

La table ``_etapes()`` fixe l'ordre d'exécution, et il compte : une
étape reprend souvent la pièce, l'arbre ou une aide qu'une précédente a
posés dans ``etat`` — chaque lecture dit quelle étape l'a posée. Les
modules d'étapes sont importés au début de l'appel, pour ne pas charger
ce paquet avec ``kernel.py`` au démarrage du serveur.
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
        from engine.kernel import (
            KernelError,
            _explain,
            selftest_summary,
        )
        etapes = _etapes()
        report = {"steps": []}

        def mark(name):
            report["steps"].append(name)
            print("selftest> {}".format(name), flush=True)

        etat = SimpleNamespace()
        try:
            for etape in etapes:
                etape(self, mark, report, etat)
            report["bilan"] = selftest_summary(report)
            return report
        except KernelError as exc:
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], exc))
        except Exception as exc:  # noqa: BLE001 - name the step, always
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], _explain(exc)))


def _etapes():
    """Les étapes dans l'ordre d'exécution, celles des plugins comprises."""
    from engine.selftest import (
        assemblage,
        document,
        esquisse,
        fonctions,
        mise_en_plan,
        noeuds,
        surfaces,
    )
    return (
        document.ping,
        fonctions.m0_piece_esquisse_bossage,
        fonctions.m0_reparametrage,
        fonctions.m1_enlevement_et_conge,
        document.m1_5_barre_de_retour,
        document.m1_5_enregistrer_rouvrir,
        esquisse.m2_rectangle_ligne_a_ligne,
        esquisse.m2_drag_suivi_solveur,
        esquisse.m2_cote_pilotante,
        esquisse.m2_extrusion_profil_dessine,
        document.p1_annuler_retablir,
        esquisse.p1_geometrie_construction,
        esquisse.p1_esquisse_plan_nomme,
        document.p1_export_stl_step,
        fonctions.p2_revolution_tube,
        fonctions.p2_revolution_autour_ligne_construction,
        fonctions.p2_symetrie_repetition_lineaire,
        fonctions.p2_repetition_circulaire,
        fonctions.p2_depouille_coque,
        fonctions.p4_apercu_jaune,
        fonctions.p4b_chanfrein,
        fonctions.p5_conge_aretes,
        fonctions.q1_conge_coque_trop_grands,
        fonctions.q2_conge_cylindre_affleurant,
        fonctions.p6_assistant_percage,
        document.p6_renommer_edition_atomique,
        document.p7_cote_nommee_variable_equation,
        document.p7_expression_sur_fonction,
        esquisse.p7_relations,
        esquisse.p7_lister_supprimer_relation,
        fonctions.p8_plan_decale_lissage,
        fonctions.p8_balayage,
        fonctions.p8_helice_ressort,
        fonctions.p9_multi_corps_combiner,
        assemblage.p10_deux_instances,
        assemblage.p10_contrainte_fixe,
        assemblage.p16_interferences,
        document.p11_evaluer_mesurer,
        assemblage.spike_solveur_assemblage,
        surfaces.p12_extrusion_couture_epaississement,
        surfaces.p12_courbe_3d_balayage,
        surfaces.p30_barre_retour_surfaces,
        mise_en_plan.p13_mise_en_plan_dxf,
        esquisse.p14_convertir_entites,
        fonctions.p15_gravure_texte,
        esquisse.p17_spline_ellipse_decalage,
        document.p18_import_step_export_3mf,
        document.p18_lecture_opensw,
        esquisse.p3_arc_rainure_polygone,
        esquisse.p3_conge_esquisse,
        esquisse.p3_ajuster_trim,
        esquisse.p3_contraintes_manuelles,
        document.cycle_de_vie_open_part,
        document.p31_gardes,
        fonctions.p31_verites_geometriques,
        document.p31_aller_retour_complet,
        document.p31_aller_retour_step,
        document.p31_annuler_en_chaine,
        document.p31_piece_vitrine,
        document.p32_refus_atomique_virgule_gravure,
        noeuds.n1_aretes_de_dependance,
        noeuds.n4_fonction_graphe,
        noeuds.n8_noeud_python,
        noeuds.n7_sous_elements_esquisse_attachee,
        noeuds.n9_repetition_groupe_fonctions,
        noeuds.n9_spike_rejeu_variable,
        noeuds.n10_repetition_variable,
        noeuds.n10_reedition,
        noeuds.n10_proprete,
        noeuds.n10_garde_topologique,
        noeuds.n10b_graphe_pilote,
        noeuds.n10b_seul_point_verite,
        noeuds.n10b_chaine_cotes,
        noeuds.n10b_garde_attache,
        noeuds.n11_helice_graphe_balayage,
        noeuds.n11_neuf_noeuds,
        noeuds.n11_ligne_appariement_refus,
        noeuds.n11b_libelle_courbe_surface,
        fonctions.p19_paroi_mince,
        fonctions.p38_coque_plusieurs_faces,
        esquisse.p40_profil_attache_origine,
        esquisse.p42_rectangle_par_centre,
        document.p43_aretes_de_couture,
        fonctions.p44_trou_place_par_cote,
        fonctions.p45_apercu_plan_reference,
        surfaces.p46_spline_3d_reeditable,
        surfaces.p46_remplissage_plane_decalee,
        surfaces.p47_couper_solide_surface,
        surfaces.p48_frontiere_reglee_composite,
        surfaces.p48_supprimer_faces_desajuster,
        surfaces.p49_supprimer_face_solide,
        surfaces.p49_remplacer_face_solide,
        surfaces.p50_courbe_helice_ressort,
        surfaces.p50_surface_radiee,
        surfaces.p50_surface_mediane_paroi,
        surfaces.p50_aplatir_surface_forme_libre,
        surfaces.p50_epaissir_en_enlevant,
        fonctions.p41_percage_centres_cliques,
        esquisse.p51_esquisse_traces_complementaires,
        esquisse.p51_esquisse_outils_edition,
        esquisse.p51_esquisse_relations_cotes,
        esquisse.p51_esquisse_references_liees,
        esquisse.p51_esquisse_texte_coin_equation,
        esquisse.p52_esquisse_partagee,
        esquisse.p52_calques_esquisse,
        document.p53_commentaires_proprietes_historique,
        document.p54_masquer_corps_surface,
        document.p55_desactiver_fonction,
        esquisse.p56_changer_plan_esquisse,
        fonctions.p57_chanfrein_sommet,
        fonctions.p58_chaine_tangente_boucle,
        document.p59_matieres_couleur_face,
        document.p60_liste_erreurs,
        fonctions.p61_axe_point_repere,
        document.p62_copier_coller_fonction,
        fonctions.p63_repetition_deux_directions,
        document.p64_gabarits_piece,
        esquisse.p65_contrainte_rapide,
        document.p66_dossiers_parents_enfants,
        fonctions.p67_tirer_face_bout,
        document.p68_configurations,
        surfaces.p69_spline_3d_poignees_poles,
        esquisse.p70_esquisse_3d,
        fonctions.p19b_paroi_mince_extremites_fermees,
        document.p71_genres_neutres,
        document.p72_maillage_identique,
        document.p73_cotes_neutres,
        esquisse.p74_accrochages_esquisse,
        esquisse.p75_accrochages_points_remarquables,
        esquisse.p76_accrochages_directions,
        esquisse.p77_glisser_accroche,
        esquisse.p78_accroche_piece,
        esquisse.p79_annuler_esquisse,
        esquisse.p80_glisser_courbe_entiere,
        document.p81_proprietes_document,
        _etapes_des_plugins,
        document.bilan,
        document.n4e_evaluer_apres_ouverture,
    )


def _etapes_des_plugins(self, mark, report, etat):
    """Après les étapes du noyau, avant le bilan qui rouvre la vitrine."""
    self._plugins.run_selftest(self, mark, report)
