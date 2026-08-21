"""Spike A4/A5 — les deux contournements TechDraw servent-ils encore ?

Usage :  freecadcmd scripts/spike-techdraw-coupe.py
         FREESOLID_SPIKE_PROBE=base-parallele   # une sonde à la fois
         FREESOLID_SPIKE_PROBE=cut-surface-hide

``engine/kernel.py:1126-1136`` porte deux contournements écrits contre
FreeCAD 1.0.0 :

1. **base-parallele** — la vue de base d'une coupe doit avoir une
   Direction non parallèle à la normale, « sinon TechDraw n'arrive pas à
   construire le CS (getSectionCS) et le cut async peut SIGSEGV ».
2. **cut-surface-hide** — hachures laissées au défaut SvgHatch, parce que
   ``CutSurfaceDisplay=Hide`` faisait SIGSEGV en 1.0.0 headless.

La lecture de la source amont (``docs/amont-freecad.md`` §4) a montré
qu'en 1.1.3 ``DrawViewSection::getSectionCS()`` enveloppe déjà la
construction du repère dans un ``try/catch`` et journalise au lieu de
planter — la prémisse de (1) est donc probablement périmée. Reste à le
vérifier **à l'exécution**, ce que seul un FreeCAD réel peut faire.

⚠️ **Ce script peut mourir d'un SIGSEGV** — c'est même son objet. Il
n'est donc PAS branché sur la CI : un crash tuerait le job. Il journalise
dans ``spike-techdraw-coupe.txt`` **avant** chaque étape risquée, et le
fichier est vidé sur disque à chaque ligne : après un crash, la dernière
ligne du journal nomme la sonde qui a tué le processus.
"""

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

_JOURNAL_PATH = os.environ.get(
    "FREESOLID_SPIKE_JOURNAL",
    os.path.join(_REPO, "spike-techdraw-coupe.txt"))

#: Quelle sonde jouer. Vide = les deux, dans l'ordre. On passe par
#: l'environnement et non par ``sys.argv`` : ``freecadcmd`` **importe**
#: le fichier comme module (cf. AGENTS.md), donc argv est celui de
#: FreeCAD, pas le nôtre.
_PROBE = (os.environ.get("FREESOLID_SPIKE_PROBE") or "").strip().lower()

_journal = open(_JOURNAL_PATH, "w", encoding="utf-8")


def note(ligne):
    """Écrit une ligne de journal et la force sur le disque.

    Le ``fsync`` est le point entier du script : si la ligne suivante
    n'existe pas, c'est que l'étape annoncée a tué le processus.
    """
    _journal.write(ligne + "\n")
    _journal.flush()
    os.fsync(_journal.fileno())
    print("spike> " + ligne, flush=True)


def _page_avec_vues(kernel):
    """Page TechDraw + les trois vues de ``make_drawing``, sans coupe.

    Reproduit ``engine/kernel.py`` (placements Face / Dessus / Iso) parce
    que ``make_drawing`` retire sa page après export : la sonde a besoin
    d'objets vivants.
    """
    doc = kernel._require_doc()
    body = kernel._require_body()
    App = kernel._app()
    page = doc.addObject("TechDraw::DrawPage", "Page")
    template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    chemin = os.path.join(App.getResourceDir(), "Mod", "TechDraw",
                          "Templates", "A4_LandscapeTD.svg")
    if os.path.exists(chemin):
        template.Template = chemin
    page.Template = template
    vues = {}
    for nom, direction, x, y in (("Face", (0, -1, 0), 70, 60),
                                 ("Dessus", (0, 0, 1), 70, 150),
                                 ("Iso", (1, -1, 1), 210, 105)):
        vue = doc.addObject("TechDraw::DrawViewPart", "View" + nom)
        vue.Source = [body]
        vue.Direction = App.Vector(*direction)
        vue.CoarseView = True
        page.addView(vue)
        vue.X, vue.Y = x, y
        vues[nom] = vue
    doc.recompute()
    return doc, body, App, page, vues


def _coupe(doc, body, App, page, base, nom):
    """Une DrawViewSection de normale Z, ancrée sur la vue ``base``."""
    section = doc.addObject("TechDraw::DrawViewSection", nom)
    page.addView(section)
    section.Source = [body]
    section.BaseView = base
    section.SectionNormal = App.Vector(0, 0, 1)
    section.SectionOrigin = App.Vector(0, 0, 0)
    section.Direction = App.Vector(0, 0, 1)
    section.X = float(base.X) + 80
    section.Y = float(base.Y)
    return section


def _etat(section):
    etat = list(getattr(section, "State", []) or [])
    aretes = None
    try:
        aretes = len(section.getVisibleEdges())
    except Exception:  # noqa: BLE001 - l'API varie, l'état suffit
        pass
    return "State={} arêtes visibles={}".format(etat, aretes)


def sonde_base_parallele(kernel):
    """Vue de base **parallèle** à la normale — le cas que (1) évite.

    ``ViewDessus`` a la Direction (0,0,1), donc exactement la normale de
    coupe : c'est la configuration que ``_drawing_add_section`` refuse.
    """
    doc, body, App, page, vues = _page_avec_vues(kernel)
    note("sonde base-parallele : DÉBUT — BaseView=ViewDessus (0,0,1), "
         "normale (0,0,1) ; c'est ici que 1.0.0 mourait")
    section = _coupe(doc, body, App, page, vues["Dessus"], "CoupeParallele")
    doc.recompute()
    note("sonde base-parallele : SURVÉCU — " + _etat(section))
    note("  => le contournement (1) n'est plus nécessaire sur cette version, "
         "sous réserve que l'état ci-dessus soit exploitable")


def sonde_cut_surface_hide(kernel):
    """``CutSurfaceDisplay = Hide`` — le cas que (2) évite."""
    doc, body, App, page, vues = _page_avec_vues(kernel)
    section = _coupe(doc, body, App, page, vues["Face"], "CoupeHide")
    doc.recompute()
    note("sonde cut-surface-hide : coupe sûre construite — " + _etat(section))
    if not hasattr(section, "CutSurfaceDisplay"):
        note("sonde cut-surface-hide : SANS OBJET — la propriété n'existe "
             "plus sur cette version")
        return
    permis = []
    try:
        permis = list(section.getEnumerationsOfProperty("CutSurfaceDisplay"))
    except Exception:  # noqa: BLE001
        pass
    if permis and "Hide" not in permis:
        note("sonde cut-surface-hide : SANS OBJET — « Hide » absent de {}"
             .format(permis))
        return
    note("sonde cut-surface-hide : DÉBUT — CutSurfaceDisplay='Hide' puis "
         "recompute ; c'est ici que 1.0.0 mourait")
    section.CutSurfaceDisplay = "Hide"
    doc.recompute()
    note("sonde cut-surface-hide : SURVÉCU — " + _etat(section))
    note("  => le contournement (2) n'est plus nécessaire sur cette version")


def main():
    from engine.kernel import Kernel
    from engine.platform import allow_from_environ, version_status

    kernel = Kernel()
    plateforme = version_status(
        kernel.ping()["freecad"], allow=allow_from_environ())
    note("FreeCAD {} (référence {})".format(
        plateforme["running"], plateforme["reference"]))

    kernel.new_part("Spike coupe")
    kernel.add_rect_sketch(100, 60)
    kernel.add_pad(10)
    note("pièce de test prête : rectangle 100×60 bossé de 10 mm")

    sondes = [("base-parallele", sonde_base_parallele),
              ("cut-surface-hide", sonde_cut_surface_hide)]
    if _PROBE:
        sondes = [(nom, fn) for nom, fn in sondes if nom == _PROBE]
        if not sondes:
            note("FREESOLID_SPIKE_PROBE={!r} inconnu — attendu "
                 "base-parallele ou cut-surface-hide".format(_PROBE))
            return
    for nom, fn in sondes:
        try:
            fn(kernel)
        except Exception as exc:  # noqa: BLE001 - une sonde rapporte
            note("sonde {} : EXCEPTION {}: {}".format(
                nom, type(exc).__name__, exc))


try:
    main()
    note("FIN — aucune sonde n'a tué le processus")
except Exception as exc:  # noqa: BLE001
    note("SPIKE CASSÉ (hors sonde) {}: {}".format(type(exc).__name__, exc))
finally:
    _journal.close()
