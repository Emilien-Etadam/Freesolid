"""Rejeu d'un groupe de fonctions, avec garde de topologie (N010).

Le moteur de rejeu (N009) n'est pas réécrit : capture, rejeu, fusion,
insertion. N010 y ajoute la garde, le plafond d'instances, et le
rejeu tout-ou-rien. FreeCAD n'est importé que dans les corps de
fonctions.
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
    "add_repeat_feature": "JSON de répétition, pas un profil",
    "add_curve3d": "liste de points",
    "add_body": "pas une fonction du groupe",
    "add_joint": "assemblage",
}

#: Fonctions qui portent un indice d'arête ou de face — la garde s'applique.
INDEXED_TYPES = frozenset({
    "PartDesign::Fillet",
    "PartDesign::Chamfer",
    "PartDesign::Draft",
    "PartDesign::Thickness",
})

#: Plafond d'instances d'une répétition variable — mesuré jusqu'à 200
#: par le spike ; 500 laisse de la marge sans attente illimitée.
REPEAT_INSTANCE_MAX = 500

_TEMP_PREFIX = "N009Replay"


def reconstitution_table():
    """Tableau figé : ce qui se reconstitue, et ce qui ne se reconstitue pas."""
    return {
        "replayable": dict(REPLAYABLE_TYPES),
        "replayable_with_extra": dict(REPLAYABLE_WITH_EXTRA),
        "unreplayable": dict(UNREPLAYABLE_OPS),
    }


def _is_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == value and abs(value) != float("inf")


def _sub_kind_index(name):
    """« Edge3 » → (« Edge », 3) ; nom illisible → (None, None)."""
    if not isinstance(name, str):
        return None, None
    if name.startswith("Edge"):
        rest = name[4:]
        family = "Edge"
    elif name.startswith("Face"):
        rest = name[4:]
        family = "Face"
    else:
        return None, None
    if not rest.isdigit():
        return None, None
    return family, int(rest)


def topology_verdict(expected, actual):
    """Rend None si le rejeu est sûr, sinon la raison, en français.

    Compare le compte d'arêtes et de faces, puis le type des
    sous-éléments réellement référencés. Deux arêtes de même type qui
    échangent leur indice passent la garde : elle réduit le risque,
    elle ne l'annule pas.
    """
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return "empreinte topologique illisible"
    exp_edges = expected.get("edges")
    exp_faces = expected.get("faces")
    act_edges = actual.get("edges")
    act_faces = actual.get("faces")
    if exp_edges != act_edges or exp_faces != act_faces:
        return (
            "la topologie a changé : {} arêtes et {} faces attendues, "
            "{} arêtes et {} faces obtenues".format(
                exp_edges, exp_faces, act_edges, act_faces)
        )
    kinds_expected = expected.get("kinds") or {}
    kinds_actual = actual.get("kinds") or {}
    if not isinstance(kinds_expected, dict):
        kinds_expected = {}
    if not isinstance(kinds_actual, dict):
        kinds_actual = {}
    for key, wanted in kinds_expected.items():
        family, index = _sub_kind_index(key)
        if family is None:
            continue
        count = act_edges if family == "Edge" else act_faces
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        noun = "arêtes" if family == "Edge" else "faces"
        if index < 1 or index > count:
            return (
                "{} est hors bornes : la forme n'a que {} {}".format(
                    key, count, noun)
            )
        got = kinds_actual.get(key)
        if got is not None and got != wanted:
            return "{} était {}, elle est {}".format(key, wanted, got)
    return None


def attachment_verdict(expected, actual):
    """Rend None si l'esquisse se repose au même endroit, sinon la raison.

    Compare le compte de faces candidates (normale.z > 0.5), le type
    de la face retenue, et sa normale arrondie. Deux faces candidates
    de même type qui échangent leur rang de hauteur passent : la garde
    réduit le risque, elle ne l'annule pas.
    """
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return "empreinte d'attache illisible"
    exp_n = expected.get("candidates")
    act_n = actual.get("candidates")
    if exp_n != act_n:
        return (
            "le nombre de faces candidates a changé : {} attendues, "
            "{} obtenues".format(exp_n, act_n)
        )
    exp_kind = expected.get("kind")
    act_kind = actual.get("kind")
    if exp_kind != act_kind:
        return "la face d'attache était {}, elle est {}".format(
            exp_kind, act_kind)
    exp_normal = expected.get("normal")
    act_normal = actual.get("normal")
    if exp_normal != act_normal:
        return (
            "la normale d'attache a changé : {} attendue, {} obtenue"
            .format(exp_normal, act_normal)
        )
    return None


#: Seuil partagé avec ``Kernel._top_face_id`` — une face « vers le haut ».
_UPWARD_Z = 0.5


def _geom_kind(geom):
    type_id = getattr(geom, "TypeId", None)
    if isinstance(type_id, str) and type_id:
        name = type_id.rsplit(":", 1)[-1]
        if name.startswith("Geom"):
            name = name[4:]
        return name
    name = type(geom).__name__
    if name.startswith("Geom"):
        name = name[4:]
    return name


def shape_fingerprint(shape, edges, faces):
    """Empreinte d'une forme aux indices déjà lus par ``_base_indices``.

    ``kinds`` ne porte que les sous-éléments réellement référencés.
    """
    n_edges = len(getattr(shape, "Edges", None) or ())
    n_faces = len(getattr(shape, "Faces", None) or ())
    kinds = {}
    for index in edges or ():
        key = "Edge{}".format(int(index) + 1)
        if 0 <= int(index) < n_edges:
            kinds[key] = _geom_kind(shape.Edges[int(index)].Curve)
    for index in faces or ():
        key = "Face{}".format(int(index) + 1)
        if 0 <= int(index) < n_faces:
            kinds[key] = _geom_kind(shape.Faces[int(index)].Surface)
    return {"edges": n_edges, "faces": n_faces, "kinds": kinds}


def attachment_fingerprint(shape):
    """Empreinte de la face d'attache choisie par ``_top_face_id``.

    ``candidates`` compte les faces dont la normale pointe vers le haut
    (``normal.z > 0.5``). ``kind`` et ``normal`` décrivent celle dont
    le centroïde est le plus élevé. Le centroïde lui-même n'est pas
    une signature : il bouge dès qu'une cote change.
    """
    if shape is None or (hasattr(shape, "isNull") and shape.isNull()):
        return {"candidates": 0, "kind": None, "normal": None}
    faces = getattr(shape, "Faces", None) or ()
    candidates = 0
    best = None
    best_z = None
    best_normal = None
    for face in faces:
        try:
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        except Exception:
            continue
        if getattr(normal, "z", 0) <= _UPWARD_Z:
            continue
        candidates += 1
        try:
            z = float(face.CenterOfMass.z)
        except Exception:
            continue
        if best_z is None or z > best_z:
            best = face
            best_z = z
            best_normal = normal
    if best is None or best_normal is None:
        return {"candidates": candidates, "kind": None, "normal": None}
    return {
        "candidates": candidates,
        "kind": _geom_kind(best.Surface),
        "normal": [
            round(float(best_normal.x), 6),
            round(float(best_normal.y), 6),
            round(float(best_normal.z), 6),
        ],
    }


def split_repeat_source(instances, graph):
    """Exclusif : graphe **ou** instances. Rend ``('graph'|'instances', valeur)``."""
    has_graph = graph is not None
    has_instances = instances is not None
    if has_graph and has_instances:
        raise KernelError(
            "la répétition attend un graphe ou une liste d'instances, "
            "pas les deux")
    if not has_graph and not has_instances:
        raise KernelError(
            "la répétition attend un graphe ou une liste d'instances")
    if has_graph:
        if not isinstance(graph, dict):
            raise KernelError("graphe de répétition illisible")
        return "graph", graph
    if not isinstance(instances, (list, tuple)):
        raise KernelError("instances doit être une liste")
    return "instances", instances


def parse_repeat_instances(instances, feature_names):
    """Valide la liste ``instances`` d'une répétition variable.

    ``params`` : des nombres, indexés par nom de fonction source.
    Fonction pure — pas d'import FreeCAD.
    """
    known = set(feature_names)
    if not isinstance(instances, (list, tuple)):
        raise KernelError("instances doit être une liste")
    if not instances:
        raise KernelError(
            "aucune instance à répéter — la liste instances est vide")
    if len(instances) > REPEAT_INSTANCE_MAX:
        raise KernelError(
            "trop d'instances ({} ; max. {})".format(
                len(instances), REPEAT_INSTANCE_MAX))
    parsed = []
    for position, raw in enumerate(instances):
        number = position + 1
        if not isinstance(raw, dict):
            raise KernelError(
                "instance n° {} : objet attendu".format(number))
        offset = raw.get("offset", [0.0, 0.0, 0.0])
        if not isinstance(offset, (list, tuple)) or len(offset) != 3:
            raise KernelError(
                "instance n° {} : offset invalide".format(number))
        if not all(_is_finite_number(value) for value in offset):
            raise KernelError(
                "instance n° {} : offset invalide".format(number))
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise KernelError(
                "instance n° {} : params doit être un objet".format(number))
        cleaned = {}
        for feat_name, props in params.items():
            if feat_name not in known:
                raise KernelError(
                    "instance n° {} : fonction inconnue « {} »".format(
                        number, feat_name))
            if not isinstance(props, dict):
                raise KernelError(
                    "instance n° {} : params de {} doit être un objet"
                    .format(number, feat_name))
            cleaned_props = {}
            for prop, value in props.items():
                if not isinstance(prop, str) or not prop:
                    raise KernelError(
                        "instance n° {} : nom de cote invalide".format(number))
                if not _is_finite_number(value):
                    raise KernelError(
                        "instance n° {} : les params sont des nombres, "
                        "pas une expression".format(number))
                cleaned_props[prop] = float(value)
            cleaned[feat_name] = cleaned_props
        parsed.append({
            "offset": (float(offset[0]), float(offset[1]), float(offset[2])),
            "params": cleaned,
        })
    return parsed


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


def _support_shape(sketch):
    """Forme de l'objet d'appui d'une esquisse, ou None."""
    support = getattr(sketch, "AttachmentSupport", None)
    if support is None:
        support = getattr(sketch, "Support", None)
    for obj, _subs in Kernel._iter_link_subs(support):
        shape = getattr(obj, "Shape", None)
        if shape is None:
            continue
        if hasattr(shape, "isNull") and shape.isNull():
            continue
        return shape
    return None


def _dump_sketch(sketch, body_shape=None):
    on_face = False
    support = getattr(sketch, "AttachmentSupport", None)
    if support is None:
        support = getattr(sketch, "Support", None)
    for _obj, subs in Kernel._iter_link_subs(support):
        if any(str(item).startswith("Face") for item in subs):
            on_face = True
            break
    dump = {
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
    if on_face:
        shape = _support_shape(sketch)
        if shape is None:
            shape = body_shape
        dump["attachment"] = attachment_fingerprint(shape)
    return dump


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
    feat = {
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "params": params,
        "profile": _linked_name(getattr(obj, "Profile", None)),
        "reversed": bool(getattr(obj, "Reversed", False)),
        "midplane": bool(getattr(obj, "Midplane", False)),
        "through": through,
        "edges": edges,
        "faces": faces,
    }
    if obj.TypeId in INDEXED_TYPES:
        base = getattr(obj, "BaseFeature", None)
        shape = getattr(base, "Shape", None) if base is not None else None
        if shape is None or (hasattr(shape, "isNull") and shape.isNull()):
            raise KernelError(
                "capture refusée : {} n'a pas de BaseFeature "
                "(fonction à indices en tête de corps)".format(obj.Label))
        feat["topology"] = shape_fingerprint(shape, edges, faces)
    return feat


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
    body_shape = getattr(body, "Shape", None)
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
            sketches[profile] = _dump_sketch(sketch, body_shape)
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


def _topology_refusal(feat, reason, instance=None, instance_count=None):
    label = feat.get("label") or feat.get("name") or "?"
    if instance is not None and instance_count is not None:
        return KernelError(
            "répétition refusée : instance n° {} sur {}, "
            "fonction « {} », {}".format(
                instance, instance_count, label, reason))
    return KernelError(
        "rejeu refusé : fonction « {} », {}".format(label, reason))


def _attachment_refusal(dump, reason, instance=None, instance_count=None):
    label = dump.get("label") or dump.get("name") or "?"
    if instance is not None and instance_count is not None:
        return KernelError(
            "répétition refusée : instance n° {} sur {}, "
            "esquisse « {} », {}".format(
                instance, instance_count, label, reason))
    return KernelError(
        "rejeu refusé : esquisse « {} », {}".format(label, reason))


def replay_group(kernel, captured, substitutions=None, offset=(0.0, 0.0, 0.0),
                 instance=None, instance_count=None):
    """Rejoue le groupe dans un corps temporaire et rend sa forme.

    Le corps temporaire (et tout ce qu'il a créé) est toujours détruit,
    y compris si une instance échoue. Une fonction à indices dont
    l'empreinte a bougé lève plutôt que de produire une géométrie
    subtilement fausse.
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
                    expected = dump.get("attachment")
                    if expected is not None:
                        actual = attachment_fingerprint(temp.Shape)
                        reason = attachment_verdict(expected, actual)
                        if reason:
                            raise _attachment_refusal(
                                dump, reason, instance, instance_count)
                    attach_face = kernel._top_face_id()
                clone = _rebuild_sketch(kernel, dump, attach_face)
                sketch_map[profile] = clone.Name
            expected = feat.get("topology")
            if expected is not None:
                actual = shape_fingerprint(
                    temp.Shape, feat["edges"], feat["faces"])
                reason = topology_verdict(expected, actual)
                if reason:
                    raise _topology_refusal(
                        feat, reason, instance, instance_count)
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


def replay_instances(kernel, captured, instances):
    """Rejoue toutes les instances, tout ou rien, et rend la forme fusionnée.

    Une instance qui échoue à la garde annule la répétition entière :
    pas d'instance sautée, pas de géométrie partielle.
    """
    names = [feat["name"] for feat in captured["features"]]
    parsed = parse_repeat_instances(instances, names)
    total = len(parsed)
    shapes = []
    for index, inst in enumerate(parsed):
        shapes.append(replay_group(
            kernel, captured,
            substitutions=inst["params"],
            offset=inst["offset"],
            instance=index + 1,
            instance_count=total,
        ))
    return fuse_shapes(shapes)


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


def _owner_name(obj):
    """Nom du groupe / booléen / corps qui détient *obj*, ou None."""
    parent = obj.getParentGeoFeatureGroup()
    if parent is not None:
        return parent.Name
    doc = obj.Document
    for other in doc.Objects:
        group = list(getattr(other, "Group", None) or [])
        if obj in group:
            return other.Name
    inlist = list(getattr(obj, "InList", None) or [])
    if inlist:
        return inlist[0].Name
    return None


def _tools_absorbed(kernel, leftover, template_name):
    """Vrai si chaque artefact N009Replay est absorbé (pas un fuyard)."""
    doc = kernel._require_doc()
    for name in leftover:
        obj = doc.getObject(name)
        if obj is None:
            continue
        owner = _owner_name(obj)
        if owner is None or owner == template_name:
            return False
    return True


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
    absorbed = _tools_absorbed(kernel, leftover, template)

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
        "leftover": leftover,
        "captured_types": [feat["type_id"] for feat in captured["features"]],
    }


def _edge_sig(edge):
    center = edge.CenterOfMass
    return (
        round(float(center.x), 4),
        round(float(center.y), 4),
        round(float(center.z), 4),
        round(float(edge.Length), 4),
    )


def probe_stale_index(kernel):
    """Congé sur un indice qui ne désigne plus la même arête.

    Un enlèvement centré 8×8 laisse Edge3 intacte mais **renumérote**
    d'autres arêtes. On prend le premier indice dont la géométrie a
    changé, et on lui applique le congé : erreur, ou silence ?
    """
    kernel.new_part("N009 indice périmé")
    kernel.add_rect_sketch(20, 20)
    kernel.add_pad(20)
    box_edges = kernel._require_body().Shape.Edges
    before = [_edge_sig(edge) for edge in box_edges]
    kernel.add_rect_sketch(8, 8, face=kernel._top_face_id())
    kernel.add_pocket(through=True)
    after_edges = kernel._require_body().Shape.Edges
    after = [_edge_sig(edge) for edge in after_edges]
    changed = [
        index for index, sig in enumerate(before)
        if index >= len(after) or after[index] != sig
    ]
    stale = changed[0] if changed else None
    volume_before = float(kernel._require_body().Shape.Volume)
    error = None
    mode = "aucun_changement"
    volume_after = volume_before
    if stale is not None:
        try:
            kernel.add_fillet(radius=2, edges=[stale])
        except KernelError as exc:
            error = str(exc)
            mode = "erreur"
        else:
            volume_after = float(kernel._require_body().Shape.Volume)
            if abs(volume_after - volume_before) < 1e-6:
                mode = "noop"
            else:
                mode = "silencieux"
    return {
        "edges_on_pad": len(before),
        "edges_after_pocket": len(after),
        "changed_indices": changed,
        "stale_index": stale,
        "sig_before": None if stale is None else before[stale],
        "sig_after": None if stale is None or stale >= len(after) else after[stale],
        "mode": mode,
        "error": error,
        "volume_before_fillet": volume_before,
        "volume_after_fillet": volume_after,
    }


def run_spike_report(kernel):
    """Selftest : cas minimal + habillage + coût 10/50/200."""
    minimal = run_minimal_spike(kernel)
    dressup = probe_dressup_breakage(kernel)
    stale = probe_stale_index(kernel)

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
        "stale_index": stale,
        "cost": cost,
        "reconstitution": reconstitution_table(),
    }
