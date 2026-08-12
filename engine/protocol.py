"""Wire protocol between the web UI and the headless engine.

Single source of truth for operation names, request validation and payload
shapes. Pure Python — no FreeCAD, no networking — so every rule here is
unit-tested in CI, and both sides (server dispatch, JS client) are written
against the same contract.

Transport (M0) is HTTP JSON on localhost: requests are
``{"op": <name>, "params": {...}}``, responses are ``ok(...)`` or
``err(...)`` envelopes. No dependency on either side.
"""

#: Every operation the engine accepts, with the params it requires.
#: (name -> tuple of required param names). Optional params are documented
#: in the kernel docstrings.
OPS: dict[str, tuple[str, ...]] = {
    "ping": (),
    # Runs the full flow headless and returns stats — the same
    # paste-me-the-report loop that debugged the Qt addon.
    "selftest": (),
    "new_part": (),                    # optional: name
    # Phase C — multi-corps.
    "add_body": (),                    # optional: name — devient le corps actif
    "set_active_body": ("body",),
    "add_boolean": ("tool",),          # optional: type (cut|fuse|common)
    # Phase C — assemblage v1 (placements directs, sans solveur).
    "new_assembly": (),                # optional: name
    "insert_component": ("path",),     # .FCStd — App::Link vers son corps
    "move_component": ("component",),  # optional: x, y, z, yaw, pitch, roll
    "assembly_tree": (),
    "tessellate_assembly": (),         # optional: deviation
    # Phase C3 — contraintes d'assemblage (joints natifs + solveur MbD).
    "add_joint": ("component1", "component2"),  # optional: type (fixe|pivot|
                                       # cylindrique|glissiere|rotule|
                                       # distance), sub1, sub2, distance
    "solve_assembly": (),
    "spike_assembly": (),              # rapport : joints Assembly headless ?
    # Phase D — surfacique (API Part, hors historique PartDesign) + courbes.
    "surface_extrude": ("length",),    # optional: sketch — profil ouvert OK
    "surface_revolve": (),             # optional: angle, sketch
    "surface_loft": ("sketches",),
    "surface_sew": ("surfaces",),      # coudre ; solidifie si fermé
    "surface_thicken": ("surface", "thickness"),
    "add_curve3d": ("points",),        # optional: spline — trajectoire 3D
    # Phase E — évaluer + mise en plan.
    "mass_properties": (),             # optional: density (g/cm³)
    "measure": ("a_kind", "a_id", "b_kind", "b_id"),  # face|edge + id
    "make_drawing": ("path",),         # optional: scale — 3 vues, export DXF
    "add_text": ("text", "face"),      # optional: size, depth, x, y, emboss, font
    "check_interference": (),          # assemblage : volumes communs par paires
    "undo": (),                        # une transaction = un Ctrl+Z
    "redo": (),
    "export_part": ("path",),          # .stl ou .step selon l'extension
    "preview": ("op", "params"),       # aperçu jaune : op exécutée puis annulée
    "add_rect_sketch": ("width", "height"),   # optional: face (id) to attach
    "add_pad": ("length",),            # optional: sketch, reversed, midplane
    "add_pocket": (),                  # optional: length | through — sans profondeur = à travers tout ; reversed
    "add_fillet": ("radius",),         # face OU edges (liste d'ids)
    "add_chamfer": ("size",),          # face OU edges
    # Palier 2 — fonctions volumiques, aucune interaction nouvelle.
    "add_revolution": (),              # optional: angle (°), sketch
    "add_groove": (),                  # optional: angle (°), sketch
    "add_mirror": (),                  # optional: plane (XY|XZ|YZ)
    "add_linear_pattern": ("length", "count"),   # optional: axis (X|Y|Z)
    "add_polar_pattern": ("count",),   # optional: angle (°), axis
    "add_thickness": ("face", "thickness"),
    "add_draft": ("face", "angle"),    # plan neutre : Plan de dessus (XY)
    # Phase B — références et ossature.
    "add_datum_plane": (),             # optional: base (XY|XZ|YZ) | face, offset, angle
    "add_loft": ("sketches",),         # optional: subtractive, ruled, closed
    "add_sweep": ("profile", "spine"),  # optional: subtractive
    "add_helix": ("pitch", "height"),  # optional: sketch
    "set_param": ("feature", "prop", "value"),
    "set_params": ("feature", "values"),  # valeur numérique OU expression
    # Paramétrique — variables globales (App::VarSet) et équations.
    "list_variables": (),
    "set_variable": ("name", "value"),
    "delete_variable": ("name",),
    "rename": ("feature", "label"),
    "add_hole": ("diameter",),         # optional: depth | through, cut
                                       # (none|lamage|fraisage), cut_diameter,
                                       # cut_depth, cut_angle
    "get_params": ("feature",),        # editable numeric properties
    "set_tip": ("feature",),           # move the rollback bar here
    "tip_to_end": (),                  # back to the final state
    "delete_feature": ("feature",),
    "save_part": ("path",),
    "open_part": ("path",),
    "get_tree": (),
    "tessellate": (),                  # optional: deviation
    "tessellate_edges": (),            # optional: deviation — picking d'arêtes
    # M2 — sketch editing. Geometry travels in sketch-local 2D; the state
    # carries the placement matrix that positions it in 3D.
    "sketch_start": (),                # optional: face | plane (XY|XZ|YZ) | datum (nom)
    "sketch_edit": ("feature",),
    "sketch_state": ("sketch",),
    "sketch_add_line": ("sketch", "x1", "y1", "x2", "y2"),
    "sketch_add_circle": ("sketch", "cx", "cy", "r"),
    # Palier 3 — outils d'esquisse avancés. Angles en radians, sens trigo.
    "sketch_add_arc": ("sketch", "cx", "cy", "r", "a1", "a2"),
    "sketch_add_spline": ("sketch", "points"),  # interpolée par les points
    "sketch_add_ellipse": ("sketch", "cx", "cy", "rx", "ry"),  # optional: angle
    "sketch_mirror": ("sketch", "geos", "axis"),  # copies symétriques
    "sketch_array": ("sketch", "geos", "dx", "dy", "cols", "rows"),
    "sketch_add_slot": ("sketch", "x1", "y1", "x2", "y2", "width"),
    "sketch_add_polygon": ("sketch", "cx", "cy", "x", "y", "sides"),
    "sketch_fillet": ("sketch", "geo1", "geo2",
                      "x1", "y1", "x2", "y2", "radius"),
    "sketch_trim": ("sketch", "geo", "x", "y"),
    "sketch_constrain": ("sketch", "kind", "geo1"),  # optional: point1, geo2, point2, geo3
    "sketch_move": ("sketch", "geo", "point", "x", "y"),
    "sketch_dim": ("sketch", "geo"),   # optional: value, geo2, point, point2
    "sketch_set_dim": ("sketch", "dim"),  # optional: value | expr, name
    "sketch_constraints": ("sketch",),    # optional: geo — relations d'une entité
    "sketch_delete_constraint": ("sketch", "constraint"),
    "sketch_delete_geo": ("sketch", "geo"),
    "sketch_toggle_construction": ("sketch", "geo"),
    "sketch_convert": ("sketch",),     # optional: face — contour projeté, bloqué
    "sketch_finish": ("sketch",),
}


class ProtocolError(Exception):
    """Malformed request. The message is safe to show to the client."""


def validate_request(payload) -> tuple[str, dict]:
    """Check an incoming request, returning ``(op, params)``.

    Raises ``ProtocolError`` with an actionable message otherwise — the
    client shows it verbatim, so it names what is missing.
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
    missing = [k for k in OPS[op] if k not in params]
    if missing:
        raise ProtocolError(
            "{} : paramètre(s) manquant(s) : {}".format(op, ", ".join(missing)))
    return op, params


def ok(result) -> dict:
    return {"ok": True, "result": result}


def err(message: str, hint: str = "") -> dict:
    out = {"ok": False, "error": str(message)}
    if hint:
        out["hint"] = hint
    return out


def pack_mesh(face_meshes) -> dict:
    """Flatten per-face tessellations into one indexed buffer.

    Args:
        face_meshes: iterable of ``(face_id, vertices, triangles)`` where
            ``vertices`` is a list of ``(x, y, z)`` and ``triangles`` a list
            of ``(a, b, c)`` indices local to that face.

    Returns:
        ``positions`` (flat xyz floats), ``indices`` (flat, rebased to the
        global buffer) and ``groups`` — one per face, ``{faceId, start,
        count}`` in *index* units. Picking works by construction: a raycast
        hit's triangle index maps to exactly one group, hence one OCCT face.
    """
    positions: list[float] = []
    indices: list[int] = []
    groups: list[dict] = []
    vertex_base = 0
    for face_id, vertices, triangles in face_meshes:
        start = len(indices)
        for x, y, z in vertices:
            positions.extend((float(x), float(y), float(z)))
        for a, b, c in triangles:
            indices.extend((a + vertex_base, b + vertex_base, c + vertex_base))
        groups.append({
            "faceId": face_id,
            "start": start,
            "count": len(indices) - start,
        })
        vertex_base += len(vertices)
    return {"positions": positions, "indices": indices, "groups": groups}


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
