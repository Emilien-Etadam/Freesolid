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
    "undo": (),                        # une transaction = un Ctrl+Z
    "redo": (),
    "export_part": ("path",),          # .stl ou .step selon l'extension
    "add_rect_sketch": ("width", "height"),   # optional: face (id) to attach
    "add_pad": ("length",),
    "add_pocket": (),                  # optional: length | through — sans profondeur = à travers tout
    "add_fillet": ("face", "radius"),
    "add_chamfer": ("face", "size"),
    "set_param": ("feature", "prop", "value"),
    "get_params": ("feature",),        # editable numeric properties
    "set_tip": ("feature",),           # move the rollback bar here
    "tip_to_end": (),                  # back to the final state
    "delete_feature": ("feature",),
    "save_part": ("path",),
    "open_part": ("path",),
    "get_tree": (),
    "tessellate": (),                  # optional: deviation
    # M2 — sketch editing. Geometry travels in sketch-local 2D; the state
    # carries the placement matrix that positions it in 3D.
    "sketch_start": (),                # optional: face | plane (XY|XZ|YZ)
    "sketch_edit": ("feature",),
    "sketch_state": ("sketch",),
    "sketch_add_line": ("sketch", "x1", "y1", "x2", "y2"),
    "sketch_add_circle": ("sketch", "cx", "cy", "r"),
    "sketch_move": ("sketch", "geo", "point", "x", "y"),
    "sketch_dim": ("sketch", "geo"),   # optional: value
    "sketch_set_dim": ("sketch", "dim", "value"),
    "sketch_delete_geo": ("sketch", "geo"),
    "sketch_toggle_construction": ("sketch", "geo"),
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
