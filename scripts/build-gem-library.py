"""Construit la bibliothèque de gabarits de pierres (headless).

Usage :  freecadcmd scripts/build-gem-library.py

Le cylindre plat est le premier fichier : VarSet + esquisse contrainte +
Pad. Les 17 tailles se fabriqueront de la même façon — jamais à la main.
"""

import json
import os
import sys

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.gems import (  # noqa: E402
    DEFAULT_GEMME, build_flat_cylinder, library_path,
)

path = library_path(DEFAULT_GEMME)
report = build_flat_cylinder(path)
print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
print("gabarit écrit : {}".format(path), flush=True)
