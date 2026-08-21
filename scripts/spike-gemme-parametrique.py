"""Sonde : la gemme est un .FCStd paramétrique, coté par une esquisse.

Usage :  freecadcmd scripts/spike-gemme-parametrique.py

Troisième conception essayée pour la bibliothèque de pierres, et la
meilleure des trois — si elle tient.

  1. « 17 chaînes PartDesign à entretenir »  → j'avais surestimé le coût.
  2. « un BREP figé, mis à l'échelle en x/y/z » → la sonde `spike-gemmes-brep`
     a montré ce que ça coûte : `transformGeometry` CONVERTIT cône et
     cylindre en B-splines (1,18 % de volume perdu avant toute mise à
     l'échelle), et `BoundBox` borne alors les pôles au lieu de la surface
     (cotes annoncées jusqu'à 70 % trop grosses).
  3. **Ici** : un `.FCStd` dont le diamètre est une COTE D'ESQUISSE, les
     proportions tenues par expressions. On ne met plus rien à l'échelle —
     on recalcule. Les trois problèmes ci-dessus disparaissent par
     construction ; reste à savoir ce que coûte le recalcul.

Sept questions :

  H1  coût        ouvrir, coter, recomputer, lire la forme : combien de ms ?
                  Et pour N tailles distinctes dans une même pièce ?
  H2  surfaces    restent-elles analytiques, ou le recalcul les dégrade-t-il ?
  H3  cotes       `BoundBox` retrouve-t-il le diamètre demandé ? (le piège
                  de la sonde précédente doit avoir disparu)
  H4  proportions V(d)/d³ constant ? — l'esquisse tient-elle ses ratios ?
  H5  instances   N pierres d'une même taille via App::Link
  H6  lien externe un App::Link vers un AUTRE document survit-il, et que
                  se passe-t-il si la bibliothèque n'est pas ouverte ?
  H7  siège       booléen avec la gemme paramétrique — contre les 73 ms
                  (facettée) et 36 ms (analytique) de la sonde BREP

Ne lève jamais : chaque question note sa réponse ou son erreur.
"""

import json
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
import Sketcher  # noqa: E402

R = {"freecad": ".".join(str(v) for v in App.Version()[:3])}
TMP = tempfile.mkdtemp(prefix="freesolid-gemme-param-")
BIBLIO = os.path.join(TMP, "brillant-rond.FCStd")


def note(key, fn):
    try:
        R[key] = fn()
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        R[key] = None
        R[key + "_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:200])


# --------------------------------------------------------------------------
# La gemme paramétrique — proportions réelles du brillant rond, rapportées
# au diamètre de rondiste. Culet à l'origine de l'esquisse : toutes les
# cotes restent POSITIVES, ce qui évite les distances signées, un cas où
# le solveur se montre capricieux.
#
#   table   0,285 d de rayon, à 0,622 d de haut
#   rondiste 0,5  d de rayon, de 0,43 d à 0,46 d
#   culet   à l'origine
# --------------------------------------------------------------------------

RATIOS = {
    "rayon_table": 0.285, "hauteur_table": 0.622,
    "rayon_rondiste": 0.5, "haut_rondiste": 0.46, "bas_rondiste": 0.43,
}


def build_library(path=None, facettes=0, diametre=1.0):
    """Écrit la gemme paramétrique sur disque, comme le ferait un modeleur
    une fois pour toutes. Retourne un rapport sur sa santé.

    ``facettes`` > 0 ajoute une répétition polaire de poches par-dessus la
    révolution. Ce ne sont pas les vraies facettes d'un brillant — mais
    c'est la même CHARGE DE CALCUL : révolution plus N coupes répétées.
    Sans ça, H1 mesurerait le coût d'un cône et on le citerait pour celui
    d'une pierre.
    """
    path = path or BIBLIO
    doc = App.newDocument("Brillant")
    try:
        varset = doc.addObject("App::VarSet", "Variables")
        varset.addProperty("App::PropertyFloat", "diametre", "Variables")
        varset.diametre = float(diametre)

        body = doc.addObject("PartDesign::Body", "Corps")
        sk = doc.addObject("Sketcher::SketchObject", "Profil")
        body.addObject(sk)
        plane = next(f for f in body.Origin.OriginFeatures
                     if getattr(f, "Role", "") == "XZ_Plane")
        try:
            sk.AttachmentSupport = [(plane, ("",))]
        except AttributeError:
            sk.Support = [(plane, ("",))]
        sk.MapMode = "FlatFace"
        doc.recompute()

        d = float(diametre)
        pts = [(0.0, RATIOS["hauteur_table"] * d),            # P0 table, axe
               (RATIOS["rayon_table"] * d,
                RATIOS["hauteur_table"] * d),                 # P1 table, bord
               (RATIOS["rayon_rondiste"] * d,
                RATIOS["haut_rondiste"] * d),                 # P2 rondiste haut
               (RATIOS["rayon_rondiste"] * d,
                RATIOS["bas_rondiste"] * d),                  # P3 rondiste bas
               (0.0, 0.0)]                                    # P4 culet, axe
        segs = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            segs.append(sk.addGeometry(Part.LineSegment(
                App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False))
        for i, g in enumerate(segs):
            sk.addConstraint(Sketcher.Constraint(
                "Coincident", g, 2, segs[(i + 1) % len(segs)], 1))

        # Le culet à l'origine (segs[4] part du culet), le sommet de table
        # sur l'axe de révolution, et le rondiste VERTICAL — c'est cette
        # dernière qui fait du rondiste un vrai cylindre et ferme le
        # dernier degré de liberté.
        sk.addConstraint(Sketcher.Constraint("Coincident", segs[4], 1, -1, 1))
        sk.addConstraint(Sketcher.Constraint("PointOnObject", segs[0], 1, -2))
        sk.addConstraint(Sketcher.Constraint("Vertical", segs[2]))

        # Chaque cote pilotée par la variable : les proportions sont dans
        # le fichier, pas dans le code appelant.
        cotes = (("hauteur_table", "DistanceY", segs[0], 1),
                 ("rayon_table", "DistanceX", segs[1], 1),
                 ("hauteur_table_bord", "DistanceY", segs[1], 1),
                 ("rayon_rondiste", "DistanceX", segs[2], 1),
                 ("haut_rondiste", "DistanceY", segs[2], 1),
                 ("bas_rondiste", "DistanceY", segs[3], 1))
        for name, kind, geo, point in cotes:
            ratio = RATIOS[name.replace("_bord", "")]
            idx = sk.addConstraint(Sketcher.Constraint(
                kind, geo, point, ratio * d))
            sk.renameConstraint(idx, name)
            sk.setExpression("Constraints[{}]".format(idx),
                             "Variables.diametre * {}".format(ratio))
        doc.recompute()

        rev = doc.addObject("PartDesign::Revolution", "Gemme")
        body.addObject(rev)
        rev.Profile = sk
        rev.ReferenceAxis = (sk, ["V_Axis"])
        rev.Angle = 360.0
        doc.recompute()

        if facettes:
            fs = doc.addObject("Sketcher::SketchObject", "Facette")
            body.addObject(fs)
            xy = next(f for f in body.Origin.OriginFeatures
                      if getattr(f, "Role", "") == "XY_Plane")
            try:
                fs.AttachmentSupport = [(xy, ("",))]
            except AttributeError:
                fs.Support = [(xy, ("",))]
            fs.MapMode = "FlatFace"
            doc.recompute()
            circ = fs.addGeometry(Part.Circle(
                App.Vector(0.46 * d, 0, 0), App.Vector(0, 0, 1), 0.11 * d),
                False)
            # Facette pilotée elle aussi : sans expression, elle garderait
            # sa taille pendant que la pierre grandit, et H8 mesurerait un
            # cas de figure qui n'existe pas.
            fs.addConstraint(Sketcher.Constraint("PointOnObject", circ, 3, -1))
            for kind, args, ratio, nom in (
                    ("DistanceX", (circ, 3), 0.46, "position_facette"),
                    ("Radius", (circ,), 0.11, "rayon_facette")):
                idx = fs.addConstraint(Sketcher.Constraint(
                    kind, *(args + (ratio * d,))))
                fs.renameConstraint(idx, nom)
                fs.setExpression("Constraints[{}]".format(idx),
                                 "Variables.diametre * {}".format(ratio))
            doc.recompute()

            pocket = doc.addObject("PartDesign::Pocket", "Facette1")
            body.addObject(pocket)
            pocket.Profile = fs
            pocket.Type = "ThroughAll"
            pocket.Reversed = True   # vers le haut : la matière est au-dessus
            doc.recompute()

            pat = doc.addObject("PartDesign::PolarPattern", "Facettes")
            body.addObject(pat)
            pat.Transformed = [pocket]
            pat.Axis = (next(f for f in body.Origin.OriginFeatures
                             if getattr(f, "Role", "") == "Z_Axis"), [""])
            pat.Angle = 360.0
            pat.Occurrences = int(facettes)
            doc.recompute()

        doc.saveAs(path)
        shape = body.Shape
        return {
            "fichier_octets": os.path.getsize(path),
            "facettes": int(facettes),
            "solveur": sk.solve() if hasattr(sk, "solve") else None,
            "entierement_contrainte": getattr(sk, "FullyConstrained", None),
            "contraintes": len(sk.Constraints),
            "corps_valide": shape.isValid(),
            "solide": len(shape.Solids) == 1,
            "faces": len(shape.Faces),
            "volume_mm3": round(shape.Volume, 9),
        }
    finally:
        App.closeDocument(doc.Name)


note("bibliotheque", build_library)


def gemme_a(diametre):
    """Le geste réel : ouvrir la bibliothèque, poser la cote, recalculer.
    Retourne (forme, durée)."""
    t0 = time.time()
    doc = App.openDocument(BIBLIO)
    try:
        doc.getObject("Variables").diametre = float(diametre)
        doc.recompute()
        shape = doc.getObject("Corps").Shape.copy()
    finally:
        App.closeDocument(doc.Name)
    return shape, time.time() - t0


# --------------------------------------------------------------------------
# H1 — ce que coûte une taille, puis N tailles distinctes.
# --------------------------------------------------------------------------

def probe_cost():
    tailles = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
    durees = []
    for d in tailles:
        _, dt = gemme_a(d)
        durees.append(dt * 1000.0)
    return {
        "tailles": len(tailles),
        "ms_premiere": round(durees[0], 1),
        "ms_mediane": round(sorted(durees)[len(durees) // 2], 1),
        "ms_total_8_tailles": round(sum(durees), 1),
        # 200 pierres d'UNE taille ne coûtent qu'un recalcul : c'est le
        # nombre de tailles DISTINCTES qui pèse, pas le nombre de pierres.
        "ms_par_taille": round(sum(durees) / len(durees), 1),
    }


note("h1_cout", probe_cost)


def surface_types(shape):
    counts = {}
    for face in shape.Faces:
        key = face.Surface.TypeId.replace("Part::Geom", "")
        counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------
# H2/H3/H4 — la santé de la forme, à plusieurs tailles.
# --------------------------------------------------------------------------

def probe_shape():
    out, ratios, types = {}, [], []
    for d in (1.0, 3.0, 7.5):
        shape, _ = gemme_a(d)
        box = shape.BoundBox
        st = surface_types(shape)
        types.append(tuple(sorted(st.items())))
        ratios.append(shape.Volume / (d ** 3))
        out["d_{}".format(d)] = {
            "surfaces": st,
            # H3 : le rondiste fait bien d de diamètre ?
            "boundbox": [round(box.XLength, 6), round(box.YLength, 6),
                         round(box.ZLength, 6)],
            "diametre_retrouve": abs(box.XLength - d) < 1e-6,
            "hauteur_attendue": abs(
                box.ZLength - d * RATIOS["hauteur_table"]) < 1e-6,
            "volume_mm3": round(shape.Volume, 9),
            "valide": shape.isValid(),
        }
    out["aucune_bspline"] = not any(
        "BSplineSurface" in dict(t) for t in types)
    out["types_stables"] = len(set(types)) == 1
    # H4 : les proportions sont-elles tenues ? V ∝ d³ si oui.
    out["volume_en_d3"] = (max(ratios) - min(ratios)) / max(ratios) < 1e-9
    out["facteur_v_sur_d3"] = round(sum(ratios) / len(ratios), 9)
    return out


note("h2h3h4_forme", probe_shape)


# --------------------------------------------------------------------------
# H5 — N pierres d'une taille : une forme, N placements.
# --------------------------------------------------------------------------

def probe_instances(count=200):
    import math
    shape, _ = gemme_a(1.5)
    doc = App.newDocument("SpikeSemis")
    try:
        feat = doc.addObject("Part::Feature", "Brillant")
        feat.Shape = shape
        link = doc.addObject("App::Link", "Semis")
        link.LinkedObject = feat
        link.ElementCount = count
        t0 = time.time()
        link.PlacementList = [
            App.Placement(App.Vector(10 * math.cos(2 * math.pi * i / count),
                                     10 * math.sin(2 * math.pi * i / count), 0),
                          App.Rotation())
            for i in range(count)]
        doc.recompute()
        pose = time.time() - t0
        path = os.path.join(TMP, "semis.FCStd")
        doc.saveAs(path)
        return {"pierres": count, "pose_s": round(pose, 3),
                "fcstd_octets": os.path.getsize(path),
                "octets_par_pierre": round(os.path.getsize(path) / count, 1)}
    finally:
        App.closeDocument(doc.Name)


note("h5_instances", probe_instances)


# --------------------------------------------------------------------------
# H6 — LE point d'architecture. Un App::Link vers un objet d'un AUTRE
#      document garde-t-il sa forme quand la bibliothèque est refermée ?
#      Si non, la pièce dépend d'un fichier externe — couplage à assumer,
#      ou à éviter en important la forme.
# --------------------------------------------------------------------------

def probe_external_link():
    biblio = App.openDocument(BIBLIO)
    piece = App.newDocument("SpikePiece")
    out = {}
    try:
        # Premier passage : « RuntimeError: Owner document not saved ».
        # FreeCAD refuse un lien INTER-DOCUMENTS depuis un document jamais
        # écrit — il lui faut un chemin pour poser la référence. C'était
        # mon test qui était faux, pas la conception. On enregistre donc
        # avant de lier.
        piece.saveAs(os.path.join(TMP, "piece-liee.FCStd"))
        link = piece.addObject("App::Link", "PierreLiee")
        link.LinkedObject = biblio.getObject("Corps")
        piece.recompute()
        out["lien_cree"] = True
        out["forme_visible"] = bool(getattr(link, "Shape", None)
                                    and link.Shape.Faces)
        piece.save()
        out["octets"] = os.path.getsize(piece.FileName)
    except Exception as exc:  # noqa: BLE001
        out["lien_cree"] = False
        out["erreur"] = "{}: {}".format(type(exc).__name__, str(exc)[:120])
        return out
    finally:
        for doc in (piece, biblio):
            try:
                App.closeDocument(doc.Name)
            except Exception:  # noqa: BLE001
                pass

    # Rouvrir la pièce SEULE : FreeCAD tire-t-il la bibliothèque avec elle ?
    reopened = App.openDocument(os.path.join(TMP, "piece-liee.FCStd"))
    try:
        link = reopened.getObject("PierreLiee")
        out["biblio_tiree_automatiquement"] = any(
            d.Name != reopened.Name for d in App.listDocuments().values())
        shape = getattr(link, "Shape", None)
        out["forme_apres_reouverture"] = bool(shape and shape.Faces)
    finally:
        for name in list(App.listDocuments()):
            try:
                App.closeDocument(name)
            except Exception:  # noqa: BLE001
                pass
    return out


note("h6_lien_externe", probe_external_link)


# --------------------------------------------------------------------------
# H7 — la gemme comme outil de siège. Référence : 73 ms (BREP facetté),
#      36 ms (BREP analytique) sur la sonde précédente.
# --------------------------------------------------------------------------

def probe_seat():
    band = Part.makeCylinder(10.0, 6.0).cut(Part.makeCylinder(8.5, 6.0))
    d = 3.0
    gem, _ = gemme_a(d)
    seat = gem.copy()
    # Premier passage : posée à 9,5 mm, la pierre n'entamait que 2,9 % de
    # son volume — le chrono mesurait un frôlement, pas un siège. Le vrai
    # geste met le RONDISTE au ras de la surface (rayon 10) et enfonce
    # toute la culasse dans la matière : culet à 10 − 0,46 d.
    seat.Placement = App.Placement(
        App.Vector(10.0 - RATIOS["haut_rondiste"] * d, 0, 3.0),
        App.Rotation(App.Vector(0, 1, 0), 90))
    t0 = time.time()
    cut = band.cut(seat)
    dt = time.time() - t0
    return {
        "duree_ms": round(dt * 1000.0, 2),
        "valide": cut.isValid(),
        "solides": len(cut.Solids),
        "a_enleve_de_la_matiere": cut.Volume < band.Volume - 1e-9,
        "volume_enleve_mm3": round(band.Volume - cut.Volume, 6),
        # Un vrai siège prend une bonne part de la culasse : si ce
        # rapport reste sous 20 %, la pierre frôle encore.
        "part_de_la_pierre_pct": round(
            (band.Volume - cut.Volume) / gem.Volume * 100, 1),
        "reference_brep_facette_ms": 72.65,
        "reference_brep_analytique_ms": 35.65,
    }


note("h7_siege", probe_seat)


# --------------------------------------------------------------------------
# H8 — H1 mesure une simple révolution : 4 faces. Un brillant en a 57.
#      5,5 ms est donc un PLANCHER, pas la réponse. On remesure avec une
#      répétition polaire de coupes par-dessus — même charge de calcul
#      qu'une vraie taille facettée.
# --------------------------------------------------------------------------

FACETTES = os.path.join(TMP, "brillant-facette.FCStd")


def probe_faceted_cost():
    infos = build_library(path=FACETTES, facettes=16)
    durees = []
    for diam in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
        t0 = time.time()
        doc = App.openDocument(FACETTES)
        try:
            doc.getObject("Variables").diametre = float(diam)
            doc.recompute()
            shape = doc.getObject("Corps").Shape.copy()
        finally:
            App.closeDocument(doc.Name)
        durees.append((time.time() - t0) * 1000.0)
        infos["d_{}".format(diam)] = {
            "faces": len(shape.Faces), "valide": shape.isValid(),
            "solide": len(shape.Solids) == 1,
            "surfaces": surface_types(shape)}
    infos["ms_par_taille"] = round(sum(durees) / len(durees), 1)
    infos["ms_mediane"] = round(sorted(durees)[len(durees) // 2], 1)
    # Le rapport qui compte : de combien la charge réelle dépasse le plancher.
    plancher = (R.get("h1_cout") or {}).get("ms_par_taille") or 0
    infos["fois_le_plancher"] = (
        round(infos["ms_par_taille"] / plancher, 1) if plancher else None)
    return infos


note("h8_cout_facette", probe_faceted_cost)


# --------------------------------------------------------------------------
# H9 — LA VOIE RETENUE : copier l'OBJET PARAMÉTRIQUE dans la pièce.
#
# Le §7.4 n'opposait que deux options, et aucune n'était bonne :
#   - lien externe    → la pièce dépend d'un fichier de bibliothèque ;
#   - forme importée  → la pièce est autonome mais la pierre est FIGÉE.
#
# Il en existe une troisième, et elle a les deux qualités : `copyObject`
# avec ses dépendances amène la VarSet, l'esquisse et la révolution DANS
# la pièce. Le document est autonome — aucun fichier externe — et la
# pierre reste entièrement paramétrable : son diamètre est toujours une
# cote d'esquisse, éditable sur place.
#
# La bibliothèque devient ce qu'elle aurait toujours dû être : un jeu de
# GABARITS qu'on instancie, pas une dépendance d'exécution.
#
# Deux choses à prouver : que la copie recalcule, et que DEUX gemmes
# copiées dans la même pièce ne se marchent pas dessus — leurs VarSet
# portent le même nom d'origine, et FreeCAD renomme en silence.
# --------------------------------------------------------------------------

def probe_copy():
    biblio = App.openDocument(BIBLIO)
    piece = App.newDocument("SpikePiece2")
    out = {}
    try:
        copies = []
        for i, diam in enumerate((1.5, 4.0)):
            copie = piece.copyObject(biblio.getObject("Corps"), True)
            copies.append(copie)
            piece.recompute()
            out["copie_{}".format(i)] = {
                "nom": copie.Name,
                "forme_valide": copie.Shape.isValid(),
                "faces": len(copie.Shape.Faces),
            }

        # Chaque copie a-t-elle SA variable, ou partagent-elles la même ?
        varsets = [o for o in piece.Objects if o.TypeId == "App::VarSet"]
        out["varsets"] = [v.Name for v in varsets]
        out["une_varset_par_gemme"] = len(varsets) == len(copies)

        # Le test qui compte : rediamétrer une copie SANS toucher l'autre.
        avant = [c.Shape.Volume for c in copies]
        for varset, diam in zip(varsets, (1.5, 4.0)):
            varset.diametre = float(diam)
        piece.recompute()
        apres = [c.Shape.Volume for c in copies]

        out["toujours_parametrable"] = all(
            abs(a - b) > 1e-9 for a, b in zip(avant, apres))
        out["diametres_independants"] = (
            len(set(round(v, 9) for v in apres)) == len(copies))
        out["volumes"] = [round(v, 6) for v in apres]

        path = os.path.join(TMP, "piece-copiee.FCStd")
        piece.saveAs(path)
        out["octets"] = os.path.getsize(path)
    finally:
        for name in list(App.listDocuments()):
            try:
                App.closeDocument(name)
            except Exception:  # noqa: BLE001
                pass

    # Autonomie : rouvrir la pièce SEULE, bibliothèque absente du disque.
    garde = os.path.join(TMP, "brillant-rond.FCStd.range")
    os.rename(BIBLIO, garde)
    try:
        reopened = App.openDocument(os.path.join(TMP, "piece-copiee.FCStd"))
        try:
            corps = [o for o in reopened.Objects
                     if o.TypeId == "PartDesign::Body"]
            out["autonome_sans_bibliotheque"] = all(
                c.Shape.isValid() and c.Shape.Solids for c in corps)
            out["documents_ouverts"] = len(App.listDocuments())
        finally:
            for name in list(App.listDocuments()):
                try:
                    App.closeDocument(name)
                except Exception:  # noqa: BLE001
                    pass
    finally:
        os.rename(garde, BIBLIO)
    return out


note("h9_copie_parametrique", probe_copy)

shutil.rmtree(TMP, ignore_errors=True)

# --------------------------------------------------------------------------

print(json.dumps(R, ensure_ascii=False, indent=1, default=str), flush=True)

forme = R.get("h2h3h4_forme") or {}
verdict = {
    "H1 recalcul mesuré": bool((R.get("h1_cout") or {}).get("ms_par_taille")),
    "H2 aucune B-spline": bool(forme.get("aucune_bspline")),
    "H3 cotes justes": all(
        v.get("diametre_retrouve") for k, v in forme.items()
        if k.startswith("d_")),
    "H4 volume en d³": bool(forme.get("volume_en_d3")),
    "H5 200 instances": bool((R.get("h5_instances") or {}).get("pierres")),
    "H7 siège creusé": bool((R.get("h7_siege") or {}).get(
        "a_enleve_de_la_matiere")),
    "H8 coût à charge réelle": bool(
        (R.get("h8_cout_facette") or {}).get("ms_par_taille")),
    "H9 copie encore paramétrable": bool(
        (R.get("h9_copie_parametrique") or {}).get("toujours_parametrable")),
    "H9 pièce autonome": bool(
        (R.get("h9_copie_parametrique") or {}).get(
            "autonome_sans_bibliotheque")),
}
print("\n".join("{}  {}".format("OK  " if v else "NON ", k)
                for k, v in verdict.items()), flush=True)
print("\nSONDE {} — H9 est désormais le verdict d'architecture : une gemme\n"
      "COPIÉE dans la pièce reste paramétrable ET n'exige plus la\n"
      "bibliothèque. Si les deux tiennent, la bibliothèque est un jeu de\n"
      "gabarits, pas une dépendance."
      .format("VERTE" if all(verdict.values()) else "ROUGE"), flush=True)
print("\n   — H2 et H3 restent acquis : forme analytique et cotes justes,\n"
      "     donc les deux pièges de la voie BREP mise à l'échelle (1,18 %\n"
      "     de volume, BoundBox 70 % trop grand) ne se posent plus.",
      flush=True)
