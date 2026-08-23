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


def couple_of(lineage, quel):
    """Le couple candidat : ``producteur`` (le plus récent) ou ``origine``.

    §4quater dit de chercher le couple stocké **dans** la trace, pas en
    tête — reste à savoir lequel des deux bouts identifie une face de
    façon à la fois unique et durable. La sonde teste les deux plutôt
    que de le décider à l'aveugle.
    """
    if not lineage or not lineage.get("paires"):
        return None
    paires = lineage["paires"]
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
    for quel in ("producteur", "origine"):
        couples = [couple_of(item, quel) for item in lineages]
        presents = [c for c in couples if c]
        out[quel] = {
            "fabricables": len(presents),
            "distincts": len(set(presents)),
            # Le seul critère qui compte ici.
            "unique_par_face": (
                len(presents) == len(set(presents)) and len(presents) > 0),
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
    couple = couple_for_face(body, side)
    out = {"couple_avant": couple}
    # La hauteur du jonc passe de 6 à 9 mm. Aucun indice ne bouge : c'est
    # tout l'intérêt d'une sonde faible — elle ne prouve rien sur la
    # survie, seulement qu'on n'a pas cassé le cas facile.
    kernel.set_param(KERNEL["pad"], "Length", 9.0)
    kernel._recompute()
    body = _body()
    hits = resolve_couple(body, couple)
    out["faces"] = len(attr(attr(body, "Shape"), "Faces") or ())
    out["hits"] = hits
    out["verdict"] = verdict_for(hits)
    out["retrouve_le_meme_indice"] = hits == [side]
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
    couples = {quel: couple_for_face(body, side, quel)
               for quel in ("producteur", "origine")}
    avant["couples"] = {k: (None if v is None else list(v))
                        for k, v in couples.items()}
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
    }
    for quel, couple in couples.items():
        hits = resolve_couple(body, couple)
        out[quel] = {
            "hits": hits,
            "verdict": verdict_for(hits),
            "retrouve_la_bonne_face": (
                hits == [reel] if reel is not None else False),
        }
    out["retrouve_la_bonne_face"] = any(
        out[quel].get("retrouve_la_bonne_face")
        for quel in couples)
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
    couple = couple_for_face(body, cible)
    avant = {"indice": cible, "signature": face_signature(faces[cible]),
             "couple": couple}
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
    hits = resolve_couple(body, couple)
    morceaux = [
        index for index, face in enumerate(faces)
        if face_signature(face).get("type") == "Part::GeomCylinder"
        and face_signature(face).get("rayon") == avant["signature"].get("rayon")
    ]
    return {
        "avant": avant,
        "faces_apres": len(faces),
        "morceaux_du_meme_cylindre": morceaux,
        "hits": hits,
        "verdict": verdict_for(hits),
        # Le point : si le cylindre s'est scindé, le verdict doit dire
        # « ambigu », pas désigner un morceau au hasard.
        "scission_detectee": len(morceaux) > 1,
        "honnete": (len(morceaux) <= 1) or verdict_for(hits) == "ambigu",
    }


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

print(json.dumps(R, ensure_ascii=False, indent=1, default=str), flush=True)

q0 = R.get("q0_bug") or {}
q1 = R.get("q1_carte_corps") or {}
q3 = R.get("q3_couple") or {}
q4 = R.get("q4_cote") or {}
q5 = R.get("q5_renumerote") or {}
q6 = R.get("q6_scission") or {}

verdict = {
    "Q0 le défaut existe (l'indice bouge)": bool(q0.get("indice_a_bouge")),
    "Q1 le corps a une carte peuplée": bool(
        (q1.get("corps") or {}).get("peuplee")),
    "Q3 un couple par face, tous distincts": bool(
        q3.get("fabricables") and q3.get("couples_uniques")),
    "Q4 la cote ne casse rien": q4.get("verdict") == "résolu",
    "Q5 la renumérotation est absorbée": bool(
        q5.get("retrouve_la_bonne_face")),
    "Q6 la scission dit « ambigu »": bool(q6.get("honnete")),
}
print("\n".join("{}  {}".format("OK  " if v else "NON ", k)
                for k, v in verdict.items()), flush=True)

print("\nQ0 et Q5 sont les deux verdicts. Q0 rouge : il n'y a rien à\n"
      "réparer, l'indice tient tout seul. Q5 rouge : la recherche à\n"
      "l'envers ne rattrape pas la renumérotation, et il faut chercher\n"
      "ailleurs — pas écrire l'UI par-dessus.", flush=True)
print("\nSONDE {}".format(
    "VERTE" if verdict["Q0 le défaut existe (l'indice bouge)"]
    and verdict["Q5 la renumérotation est absorbée"] else "ROUGE"), flush=True)
