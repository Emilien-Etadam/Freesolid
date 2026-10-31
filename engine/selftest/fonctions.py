"""Selftest — fonctions volumiques : extrusions, révolutions, habillage,
répétitions, perçage, références.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import math
import os

from engine.kernel import KernelError


def m0_piece_esquisse_bossage(self, mark, report, etat):
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
    etat.mesh = mesh
    etat.tree = tree


def m0_reparametrage(self, mark, report, etat):
    mesh = etat.mesh  # posé par fonctions.m0_piece_esquisse_bossage
    tree = etat.tree  # posé par fonctions.m0_piece_esquisse_bossage
    mark("m0: reparamétrage 10 → 25")
    pad = next(f["name"] for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    self.set_param(pad, "Length", 25.0)
    report["m0_reparam_ok"] = self.tessellate() != mesh


def m1_enlevement_et_conge(self, mark, report, etat):
    mark("m1: esquisse sur face + enlèvement à travers tout + congé")
    top = self._top_face_id()
    report["m1_top_face"] = top
    self.add_rect_sketch(40, 20, face=top)
    self.add_pocket(through=True)
    report["m1_pocket_faces"] = len(self.tessellate()["groups"])
    tree = self.add_fillet(3, face=self._top_face_id())
    report["m1_fillet_ok"] = not any(
        f["error"] for f in tree["features"])
    etat.tree = tree


def p2_revolution_tube(self, mark, report, etat):
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


def p2_revolution_autour_ligne_construction(self, mark, report, etat):
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


def p2_symetrie_repetition_lineaire(self, mark, report, etat):
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


def p2_repetition_circulaire(self, mark, report, etat):
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


def p2_depouille_coque(self, mark, report, etat):
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
    # La capture du rejeu (répétition variable) relit le plan neutre.
    from engine.replay import capture_group
    draft = next(f["name"] for f in tree["features"]
                 if f["type"] == "PartDesign::Draft")
    captured = capture_group(self, [draft])["features"][0]
    report["p2_draft_neutral_capture"] = captured.get("neutral") == "XZ"
    self.new_part("Pièce coque")
    self.add_rect_sketch(40, 40)
    self.add_pad(20)
    tree = self.add_draft(face=self._side_face_id(), angle=5)
    report["p2_draft_ok"] = not any(
        f["error"] for f in tree["features"])
    tree = self.add_thickness(self._top_face_id(), 2)
    report["p2_thickness_ok"] = not any(
        f["error"] for f in tree["features"])


def p4_apercu_jaune(self, mark, report, etat):
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


def p4b_chanfrein(self, mark, report, etat):
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


def p5_conge_aretes(self, mark, report, etat):
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


def q1_conge_coque_trop_grands(self, mark, report, etat):
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


def _plaque_cylindre_affleurant(self, rayon):
    """Plaque en rainure conique (R12 en (0, 0), R25 en (70, 0), tangentes
    extérieures, 10 mm) et cylindre de rayon ``rayon`` centré en (70, 0),
    posé dessus (22 mm). Rend l'indice de l'arc commun au cylindre et au
    dessus de la plaque, côté plaque."""
    self.new_part("Pièce affleurante")
    sk = self.sketch_start(plane="XY")["sketch"]
    phi = math.acos((12.0 - 25.0) / 70.0)
    haut1 = (12 * math.cos(phi), 12 * math.sin(phi))
    haut2 = (70 + 25 * math.cos(phi), 25 * math.sin(phi))
    self.sketch_add_arc(sk, 70, 0, 25, -phi, phi)
    self.sketch_add_line(sk, haut2[0], haut2[1], haut1[0], haut1[1])
    self.sketch_add_arc(sk, 0, 0, 12, phi, 2 * math.pi - phi)
    self.sketch_add_line(sk, haut1[0], -haut1[1], haut2[0], -haut2[1])
    self.sketch_finish(sk)
    self.add_pad(10)
    sk = self.sketch_start(face=self._top_face_id())["sketch"]
    centre = self._get_sketch(sk).Placement.inverse().multVec(
        self._app().Vector(70, 0, 10))
    self.sketch_add_circle(sk, centre.x, centre.y, rayon)
    self.sketch_finish(sk)
    self.add_pad(22)
    for i, edge in enumerate(self._require_body().Shape.Edges):
        curve = edge.Curve
        milieu = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
        if (curve.TypeId == "Part::GeomCircle"
                and abs(curve.Radius - rayon) < 1e-9
                and abs(curve.Center.x - 70) < 1e-6
                and abs(curve.Center.z - 10) < 1e-6 and milieu.x < 70):
            return i
    raise KernelError("arc commun cylindre / plaque introuvable")


def q2_conge_cylindre_affleurant(self, mark, report, etat):
    mark("q2: congé sur un cylindre qui affleure")
    # Cylindre R25 au ras de l'arrondi R25 : le modeleur rend un congé « à
    # jour » de forme invalide. Il est refusé, avec l'indice.
    arete = _plaque_cylindre_affleurant(self, 25.0)
    body = self._require_body()
    pointe = body.Tip
    avant = [f["name"] for f in self.get_tree()["features"]]

    def refuse(appel):
        try:
            appel()
        except KernelError as exc:
            texte = str(exc)
            tree = self.get_tree()
            return ("pièce invalide" in texte
                    and "affleure exactement" in texte
                    and [f["name"] for f in tree["features"]] == avant
                    and not any(f.get("error") for f in tree["features"])
                    and body.Tip is pointe and body.Shape.isValid())
        return False

    report["q2_conge_affleurant_refuse"] = refuse(
        lambda: self.add_fillet(3, edges=[arete]))
    report["q2_chanfrein_affleurant_refuse"] = refuse(
        lambda: self.add_chamfer(3, edges=[arete]))
    report["q2_apercu_affleurant_refuse"] = refuse(
        lambda: self.preview("add_fillet", {"radius": 3, "edges": [arete]}))
    # Un congé cassé déjà là (fichier d'avant la garde) : la réédition de
    # son rayon est refusée et le rayon reste.
    conge = body.newObject("PartDesign::Fillet", "Fillet")
    conge.Base = (pointe, ["Edge{}".format(arete + 1)])
    conge.Radius = 3.0
    self._require_doc().recompute()
    try:
        self.set_params(conge.Name, {"Radius": 2})
        report["q2_reedition_affleurant_refusee"] = False
    except KernelError as exc:
        texte = str(exc)
        report["q2_reedition_affleurant_refusee"] = (
            "affleure exactement" in texte
            and "la pièce n'a pas été modifiée" in texte
            and abs(self._prop_float(conge, "Radius") - 3.0) < 1e-9)
    # Cylindre élargi de 0,001 mm : le même congé passe, forme valide.
    arete = _plaque_cylindre_affleurant(self, 25.001)
    body = self._require_body()
    volume = float(body.Shape.Volume)
    tree = self.add_fillet(3, edges=[arete])
    report["q2_conge_elargi_valide"] = (
        body.Tip.TypeId == "PartDesign::Fillet"
        and body.Tip.Shape.isValid()
        and float(body.Shape.Volume) > volume
        and not any(f.get("error") for f in tree["features"]))


def p6_assistant_percage(self, mark, report, etat):
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
    etat.tree = tree


def p8_plan_decale_lissage(self, mark, report, etat):
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


def p8_balayage(self, mark, report, etat):
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


def p8_helice_ressort(self, mark, report, etat):
    mark("p8: hélice (ressort)")
    self.new_part("Pièce hélice")
    state = self.sketch_start(plane="XZ")
    hel_sk = state["sketch"]
    self.sketch_add_circle(hel_sk, 15, 0, 2)
    self.sketch_finish(hel_sk)
    tree = self.add_helix(pitch=8, height=40, sketch=hel_sk)
    report["p8_helix_ok"] = not any(
        f["error"] for f in tree["features"])


def p9_multi_corps_combiner(self, mark, report, etat):
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
    mesh = self.tessellate()
    report["p9_others_shown"] = "others" in mesh
    # L'autre corps se dessine face par face, numéroté comme quand il
    # sera actif, arêtes comprises : le clic dans la vue l'active.
    other = next((b for b in mesh.get("other_bodies", ())
                  if b["name"] == first_body), {})
    first = self._doc.getObject(first_body)
    report["p9_autres_cliquables"] = (
        other.get("label") == first.Label
        and sorted(g["faceId"] for g in other.get("groups", ()))
        == list(range(len(first.Shape.Faces)))
        and bool(other.get("edges", {}).get("groups")))
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


def p15_gravure_texte(self, mark, report, etat):
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


def p31_verites_geometriques(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
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


def p19_paroi_mince(self, mark, report, etat):
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


def p38_coque_plusieurs_faces(self, mark, report, etat):
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


def p44_trou_place_par_cote(self, mark, report, etat):
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


def p45_apercu_plan_reference(self, mark, report, etat):
    mark("p45: aperçu du plan de référence, sans le créer")
    self.new_part("Pièce plan")
    before = len(self._require_doc().Objects)
    shown = self.preview("add_datum_plane",
                         {"base": "XY", "offset": 50})
    matrix = shown.get("plane") or []
    report["p45_apercu_plan"] = (
        len(matrix) == 16 and abs(matrix[11] - 50) < 1e-6
        and len(self._require_doc().Objects) == before)


def p41_percage_centres_cliques(self, mark, report, etat):
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


def p57_chanfrein_sommet(self, mark, report, etat):
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


def p58_chaine_tangente_boucle(self, mark, report, etat):
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


def p61_axe_point_repere(self, mark, report, etat):
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


def p63_repetition_deux_directions(self, mark, report, etat):
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


def p67_tirer_face_bout(self, mark, report, etat):
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
        and abs(hole["value"] - 5) < 1e-9
        and cap["key"] == hole["key"] == "length")

    # Réédition : la flèche au bout de la fonction, comme à la création.
    def near(drag, z, dz, factor):
        return (drag is not None and abs(drag["point"][2] - z) < 1e-6
                and abs(drag["normal"][2] - dz) < 1e-6
                and drag["factor"] == factor and drag["key"] == "length")
    sketch = self._doc.getObject(cap["feature"]).Profile[0].Name
    tip = self.feature_drag_info(cap["feature"])["drag"]
    dig = self.feature_drag_info(hole["feature"])["drag"]
    self.add_rect_sketch(10, 10)
    both = self.add_pad(8, midplane=True)["features"][-1]["name"]
    half = self.feature_drag_info(both)["drag"]
    under = next(i for i, f in enumerate(body.Shape.Faces)
                 if f.normalAt(0, 0).z < -0.9
                 and abs(f.CenterOfMass.z + 4) < 1e-6)
    pulled = self.face_drag_info(under)["drag"]
    report["p67_fleche_reedition"] = (
        near(tip, 20, 1, 1) and tip["value"] == 20
        and near(dig, 15, -1, 1) and near(half, 4, 1, 2)
        and self.feature_drag_info(sketch)["drag"] is None)
    # Plan milieu (SideType depuis FreeCAD 1.1) : sa face se tire aussi.
    report["p67_tirer_face_symetrique"] = (
        pulled is not None and pulled["factor"] == 2
        and pulled["value"] == 8)


def p19b_paroi_mince_extremites_fermees(self, mark, report, etat):
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


def _volumes(self):
    """Volume de chaque corps de la pièce (outils internes exclus)."""
    return {o.Name: o.Shape.Volume for o in self._doc.Objects
            if o.TypeId == "PartDesign::Body"
            and not self._is_internal_tool(o)}


def _centre_x(self, name):
    bb = self._doc.getObject(name).Shape.BoundBox
    return (bb.XMin + bb.XMax) / 2, (bb.YMin + bb.YMax) / 2


def p82_reseau_de_corps(self, mark, report, etat):
    mark("p82: réseau de corps — chaque occurrence est un corps")
    import tempfile
    self.new_part("Réseau de corps")
    self.add_rect_sketch(10, 10)
    self.add_pad(8)
    source = self._require_body().Name
    pad = self._require_body().Tip.Name
    self.add_body_pattern("linear", [source], length=20, count=3,
                          axis="X", spacing=True)
    host = self._body_pattern_hosts()[0]
    copies = [n for n in _volumes(self) if n != source]
    centres = sorted(round(_centre_x(self, n)[0], 6) for n in copies)
    report["p82_lineaire"] = (
        len(copies) == 2 and centres == [20.0, 40.0]
        and all(abs(v - 800) < 1e-6 for v in _volumes(self).values()))
    # Le réseau est une ligne de l'arbre de sa source ; ses copies
    # s'affichent arêtes comprises, et la source aussi quand une copie
    # est active.
    rows = [f for f in self.get_tree()["features"]
            if f["type_key"] == "body_pattern"]
    shown = {b["name"]: b for b in self.tessellate().get("other_bodies", [])}
    self.set_active_body(copies[0])
    from_copy = {b["name"]: b
                 for b in self.tessellate().get("other_bodies", [])}
    self.set_active_body(source)
    report["p82_ligne_et_vue"] = (
        len(rows) == 1 and rows[0]["name"] == host.Name
        and sorted(rows[0].get("copies") or ()) == sorted(
            self._doc.getObject(n).Label for n in copies)
        and all(shown.get(n, {}).get("edges", {}).get("indices")
                for n in copies)
        and all(from_copy.get(n, {}).get("groups")
                for n in (source, copies[1])))
    # La source ne se combine pas avec sa copie : la copie la suit, le
    # graphe bouclerait. Rien n'est ajouté.
    group = len(self._require_body().Group)
    try:
        self.add_boolean(tool=copies[0], type="fuse")
        looped = False
    except KernelError as exc:
        looped = "suit le corps actif" in str(exc)
    report["p82_refus_boucle"] = (
        looped and len(self._require_body().Group) == group
        and all(abs(v - 800) < 1e-6 for v in _volumes(self).values()))
    # La source change : les copies suivent ; la cote se réédite.
    self.set_active_body(source)
    top = self._top_face_id()
    self.add_rect_sketch(4, 4, face=top)
    self.add_pocket(2)
    self.set_params(host.Name, {"count": 4})
    volumes = _volumes(self)
    report["p82_suit_la_source"] = (
        len(volumes) == 4
        and all(abs(v - 768) < 1e-6 for v in volumes.values()))
    # Le réseau a son rang : l'enlèvement ajouté ensuite vient dessous.
    # La barre au-dessus de lui, ses copies n'existent pas encore ; posée
    # sur lui, elles reviennent, sans l'enlèvement.
    pocket = self._require_body().Tip.Name
    host_name = host.Name
    ranks = {f["name"]: f["order"] for f in self.get_tree()["features"]}
    grown = list(self._body_pattern_copies(host).values())
    hidden = {f["name"]: f.get("rolled_back")
              for f in self.set_tip(pad)["features"]}
    unborn = all(copy.Tip is None for copy in grown)
    shown = {f["name"]: f.get("rolled_back")
             for f in self.set_tip(host.Name)["features"]}
    back = _volumes(self)
    self.tip_to_end()
    # Une fonction sur une copie vient aussi sous le réseau, et y reste
    # quand on annule sa suppression (FreeCAD rend les objets en fin de
    # document).
    from engine.kernel import dispatch
    grown = [copy.Name for copy in grown]
    self.set_active_body(grown[0])
    self.add_fillet(radius=0.5, face=self._top_face_id())
    fillet = self._require_body().Tip.Name
    for op, params in (("set_tip", {"feature": pad}),
                       ("delete_rolled_back", {})):
        if not dispatch(self, op, params)["ok"]:
            raise KernelError(op)
    gone = all(self._doc.getObject(name) is None
               for name in grown + [fillet, host_name])
    self.undo()
    self.tip_to_end()
    self.set_active_body(source)
    host = self._doc.getObject(host_name)
    tree = self.get_tree()
    restored = {f["name"]: f["order"]
                for f in tree["features"] + tree["other_features"]}
    report["p82_reseau_a_son_rang"] = (
        ranks[pad] < ranks[host.Name] < ranks[pocket]
        and hidden.get(host.Name) is True and unborn
        and shown.get(host.Name) is False and shown.get(pocket) is True
        and len(back) == 4
        and all(abs(v - 800) < 1e-6 for v in back.values())
        and gone and restored[host_name] < restored.get(fillet, -1)
        and len(_volumes(self)) == 4)
    # Une copie supprimée reste sautée ; la source est protégée.
    far = max(copies, key=lambda n: _centre_x(self, n)[0])
    self.delete_feature(far)
    self.set_params(host.Name, {"length": 25})
    shifted = sorted(round(_centre_x(self, n)[0], 6)
                     for n in _volumes(self) if n != source)
    try:
        self.delete_feature(source)
        protected = False
    except KernelError:
        protected = True
    report["p82_copie_sautee"] = shifted == [25.0, 75.0] and protected
    # Symétrie d'une copie, réseau circulaire : d'autres corps encore.
    near = min((n for n in _volumes(self) if n != source),
               key=lambda n: _centre_x(self, n)[0])
    before = set(_volumes(self))
    self.add_body_pattern("mirror", [near], plane="YZ")
    mirrored = (set(_volumes(self)) - before).pop()
    before = set(_volumes(self))
    self.add_body_pattern("polar", [near], count=4, angle=360, axis="Z")
    turned = sorted((round(x, 6), round(y, 6)) for x, y in (
        _centre_x(self, n) for n in set(_volumes(self)) - before))
    report["p82_symetrie_circulaire"] = (
        abs(_centre_x(self, mirrored)[0] + 25) < 1e-6
        and turned == [(-25.0, 0.0), (0.0, -25.0), (0.0, 25.0)])
    # Rouvert : les mêmes volumes, objets FreeCAD standard.
    volumes = _volumes(self)
    path = os.path.join(tempfile.gettempdir(),
                        "freesolid-selftest-reseau-corps.FCStd")
    self.save_part(path)
    self.open_part(path)
    reopened = _volumes(self)
    report["p82_rouvert"] = (
        set(reopened) == set(volumes)
        and all(abs(reopened[n] - volumes[n]) < 1e-6 for n in volumes))


def p83_corps_concernes(self, mark, report, etat):
    mark("p83: corps concernés — les trous répétés creusent l'autre corps")
    self.new_part("Corps concernés")
    self.add_rect_sketch(60, 20)
    self.add_pad(5)
    top = self._require_body().Name
    self.add_body("Dessous")
    low = self._require_body().Name
    self.add_rect_sketch(60, 20)
    self.add_pad(5, reversed=True)
    self.set_active_body(top)
    sketch = self.sketch_start(face=self._top_face_id())["sketch"]
    self.sketch_add_circle(sketch, -20, 0, 2)
    self.sketch_finish(sketch)
    self.add_pocket(through=True)
    hole = math.pi * 4 * 5
    tree = self.add_linear_pattern(20, 3, axis="X", spacing=True,
                                   scope=[low])
    pattern = next(f for f in tree["features"]
                   if f["type"] == "PartDesign::LinearPattern")
    volumes = _volumes(self)
    report["p83_creuse_l_autre"] = (
        abs(volumes[low] - (6000 - 3 * hole)) < 1e-6
        and abs(volumes[top] - volumes[low]) < 1e-6
        and pattern.get("scope") == ["Dessous"])
    self.set_params(pattern["name"], {"count": 2})
    two = _volumes(self)[low]
    self.set_suppressed([pattern["name"]], True)
    off = _volumes(self)[low]
    self.set_suppressed([pattern["name"]], False)
    try:
        self.add_rect_sketch(4, 4, face=self._top_face_id())
        self.add_pad(2)
        self.add_linear_pattern(10, 2, axis="Y", scope=[low])
        refused = False
    except KernelError:
        refused = True
    report["p83_suit_et_refuse"] = (
        abs(two - (6000 - 2 * hole)) < 1e-6 and abs(off - 6000) < 1e-6
        and refused)
    # Supprimer au milieu de la chaîne : la fonction d'après se rebranche.
    self.set_active_body(low)
    cut = next(f["name"] for f in self.get_tree()["features"]
               if f.get("edits") == pattern["name"])
    self.add_rect_sketch(4, 4)
    self.add_pad(3)
    self.delete_feature(cut)
    after = _volumes(self)
    self.set_active_body(top)
    self.delete_feature(pattern["name"])
    kept = _volumes(self)[top]
    report["p83_suppression_au_milieu"] = (
        abs(after[low] - (6000 + 48)) < 1e-6
        and self._doc.getObject(pattern["name"]) is None
        and abs(kept - (6000 - hole + 32)) < 1e-6
        and not [o for o in self._doc.Objects
                 if getattr(o, "FreeSolidBodyPatternTool", False)])


def p84_arbre_unique(self, mark, report, etat):
    mark("p84: un seul arbre, une seule barre pour tous les corps")
    from engine import protocol
    self.new_part("Arbre unique")
    self.add_rect_sketch(20, 20)
    self.add_pad(5)
    first = self._require_body().Name
    pad = self._require_body().Tip.Name
    self.add_body()
    second = self._require_body().Name
    state = self.sketch_start()
    self.sketch_add_circle(state["sketch"], 30, 0, 5)
    self.sketch_finish(state["sketch"])
    self.add_pad(10)
    other_pad = self._require_body().Tip.Name
    self.set_active_body(first)
    self.add_rect_sketch(4, 4, face=self._top_face_id())
    self.add_pocket(2)
    pocket = self._require_body().Tip.Name
    # L'arbre du premier corps montre aussi l'histoire du second, à son
    # rang : Extrusion, puis celle du second corps, puis l'enlèvement.
    tree = self.get_tree()
    ranks = {f["name"]: f["order"]
             for f in tree["features"] + tree["other_features"]}
    foreign = {f["name"]: f.get("body") for f in tree["other_features"]}
    report["p84_arbre_unique"] = (
        foreign.get(other_pad) == second
        and ranks[pad] < ranks[other_pad] < ranks[pocket]
        and not protocol.dangling_deps(tree))
    # La barre recule tous les corps : après l'extrusion du premier, le
    # second n'existe pas encore ; un cran plus bas, il revient.
    tree = self.set_tip(pad)
    flags = {f["name"]: f.get("rolled_back")
             for f in tree["features"] + tree["other_features"]}
    born_later = self._doc.getObject(second).Tip is None
    self.set_tip(other_pad)
    volumes = _volumes(self)
    report["p84_barre_commune"] = (
        born_later and flags.get(pocket) and flags.get(other_pad)
        and not flags.get(pad)
        and abs(volumes[first] - 2000) < 1e-6
        and abs(volumes[second] - math.pi * 250) < 1e-6)
    # On réordonne dans un corps, pas d'un corps à l'autre.
    self.tip_to_end()
    try:
        self.reorder_feature(pocket, other_pad)
        crossed = True
    except KernelError:
        crossed = False
    # Sous la barre, tout part — dans chaque corps.
    self.set_tip(pad)
    self.delete_rolled_back()
    report["p84_sous_la_barre"] = (
        not crossed
        and self._doc.getObject(pocket) is None
        and self._doc.getObject(other_pad) is None
        and self._doc.getObject(pad) is not None)
