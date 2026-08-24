"""Premier client du registre : la bijouterie reste dans le dépôt.

Le code métier ne bouge pas. ``engine.gems`` reste, les méthodes gem
restent sur ``Kernel``. Ici on n'enregistre que les coutures : recompute,
arbre, maillage, ops, selftest.
"""


def register(registre):
    registre.after_recompute(_after_recompute)
    registre.tree_contribution(_tree)
    registre.mesh_contribution(_mesh)
    registre.op("place_gem", _place_gem)
    registre.op("move_gem", _move_gem)
    registre.op("spin_gem", _spin_gem)
    registre.op("remove_gem", _remove_gem)
    registre.op("list_gems", _list_gems)
    registre.op("resize_gem", _resize_gem)
    from bijouterie.selftest import register_steps
    register_steps(registre)


def _after_recompute(kernel):
    kernel._refresh_gem_placements()
    kernel._refresh_gem_boolean_tools()


def _tree(kernel):
    return {"gems": kernel._gem_entries()}


def _mesh(kernel, deviation):
    return {"gems": kernel._tessellate_gems(deviation)}


def _place_gem(kernel, **params):
    return kernel.place_gem(**params)


def _move_gem(kernel, **params):
    return kernel.move_gem(**params)


def _spin_gem(kernel, **params):
    return kernel.spin_gem(**params)


def _remove_gem(kernel, **params):
    return kernel.remove_gem(**params)


def _list_gems(kernel, **params):
    return kernel.list_gems(**params)


def _resize_gem(kernel, **params):
    return kernel.resize_gem(**params)
