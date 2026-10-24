"""Plugin bouchon — uniquement pour les tests. Ne charge pas en production.

Couvre le chemin ``dispatch`` → ``call_op`` sans plugin réel installé.
Découvert par personne : ``discover`` ne lit que ``plugins/*/plugin.json``.
"""

from engine.kernel import KernelError


def register(registre):
    registre.op("echo_bouchon", echo_bouchon)
    registre.op("muter_bouchon", muter_bouchon)
    registre.op("boom_bouchon", boom_bouchon)
    registre.transactional.update({"muter_bouchon", "boom_bouchon"})
    registre.tolerates_invalid(_personne)
    registre.boolean_tool(_rien)
    registre.deletes_feature(_personne)
    registre.internal_object(_personne)
    registre.tree_node(_personne)


def echo_bouchon(kernel, message):
    return {"echo": message}


def muter_bouchon(kernel):
    return {"muté": True}


def boom_bouchon(kernel):
    raise KernelError("le bouchon a levé")


def _personne(_kernel, _obj):
    return False


def _rien(_kernel, _obj):
    return None
