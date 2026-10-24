"""Surfaces et courbes : construction, retouche, passage au solide.

Méthodes : surfacefeat/, splineedit.py.
"""

from engine.ops._base import Op, Req


OPS = (
    # Phase D — surfacique (API Part, hors historique PartDesign) + courbes.
    Op("surface_extrude", Req(("length", float)), undo=True),
                                       # optional: sketch — profil ouvert OK
    Op("surface_revolve", undo=True),  # optional: angle, sketch
    Op("surface_loft", Req(("sketches", list)), undo=True),
    Op("surface_sew", Req(("surfaces", list)), undo=True),
                                       # coudre ; solidifie si fermé
    Op("surface_thicken", Req(("surface", str), ("thickness", float)),
       undo=True),
    Op("add_curve3d", Req(("points", list)), undo=True,
       no_replay="liste de points"),
                                       # optional: spline, closed,
                                       # rules [{axis, length}] par segment,
                                       # links, tangents [{dir, in, out}|None]
    Op("curve_poles", Req(("points", list))),  # lecture : polygone de contrôle
                                       # optional: closed, tangents
    Op("curve_move_pole", Req(("points", list), ("index", int),
                              ("point", list))),  # lecture : points et
                                       # poignées après avoir tiré un pôle
    Op("curve3d_preview", Req(("points", list))),
                                       # optional: spline, closed — lecture seule
    Op("edit_curve3d", Req(("curve", str), ("points", list)), undo=True),
                                       # optional: spline, closed, rules,
                                       # links, tangents
    Op("surface_planar", undo=True),   # optional: sketch — contour fermé
    Op("surface_sweep", Req(("profile", str), ("spine", str)), undo=True),
    Op("surface_offset", Req(("surface", str), ("distance", float)),
       undo=True),
    Op("surface_fill", Req(("boundary", list)), undo=True),
                                       # [{name, edge?} | {body: true, edge}]
                                       # optional: tangent
    Op("surface_boundary", Req(("boundary", list)), undo=True),
                                       # 2 à 4 courbes
    Op("surface_ruled", Req(("boundary", list)), undo=True),
                                       # exactement 2 courbes
    Op("surface_delete_faces", Req(("surface", str), ("faces", list)),
       undo=True, preview=True),
    Op("surface_untrim", Req(("surface", str)), undo=True),  # optional: face
    Op("surface_split", Req(("surface", str), ("tool", str)), undo=True),
    Op("surface_fillet", Req(("surface", str), ("edges", list),
                             ("radius", float)), undo=True),
    Op("edit_surface_fillet", Req(("surface", str), ("radius", float)),
       undo=True),
    Op("curve_intersection", Req(("first", str)), undo=True),
                                       # optional: second, body
    Op("curve_project", Req(("sketch", str), ("surface", str)), undo=True),
                                       # optional: face
    Op("curve_composite", Req(("boundary", list)), undo=True),
    Op("surface_radiate", Req(("boundary", list), ("distance", float)),
       undo=True),
    Op("surface_mid", undo=True),      # optional: faces (deux, base 0) |
                                       # thickness (paires automatiques)
    Op("surface_flatten", Req(("surface", str)), undo=True),  # optional: face
    Op("surface_freeform", Req(("surface", str)), undo=True),
                                       # radius + pushes [[x,y,z,h]…] |
                                       # point + height ; ou moves
                                       # [[i,j,dx,dy,dz]…] + grid ;
                                       # face, keep_edges
    Op("edit_surface_freeform", Req(("surface", str)), undo=True),
                                       # radius, pushes, height,
                                       # keep_edges | moves, grid
    Op("surface_control_points", Req(("surface", str))),
                                       # optional: face, grid — lecture seule
    Op("curve_helix", Req(("pitch", float), ("height", float),
                          ("radius", float)), undo=True),
                                       # optional: angle, left, axis (X|Y|Z)
    Op("surface_extend", Req(("surface", str), ("distance", float)),
       undo=True),
                                       # optional: edge (bord prolongé)
    Op("edit_surface_extend", Req(("surface", str), ("distance", float)),
       undo=True),
                                       # optional: edge
    Op("surface_trim", Req(("surface", str), ("tool", str)), undo=True),
                                       # optional: point — partie gardée,
                                       # tool_point — ajustement mutuel
    Op("add_surface_cut", Req(("surface", str)), undo=True, preview=True,
       no_replay="corps outil tiré d'une surface, pas un profil"),
                                       # optional: flip,
                                       # thickness (bande enlevée)
    Op("add_delete_face", Req(("faces", list)), undo=True, preview=True,
       no_replay="forme figée (FrozenShape), pas get_params"),
                                       # faces du solide, base 0
    Op("add_replace_face", Req(("face", int), ("surface", str)),
       undo=True, preview=True,
       no_replay="forme figée (FrozenShape), pas get_params"),
    Op("edit_surface_cut", Req(("feature", str), ("flip", bool)), undo=True),
                                       # optional: thickness
    Op("edit_surface_trim", Req(("surface", str)), undo=True),
                                       # optional: point — sans point,
                                       # la partie suivante
)
