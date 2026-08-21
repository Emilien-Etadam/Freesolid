"""Wire protocol between the web UI and the headless engine.

Single source of truth for operation names, request validation and payload
shapes. Pure Python — no FreeCAD, no networking — so every rule here is
unit-tested in CI, and both sides (server dispatch, JS client) are written
against the same contract.

Transport (M0) is HTTP JSON on localhost: requests are
``{"op": <name>, "params": {...}}``, responses are ``ok(...)`` or
``err(...)`` envelopes. No dependency on either side.
"""

import json
import os
import tempfile

class _Req(tuple):
    """Tuple of required param names, with optional JSON types.

    ``_Req(("length", float), "value")`` equals ``("length", "value")`` so
    existing ``OPS[op] == (...)`` assertions keep working. ``.kinds`` maps
    typed names to ``float``, ``int``, ``str``, ``list``, ``dict`` or
    ``bool``. ``.optional`` maps optional names to the same kinds — present
    params are type-checked, absent ones are not required. Bare names are
    presence-only (no type check, no coercion).
    """

    def __new__(cls, *items, optional=None):
        names = []
        kinds = {}
        for item in items:
            if isinstance(item, str):
                names.append(item)
            else:
                name, kind = item
                names.append(name)
                kinds[name] = kind
        obj = super().__new__(cls, names)
        obj.kinds = kinds
        obj.optional = dict(optional or {})
        return obj


#: Comptes / occurrences : entier ≥ 1, plafond anti-absurde.
_COUNT_PARAMS = frozenset({"count", "cols", "rows", "sides"})
_COUNT_MIN = 1
_COUNT_MAX = 10000

#: Noms d'objets / ops — str non vide (``text`` est du contenu, pas un nom).
_NONEMPTY_STR_PARAMS = frozenset({
    "op", "feature", "sketch", "body", "tool", "component",
    "component1", "component2", "name", "label", "path", "prop",
    "profile", "spine", "surface", "kind", "a_kind", "b_kind",
    "gem", "gemme",
})

_TYPE_LABELS = {
    float: "nombre",
    int: "entier",
    str: "texte",
    list: "liste",
    dict: "objet",
    bool: "booléen",
}

#: Every operation the engine accepts, with the params it requires.
#: Values stay name-tuples; typed specs use ``(name, type)``. Optional
#: params are documented in the kernel docstrings and are not typed here.
OPS: dict[str, tuple[str, ...]] = {
    "ping": (),
    # Runs the full flow headless and returns stats — the same
    # paste-me-the-report loop that debugged the Qt addon.
    "selftest": (),
    "new_part": (),                    # optional: name
    # Phase C — multi-corps.
    "add_body": (),                    # optional: name — devient le corps actif
    "set_active_body": _Req(("body", str)),
    "set_body_color": _Req(("body", str), "color"),
                                       # "#rrggbb" | null | "" (défaut)
    "add_boolean": _Req(("tool", str)),  # optional: type (cut|fuse|common)
    # Phase C — assemblage v1 (placements directs, sans solveur).
    "new_assembly": (),                # optional: name
    "insert_component": _Req(("path", str)),  # .FCStd — App::Link vers son corps
    "move_component": _Req(("component", str)),  # optional: x, y, z, yaw, pitch, roll
    "array_component": _Req(("component", str), ("count", int)),  # optional: dx, dy, dz
    "assembly_tree": (),
    "tessellate_assembly": (),         # optional: deviation
    # Phase C3 — contraintes d'assemblage (joints natifs + solveur MbD).
    "add_joint": _Req(("component1", str), ("component2", str)),
                                       # optional: type (fixe|pivot|
                                       # cylindrique|glissiere|rotule|
                                       # distance), sub1, sub2, distance
    "solve_assembly": (),
    "spike_assembly": (),              # rapport : joints Assembly headless ?
    # Phase D — surfacique (API Part, hors historique PartDesign) + courbes.
    "surface_extrude": _Req(("length", float)),  # optional: sketch — profil ouvert OK
    "surface_revolve": (),             # optional: angle, sketch
    "surface_loft": _Req(("sketches", list)),
    "surface_sew": _Req(("surfaces", list)),  # coudre ; solidifie si fermé
    "surface_thicken": _Req(("surface", str), ("thickness", float)),
    "add_curve3d": _Req(("points", list)),  # optional: spline — trajectoire 3D
    # Phase E — évaluer + mise en plan.
    "mass_properties": (),             # optional: density (g/cm³)
    "measure": _Req(("a_kind", str), ("a_id", int),
                    ("b_kind", str), ("b_id", int)),  # face|edge + id
    "make_drawing": _Req(("path", str)),
                                       # optional: scale, dims (bool, défaut True),
                                       # section ("X"|"Y"|"Z") — 3 vues + cotes + coupe, export DXF
    "add_text": _Req(("text", str), ("face", int)),
                                       # optional: size, depth, x, y, emboss, font
    "edit_text": _Req(("feature", str)),
                                       # optional: text, size, depth, x, y
                                       # — absents = inchangés
    "add_graph_feature": _Req(("graph", dict), ("mode", str)),
                                       # mode : fuse | cut
    "edit_graph_feature": _Req(("feature", str), ("graph", dict)),
    "get_graph_feature": _Req(("feature", str)),
    "add_repeat_feature": _Req(("features", list), ("instances", list),
                               ("mode", str)),
    "edit_repeat_feature": _Req(("feature", str), ("instances", list)),
    "get_repeat_feature": _Req(("feature", str)),
    "graph_vocabulary": (),             # lecture : types, libellés, ports
    "script_trust_status": (),          # lecture : Python autorisé ce document / session
    "authorize_scripts": (),            # consentement : jamais persisté dans le .FCStd
    "check_interference": (),          # assemblage : volumes communs par paires
    "undo": (),                        # une transaction = un Ctrl+Z
    "redo": (),
    "export_part": _Req(("path", str)),  # .stl ou .step selon l'extension
    "preview": _Req(("op", str), ("params", dict)),
                                       # aperçu jaune : op exécutée puis annulée
    "add_rect_sketch": _Req(("width", float), ("height", float)),
                                       # optional: face (id) to attach
    "add_pad": _Req(("length", float)),  # optional: sketch, reversed, midplane
    "add_pocket": (),                  # optional: length | through — sans profondeur = à travers tout ; reversed, sketch
    "add_fillet": _Req(("radius", float)),  # face OU edges (liste d'ids)
    "add_chamfer": _Req(("size", float)),  # face OU edges
    # Palier 2 — fonctions volumiques, aucune interaction nouvelle.
    "add_revolution": (),              # optional: angle (°), sketch
    "add_groove": (),                  # optional: angle (°), sketch
    "add_mirror": _Req(optional={"features": list}),
                                       # optional: plane (XY|XZ|YZ), features
    "add_linear_pattern": _Req(("length", float), ("count", int),
                               optional={"features": list}),
                                       # optional: axis (X|Y|Z), features
    "add_polar_pattern": _Req(("count", int),
                              optional={"features": list}),
                                       # optional: angle (°), axis, features
    "add_thickness": _Req(("face", int), ("thickness", float)),
    "add_draft": _Req(("face", int), ("angle", float)),
                                       # optional: neutral (XY|XZ|YZ)
    # Phase B — références et ossature.
    "add_datum_plane": (),             # optional: base (XY|XZ|YZ) | face, offset, angle
    "add_loft": _Req(("sketches", list)),  # optional: subtractive, ruled, closed
    "add_sweep": _Req(("profile", str), ("spine", str)),  # optional: subtractive
    "add_helix": _Req(("pitch", float), ("height", float)),  # optional: sketch
    "set_param": _Req(("feature", str), ("prop", str), "value"),
    "set_params": _Req(("feature", str), ("values", dict)),
                                       # valeur numérique OU expression
    # Paramétrique — variables globales (App::VarSet) et équations.
    "list_variables": (),
    "set_variable": _Req(("name", str), "value"),
    "delete_variable": _Req(("name", str)),
    "rename": _Req(("feature", str), ("label", str)),
    "add_hole": _Req(("diameter", float)),  # optional: depth | through, cut
                                       # (none|lamage|fraisage), cut_diameter,
                                       # cut_depth, cut_angle
    "get_params": _Req(("feature", str)),  # editable numeric properties
    "set_tip": (),                     # optional: feature — nom d'une
                                       # ligne d'historique (fonction,
                                       # esquisse libre, surface).
                                       # Absent = barre avant la première
    "tip_to_end": (),                  # back to the final state
    "delete_feature": _Req(("feature", str)),
    "save_part": _Req(("path", str)),
    "open_part": _Req(("path", str)),
    "get_tree": (),
    "tessellate": (),                  # optional: deviation
    "tessellate_edges": (),            # optional: deviation — picking d'arêtes
    # P034 — pierres aimantées sur une face. x,y,z = point du raycast ;
    # le moteur projette et retient (u, v), jamais le point reçu.
    "place_gem": _Req(("face", int), ("x", float), ("y", float), ("z", float),
                      optional={"gemme": str, "diametre": float,
                                "spin": float, "lift": float}),
    "move_gem": _Req(("gem", str), ("index", int),
                     ("x", float), ("y", float), ("z", float),
                     optional={"face": int}),
    "spin_gem": _Req(("gem", str), ("index", int),
                     optional={"spin": float, "lift": float}),
    "remove_gem": _Req(("gem", str), ("index", int)),
    "list_gems": (),
    # M2 — sketch editing. Geometry travels in sketch-local 2D; the state
    # carries the placement matrix that positions it in 3D.
    "sketch_start": (),                # optional: face | plane (XY|XZ|YZ) | datum (nom)
    "sketch_edit": _Req(("feature", str)),
    "sketch_state": _Req(("sketch", str)),
    "sketch_add_line": _Req(
        ("sketch", str), ("x1", float), ("y1", float),
        ("x2", float), ("y2", float)),
    "sketch_add_circle": _Req(
        ("sketch", str), ("cx", float), ("cy", float), ("r", float)),
    # Palier 3 — outils d'esquisse avancés. Angles en radians, sens trigo.
    "sketch_add_arc": _Req(
        ("sketch", str), ("cx", float), ("cy", float), ("r", float),
        ("a1", float), ("a2", float)),
    "sketch_add_spline": _Req(("sketch", str), ("points", list)),
                                       # interpolée par les points
    "sketch_add_ellipse": _Req(
        ("sketch", str), ("cx", float), ("cy", float),
        ("rx", float), ("ry", float)),  # optional: angle
    "sketch_mirror": _Req(("sketch", str), ("geos", list), ("axis", int)),
                                       # copies symétriques
    "sketch_array": _Req(
        ("sketch", str), ("geos", list), ("dx", float), ("dy", float),
        ("cols", int), ("rows", int)),
    "sketch_offset": _Req(
        ("sketch", str), ("geos", list), ("distance", float)),
                                       # optional: reversed
    "sketch_add_slot": _Req(
        ("sketch", str), ("x1", float), ("y1", float),
        ("x2", float), ("y2", float), ("width", float)),
    "sketch_add_polygon": _Req(
        ("sketch", str), ("cx", float), ("cy", float),
        ("x", float), ("y", float), ("sides", int)),
    "sketch_fillet": _Req(
        ("sketch", str), ("geo1", int), ("geo2", int),
        ("x1", float), ("y1", float), ("x2", float), ("y2", float),
        ("radius", float)),
    "sketch_trim": _Req(
        ("sketch", str), ("geo", int), ("x", float), ("y", float)),
    "sketch_constrain": _Req(("sketch", str), ("kind", str), ("geo1", int)),
                                       # optional: point1, geo2, point2, geo3
    "sketch_move": _Req(
        ("sketch", str), ("geo", int), ("point", int),
        ("x", float), ("y", float)),
    "sketch_dim": _Req(("sketch", str), ("geo", int)),
                                       # optional: value, geo2, point, point2
    "sketch_set_dim": _Req(("sketch", str), ("dim", int)),
                                       # optional: value | expr, name
    "sketch_constraints": _Req(("sketch", str)),
                                       # optional: geo — relations d'une entité
    "sketch_delete_constraint": _Req(("sketch", str), ("constraint", int)),
    "sketch_delete_geo": _Req(("sketch", str), ("geo", int)),
    "sketch_toggle_construction": _Req(("sketch", str), ("geo", int)),
    "sketch_convert": _Req(("sketch", str)),
                                       # optional: face — contour projeté, bloqué
    "sketch_finish": _Req(("sketch", str)),
}


class ProtocolError(Exception):
    """Malformed request. The message is safe to show to the client."""


def _received(value) -> str:
    """JSON-faithful rendering of a rejected value, for error messages."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def _is_bool(value) -> bool:
    return isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not _is_bool(value)


def _is_integral(value) -> bool:
    if _is_bool(value):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    return False


def _type_error(name: str, kind, value) -> None:
    raise ProtocolError(
        "paramètre {} : {} attendu, reçu {}".format(
            name, _TYPE_LABELS[kind], _received(value)))


def _check_param(name: str, kind, value) -> None:
    """Raise ProtocolError if *value* does not match *kind*. No coercion."""
    if kind is float:
        if not _is_number(value):
            _type_error(name, float, value)
        return
    if kind is int:
        if not _is_integral(value):
            _type_error(name, int, value)
        if name in _COUNT_PARAMS:
            number = int(value)
            if number < _COUNT_MIN or number > _COUNT_MAX:
                raise ProtocolError(
                    "paramètre {} : entier entre {} et {} attendu, reçu {}"
                    .format(name, _COUNT_MIN, _COUNT_MAX, _received(value)))
        return
    if kind is str:
        if not isinstance(value, str):
            _type_error(name, str, value)
        if name in _NONEMPTY_STR_PARAMS and not value.strip():
            raise ProtocolError(
                "paramètre {} : nom non vide attendu, reçu {}".format(
                    name, _received(value)))
        return
    if kind is list:
        if not isinstance(value, list):
            _type_error(name, list, value)
        return
    if kind is dict:
        if not isinstance(value, dict):
            _type_error(name, dict, value)
        return
    if kind is bool:
        if not _is_bool(value):
            _type_error(name, bool, value)
        return
    raise ProtocolError(
        "paramètre {} : type de schéma inconnu".format(name))


def _check_params(op: str, params: dict) -> None:
    spec = OPS[op]
    missing = [k for k in spec if k not in params]
    if missing:
        raise ProtocolError(
            "{} : paramètre(s) manquant(s) : {}".format(op, ", ".join(missing)))
    kinds = getattr(spec, "kinds", {})
    for name, kind in kinds.items():
        _check_param(name, kind, params[name])
    optional = getattr(spec, "optional", {})
    for name, kind in optional.items():
        if name in params:
            _check_param(name, kind, params[name])


def validate_request(payload) -> tuple[str, dict]:
    """Check an incoming request, returning ``(op, params)``.

    Raises ``ProtocolError`` with an actionable message otherwise — the
    client shows it verbatim, so it names what is missing or mistyped.
    Values are not coerced. Nested ``preview`` ops are re-validated
    against the same registry; ``preview`` of ``preview`` is refused.
    """
    if not isinstance(payload, dict):
        raise ProtocolError("la requête doit être un objet JSON")
    op = payload.get("op")
    if op not in OPS:
        raise ProtocolError(
            "opération inconnue {!r} — attendu l'une de : {}".format(
                op, ", ".join(sorted(OPS))))
    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        # Explicit None-check above: `or {}` would silently accept [] or "".
        raise ProtocolError("params doit être un objet JSON")
    _check_params(op, params)
    if op == "preview":
        nested_op = params["op"]
        if nested_op == "preview":
            raise ProtocolError("preview d'un preview refusé")
        validate_request({"op": nested_op, "params": params["params"]})
    return op, params


def ok(result) -> dict:
    return {"ok": True, "result": result}


def err(message: str, hint: str = "") -> dict:
    out = {"ok": False, "error": str(message)}
    if hint:
        out["hint"] = hint
    return out


def _allowed_path_roots():
    """Racines sous lesquelles les chemins client sont autorisés."""
    roots = [
        os.path.realpath(os.path.expanduser("~")),
        os.path.realpath(tempfile.gettempdir()),
    ]
    data_dir = os.environ.get("FREESOLID_DATA_DIR")
    if data_dir:
        roots.append(os.path.realpath(os.path.expanduser(str(data_dir))))
    return roots


def _is_under_root(root: str, resolved: str) -> bool:
    try:
        return os.path.commonpath([root, resolved]) == root
    except ValueError:
        return False


#: Ponctuation arithmétique autorisée dans une expression client.
#: Tout le reste (``<<Label>>``, indexation, chaînes, affectation…) est
#: refusé — le moteur d'expressions FreeCAD sait sinon référencer
#: n'importe quel objet du document.
_EXPR_PUNCT = frozenset(" _.,+-*/%^()")
_EXPR_MAX_LEN = 256


def validate_expression(text):
    """Expression paramétrique client — retourne le texte épuré,
    ou lève ProtocolError."""
    cleaned = str(text).strip() if text is not None else ""
    if not cleaned:
        raise ProtocolError("expression refusée — vide")
    if len(cleaned) > _EXPR_MAX_LEN:
        raise ProtocolError(
            "expression refusée — trop longue (max. {} caractères)".format(
                _EXPR_MAX_LEN))
    for ch in cleaned:
        if ch.isalpha() or ch in "0123456789" or ch in _EXPR_PUNCT:
            continue
        raise ProtocolError(
            "expression refusée — caractère non autorisé : «{}»".format(ch))
    return cleaned


def resolve_user_path(path, extensions, must_exist=False):
    """Résout un chemin fourni par le client, ou lève ProtocolError.

    Les symlinks sont résolus avant toute vérification. Le chemin doit
    rester sous le home, le répertoire temporaire, ou ``FREESOLID_DATA_DIR``
    s'il est défini. Aucun composant relatif à cette racine ne peut
    commencer par ``.`` (``.ssh``, ``.bashrc``, …).
    """
    if path is None or str(path).strip() == "":
        raise ProtocolError("chemin manquant")
    allowed_ext = {
        (e if e.startswith(".") else "." + e).lower()
        for e in extensions
    }
    if not allowed_ext:
        raise ProtocolError("extension non autorisée : (aucune)")

    expanded = os.path.expanduser(str(path))
    # Refuser les segments ``..`` avant realpath : ``~/../ailleurs`` ne
    # doit pas passer même si le résultat retombe sous le tempdir.
    if ".." in expanded.replace("\\", "/").split("/"):
        raise ProtocolError("chemin hors du dossier autorisé")
    resolved = os.path.realpath(expanded)
    matched_root = None
    for root in _allowed_path_roots():
        if _is_under_root(root, resolved):
            matched_root = root
            break
    if matched_root is None:
        raise ProtocolError("chemin hors du dossier autorisé")

    relative = os.path.relpath(resolved, matched_root)
    if relative == os.curdir or relative.startswith(".." + os.sep) or relative == "..":
        raise ProtocolError("chemin hors du dossier autorisé")
    for component in relative.split(os.sep):
        if component.startswith("."):
            raise ProtocolError("chemin hors du dossier autorisé")

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in allowed_ext:
        raise ProtocolError(
            "extension non autorisée : {}".format(ext or "(aucune)"))

    if must_exist:
        if not os.path.isfile(resolved):
            raise ProtocolError("fichier introuvable : {}".format(resolved))
    else:
        parent = os.path.dirname(resolved)
        if not os.path.isdir(parent):
            raise ProtocolError(
                "dossier parent introuvable : {}".format(parent))
    return resolved


def visible_deps(dep_names, known_names):
    """Noms de ``dep_names`` qui désignent un nœud de ``known_names``.

    Dédoublonne en conservant l'ordre d'entrée. Les cibles absentes de
    ``known_names`` (Origin, VarSet, artefacts internes) sont écartées :
    une arête n'est émise que si sa cible est elle-même un nœud du payload.
    """
    known = set(known_names)
    seen = set()
    names = []
    for name in dep_names:
        if name not in known or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def visible_dep_subs(dep_subs, known_names):
    """Sous-éléments dont la cible est un nœud de ``known_names``.

    ``dep_subs`` : ``{nom de cible: [sous-éléments]}``. Une cible hors
    payload n'émet rien — même règle que ``visible_deps``. Les listes
    vides et les sous-éléments vides (attache à l'objet entier) sont
    écartés. L'ordre des cibles et des noms est conservé.

    Fonction pure — pas d'import FreeCAD.
    """
    if not isinstance(dep_subs, dict):
        return {}
    known = set(known_names or ())
    result = {}
    for name, subs in dep_subs.items():
        if name not in known:
            continue
        seen = set()
        cleaned = []
        for sub in subs or ():
            if not isinstance(sub, str) or not sub or sub in seen:
                continue
            seen.add(sub)
            cleaned.append(sub)
        if cleaned:
            result[name] = cleaned
    return result


def dangling_deps(tree):
    """Arêtes de ``tree`` dont la cible n'est aucun nœud du payload.

    Retour : liste de ``(nom du nœud source, nom de cible non résolue)``,
    dans l'ordre de parcours, vide quand l'arbre est cohérent.

    L'invariant que ``visible_deps`` promet — aucune arête pendante — se
    vérifie contre ce que le payload **expose**, jamais contre l'ensemble
    de noms qui a servi à le filtrer : c'est précisément là que les deux
    peuvent diverger. Toute section porteuse de noms compte donc comme
    cible légitime : ``features``, ``surfaces`` et leurs ``children``,
    ``planes``, ``bodies``, ``gems``.

    Fonction pure sur un dictionnaire — pas d'import FreeCAD.
    """
    if not isinstance(tree, dict):
        return []

    def walk(items):
        """Entrées d'une section, enfants compris."""
        for item in items or ():
            if not isinstance(item, dict):
                continue
            yield item
            for child in walk(item.get("children")):
                yield child

    sections = (tree.get("features"), tree.get("surfaces"),
                tree.get("planes"), tree.get("bodies"), tree.get("gems"))
    known = set()
    for section in sections:
        for item in walk(section):
            name = item.get("name")
            if name:
                known.add(name)

    pendantes = []
    for section in sections:
        for item in walk(section):
            source = item.get("name") or ""
            for target in item.get("deps") or ():
                if target not in known:
                    pendantes.append((source, target))
    return pendantes


def pack_mesh(face_meshes) -> dict:
    """Flatten per-face tessellations into one indexed buffer.

    Args:
        face_meshes: iterable of ``(face_id, vertices, triangles)`` or
            ``(face_id, vertices, triangles, normals)`` where ``vertices``
            is a list of ``(x, y, z)``, ``triangles`` a list of
            ``(a, b, c)`` indices local to that face, and ``normals`` —
            optional — a list of ``(nx, ny, nz)`` aligned on ``vertices``.

    Returns:
        ``positions`` (flat xyz floats), ``indices`` (flat, rebased to the
        global buffer) and ``groups`` — one per face, ``{faceId, start,
        count}`` in *index* units. Picking works by construction: a raycast
        hit's triangle index maps to exactly one group, hence one OCCT face.
        ``normals`` is present iff at least one face supplied them — same
        length as ``positions``, zeros where a face had none.
    """
    positions: list[float] = []
    indices: list[int] = []
    groups: list[dict] = []
    normals: list[float] = []
    has_normals = False
    vertex_base = 0
    for item in face_meshes:
        if len(item) == 4:
            face_id, vertices, triangles, face_normals = item
            has_normals = True
        else:
            face_id, vertices, triangles = item
            face_normals = None
        start = len(indices)
        for x, y, z in vertices:
            positions.extend((float(x), float(y), float(z)))
        if face_normals is not None and len(face_normals) == len(vertices):
            for nx, ny, nz in face_normals:
                normals.extend((float(nx), float(ny), float(nz)))
        else:
            for _ in vertices:
                normals.extend((0.0, 0.0, 0.0))
        for a, b, c in triangles:
            indices.extend((a + vertex_base, b + vertex_base, c + vertex_base))
        groups.append({
            "faceId": face_id,
            "start": start,
            "count": len(indices) - start,
        })
        vertex_base += len(vertices)
    packed = {"positions": positions, "indices": indices, "groups": groups}
    if has_normals:
        packed["normals"] = normals
    return packed


def pack_edges(edge_lines) -> dict:
    """Flatten per-edge polylines into one indexed segment buffer.

    Args:
        edge_lines: iterable of ``(edge_id, points)`` where ``points`` is
            the discretized polyline of that BREP edge, as ``(x, y, z)``.

    Returns:
        ``positions``, ``indices`` (pairs — LineSegments) and ``groups``
        (``{edgeId, start, count}`` in index units). Same contract as
        ``pack_mesh``: a raycast hit's segment index maps to exactly one
        group, hence one OCCT edge. Picking by construction.
    """
    positions: list[float] = []
    indices: list[int] = []
    groups: list[dict] = []
    vertex_base = 0
    for edge_id, points in edge_lines:
        if len(points) < 2:
            continue
        start = len(indices)
        for x, y, z in points:
            positions.extend((float(x), float(y), float(z)))
        for i in range(len(points) - 1):
            indices.extend((vertex_base + i, vertex_base + i + 1))
        groups.append({
            "edgeId": edge_id,
            "start": start,
            "count": len(indices) - start,
        })
        vertex_base += len(points)
    return {"positions": positions, "indices": indices, "groups": groups}
