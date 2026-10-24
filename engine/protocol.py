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

from engine.ops import CORE_OPS
from engine.ops._base import Name, Req as _Req  # noqa: F401 — ré-exportés

#: Comptes / occurrences : entier ≥ 1, plafond anti-absurde.
_COUNT_PARAMS = frozenset({"count", "cols", "rows", "sides"})
_COUNT_MIN = 1
_COUNT_MAX = 10000

#: Noms d'objets / ops — str non vide (``text`` est du contenu, pas un nom).
_NONEMPTY_STR_PARAMS = frozenset({
    "op", "feature", "sketch", "body", "tool", "component",
    "component1", "component2", "name", "label", "path", "prop",
    "profile", "spine", "surface", "kind", "a_kind", "b_kind",
})


_TYPE_LABELS = {
    float: "nombre",
    int: "entier",
    str: "texte",
    Name: "texte",
    list: "liste",
    dict: "objet",
    bool: "booléen",
}

#: Every operation the engine accepts, with the params it requires.
#: Values stay name-tuples; typed specs use ``(name, type)``. Optional
#: params are documented in the kernel docstrings and are not typed here.
OPS: dict[str, tuple[str, ...]] = {
    "ping": (),
    "document_status": (),             # ouvert, modifié depuis l'enregistrement
    "list_plugins": (),            # nom + point d'entrée JS de chaque plugin chargé
    # Runs the full flow headless and returns stats — the same
    # paste-me-the-report loop that debugged the Qt addon.
    "selftest": (),
    "new_part": (),                    # optional: name
    # Phase E — évaluer + mise en plan.
    "mass_properties": (),             # optional: density (g/cm³)
    "material_library": (),            # lecture : matières proposées
    "list_templates": (),              # lecture : gabarits de pièce
    "set_folder": _Req(("features", list), optional={"folder": str}),
    "rename_folder": _Req(("folder", str), optional={"name": str}),
    "feature_relations": _Req(("feature", str)),  # lecture : parents, enfants
    "list_configurations": (),         # lecture : noms, active
    "add_configuration": _Req(("name", str)),
    "activate_configuration": _Req(("name", str)),
    "rename_configuration": _Req(("name", str), ("new_name", str)),
    "delete_configuration": _Req(("name", str)),
    "configuration_table": (),         # lecture : cotes par configuration
    "set_configuration_values": _Req(("values", dict)),
    "save_template": _Req(("name", str)),
    "new_from_template": _Req(("name", str)),
    "paste_feature": _Req(("feature", str), optional={
        "face": int, "plane": str, "datum": str}),
    "set_body_material": _Req(("body", str), optional={
        "material": str, "density": float}),
    "set_face_color": _Req(("faces", list), "color"),
    "measure": _Req(("a_kind", str), ("a_id", int),
                    ("b_kind", str), ("b_id", int)),  # face|edge + id
    "make_drawing": _Req(("path", str)),
                                       # optional: scale, dims (bool, défaut True),
                                       # section ("X"|"Y"|"Z") — 3 vues + cotes + coupe, export DXF
    "undo": _Req(optional={"steps": int}),  # une transaction = un Ctrl+Z
    "redo": _Req(optional={"steps": int}),
    "undo_history": (),                # lecture : pas à défaire / refaire
    "rebuild_errors": (),              # lecture : fonctions en erreur
    "set_comment": _Req(("feature", str), optional={"text": str}),
    "set_hidden": _Req(("objects", list), optional={"hidden": bool}),
    "edge_chain": _Req(("edge", int), optional={"mode": str, "face": int}),
    "set_suppressed": _Req(("features", list),
                           optional={"suppressed": bool}),
    "document_properties": (),         # lecture : auteur, société, libres
    "set_document_properties": _Req(("values", dict)),
    "export_part": _Req(("path", str)),  # .stl ou .step selon l'extension
    "preview": _Req(("op", str), ("params", dict)),
                                       # aperçu jaune : op exécutée puis annulée
    "progress": (),                    # avancement hors noyau — jamais de verrou
    "set_param": _Req(("feature", str), ("prop", str), "value"),
    "set_params": _Req(("feature", str), ("values", dict)),
                                       # valeur numérique OU expression
    # Paramétrique — variables globales (App::VarSet) et équations.
    "list_variables": (),
    "set_variable": _Req(("name", str), "value"),
    "delete_variable": _Req(("name", str)),
    "rename": _Req(("feature", str), ("label", str)),
    "get_params": _Req(("feature", str)),  # editable numeric properties
    "set_tip": (),                     # optional: feature — nom d'une
                                       # ligne d'historique (fonction,
                                       # esquisse libre, surface).
                                       # Absent = barre avant la première
    "tip_to_end": (),                  # back to the final state
    "delete_feature": _Req(("feature", str)),
    "reorder_feature": _Req(("feature", str), ("target", str),
                            optional={"after": bool}),
    "save_part": _Req(("path", str)),
    "open_part": _Req(("path", str)),
    "list_dir": _Req(optional={"path": str}),  # dossier ; absent = dossier personnel
    "get_tree": (),
    "rebuild": (),                     # recalcul forcé de tout l'arbre
    "tessellate": (),                  # optional: deviation
    "tessellate_edges": (),            # optional: deviation — picking d'arêtes
    # Les ops des plugins viennent de leur manifeste : fusionnées dans
    # OPS au chargement. Un plugin ne peut pas redéfinir une op du noyau.
}

# Migration vers le catalogue engine/ops/ : les familles décrites
# rejoignent les ops encore déclarées ci-dessus.
for _op in CORE_OPS:
    assert _op.name not in OPS, _op.name
    OPS[_op.name] = _op.req

#: Ops du noyau, avant fusion des plugins. Un plugin ne peut pas les redéfinir.
CORE_OP_NAMES = frozenset(OPS)

_PLUGIN_KINDS = {
    "int": int,
    "float": float,
    "str": str,
    "nom": Name,
    "list": list,
    "dict": dict,
    "bool": bool,
}


def req_from_plugin_op(spec) -> tuple:
    """Convertit la spec d'un manifeste en entrée ``OPS``."""
    if not spec:
        return ()
    requis = spec.get("requis") or {}
    optionnels = spec.get("optionnels") or {}
    items = tuple(
        (name, _PLUGIN_KINDS[kind]) for name, kind in requis.items())
    optional = {
        name: _PLUGIN_KINDS[kind] for name, kind in optionnels.items()}
    if not items and not optional:
        return ()
    return _Req(*items, optional=optional or None)


def _merge_plugin_ops():
    """Fusionne les ops des manifestes. Collision → ce plugin seul est refusé."""
    from engine.plugins import discover
    for manifest in discover(reserved=CORE_OP_NAMES):
        pending = {}
        collision = False
        for name, spec in (manifest.get("ops") or {}).items():
            if name in OPS:
                collision = True
                break
            pending[name] = req_from_plugin_op(spec)
        if collision:
            continue
        OPS.update(pending)


_merge_plugin_ops()


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
    if kind is str or kind is Name:
        if not isinstance(value, str):
            _type_error(name, str, value)
        if ((kind is Name or name in _NONEMPTY_STR_PARAMS)
                and not value.strip()):
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


def request_lang(payload) -> str:
    """Langue demandée par la requête (« lang »), français par défaut."""
    from engine.i18n import normalize_lang
    if not isinstance(payload, dict):
        return normalize_lang(None)
    return normalize_lang(payload.get("lang"))


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


def _assert_in_jail(resolved, *, allow_root=False):
    """Même prison que ``resolve_user_path``.

    ``allow_root`` autorise la racine elle-même (lister le dossier
    personnel). Un fichier n'a pas le droit d'être la racine.
    """
    matched_root = None
    for root in _allowed_path_roots():
        if _is_under_root(root, resolved):
            matched_root = root
            break
    if matched_root is None:
        raise ProtocolError("chemin hors du dossier autorisé")
    try:
        relative = os.path.relpath(resolved, matched_root)
    except ValueError:
        # Windows : un nom réservé (« nul », « con »…) se résout en
        # périphérique, sur un autre « lecteur » que la prison.
        raise ProtocolError("chemin hors du dossier autorisé") from None
    if relative == ".." or relative.startswith(".." + os.sep):
        raise ProtocolError("chemin hors du dossier autorisé")
    if relative == os.curdir:
        if allow_root:
            return matched_root
        raise ProtocolError("chemin hors du dossier autorisé")
    for component in relative.split(os.sep):
        if component.startswith("."):
            raise ProtocolError("chemin hors du dossier autorisé")
    return matched_root


#: Extensions qu'un dialogue peut montrer. Le filtre fin est côté client.
_LIST_EXTENSIONS = frozenset({
    ".fcstd", ".step", ".stp", ".stl", ".3mf", ".iges", ".igs",
})


def resolve_user_dir(path):
    """Dossier listable, ou lève ProtocolError. Vide : le dossier personnel."""
    if path is None or str(path).strip() == "":
        resolved = os.path.realpath(os.path.expanduser("~"))
    else:
        expanded = os.path.expanduser(str(path))
        if ".." in expanded.replace("\\", "/").split("/"):
            raise ProtocolError("chemin hors du dossier autorisé")
        resolved = os.path.realpath(expanded)
    _assert_in_jail(resolved, allow_root=True)
    if not os.path.isdir(resolved):
        raise ProtocolError("dossier introuvable")
    return resolved


def list_user_dir(path=None):
    """Contenu d'un dossier de la prison : dossiers, puis fichiers connus.

    Les noms qui commencent par ``.`` sont omis. Un lien dont la cible
    sort de la prison est omis aussi. ``parent`` est ``None`` si remonter
    sortirait de la prison.
    """
    resolved = resolve_user_dir(path)
    parent = os.path.dirname(resolved)
    parent_ok = None
    if parent and os.path.normcase(parent) != os.path.normcase(resolved):
        try:
            parent_ok = resolve_user_dir(parent)
        except ProtocolError:
            parent_ok = None
    try:
        names = os.listdir(resolved)
    except OSError as exc:
        raise ProtocolError("dossier introuvable") from exc
    entries = []
    for name in names:
        if not name or name.startswith("."):
            continue
        full = os.path.join(resolved, name)
        try:
            real = os.path.realpath(full)
        except OSError:
            continue
        try:
            _assert_in_jail(real, allow_root=True)
        except ProtocolError:
            continue
        if os.path.isdir(real):
            entries.append({"name": name, "kind": "dir"})
        elif os.path.isfile(real):
            ext = os.path.splitext(name)[1].lower()
            if ext in _LIST_EXTENSIONS:
                entries.append({"name": name, "kind": "file"})
    entries.sort(key=lambda entry: (entry["kind"] != "dir", entry["name"].casefold()))
    return {"path": resolved, "parent": parent_ok, "entries": entries}


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
    _assert_in_jail(resolved)

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


#: Clés que ``get_tree`` émet lui-même. Les autres viennent des plugins
#: (``tree_contribution``).
CORE_TREE_KEYS = frozenset({
    "body", "tip", "bodies", "planes", "features", "surfaces",
    "variables", "configurations",
})


def dangling_deps(tree):
    """Arêtes de ``tree`` dont la cible n'est aucun nœud du payload.

    Retour : liste de ``(nom du nœud source, nom de cible non résolue)``,
    dans l'ordre de parcours, vide quand l'arbre est cohérent.

    L'invariant que ``visible_deps`` promet — aucune arête pendante — se
    vérifie contre ce que le payload **expose**, jamais contre l'ensemble
    de noms qui a servi à le filtrer : c'est précisément là que les deux
    peuvent diverger. Toute section porteuse de noms compte donc comme
    cible légitime : ``features``, ``surfaces`` et leurs ``children``,
    ``planes``, ``bodies`` — et chaque liste qu'un plugin ajoute au
    payload (une clé hors de ``CORE_TREE_KEYS``).

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

    sections = [tree.get("features"), tree.get("surfaces"),
                tree.get("planes"), tree.get("bodies")]
    sections += [value for key, value in tree.items()
                 if key not in CORE_TREE_KEYS and isinstance(value, list)]
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
            the discretized polyline of that BREP edge, as ``(x, y, z)`` ;
            un troisième élément facultatif, la longueur exacte de l'arête,
            est recopié dans son groupe (``length``, barre d'état) ; un
            quatrième, le centre d'un cercle ou d'un arc (``center``, où
            s'aimante un clic de position).

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
    for edge_id, points, *extra in edge_lines:
        if len(points) < 2:
            continue
        start = len(indices)
        for x, y, z in points:
            positions.extend((float(x), float(y), float(z)))
        for i in range(len(points) - 1):
            indices.extend((vertex_base + i, vertex_base + i + 1))
        group = {
            "edgeId": edge_id,
            "start": start,
            "count": len(indices) - start,
        }
        if extra:
            group["length"] = round(float(extra[0]), 6)
        if len(extra) > 1 and extra[1] is not None:
            group["center"] = [round(float(v), 6) for v in extra[1]]
        groups.append(group)
        vertex_base += len(points)
    return {"positions": positions, "indices": indices, "groups": groups}
