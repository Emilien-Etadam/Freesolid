"""Plateforme de référence FreeCAD — une seule source.

Le selftest, pytest et la CI lisent ``FREECAD`` ici. Aucun autre fichier
ne doit porter le numéro de version comme vérité.
"""

import os
import re

#: Version que la CI installe et que le selftest exige.
FREECAD = "1.1.3"

#: Repli explicite : travailler sciemment sur une autre version.
#: Les mesures du rapport ne sont alors pas comparables.
OVERRIDE_ENV = "FREESOLID_ALLOW_FREECAD"


def normalize_version(value) -> str:
    """« 1.1.3 », (1, 1, 3) ou « 1.1.3R… » → « 1.1.3 »."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value[:3]]
        parts = [p for p in parts if p]
        return ".".join(parts)
    digits = re.findall(r"\d+", str(value).strip())
    return ".".join(digits[:3]) if digits else str(value).strip()


def version_status(running, reference=None, allow=None) -> dict:
    """Compare la version courante à la référence.

    Retour : ``running``, ``reference``, ``match``, ``override``, ``message``.
    Fonction pure — pas d'import FreeCAD.
    """
    reference = normalize_version(reference if reference is not None else FREECAD)
    running = normalize_version(running)
    if allow is None:
        allow = ""
    else:
        allow = normalize_version(allow)
    if running == reference:
        return {
            "running": running,
            "reference": reference,
            "match": True,
            "override": False,
            "message": "FreeCAD {}".format(running),
        }
    if allow and running == allow:
        return {
            "running": running,
            "reference": reference,
            "match": False,
            "override": True,
            "message": (
                "FreeCAD {} — repli explicite (référence {}) ; "
                "les mesures ne sont pas comparables".format(
                    running, reference)
            ),
        }
    return {
        "running": running,
        "reference": reference,
        "match": False,
        "override": False,
        "message": (
            "FreeCAD {} n'est pas la plateforme de référence {} — "
            "les mesures de ce rapport ne veulent rien dire. "
            "Installez {} ou exportez {}={}".format(
                running, reference, reference, OVERRIDE_ENV, running)
        ),
    }


def allow_from_environ(environ=None) -> str | None:
    """Valeur du repli explicite, ou ``None`` s'il est absent / vide."""
    env = os.environ if environ is None else environ
    raw = env.get(OVERRIDE_ENV)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip()


def format_selftest_failure(version=None, failed=None, error=None) -> str:
    """Texte du fichier d'échec — lisible hors des barres FreeCAD."""
    lines = ["SELFTEST ÉCHEC"]
    if version:
        lines.append("FreeCAD {} (référence {})".format(
            version.get("running", "?"),
            version.get("reference", "?")))
        if version.get("override"):
            lines.append("repli explicite : les mesures ne sont pas comparables")
        if version.get("message"):
            lines.append(version["message"])
    if error:
        lines.append("erreur : {}".format(error))
    if failed:
        lines.append("indicateurs faux : {}".format(", ".join(failed)))
    elif failed is not None:
        lines.append("indicateurs faux : (aucun nom — voir l'erreur)")
    lines.append("")
    return "\n".join(lines)
