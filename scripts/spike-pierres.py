"""Sonde : poser une pierre sur une surface courbe, et l'y garder.

Usage :  freecadcmd scripts/spike-pierres.py

Prouve ou tue la chaîne « clic → (u,v) → placement exact », avant
d'investir la moindre UI. Ne lève jamais : chaque question note sa
réponse ou son erreur, comme ``Kernel.spike_assembly``.

Les sept questions, dans l'ordre où elles peuvent tuer l'approche :

  Q1  inverse       le point cliqué se convertit-il en (u,v) sur une face
                    COURBE (cylindre, tore, B-spline) ?
  Q2  ancrage       en rejouant (u,v) après changement d'une cote
                    pilotante, la pierre reste-t-elle collée ? — c'est le
                    seul point qui distingue le BRep du maillage
  Q2b libre         le même, sur surface libre, où (u,v) n'ont plus le
                    sens évident qu'ils ont sur un cylindre
  Q3  domaine       (u,v) tombe-t-il dans le contour trimmé, ou dans un
                    trou ?
  Q4  couture       une pierre près de la couture d'une surface
                    périodique saute-t-elle ?
  Q5  tessellation  écart entre ce que le client voit pendant le drag et
                    ce que le moteur pose au relâchement — et, accessoire,
                    pourquoi la déviation demandée semble sans effet
  Q6  booléen       N sièges : N coupes, ou un compound et une seule ?
                    La COURBE (40/100/200), pas un point
  Q7  instances     App::Link à N placements — ou N objets ?
"""

import json
import math
import os
import sys
import time

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — stdout ASCII, sans importance ici
    pass

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

R = {"freecad": ".".join(str(v) for v in App.Version()[:3])}


def note(key, fn):
    """Exécute une sonde, range son résultat ou son erreur sous ``key``."""
    try:
        R[key] = fn()
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        R[key] = None
        R[key + "_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])


# --------------------------------------------------------------------------
# Les surfaces d'essai : plane, simplement courbe, doublement courbe, libre.
# --------------------------------------------------------------------------

def curved_face(shape):
    """La première face non plane — celle qui compte."""
    for face in shape.Faces:
        if face.Surface.TypeId != "Part::GeomPlane":
            return face
    return shape.Faces[0]


def outer_cylinder_face(shape):
    """La face cylindrique de plus GRAND rayon — le dessus du jonc.

    Sur un tube, ``curved_face`` rendrait la première face non plane, qui
    peut être l'alésage : normale rentrante, sièges creusés du mauvais
    côté, chronomètre qui mesure autre chose. Ici le choix est explicite.
    """
    best = None
    for face in shape.Faces:
        if face.Surface.TypeId != "Part::GeomCylinder":
            continue
        if best is None or face.Surface.Radius > best.Surface.Radius:
            best = face
    return best if best is not None else curved_face(shape)


SURFACES = {}


def build_surfaces():
    SURFACES["cylindre"] = curved_face(Part.makeCylinder(10.0, 6.0))
    SURFACES["tore"] = curved_face(Part.makeTorus(10.0, 2.0))
    SURFACES["sphere"] = curved_face(Part.makeSphere(10.0))
    # Surface libre : une B-spline bombée, le cas du chaton ou du signet.
    poles = [[App.Vector(i * 5.0, j * 5.0,
                         2.0 * math.sin(i * 0.9) * math.cos(j * 0.9))
              for j in range(4)] for i in range(4)]
    bs = Part.BSplineSurface()
    bs.interpolate(poles)
    SURFACES["bspline"] = bs.toShape().Faces[0]
    return sorted(SURFACES)


note("surfaces", build_surfaces)


# --------------------------------------------------------------------------
# Q0 — quelles méthodes existent vraiment sur cette version ?
# --------------------------------------------------------------------------

def probe_api():
    face = SURFACES["cylindre"]
    u0, u1, v0, v1 = face.ParameterRange
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    out = {}
    for name, call in (
            ("Face.valueAt", lambda: face.valueAt(u, v)),
            ("Face.normalAt", lambda: face.normalAt(u, v)),
            ("Face.tangentAt", lambda: face.tangentAt(u, v)),
            ("Face.isPartOfDomain", lambda: face.isPartOfDomain(u, v)),
            ("Face.curvatureAt", lambda: face.curvatureAt(u, v)),
            ("Surface.value", lambda: face.Surface.value(u, v)),
            ("Surface.parameter",
             lambda: face.Surface.parameter(face.Surface.value(u, v))),
    ):
        try:
            call()
            out[name] = True
        except Exception as exc:  # noqa: BLE001
            out[name] = "{}: {}".format(type(exc).__name__, str(exc)[:80])
    return out


note("q0_api", probe_api)


# --------------------------------------------------------------------------
# Q1 — l'inverse : un point du monde → (u,v). Trois voies, on garde
#      celle qui tient sur les quatre surfaces.
# --------------------------------------------------------------------------

def uv_by_surface_parameter(face, pt):
    return tuple(face.Surface.parameter(pt))


def uv_by_project(face, pt):
    return tuple(face.Surface.projectPoint(pt, "LowerDistanceParameters"))


def uv_by_dist(face, pt):
    _, _, info = face.distToShape(Part.Vertex(pt))
    return tuple(info[0][2])


ROUTES = (("Surface.parameter", uv_by_surface_parameter),
          ("Surface.projectPoint", uv_by_project),
          ("distToShape", uv_by_dist))


def sample_point(face):
    """Le point qu'un raycast Three.js rendrait : centre d'un triangle
    de la tessellation — donc À CÔTÉ de la surface exacte, pas dessus."""
    vertices, triangles = face.tessellate(0.1)
    a, b, c = triangles[len(triangles) // 2]
    return (vertices[a] + vertices[b] + vertices[c]) * (1.0 / 3.0)


def probe_inverse():
    out = {}
    for name in sorted(SURFACES):
        face = SURFACES[name]
        pt = sample_point(face)
        per_route = {}
        for route, fn in ROUTES:
            try:
                u, v = fn(face, pt)
                exact = face.valueAt(u, v)
                per_route[route] = {
                    "uv": [round(u, 6), round(v, 6)],
                    # Distance point cliqué → point exact reprojeté :
                    # c'est l'aimantation elle-même.
                    "snap_mm": round(pt.distanceToPoint(exact), 6),
                }
            except Exception as exc:  # noqa: BLE001
                per_route[route] = "{}: {}".format(
                    type(exc).__name__, str(exc)[:80])
        out[name] = per_route
    return out


note("q1_inverse", probe_inverse)


# --------------------------------------------------------------------------
# Q2 — L'ANCRAGE. Le seul résultat qui compte : (u,v) rejoué sur une
#      surface reconstruite avec une cote différente.
#
#      Un jonc de bague : cylindre de rayon r. On pose la pierre à mi-
#      hauteur, on passe de r=10 à r=12 (taille au-dessus), on rejoue
#      (u,v). Attendu : même angle, même hauteur, toujours plaquée, la
#      normale toujours radiale. C'est ce qu'un Placement figé perd.
# --------------------------------------------------------------------------

def placement_at(face, u, v, spin=0.0, lift=0.0):
    """Placement d'une pierre : +Z de la pierre aligné sur la normale."""
    origin = face.valueAt(u, v)
    normal = face.normalAt(u, v).normalize()
    rot = App.Rotation(App.Vector(0, 0, 1), normal)
    if spin:
        rot = rot.multiply(App.Rotation(App.Vector(0, 0, 1), spin))
    return App.Placement(origin + normal.multiply(lift), rot)


def probe_anchor():
    small = curved_face(Part.makeCylinder(10.0, 6.0))
    u0, u1, v0, v1 = small.ParameterRange
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    before = placement_at(small, u, v)

    big = curved_face(Part.makeCylinder(12.0, 6.0))
    after = placement_at(big, u, v)

    def radial(p):
        return math.hypot(p.Base.x, p.Base.y)

    def axis_of(p):
        return p.Rotation.multVec(App.Vector(0, 0, 1))

    return {
        # La pierre suit le rayon : 10 → 12.
        "rayon_avant": round(radial(before), 6),
        "rayon_apres": round(radial(after), 6),
        "colle_au_jonc": abs(radial(after) - 12.0) < 1e-6,
        # Même hauteur sur le jonc.
        "z_avant": round(before.Base.z, 6),
        "z_apres": round(after.Base.z, 6),
        "meme_hauteur": abs(after.Base.z - before.Base.z) < 1e-6,
        # Même angle autour de l'axe.
        "angle_avant_deg": round(math.degrees(
            math.atan2(before.Base.y, before.Base.x)), 6),
        "angle_apres_deg": round(math.degrees(
            math.atan2(after.Base.y, after.Base.x)), 6),
        # La normale reste radiale : la pierre n'a pas basculé.
        "normale_radiale": abs(
            axis_of(after).dot(App.Vector(after.Base.x, after.Base.y, 0.0)
                               .normalize()) - 1.0) < 1e-6,
        # Le témoin négatif : un Placement figé, lui, décolle de 2 mm.
        "placement_fige_ecart_mm": round(
            abs(radial(before) - 12.0), 6),
    }


note("q2_ancrage", probe_anchor)


def bumped_bspline(amplitude):
    """Même surface libre, une seule cote changée — le chaton qu'on
    bombe davantage. Les nœuds (u,v) de l'interpolation ne bougent pas."""
    poles = [[App.Vector(i * 5.0, j * 5.0,
                         amplitude * math.sin(i * 0.9) * math.cos(j * 0.9))
              for j in range(4)] for i in range(4)]
    bs = Part.BSplineSurface()
    bs.interpolate(poles)
    return bs.toShape().Faces[0]


def probe_anchor_freeform():
    """Q2 bis — le cas qui peut mal tourner.

    Sur un cylindre, (u,v) valent angle et hauteur : leur sens survit
    trivialement au changement de rayon. Sur une surface libre, (u,v)
    n'ont de sens que relativement à la paramétrisation — si la
    reconstruction la change, la pierre glisse. On mesure le glissement.
    """
    before, after = bumped_bspline(2.0), bumped_bspline(3.5)
    u0, u1, v0, v1 = before.ParameterRange
    u, v = u0 + (u1 - u0) * 0.37, v0 + (v1 - v0) * 0.62
    pa, pb = placement_at(before, u, v), placement_at(after, u, v)
    return {
        "plage_uv_identique": [round(x, 6) for x in before.ParameterRange]
                              == [round(x, 6) for x in after.ParameterRange],
        # Le glissement EN PLAN : si (u,v) garde son sens, x et y ne
        # bougent pas et seul z suit le bombé.
        "glissement_xy_mm": round(
            math.hypot(pb.Base.x - pa.Base.x, pb.Base.y - pa.Base.y), 6),
        "dz_mm": round(pb.Base.z - pa.Base.z, 6),
        # La pierre s'est bien réorientée sur la nouvelle normale.
        "bascule_deg": round(math.degrees(
            pa.Rotation.multVec(App.Vector(0, 0, 1)).getAngle(
                pb.Rotation.multVec(App.Vector(0, 0, 1)))), 3),
        "sur_la_surface": abs(after.distToShape(
            Part.Vertex(pb.Base))[0]) < 1e-6,
    }


note("q2b_ancrage_libre", probe_anchor_freeform)


# --------------------------------------------------------------------------
# Q3 — le domaine trimmé : une pierre dans un trou doit être refusée.
# --------------------------------------------------------------------------

def probe_domain():
    plate = Part.makeBox(20, 20, 2)
    hole = Part.makeCylinder(4, 10, App.Vector(10, 10, -1))
    top = max(plate.cut(hole).Faces, key=lambda f: f.CenterOfMass.z)
    out = {"face_trouee": len(top.Wires)}
    for label, (x, y) in (("plein", (3.0, 3.0)), ("dans_le_trou", (10.0, 10.0))):
        try:
            u, v = top.Surface.parameter(App.Vector(x, y, 2.0))
            out[label] = bool(top.isPartOfDomain(u, v))
        except Exception as exc:  # noqa: BLE001
            out[label] = "{}: {}".format(type(exc).__name__, str(exc)[:80])
    out["verdict"] = (out.get("plein") is True
                      and out.get("dans_le_trou") is False)
    return out


note("q3_domaine", probe_domain)


# --------------------------------------------------------------------------
# Q4 — la couture. Sur un cylindre u boucle à 2π : une pierre posée à
#      u≈0⁻ et une à u≈0⁺ doivent rester voisines dans l'espace.
# --------------------------------------------------------------------------

def probe_seam():
    face = SURFACES["cylindre"]
    u0, u1, v0, v1 = face.ParameterRange
    v = (v0 + v1) / 2.0
    eps = 1e-3
    a = face.valueAt(u0 + eps, v)
    b = face.valueAt(u1 - eps, v)
    # Aller-retour par le point : le paramètre revient-il du bon côté ?
    ua, _ = face.Surface.parameter(a)
    ub, _ = face.Surface.parameter(b)
    return {
        "plage_u": [round(u0, 6), round(u1, 6)],
        "periodique": bool(face.Surface.isUPeriodic()),
        # Deux pierres de part et d'autre de la couture : voisines ?
        "distance_3d_mm": round(a.distanceToPoint(b), 6),
        "u_retour_a": round(ua, 6),
        "u_retour_b": round(ub, 6),
        # Le piège : ub peut revenir ≈0 au lieu de ≈2π. Sans normalisation,
        # un drag qui franchit la couture téléporte la pierre.
        "u_replie": abs(ub - (u1 - eps)) > 1e-3,
    }


note("q4_couture", probe_seam)


# --------------------------------------------------------------------------
# Q5 — le drag à 60 fps est client-side : il vise la TESSELLATION.
#      De combien la pierre s'enfonce-t-elle avant le recalage exact ?
# --------------------------------------------------------------------------

def sink_of(face, deviation):
    """(nb de triangles, enfoncement max) — l'écart entre ce que le client
    voit pendant le drag et la surface exacte visée au relâchement."""
    vertices, triangles = face.tessellate(deviation)
    worst = 0.0
    for a, b, c in triangles[::max(1, len(triangles) // 200)]:
        centre = (vertices[a] + vertices[b] + vertices[c]) * (1.0 / 3.0)
        u, v = face.Surface.parameter(centre)
        worst = max(worst, centre.distanceToPoint(face.valueAt(u, v)))
    return len(triangles), worst


def probe_tessellation():
    """Deux questions distinctes, dont une seule est critique.

    (a) La déviation demandée change-t-elle quelque chose ? Le premier
        passage a rendu trois fois le même maillage. J'ai supposé un cache
        de triangulation sur la forme : **hypothèse fausse** — avec une
        face neuve à chaque tour, les chiffres n'ont pas bougé d'un iota.
        Hypothèse restante : sur une face **analytique** (tore), le
        mailleur OCCT subdivise par l'angle et la flèche linéaire ne mord
        pas. On la départage en comparant tore et B-spline sur une plage
        large — si la libre répond et l'analytique non, c'est réglé.

    (b) Pour le maillage que l'app produit RÉELLEMENT — déviation 0,1,
        défaut de ``Kernel.tessellate`` — de combien la pierre
        s'enfonce-t-elle pendant le drag ? **Le seul chiffre dont la
        conception dépende**, et il ne dépend pas de la réponse à (a).
    """
    out = {}
    for name, make in (
            ("tore_analytique", lambda: curved_face(Part.makeTorus(10.0, 2.0))),
            ("bspline_libre", lambda: bumped_bspline(2.0))):
        rows = {}
        for deviation in (5.0, 1.0, 0.1, 0.01):
            n, worst = sink_of(make(), deviation)  # face neuve : pas de cache
            rows["dev_{}".format(deviation)] = {
                "triangles": n, "enfoncement_max_mm": round(worst, 6)}
        rows["deviation_agit"] = len(
            {r["triangles"] for r in rows.values()
             if isinstance(r, dict)}) > 1
        out[name] = rows

    n, worst = sink_of(curved_face(Part.makeTorus(10.0, 2.0)), 0.1)
    out["ce_que_lapp_produit"] = {
        "deviation": 0.1,
        "triangles": n,
        "enfoncement_max_mm": round(worst, 6),
        # Sous le centième de millimètre, le drag client-side est acquis.
        "invisible": worst < 0.01,
    }
    return out


note("q5_tessellation", probe_tessellation)


# --------------------------------------------------------------------------
# Q6 — N sièges à creuser. Une coupe par pierre, ou un compound et une
#      seule coupe ? La réponse décide si 200 pierres sont tenables.
# --------------------------------------------------------------------------

PAS_MM = 1.5  # entraxe réaliste entre deux pierres d'un rang


def boolean_round(count):
    """N sièges creusés dans un jonc, à entraxe constant.

    Le rayon du jonc suit le nombre de pierres : à rayon figé, 200 sièges
    se recouperaient et trancheraient le jonc — on mesurerait la faillite
    du jeu d'essai, pas le coût du booléen. À entraxe constant, chaque
    coupe garde la même difficulté locale et seul le NOMBRE varie : c'est
    la question posée.
    """
    r_out = max(10.0, count * PAS_MM / (2.0 * math.pi))
    band = (Part.makeCylinder(r_out, 6.0)
            .cut(Part.makeCylinder(r_out - 1.5, 6.0)))
    face = outer_cylinder_face(band)
    u0, u1, v0, v1 = face.ParameterRange
    seats = []
    for i in range(count):
        u = u0 + (u1 - u0) * (i + 0.5) / count
        cone = Part.makeCone(PAS_MM * 0.35, 0.1, 2.0)
        cone.Placement = placement_at(face, u, (v0 + v1) / 2.0, lift=-1.0)
        seats.append(cone)

    t0 = time.time()
    one_by_one = band.copy()
    for seat in seats:
        one_by_one = one_by_one.cut(seat)
    t_seq = time.time() - t0

    t0 = time.time()
    at_once = band.cut(Part.makeCompound(seats))
    t_bulk = time.time() - t0

    return {
        "pierres": count,
        "coupe_par_pierre_s": round(t_seq, 3),
        "compound_une_coupe_s": round(t_bulk, 3),
        "gain": round(t_seq / t_bulk, 1) if t_bulk > 1e-6 else None,
        # Le chiffre qui se projette : coût marginal d'une pierre.
        "ms_par_pierre": round(t_bulk * 1000.0 / count, 2),
        "meme_volume": abs(one_by_one.Volume - at_once.Volume) < 1e-6,
        "solide_valide": at_once.isValid() and len(at_once.Solids) == 1,
    }


def probe_boolean():
    """La courbe, pas un point : 40 sièges tenables ne disent rien de 200.
    Si ms_par_pierre reste plat, le coût est linéaire et 200 pierres
    passent ; s'il grimpe, il faudra découper le semis en paquets."""
    return {"n{}".format(n): boolean_round(n) for n in (40, 100, 200)}


note("q6_booleen", probe_boolean)


# --------------------------------------------------------------------------
# Q7 — l'affichage de N pierres : App::Link à N placements ?
# --------------------------------------------------------------------------

def probe_instances(count=200):
    doc = App.newDocument("SpikePierres")
    try:
        gem = doc.addObject("Part::Feature", "Pierre")
        gem.Shape = Part.makeCone(1.0, 0.1, 1.5)
        link = doc.addObject("App::Link", "Semis")
        link.LinkedObject = gem
        out = {"element_count": hasattr(link, "ElementCount"),
               "placement_list": hasattr(link, "PlacementList")}
        if out["element_count"]:
            link.ElementCount = count
            face = SURFACES["cylindre"]
            u0, u1, v0, v1 = face.ParameterRange
            t0 = time.time()
            link.PlacementList = [
                placement_at(face, u0 + (u1 - u0) * i / count,
                             (v0 + v1) / 2.0)
                for i in range(count)]
            doc.recompute()
            out["pierres"] = count
            out["pose_s"] = round(time.time() - t0, 3)
            out["placements_retenus"] = len(link.PlacementList)
        return out
    finally:
        App.closeDocument(doc.Name)


note("q7_instances", probe_instances)


# --------------------------------------------------------------------------

print(json.dumps(R, ensure_ascii=False, indent=1, default=str), flush=True)

verdict = {
    "Q1 inverse": isinstance(R.get("q1_inverse"), dict),
    "Q2 ancrage": bool((R.get("q2_ancrage") or {}).get("colle_au_jonc")),
    "Q2b surface libre": bool(
        (R.get("q2b_ancrage_libre") or {}).get("sur_la_surface")),
    "Q3 domaine": bool((R.get("q3_domaine") or {}).get("verdict")),
    "Q6 booléen": all(
        isinstance(v, dict) and v.get("solide_valide")
        for v in (R.get("q6_booleen") or {"_": None}).values()),
    "Q7 instances": bool((R.get("q7_instances") or {}).get("element_count")),
}
print("\n".join("{}  {}".format("OK  " if v else "NON ", k)
                for k, v in verdict.items()), flush=True)
print("\nSONDE {} — Q2 est le verdict : sans ancrage (u,v), rien ne "
      "distingue\ncette approche d'un placement figé à la Blender."
      .format("VERTE" if all(verdict.values()) else "ROUGE"), flush=True)
