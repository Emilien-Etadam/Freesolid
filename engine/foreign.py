"""Pièces d'un autre modeleur — .sldprt, .x_t, .x_b.

Le lecteur est celui d'OpenSW, repris tel quel dans ``engine/vendor/sldprt``
(même auteur, même licence — voir son README). Il décode la partition
Parasolid et écrit un STEP, que FreeCAD relit ensuite. Aucun fichier de
schéma Parasolid : les faits intégrés au lecteur suffisent.

Seule la géométrie morte entre : l'arbre de fonctions du fichier n'est
jamais rejoué.

Pur Python, sans FreeCAD.
"""

import os

from engine.vendor.sldprt.load import load_model
from engine.vendor.sldprt.step import write_step

#: Extensions confiées au lecteur, en minuscules.
EXTENSIONS = (".sldprt", ".x_t", ".x_b")

#: Nom de produit écrit dans le STEP, au plus — comme le convertisseur
#: d'OpenSW.
_PRODUCT_CHARS = 40

#: Raison d'un échec, telle que le lecteur l'écrit, au plus.
_REASON_CHARS = 300


class ForeignError(Exception):
    """Lecture impossible — le message dit pourquoi."""


def is_foreign(path) -> bool:
    return os.path.splitext(str(path))[1].lower() in EXTENSIONS


def failure_reason(exc) -> str:
    """« Classe: message » de l'exception du lecteur, sur une ligne."""
    text = " ".join(str(exc).split())
    reason = type(exc).__name__ + (": " + text if text else "")
    return reason[:_REASON_CHARS]


def convert(source, step_path):
    """Écrit dans ``step_path`` le STEP de ``source``.

    Retourne le rapport d'écriture du lecteur (``bodies``, ``faces``,
    ``skipped_bodies``…). Lève ``ForeignError`` s'il refuse le fichier.
    """
    name = os.path.splitext(os.path.basename(str(source)))[0][:_PRODUCT_CHARS]
    try:
        return write_step(load_model(source), step_path, name=name)
    except Exception as exc:  # noqa: BLE001 — tout refus se dit de même
        raise ForeignError("OpenSW n'a pas pu lire ce fichier : {}".format(
            failure_reason(exc))) from None
