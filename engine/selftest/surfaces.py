"""Selftest — surfaces et courbes : construction, retouche, passage au solide.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import math
import os
import tempfile

from engine.kernel import KernelError


def p12_extrusion_couture_epaississement(self, mark, report, etat):
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
    sewn = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    area0 = sewn.Shape.Area
    # La couture suit ses sources : une surface rallongée de 20 à
    # 30 mm agrandit la peau cousue (40 × 10 mm de plus).
    self._require_doc().getObject(names[0]).LengthFwd = 30
    self._recompute()
    sew_follows = abs(sewn.Shape.Area - area0 - 400) < 1e-6
    self._require_doc().getObject(names[0]).LengthFwd = 20
    self._recompute()
    report["p12_sew_ok"] = (len(tree["surfaces"]) == 3 and sew_follows
                            and abs(sewn.Shape.Area - area0) < 1e-6)
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


def p12_courbe_3d_balayage(self, mark, report, etat):
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


def p30_barre_retour_surfaces(self, mark, report, etat):
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


def p46_spline_3d_reeditable(self, mark, report, etat):
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
    # Règles d'esquisse 3D : segment 1 sur Z, coté 30 ; segment 2
    # sur X, coté 15. Le solveur en chaîne recale les points et les
    # règles restent attachées à la courbe.
    ruled_tree = self.add_curve3d(
        [[0, 0, 0], [1, 2, 25], [9, 1, 26]], spline=False,
        rules=[{"axis": "Z", "length": 30},
               {"axis": "X", "length": 15}])
    ruled_spec = ruled_tree["surfaces"][-1].get("curve") or {}
    moved = self.edit_curve3d(
        ruled_tree["surfaces"][-1]["name"],
        [[5, 5, 5], [6, 6, 6], [7, 7, 7]], spline=False)
    moved_spec = moved["surfaces"][-1].get("curve") or {}
    report["p46_esquisse3d_regles"] = (
        ruled_spec.get("points") == [[0, 0, 0], [0, 0, 30],
                                     [15, 0, 30]]
        and len(ruled_spec.get("rules") or []) == 2
        and moved_spec.get("points") == [[5, 5, 5], [5, 5, 35],
                                         [20, 5, 35]])
    # Angle entre segments, point lié à un sommet du solide qui
    # suit quand le solide change.
    self.add_rect_sketch(20, 20)
    pad_tree = self.add_pad(10)
    pad_name = next(f["name"] for f in pad_tree["features"]
                    if f["type"] == "PartDesign::Pad")
    angle_tree = self.add_curve3d(
        [[10, 10, 10], [10, 10, 30], [20, 10, 40]], spline=False,
        rules=[{}, {"angle": 90, "length": 10}],
        links=[True, None, None])
    spec_a = angle_tree["surfaces"][-1].get("curve") or {}
    angle_obj = self._require_doc().getObject(
        angle_tree["surfaces"][-1]["name"])
    anchored = (spec_a.get("links") or [None])[0]
    self.set_params(pad_name, {"Length": 15.0})
    first = angle_obj.FreeSolidPoints[0]
    # Solveur global : deux extrémités liées, deux longueurs —
    # le point du milieu se place sur les deux sphères à la fois ;
    # des règles impossibles sont refusées.
    pts = self.solve_curve_rules(
        [[0, 0, 0], [5, 5, 0], [14, 0, 0]],
        [{"length": 10}, {"length": 10}], [0, 2])
    import math as _m
    global_ok = (abs(_m.dist(pts[0], pts[1]) - 10) < 1e-4
                 and abs(_m.dist(pts[1], pts[2]) - 10) < 1e-4
                 and pts[2] == [14, 0, 0])
    try:
        self.solve_curve_rules(
            [[0, 0, 0], [5, 5, 0], [30, 0, 0]],
            [{"length": 10}, {"length": 10}], [0, 2])
        impossible_refused = False
    except KernelError as exc:
        impossible_refused = "incompatibles" in str(exc)
    report["p46_esquisse3d_solveur_global"] = (
        global_ok and impossible_refused)
    report["p46_esquisse3d_angle_lien"] = (
        spec_a.get("points")[2] == [20, 10, 30]
        and isinstance(anchored, dict)
        and abs(first.z - 15) < 1e-6)
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
    etat.closed = closed


def p46_remplissage_plane_decalee(self, mark, report, etat):
    closed = etat.closed  # posé par surfaces.p46_spline_3d_reeditable
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
    # Ajustement mutuel : un carré neuf et la paroi se coupent l'un
    # l'autre, une partie de chacun gardée.
    state = self.sketch_start(plane="XY")
    square2 = state["sketch"]
    self.sketch_add_rectangle(square2, 0, 0, 40, 40)
    self.sketch_finish(square2)
    plate2 = self.surface_planar(sketch=square2)["surfaces"][-1]["name"]
    state = self.sketch_start(plane="XY")
    wall2 = state["sketch"]
    self.sketch_add_line(wall2, 10, 0, 10, 40)
    self.sketch_finish(wall2)
    self._require_doc().getObject(wall2).AttachmentOffset = (
        App.Placement(App.Vector(0, 0, -10), App.Rotation()))
    self._recompute()
    cutter2 = self.surface_extrude(30, sketch=wall2)["surfaces"][-1]
    tree = self.surface_trim(plate2, cutter2["name"],
                             point=[30, 20, 0],
                             tool_point=[10, 20, 15])
    pair = [self._require_doc().getObject(s["name"])
            for s in tree["surfaces"][-2:]]
    report["p46_ajustement_mutuel"] = (
        abs(pair[0].Shape.Area - 1200) < 1e-3
        and abs(pair[1].Shape.Area - 40 * 20) < 1e-3)
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


def p47_couper_solide_surface(self, mark, report, etat):
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


def p48_frontiere_reglee_composite(self, mark, report, etat):
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
    try:
        self.curve_composite([{"name": curves[0]},
                              {"name": curves[2]}])
        apart_refused = False
    except KernelError as exc:
        apart_refused = "bout à bout" in str(exc)
    report["p48_courbe_composite"] = apart_refused and (
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

    # Bout de tube : une seule arête fermée se remplit aussi.
    tube_end = [i for i, e in enumerate(tube.Shape.Edges)
                if e.isClosed() and e.BoundBox.ZMin > 19]
    cap = obj_of(self.surface_fill(
        [{"name": tube.Name, "edge": tube_end[0]}]))
    cap_ok = abs(cap.Shape.Area - math.pi * 25) < 0.5
    # Bouchon tangent au tube (faces voisines perpendiculaires :
    # le solveur échoue, le bouchon B-spline prend le relais).
    dome = obj_of(self.surface_fill(
        [{"name": tube.Name, "edge": tube_end[0]}], tangent=True))
    side = next(f for f in tube.Shape.Faces)
    worst = 0.0
    for edge in [tube.Shape.Edges[tube_end[0]]]:
        for point in edge.discretize(12):
            u, v = dome.Shape.Faces[0].Surface.parameter(point)
            n1 = dome.Shape.Faces[0].normalAt(u, v)
            su, sv = side.Surface.parameter(point)
            n2 = side.normalAt(su, sv)
            worst = max(worst, math.degrees(
                math.acos(min(1.0, abs(n1.dot(n2))))))
    report["p48_remplir_arete_fermee"] = (
        len(tube_end) == 1 and cap_ok
        and dome.Shape.BoundBox.ZMax > 21 and worst < 0.5)
    etat.obj_of = obj_of


def p48_supprimer_faces_desajuster(self, mark, report, etat):
    obj_of = etat.obj_of  # posé par surfaces.p48_frontiere_reglee_composite
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


def p49_supprimer_face_solide(self, mark, report, etat):
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


def p49_remplacer_face_solide(self, mark, report, etat):
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
    labels = [f["label"] for f in tree["features"]]
    mixed_ok = (abs(body.Shape.Volume - 1600 * 10) < 1
                and abs(body.Shape.BoundBox.ZMax - 13) < 1e-6
                and labels[-1] == "Remplacer la face"
                and "Remplacer la face — ajout" not in labels)
    # Une seule ligne : la supprimer retire aussi l'ajout caché.
    tree = self.delete_feature(tree["features"][-1]["name"])
    report["p49_remplacer_mixte"] = (
        mixed_ok and abs(body.Shape.Volume - 1600 * 10) < 1
        and abs(body.Shape.BoundBox.ZMax - 10) < 1e-6
        and not any(o.TypeId == "PartDesign::Boolean"
                    for o in body.Group))


def p50_courbe_helice_ressort(self, mark, report, etat):
    mark("p50: courbe hélice, balayage d'un ressort en surface")
    import math
    self.new_part("Pièce hélice")
    tree = self.curve_helix(5, 20, 10)
    helix = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    turns = 20 / 5
    expected = turns * math.hypot(2 * math.pi * 10, 5)
    state = self.sketch_start(plane="XZ")
    wire_sk = state["sketch"]
    self.sketch_add_line(wire_sk, 9, -1, 11, 1)
    self.sketch_finish(wire_sk)
    swept = self._require_doc().getObject(
        self.surface_sweep(wire_sk, helix.Name)["surfaces"][-1]["name"])
    length4 = helix.Shape.Length
    length_ok = abs(length4 - expected) < 0.5
    self.set_params(helix.Name, {"Pitch": 4.0})
    report["p50_helice"] = (
        length_ok
        and helix.Name in {s["name"] for s
                           in self.get_tree()["surfaces"]}
        and bool(swept.Shape.Faces)
        and any(c["name"] == helix.Name
                for c in self.tessellate().get("curves") or [])
        and helix.Shape.Length > length4)


def p50_surface_radiee(self, mark, report, etat):
    mark("p50: surface radiée depuis les arêtes du solide")
    self.new_part("Pièce radiée")
    self.add_rect_sketch(20, 20)
    self.add_pad(10)
    body = self._require_body()
    top = [i for i, e in enumerate(body.Shape.Edges)
           if abs(e.CenterOfMass.z - 10) < 1e-6]
    tree = self.surface_radiate(
        [{"body": True, "edge": i} for i in top], 5)
    band = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    report["p50_surface_radiee"] = (
        abs(band.Shape.Area - 500) < 1e-3
        and abs(band.Shape.BoundBox.ZMin - 10) < 1e-6
        and abs(band.Shape.BoundBox.ZMax - 10) < 1e-6
        and len(tree["surfaces"]) == 1)


def p50_surface_mediane_paroi(self, mark, report, etat):
    mark("p50: surface médiane d'une paroi")
    self.new_part("Pièce médiane")
    self.add_rect_sketch(40, 30)
    tree = self.add_pad(6)
    pad = next(f["name"] for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    body = self._require_body()
    top = next(i for i, f in enumerate(body.Shape.Faces)
               if abs(f.CenterOfMass.z - 6) < 1e-6)
    bottom = next(i for i, f in enumerate(body.Shape.Faces)
                  if abs(f.CenterOfMass.z) < 1e-6)
    tree = self.surface_mid([top, bottom])
    mid = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    first_ok = (abs(mid.Shape.BoundBox.ZMin - 3) < 1e-6
                and abs(mid.Shape.Area - 1200) < 1e-6)
    self.set_params(pad, {"Length": 10.0})
    follow_ok = abs(mid.Shape.BoundBox.ZMin - 5) < 1e-6
    # Coque mince : les paires se trouvent seules (parois de 2 mm).
    self.new_part("Pièce médiane auto")
    self.add_rect_sketch(40, 30)
    self.add_pad(20)
    body = self._require_body()
    top = next(i for i, f in enumerate(body.Shape.Faces)
               if abs(f.CenterOfMass.z - 20) < 1e-6)
    self.add_thickness(thickness=2, faces=[top])
    tree = self.surface_mid(thickness=3)
    auto = self._require_doc().getObject(
        tree["surfaces"][-1]["name"])
    auto_faces = len(auto.Shape.Faces)
    # Faces inclinées (dépouille) : la médiane générale passe au
    # milieu.
    self.new_part("Pièce médiane inclinée")
    state = self.sketch_start(plane="XZ")
    wedge = state["sketch"]
    self.sketch_add_line(wedge, 0, 0, 30, 0)
    self.sketch_add_line(wedge, 30, 0, 30, 2)
    self.sketch_add_line(wedge, 30, 2, 0, 6)
    self.sketch_add_line(wedge, 0, 6, 0, 0)
    self.sketch_finish(wedge)
    self.add_pad(20)
    body = self._require_body()
    bottom = next(i for i, f in enumerate(body.Shape.Faces)
                  if abs(f.CenterOfMass.z) < 1e-6
                  and f.Area > 100)
    slope = max(range(len(body.Shape.Faces)),
                key=lambda i: body.Shape.Faces[i].CenterOfMass.z)
    tree = self.surface_mid([bottom, slope])
    tilted = self._require_doc().getObject(
        tree["surfaces"][-1]["name"])
    bb = tilted.Shape.BoundBox
    report["p50_surface_mediane"] = (
        first_ok and follow_ok
        and auto_faces == 5
        # Milieux au point le plus proche : ~2,95 au bord épais.
        and abs(bb.ZMax - 3) < 0.1 and abs(bb.ZMin - 1) < 0.05)


def p50_aplatir_surface_forme_libre(self, mark, report, etat):
    mark("p50: aplatir une surface, forme libre")
    import math
    self.new_part("Pièce aplatir")
    state = self.sketch_start(plane="XY")
    arc_sk = state["sketch"]
    self.sketch_add_arc(arc_sk, 0, 0, 10, 0, math.pi)
    self.sketch_finish(arc_sk)
    half = self._require_doc().getObject(
        self.surface_extrude(30, sketch=arc_sk)["surfaces"][-1]["name"])
    tree = self.surface_flatten(half.Name)
    flat = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    flat_spec = tree["surfaces"][-1].get("surface") or {}
    report["p50_aplatir"] = (
        flat_spec.get("area_error", 99) < 1
        and flat_spec.get("edge_error", 99) < 1
        and abs(flat.Shape.Area - math.pi * 10 * 30) < 2
        and flat.Shape.BoundBox.XMin >= half.Shape.BoundBox.XMax
        and abs(flat.Shape.BoundBox.ZMax) < 1e-6
        and (tree["surfaces"][-1].get("surface") or {}).get("kind")
        == "flatten")
    state = self.sketch_start(plane="XY")
    plate_sk = state["sketch"]
    self.sketch_add_rectangle(plate_sk, 0, 0, 40, 40)
    self.sketch_finish(plate_sk)
    plate = self._require_doc().getObject(
        self.surface_planar(sketch=plate_sk)["surfaces"][-1]["name"])
    tree = self.surface_freeform(plate.Name, 15, point=[20, 20, 0],
                                 height=5)
    bump = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    top = bump.Shape.BoundBox.ZMax
    # Une bosse n'est pas développable : son patron dit de combien
    # il s'étire.
    dome_spec = self.surface_flatten(bump.Name)["surfaces"][-1].get(
        "surface") or {}
    report["p50_aplatir"] = report["p50_aplatir"] and (
        max(dome_spec.get("area_error", 0),
            dome_spec.get("edge_error", 0)) > 0.5)
    self.edit_surface_freeform(bump.Name, 15, height=8)
    # Deux poussées opposées, bords fixes : une bosse et un creux,
    # le contour de la plaque ne bouge pas.
    tree = self.surface_freeform(
        bump.Name, 15, pushes=[[10, 10, 0, 6], [30, 30, 0, -6]],
        keep_edges=True)
    wave = self._require_doc().getObject(tree["surfaces"][-1]["name"])
    wb = wave.Shape.BoundBox
    edges_still = all(abs(p.z) < 1e-6 for e in wave.Shape.Edges
                      for p in e.discretize(20))
    spec = (tree["surfaces"][-1].get("surface") or {})
    multi_ok = (wb.ZMax > 3 and wb.ZMin < -3 and edges_still
                and len(spec.get("pushes") or []) == 2
                and spec.get("keep_edges") is True)
    # Points de contrôle : la grille se lit, un pôle intérieur
    # monte de 6 mm, le bord ne bouge pas.
    grid = self.surface_control_points(plate.Name, grid=6)
    tree = self.surface_freeform(plate.Name, moves=[[3, 3, 0, 0, 6]],
                                 grid=6)
    lifted = self._require_doc().getObject(
        tree["surfaces"][-1]["name"])
    # La boîte d'une B-spline borne ses pôles : on échantillonne.
    def heights(obj):
        f = obj.Shape.Faces[0]
        u0, u1, v0, v1 = f.ParameterRange
        return [f.valueAt(u0 + (u1 - u0) * a / 20,
                          v0 + (v1 - v0) * b / 20).z
                for a in range(21) for b in range(21)]
    zs = heights(lifted)
    poles_ok = (grid["grid"] == [6, 6] and 1 < max(zs) < 6
                and abs(min(zs)) < 1e-6
                and (tree["surfaces"][-1].get("surface") or {})
                .get("moves") == [[0, 3, 3, 0.0, 0.0, 6.0]])
    self.edit_surface_freeform(lifted.Name, moves=[[3, 3, 0, 0, -6]])
    poles_ok = poles_ok and min(heights(lifted)) < -1
    # Surface à deux faces (extrusion d'un profil en L) : la face
    # déformée change, l'autre reste — rien ne disparaît.
    st = self.sketch_start(plane="XY")
    l_sk = st["sketch"]
    self.sketch_add_line(l_sk, 100, 0, 140, 0)
    self.sketch_add_line(l_sk, 140, 0, 140, 30)
    self.sketch_finish(l_sk)
    l_surf = self._require_doc().getObject(
        self.surface_extrude(20, sketch=l_sk)["surfaces"][-1]["name"])
    faces_before = len(l_surf.Shape.Faces)
    area_before = l_surf.Shape.Area
    tree = self.surface_freeform(l_surf.Name, moves=[[3, 3, 0, 6, 0]],
                                 grid=6, face=0)
    l_free = self._require_doc().getObject(
        tree["surfaces"][-1]["name"])
    area_one = l_free.Shape.Area
    # Les deux faces dans la même fonction ; puis grille plus fine
    # en réédition : le pôle réglé suit sa place.
    self.edit_surface_freeform(l_free.Name, moves=[
        [0, 3, 3, 0, 6, 0], [1, 3, 3, -6, 0, 0]])
    area_two = l_free.Shape.Area
    self.edit_surface_freeform(l_free.Name, grid=11)
    spec = next(s for s in self.get_tree()["surfaces"]
                if s["name"] == l_free.Name)["surface"]
    grids = self.surface_control_points(l_surf.Name, grid=6)
    poles_ok = poles_ok and (
        faces_before == 2 and len(l_free.Shape.Faces) == 2
        and area_one > area_before + 1e-3
        and area_two > area_one + 1e-3
        and len(grids["faces"]) == 2
        and spec["grid"] == 11
        and [m[:3] for m in spec["moves"]] == [[0, 5, 5], [1, 5, 5]]
        and len(l_free.Shape.Faces) == 2)
    report["p50_forme_libre"] = poles_ok and multi_ok and (
        3 < abs(top) < 5.5
        and 5 < abs(bump.Shape.BoundBox.ZMax) < 8.5
        and abs(bump.Shape.BoundBox.XLength - 40) < 1e-3
        and plate.Name not in {s["name"] for s
                               in self.tessellate().get("surfaces")
                               or []})


def p50_epaissir_en_enlevant(self, mark, report, etat):
    mark("p50: épaissir en enlevant la matière")
    # Bloc 40×30×10 ; plaque à z = 8, épaissie de 3 mm vers le
    # haut : la tranche 8–10 part (2 400 mm³). Réédition : côté
    # inversé, 8 mm — la tranche 0–8 part (9 600 mm³).
    App = self._app()
    self.new_part("Pièce épaissir-enlever")
    self.add_rect_sketch(40, 30)
    self.add_pad(10)
    st = self.sketch_start(plane="XY")
    slab_sk = st["sketch"]
    self.sketch_add_rectangle(slab_sk, -25, -20, 25, 20)
    self.sketch_finish(slab_sk)
    slab = self._require_doc().getObject(
        self.surface_planar(sketch=slab_sk)["surfaces"][-1]["name"])
    slab.Placement = App.Placement(App.Vector(0, 0, 8),
                                   App.Rotation())
    self._recompute()
    body = self._require_body()
    v0 = body.Shape.Volume
    tree = self.add_surface_cut(slab.Name, thickness=3)
    cut_feat = body.Tip
    v1 = body.Shape.Volume
    spec = next((f.get("surface_cut") for f in tree["features"]
                 if f.get("name") == cut_feat.Name), None) or {}
    self.edit_surface_cut(cut_feat.Name, flip=True, thickness=8)
    v2 = body.Shape.Volume
    report["p50_epaissir_enlever"] = (
        abs((v0 - v1) - 2400) < 1e-2
        and abs((v0 - v2) - 9600) < 1e-2
        and spec.get("thickness") == 3.0
        and slab.Name in {s["name"] for s
                          in self.tessellate().get("surfaces") or []})


def p69_spline_3d_poignees_poles(self, mark, report, etat):
    mark("p69: spline 3D — poignées, pôles")
    self.new_part("Pièce courbes")
    App = self._app()
    pts = [[0, 0, 0], [20, 10, 5], [40, 0, 10], [60, 15, 0]]
    tans = [None, {"dir": [1, 0, 0], "in": 0.5, "out": 2.0},
            None, None]
    tree = self.add_curve3d(pts, tangents=tans)
    entry = tree["surfaces"][-1]
    obj = self._require_doc().getObject(entry["name"])
    edge = obj.Shape.Edges[0]
    curve = edge.Curve
    # La courbe passe par les points ; au point 2, la pente vaut
    # la poignée de chaque côté (paramètre = longueur de corde).
    knots = curve.getKnots()
    through = all(
        (curve.value(u) - App.Vector(*p)).Length < 1e-7
        for u, p in zip(knots, pts))
    d_in = curve.getD1(knots[1] - 1e-9)[1]
    d_out = curve.getD1(knots[1] + 1e-9)[1]
    stored = entry["curve"]["tangents"]
    report["p69_poignees"] = (
        through and len(knots) == 4
        and abs(d_in.x - 0.5) < 1e-5 and abs(d_out.x - 2.0) < 1e-5
        and abs(d_in.y) < 1e-6 and abs(d_out.y) < 1e-6
        and stored[1] == {"dir": [1.0, 0.0, 0.0], "in": 0.5,
                          "out": 2.0}
        and stored[0] is None)
    # Réédition sans tangentes, même nombre de points : les poignées
    # restent ; un point de plus : toutes libres.
    self.edit_curve3d(entry["name"], [[0, 0, 0], [20, 12, 5],
                                      [40, 0, 10], [60, 15, 0]])
    kept = self._curve_spec(obj)["tangents"][1] is not None
    poles = self.curve_poles(pts, tangents=tans)["poles"]
    moved = self.curve_move_pole(pts, 2, [
        poles[2][0], poles[2][1] + 8, poles[2][2]], tangents=tans)
    rebuilt = self.curve_poles(moved["points"],
                               tangents=moved["tangents"])["poles"]
    report["p69_poles"] = (
        kept and len(moved["points"]) == 4
        and moved["points"][0] == [0.0, 0.0, 0.0]
        and all(abs(a - b) < 1e-6 for p, q in zip(rebuilt,
                                                 moved["poles"])
                for a, b in zip(p, q))
        and abs(rebuilt[2][1] - (poles[2][1] + 8)) < 1e-6)

    # Esquisse : la spline se relit en points et poignées, se
    # redessine à sa place et garde ses relations.
    st = self.sketch_start(plane="XY")
    sk_name = st["sketch"]
    self.sketch_add_line(sk_name, -20, 0, 0, 0)
    state = self.sketch_add_spline(
        sk_name, [[0, 0], [10, 8], [20, 0], [30, 6]])
    spline = next(e for e in state["entities"]
                  if e.get("kind") == "spline")
    read = spline.get("spline") or {}
    sk_obj = self._require_doc().getObject(sk_name)
    import Sketcher
    sk_obj.addConstraint(Sketcher.Constraint(
        "Coincident", 0, 2, spline["id"], 1))
    sk_obj.setConstruction(spline["id"], True)
    count = len(sk_obj.Constraints)
    state = self.sketch_set_spline(
        sk_name, spline["id"], [[0, 0], [10, 12], [20, 0], [30, 6]],
        tangents=[None, {"dir": [1, 0], "in": 1, "out": 1.5},
                  None, None])
    again = next(e for e in state["entities"]
                 if e["id"] == spline["id"])
    geo = sk_obj.Geometry[spline["id"]]
    report["p69_esquisse"] = (
        read.get("points") == [[0.0, 0.0], [10.0, 8.0], [20.0, 0.0],
                               [30.0, 6.0]]
        and not any(read.get("tangents") or [1])
        and len(sk_obj.Constraints) == count
        and bool(sk_obj.getConstruction(spline["id"]))
        and (geo.value(geo.getKnots()[1])
             - App.Vector(10, 12, 0)).Length < 1e-6
        and again["spline"]["tangents"][1] is not None
        and abs(again["spline"]["tangents"][1]["out"] - 1.5) < 1e-6)
    self.sketch_finish(sk_name)
