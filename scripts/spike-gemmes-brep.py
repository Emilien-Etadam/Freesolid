"""Sonde : une gemme est un BREP, pas une fonction paramétrique.

Usage :  freecadcmd scripts/spike-gemmes-brep.py

Le relevé de `docs/bijouterie.md` chiffrait les 17 tailles de pierre comme
« le gros du travail : à re-modeler en BRep **paramétrique** ». C'est faux,
et cette sonde le vérifie plutôt que de le décréter.

Une taille de pierre est une **géométrie normalisée et figée** : un brillant
rond a 57 facettes dans des proportions données. Personne ne réédite l'angle
de couronne d'un diamant dans un historique — on choisit la taille et la
dimension. L'historique paramétrique est donc de la machinerie **inutile** ;
ce qu'il faut, c'est une forme **exacte**, mise à l'échelle en x, y, z.

D'où six questions :

  G1  aller-retour   `.brep` rend-il la forme au bit près, et à quel prix
                     en octets et en millisecondes ?
  G2  échelle        une mise à l'échelle NON uniforme (rond → ovale) :
                     que deviennent les surfaces ?
  G3  carat          le volume se multiplie-t-il par sx·sy·sz ? Si oui, le
                     « facteur de correction » que JewelCraft TABULE se
                     DÉRIVE ici, une fois par taille, et devient exact
  G4  booléen        une gemme importée sert-elle d'outil pour le siège ?
  G5  instances      200 gemmes importées via App::Link
  G6  poids          ce que pèse la bibliothèque sur le disque

Ne lève jamais : chaque question note sa réponse ou son erreur.
"""

import json
import math
import os
import shutil
import sys
import tempfile
import time

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

R = {"freecad": ".".join(str(v) for v in App.Version()[:3])}
TMP = tempfile.mkdtemp(prefix="freesolid-gemmes-")


def note(key, fn):
    try:
        R[key] = fn()
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        R[key] = None
        R[key + "_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])


# --------------------------------------------------------------------------
# Le banc d'essai : un brillant rond, en deux versions.
#
# Proportions réelles, rapportées au diamètre de rondiste = 1 :
# table 57 %, couronne 16,2 %, rondiste 3 %, culasse 43 %.
# --------------------------------------------------------------------------

TABLE_R, TABLE_Z = 0.285, 0.162
GIRDLE_R, GIRDLE_Z = 0.5, 0.0
GIRDLE_BAS = -0.03
CULET_R, CULET_Z = 0.01, -0.46


def polygon_wire(radius, z, sides=16):
    pts = [App.Vector(radius * math.cos(2 * math.pi * i / sides),
                      radius * math.sin(2 * math.pi * i / sides), z)
           for i in range(sides)]
    pts.append(pts[0])
    return Part.makePolygon(pts)


def circle_wire(radius, z):
    return Part.Wire(Part.makeCircle(radius, App.Vector(0, 0, z)))


def gemme_facettee():
    """Toutes faces planes — le cas d'une vraie taille, rondiste facetté.

    Culet en petit polygone plutôt qu'en sommet : un vrai brillant a
    souvent une facette de culet, et un loft sur sommet est le genre de
    cas limite qu'on n'a pas envie de découvrir en production.
    """
    return Part.makeLoft([polygon_wire(CULET_R, CULET_Z),
                          polygon_wire(GIRDLE_R, GIRDLE_BAS),
                          polygon_wire(GIRDLE_R, GIRDLE_Z),
                          polygon_wire(TABLE_R, TABLE_Z)], True, True)


def gemme_analytique():
    """Rondiste cylindrique, couronne et culasse coniques — le cas où la
    mise à l'échelle non uniforme peut abîmer les surfaces."""
    return Part.makeLoft([circle_wire(CULET_R, CULET_Z),
                          circle_wire(GIRDLE_R, GIRDLE_BAS),
                          circle_wire(GIRDLE_R, GIRDLE_Z),
                          circle_wire(TABLE_R, TABLE_Z)], True, True)


GEMMES = {}


def build():
    GEMMES["facettee"] = gemme_facettee()
    GEMMES["analytique"] = gemme_analytique()
    return {name: {"faces": len(g.Faces), "aretes": len(g.Edges),
                   "volume_mm3": round(g.Volume, 9),
                   "valide": g.isValid(), "solide": len(g.Solids) == 1}
            for name, g in GEMMES.items()}


note("banc", build)


def read_brep(path):
    """Relit un `.brep`. Le nom de la méthode n'est pas gravé dans le
    marbre selon les versions — on essaie, et on dit laquelle a marché."""
    try:
        shape = Part.Shape()
        shape.importBrep(path)
        R.setdefault("lecteur_brep", "Shape.importBrep")
        return shape
    except Exception:  # noqa: BLE001
        R["lecteur_brep"] = "Part.read"
        return Part.read(path)


def surface_types(shape):
    counts = {}
    for face in shape.Faces:
        key = face.Surface.TypeId.replace("Part::Geom", "")
        counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------
# G1 — l'aller-retour .brep : exact, ou « à peu près » ?
# --------------------------------------------------------------------------

def probe_roundtrip():
    out = {}
    for name, gem in GEMMES.items():
        path = os.path.join(TMP, name + ".brep")
        gem.exportBrep(path)

        t0 = time.time()
        back = read_brep(path)
        t_read = time.time() - t0

        out[name] = {
            "octets": os.path.getsize(path),
            "lecture_ms": round(t_read * 1000.0, 3),
            "faces_identiques": len(back.Faces) == len(gem.Faces),
            "aretes_identiques": len(back.Edges) == len(gem.Edges),
            # Au bit près, ou seulement à la tolérance près ?
            "ecart_volume_mm3": abs(back.Volume - gem.Volume),
            "exact": abs(back.Volume - gem.Volume) == 0.0,
            "valide": back.isValid(),
            "surfaces": surface_types(back),
        }
    return out


note("g1_aller_retour", probe_roundtrip)


# --------------------------------------------------------------------------
# G2 — rond → ovale. Une gemme se dimensionne en x, y, z INDÉPENDANTS.
#      transformGeometry() applique une affinité : un plan reste un plan,
#      mais un cylindre ne reste pas un cylindre.
# --------------------------------------------------------------------------

def scaled(shape, sx, sy, sz):
    m = App.Matrix()
    m.A11, m.A22, m.A33 = sx, sy, sz
    return shape.transformGeometry(m)


def probe_scale():
    out = {}
    for name, gem in GEMMES.items():
        # 4 × 6 × 2,5 mm : un ovale, donc x ≠ y — le cas qui mord.
        oval = scaled(gem, 4.0, 6.0, 2.5)
        box = oval.BoundBox
        out[name] = {
            "surfaces_avant": surface_types(gem),
            "surfaces_apres": surface_types(oval),
            "types_preserves": surface_types(gem) == surface_types(oval),
            "valide": oval.isValid(),
            "solide": len(oval.Solids) == 1,
            "encombrement": [round(box.XLength, 6), round(box.YLength, 6),
                             round(box.ZLength, 6)],
            "faces": len(oval.Faces),
        }
    return out


note("g2_echelle", probe_scale)


# --------------------------------------------------------------------------
# G3 — LE point. Si Volume(mis à l'échelle) == Volume(base) × sx·sy·sz,
#      alors le rapport Volume / (x·y·z) est INVARIANT : c'est le « facteur
#      de correction » de JewelCraft, mais DÉRIVÉ de la géométrie au lieu
#      d'être tabulé — donc exact, et calculé une seule fois par taille.
# --------------------------------------------------------------------------

def probe_carat():
    out = {}
    for name, gem in GEMMES.items():
        base = gem.Volume  # rondiste ø 1 mm
        rows = {}
        facteurs = []
        for sx, sy, sz in ((1.0, 1.0, 1.0), (2.0, 2.0, 2.0),
                           (4.0, 6.0, 2.5), (10.0, 3.0, 7.0)):
            v = scaled(gem, sx, sy, sz).Volume
            attendu = base * sx * sy * sz
            # x, y, z de la pierre = son encombrement réel.
            facteur = v / (sx * sy * sz * (2 * GIRDLE_R) * (2 * GIRDLE_R)
                           * (TABLE_Z - CULET_Z))
            facteurs.append(facteur)
            rows["{}x{}x{}".format(sx, sy, sz)] = {
                "volume_mm3": round(v, 9),
                "attendu_mm3": round(attendu, 9),
                "ecart_relatif": abs(v - attendu) / attendu if attendu else None,
            }
        rows["multiplicatif"] = all(
            r["ecart_relatif"] < 1e-9 for r in rows.values()
            if isinstance(r, dict) and r.get("ecart_relatif") is not None)
        # Invariant ⇒ un seul nombre par taille suffit, pour toutes les
        # dimensions. C'est la table de JewelCraft, rendue exacte.
        rows["facteur_derive"] = round(sum(facteurs) / len(facteurs), 6)
        rows["facteur_invariant"] = (max(facteurs) - min(facteurs)) < 1e-9
        out[name] = rows
    return out


note("g3_carat", probe_carat)


# --------------------------------------------------------------------------
# G4 — la gemme importée comme OUTIL : creuser le siège sous la pierre.
#      Les facettes vives et les faces coïncidentes font trébucher OCCT ;
#      c'est le moment de le savoir.
# --------------------------------------------------------------------------

def probe_boolean():
    band = (Part.makeCylinder(10.0, 6.0)
            .cut(Part.makeCylinder(8.5, 6.0)))
    out = {}
    for name, gem in GEMMES.items():
        path = os.path.join(TMP, name + ".brep")
        tool = read_brep(path)
        seat = scaled(tool, 3.0, 3.0, 3.0)
        # Table vers l'extérieur du jonc : +Z local amené sur +X.
        seat.Placement = App.Placement(
            App.Vector(9.5, 0, 3.0), App.Rotation(App.Vector(0, 1, 0), 90))
        t0 = time.time()
        cut = band.cut(seat)
        dt = time.time() - t0
        out[name] = {
            "duree_ms": round(dt * 1000.0, 2),
            "valide": cut.isValid(),
            "solides": len(cut.Solids),
            "a_enleve_de_la_matiere": cut.Volume < band.Volume - 1e-9,
            "volume_enleve_mm3": round(band.Volume - cut.Volume, 6),
        }
    return out


note("g4_booleen_siege", probe_boolean)


# --------------------------------------------------------------------------
# G5 — 200 gemmes importées, une seule forme, N placements.
# --------------------------------------------------------------------------

def probe_instances(count=200):
    doc = App.newDocument("SpikeGemmes")
    try:
        shape = read_brep(os.path.join(TMP, "facettee.brep"))
        feat = doc.addObject("Part::Feature", "Brillant")
        feat.Shape = scaled(shape, 3.0, 3.0, 3.0)
        link = doc.addObject("App::Link", "Semis")
        link.LinkedObject = feat
        link.ElementCount = count
        t0 = time.time()
        link.PlacementList = [
            App.Placement(App.Vector(10.0 * math.cos(2 * math.pi * i / count),
                                     10.0 * math.sin(2 * math.pi * i / count),
                                     0.0), App.Rotation())
            for i in range(count)]
        doc.recompute()
        pose = time.time() - t0

        path = os.path.join(TMP, "semis.FCStd")
        doc.saveAs(path)
        return {
            "pierres": count,
            "pose_s": round(pose, 3),
            "placements_retenus": len(link.PlacementList),
            # Une forme pour 200 pierres : le document ne doit pas enfler.
            "fcstd_octets": os.path.getsize(path),
            "octets_par_pierre": round(os.path.getsize(path) / count, 1),
        }
    finally:
        App.closeDocument(doc.Name)


note("g5_instances", probe_instances)


# --------------------------------------------------------------------------
# G6 — ce que pèserait la bibliothèque : 17 tailles sur le disque.
# --------------------------------------------------------------------------

def probe_library():
    brep = os.path.getsize(os.path.join(TMP, "facettee.brep"))
    doc = App.newDocument("SpikeUneGemme")
    try:
        feat = doc.addObject("Part::Feature", "Brillant")
        feat.Shape = GEMMES["facettee"]
        path = os.path.join(TMP, "une-gemme.FCStd")
        doc.saveAs(path)
        fcstd = os.path.getsize(path)
    finally:
        App.closeDocument(doc.Name)
    return {
        "brep_octets": brep,
        "fcstd_octets": fcstd,
        "17_tailles_en_brep_ko": round(brep * 17 / 1024.0, 1),
        "17_tailles_en_fcstd_ko": round(fcstd * 17 / 1024.0, 1),
    }


note("g6_bibliotheque", probe_library)

shutil.rmtree(TMP, ignore_errors=True)

# --------------------------------------------------------------------------

print(json.dumps(R, ensure_ascii=False, indent=1, default=str), flush=True)

verdict = {
    "G1 aller-retour exact": all(
        v.get("exact") for v in (R.get("g1_aller_retour") or {"_": {}}).values()),
    "G2 échelle non uniforme": all(
        v.get("solide") for v in (R.get("g2_echelle") or {"_": {}}).values()),
    "G3 volume multiplicatif": all(
        v.get("multiplicatif") for v in (R.get("g3_carat") or {"_": {}}).values()),
    "G4 gemme en outil": all(
        v.get("valide") and v.get("a_enleve_de_la_matiere")
        for v in (R.get("g4_booleen_siege") or {"_": {}}).values()),
    "G5 200 instances": bool((R.get("g5_instances") or {}).get("pierres")),
}
print("\n".join("{}  {}".format("OK  " if v else "NON ", k)
                for k, v in verdict.items()), flush=True)
print("\nSONDE {} — G3 est le verdict : si le volume se multiplie, le carat\n"
      "se calcule EXACTEMENT, et le facteur tabulé de JewelCraft disparaît."
      .format("VERTE" if all(verdict.values()) else "ROUGE"), flush=True)
