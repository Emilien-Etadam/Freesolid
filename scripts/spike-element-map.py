"""Spike A7 — la carte d'éléments de FreeCAD est-elle peuplée chez nous ?

Usage :  freecadcmd scripts/spike-element-map.py

Le registre amont (``docs/amont-freecad.md`` §4ter) a établi *sur la
source* que FreeCAD 1.1.3 expose la carte d'éléments en Python :
``getElementMappedName``, ``getElementIndexedName``, ``getElementName``,
les attributs ``ElementMap`` / ``ElementReverseMap`` / ``ElementMapSize``
/ ``ElementMapVersion`` / ``Tag``, et ``getElementHistory``.

Reste la seule question qui décide de la suite : **est-elle peuplée pour
nos objets ?** Si oui, ``engine/replay.py`` doit stocker le nom mappé au
lieu de ``Edge3`` et la garde ``shape_fingerprint`` devient un filet ; si
non, la garde reste la seule défense.

Ce script est une **sonde, pas un test**. Un verdict négatif est un
résultat, pas un échec : il sort en 0 sauf si la sonde elle-même casse.
La CI l'exécute pour archiver le verdict, jamais pour bloquer.
"""

import json
import os
import sys

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

_REPORT_PATH = os.environ.get(
    "FREESOLID_SPIKE_REPORT",
    os.path.join(_REPO, "spike-element-map.json"))

#: Les trois états du reçu (docs/vcad.md §5.2) : « n'a pas pu tourner »
#: n'est jamais confondu avec « passé ».
VERIFIE = "vérifié"
ECHOUE = "échoué"
INVERIFIABLE = "invérifiable"

probes = []


def probe(nom, etat, detail):
    """Enregistre un constat et l'imprime tout de suite.

    Sortie immédiate : FreeCAD noie stdout en fin de processus (même
    raison que ``scripts/run-selftest.py``).
    """
    probes.append({"sonde": nom, "état": etat, "détail": detail})
    print("spike> {:<28} {:<12} {}".format(nom, etat, detail), flush=True)


def attr(obj, nom):
    """Valeur d'un attribut, ou None s'il est absent ou illisible.

    L'appelant distingue « absent » de « illisible » avec ``hasattr`` ;
    ici on veut seulement ne jamais lever.
    """
    try:
        return getattr(obj, nom)
    except Exception:  # noqa: BLE001 - une sonde ne casse pas sur un attribut
        return None


def main():
    from engine.kernel import Kernel
    from engine.platform import allow_from_environ, version_status

    kernel = Kernel()
    plateforme = version_status(
        kernel.ping()["freecad"], allow=allow_from_environ())
    print("spike> FreeCAD {} (référence {})".format(
        plateforme["running"], plateforme["reference"]), flush=True)

    # --- une pièce minimale : esquisse cotée + bossage -------------------
    kernel.new_part("Spike carte d'éléments")
    kernel.add_rect_sketch(100, 60)
    arbre = kernel.add_pad(10)
    pad_nom = next(f["name"] for f in arbre["features"]
                   if f["type"] == "PartDesign::Pad")
    pad = kernel._doc.getObject(pad_nom)
    forme = pad.Shape

    # --- 1. l'API est-elle là, à l'exécution ? --------------------------
    manquants = [n for n in ("getElementMappedName", "getElementIndexedName",
                             "getElementName", "ElementMap", "ElementMapSize",
                             "ElementMapVersion", "Tag")
                 if not hasattr(forme, n)]
    if manquants:
        probe("api_exposée", ECHOUE, "absents : " + ", ".join(manquants))
        return  # sans l'API, les sondes suivantes n'ont pas de sens
    probe("api_exposée", VERIFIE, "les sept noms attendus sont présents")

    # --- 2. la carte est-elle peuplée ? ---------------------------------
    taille = attr(forme, "ElementMapSize")
    tag = attr(forme, "Tag")
    version = attr(forme, "ElementMapVersion")
    peuplee = bool(taille)
    probe("carte_peuplée", VERIFIE if peuplee else ECHOUE,
          "ElementMapSize={} Tag={} version={!r}".format(taille, tag, version))

    # --- 3. aller-retour indexé -> mappé -> indexé ----------------------
    #     C'est l'opération dont replay.py a besoin : stocker le nom
    #     stable, le rendre à un « Face1 » au rejeu.
    if not peuplee:
        probe("aller_retour", INVERIFIABLE, "carte vide — rien à résoudre")
        probe("survie_reparam", INVERIFIABLE, "carte vide")
        probe("historique_élément", INVERIFIABLE, "carte vide")
        return

    indexe = "Face1"
    mappe = attr(forme, "getElementMappedName")
    mappe = mappe(indexe) if callable(mappe) else None
    if isinstance(mappe, (tuple, list)):
        mappe = mappe[0] if mappe else None
    if not mappe:
        probe("aller_retour", ECHOUE,
              "getElementMappedName({!r}) rend {!r}".format(indexe, mappe))
        return
    retour = forme.getElementIndexedName(mappe)
    if isinstance(retour, (tuple, list)):
        retour = retour[0] if retour else None
    probe("aller_retour", VERIFIE if retour == indexe else ECHOUE,
          "{} -> {!r} -> {!r}".format(indexe, mappe, retour))

    # --- 4. le nom mappé survit-il à un reparamétrage ? -----------------
    #     Le cas qui compte : la garde de rejeu existe précisément parce
    #     qu'une cote change et que les indices bougent.
    kernel.set_param(pad_nom, "Length", 25.0)
    kernel._doc.recompute()
    apres = kernel._doc.getObject(pad_nom).Shape
    resolu = attr(apres, "getElementIndexedName")
    resolu = resolu(mappe) if callable(resolu) else None
    if isinstance(resolu, (tuple, list)):
        resolu = resolu[0] if resolu else None
    probe("survie_reparam", VERIFIE if resolu else ECHOUE,
          "après 10 -> 25 mm, {!r} -> {!r}".format(mappe, resolu))

    # --- 5. l'historique d'élément remonte-t-il ? -----------------------
    histoire = attr(pad, "getElementHistory")
    if not callable(histoire):
        probe("historique_élément", INVERIFIABLE,
              "Part::Feature.getElementHistory absent sur cet objet")
        return
    try:
        trace = histoire(mappe)
    except Exception as exc:  # noqa: BLE001 - une sonde rapporte, ne lève pas
        probe("historique_élément", ECHOUE,
              "{}: {}".format(type(exc).__name__, exc))
        return
    probe("historique_élément", VERIFIE if trace else ECHOUE, repr(trace))


try:
    main()
except Exception as exc:  # noqa: BLE001 - la sonde rapporte sa propre casse
    probe("sonde", ECHOUE, "{}: {}".format(type(exc).__name__, exc))

verdict = {
    "spike": "A7 — carte d'éléments",
    "sondes": probes,
    "verifie": sum(1 for p in probes if p["état"] == VERIFIE),
    "echoue": sum(1 for p in probes if p["état"] == ECHOUE),
    "inverifiable": sum(1 for p in probes if p["état"] == INVERIFIABLE),
}
with open(_REPORT_PATH, "w", encoding="utf-8") as fh:
    json.dump(verdict, fh, ensure_ascii=False, indent=2)
print("spike> verdict écrit dans {}".format(_REPORT_PATH), flush=True)
print("spike> {} vérifié · {} échoué · {} invérifiable".format(
    verdict["verifie"], verdict["echoue"], verdict["inverifiable"]), flush=True)
