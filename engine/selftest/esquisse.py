"""Selftest — esquisse 2D et 3D : tracés, relations, cotes, outils d'édition.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import math

from engine.kernel import KernelError


def m2_rectangle_ligne_a_ligne(self, mark, report, etat):
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
    etat.name = name


def m2_drag_suivi_solveur(self, mark, report, etat):
    name = etat.name  # posé par esquisse.m2_rectangle_ligne_a_ligne
    mark("m2: drag suivi par le solveur")
    self.sketch_move(name, 1, 2, 85, 45)


def m2_cote_pilotante(self, mark, report, etat):
    name = etat.name  # posé par esquisse.m2_rectangle_ligne_a_ligne
    mark("m2: cote pilotante à 90")
    state = self.sketch_dim(name, 0)
    dim = max(d["id"] for d in state["dims"])
    state = self.sketch_set_dim(name, dim, 90)
    report["m2_dim_drives"] = any(
        abs(d["value"] - 90) < 1e-6 for d in state["dims"])
    report["m2_dof"] = state["dof"]


def m2_extrusion_profil_dessine(self, mark, report, etat):
    name = etat.name  # posé par esquisse.m2_rectangle_ligne_a_ligne
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


def p1_geometrie_construction(self, mark, report, etat):
    sk_name = etat.sk_name  # posé par document.p1_annuler_retablir
    mark("p1: géométrie de construction")
    state = self.sketch_toggle_construction(sk_name, 0)
    report["p1_construction_ok"] = bool(
        state["entities"][0].get("construction"))
    self.sketch_finish(sk_name)


def p1_esquisse_plan_nomme(self, mark, report, etat):
    mark("p1: esquisse sur plan nommé (XZ = Plan de face)")
    state = self.sketch_start(plane="XZ")
    identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    report["p1_plane_ok"] = (
        [round(v, 6) for v in state["placement"]] != identity)
    self.sketch_finish(state["sketch"])


def p7_relations(self, mark, report, etat):
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
    etat.rel = rel


def p7_lister_supprimer_relation(self, mark, report, etat):
    rel = etat.rel  # posé par esquisse.p7_relations
    mark("p7: lister et supprimer une relation")
    listed = self.sketch_constraints(rel, geo=2)
    report["p7_list_count"] = len(listed["constraints"])
    before = len(self._get_sketch(rel).Constraints)
    self.sketch_delete_constraint(
        rel, listed["constraints"][-1]["id"])
    report["p7_delete_constraint_ok"] = (
        len(self._get_sketch(rel).Constraints) == before - 1)
    self.sketch_finish(rel)


def p14_convertir_entites(self, mark, report, etat):
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


def p17_spline_ellipse_decalage(self, mark, report, etat):
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


def p3_arc_rainure_polygone(self, mark, report, etat):
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


def p3_conge_esquisse(self, mark, report, etat):
    mark("p3: congé d'esquisse")
    state = self.sketch_start()
    fil = state["sketch"]
    self.sketch_add_line(fil, 0, 0, 40, 0)
    self.sketch_add_line(fil, 40, 0, 40, 30)
    state = self.sketch_fillet(fil, 0, 1, 30, 0, 40, 20, 5)
    report["p3_sketch_fillet_ok"] = any(
        e["type"] == "arc" for e in state["entities"])
    self.sketch_finish(fil)


def p3_ajuster_trim(self, mark, report, etat):
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


def p3_contraintes_manuelles(self, mark, report, etat):
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


def p40_profil_attache_origine(self, mark, report, etat):
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


def p42_rectangle_par_centre(self, mark, report, etat):
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


def p51_esquisse_traces_complementaires(self, mark, report, etat):
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


def p51_esquisse_outils_edition(self, mark, report, etat):
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


def p51_esquisse_relations_cotes(self, mark, report, etat):
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


def p51_esquisse_references_liees(self, mark, report, etat):
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


def p51_esquisse_texte_coin_equation(self, mark, report, etat):
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


def p52_esquisse_partagee(self, mark, report, etat):
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


def p52_calques_esquisse(self, mark, report, etat):
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


def p56_changer_plan_esquisse(self, mark, report, etat):
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


def p65_contrainte_rapide(self, mark, report, etat):
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


def p70_esquisse_3d(self, mark, report, etat):
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
