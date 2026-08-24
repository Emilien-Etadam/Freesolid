"""Étapes selftest bijouterie — les 26 indicateurs, hors du noyau."""

import math

from engine.kernel import KernelError


def register_steps(registre):
    ctx = {}
    registre.selftest_step(
        "p034: pierre aimantée sur un cylindre",
        lambda kernel, mark, report: _p034(kernel, mark, report, ctx))
    registre.selftest_step(
        "p036: glisser d'une face à l'autre",
        lambda kernel, mark, report: _p036_migration(kernel, mark, report, ctx))
    registre.selftest_step(
        "p036: cote hors esquisse",
        lambda kernel, mark, report: _p036_cote(kernel, mark, report, ctx))
    registre.selftest_step(
        "p036: reconstruire",
        lambda kernel, mark, report: _p036_rebuild(kernel, mark, report, ctx))
    registre.selftest_step(
        "p042: lire l'écart, redimensionner",
        lambda kernel, mark, report: _p042(kernel, mark, report, ctx))
    registre.selftest_step(
        "p043: le booléen suit la cote, la sélection suit la pierre",
        lambda kernel, mark, report: _p043(kernel, mark, report, ctx))
    registre.selftest_step(
        "p035: booléen sur un semis",
        lambda kernel, mark, report: _p035(kernel, mark, report, ctx))
    registre.selftest_step(
        "p044: ancre par provenance",
        lambda kernel, mark, report: _p044(kernel, mark, report, ctx))


def _close(actual, expected, tol=1e-6):
    scale = abs(float(expected)) or 1.0
    return abs(float(actual) - float(expected)) <= tol * scale


def _volume(kernel):
    return float(kernel._require_body().Shape.Volume)


def _p034(kernel, mark, report, ctx):
    mark("p034: pierre aimantée sur un cylindre")
    kernel.new_part("Jonc P034")
    state = kernel.sketch_start()
    sk_gem = state["sketch"]
    kernel.sketch_add_circle(sk_gem, 0, 0, 10)
    kernel.sketch_constrain(
        sk_gem, "coincident", 0, point1=3, geo2=-1, point2=1)
    dim_state = kernel.sketch_dim(sk_gem, 0)
    radius_dim = max(d["id"] for d in dim_state["dims"])
    kernel.sketch_finish(sk_gem)
    kernel.add_pad(6, sketch=sk_gem)
    side = kernel._side_face_id()
    face = kernel._require_body().Shape.Faces[side]
    u0, u1, v0, v1 = face.ParameterRange
    seed = face.valueAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
    placed = kernel.place_gem(
        face=side, x=seed.x, y=seed.y, z=seed.z, diametre=1.5)
    gems = placed.get("gems") or []
    report["p034_pose"] = (
        len(gems) == 1
        and gems[0]["count"] == 1
        and not gems[0]["error"])
    stone = gems[0]["stones"][0]
    r_before = math.hypot(stone["x"], stone["y"])
    z_before = stone["z"]
    angle_before = math.atan2(stone["y"], stone["x"])
    mesh = kernel.tessellate()
    report["p034_mesh"] = (
        bool(mesh.get("normals"))
        and len(mesh.get("gems") or []) == 1
        and bool((mesh["gems"][0].get("instances") or [{}])[0]
                 .get("matrix")))
    tree = kernel.get_tree()
    from engine.protocol import dangling_deps
    report["p034_arbre"] = (
        len(tree.get("gems") or []) == 1
        and not any(b.get("label", "").startswith("Gabarit")
                    for b in tree["bodies"])
        and not dangling_deps(tree))
    kernel.sketch_set_dim(sk_gem, radius_dim, 12)
    after = (kernel.list_gems().get("gems") or [{}])[0]
    stone2 = (after.get("stones") or [{}])[0]
    r_after = math.hypot(stone2.get("x", 0), stone2.get("y", 0))
    z_after = stone2.get("z", 0)
    angle_after = math.atan2(stone2.get("y", 0), stone2.get("x", 0))
    import Part as _Part
    face_after = kernel._require_body().Shape.Faces[kernel._side_face_id()]
    origin = _Part.Vertex(kernel._app().Vector(
        stone2.get("x", 0), stone2.get("y", 0), stone2.get("z", 0)))
    dist = face_after.distToShape(origin)[0]
    report["p034_ancrage"] = (
        not after.get("error")
        and dist < 1e-6
        and abs(r_after - 12.0) < 1e-4
        and abs(z_after - z_before) < 1e-4
        and abs((angle_after - angle_before + math.pi) % (2 * math.pi)
                - math.pi) < 1e-4
        and abs(r_before - 10.0) < 1e-3)
    report["p034_temoin_fige"] = abs(r_before - 12.0) > 1.0
    moved = kernel.move_gem(
        gems[0]["name"], 0, seed.x, seed.y, seed.z + 1.0)
    report["p034_deplace"] = (
        (moved.get("gems") or [{}])[0].get("count") == 1)
    removed = kernel.remove_gem(gems[0]["name"], 0)
    report["p034_retire"] = (removed.get("gems") or []) == []
    kernel.place_gem(face=side, x=seed.x, y=seed.y, z=seed.z)
    try:
        kernel.place_gem(face=side, x=1000.0, y=1000.0, z=1000.0)
        report["p034_hors_domaine"] = False
    except KernelError as exc:
        report["p034_hors_domaine"] = "hors" in str(exc).lower() or (
            "contour" in str(exc).lower())
    ctx["sk_gem"] = sk_gem
    ctx["radius_dim"] = radius_dim
    ctx["z_before"] = z_before


def _p036_migration(kernel, mark, report, ctx):
    mark("p036: glisser d'une face à l'autre")
    current = (kernel.list_gems().get("gems") or [{}])[0]
    src_name = current.get("name")
    src_face = current.get("face")
    top = kernel._top_face_id()
    top_face, _ = kernel._anchor_face(top)
    tu0, tu1, tv0, tv1 = top_face.ParameterRange
    top_pt = top_face.valueAt((tu0 + tu1) / 2.0, (tv0 + tv1) / 2.0)
    migrated = kernel.move_gem(
        src_name, 0, top_pt.x, top_pt.y, top_pt.z, face=top)
    after_mig = migrated.get("gems") or []
    report["p036_migration"] = (
        len(after_mig) == 1
        and after_mig[0].get("count") == 1
        and after_mig[0].get("name") != src_name
        and after_mig[0].get("face") != src_face
        and not after_mig[0].get("error"))
    ctx["migrated"] = migrated
    ctx["after_mig"] = after_mig


def _p036_cote(kernel, mark, report, ctx):
    mark("p036: cote hors esquisse")
    vol_before_dim = _volume(kernel)
    kernel.sketch_set_dim(ctx["sk_gem"], ctx["radius_dim"], 11)
    report["p036_cote_hors_esquisse"] = (
        abs(_volume(kernel) - vol_before_dim) > 1.0
        and abs(_volume(kernel) - (math.pi * 11.0 * 11.0 * 6.0)) < 2.0)


def _p036_rebuild(kernel, mark, report, ctx):
    mark("p036: reconstruire")
    mesh_a = kernel.tessellate()
    vol_a = _volume(kernel)
    gems_a = kernel.list_gems().get("gems") or []
    kernel.rebuild()
    mesh_b = kernel.tessellate()
    gems_b = kernel.list_gems().get("gems") or []
    report["p036_rebuild"] = (
        _close(_volume(kernel), vol_a)
        and len(mesh_a.get("indices") or [])
        == len(mesh_b.get("indices") or [])
        and len(mesh_a.get("groups") or [])
        == len(mesh_b.get("groups") or [])
        and len(gems_a) == len(gems_b) == 1
        and gems_a[0].get("count") == gems_b[0].get("count") == 1)


def _p042(kernel, mark, report, ctx):
    mark("p042: lire l'écart, redimensionner")
    top = kernel._top_face_id()
    first = (kernel.list_gems().get("gems") or [{}])[0]
    stone0 = (first.get("stones") or [{}])[0]
    kernel.place_gem(
        face=top,
        x=float(stone0.get("x", 0)) + 3.0,
        y=float(stone0.get("y", 0)),
        z=float(stone0.get("z", 0)),
        diametre=1.5)
    pair = (kernel.list_gems().get("gems") or [{}])[0]
    old_v = pair.get("voisine_min_mm")
    old_e = pair.get("ecart_min_mm")
    report["p042_deux_pierres"] = (
        pair.get("count") == 2
        and old_v is not None
        and old_e is not None)
    resized = kernel.resize_gem(pair.get("name"), 2.0)
    after_r = (resized.get("gems") or [{}])[0]
    report["p042_resize"] = (
        abs((after_r.get("diametre") or 0) - 2.0) < 1e-9
        and after_r.get("voisine_min_mm") is not None
        and old_v is not None
        and abs(after_r["voisine_min_mm"] - old_v) < 1e-6
        and old_e is not None
        and abs((after_r.get("ecart_min_mm") or 0) - (old_e - 0.5))
        < 1e-4)


def _p043(kernel, mark, report, ctx):
    mark("p043: le booléen suit la cote, la sélection suit la pierre")
    migrated = ctx.get("migrated")
    after_mig = ctx.get("after_mig") or []
    moved_info = migrated.get("gem_moved") if isinstance(
        migrated, dict) else None
    dest_name = (after_mig or [{}])[0].get("name")
    report["p043_gem_moved"] = (
        isinstance(moved_info, dict)
        and moved_info.get("gem") == dest_name
        and moved_info.get("index") == 0)

    kernel.new_part("Jonc P043")
    state = kernel.sketch_start()
    sk_p043 = state["sketch"]
    kernel.sketch_add_circle(sk_p043, 0, 0, 10)
    kernel.sketch_constrain(
        sk_p043, "coincident", 0, point1=3, geo2=-1, point2=1)
    kernel.sketch_finish(sk_p043)
    kernel.add_pad(6, sketch=sk_p043)
    side_p043 = kernel._side_face_id()
    face_p043 = kernel._require_body().Shape.Faces[side_p043]
    u0, u1, v0, v1 = face_p043.ParameterRange
    v_mid = (v0 + v1) / 2.0
    for i in range(2):
        u = u0 + (u1 - u0) * (i + 0.5) / 2.0
        pt = face_p043.valueAt(u, v_mid)
        kernel.place_gem(
            face=side_p043, x=pt.x, y=pt.y, z=pt.z,
            diametre=1.5, lift=-0.25)
    gems_p043 = kernel.list_gems().get("gems") or []
    semis_p043 = (gems_p043 or [{}])[0].get("name")
    kernel.add_boolean(tool=semis_p043, type="cut")
    vol_before_cote = _volume(kernel)
    kernel.resize_gem(semis_p043, 2.0)
    vol_after_cote = _volume(kernel)
    report["p043_booleen_suit_cote"] = (
        abs(vol_after_cote - vol_before_cote) > 1e-3)


def _jonc_trois_pierres(kernel, name):
    kernel.new_part(name)
    state = kernel.sketch_start()
    sk = state["sketch"]
    kernel.sketch_add_circle(sk, 0, 0, 10)
    kernel.sketch_constrain(
        sk, "coincident", 0, point1=3, geo2=-1, point2=1)
    kernel.sketch_finish(sk)
    tree = kernel.add_pad(6, sketch=sk)
    pad_name = next(
        f["name"] for f in tree["features"]
        if f["type"] == "PartDesign::Pad")
    side = kernel._side_face_id()
    face = kernel._require_body().Shape.Faces[side]
    u0, u1, v0, v1 = face.ParameterRange
    v_mid = (v0 + v1) / 2.0
    for i in range(3):
        u = u0 + (u1 - u0) * (i + 0.5) / 3.0
        pt = face.valueAt(u, v_mid)
        kernel.place_gem(
            face=side, x=pt.x, y=pt.y, z=pt.z,
            diametre=1.5, lift=-0.25)
    gems = kernel.list_gems().get("gems") or []
    return pad_name, side, gems, _volume(kernel)


def _p035(kernel, mark, report, ctx):
    mark("p035: booléen sur un semis")
    pad_name, side, gems, vol_nu = _jonc_trois_pierres(kernel, "Jonc P035")
    semis = (gems or [{}])[0].get("name")
    tree = kernel.add_boolean(tool=semis, type="cut")
    shape_cut = kernel._require_body().Shape
    vol_cut = _volume(kernel)
    after_cut = kernel.list_gems().get("gems") or []
    report["p035_cut"] = (
        len(getattr(shape_cut, "Solids", ()) or ()) == 1
        and vol_cut < vol_nu - 0.05
        and len(after_cut) == 1
        and after_cut[0].get("count") == 3
        and not any(b.get("label", "").startswith("Corps outil du semis")
                    for b in tree["bodies"]))
    stone_before = (after_cut[0].get("stones") or [{}])[0]
    mesh_before = kernel.tessellate()
    kernel.set_tip(pad_name)
    face = kernel._require_body().Shape.Faces[side]
    u0, u1, v0, v1 = face.ParameterRange
    moved_pt = face.valueAt(
        u0 + (u1 - u0) * 0.05, (v0 + v1) / 2.0)
    kernel.move_gem(semis, 0, moved_pt.x, moved_pt.y, moved_pt.z)
    kernel.tip_to_end()
    stone_after = ((kernel.list_gems().get("gems") or [{}])[0]
                   .get("stones") or [{}])[0]
    dx = float(stone_after.get("x", 0)) - float(stone_before.get("x", 0))
    dy = float(stone_after.get("y", 0)) - float(stone_before.get("y", 0))
    mesh_after = kernel.tessellate()
    report["p035_deplace"] = (
        (dx * dx + dy * dy) ** 0.5 > 1.0
        and mesh_before.get("positions") != mesh_after.get("positions")
        and len(kernel._require_body().Shape.Solids) == 1
        and abs(_volume(kernel) - vol_cut) < 0.5)

    _pad, _side, gems_fuse, vol_nu_fuse = _jonc_trois_pierres(
        kernel, "Jonc P035 fuse")
    semis_fuse = (gems_fuse or [{}])[0].get("name")
    kernel.add_boolean(tool=semis_fuse, type="fuse")
    report["p035_fuse"] = (
        len(kernel._require_body().Shape.Solids) == 1
        and _volume(kernel) > vol_nu_fuse + 0.05)


def _p044(kernel, mark, report, ctx):
    mark("p044: ancre par provenance")
    from engine.gems import face_radius_mm as _face_radius_mm

    def _cylindre_ids(radius):
        found = []
        for i, face in enumerate(kernel._require_body().Shape.Faces):
            surface = getattr(face, "Surface", None)
            type_id = str(getattr(surface, "TypeId", "") or "")
            if "Cylinder" not in type_id:
                continue
            r = _face_radius_mm(face)
            if r is not None and abs(r - radius) < 1e-6:
                found.append(i)
        return found

    kernel.new_part("Tube P044")
    state = kernel.sketch_start()
    sk_p044 = state["sketch"]
    kernel.sketch_add_circle(sk_p044, 0, 0, 10)
    kernel.sketch_constrain(
        sk_p044, "coincident", 0, point1=3, geo2=-1, point2=1)
    kernel.sketch_add_circle(sk_p044, 0, 0, 4)
    kernel.sketch_constrain(
        sk_p044, "coincident", 1, point1=3, geo2=-1, point2=1)
    kernel.sketch_finish(sk_p044)
    kernel.add_pad(6, sketch=sk_p044)
    bore_before = _cylindre_ids(4.0)
    report["p044_alesage_avant"] = (len(bore_before) == 1)
    alesage = bore_before[0] if len(bore_before) == 1 else None
    if alesage is None:
        report["p044_ancre"] = False
    else:
        face = kernel._require_body().Shape.Faces[alesage]
        u0, u1, v0, v1 = face.ParameterRange
        seed = face.valueAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
        placed = kernel.place_gem(
            face=alesage, x=seed.x, y=seed.y, z=seed.z,
            diametre=1.5)
        gem0 = (placed.get("gems") or [{}])[0]
        report["p044_pose"] = (
            gem0.get("count") == 1 and not gem0.get("error"))
        kernel.add_fillet(0.4, face=kernel._top_face_id())
        after = (kernel.list_gems().get("gems") or [{}])[0]
        bore_after = _cylindre_ids(4.0)
        stone = (after.get("stones") or [{}])[0]
        report["p044_indice_a_bouge"] = (
            len(bore_after) == 1 and alesage != bore_after[0])
        report["p044_ancre"] = (
            len(bore_after) == 1
            and alesage != bore_after[0]
            and not after.get("error")
            and after.get("count") == 1
            and after.get("face_id") == bore_after[0]
            and abs((after.get("rayon_mm") or 0) - 4.0) < 1e-3
            and "x" in stone)
