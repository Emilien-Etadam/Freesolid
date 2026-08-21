"""Lance le selftest headless et sort en erreur s'il échoue.

Usage :  freecadcmd scripts/run-selftest.py

C'est le même selftest que le bouton de l'interface — utilisé par la CI
et par les sessions de développement pour valider AVANT de pousser.

Les indicateurs faux sont aussi écrits dans ``selftest-echecs.txt``
(racine du dépôt) : FreeCAD vide ses barres de progression en fin de
processus et noie le diagnostic stdout.
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
from engine.platform import (  # noqa: E402
    allow_from_environ, format_selftest_failure, version_status,
)

_FAILURES_PATH = os.environ.get(
    "FREESOLID_SELFTEST_FAILURES",
    os.path.join(_REPO, "selftest-echecs.txt"),
)


def _write_failures(*, version=None, failed=None, error=None):
    text = format_selftest_failure(
        version=version, failed=failed, error=error)
    with open(_FAILURES_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("SELFTEST ÉCHEC — détail : {}".format(_FAILURES_PATH), flush=True)


def _clear_failures():
    try:
        os.remove(_FAILURES_PATH)
    except FileNotFoundError:
        pass


def _platform_of(kernel):
    try:
        return version_status(
            kernel.ping()["freecad"], allow=allow_from_environ())
    except Exception:
        return None


kernel = Kernel()
platform = _platform_of(kernel)
try:
    report = kernel.selftest()
except KernelError as exc:
    print("SELFTEST ÉCHEC : {}".format(exc), flush=True)
    _write_failures(version=platform, error=str(exc))
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
    _write_failures(
        version={
            "running": report.get("freecad"),
            "reference": report.get("freecad_reference"),
            "override": bool(report.get("freecad_override")),
            "message": "",
        },
        failed=failed,
    )
    sys.exit(1)
_clear_failures()
print("SELFTEST OK — {} étapes, {} indicateurs verts".format(
    len(report["steps"]), len(flags)), flush=True)
