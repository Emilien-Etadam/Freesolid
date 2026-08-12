"""Lance le selftest headless et sort en erreur s'il échoue.

Usage :  freecadcmd scripts/run-selftest.py

C'est le même selftest que le bouton de l'interface — utilisé par la CI
et par les sessions de développement pour valider AVANT de pousser.
"""

import json
import os
import sys

os.environ["FREESOLID_NO_SERVE"] = "1"

# Les marques du selftest sont en français ; un stdout ASCII (conteneur
# sans locale) ne doit pas faire échouer le test lui-même.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.kernel import Kernel, KernelError  # noqa: E402

try:
    report = Kernel().selftest()
except KernelError as exc:
    print("SELFTEST ÉCHEC : {}".format(exc), flush=True)
    sys.exit(1)

flags = {k: v for k, v in report.items()
         if isinstance(v, bool)}
failed = [k for k, v in flags.items() if v is not True]
print(json.dumps({k: v for k, v in report.items()
                  if k not in ("tree_after_pad", "steps")},
                 ensure_ascii=False, indent=1, default=str), flush=True)
if failed:
    print("SELFTEST ÉCHEC — indicateurs faux : {}".format(
        ", ".join(failed)), flush=True)
    sys.exit(1)
print("SELFTEST OK — {} étapes, {} indicateurs verts".format(
    len(report["steps"]), len(flags)), flush=True)
