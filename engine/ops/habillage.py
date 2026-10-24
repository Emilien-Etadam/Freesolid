"""Habillage : congé, chanfrein, coque, dépouille, chanfrein de sommet.

Méthodes : solids.py, vertexchamfer.py.
"""

from engine.ops._base import Op, Req


def _rejouer_conge(kernel, feat, sketch, cote):
    from engine.kernel import KernelError
    radius = cote("Radius")
    if feat["edges"]:
        kernel.add_fillet(radius=radius, edges=feat["edges"])
    elif feat["faces"]:
        kernel.add_fillet(radius=radius, face=feat["faces"][0])
    else:
        raise KernelError(
            "congé sans arête ni face : {}".format(feat["name"]))


def _rejouer_chanfrein(kernel, feat, sketch, cote):
    from engine.kernel import KernelError
    size = cote("Size")
    kind = feat.get("chamfer_type") or "egale"
    extra = {}
    if kind == "deux":
        extra["size2"] = cote("Size2")
        extra["chamfer_type"] = "deux"
        extra["flip"] = bool(feat.get("flip"))
    elif kind == "angle":
        extra["angle"] = cote("Angle")
        extra["chamfer_type"] = "angle"
        extra["flip"] = bool(feat.get("flip"))
    if feat["edges"]:
        kernel.add_chamfer(size=size, edges=feat["edges"], **extra)
    elif feat["faces"]:
        kernel.add_chamfer(size=size, face=feat["faces"][0], **extra)
    else:
        raise KernelError(
            "chanfrein sans arête ni face : {}".format(feat["name"]))


def _rejouer_coque(kernel, feat, sketch, cote):
    from engine.kernel import KernelError
    if not feat["faces"]:
        raise KernelError("coque sans face : {}".format(feat["name"]))
    kernel.add_thickness(
        faces=feat["faces"],
        thickness=cote("Value"),
        outward=not feat["reversed"])


def _rejouer_depouille(kernel, feat, sketch, cote):
    from engine.kernel import KernelError
    if not feat["faces"]:
        raise KernelError(
            "dépouille sans face : {}".format(feat["name"]))
    kernel.add_draft(
        face=feat["faces"][0],
        angle=cote("Angle"))


OPS = (
    Op("add_fillet", Req(("radius", float)),
       undo=True, preview=True, creates="PartDesign::Fillet", indexed=True,
       replay=_rejouer_conge),              # face OU edges (liste d'ids)
    Op("add_chamfer", Req(("size", float), optional={
        "size2": float,          # deux distances
        "angle": float,          # distance et angle, degrés
        "chamfer_type": str,     # egale | deux | angle
        "flip": bool,            # échange les deux côtés
    }),
       undo=True, preview=True, creates="PartDesign::Chamfer", indexed=True,
       replay=_rejouer_chanfrein),  # face OU edges
    # face (une) ou faces (plusieurs) ; outward : coque vers l'extérieur.
    Op("add_thickness", Req(("thickness", float),
                            optional={"face": int, "faces": list,
                                      "outward": bool}),
       undo=True, preview=True, creates="PartDesign::Thickness", indexed=True,
       replay=_rejouer_coque),
    Op("add_draft", Req(("face", int), ("angle", float)),
       undo=True, preview=True, creates="PartDesign::Draft", indexed=True,
       replay=_rejouer_depouille),
                                       # optional: neutral (XY|XZ|YZ)
    Op("add_vertex_chamfer", Req(("distances", list), optional={
        "point": list, "vertex": int}), undo=True, preview=True,
       no_replay="forme figée (FrozenShape), pas get_params"),
    Op("edit_vertex_chamfer", Req(("feature", str), ("distances", list)),
       undo=True),
)
