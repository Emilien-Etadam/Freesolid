"""Aucun nom de produit de CAO commerciale dans le moteur.

Pendant de ``tests/js/cleanroom.test.mjs``. Les messages destinés au
concepteur sont déjà couverts par ``tests/test_guard.py`` ; ici ce sont
les sources du moteur, commentaires compris.
"""

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "engine"
FORBIDDEN = re.compile(
    r"solidworks|dassault|catia|propertymanager|featuremanager|commandmanager",
    re.IGNORECASE,
)

# Le selftest vérifie qu'un message d'erreur ne contient pas ce nom.
# La liste de ``tests/test_guard.py`` est hors de engine/, donc déjà exclue.
EXCEPTIONS = (
    ("selftest/fonctions.py", '"SolidWorks" not in text'),
)


def test_engine_names_no_commercial_cad():
    hits = []
    # Récursif : les sous-paquets (engine/ops/…) sont des sources du moteur.
    # Sauf vendor/ : repris tel quel d'un autre dépôt, comme app/vendor/
    # côté interface.
    paths = sorted(p for p in ENGINE.rglob("*.py")
                   if "vendor" not in p.relative_to(ENGINE).parts)
    lang = ENGINE / "lang" / "en.json"
    if lang.is_file():
        paths.append(lang)
    for path in paths:
        rel = path.relative_to(ENGINE).as_posix()
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line) is None:
                continue
            if any(rel == name and marker in line
                   for name, marker in EXCEPTIONS):
                continue
            hits.append("{}:{}: {}".format(rel, number, line.strip()))
    assert hits == []
