"""Spike N009 — rejeu d'un groupe de fonctions avec paramètres substitués.

Pas d'opération exposée, pas de fonction d'arbre, pas d'UI. Le selftest
appelle ``run_minimal_spike``. FreeCAD n'est importé que dans les corps
de fonctions.
"""

from engine.kernel import Kernel, KernelError


#: Ce que ``get_params`` + le profil suffisent à reconstituer.
REPLAYABLE_TYPES = {
    "PartDesign::Pad": "add_pad",
    "PartDesign::Pocket": "add_pocket",
    "PartDesign::Revolution": "add_revolution",
    "PartDesign::Groove": "add_groove",
    "PartDesign::Fillet": "add_fillet",
    "PartDesign::Chamfer": "add_chamfer",
    "PartDesign::Draft": "add_draft",
    "PartDesign::Thickness": "add_thickness",
    "PartDesign::Hole": "add_hole",
}

#: TypeId rejouable seulement si l'on lit des propriétés hors get_params.
REPLAYABLE_WITH_EXTRA = {
    "PartDesign::AdditiveHelix": "add_helix — Pitch/Height absents de get_params",
}

#: Les 23 add_* : ce qui n'a pas de réciproque TypeId + cotes + profil.
UNREPLAYABLE_OPS = {
    "add_rect_sketch": "l'esquisse se copie, elle ne se reconstitue pas",
    "add_datum_plane": "AttachmentSupport, pas une cote",
    "add_loft": "plusieurs profils (Sections), pas get_params",
    "add_sweep": "Profile + Spine, pas get_params",
    "add_helix": "Pitch/Height hors whitelist get_params",
    "add_linear_pattern": "Originals n'est pas une cote",
    "add_polar_pattern": "Originals n'est pas une cote",
    "add_mirror": "Originals n'est pas une cote",
    "add_boolean": "corps outil, pas un profil",
    "add_text": "propriétés FreeSolid* hors get_params",
    "add_graph_feature": "JSON du graphe, pas un profil",
    "add_curve3d": "liste de points",
    "add_body": "pas une fonction du groupe",
    "add_joint": "assemblage",
}

_TEMP_PREFIX = "N009Replay"


def reconstitution_table():
    """Tableau figé : ce qui se reconstitue, et ce qui ne se reconstitue pas."""
    return {
        "replayable": dict(REPLAYABLE_TYPES),
        "replayable_with_extra": dict(REPLAYABLE_WITH_EXTRA),
        "unreplayable": dict(UNREPLAYABLE_OPS),
    }


def _linked_name(value):
    linked = value[0] if isinstance(value, tuple) else value
    return getattr(linked, "Name", None)


def _base_indices(obj):
    edges = []
    faces = []
    for _target, subs in Kernel._iter_link_subs(getattr(obj, "Base", None)):
        for sub in subs:
            sub = str(sub)
            if sub.startswith("Edge"):
                edges.append(int(sub[4:]) - 1)
            elif sub.startswith("Face"):
                faces.append(int(sub[4:]) - 1)
    return edges, faces


def _dump_sketch(sketch):
    on_face = False
    support = getattr(sketch, "AttachmentSupport", None)
    if support is None:
        support = getattr(sketch, "Support", None)
    for _obj, subs in Kernel._iter_link_subs(support):
        if any(str(item).startswith("Face") for item in subs):
            on_face = True
            break
    return {
        "name": sketch.Name,
        "label": sketch.Label,
        "geometry": [geo.copy() for geo in sketch.Geometry],
        "construction": [
            bool(getattr(geo, "Construction", False))
            for geo in sketch.Geometry
        ],
        "constraints": list(sketch.Constraints),
        "placement": sketch.Placement.copy(),
        "on_face": on_face,
    }


def _capture_feature(kernel, obj):
    params = {}
    for entry in kernel.get_params(obj.Name)["params"]:
        params[entry["prop"]] = entry["value"]
    for extra in ("Pitch", "Height"):
        if extra in params or not hasattr(obj, extra):
            continue
        value = getattr(obj, extra)
        params[extra] = float(getattr(value, "Value", value))
    through = False
    if obj.TypeId == "PartDesign::Pocket":
        through = str(getattr(obj, "Type", "")) == "ThroughAll"
    elif obj.TypeId == "PartDesign::Hole":
        through = str(getattr(obj, "DepthType", "")) == "ThroughAll"
    edges, faces = _base_indices(obj)
    return {
        "name": obj.Name,
        "type_id": obj.TypeId,
        "params": params,
        "profile": _linked_name(getattr(obj, "Profile", None)),
        "reversed": bool(getattr(obj, "Reversed", False)),
        "midplane": bool(getattr(obj, "Midplane", False)),
        "through": through,
        "edges": edges,
        "faces": faces,
    }


def capture_group(kernel, names):
    """Instantané d'un groupe : type, cotes, profil copié.

    Les habillages (congé, chanfrein) font partie du rejeu variable ;
    ``resolve_pattern_originals`` les refuse — c'est la répétition native.
    """
    if not isinstance(names, (list, tuple)) or not names:
        raise KernelError("aucune fonction à répéter — la liste features "
                          "est vide")
    body = kernel._require_body()
    doc = kernel._require_doc()
    in_body = {obj.Name for obj in body.Group}
    features = []
    sketches = {}
    seen = set()
    for raw in names:
        name = str(raw).strip()
        if name in seen:
            continue
        seen.add(name)
        obj = doc.getObject(name)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(name))
        if obj.Name not in in_body:
            raise KernelError(
                "{} n'appartient pas au corps actif".format(obj.Label))
        feat = _capture_feature(kernel, obj)
        if feat["type_id"] not in REPLAYABLE_TYPES:
            raise KernelError(
                "rejeu impossible pour {} ({})".format(
                    feat["name"], feat["type_id"]))
        features.append(feat)
        profile = feat.get("profile")
        if profile and profile not in sketches:
            sketch = doc.getObject(profile)
            if sketch is None or sketch.TypeId != "Sketcher::SketchObject":
                raise KernelError("esquisse inconnue : {}".format(profile))
            sketches[profile] = _dump_sketch(sketch)
    return {"features": features, "sketches": sketches}


def _substituted(feat, substitutions, prop):
    per_feature = substitutions.get(feat["name"])
    if isinstance(per_feature, dict) and prop in per_feature:
        return per_feature[prop]
    if prop in feat["params"]:
        return feat["params"][prop]
    raise KernelError(
        "cote {} absente de {}".format(prop, feat["name"]))


def _rebuild_sketch(kernel, dump, attach_face=None):
    body = kernel._require_body()
    doc = kernel._require_doc()
    clone = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(clone)
    clone.Label = dump.get("label") or "Esquisse"
    clone.Geometry = list(dump["geometry"])
    for index, flag in enumerate(dump.get("construction") or ()):
        try:
            clone.setConstruction(index, bool(flag))
        except Exception:
            pass
    clone.Constraints = list(dump["constraints"])
    if attach_face is not None:
        kernel._attach_to_face(clone, attach_face)
    elif dump.get("on_face"):
        clone.Placement = dump["placement"]
    else:
        kernel._attach_to_support(
            clone,
            [(kernel._origin_feature(kernel._PLANE_ROLES["XY"]), ("",))])
    doc.recompute()
    return clone


def _replay_feature(kernel, feat, sketch_map, substitutions):
    type_id = feat["type_id"]
    sketch = sketch_map.get(feat.get("profile"))
    if type_id == "PartDesign::Pad":
        kernel.add_pad(
            length=_substituted(feat, substitutions, "Length"),
            sketch=sketch,
            reversed=feat["reversed"],
            midplane=feat["midplane"])
        return
    if type_id == "PartDesign::Pocket":
        if feat["through"]:
            kernel.add_pocket(through=True, sketch=sketch,
                              reversed=feat["reversed"])
        else:
            kernel.add_pocket(
                length=_substituted(feat, substitutions, "Length"),
                sketch=sketch, reversed=feat["reversed"])
        return
    if type_id == "PartDesign::Revolution":
        kernel.add_revolution(
            angle=_substituted(feat, substitutions, "Angle"),
            sketch=sketch)
        return
    if type_id == "PartDesign::Groove":
        kernel.add_groove(
            angle=_substituted(feat, substitutions, "Angle"),
            sketch=sketch)
        return
    if type_id == "PartDesign::Fillet":
        radius = _substituted(feat, substitutions, "Radius")
        if feat["edges"]:
            kernel.add_fillet(radius=radius, edges=feat["edges"])
        elif feat["faces"]:
            kernel.add_fillet(radius=radius, face=feat["faces"][0])
        else:
            raise KernelError(
                "congé sans arête ni face : {}".format(feat["name"]))
        return
    if type_id == "PartDesign::Chamfer":
        size = _substituted(feat, substitutions, "Size")
        if feat["edges"]:
            kernel.add_chamfer(size=size, edges=feat["edges"])
        elif feat["faces"]:
            kernel.add_chamfer(size=size, face=feat["faces"][0])
        else:
            raise KernelError(
                "chanfrein sans arête ni face : {}".format(feat["name"]))
        return
    if type_id == "PartDesign::Draft":
        if not feat["faces"]:
            raise KernelError(
                "dépouille sans face : {}".format(feat["name"]))
        kernel.add_draft(
            face=feat["faces"][0],
            angle=_substituted(feat, substitutions, "Angle"))
        return
    if type_id == "PartDesign::Thickness":
        if not feat["faces"]:
            raise KernelError("coque sans face : {}".format(feat["name"]))
        kernel.add_thickness(
            face=feat["faces"][0],
            thickness=_substituted(feat, substitutions, "Value"))
        return
    if type_id == "PartDesign::Hole":
        # add_hole consomme _latest_sketch — le profil a été cloné juste avant.
        diameter = _substituted(feat, substitutions, "Diameter")
        if feat["through"]:
            kernel.add_hole(diameter=diameter, through=True)
        else:
            kernel.add_hole(
                diameter=diameter,
                depth=_substituted(feat, substitutions, "Depth"))
        return
    raise KernelError(
        "rejeu impossible pour {} ({})".format(feat["name"], type_id))


def _purge_named(kernel, names):
    doc = kernel._require_doc()
    remaining = [name for name in names if doc.getObject(name) is not None]
    # Enfants avant les corps, pour ne pas laisser d'orphelins.
    remaining.sort(
        key=lambda name: 0 if (doc.getObject(name) is not None
                               and doc.getObject(name).TypeId
                               != "PartDesign::Body") else 1)
    for name in remaining:
        try:
            if doc.getObject(name) is not None:
                doc.removeObject(name)
        except Exception:
            pass
    try:
        doc.recompute()
    except Exception:
        pass


def _object_names(kernel):
    return {obj.Name for obj in kernel._require_doc().Objects}


def replay_group(kernel, captured, substitutions=None, offset=(0.0, 0.0, 0.0)):
    """Rejoue le groupe dans un corps temporaire et rend sa forme.

    Le corps temporaire (et tout ce qu'il a créé) est toujours détruit,
    y compris si une instance échoue.
    """
    substitutions = substitutions or {}
    App = kernel._app()
    host = kernel._require_body()
    before = _object_names(kernel)
    try:
        temp = kernel._require_doc().addObject("PartDesign::Body", _TEMP_PREFIX)
        kernel._body = temp
        sketch_map = {}
        for feat in captured["features"]:
            profile = feat.get("profile")
            if profile and profile not in sketch_map:
                dump = captured["sketches"][profile]
                attach_face = None
                if dump.get("on_face"):
                    attach_face = kernel._top_face_id()
                clone = _rebuild_sketch(kernel, dump, attach_face)
                sketch_map[profile] = clone.Name
            _replay_feature(kernel, feat, sketch_map, substitutions)
        shape = temp.Shape.copy()
        dx, dy, dz = offset
        if dx or dy or dz:
            shape.translate(App.Vector(float(dx), float(dy), float(dz)))
        return shape
    finally:
        kernel._body = host
        created = [name for name in _object_names(kernel) - before]
        _purge_named(kernel, created)


def fuse_shapes(shapes):
    if not shapes:
        raise KernelError("aucune forme à réunir")
    result = shapes[0]
    for extra in shapes[1:]:
        result = result.fuse(extra)
    return result


def insert_via_tool_body(kernel, solid, mode="cut"):
    """Route du corps outil — même patron que la gravure et le graphe."""
    doc = kernel._require_doc()
    shape_feature = doc.addObject("Part::Feature", _TEMP_PREFIX + "Shape")
    shape_feature.Shape = solid
    shape_feature.Label = "Forme rejouée"
    tool_body = doc.addObject("PartDesign::Body", _TEMP_PREFIX + "Body")
    tool_body.Label = "Corps rejeu"
    tool_body.BaseFeature = shape_feature
    doc.recompute()
    try:
        kernel.add_boolean(tool=tool_body.Name, type=mode)
    except KernelError:
        for name in (tool_body.Name, shape_feature.Name):
            try:
                doc.removeObject(name)
            except Exception:
                pass
            try:
                doc.recompute()
            except Exception:
                pass
        raise


def _temp_bodies_left(kernel):
    doc = kernel._require_doc()
    return [
        obj.Name for obj in doc.Objects
        if obj.Name.startswith(_TEMP_PREFIX)
        or (obj.TypeId == "PartDesign::Body"
            and str(obj.Label).startswith("Rejeu"))
    ]


def probe_dressup_breakage(kernel):
    """Congé sur Edge3 d'un bossage, hauteur substituée.

    Mesure, ne devine pas : à partir de quelle hauteur le rejeu casse,
    et ce que devient Edge3 quand un enlèvement change la topologie.
    """
    kernel.new_part("N009 habillage")
    kernel.add_rect_sketch(20, 20)
    tree = kernel.add_pad(20)
    pad_name = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pad")
    n_edges_box = len(kernel._require_body().Shape.Edges)
    # Edge3 = indice 2 — le prompt parle de cet index-là.
    tree = kernel.add_fillet(radius=3, edges=[2])
    fillet_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Fillet")
    captured = capture_group(kernel, [pad_name, fillet_name])
    heights = (20, 15, 12, 10, 8, 7, 6, 5, 4, 3, 2)
    ok = []
    first_break = None
    first_reason = None
    for height in heights:
        try:
            replay_group(
                kernel, captured,
                substitutions={pad_name: {"Length": float(height)}})
            ok.append(height)
        except KernelError as exc:
            first_break = height
            first_reason = str(exc)
            break

    kernel.new_part("N009 habillage topologie")
    kernel.add_rect_sketch(20, 20)
    kernel.add_pad(20)
    kernel.add_rect_sketch(8, 8, face=kernel._top_face_id())
    kernel.add_pocket(through=True)
    n_edges_pocket = len(kernel._require_body().Shape.Edges)

    leftover = _temp_bodies_left(kernel)
    return {
        "edge": "Edge3",
        "radius": 3,
        "edges_on_pad": n_edges_box,
        "edges_after_pocket": n_edges_pocket,
        "heights_ok": ok,
        "first_break": first_break,
        "reason": first_reason,
        "cleanup_ok": leftover == [],
    }


def measure_replay_cost(kernel, captured, counts=(10, 50, 200)):
    import time
    times = {}
    for count in counts:
        started = time.perf_counter()
        for index in range(count):
            replay_group(
                kernel, captured, substitutions={},
                offset=(float(index) * 50.0, 0.0, 0.0))
        times[str(count)] = round(time.perf_counter() - started, 3)
    leftover = _temp_bodies_left(kernel)
    times["cleanup_ok"] = leftover == []
    return times


def run_minimal_spike(kernel):
    """Cas minimal : deux fonctions, trois variations, volume attendu.

    Groupe = bossage 20×20 × L + enlèvement 8×8 à travers tout.
    Variations L = 10, 20, 30, décalées de 40 mm. Coupées d'un hôte
    200×80×40 via la route du corps outil.
    """
    kernel.new_part("N009 spike variable")
    kernel.add_rect_sketch(20, 20)
    tree = kernel.add_pad(10)
    pad_name = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pad")
    kernel.add_rect_sketch(8, 8, face=kernel._top_face_id())
    tree = kernel.add_pocket(through=True)
    pocket_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pocket")
    captured = capture_group(kernel, [pad_name, pocket_name])

    before_fail = _object_names(kernel)
    failed_clean = False
    try:
        replay_group(
            kernel, captured,
            substitutions={pad_name: {"Length": 0.0}})
    except KernelError:
        failed_clean = _object_names(kernel) == before_fail
    if not failed_clean:
        _purge_named(
            kernel, list(_object_names(kernel) - before_fail))

    lengths = (10.0, 20.0, 30.0)
    shapes = []
    for index, length in enumerate(lengths):
        shapes.append(replay_group(
            kernel, captured,
            substitutions={pad_name: {"Length": length}},
            offset=(float(index) * 40.0, 0.0, 0.0)))
    fused = fuse_shapes(shapes)
    fused_volume = float(fused.Volume)
    # 20×20×L − 8×8×L = 336 L ; 10+20+30 → 20160.
    expected_fused = 336.0 * sum(lengths)

    template = kernel._require_body().Name
    kernel.add_body("Hote")
    kernel.add_rect_sketch(200, 80)
    kernel.add_pad(40)
    host_volume = float(kernel._require_body().Shape.Volume)
    insert_via_tool_body(kernel, fused, mode="cut")
    cut_volume = float(kernel._require_body().Shape.Volume)
    expected_cut = host_volume - expected_fused

    leftover = _temp_bodies_left(kernel)
    # Le corps outil absorbé par le booléen peut rester dans Group.
    absorbed = True
    for name in leftover:
        obj = kernel._require_doc().getObject(name)
        if obj is None:
            continue
        parent = obj.getParentGeoFeatureGroup()
        if parent is None or parent.Name == template:
            absorbed = False
            break

    def _close(actual, expected, tol=1e-3):
        scale = abs(float(expected)) or 1.0
        return abs(float(actual) - float(expected)) <= tol * scale

    return {
        "ok": (
            _close(fused_volume, expected_fused)
            and _close(cut_volume, expected_cut)
            and failed_clean
            and absorbed
        ),
        "fused_volume": fused_volume,
        "expected_fused": expected_fused,
        "cut_volume": cut_volume,
        "expected_cut": expected_cut,
        "failed_instance_cleaned": failed_clean,
        "tool_absorbed": absorbed,
        "captured_types": [feat["type_id"] for feat in captured["features"]],
    }


def run_spike_report(kernel):
    """Selftest : cas minimal + habillage + coût 10/50/200."""
    minimal = run_minimal_spike(kernel)
    dressup = probe_dressup_breakage(kernel)

    kernel.new_part("N009 coût")
    kernel.add_rect_sketch(20, 20)
    tree = kernel.add_pad(10)
    pad_name = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pad")
    kernel.add_rect_sketch(8, 8, face=kernel._top_face_id())
    tree = kernel.add_pocket(through=True)
    pocket_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pocket")
    tree = kernel.add_fillet(radius=1, face=kernel._top_face_id())
    fillet_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Fillet")
    captured_three = capture_group(
        kernel, [pad_name, pocket_name, fillet_name])
    cost = measure_replay_cost(kernel, captured_three)

    return {
        "minimal": minimal,
        "dressup": dressup,
        "cost": cost,
        "reconstitution": reconstitution_table(),
    }
