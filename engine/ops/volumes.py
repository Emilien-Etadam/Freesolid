"""Corps et fonctions volumiques : extrusions, révolutions, lissage,
balayage, hélice, perçage, texte, Combiner.

Méthodes : solids.py, text.py, sketchshare.py, directedit.py.
"""

from engine.ops._base import Op, Req

#: Conditions de fin d'extrusion communes au bossage et à l'enlèvement.
_EXTRUDE_OPTIONAL = {"cond": str, "face": int, "offset": float, "taper": float, "midplane": bool, "reversed": bool, "cond2": str, "length2": float, "face2": int, "offset2": float, "taper2": float, "sketch": str, "thin": dict}


def _rejouer_extrusion(kernel, feat, sketch, cote):
    kernel.add_pad(
        length=cote("Length"),
        sketch=sketch,
        reversed=feat["reversed"],
        midplane=feat["midplane"])


def _rejouer_enlevement(kernel, feat, sketch, cote):
    if feat["through"]:
        kernel.add_pocket(through=True, sketch=sketch,
                          reversed=feat["reversed"])
    else:
        kernel.add_pocket(
            length=cote("Length"),
            sketch=sketch, reversed=feat["reversed"])


def _rejouer_revolution(kernel, feat, sketch, cote):
    kernel.add_revolution(
        angle=cote("Angle"),
        sketch=sketch,
        axis=feat.get("axis") or "vertical",
        reversed=bool(feat.get("reversed")),
        midplane=bool(feat.get("midplane")))


def _rejouer_enlevement_revolution(kernel, feat, sketch, cote):
    kernel.add_groove(
        angle=cote("Angle"),
        sketch=sketch,
        axis=feat.get("axis") or "vertical",
        reversed=bool(feat.get("reversed")),
        midplane=bool(feat.get("midplane")))


def _rejouer_percage(kernel, feat, sketch, cote):
    # add_hole consomme _latest_sketch — le profil a été cloné juste avant.
    diameter = cote("Diameter")
    if feat["through"]:
        kernel.add_hole(diameter=diameter, through=True)
    else:
        kernel.add_hole(
            diameter=diameter,
            depth=cote("Depth"))


OPS = (
    # Phase C — multi-corps.
    Op("add_body", undo=True,          # optional: name — devient le corps actif
       no_replay="pas une fonction du groupe"),
    Op("set_active_body", Req(("body", str))),
    Op("set_body_color", Req(("body", str), "color"), undo=True),
                                       # "#rrggbb" | null | "" (défaut)
    Op("add_boolean", Req(("tool", str)), undo=True, preview=True,
       no_replay="corps outil, pas un profil"),
                                       # optional: type (cut|fuse|common)
    # Conditions de fin : engine/extrude.py. Sans length : jusqu'à…
    Op("add_pad", Req(optional={"length": float, "contours": list,
                                **_EXTRUDE_OPTIONAL}),
       undo=True, preview=True, creates="PartDesign::Pad",
       replay=_rejouer_extrusion),
    # Sans profondeur ni condition = à travers tout.
    Op("add_pocket", Req(optional={"length": float, "through": bool,
                                   "contours": list, **_EXTRUDE_OPTIONAL}),
       undo=True, preview=True, creates="PartDesign::Pocket",
       replay=_rejouer_enlevement),
    # Palier 2 — fonctions volumiques, aucune interaction nouvelle.
    Op("add_revolution", Req(optional={
        "angle": float,          # degrés, défaut 360
        "axis": str,             # vertical | horizontal | line:<id> | X | Y | Z
        "reversed": bool,
        "midplane": bool,
        "contours": list,        # index des contours de l'esquisse pris
    }),
       undo=True, preview=True, creates="PartDesign::Revolution",
       replay=_rejouer_revolution),    # sketch reste libre (nom d'esquisse)
    Op("add_groove", Req(optional={
        "angle": float,
        "axis": str,
        "reversed": bool,
        "midplane": bool,
        "contours": list,
    }),
       undo=True, preview=True, creates="PartDesign::Groove",
       replay=_rejouer_enlevement_revolution),
    Op("set_profile_contours", Req(("feature", str), ("contours", list)),
       undo=True),
                                       # [] : toute l'esquisse
    Op("add_loft", Req(("sketches", list)), undo=True, preview=True,
       no_replay="plusieurs profils (Sections), pas get_params"),
                                       # optional: subtractive, ruled, closed
    Op("add_sweep", Req(("profile", str), ("spine", str)),
       undo=True, preview=True,
       no_replay="Profile + Spine, pas get_params"),  # optional: subtractive
    Op("add_helix", Req(("pitch", float), ("height", float)),
       undo=True, preview=True,
       no_replay="Pitch/Height hors whitelist get_params"),  # optional: sketch
    Op("add_hole", Req(("diameter", float), optional={"face": int, "points": list}),
       undo=True, preview=True, creates="PartDesign::Hole",
       replay=_rejouer_percage),
                                       # optional: depth | through, cut
                                       # (none|lamage|fraisage), cut_diameter,
                                       # cut_depth, cut_angle ; face + points :
                                       # les centres cliqués sur la face
    Op("add_text", Req(("text", str), ("face", int)), undo=True, preview=True,
       no_replay="propriétés FreeSolid* hors get_params"),
                                       # optional: size, depth, x, y, emboss, font
    Op("edit_text", Req(("feature", str)), undo=True),
                                       # optional: text, size, depth, x, y
                                       # — absents = inchangés
    Op("face_drag_info", Req(("face", int))),
                                       # lecture : la face se tire-t-elle
)
