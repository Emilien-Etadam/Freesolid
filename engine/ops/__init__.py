"""Catalogue des opérations du noyau, une famille par fichier.

Ajouter une op : son descripteur ``Op`` dans la famille qui lui va, sa
méthode dans le mixin du même domaine. Tout ce qui suit en est dérivé.
"""

from engine.ops import (
    habillage, references, repetitions, surfaces, volumes,
)

#: Toutes les ops du noyau. L'ordre n'a pas de sens pour le protocole.
CORE_OPS = (
    volumes.OPS
    + habillage.OPS
    + repetitions.OPS
    + references.OPS
    + surfaces.OPS
)

#: Nom → descripteur. Un nom en double est une erreur de catalogue.
BY_NAME = {}
for _op in CORE_OPS:
    if _op.name in BY_NAME:
        raise ValueError("op déclarée deux fois : {}".format(_op.name))
    BY_NAME[_op.name] = _op

#: Ops enregistrées comme un pas d'annulation chacune.
TRANSACTIONAL = frozenset(op.name for op in CORE_OPS if op.undo)

#: Ops que l'aperçu jaune exécute puis annule.
PREVIEWABLE = frozenset(op.name for op in CORE_OPS if op.preview)

#: TypeId → descripteur de l'op qui le recrée au rejeu.
REPLAYERS = {op.creates: op for op in CORE_OPS if op.replay is not None}

#: TypeId des fonctions à indices d'arête ou de face.
INDEXED = frozenset(op.creates for op in CORE_OPS if op.indexed)
