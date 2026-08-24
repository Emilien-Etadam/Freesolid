"""Lance le selftest headless et sort en erreur s'il échoue.

Usage :  freecadcmd scripts/run-selftest.py

C'est le même selftest que le bouton de l'interface — utilisé par la CI
et par les sessions de développement pour valider AVANT de pousser.

Les indicateurs faux sont aussi écrits dans ``selftest-echecs.txt``
(racine du dépôt) : FreeCAD vide ses barres de progression en fin de
processus et noie le diagnostic stdout.

``FREESOLID_SELFTEST_PLUGINS`` (noms séparés par des virgules) exige que
ces plugins soient chargés ET qu'ils aient contribué au moins un
indicateur. Sans cette exigence, un plugin absent ou cassé donne un
rapport plus court, tous les indicateurs du noyau vrais, et un selftest
VERT — le registre avale l'erreur de chargement dans une note pour
qu'un plugin cassé ne brique pas FreeSolid, et cette note n'était lue
par personne. C'est la CI d'un dépôt de plugin qui pose la variable :
elle est la seule à savoir ce qui doit être là.
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
from engine.plugins import missing_selftest_plugins  # noqa: E402
from engine.platform import (  # noqa: E402
    allow_from_environ, format_selftest_failure, version_status,
)

_EXPECTED_PLUGINS = [
    nom.strip()
    for nom in os.environ.get("FREESOLID_SELFTEST_PLUGINS", "").split(",")
    if nom.strip()
]

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


def _announce_plugins(kernel):
    """Imprime les plugins chargés et TOUTES les notes du registre.

    ``load_plugins`` attrape ``Exception`` autour de ``register()`` pour
    qu'un plugin cassé n'empêche pas FreeSolid de démarrer — c'est le bon
    choix. Mais la note qui en résulte n'était affichée nulle part : un
    plugin qui échouait à se charger le faisait en silence. L'imprimer
    coûte deux lignes et transforme une panne muette en panne lisible.
    """
    registry = getattr(kernel, "_plugins", None)
    if registry is None:
        return None
    charges = [m["nom"] for m in getattr(registry, "manifests", [])]
    print("selftest> plugins chargés : {}".format(
        ", ".join(charges) if charges else "(aucun)"), flush=True)
    for note in getattr(registry, "notes", []):
        print("selftest> plugin — {}".format(note), flush=True)
    return registry


kernel = Kernel()
platform = _platform_of(kernel)
registry = _announce_plugins(kernel)
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
manquants = missing_selftest_plugins(registry, _EXPECTED_PLUGINS)
if manquants:
    # Tous les indicateurs présents sont verts — mais ceux qu'on attendait
    # ne sont pas là. Un rapport plus court n'est pas un rapport réussi.
    print("SELFTEST ÉCHEC — plugins exigés absents du rapport : {}".format(
        "; ".join(manquants)), flush=True)
    _write_failures(
        version={
            "running": report.get("freecad"),
            "reference": report.get("freecad_reference"),
            "override": bool(report.get("freecad_override")),
            "message": "",
        },
        error="plugins exigés absents du rapport : {}".format(
            "; ".join(manquants)),
    )
    sys.exit(1)
_clear_failures()
contributions = getattr(registry, "selftest_counts", {}) if registry else {}
detail = "".join(
    " ({} : {})".format(nom, n) for nom, n in sorted(contributions.items()))
print("SELFTEST OK — {} étapes, {} indicateurs verts{}".format(
    len(report["steps"]), len(flags), detail), flush=True)
