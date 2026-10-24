"""Géométrie de référence : plan, axe, point, repère.

Méthodes : solids.py (plan), refgeom.py.
"""

from engine.ops._base import Op, Req


OPS = (
    # Phase B — références et ossature.
    Op("add_datum_plane", undo=True, preview=True,
       no_replay="AttachmentSupport, pas une cote"),
                                       # optional: base (XY|XZ|YZ) | face, offset, angle
    Op("add_datum_axis", Req(optional={"axis": str, "edge": int}), undo=True,
       no_replay="AttachmentSupport ou Placement, pas une cote"),
    Op("add_datum_point", Req(optional={"point": list, "vertex": list,
                                        "edge": int}), undo=True,
       no_replay="AttachmentSupport ou Placement, pas une cote"),
    Op("add_datum_cs", Req(optional={"point": list, "vertex": list}),
       undo=True,
       no_replay="AttachmentSupport ou Placement, pas une cote"),
)
