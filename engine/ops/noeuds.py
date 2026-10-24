"""Fonctions graphe, répétitions variables, nœud Python.

Méthodes : graphfeat.py.
"""

from engine.ops._base import Op, Req


OPS = (
    Op("add_graph_feature", Req(("graph", dict), optional={"mode": str}),
       undo=True),
                                       # mode : fuse | cut pour un solide ;
                                       # absent pour une courbe / surface
    Op("edit_graph_feature", Req(("feature", str), ("graph", dict)),
       undo=True),
    Op("get_graph_feature", Req(("feature", str))),
    Op("add_repeat_feature", Req(("features", list), ("mode", str),
                                 optional={"instances": list, "graph": dict}),
       undo=True),
                                       # exactement un de instances | graph
    Op("edit_repeat_feature", Req(("feature", str),
                                  optional={"instances": list, "graph": dict}),
       undo=True),
                                       # exactement un de instances | graph
    Op("get_repeat_feature", Req(("feature", str))),
    Op("graph_vocabulary"),             # lecture : types, libellés, ports
    Op("script_trust_status"),          # lecture : Python autorisé ce document / session
    Op("authorize_scripts"),            # consentement : jamais persisté dans le .FCStd
)
