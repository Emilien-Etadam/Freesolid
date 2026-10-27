"""Esquisses 2D et 3D : tracés, édition, relations, cotes, calques.

Méthodes : sketch.py et les mixins sketch*, sketch3d.py.
"""

from engine.ops._base import Op, Req


OPS = (
    Op("add_sketch3d", Req(("spec", dict)), undo=True,
       no_replay="spécification 3D (points, liens), pas un profil"),
                                       # points, links, entities,
                                       # dims, relations (sketch3dmath)
    Op("edit_sketch3d", Req(("sketch3d", str), ("spec", dict)), undo=True),
    Op("sketch_set_spline", Req(("sketch", str), ("geo", int),
                                ("points", list)), undo=True),
                                       # optional: tangents,
                                       # closed — points de passage 2D
    Op("sketch_frame", Req(("sketch", str))),  # lecture : centre et normale
    Op("sketch_set_plane", Req(("sketch", str), optional={
        "plane": str, "datum": str, "face": int}), undo=True),
    Op("add_rect_sketch", Req(("width", float), ("height", float)), undo=True,
       no_replay="l'esquisse se copie, elle ne se reconstitue pas"),
                                       # optional: face (id) to attach
    Op("sketch_contours", Req(("sketch", str))),  # lecture
    # M2 — sketch editing. Geometry travels in sketch-local 2D; the state
    # carries the placement matrix that positions it in 3D.
    Op("sketch_start", undo=True),     # optional: face | plane (XY|XZ|YZ) | datum (nom)
    Op("sketch_edit", Req(("feature", str))),
    Op("sketch_state", Req(("sketch", str))),
    Op("sketch_add_line", Req(
        ("sketch", str), ("x1", float), ("y1", float),
        ("x2", float), ("y2", float),
        optional={"construction": bool, "snaps": dict}), undo=True),
                                       # construction : ligne d'axe ;
                                       # snaps : ce que l'interface a
                                       # accroché (engine/sketchsnap.py)
    Op("sketch_add_rectangle", Req(
        ("sketch", str), ("x1", float), ("y1", float),
        ("x2", float), ("y2", float),
        optional={"center": bool, "snaps": dict}), undo=True),
                                       # coins opposés ; center : tenu par
                                       # son centre s'il est sur l'origine
    Op("sketch_add_circle", Req(
        ("sketch", str), ("cx", float), ("cy", float), ("r", float),
        optional={"snaps": dict}), undo=True),
    # Palier 3 — outils d'esquisse avancés. Angles en radians, sens trigo.
    Op("sketch_add_arc", Req(
        ("sketch", str), ("cx", float), ("cy", float), ("r", float),
        ("a1", float), ("a2", float), optional={"snaps": dict}), undo=True),
    Op("sketch_add_spline", Req(("sketch", str), ("points", list)), undo=True),
                                       # interpolée par les points
    Op("sketch_add_ellipse", Req(
        ("sketch", str), ("cx", float), ("cy", float),
        ("rx", float), ("ry", float)), undo=True),  # optional: angle
    Op("sketch_mirror", Req(("sketch", str), ("geos", list), ("axis", int)),
       undo=True),
                                       # copies symétriques
    Op("sketch_array", Req(
        ("sketch", str), ("geos", list), ("dx", float), ("dy", float),
        ("cols", int), ("rows", int)), undo=True),
    Op("sketch_offset_preview", Req(
        ("sketch", str), ("geos", list), ("distance", float))),
                                       # optional: reversed — lecture seule
    Op("sketch_offset", Req(
        ("sketch", str), ("geos", list), ("distance", float)), undo=True),
                                       # optional: reversed, construction
    # Tracés complémentaires (engine/sketchdraw.py).
    Op("sketch_add_point", Req(("sketch", str), ("x", float), ("y", float),
                               optional={"snaps": dict}), undo=True),
    Op("sketch_add_tangent_arc", Req(
        ("sketch", str), ("geo", int), ("point", int),
        ("x", float), ("y", float)), undo=True),  # part d'une extrémité (1|2)
    Op("sketch_add_rect3", Req(
        ("sketch", str), ("x1", float), ("y1", float), ("x2", float),
        ("y2", float), ("x3", float), ("y3", float),
        optional={"parallelogram": bool}), undo=True),
    Op("sketch_add_ellipse_arc", Req(
        ("sketch", str), ("cx", float), ("cy", float), ("rx", float),
        ("ry", float), ("a1", float), ("a2", float)), undo=True),
                                       # optional: angle (°)
    Op("sketch_add_parabola", Req(
        ("sketch", str), ("vx", float), ("vy", float), ("fx", float),
        ("fy", float), ("x1", float), ("y1", float), ("x2", float),
        ("y2", float)), undo=True),    # sommet, foyer, deux bouts
    Op("sketch_add_conic", Req(
        ("sketch", str), ("x1", float), ("y1", float), ("x2", float),
        ("y2", float), ("ax", float), ("ay", float)), undo=True),
                                       # optional: rho
    Op("sketch_add_spline_poles", Req(("sketch", str), ("points", list)),
       undo=True),
    Op("sketch_add_arc_slot", Req(
        ("sketch", str), ("cx", float), ("cy", float), ("r", float),
        ("a1", float), ("a2", float), ("width", float)), undo=True),
    # Édition (engine/sketchedit.py).
    Op("sketch_chamfer", Req(
        ("sketch", str), ("geo1", int), ("geo2", int), ("x1", float),
        ("y1", float), ("x2", float), ("y2", float), ("distance", float)),
       undo=True),
                                       # optional: distance2
    Op("sketch_extend", Req(
        ("sketch", str), ("geo", int), ("x", float), ("y", float)), undo=True),
    Op("sketch_split", Req(
        ("sketch", str), ("geo", int), ("x", float), ("y", float)), undo=True),
    Op("sketch_transform", Req(("sketch", str), ("geos", list)), undo=True),
                                       # optional: dx, dy, angle (°), cx, cy,
                                       # scale, copy
    Op("sketch_polar_array", Req(
        ("sketch", str), ("geos", list), ("cx", float), ("cy", float),
        ("count", int)), undo=True),   # optional: angle (°, 360)
    Op("sketch_silhouette", Req(("sketch", str)), undo=True),
                                       # arêtes vues, bloquées
    Op("sketch_reference", Req(("sketch", str)), undo=True),
                                       # optional: mode (edges | intersection
                                       # | pierce), defining — liées à la pièce
    # Compléments (engine/sketchmore.py).
    Op("sketch_add_text", Req(("sketch", str), ("text", str)), undo=True),
                                       # optional: x, y, size, angle, font
    Op("sketch_corner", Req(
        ("sketch", str), ("geo1", int), ("geo2", int), ("x1", float),
        ("y1", float), ("x2", float), ("y2", float)), undo=True),
    Op("sketch_add_equation", Req(
        ("sketch", str), ("x", str), ("y", str), ("t0", float),
        ("t1", float)), undo=True),    # optional: count
    Op("sketch_repair", Req(("sketch", str)), undo=True),
    Op("sketch_fully_define", Req(("sketch", str)), undo=True),
    Op("sketch_spline", Req(
        ("sketch", str), ("geo", int), ("action", str)), undo=True),
                                       # convert | knot | degree ; x, y
    Op("sketch_match_curvature", Req(
        ("sketch", str), ("geo1", int), ("point1", int), ("geo2", int),
        ("point2", int)), undo=True),  # G2 au raccord de deux splines
    Op("sketch_layers", Req(("sketch", str)), undo=True),
                                       # optional: layers (remplace)
    Op("sketch_set_layer", Req(("sketch", str), ("geos", list)), undo=True),
                                       # optional: layer ("" : par défaut)
    Op("sketch_blocks"),
    Op("sketch_block_save", Req(
        ("sketch", str), ("geos", list), ("name", str)), undo=True),
    Op("sketch_block_insert", Req(
        ("sketch", str), ("name", str), ("x", float), ("y", float)),
       undo=True),
                                       # optional: angle, scale
    Op("sketch_picture", Req(("sketch", str)), undo=True),  # optional: picture
    Op("sketch_add_slot", Req(
        ("sketch", str), ("x1", float), ("y1", float),
        ("x2", float), ("y2", float), ("width", float)), undo=True),
    Op("sketch_add_polygon", Req(
        ("sketch", str), ("cx", float), ("cy", float),
        ("x", float), ("y", float), ("sides", int)), undo=True),
    Op("sketch_fillet", Req(
        ("sketch", str), ("geo1", int), ("geo2", int),
        ("x1", float), ("y1", float), ("x2", float), ("y2", float),
        ("radius", float)), undo=True),
    Op("sketch_trim", Req(
        ("sketch", str), ("geo", int), ("x", float), ("y", float)), undo=True),
    Op("sketch_constrain", Req(("sketch", str), ("kind", str), ("geo1", int)),
       undo=True),
                                       # optional: point1, geo2, point2, geo3
    Op("sketch_move", Req(
        ("sketch", str), ("geo", int), ("point", int),
        ("x", float), ("y", float))),
    Op("sketch_dim", Req(("sketch", str), ("geo", int)), undo=True),
                                       # optional: value, geo2, point, point2,
                                       # axis (x | y : cote horizontale / verticale),
                                       # at ([x, y] : où la cote a été posée),
                                       # radius (cercle coté au rayon)
    Op("sketch_set_dim", Req(("sketch", str), ("dim", int)), undo=True),
    Op("sketch_place_dim", Req(("sketch", str), ("dim", int),
                               ("offset", float)), undo=True),
                                       # optional: value | expr, name
    Op("sketch_constraints", Req(("sketch", str))),
                                       # optional: geo — relations d'une entité
    Op("sketch_delete_constraint", Req(("sketch", str), ("constraint", int)),
       undo=True),
    Op("sketch_delete_geo", Req(("sketch", str), ("geo", int)), undo=True),
    Op("sketch_toggle_construction", Req(("sketch", str), ("geo", int)),
       undo=True),
    Op("sketch_convert", Req(("sketch", str)), undo=True),
                                       # optional: face — contour projeté, bloqué
    Op("sketch_finish", Req(("sketch", str)), undo=True),
    Op("sketch_cancel", Req(("sketch", str))),  # quitter sans garder
)
