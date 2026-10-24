"""Assemblage : composants, contraintes, solveur, interférences.

Méthodes : assembly.py.
"""

from engine.ops._base import Op, Req


OPS = (
    # Phase C — assemblage v1 (placements directs, sans solveur).
    Op("new_assembly"),                # optional: name
    Op("insert_component", Req(("path", str)), undo=True),
                                       # .FCStd — App::Link vers son corps
    Op("move_component", Req(("component", str)), undo=True),
                                       # optional: x, y, z, yaw, pitch, roll
    Op("set_component_grounded", Req(("component", str),
                                     optional={"grounded": bool}), undo=True),
    Op("array_component", Req(("component", str), ("count", int)), undo=True),
                                       # optional: dx, dy, dz
    Op("assembly_tree"),
    Op("tessellate_assembly"),         # optional: deviation
    # Phase C3 — contraintes d'assemblage (joints natifs + solveur MbD).
    Op("add_joint", Req(("component1", str), ("component2", str),
                        optional={"angle": float, "flip": bool}), undo=True,
       no_replay="assemblage"),
                                       # optional: type (fixe|pivot|
                                       # cylindrique|glissiere|rotule|
                                       # distance), sub1, sub2, distance
    Op("solve_assembly", undo=True),
    Op("spike_assembly"),              # rapport : joints Assembly headless ?
    Op("check_interference"),          # assemblage : volumes communs par paires
)
