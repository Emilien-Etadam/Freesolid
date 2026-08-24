"""Métier bijouterie — fonctions prenant ``kernel`` en premier argument.

Pas de mixin, pas d'héritage : sortir ce module vers un dépôt privé
devient un ``git mv``. Le noyau n'est appelé que via la surface
documentée dans ``engine/plugins.py``.
"""

from __future__ import annotations

import os
import re

from engine.kernel import KernelError, _explain, _format_mm

_GEM_ANCHOR_PROPS = (
    ("FreeSolidGemFace", "App::PropertyString",
     "Face d'ancrage du semis (nom OCCT, ex. Face3)"),
    ("FreeSolidGemOwner", "App::PropertyString",
     "Fonction propriétaire de la face d'ancrage"),
    ("FreeSolidGemElement", "App::PropertyString",
     "Nom mappé de la face sur cette fonction"),
    ("FreeSolidGemU", "App::PropertyFloatList",
     "Paramètres u, un par pierre"),
    ("FreeSolidGemV", "App::PropertyFloatList",
     "Paramètres v, un par pierre"),
    ("FreeSolidGemSpin", "App::PropertyFloatList",
     "Rotation autour de la normale, degrés"),
    ("FreeSolidGemLift", "App::PropertyFloatList",
     "Enfoncement le long de la normale, mm"),
    ("FreeSolidGemTemplate", "App::PropertyString",
     "Nom du gabarit de bibliothèque"),
    ("FreeSolidGemError", "App::PropertyString",
     "Erreur d'ancrage (toponaming) — vide si le semis tient"),
)

_GEM_VARSET_FINGERPRINT_SKIP = frozenset({
    "Label", "Label2", "Visibility", "Proxy", "ExpressionEngine",
})

def _mark_gem_tool(kernel, obj):
    if "FreeSolidGemTool" not in obj.PropertiesList:
        obj.addProperty("App::PropertyBool", "FreeSolidGemTool",
                        "FreeSolid", "Gabarit de pierre copié, hors arbre")
    obj.FreeSolidGemTool = True
    if hasattr(obj, "Visibility"):
        obj.Visibility = False

def _mark_gem_boolean_tool(kernel, obj):
    """Corps / forme dérivés d'un semis pour Combiner : hors arbre."""
    if "FreeSolidGemBooleanTool" not in obj.PropertiesList:
        obj.addProperty("App::PropertyBool", "FreeSolidGemBooleanTool",
                        "FreeSolid",
                        "Outil interne d'un booléen sur un semis")
    obj.FreeSolidGemBooleanTool = True
    if hasattr(obj, "Visibility"):
        obj.Visibility = False

def _is_gem_link(kernel, obj):
    return (obj is not None
            and obj.TypeId == "App::Link"
            and "FreeSolidGemFace" in obj.PropertiesList)

def _is_gem_array_child(kernel, obj):
    """Élément ``Semis_i0`` d'un App::Link tableau — pas un semis."""
    if obj is None or getattr(obj, "TypeId", "") != "App::Link":
        return False
    if _is_gem_link(kernel, obj):
        return False
    for parent in getattr(obj, "InList", ()) or ():
        if _is_gem_link(kernel, parent):
            return True
    return False

def _gem_links(kernel):
    doc = kernel._require_doc()
    return [obj for obj in doc.Objects if _is_gem_link(kernel, obj)]

def _ensure_gem_anchor_props(kernel, link):
    for name, type_id, doc in _GEM_ANCHOR_PROPS:
        if name not in link.PropertiesList:
            link.addProperty(type_id, name, "FreeSolid", doc)

def _gem_varset(kernel, body):
    """La VarSet de CETTE copie, jamais la première du document.

    FreeCAD renomme ``Variables`` → ``Variables001`` à la deuxième
    copie. On parcourt le graphe du corps, et on préfère celle qui
    porte ``diametre`` — l'Équations de la pièce n'en a pas.
    """
    seen = []
    for bag in (getattr(body, "OutListRecursive", None),
                getattr(body, "InListRecursive", None)):
        for obj in bag or ():
            if getattr(obj, "TypeId", "") != "App::VarSet":
                continue
            if obj in seen:
                continue
            seen.append(obj)
    for obj in seen:
        if hasattr(obj, "diametre"):
            return obj
    return seen[0] if seen else None

def _library_body(kernel, gemme):
    """Ouvre le gabarit (le construit s'il manque) et rend son corps."""
    from engine.gems import (
        DEFAULT_GEMME, GemError, ensure_flat_cylinder, library_path,
        sanitize_gemme,
    )
    try:
        gemme = sanitize_gemme(gemme)
    except GemError as exc:
        raise KernelError(str(exc)) from exc
    path = library_path(gemme)
    if not os.path.isfile(path):
        if gemme != DEFAULT_GEMME:
            raise KernelError(
                "gabarit de pierre inconnu « {} »".format(gemme))
        try:
            path = ensure_flat_cylinder(path)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(
                "impossible de construire le gabarit cylindre-plat : "
                "{}".format(_explain(exc))) from exc
    real_path = os.path.realpath(path)
    App = kernel._app()
    opened_here = False
    lib = None
    for open_doc in App.listDocuments().values():
        existing = os.path.realpath(getattr(open_doc, "FileName", "") or "")
        if existing == real_path:
            lib = open_doc
            break
    if lib is None:
        try:
            lib = App.openDocument(path, True)
        except TypeError:
            lib = App.openDocument(path)
        opened_here = True
    body = next((obj for obj in lib.Objects
                 if obj.TypeId == "PartDesign::Body"), None)
    if body is None:
        if opened_here:
            try:
                App.closeDocument(lib.Name)
            except Exception:
                pass
        raise KernelError(
            "gabarit « {} » sans corps PartDesign".format(gemme))
    return lib, body, opened_here

def _copy_gem_body(kernel, gemme, diametre):
    """Copie le corps paramétrique dans la pièce (sonde H9)."""
    from engine.gems import cache_key
    doc = kernel._require_doc()
    App = kernel._app()
    # Ne pas créer l'Équations avant la copie : le gabarit s'appelle
    # ``Variables``. Le réserver ferait renommer la copie, et les
    # expressions ``Variables.diametre`` viseraient le mauvais objet.
    lib, src, opened_here = _library_body(kernel, gemme)
    before = {obj.Name for obj in doc.Objects}
    try:
        copie = doc.copyObject(src, True)
    except Exception as exc:  # noqa: BLE001
        raise KernelError(
            "copie du gabarit impossible : {}".format(_explain(exc)))
    finally:
        if opened_here:
            try:
                App.closeDocument(lib.Name)
            except Exception:
                pass
        if doc.Name in App.listDocuments():
            App.setActiveDocument(doc.Name)
    added = [obj for obj in doc.Objects if obj.Name not in before]
    for obj in added:
        _mark_gem_tool(kernel, obj)
    if "FreeSolidGemTemplate" not in copie.PropertiesList:
        copie.addProperty("App::PropertyString", "FreeSolidGemTemplate",
                          "FreeSolid", "Nom du gabarit de bibliothèque")
    copie.FreeSolidGemTemplate = gemme
    varset = next((obj for obj in added if obj.TypeId == "App::VarSet"),
                  _gem_varset(kernel, copie))
    if varset is None:
        raise KernelError(
            "le gabarit copié n'a pas sa variable — le diamètre "
            "ne pourrait plus être piloté")
    _bind_gem_expressions(added, varset)
    if abs(float(varset.diametre) - float(diametre)) > 1e-9:
        varset.diametre = float(diametre)
        doc.recompute()
    copie.Label = "Gabarit {} Ø{} mm".format(
        gemme, _format_mm(diametre))
    kernel._gem_bodies[cache_key(gemme, diametre)] = copie.Name
    return copie

def _bind_gem_expressions(objects, varset):
    """Réécrit ``Variables.x`` vers le nom réel de la VarSet copiée."""
    name = getattr(varset, "Name", "") or ""
    if not name:
        return
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])Variables(?![A-Za-z0-9_])\.")
    replacement = name + "."
    for obj in objects:
        engine = getattr(obj, "ExpressionEngine", None) or ()
        for path, expr in list(engine):
            text = str(expr)
            rewritten = pattern.sub(replacement, text)
            if rewritten == text:
                continue
            try:
                obj.setExpression(path, rewritten)
            except Exception:
                pass

def _ensure_gem_body(kernel, gemme, diametre):
    from engine.gems import cache_key
    doc = kernel._require_doc()
    key = cache_key(gemme, diametre)
    name = kernel._gem_bodies.get(key)
    if name:
        obj = doc.getObject(name)
        if obj is not None:
            return obj
    for obj in doc.Objects:
        if obj.TypeId != "PartDesign::Body":
            continue
        if not getattr(obj, "FreeSolidGemTool", False):
            continue
        if getattr(obj, "FreeSolidGemTemplate", "") != gemme:
            continue
        varset = _gem_varset(kernel, obj)
        if varset is None or not hasattr(varset, "diametre"):
            continue
        if abs(float(varset.diametre) - float(diametre)) < 1e-9:
            kernel._gem_bodies[key] = obj.Name
            return obj
    return _copy_gem_body(kernel, gemme, diametre)

def _anchor_face(kernel, face_id):
    body = kernel._require_body()
    shape = getattr(body, "Shape", None)
    faces = getattr(shape, "Faces", None) or ()
    index = int(face_id)
    if index < 0 or index >= len(faces):
        raise KernelError("face inconnue : {}".format(face_id))
    return faces[index], index

def _gem_uv(kernel, face, x, y, z):
    from engine.gems import GemError, project_uv
    try:
        u, v, on_domain = project_uv(face, x, y, z)
    except GemError as exc:
        raise KernelError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise KernelError(
            "ce point ne se projette pas sur la face : {}".format(
                _explain(exc))) from exc
    if not on_domain:
        raise KernelError(
            "ce point tombe hors du contour de la face "
            "(trou ou hors surface) — la pierre n'est pas posée")
    return u, v

def _find_semis(kernel, body, face_name, gemme, diametre):
    for link in _gem_links(kernel):
        linked = getattr(link, "LinkedObject", None)
        if linked is not body:
            continue
        if str(getattr(link, "FreeSolidGemFace", "")) != face_name:
            continue
        if getattr(link, "FreeSolidGemTemplate", "") != gemme:
            continue
        varset = _gem_varset(kernel, linked)
        if varset is None:
            continue
        if abs(float(getattr(varset, "diametre", 0)) - float(diametre)) < 1e-9:
            return link
    return None

def _new_semis(kernel, body, face_name, gemme, diametre):
    from engine.gems import is_bspline_surface
    doc = kernel._require_doc()
    link = doc.addObject("App::Link", "Semis")
    link.LinkedObject = body
    # Sans ça, ElementCount crée Semis_i0… dans l'arbre, souvent
    # « Link broken » tant que PlacementList n'est pas recomputé.
    if hasattr(link, "ShowElement"):
        link.ShowElement = False
    _ensure_gem_anchor_props(kernel, link)
    link.FreeSolidGemFace = face_name
    link.FreeSolidGemOwner = ""
    link.FreeSolidGemElement = ""
    link.FreeSolidGemU = []
    link.FreeSolidGemV = []
    link.FreeSolidGemSpin = []
    link.FreeSolidGemLift = []
    link.FreeSolidGemTemplate = gemme
    link.FreeSolidGemError = ""
    link.Label = "Semis de pierres — {} Ø{} mm".format(
        gemme, _format_mm(diametre))
    try:
        index = _face_index_or_none(kernel, face_name)
        if index is not None:
            _capture_gem_couple(kernel, link, index)
            face, _ = _anchor_face(kernel, index)
            if is_bspline_surface(face):
                link.Label = link.Label + " (surface libre)"
    except KernelError:
        pass
    return link

def _face_index_or_none(kernel, name):
    from engine.gems import GemError, face_index
    try:
        return face_index(name)
    except GemError:
        return None

def _append_stone(kernel, link, u, v, spin, lift):
    us = list(link.FreeSolidGemU or [])
    vs = list(link.FreeSolidGemV or [])
    spins = list(link.FreeSolidGemSpin or [])
    lifts = list(link.FreeSolidGemLift or [])
    us.append(float(u))
    vs.append(float(v))
    spins.append(float(spin))
    lifts.append(float(lift))
    link.FreeSolidGemU = us
    link.FreeSolidGemV = vs
    link.FreeSolidGemSpin = spins
    link.FreeSolidGemLift = lifts
    return len(us) - 1

def _write_stone_lists(kernel, link, us, vs, spins, lifts):
    link.FreeSolidGemU = [float(v) for v in us]
    link.FreeSolidGemV = [float(v) for v in vs]
    link.FreeSolidGemSpin = [float(v) for v in spins]
    link.FreeSolidGemLift = [float(v) for v in lifts]

def _require_gem_link(kernel, name):
    doc = kernel._require_doc()
    obj = doc.getObject(str(name))
    if obj is None or not _is_gem_link(kernel, obj):
        raise KernelError("semis inconnu : {}".format(name))
    return obj

def _require_stone_index(kernel, link, index):
    count = len(list(link.FreeSolidGemU or []))
    number = int(index)
    if number < 0 or number >= count:
        raise KernelError(
            "pierre n° {} absente de « {} » ({} pierre(s))".format(
                index, link.Label, count))
    return number, count

def _drop_empty_semis(kernel, link):
    if len(list(link.FreeSolidGemU or [])) > 0:
        return
    doc = kernel._require_doc()
    body = getattr(link, "LinkedObject", None)
    doc.removeObject(link.Name)
    if body is not None and not any(
            getattr(other, "LinkedObject", None) is body
            for other in _gem_links(kernel)):
        _remove_gem_body(kernel, body)

def _remove_gem_body(kernel, body):
    from engine.gems import cache_key
    doc = kernel._require_doc()
    varset = _gem_varset(kernel, body)
    gemme = getattr(body, "FreeSolidGemTemplate", "") or ""
    diametre = float(getattr(varset, "diametre", 0)) if varset else 0.0
    kernel._gem_bodies.pop(cache_key(gemme, diametre), None)
    to_remove = []
    if varset is not None:
        to_remove.append(varset)
    for obj in list(getattr(body, "Group", ()) or ()):
        to_remove.append(obj)
    to_remove.append(body)
    for obj in to_remove:
        try:
            doc.removeObject(obj.Name)
        except Exception:
            pass

def _element_map_populated(kernel, shape=None):
    """True si la carte d'éléments du corps est peuplée.

    Repli explicite : une carte vide (FreeCAD ancien, forme
    importée) interdit la capture — on résout par indice, comme
    avant P044. Pas un ``try`` autour de la capture.
    """
    if shape is None:
        body = kernel._body
        shape = getattr(body, "Shape", None) if body is not None else None
    if shape is None:
        return False
    size = getattr(shape, "ElementMapSize", None)
    if size is None:
        return False
    try:
        return int(size) > 0
    except (TypeError, ValueError):
        return False

def _mapped_element_name(kernel, shape, indexed):
    if shape is None:
        return ""
    fn = getattr(shape, "getElementMappedName", None)
    if not callable(fn):
        return ""
    try:
        value = fn(indexed)
    except Exception:
        return ""
    if isinstance(value, (tuple, list)):
        value = value[0] if value else ""
    return str(value or "")

def _element_history(kernel, bearer, mapped):
    if bearer is None or not mapped:
        return None
    fn = getattr(bearer, "getElementHistory", None)
    if not callable(fn):
        shape = getattr(bearer, "Shape", None)
        fn = getattr(shape, "getElementHistory", None) if shape is not None else None
    if not callable(fn):
        return None
    try:
        return fn(mapped)
    except Exception:
        return None

def _history_pairs_for_face(kernel, face_index):
    """Généalogie d'une face du corps : liste de ``(fonction, nom mappé)``."""
    from engine.gems import face_name, trace_pairs
    body = kernel._body
    if body is None:
        return []
    indexed = face_name(face_index)
    mapped = _mapped_element_name(kernel, getattr(body, "Shape", None), indexed)
    bearer = body
    if not mapped:
        tip = getattr(body, "Tip", None)
        if tip is not None:
            mapped = _mapped_element_name(
                kernel, getattr(tip, "Shape", None), indexed)
            if mapped:
                bearer = tip
    if not mapped:
        return []
    pairs = trace_pairs(_element_history(kernel, bearer, mapped))
    head = (str(getattr(bearer, "Name", "") or ""), str(mapped))
    if head[0] and head not in pairs:
        pairs = [head] + list(pairs)
    return pairs

def _gem_stored_couple(kernel, link):
    owner = str(getattr(link, "FreeSolidGemOwner", "") or "")
    element = str(getattr(link, "FreeSolidGemElement", "") or "")
    if owner and element:
        return (owner, element)
    return None

def _capture_gem_couple(kernel, link, face_index):
    """Enregistre le couple propriétaire. No-op si la carte est vide."""
    from engine.gems import owner_couple
    _ensure_gem_anchor_props(kernel, link)
    if not _element_map_populated(kernel):
        return
    couple = owner_couple(_history_pairs_for_face(kernel, face_index))
    if couple is None:
        return
    link.FreeSolidGemOwner = couple[0]
    link.FreeSolidGemElement = couple[1]

def _resolve_gem_couple(kernel, couple, n_faces):
    from engine.gems import resolution_verdict
    hits = []
    for index in range(n_faces):
        if couple in _history_pairs_for_face(kernel, index):
            hits.append(index)
    return resolution_verdict(hits), hits

def _refresh_gem_placements(kernel):
    """Recalcule PlacementList depuis (u, v) et la face courante.

    Si le semis porte un couple de provenance, on cherche la face à
    l'envers dans la généalogie. Ambigu ou perdu : on ne déplace
    rien — l'indice précédent reste, l'erreur le dit. Sans couple,
    résolution par indice comme avant, et capture au premier
    recompute réussi (documents existants).
    """
    from engine.gems import face_name, is_bspline_surface, placement_at
    if kernel._doc is None or kernel._body is None:
        return
    shape = getattr(kernel._body, "Shape", None)
    faces = list(getattr(shape, "Faces", None) or ())
    map_ready = _element_map_populated(kernel, shape)
    for link in _gem_links(kernel):
        _ensure_gem_anchor_props(kernel, link)
        us = list(link.FreeSolidGemU or [])
        vs = list(link.FreeSolidGemV or [])
        spins = list(link.FreeSolidGemSpin or [])
        lifts = list(link.FreeSolidGemLift or [])
        count = min(len(us), len(vs))
        while len(spins) < count:
            spins.append(0.0)
        while len(lifts) < count:
            lifts.append(0.0)
        face_id = _face_index_or_none(kernel, link.FreeSolidGemFace)
        error = ""
        face = None
        couple = _gem_stored_couple(kernel, link)
        if couple is not None and map_ready:
            verdict, hits = _resolve_gem_couple(kernel, couple, len(faces))
            if verdict == "résolu":
                face_id = hits[0]
                link.FreeSolidGemFace = face_name(face_id)
            elif verdict == "ambigu":
                error = ("la face d'appui s'est scindée — les pierres "
                         "ne savent plus laquelle suivre")
            else:
                error = "la face d'appui a disparu"
        if error:
            link.FreeSolidGemError = error
            continue
        if face_id is None or face_id < 0 or face_id >= len(faces):
            error = ("la face d'ancrage « {} » a disparu — "
                     "le semis n'a pas été déplacé".format(
                         link.FreeSolidGemFace or "?"))
        else:
            face = faces[face_id]
        placements = []
        if face is not None and count:
            try:
                for i in range(count):
                    placements.append(placement_at(
                        face, us[i], vs[i], spins[i], lifts[i]))
            except Exception as exc:  # noqa: BLE001
                error = ("la face d'ancrage a changé de nature : {}"
                         .format(_explain(exc)))
                placements = []
        if error:
            link.FreeSolidGemError = error
            continue
        link.FreeSolidGemError = ""
        if couple is None and map_ready and face_id is not None:
            _capture_gem_couple(kernel, link, face_id)
        if not hasattr(link, "ElementCount") or not hasattr(
                link, "PlacementList"):
            continue
        if hasattr(link, "ShowElement"):
            link.ShowElement = False
        link.ElementCount = count
        if count:
            link.PlacementList = placements
        spline = is_bspline_surface(face) if face is not None else False
        label = "Semis de pierres — {} Ø{} mm".format(
            link.FreeSolidGemTemplate or "pierre",
            _format_mm(_gem_diametre(kernel, link)))
        if spline:
            label += " (surface libre)"
        if count > 1:
            label = "{} × {}".format(count, label)
        link.Label = label

def _gem_diametre(kernel, link):
    body = getattr(link, "LinkedObject", None)
    varset = _gem_varset(kernel, body) if body is not None else None
    if varset is None or not hasattr(varset, "diametre"):
        return 0.0
    return float(varset.diametre)

def _gem_entry(kernel, link):
    from engine.gems import (
        arc_entraxe_mm, face_radius_mm, is_bspline_surface,
        placement_at, seating_gap_mm,
    )
    us = list(link.FreeSolidGemU or [])
    vs = list(link.FreeSolidGemV or [])
    spins = list(link.FreeSolidGemSpin or [])
    lifts = list(link.FreeSolidGemLift or [])
    count = min(len(us), len(vs))
    error = str(getattr(link, "FreeSolidGemError", "") or "")
    face = None
    spline = False
    face_id = _face_index_or_none(kernel, getattr(link, "FreeSolidGemFace", ""))
    try:
        if face_id is not None:
            face, face_id = _anchor_face(kernel, face_id)
            spline = is_bspline_surface(face)
    except KernelError:
        face = None
        if not error:
            error = "la face d'ancrage « {} » a disparu".format(
                link.FreeSolidGemFace)
    stones = []
    for i in range(count):
        spin = spins[i] if i < len(spins) else 0.0
        lift = lifts[i] if i < len(lifts) else 0.0
        stone = {
            "index": i,
            "u": float(us[i]),
            "v": float(vs[i]),
            "spin": float(spin),
            "lift": float(lift),
        }
        if face is not None:
            try:
                place = placement_at(face, us[i], vs[i], spin, lift)
                stone["x"] = float(place.Base.x)
                stone["y"] = float(place.Base.y)
                stone["z"] = float(place.Base.z)
            except Exception:
                pass
        stones.append(stone)
    diametre = _gem_diametre(kernel, link)
    rayon = face_radius_mm(face) if face is not None else None
    entraxe = arc_entraxe_mm(rayon, count)
    ecart = seating_gap_mm(entraxe, diametre)
    return {
        "name": link.Name,
        "label": link.Label,
        "kind": "Semis de pierres",
        "type": link.TypeId,
        "gemme": getattr(link, "FreeSolidGemTemplate", "") or "",
        "diametre": diametre,
        "rayon_mm": None if rayon is None else round(float(rayon), 3),
        "entraxe_mm": None if entraxe is None else round(float(entraxe), 3),
        "ecart_sieges_mm": (
            None if ecart is None else round(float(ecart), 3)),
        "chevauchement": bool(ecart is not None and ecart < 0),
        "voisine_min_mm": None,
        "ecart_min_mm": None,
        "face": getattr(link, "FreeSolidGemFace", "") or "",
        "face_id": face_id,
        "count": count,
        "error": bool(error) or "Invalid" in (link.State or ()),
        "error_message": error,
        "spline": spline,
        "stones": stones,
    }

def list_gems(kernel):
    """Liste des semis — pour l'UI et le selftest."""
    kernel._require_body()
    _refresh_gem_placements(kernel)
    return {"gems": _gem_entries(kernel)}

def _gem_entries(kernel):
    entries = [_gem_entry(kernel, link) for link in _gem_links(kernel)]
    return _annotate_gem_neighbors(kernel, entries)

def _annotate_gem_neighbors(kernel, entries):
    """Écart et entraxe min : balayage global, puis min par semis."""
    from engine.gems import voisines_min_mm
    points = []
    radii = []
    owners = []
    for index, entry in enumerate(entries):
        radius = float(entry.get("diametre") or 0) / 2.0
        for stone in entry.get("stones") or []:
            if "x" not in stone or "y" not in stone or "z" not in stone:
                continue
            points.append((stone["x"], stone["y"], stone["z"]))
            radii.append(radius)
            owners.append(index)
    pairs = voisines_min_mm(points, radii)
    best = {}
    for (entraxe, ecart), owner in zip(pairs, owners):
        if entraxe is None:
            continue
        previous = best.get(owner)
        if previous is None or entraxe < previous[0]:
            best[owner] = (entraxe, ecart)
    for index, entry in enumerate(entries):
        pair = best.get(index)
        if pair is None:
            entry["voisine_min_mm"] = None
            entry["ecart_min_mm"] = None
        else:
            entry["voisine_min_mm"] = round(float(pair[0]), 6)
            entry["ecart_min_mm"] = round(float(pair[1]), 6)
    return entries

def place_gem(kernel, face, x, y, z, gemme=None, diametre=None,
              spin=None, lift=None):
    """Pose une pierre sur une face. Le point reçu est projeté.

    L'autorité est ``(u, v)``, jamais le point du raycast ni une
    matrice de placement. Poser n'enlève pas de matière.
    """
    from engine.gems import (
        DEFAULT_GEMME, GemError, face_name, parse_diametre,
        parse_spin_lift, sanitize_gemme,
    )
    kernel._require_body()
    try:
        gemme = sanitize_gemme(gemme or DEFAULT_GEMME)
        diametre = parse_diametre(diametre)
        spin = parse_spin_lift(spin)
        lift = parse_spin_lift(lift)
        name = face_name(face)
    except GemError as exc:
        raise KernelError(str(exc)) from exc
    target, _index = _anchor_face(kernel, face)
    u, v = _gem_uv(kernel, target, x, y, z)
    body = _ensure_gem_body(kernel, gemme, diametre)
    link = _find_semis(kernel, body, name, gemme, diametre)
    if link is None:
        link = _new_semis(kernel, body, name, gemme, diametre)
    _append_stone(kernel, link, u, v, spin, lift)
    try:
        kernel._recompute()
    except KernelError:
        us = list(link.FreeSolidGemU or [])
        if us:
            _write_stone_lists(
                kernel, link, us[:-1],
                list(link.FreeSolidGemV or [])[:-1],
                list(link.FreeSolidGemSpin or [])[:-1],
                list(link.FreeSolidGemLift or [])[:-1])
        _drop_empty_semis(kernel, link)
        raise
    return kernel.get_tree()

def move_gem(kernel, gem, index, x, y, z, face=None):
    """Déplace une pierre. ``face`` absent = la même face."""
    from engine.gems import GemError, face_name
    link = _require_gem_link(kernel, gem)
    number, _count = _require_stone_index(kernel, link, index)
    if face is None:
        target_name = str(link.FreeSolidGemFace)
        face_id = _face_index_or_none(kernel, target_name)
        if face_id is None:
            raise KernelError(
                "la face d'ancrage « {} » a disparu — "
                "la pierre n'a pas été déplacée".format(target_name))
        target, _ = _anchor_face(kernel, face_id)
    else:
        try:
            target_name = face_name(face)
        except GemError as exc:
            raise KernelError(str(exc)) from exc
        target, _ = _anchor_face(kernel, face)
    u, v = _gem_uv(kernel, target, x, y, z)
    us = list(link.FreeSolidGemU or [])
    vs = list(link.FreeSolidGemV or [])
    spins = list(link.FreeSolidGemSpin or [])
    lifts = list(link.FreeSolidGemLift or [])
    same_face = target_name == str(link.FreeSolidGemFace)
    dest_link = link
    dest_index = number
    if same_face:
        us[number] = u
        vs[number] = v
        _write_stone_lists(kernel, link, us, vs, spins, lifts)
    else:
        spin = spins[number] if number < len(spins) else 0.0
        lift = lifts[number] if number < len(lifts) else 0.0
        del us[number], vs[number]
        if number < len(spins):
            del spins[number]
        if number < len(lifts):
            del lifts[number]
        _write_stone_lists(kernel, link, us, vs, spins, lifts)
        body = getattr(link, "LinkedObject", None)
        gemme = getattr(link, "FreeSolidGemTemplate", "") or ""
        diametre = _gem_diametre(kernel, link)
        dest = _find_semis(kernel, body, target_name, gemme, diametre)
        if dest is None:
            dest = _new_semis(kernel, body, target_name, gemme, diametre)
        dest_index = _append_stone(kernel, dest, u, v, spin, lift)
        dest_link = dest
        _drop_empty_semis(kernel, link)
    try:
        kernel._recompute()
    except KernelError as exc:
        raise KernelError(
            "{} — la pierre n'a pas été déplacée".format(exc)) from exc
    tree = kernel.get_tree()
    tree["gem_moved"] = {"gem": dest_link.Name, "index": dest_index}
    return tree

def spin_gem(kernel, gem, index, spin=None, lift=None):
    """Rotation autour de la normale et enfoncement. Absents = inchangés."""
    from engine.gems import GemError, parse_spin_lift
    link = _require_gem_link(kernel, gem)
    number, _count = _require_stone_index(kernel, link, index)
    spins = list(link.FreeSolidGemSpin or [])
    lifts = list(link.FreeSolidGemLift or [])
    while len(spins) <= number:
        spins.append(0.0)
    while len(lifts) <= number:
        lifts.append(0.0)
    try:
        if spin is not None:
            spins[number] = parse_spin_lift(spin)
        if lift is not None:
            lifts[number] = parse_spin_lift(lift)
    except GemError as exc:
        raise KernelError(str(exc)) from exc
    link.FreeSolidGemSpin = spins
    link.FreeSolidGemLift = lifts
    kernel._recompute()
    return kernel.get_tree()

def remove_gem(kernel, gem, index):
    """Retire une pierre du semis. Le dernier enlève le semis."""
    link = _require_gem_link(kernel, gem)
    number, _count = _require_stone_index(kernel, link, index)
    us = list(link.FreeSolidGemU or [])
    vs = list(link.FreeSolidGemV or [])
    spins = list(link.FreeSolidGemSpin or [])
    lifts = list(link.FreeSolidGemLift or [])
    del us[number], vs[number]
    if number < len(spins):
        del spins[number]
    if number < len(lifts):
        del lifts[number]
    _write_stone_lists(kernel, link, us, vs, spins, lifts)
    _drop_empty_semis(kernel, link)
    kernel._recompute()
    return kernel.get_tree()

def resize_gem(kernel, gem, diametre):
    """Change le diamètre d'un semis. Les ``(u, v)`` ne bougent pas.

    Si le gabarit ne sert que ce semis, on écrit la VarSet en place.
    S'il en sert d'autres, on relie un gabarit au nouveau diamètre
    sans toucher aux jumeaux — fusionner casserait la sélection.
    """
    from engine.gems import GemError, cache_key, parse_diametre
    link = _require_gem_link(kernel, gem)
    try:
        new_d = parse_diametre(diametre)
    except GemError as exc:
        raise KernelError(str(exc)) from exc
    old_body = getattr(link, "LinkedObject", None)
    if old_body is None:
        raise KernelError("semis sans gabarit : {}".format(gem))
    gemme = getattr(link, "FreeSolidGemTemplate", "") or ""
    old_d = _gem_diametre(kernel, link)
    if abs(old_d - new_d) < 1e-9:
        return kernel.get_tree()
    users = [
        other for other in _gem_links(kernel)
        if getattr(other, "LinkedObject", None) is old_body
    ]
    if len(users) <= 1:
        varset = _gem_varset(kernel, old_body)
        if varset is None or not hasattr(varset, "diametre"):
            raise KernelError(
                "le gabarit n'a pas sa variable — le diamètre "
                "ne peut pas être changé")
        varset.diametre = float(new_d)
        kernel._gem_bodies.pop(cache_key(gemme, old_d), None)
        kernel._gem_bodies[cache_key(gemme, new_d)] = old_body.Name
        old_body.Label = "Gabarit {} Ø{} mm".format(
            gemme, _format_mm(new_d))
    else:
        link.LinkedObject = _ensure_gem_body(kernel, gemme, new_d)
    kernel._recompute()
    return kernel.get_tree()

def _placed_gem_copy(kernel, shape, placement):
    """Copie du gabarit, géométrie déjà au placement d'instance."""
    copy = shape.copy()
    combined = placement
    existing = getattr(copy, "Placement", None)
    if existing is not None:
        combined = placement.multiply(existing)
    try:
        baked = copy.transformGeometry(combined.toMatrix())
        return baked
    except Exception:
        copy.Placement = combined
        return copy

def _gem_compound_shape(kernel, link):
    """Compound des N copies : une forme, une opération booléenne.

    Relit ``PlacementList`` (jamais une copie figée). ``None`` si le
    semis n'a pas encore de placement — l'appelant distingue le
    vide initial d'un gabarit sans solide.
    """
    import Part
    linked = getattr(link, "LinkedObject", None)
    base = getattr(linked, "Shape", None) if linked is not None else None
    if base is None or not getattr(base, "Solids", None):
        raise KernelError(
            "le gabarit du semis n'a pas de solide — rien à combiner")
    placements = list(getattr(link, "PlacementList", None) or [])
    if not placements:
        return None
    total = len(placements)
    copies = []
    for index, place in enumerate(placements, start=1):
        kernel._report_progress("Construction du compound", index, total)
        copies.append(_placed_gem_copy(kernel, base, place))
    return Part.makeCompound(copies)

def _gem_template_signature(kernel, link):
    """Nom du gabarit et variables de sa VarSet, triées par nom.

    ``resize_gem`` ne bouge aucun placement : sans ces cotes dans
    l'empreinte, le booléen resterait cuit à l'ancien diamètre.
    """
    template = str(getattr(link, "FreeSolidGemTemplate", "") or "")
    body = getattr(link, "LinkedObject", None)
    varset = _gem_varset(kernel, body) if body is not None else None
    values = []
    if varset is not None:
        for name in getattr(varset, "PropertiesList", ()) or ():
            if name in _GEM_VARSET_FINGERPRINT_SKIP:
                continue
            raw = getattr(varset, name, None)
            if isinstance(raw, bool):
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            values.append((name, number))
        values.sort(key=lambda item: item[0])
    signed = ",".join(
        "{}={:.6f}".format(name, number) for name, number in values)
    return "{}#{}".format(template, signed)

def _gem_placement_fingerprint(kernel, link):
    """Signature gabarit + placements — pour ne pas recuire un compound identique."""
    placements = list(getattr(link, "PlacementList", None) or [])
    chunks = []
    for place in placements:
        base = getattr(place, "Base", None)
        rot = getattr(place, "Rotation", None)
        quat = getattr(rot, "Q", None) if rot is not None else None
        if base is None:
            chunks.append("?")
            continue
        qx, qy, qz, qw = (quat if quat is not None else (0, 0, 0, 1))[:4]
        chunks.append("{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f}".format(
            float(base.x), float(base.y), float(base.z),
            float(qx), float(qy), float(qz), float(qw)))
    return "{}#{}#{}".format(
        link.Name, _gem_template_signature(kernel, link), "|".join(chunks))

def _set_gem_boolean_shape(kernel, obj, compound, fingerprint):
    """Pose la forme si le gabarit ou les placements ont changé.

    Retourne True si écrit.
    """
    if "FreeSolidGemBooleanFingerprint" not in obj.PropertiesList:
        obj.addProperty(
            "App::PropertyString", "FreeSolidGemBooleanFingerprint",
            "FreeSolid", "Empreinte du gabarit et des placements du semis")
    if str(getattr(obj, "FreeSolidGemBooleanFingerprint", "") or "") == fingerprint:
        return False
    obj.Shape = compound
    obj.FreeSolidGemBooleanFingerprint = fingerprint
    return True

def _derive_gem_boolean_body(kernel, link):
    """Corps outil dérivé du semis — le semis lui-même n'est pas absorbé.

    Même route que la gravure : ``Part::Feature`` porteur de la
    forme, enveloppé dans un corps par ``BaseFeature``.
    """
    doc = kernel._require_doc()
    _refresh_gem_placements(kernel)
    compound = _gem_compound_shape(kernel, link)
    if compound is None:
        raise KernelError("semis vide — rien à combiner")
    shape_feature = doc.addObject("Part::Feature", "GemBooleanShape")
    shape_feature.Label = "Forme du semis"
    if "FreeSolidGemBooleanSource" not in shape_feature.PropertiesList:
        shape_feature.addProperty(
            "App::PropertyString", "FreeSolidGemBooleanSource",
            "FreeSolid", "Semis dont le compound est dérivé")
    shape_feature.FreeSolidGemBooleanSource = link.Name
    _set_gem_boolean_shape(
        kernel, shape_feature, compound,
        _gem_placement_fingerprint(kernel, link))
    _mark_gem_boolean_tool(kernel, shape_feature)
    tool_body = doc.addObject("PartDesign::Body", "GemBooleanBody")
    tool_body.Label = "Corps outil du semis"
    tool_body.BaseFeature = shape_feature
    _mark_gem_boolean_tool(kernel, tool_body)
    doc.recompute()
    return tool_body

def _refresh_gem_boolean_tools(kernel):
    """Rebâtit le compound de chaque booléen dérivé d'un semis.

    C'est ce qui distingue un booléen vivant d'une cuisson : bouger
    une pierre puis reconstruire déplace son empreinte.
    """
    doc = kernel._doc
    if doc is None:
        return
    for obj in list(doc.Objects):
        if "FreeSolidGemBooleanSource" not in getattr(
                obj, "PropertiesList", ()):
            continue
        source = str(getattr(obj, "FreeSolidGemBooleanSource", "") or "")
        if not source:
            continue
        link = doc.getObject(source)
        if link is None or not _is_gem_link(kernel, link):
            continue
        try:
            compound = _gem_compound_shape(kernel, link)
        except KernelError:
            continue
        if compound is None:
            continue
        _set_gem_boolean_shape(
            kernel, obj, compound, _gem_placement_fingerprint(kernel, link))

def _tessellate_gems(kernel, deviation):
    """Une géométrie par semis, N matrices d'instance — pas N objets."""
    from engine.gems import matrix_list, placement_at
    from engine import protocol
    _refresh_gem_placements(kernel)
    out = []
    for link in _gem_links(kernel):
        entry = _gem_entry(kernel, link)
        linked = getattr(link, "LinkedObject", None)
        shape = getattr(linked, "Shape", None)
        geometry = {"positions": [], "indices": []}
        if shape is not None and shape.Faces:
            faces = []
            for i, face in enumerate(shape.Faces):
                packed, _spline = kernel._face_mesh(face, i, deviation)
                faces.append(packed)
            packed = protocol.pack_mesh(faces)
            geometry = {
                "positions": packed["positions"],
                "indices": packed["indices"],
            }
            if packed.get("normals"):
                geometry["normals"] = packed["normals"]
        instances = []
        face = None
        face_id = entry.get("face_id")
        try:
            if face_id is not None:
                face, _ = _anchor_face(kernel, face_id)
        except KernelError:
            face = None
        for stone in entry["stones"]:
            matrix = None
            if face is not None:
                try:
                    place = placement_at(
                        face, stone["u"], stone["v"],
                        stone["spin"], stone["lift"])
                    matrix = matrix_list(place)
                except Exception:
                    matrix = None
            instances.append({
                "index": stone["index"],
                "matrix": matrix or [],
                "x": stone.get("x"),
                "y": stone.get("y"),
                "z": stone.get("z"),
                "spin": stone["spin"],
                "lift": stone["lift"],
            })
        out.append({
            "name": entry["name"],
            "label": entry["label"],
            "error": entry["error"],
            "spline": entry["spline"],
            "face_id": entry.get("face_id"),
            "positions": geometry["positions"],
            "indices": geometry["indices"],
            "normals": geometry.get("normals"),
            "diametre": entry.get("diametre"),
            "instances": instances,
        })
    return out

def tolerates_invalid(kernel, obj):
    return _is_gem_link(kernel, obj) or _is_gem_array_child(kernel, obj)

def boolean_tool(kernel, obj):
    if obj is None or not _is_gem_link(kernel, obj):
        return None
    return _derive_gem_boolean_body(kernel, obj)

def deletes_feature(kernel, obj):
    if obj is None or not _is_gem_link(kernel, obj):
        return False
    doc = kernel._require_doc()
    body = getattr(obj, "LinkedObject", None)
    doc.removeObject(obj.Name)
    if body is not None and not any(
            getattr(other, "LinkedObject", None) is body
            for other in _gem_links(kernel)):
        _remove_gem_body(kernel, body)
    kernel._recompute()
    return True
