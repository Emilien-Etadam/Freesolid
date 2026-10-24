"""Les tables d'opérations du noyau, comparées à leur instantané.

``tests/ops_instantane.json`` a été pris sur le code d'avant le catalogue
``engine/ops/`` (``main`` à ffb81f7) avec ``photographier()`` ci-dessous,
puis mis à une ligne par op pour se relire.

Les tables dérivées des descripteurs doivent rester identiques : mêmes ops,
mêmes paramètres requis dans le même ordre (l'ordre est celui du message
« paramètre(s) manquant(s) »), mêmes types, mêmes optionnels, mêmes ops
annulables, prévisualisables et rejouables.

Un refactoring ne touche jamais ce fichier. Une op ajoutée ou modifiée le
met à jour dans le même commit : son diff *est* le changement de protocole,
lisible en revue.
"""

import json
from pathlib import Path

_INSTANTANE = Path(__file__).resolve().parent / "ops_instantane.json"


def _type(kind):
    return kind.__name__


def _schema(spec):
    kinds = getattr(spec, "kinds", {})
    optional = getattr(spec, "optional", {})
    return {
        "requis": list(spec),
        "types": [[name, _type(kind)] for name, kind in kinds.items()],
        "optionnels": [[name, _type(kind)] for name, kind in optional.items()],
    }


def photographier():
    from engine import kernel, protocol, replay
    return {
        "ops": {name: _schema(protocol.OPS[name])
                for name in sorted(protocol.CORE_OP_NAMES)},
        "annulables": sorted(kernel._TRANSACTIONAL),
        "previsualisables": sorted(kernel.Kernel._PREVIEWABLE),
        "rejouables": [list(item)
                       for item in sorted(replay.REPLAYABLE_TYPES.items())],
        "indices": sorted(replay.INDEXED_TYPES),
        "reconstitution": replay.reconstitution_table(),
    }


def _attendu():
    return json.loads(_INSTANTANE.read_text(encoding="utf-8"))


def test_memes_ops_et_memes_schemas():
    actuel = photographier()["ops"]
    attendu = _attendu()["ops"]
    assert sorted(actuel) == sorted(attendu)
    differents = [name for name in attendu if actuel[name] != attendu[name]]
    assert differents == []


def test_memes_ops_annulables():
    assert photographier()["annulables"] == _attendu()["annulables"]


def test_memes_ops_previsualisables():
    assert photographier()["previsualisables"] == _attendu()["previsualisables"]


def test_meme_table_de_rejeu():
    actuel = photographier()
    attendu = _attendu()
    assert actuel["rejouables"] == attendu["rejouables"]
    assert actuel["indices"] == attendu["indices"]


def test_meme_tableau_de_reconstitution():
    """Sort tel quel dans ``n9_spike_rapport`` : ordre des clés compris."""
    actuel = json.dumps(photographier()["reconstitution"], ensure_ascii=False)
    attendu = json.dumps(_attendu()["reconstitution"], ensure_ascii=False)
    assert actuel == attendu
