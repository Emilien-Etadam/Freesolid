"""Pièces d'un autre modeleur — .sldprt, .x_t, .x_b — lues par OpenSW.

FreeSolid ne décode pas ces formats lui-même. Le lecteur est le projet
OpenSW (https://github.com/Emilien-Etadam/OpenSW), sous AGPL-3.0 : il
reste un programme à part, cloné à côté, lancé dans son propre
processus. FreeSolid ne relit que le STEP qu'il écrit — aucune ligne
d'OpenSW ici, et aucun fichier de schéma Parasolid.

Seule la géométrie morte entre : l'arbre de fonctions du fichier n'est
jamais rejoué.

Pur Python, sans FreeCAD.
"""

import os
import shutil
import subprocess

#: Extensions confiées au lecteur, en minuscules.
EXTENSIONS = (".sldprt", ".x_t", ".x_b")

#: Dossier du dépôt OpenSW cloné (ou chemin de son ``tools/convert.py``).
READER_ENV = "FREESOLID_OPENSW"

#: Interpréteur Python du lecteur (3.10 ou plus), s'il faut le forcer.
PYTHON_ENV = "FREESOLID_PYTHON"

READER_URL = "https://github.com/Emilien-Etadam/OpenSW"

#: Le convertisseur, dans le dépôt cloné.
CONVERTER = os.path.join("tools", "convert.py")

#: Noms du dépôt cherchés à côté de celui de FreeSolid.
SIBLINGS = ("OpenSW", "openSW")

#: Plafond d'une lecture : les grosses pièces prennent une à deux minutes.
TIMEOUT_S = 900

#: Raison d'un échec, telle que le lecteur l'écrit, au plus.
_REASON_CHARS = 300


class ForeignError(Exception):
    """Lecture impossible — le message dit quoi faire."""


def is_foreign(path) -> bool:
    return os.path.splitext(str(path))[1].lower() in EXTENSIONS


def find_converter(environ, repo_root):
    """Chemin de ``tools/convert.py`` d'OpenSW, ou None.

    ``FREESOLID_OPENSW`` l'emporte : il désigne le dépôt, ou le script
    lui-même. Sinon, un dépôt ``OpenSW`` posé à côté de celui de
    FreeSolid.
    """
    configured = os.path.expanduser((environ.get(READER_ENV) or "").strip())
    if configured:
        if not configured.lower().endswith(".py"):
            configured = os.path.join(configured, CONVERTER)
        candidates = [configured]
    else:
        parent = os.path.dirname(os.path.abspath(repo_root))
        candidates = [os.path.join(parent, name, CONVERTER) for name in SIBLINGS]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def find_python(environ, prefix, which=shutil.which):
    """Interpréteur qui lancera le lecteur, ou None.

    Sous ``freecadcmd``, ``sys.executable`` est FreeCAD lui-même : on
    cherche le Python de la même installation (``sys.prefix``), puis
    celui du ``PATH``.
    """
    configured = os.path.expanduser((environ.get(PYTHON_ENV) or "").strip())
    if configured:
        return configured if os.path.isfile(configured) else None
    for relative in (("bin", "python3"), ("bin", "python"),
                     ("python.exe",), ("bin", "python.exe")):
        candidate = os.path.join(prefix, *relative)
        if os.path.isfile(candidate):
            return candidate
    for name in ("python3", "python"):
        found = which(name)
        if found:
            return found
    return None


def convert_command(python, converter, source, out_dir):
    """STEP seul, dans ``out_dir`` — le convertisseur n'écrit rien d'autre."""
    return [python, converter, "--step", "--force", "-o", out_dir, source]


def expected_output(out_dir, source):
    """Où le convertisseur écrit le STEP : le radical du fichier, ``.STEP``."""
    stem = os.path.splitext(os.path.basename(source))[0]
    return os.path.join(out_dir, stem + ".STEP")


def failure_reason(stderr, returncode):
    """Dernière ligne écrite par le lecteur, sans le nom du fichier."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    if not lines:
        return "code de sortie {}".format(returncode)
    reason = lines[-1]
    marker = "→ .STEP: "
    if marker in reason:
        reason = reason.split(marker, 1)[1]
    return reason[:_REASON_CHARS]


def convert(source, out_dir, *, environ, repo_root, prefix,
            run=subprocess.run, timeout=TIMEOUT_S):
    """Fait écrire à OpenSW le STEP de ``source`` dans ``out_dir``.

    Retourne le chemin du STEP. Lève ``ForeignError`` avec la marche à
    suivre quand le lecteur manque, échoue ou dépasse ``timeout``.
    """
    converter = find_converter(environ, repo_root)
    if converter is None:
        if (environ.get(READER_ENV) or "").strip():
            raise ForeignError(
                "{} ne désigne pas un dépôt OpenSW (tools/convert.py "
                "introuvable)".format(READER_ENV))
        raise ForeignError(
            "lecteur OpenSW absent — clonez {} à côté de FreeSolid, ou "
            "indiquez son dossier dans {}".format(READER_URL, READER_ENV))
    python = find_python(environ, prefix)
    if python is None:
        raise ForeignError(
            "aucun Python pour lancer le lecteur OpenSW — indiquez-le "
            "dans {}".format(PYTHON_ENV))
    child = dict(environ)
    child["PYTHONIOENCODING"] = "utf-8"
    try:
        done = run(convert_command(python, converter, source, out_dir),
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=timeout, cwd=out_dir, env=child)
    except subprocess.TimeoutExpired:
        raise ForeignError(
            "lecture abandonnée au bout de {} s".format(timeout)) from None
    except OSError as exc:
        raise ForeignError(
            "lecteur OpenSW impossible à lancer : {}".format(exc)) from None
    step = expected_output(out_dir, source)
    if done.returncode != 0 or not os.path.isfile(step):
        raise ForeignError("OpenSW n'a pas pu lire ce fichier : {}".format(
            failure_reason(done.stderr, done.returncode)))
    return step
