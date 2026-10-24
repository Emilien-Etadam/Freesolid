"""Répétitions : symétrie, répétitions linéaire et circulaire.

Méthodes : solids.py.
"""

from engine.ops._base import Op, Req


OPS = (
    Op("add_mirror", Req(optional={"features": list}),
       undo=True, preview=True),
                                       # optional: plane (XY|XZ|YZ), features
    Op("add_linear_pattern", Req(("length", float), ("count", int),
                                 optional={"features": list, "axis": str,
                                           "edge": int, "spacing": bool,
                                           "reversed": bool,
                                           "length2": float, "count2": int,
                                           "axis2": str, "edge2": int,
                                           "reversed2": bool}),
       undo=True, preview=True),
                                       # optional: axis (X|Y|Z), features
    Op("add_polar_pattern", Req(("count", int),
                                optional={"features": list, "axis": str,
                                          "edge": int, "angle": float,
                                          "reversed": bool}),
       undo=True, preview=True),
                                       # optional: angle (°), axis, features
)
