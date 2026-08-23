"""Sonde — l'ancrage d'un semis survit-il à une renumérotation de faces ?

Usage :  freecadcmd scripts/spike-toponaming-semis.py

Un semis retient sa face d'appui sous la forme ``FreeSolidGemFace =
"Face3"`` : un **indice**, c'est-à-dire précisément l'identifiant que
OCCT ne promet pas de conserver. Ajoutez un congé, un enlèvement, et
200 pierres peuvent pointer ailleurs — ou nulle part.

``docs/amont-freecad.md`` §4quater a déjà tranché la méthode, sur mesure
réelle : un nom mappé **n'est pas une clé globale**, il est porté par la
forme d'une fonction. La chaîne se traverse **à l'envers** — depuis un
élément de la pointe courante, ``getElementHistory`` remonte à la
fonction d'origine. D'où le couple à stocker :

    (fonction propriétaire, nom mappé sur cette fonction)

et, au rejeu, une recherche à l'envers sur les faces de la pointe.

**Mais §4quater a mesuré ça sur la forme d'une FONCTION** (un `Pad`, un
`Pocket`). Un semis, lui, s'ancre sur ``body.Shape`` — la forme du
**corps** — parce que c'est elle que le client tessellise et raycaste
(``Kernel._anchor_face``). Et la seule sonde qui ait touché au corps,
``resolution_corps``, était rouge : un nom capturé sur le `Pad` ne
résout pas sur le `Body`. Elle ne dit rien de la carte **propre** du
corps.

C'est le trou que cette sonde comble. Et la leçon de §4quater est
exactement celle à ne pas re-rater : *lire la source dit ce qui est
exposé ; seule l'exécution dit ce qui marche.*

Les questions, dans l'ordre où elles peuvent tuer l'approche :

  Q0  bug          l'indice de la face d'appui bouge-t-il vraiment quand
                   la topologie change ? Sans ça, il n'y a rien à réparer
  Q1  carte_corps  ``body.Shape`` a-t-il une carte d'éléments peuplée ?
  Q2  corps_pointe si non : les faces du corps et celles du Tip sont-elles
                   les mêmes, dans le même ordre ? (c'est le repli)
  Q3  couple       depuis une face du corps, obtient-on le couple
                   (fonction, nom) par ``getElementHistory`` ?
  Q4  cote         après un simple changement de cote, la recherche à
                   l'envers retrouve-t-elle la face — et une seule ?
  Q5  renumerote   après un enlèvement qui renumérote — le cas qui compte
  Q6  scission     face d'appui coupée en deux : combien de candidats ?
                   (l'état « ambigu » du verdict à trois états)
  Q7  cout         combien de secondes pour résoudre une référence ?

Ne lève jamais : chaque question note sa réponse ou son erreur.
"""

import json
import os
import sys
import time

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — stdout ASCII, sans importance ici
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

#: Même convention que ``spike-element-map.py`` : la CI archive le JSON.
_REPORT_PATH = os.environ.get(
    "FREESOLID_SPIKE_REPORT",
    os.path.join(_REPO, "spike-toponaming-semis.json"))

R = {}


def note(key, fn):
    """Exécute une sonde, range son résultat ou son erreur sous ``key``."""
    try:
        R[key] = fn()
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        R[key] = None
        R[key + "_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:200])


def attr(obj, name):
    try:
        return getattr(obj, name)
    except Exception:  # noqa: BLE001 — une sonde ne casse pas sur un attribut
        return None


def first(value):
    """``getElementMappedName`` rend parfois un tuple. On veut le nom."""
    if isinstance(value, (tuple, list)):
        return value[0] if value else None
    return value


def mapped_name(shape, indexed):
    fn = attr(shape, "getElementMappedName")
    if not callable(fn):
        return None
    try:
        return first(fn(indexed))
    except Exception:  # noqa: BLE001
        return None


def history(obj_or_shape, name):
    """``getElementHistory`` sur l'objet OU sur la forme. Rend la trace."""
    fn = attr(obj_or_shape, "getElementHistory")
    if not callable(fn) or not name:
        return None
    try:
        return fn(name)
    except Exception as exc:  # noqa: BLE001
        return "{}: {}".format(type(exc).__name__, str(exc)[:120])


def face_signature(face):
    """De quoi reconnaître une face À L'ŒIL dans le rapport.

    Ce n'est **pas** l'identifiant proposé — la ressemblance géométrique
    est justement l'approche que §4quater écarte. C'est un repère de
    lecture, pour que le rapport dise « la même face » de façon lisible.
    """
    surface = attr(face, "Surface")
    out = {"type": str(attr(surface, "TypeId") or "?")}
    for name in ("Radius", "MajorRadius"):
        value = attr(surface, name)
        if value is not None:
            out["rayon"] = round(float(value), 4)
            break
    area = attr(face, "Area")
    if area is not None:
        out["aire"] = round(float(area), 3)
    return out


# --------------------------------------------------------------------------
# La pièce d'essai : un jonc. Rayon 10, hauteur 6 — une bague.
# --------------------------------------------------------------------------

KERNEL = {}


def make_ring(nom):
    """Un jonc neuf, dans son propre document.

    Chaque sonde qui abîme la pièce prend la sienne : Q0 pose une pierre
    et un congé, et une sonde qui hérite d'un état sali ne mesure plus
    ce qu'elle annonce.
    """
    from engine.kernel import Kernel

    kernel = Kernel()
    kernel.new_part(nom)
    state = kernel.sketch_start()
    sketch = state["sketch"]
    kernel.sketch_add_circle(sketch, 0, 0, 10)
    kernel.sketch_constrain(sketch, "coincident", 0, point1=3,
                            geo2=-1, point2=1)
    kernel.sketch_finish(sketch)
    arbre = kernel.add_pad(6, sketch=sketch)
    body = kernel._require_body()
    return {
        "k": kernel,
        "sketch": sketch,
        "pad": next(f["name"] for f in arbre["features"]
                    if f["type"] == "PartDesign::Pad"),
        "body": body.Name,
        "side": kernel._side_face_id(),
    }


def build_ring():
    from engine.platform import allow_from_environ, version_status

    handles = make_ring("Sonde toponaming semis")
    kernel = handles["k"]
    plateforme = version_status(
        kernel.ping()["freecad"], allow=allow_from_environ())
    R["freecad"] = plateforme["running"]
    R["reference"] = plateforme["reference"]
    KERNEL.update(handles)
    body = kernel._doc.getObject(handles["body"])
    faces = body.Shape.Faces
    return {
        "faces": len(faces),
        "face_appui": handles["side"],
        "signature": face_signature(faces[handles["side"]]),
        "tip": str(attr(attr(body, "Tip"), "Name") or ""),
    }


note("piece", build_ring)


def _kernel():
    kernel = KERNEL.get("k")
    if kernel is None:
        raise RuntimeError("la pièce d'essai n'a pas été construite")
    return kernel


def _body():
    return _kernel()._doc.getObject(KERNEL["body"])


# --------------------------------------------------------------------------
# Q0 — le défaut existe-t-il ? Sans ça, rien à réparer.
# --------------------------------------------------------------------------

def probe_bug():
    """L'indice de la face d'appui bouge-t-il quand la topologie change ?

    On pose une pierre, on ajoute un congé sur une arête, et on regarde
    si ``FreeSolidGemFace`` désigne encore la même face. C'est LA
    question : si l'indice tient, tout ce qui suit est du luxe.
    """
    handles = make_ring("Sonde toponaming Q0")
    kernel = handles["k"]
    side = handles["side"]

    def body_now():
        return kernel._doc.getObject(handles["body"])

    body = body_now()
    before_face = body.Shape.Faces[side]
    before = {
        "faces": len(body.Shape.Faces),
        "indice_appui": side,
        "signature": face_signature(before_face),
    }
    point = before_face.valueAt(*[
        (a + b) / 2.0 for a, b in zip(before_face.ParameterRange[::2],
                                      before_face.ParameterRange[1::2])])
    kernel.place_gem(face=side, x=point.x, y=point.y, z=point.z,
                     diametre=1.5)
    semis = (kernel.list_gems().get("gems") or [{}])[0]
    before["semis_face"] = semis.get("face")
    before["semis_erreur"] = semis.get("error")

    # Un congé sur l'arête du dessus : la topologie change vraiment.
    # Si le congé lui-même échoue à cause du semis, c'est un résultat —
    # et il faut le distinguer d'une ancre qui tient.
    try:
        kernel.add_fillet(0.4, face=kernel._top_face_id())
    except Exception as exc:  # noqa: BLE001 — une sonde rapporte
        return {"avant": before,
                "conge_refuse": "{}: {}".format(
                    type(exc).__name__, str(exc)[:200]),
                "indice_a_bouge": None, "ancre_encore_juste": None}
    faces = body_now().Shape.Faces
    # Où est passée la face cylindrique de rayon 10 ?
    cible = None
    for index, face in enumerate(faces):
        sig = face_signature(face)
        if (sig.get("type") == before["signature"].get("type")
                and sig.get("rayon") == before["signature"].get("rayon")):
            cible = index
            break
    semis_after = (kernel.list_gems().get("gems") or [{}])[0]
    return {
        "avant": before,
        "apres": {
            "faces": len(faces),
            "indice_reel_appui": cible,
            "signature_a_cet_indice": (
                None if cible is None else face_signature(faces[cible])),
            "signature_a_l_ancien_indice": (
                face_signature(faces[side]) if side < len(faces) else None),
            "semis_face": semis_after.get("face"),
            "semis_erreur": semis_after.get("error"),
            "semis_message": semis_after.get("error_message"),
            "pierres": semis_after.get("count"),
        },
        # Le verdict : l'ancre pointe-t-elle encore la bonne face ?
        "indice_a_bouge": cible is not None and cible != side,
        "ancre_encore_juste": cible == side,
    }


note("q0_bug", probe_bug)


# --------------------------------------------------------------------------
# Q1 — la carte d'éléments du CORPS.
# --------------------------------------------------------------------------

def probe_carte_corps():
    """``resolution_corps`` de §4quater ne testait qu'un nom étranger.

    Ici la question est autre : le corps a-t-il une carte À LUI ?
    """
    body = _body()
    shape = attr(body, "Shape")
    tip = attr(body, "Tip")
    tip_shape = attr(tip, "Shape")
    out = {}
    for label, target in (("corps", shape), ("pointe", tip_shape)):
        if target is None:
            out[label] = "forme absente"
            continue
        entry = {
            "ElementMapSize": attr(target, "ElementMapSize"),
            "Tag": attr(target, "Tag"),
            "ElementMapVersion": attr(target, "ElementMapVersion"),
            "faces": len(attr(target, "Faces") or ()),
        }
        entry["peuplee"] = bool(entry["ElementMapSize"])
        entry["Face1_mappe"] = mapped_name(target, "Face1")
        out[label] = entry
    out["tip_nom"] = str(attr(tip, "Name") or "")
    return out


note("q1_carte_corps", probe_carte_corps)


# --------------------------------------------------------------------------
# Q2 — le repli : corps et pointe portent-ils les mêmes faces ?
# --------------------------------------------------------------------------

def probe_corps_pointe():
    """Si la carte du corps est vide, on résout via la pointe.

    Encore faut-il que ``body.Shape.Faces[i]`` et
    ``body.Tip.Shape.Faces[i]`` soient la même face. ``isSame`` le dit ;
    l'ordre est la seconde question.
    """
    body = _body()
    faces_corps = list(attr(attr(body, "Shape"), "Faces") or ())
    tip = attr(body, "Tip")
    faces_tip = list(attr(attr(tip, "Shape"), "Faces") or ())
    out = {"faces_corps": len(faces_corps), "faces_pointe": len(faces_tip)}
    if not faces_corps or not faces_tip:
        return out
    meme_indice = 0
    trouve_ailleurs = 0
    absent = 0
    for index, face in enumerate(faces_corps):
        same_here = False
        if index < len(faces_tip):
            try:
                same_here = bool(face.isSame(faces_tip[index]))
            except Exception:  # noqa: BLE001
                same_here = False
        if same_here:
            meme_indice += 1
            continue
        found = False
        for other in faces_tip:
            try:
                if face.isSame(other):
                    found = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if found:
            trouve_ailleurs += 1
        else:
            absent += 1
    out["meme_indice"] = meme_indice
    out["trouve_a_un_autre_indice"] = trouve_ailleurs
    out["absent_de_la_pointe"] = absent
    out["ordre_identique"] = (
        meme_indice == len(faces_corps) == len(faces_tip))
    return out


note("q2_corps_pointe", probe_corps_pointe)


# --------------------------------------------------------------------------
# Le mécanisme proposé — le code qui, s'il tient, part dans engine/.
# --------------------------------------------------------------------------

def _source_name(value):
    """Le premier membre d'une entrée de trace est un objet ou un Tag."""
    name = getattr(value, "Name", None)
    return str(name) if name else str(value)


def trace_pairs(trace):
    """Normalise ``getElementHistory`` en liste de ``(source, nom)``.

    Deux formes coexistent, et §4ter les liste toutes les deux sans dire
    qu'elles diffèrent : ``Part::Feature.getElementHistory`` rend une
    **liste** de couples, ``TopoShape.getElementHistory`` un **tuple**
    ``(tag source, nom source, [intermédiaires])``. Confondre les deux,
    c'est lire ``trace[1]`` comme un nom là où c'est déjà un couple.
    """
    if not trace or isinstance(trace, str):
        return []
    if isinstance(trace, (tuple, list)) and trace:
        premier = trace[0]
        if isinstance(premier, (tuple, list)):
            out = []
            for entry in trace:
                if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                    out.append((_source_name(entry[0]), str(entry[1])))
            return out
        # Forme plate : (tag, nom, [intermédiaires])
        if len(trace) >= 2:
            return [(_source_name(premier), str(trace[1]))]
    return []


def face_lineage(body, index):
    """La généalogie d'une face du corps : liste de ``(fonction, nom)``.

    Du plus récent au plus ancien. Le nom mappé se lit sur la forme du
    corps si sa carte est peuplée, sinon sur celle de la pointe — repli
    qui ne vaut que si Q2 dit que les deux portent les mêmes faces dans
    le même ordre.
    """
    shape = attr(body, "Shape")
    faces = list(attr(shape, "Faces") or ())
    if index < 0 or index >= len(faces):
        return None
    indexed = "Face{}".format(index + 1)
    porteur, name, via = body, mapped_name(shape, indexed), "corps"
    if not name:
        tip = attr(body, "Tip")
        porteur, name, via = tip, mapped_name(attr(tip, "Shape"), indexed), "pointe"
        if not name:
            return None
    paires = trace_pairs(history(porteur, name))
    tete = (str(attr(porteur, "Name") or ""), str(name))
    if tete not in paires:
        paires = [tete] + paires
    return {"via": via, "paires": paires}


def rungs(lineage):
    """Tous les barreaux de la généalogie, du plus récent au plus ancien.

    Le premier passage de cette sonde n'en testait que les **deux
    bouts** — le corps et l'esquisse — et manquait celui du milieu. Or
    sur un jonc la généalogie fait trois barreaux, `[Body, Pad, Sketch]`,
    et c'est le **Pad** que §4quater appelle « fonction propriétaire » :
    ni le conteneur, ni l'ancêtre ultime, mais la fonction qui a
    introduit la face. Tester les extrémités et sauter celui-là, c'est
    mesurer tout sauf la conception qu'on évalue.
    """
    return list(lineage["paires"]) if lineage and lineage.get("paires") else []


def couple_of(lineage, quel):
    """``quel`` : ``producteur``, ``origine``, ou un rang entier."""
    paires = rungs(lineage)
    if not paires:
        return None
    if isinstance(quel, int):
        return paires[quel] if -len(paires) <= quel < len(paires) else None
    return paires[0] if quel == "producteur" else paires[-1]


def resolve_couple(body, couple):
    """Recherche à l'envers : quels indices de face portent ce couple ?

    On cherche le couple **n'importe où** dans la généalogie de chaque
    face de la pointe courante — c'est ce qui absorbe l'insertion d'une
    fonction en aval. O(faces) par référence, et une référence par
    SEMIS, pas par pierre : 200 pierres sur une face, une résolution.
    """
    if not couple:
        return []
    hits = []
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    for index in range(len(faces)):
        lineage = face_lineage(body, index)
        if lineage and tuple(couple) in [tuple(p) for p in lineage["paires"]]:
            hits.append(index)
    return hits


def couple_for_face(body, index, quel="origine"):
    return couple_of(face_lineage(body, index), quel)


def verdict_for(hits):
    """Le verdict à trois états. Jamais de re-liaison silencieuse."""
    if len(hits) == 1:
        return "résolu"
    if len(hits) > 1:
        return "ambigu"
    return "perdu"


# --------------------------------------------------------------------------
# Q3 — le couple se fabrique-t-il depuis une face du corps ?
# --------------------------------------------------------------------------

def probe_couple():
    """Deux bouts de généalogie, et un critère : l'unicité.

    Un couple qui ne distingue pas deux faces ne sert à rien — un semis
    se rebrancherait sur la voisine. C'est ce qui départage le
    producteur de l'origine, avant même la question de la survie.
    """
    body = _body()
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    out = {"faces": len(faces), "genealogies": []}
    lineages = []
    for index in range(len(faces)):
        lineage = face_lineage(body, index)
        lineages.append(lineage)
        out["genealogies"].append({
            "indice": index,
            "signature": face_signature(faces[index]),
            "via": None if lineage is None else lineage["via"],
            "paires": None if lineage is None else lineage["paires"],
        })
    out["fabricables"] = sum(1 for item in lineages if item)
    # Tous les barreaux, pas seulement les deux bouts.
    profond = max((len(rungs(item)) for item in lineages), default=0)
    out["barreaux"] = profond
    out["par_rang"] = {}
    for rang in range(profond):
        couples = [couple_of(item, rang) for item in lineages]
        presents = [c for c in couples if c]
        if not presents:
            continue
        out["par_rang"]["rang{}".format(rang)] = {
            "fonctions": sorted({c[0] for c in presents}),
            "fabricables": len(presents),
            "distincts": len(set(presents)),
            # Le seul critère qui compte ici.
            "unique_par_face": len(presents) == len(set(presents)),
            "exemples": [list(c) for c in presents[:3]],
        }
    return out


note("q3_couple", probe_couple)


# --------------------------------------------------------------------------
# Q4 — un simple changement de cote.
# --------------------------------------------------------------------------

def probe_cote():
    """Sonde faible, et il faut le dire : un reparamétrage ne renumérote
    rien. Elle ne prouve que l'absence de régression, pas la survie.
    """
    kernel = _kernel()
    body = _body()
    side = KERNEL["side"]
    couples = list(enumerate(rungs(face_lineage(body, side))))
    out = {"couples_avant": {"rang{}".format(r): list(c) for r, c in couples}}
    # La hauteur du jonc passe de 6 à 9 mm. Aucun indice ne bouge : c'est
    # tout l'intérêt d'une sonde faible — elle ne prouve rien sur la
    # survie, seulement qu'on n'a pas cassé le cas facile.
    kernel.set_param(KERNEL["pad"], "Length", 9.0)
    kernel._recompute()
    body = _body()
    out["faces"] = len(attr(attr(body, "Shape"), "Faces") or ())
    for rang, couple in couples:
        hits = resolve_couple(body, couple)
        out["rang{}".format(rang)] = {
            "couple": list(couple), "hits": hits,
            "verdict": verdict_for(hits),
            "retrouve_le_meme_indice": hits == [side],
        }
    out["rang_gagnant"] = next(
        ("rang{}".format(r) for r, _ in couples
         if out["rang{}".format(r)]["retrouve_le_meme_indice"]), None)
    return out


note("q4_cote", probe_cote)


# --------------------------------------------------------------------------
# Q5 — la renumérotation. Le cas qui compte.
# --------------------------------------------------------------------------

def probe_renumerote():
    """Un enlèvement traversant : le nombre de faces change, les indices
    aussi. C'est exactement la situation où l'ancre actuelle casse.
    """
    kernel = _kernel()
    body = _body()
    side = KERNEL["side"]
    avant = {
        "faces": len(attr(attr(body, "Shape"), "Faces") or ()),
        "indice": side,
        "signature": face_signature(body.Shape.Faces[side]),
        "genealogie": (face_lineage(body, side) or {}).get("paires"),
    }
    # Un couple par barreau — le Pad compris, qu'on avait sauté.
    couples = {rang: couple for rang, couple in enumerate(
        rungs(face_lineage(body, side)))}
    avant["couples"] = {"rang{}".format(r): list(c)
                        for r, c in couples.items()}
    haut = kernel._top_face_id()
    kernel.add_rect_sketch(6, 3, face=haut)
    kernel.add_pocket(through=True)
    body = _body()
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    # Où est réellement la face cylindrique d'origine ?
    reel = None
    for index, face in enumerate(faces):
        sig = face_signature(face)
        if (sig.get("type") == avant["signature"].get("type")
                and sig.get("rayon") == avant["signature"].get("rayon")):
            reel = index
            break
    out = {
        "avant": avant,
        "faces_apres": len(faces),
        "indice_reel": reel,
        "indice_a_bouge": reel is not None and reel != side,
        "tip_apres": str(attr(attr(body, "Tip"), "Name") or ""),
        # Sans les généalogies d'après, un « perdu » n'est pas
        # diagnosticable : on ne sait pas ce qui a remplacé quoi.
        "genealogie_apres_de_la_bonne_face": (
            None if reel is None else (face_lineage(body, reel) or {}).get(
                "paires")),
    }
    for rang, couple in couples.items():
        hits = resolve_couple(body, couple)
        out["rang{}".format(rang)] = {
            "couple": list(couple),
            "hits": hits,
            "verdict": verdict_for(hits),
            "retrouve_la_bonne_face": (
                hits == [reel] if reel is not None else False),
        }
    out["rang_gagnant"] = next(
        ("rang{}".format(r) for r in couples
         if out["rang{}".format(r)]["retrouve_la_bonne_face"]), None)
    out["retrouve_la_bonne_face"] = out["rang_gagnant"] is not None
    return out


note("q5_renumerote", probe_renumerote)


# --------------------------------------------------------------------------
# Q6 — la scission : l'état « ambigu ».
# --------------------------------------------------------------------------

def probe_scission():
    """Une face d'appui coupée en deux morceaux par un enlèvement.

    Le verdict à trois états prévoit « ambigu ». Encore faut-il que la
    recherche à l'envers rende bien PLUSIEURS candidats — sinon l'état
    est décoratif et un semis se rebranchera en silence sur un morceau.
    """
    kernel = _kernel()
    body = _body()
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    # La face cylindrique extérieure, telle qu'elle est maintenant.
    cible = None
    for index, face in enumerate(faces):
        sig = face_signature(face)
        if sig.get("type") == "Part::GeomCylinder" and sig.get("rayon"):
            cible = index
            break
    if cible is None:
        return {"face_cible": None}
    couples = list(enumerate(rungs(face_lineage(body, cible))))
    avant = {"indice": cible, "signature": face_signature(faces[cible]),
             "couples": {"rang{}".format(r): list(c) for r, c in couples}}
    # Une rainure qui traverse le flanc : la face cylindrique se scinde.
    try:
        haut = kernel._top_face_id()
        kernel.add_rect_sketch(40, 2, face=haut)
        kernel.add_pocket(length=3.0)
    except Exception as exc:  # noqa: BLE001
        return {"avant": avant,
                "scission_impossible": "{}: {}".format(
                    type(exc).__name__, str(exc)[:120])}
    body = _body()
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    morceaux = [
        index for index, face in enumerate(faces)
        if face_signature(face).get("type") == "Part::GeomCylinder"
        and face_signature(face).get("rayon") == avant["signature"].get("rayon")
    ]
    out = {
        "avant": avant,
        "faces_apres": len(faces),
        "morceaux_du_meme_cylindre": morceaux,
        # Le point : si le cylindre s'est scindé, le verdict doit dire
        # « ambigu », pas désigner un morceau au hasard.
        "scission_detectee": len(morceaux) > 1,
    }
    for rang, couple in couples:
        hits = resolve_couple(body, couple)
        out["rang{}".format(rang)] = {
            "couple": list(couple), "hits": hits,
            "verdict": verdict_for(hits),
            "couvre_les_morceaux": sorted(hits) == sorted(morceaux),
        }
    # Honnête si, quand il y a scission, un rang au moins la voit
    # entière — ou déclare « ambigu » plutôt que d'élire un morceau.
    out["honnete"] = (len(morceaux) <= 1) or any(
        out["rang{}".format(r)]["couvre_les_morceaux"]
        or out["rang{}".format(r)]["verdict"] == "ambigu"
        for r, _ in couples)
    return out


note("q6_scission", probe_scission)


# --------------------------------------------------------------------------
# Q7 — le coût.
# --------------------------------------------------------------------------

def probe_cout():
    body = _body()
    faces = list(attr(attr(body, "Shape"), "Faces") or ())
    couple = couple_for_face(body, 0)
    t0 = time.time()
    for _ in range(10):
        resolve_couple(body, couple)
    duree = (time.time() - t0) / 10.0
    return {
        "faces": len(faces),
        "resolution_s": round(duree, 4),
        # Une référence par SEMIS, pas par pierre.
        "pour_5_semis_s": round(duree * 5, 4),
    }


note("q7_cout", probe_cout)


# --------------------------------------------------------------------------
# Q8 — ancrer AILLEURS qu'à l'indice 0. Le vrai test de renumérotation.
# --------------------------------------------------------------------------

def probe_alesage():
    """Q0 et Q5 ancraient sur la face 0 d'un plein — la position la plus
    stable qui soit : OCCT range d'abord les faces du solide de base.

    Un jonc réel est un **tube**. Son alésage n'est pas la face 0, et
    c'est là qu'une renumérotation a une chance de se voir. Sans ce cas,
    « l'indice n'a pas bougé » ne dit rien : on n'a mesuré que le
    barreau le plus solide de l'échelle.
    """
    from engine.kernel import Kernel

    kernel = Kernel()
    kernel.new_part("Sonde toponaming alésage")
    state = kernel.sketch_start()
    sketch = state["sketch"]
    kernel.sketch_add_circle(sketch, 0, 0, 10)
    kernel.sketch_constrain(sketch, "coincident", 0, point1=3, geo2=-1,
                            point2=1)
    kernel.sketch_add_circle(sketch, 0, 0, 4)
    kernel.sketch_constrain(sketch, "coincident", 1, point1=3, geo2=-1,
                            point2=1)
    kernel.sketch_finish(sketch)
    kernel.add_pad(6, sketch=sketch)
    body_name = kernel._require_body().Name

    def body_now():
        return kernel._doc.getObject(body_name)

    faces = list(body_now().Shape.Faces)
    avant = [{"indice": i, "signature": face_signature(f)}
             for i, f in enumerate(faces)]
    # L'alésage : le cylindre de rayon 4.
    cible = next(
        (i for i, f in enumerate(faces)
         if face_signature(f).get("type") == "Part::GeomCylinder"
         and face_signature(f).get("rayon") == 4.0), None)
    out = {"faces": len(faces), "avant": avant, "indice_alesage": cible}
    if cible is None:
        out["tube_rate"] = True
        return out
    out["genealogie_avant"] = (face_lineage(body_now(), cible) or {}).get(
        "paires")
    couples = list(enumerate(rungs(face_lineage(body_now(), cible))))
    try:
        kernel.add_fillet(0.4, face=kernel._top_face_id())
    except Exception as exc:  # noqa: BLE001 — une sonde rapporte
        out["conge_refuse"] = "{}: {}".format(
            type(exc).__name__, str(exc)[:160])
        return out
    faces = list(body_now().Shape.Faces)
    reel = next(
        (i for i, f in enumerate(faces)
         if face_signature(f).get("type") == "Part::GeomCylinder"
         and face_signature(f).get("rayon") == 4.0), None)
    out["faces_apres"] = len(faces)
    out["indice_reel_apres"] = reel
    out["indice_a_bouge"] = reel is not None and reel != cible
    out["genealogie_apres"] = (
        None if reel is None
        else (face_lineage(body_now(), reel) or {}).get("paires"))
    for rang, couple in couples:
        hits = resolve_couple(body_now(), couple)
        out["rang{}".format(rang)] = {
            "couple": list(couple), "hits": hits,
            "verdict": verdict_for(hits),
            "retrouve_la_bonne_face": (
                hits == [reel] if reel is not None else False),
        }
    out["rang_gagnant"] = next(
        ("rang{}".format(r) for r, _ in couples
         if out["rang{}".format(r)]["retrouve_la_bonne_face"]), None)
    return out


note("q8_alesage", probe_alesage)


# --------------------------------------------------------------------------

print(json.dumps(R, ensure_ascii=False, indent=1, default=str), flush=True)

try:
    with open(_REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=2, default=str)
    print("spike> verdict écrit dans {}".format(_REPORT_PATH), flush=True)
except Exception as exc:  # noqa: BLE001 — le rapport imprimé suffit
    print("spike> rapport non écrit : {}".format(exc), flush=True)

q0 = R.get("q0_bug") or {}
q1 = R.get("q1_carte_corps") or {}
q3 = R.get("q3_couple") or {}
q4 = R.get("q4_cote") or {}
q5 = R.get("q5_renumerote") or {}
q6 = R.get("q6_scission") or {}
q8 = R.get("q8_alesage") or {}

bouge = bool(q0.get("indice_a_bouge")) or bool(q8.get("indice_a_bouge"))
rangs_uniques = [nom for nom, item in (q3.get("par_rang") or {}).items()
                 if item.get("unique_par_face")]

verdict = {
    "Q0/Q8 le défaut existe (un indice bouge)": bouge,
    "Q1 le corps a une carte peuplée": bool(
        (q1.get("corps") or {}).get("peuplee")),
    "Q3 au moins un rang est unique par face": bool(rangs_uniques),
    "Q4 la cote ne casse rien": bool(q4.get("rang_gagnant")),
    "Q5 la renumérotation est absorbée": bool(
        q5.get("retrouve_la_bonne_face")),
    "Q6 la scission dit « ambigu »": bool(q6.get("honnete")),
}
print("\n".join("{}  {}".format("OK  " if v else "NON ", k)
                for k, v in verdict.items()), flush=True)
print("\nrangs uniques par face : {}".format(rangs_uniques or "aucun"),
      flush=True)
for nom, source in (("Q4", q4), ("Q5", q5), ("Q8", q8)):
    print("{} rang gagnant : {}".format(nom, source.get("rang_gagnant")),
          flush=True)

print("\nDeux verdicts, dans cet ordre. Si AUCUN indice ne bouge (Q0 et\n"
      "Q8), il n'y a pas de défaut à réparer et le mécanisme est du luxe.\n"
      "Si un indice bouge mais qu'aucun rang ne le rattrape (Q5), la\n"
      "recherche à l'envers ne suffit pas — chercher ailleurs, surtout\n"
      "pas écrire l'UI par-dessus.", flush=True)
print("\nSONDE {}".format(
    "VERTE" if bouge and verdict["Q5 la renumérotation est absorbée"]
    else "ROUGE"), flush=True)
