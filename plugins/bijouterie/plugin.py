"""Premier client du registre : la bijouterie, bientôt déplaçable.

Le métier vit dans ``gemkernel`` — des fonctions, pas un mixin.
Ici on n'enregistre que les coutures.
"""

from bijouterie import gemkernel


def register(registre):
    registre.after_recompute(_after_recompute)
    registre.tree_contribution(_tree)
    registre.mesh_contribution(_mesh)
    registre.op("place_gem", gemkernel.place_gem)
    registre.op("move_gem", gemkernel.move_gem)
    registre.op("spin_gem", gemkernel.spin_gem)
    registre.op("remove_gem", gemkernel.remove_gem)
    registre.op("list_gems", gemkernel.list_gems)
    registre.op("resize_gem", gemkernel.resize_gem)
    registre.tolerates_invalid(gemkernel.tolerates_invalid)
    registre.boolean_tool(gemkernel.boolean_tool)
    registre.deletes_feature(gemkernel.deletes_feature)
    from bijouterie.selftest import register_steps
    register_steps(registre)


def _after_recompute(kernel):
    gemkernel._refresh_gem_placements(kernel)
    gemkernel._refresh_gem_boolean_tools(kernel)


def _tree(kernel):
    return {"gems": gemkernel._gem_entries(kernel)}


def _mesh(kernel, deviation):
    return {"gems": gemkernel._tessellate_gems(kernel, deviation)}
