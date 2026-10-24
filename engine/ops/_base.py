"""Descripteur d'une opération du moteur : une seule déclaration par op.

Pur Python — ni FreeCAD, ni le noyau au chargement — pour que le catalogue
soit importé par ``protocol.py`` et testé en CI. Les tables du noyau en sont
dérivées (``engine/ops/__init__.py``) : ``protocol.OPS``,
``kernel._TRANSACTIONAL``, ``Kernel._PREVIEWABLE`` et la table de rejeu de
``replay.py``.
"""

from dataclasses import dataclass
from typing import Callable, Optional


class Req(tuple):
    """Tuple of required param names, with optional JSON types.

    ``Req(("length", float), "value")`` equals ``("length", "value")`` so
    existing ``OPS[op] == (...)`` assertions keep working. ``.kinds`` maps
    typed names to ``float``, ``int``, ``str``, ``list``, ``dict``,
    ``bool`` or ``Name`` (non-empty ``str``). ``.optional`` maps optional names to the same kinds — present
    params are type-checked, absent ones are not required. Bare names are
    presence-only (no type check, no coercion).
    """

    def __new__(cls, *items, optional=None):
        names = []
        kinds = {}
        for item in items:
            if isinstance(item, str):
                names.append(item)
            else:
                name, kind = item
                names.append(name)
                kinds[name] = kind
        obj = super().__new__(cls, names)
        obj.kinds = kinds
        obj.optional = dict(optional or {})
        return obj


class Name(str):
    """Kind ``nom`` d'un manifeste de plugin : texte non vide.

    Jamais instancié — il marque seulement un paramètre dans ``OPS``,
    comme ``_NONEMPTY_STR_PARAMS`` le fait pour les ops du noyau.
    """


@dataclass(frozen=True)
class Op:
    """Une opération du noyau.

    Attributes:
        name: le nom d'op du protocole JSON.
        req: les paramètres — ``()`` ou un ``Req``. Les optionnels non
            typés sont documentés en commentaire et dans la méthode.
        undo: un pas d'annulation (``kernel._TRANSACTIONAL``). Restent
            dehors, exprès : le cycle de vie du document (nouveau, ouvrir),
            les lectures, undo/redo eux-mêmes, et ``sketch_move`` — un
            glisser à ~20 Hz découperait la pile d'annulation en pas par
            image.
        preview: l'aperçu jaune l'accepte (``Kernel._PREVIEWABLE``).
        creates: le TypeId de la fonction créée, quand elle se rejoue.
        indexed: elle porte des indices d'arête ou de face — la garde
            topologique du rejeu s'applique (``replay.INDEXED_TYPES``).
        replay: ``replay(kernel, feat, sketch, cote)`` la recrée depuis sa
            capture (``replay._capture_feature``) ; ``sketch`` est le profil
            recopié, ``cote(prop)`` la cote capturée ou substituée.
        no_replay: pourquoi une op ``add_*`` ne se rejoue pas — chaque
            ``add_*`` a ``replay`` ou cette raison (test de cohérence).
    """

    name: str
    req: tuple = ()
    undo: bool = False
    preview: bool = False
    creates: str = ""
    indexed: bool = False
    replay: Optional[Callable] = None
    no_replay: str = ""
