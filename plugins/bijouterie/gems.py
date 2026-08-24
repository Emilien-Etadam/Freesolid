"""Pierres aimantées sur une surface — gabarits et ancrage ``(u, v)``.

Le mécanisme (P034) copie un corps paramétrique depuis une bibliothèque
de gabarits, l'instancie par ``App::Link`` et le recale à chaque
recompute depuis les paramètres de surface. Rien ici n'importe FreeCAD
au niveau module.
"""

from __future__ import annotations

import math
import os
import re

DEFAULT_GEMME = "cylindre-plat"
DEFAULT_DIAMETRE = 1.5
DEFAULT_EPAISSEUR = 0.5

#: Noms de gabarit = nom de fichier sous ``assets/`` du plugin, sans extension.
_GEMME_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_FACE_NAME_RE = re.compile(r"^Face(\d+)$")
#: Nom FreeCAD d'une esquisse — pas une fonction propriétaire (P044).
_SKETCH_NAME_RE = re.compile(r"^(?:Sketch|Esquisse)\d*$", re.I)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIBRARY_DIR = os.path.join(_PLUGIN_DIR, "assets")


class GemError(ValueError):
    """Entrée invalide (nom de gabarit, face, cote) — message designer."""


def library_dir() -> str:
    return _LIBRARY_DIR


def sanitize_gemme(name) -> str:
    """Valide un nom de gabarit. Refuse tout chemin."""
    text = "" if name is None else str(name).strip()
    if not text:
        return DEFAULT_GEMME
    if not _GEMME_NAME_RE.fullmatch(text):
        raise GemError(
            "gabarit de pierre inconnu « {} » — attendu un nom "
            "comme cylindre-plat".format(text))
    return text


def library_path(gemme) -> str:
    """Chemin du ``.FCStd`` gabarit, déjà jailé par ``sanitize_gemme``."""
    return os.path.join(library_dir(), sanitize_gemme(gemme) + ".FCStd")


def parse_positive(value, default, what) -> float:
    if value is None:
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GemError("{} invalide".format(what)) from exc
    if number <= 0:
        raise GemError("le {} doit être positif".format(what))
    return number


def parse_diametre(value, default=DEFAULT_DIAMETRE) -> float:
    return parse_positive(value, default, "diamètre")


def parse_spin_lift(value, default=0.0) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise GemError("angle ou enfoncement invalide") from exc


def cache_key(gemme, diametre) -> tuple:
    return (sanitize_gemme(gemme), round(float(diametre), 6))


def face_radius_mm(face):
    """Rayon d'une face cylindrique ou d'un tore, sinon ``None``.

    Pas d'import FreeCAD : ``getattr`` sur l'objet face suffit, et rend
    la fonction testable avec un simple stub.
    """
    surface = getattr(face, "Surface", None)
    if surface is None:
        return None
    for attr in ("Radius", "MajorRadius"):
        raw = getattr(surface, attr, None)
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def arc_entraxe_mm(rayon_mm, count):
    """Entraxe d'arc : circonférence / effectif. ``None`` si indéfini."""
    try:
        n = int(count)
        radius = float(rayon_mm)
    except (TypeError, ValueError):
        return None
    if n <= 0 or radius <= 0:
        return None
    return 2.0 * math.pi * radius / n


def seating_gap_mm(entraxe_mm, diametre_mm):
    """Écart entre sièges : entraxe moins diamètre. Négatif = chevauchement."""
    try:
        entraxe = float(entraxe_mm)
        diametre = float(diametre_mm)
    except (TypeError, ValueError):
        return None
    return entraxe - diametre


def voisines_min_mm(points, rayons):
    """Pour chaque pierre : (entraxe, écart) avec sa plus proche voisine.

    ``points`` : liste de (x, y, z). ``rayons`` : demi-diamètres, même
    ordre. Rend une liste de (entraxe_mm, ecart_mm), ``(None, None)``
    quand il n'y a pas d'autre pierre.

    La plus proche se choisit sur l'entraxe, pas sur l'écart. Double
    boucle symétrique : chaque paire mise à jour des deux côtés.
    """
    n = min(len(points), len(rayons))
    best_entraxe = [None] * n
    best_ecart = [None] * n
    if n < 2:
        return list(zip(best_entraxe, best_ecart))
    coords = []
    radii = []
    for i in range(n):
        point = points[i]
        coords.append((float(point[0]), float(point[1]), float(point[2])))
        radii.append(float(rayons[i]))
    for i in range(n):
        xi, yi, zi = coords[i]
        ri = radii[i]
        for j in range(i + 1, n):
            dx = xi - coords[j][0]
            dy = yi - coords[j][1]
            dz = zi - coords[j][2]
            entraxe = math.sqrt(dx * dx + dy * dy + dz * dz)
            ecart = entraxe - (ri + radii[j])
            if best_entraxe[i] is None or entraxe < best_entraxe[i]:
                best_entraxe[i] = entraxe
                best_ecart[i] = ecart
            if best_entraxe[j] is None or entraxe < best_entraxe[j]:
                best_entraxe[j] = entraxe
                best_ecart[j] = ecart
    return list(zip(best_entraxe, best_ecart))


def face_name(index) -> str:
    """Index tessellation 0-based → nom OCCT ``FaceN`` (1-based)."""
    number = int(index)
    if number < 0:
        raise GemError("face inconnue : {}".format(index))
    return "Face{}".format(number + 1)


def face_index(name) -> int:
    """``Face3`` → 2. Lève ``GemError`` si le nom n'est pas une face."""
    text = "" if name is None else str(name).strip()
    match = _FACE_NAME_RE.fullmatch(text)
    if match is None:
        raise GemError("face d'ancrage illisible : {}".format(name))
    return int(match.group(1)) - 1


def _history_source_name(value) -> str:
    """Nom d'un barreau d'historique : ``Name`` de l'objet, sinon ``str``."""
    name = getattr(value, "Name", None)
    if name:
        return str(name)
    return str(value)


def _is_sketch_source(source) -> bool:
    """True si le barreau est une esquisse, pas une fonction propriétaire."""
    type_id = str(getattr(source, "TypeId", "") or "")
    if "Sketcher" in type_id:
        return True
    return bool(_SKETCH_NAME_RE.fullmatch(_history_source_name(source)))


def trace_pairs(trace):
    """Normalise ``getElementHistory`` en liste de ``(source, nom)``.

    Deux formes coexistent : ``Part::Feature.getElementHistory`` rend une
    **liste de couples**, ``TopoShape.getElementHistory`` un **tuple plat**
    ``(tag, nom, [intermédiaires])``. ``None``, une chaîne d'erreur et une
    liste vide rendent ``[]``.
    """
    if not trace or isinstance(trace, str):
        return []
    if not isinstance(trace, (tuple, list)):
        return []
    first = trace[0]
    if isinstance(first, (tuple, list)):
        out = []
        for entry in trace:
            if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                out.append((_history_source_name(entry[0]), str(entry[1])))
        return out
    if len(trace) >= 2:
        return [(_history_source_name(first), str(trace[1]))]
    return []


def owner_couple(pairs):
    """Le couple à retenir : le barreau le plus profond qui n'est pas une esquisse.

    La généalogie va du plus récent au plus ancien. Le rang 1 est la
    pointe courante, pas forcément le propriétaire de la face — d'où
    la recherche du plus profond, pas d'un rang fixe.
    """
    if not pairs:
        return None
    for source, name in reversed(list(pairs)):
        if not _is_sketch_source(source):
            return (_history_source_name(source), str(name))
    return None


def resolution_verdict(hits):
    """1 → ``'résolu'``, plus d'un → ``'ambigu'``, zéro → ``'perdu'``."""
    n = len(hits) if hits is not None else 0
    if n == 1:
        return "résolu"
    if n > 1:
        return "ambigu"
    return "perdu"


def placement_at(face, u, v, spin=0.0, lift=0.0):
    """Placement d'une pierre : +Z aligné sur la normale de la face.

    ``spin`` en degrés autour de la normale. ``lift`` en mm le long
    de la normale (positif = hors de la matière).
    """
    App = _app()
    origin = face.valueAt(float(u), float(v))
    normal = face.normalAt(float(u), float(v))
    unit = App.Vector(normal)
    if hasattr(unit, "normalize"):
        unit.normalize()
    rot = App.Rotation(App.Vector(0, 0, 1), unit)
    if spin:
        rot = rot.multiply(App.Rotation(App.Vector(0, 0, 1), float(spin)))
    offset = (App.Vector(unit).multiply(float(lift))
              if lift else App.Vector(0, 0, 0))
    return App.Placement(origin + offset, rot)


def matrix_list(placement) -> list:
    return [float(v) for v in placement.Matrix.A]


def build_flat_cylinder(path, diametre=DEFAULT_DIAMETRE, epaisseur=DEFAULT_EPAISSEUR):
    """Écrit le gabarit ``cylindre-plat.FCStd`` : VarSet + esquisse + Pad.

    Construction headless calquée sur la sonde ``build_library`` :
    esquisse sur le plan XY du corps, cotes nommées liées par expression.
    """
    import Part
    import Sketcher

    App = _app()
    diametre = parse_diametre(diametre)
    epaisseur = parse_positive(epaisseur, DEFAULT_EPAISSEUR, "épaisseur")
    path = os.path.abspath(str(path))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    doc = App.newDocument("CylindrePlat")
    try:
        varset = doc.addObject("App::VarSet", "Variables")
        varset.addProperty("App::PropertyFloat", "diametre", "Variables")
        varset.addProperty("App::PropertyFloat", "epaisseur", "Variables")
        varset.diametre = diametre
        varset.epaisseur = epaisseur

        body = doc.addObject("PartDesign::Body", "Corps")
        sketch = doc.addObject("Sketcher::SketchObject", "Profil")
        body.addObject(sketch)
        plane = next(feature for feature in body.Origin.OriginFeatures
                     if getattr(feature, "Role", "") == "XY_Plane")
        try:
            sketch.AttachmentSupport = [(plane, ("",))]
        except AttributeError:
            sketch.Support = [(plane, ("",))]
        sketch.MapMode = "FlatFace"
        doc.recompute()

        gid = sketch.addGeometry(Part.Circle(
            App.Vector(0, 0, 0), App.Vector(0, 0, 1), diametre / 2.0), False)
        sketch.addConstraint(Sketcher.Constraint(
            "Coincident", gid, 3, -1, 1))
        diameter_id = sketch.addConstraint(Sketcher.Constraint(
            "Diameter", gid, diametre))
        sketch.renameConstraint(diameter_id, "diametre")
        sketch.setExpression("Constraints[{}]".format(diameter_id),
                             "Variables.diametre")
        doc.recompute()

        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = epaisseur
        pad.setExpression("Length", "Variables.epaisseur")
        body.Tip = pad
        doc.recompute()

        shape = body.Shape
        if not shape.isValid() or not shape.Solids:
            raise GemError("le gabarit cylindre-plat n'a pas produit de solide")
        doc.saveAs(path)
        return {
            "path": path,
            "octets": os.path.getsize(path),
            "entierement_contrainte": bool(getattr(sketch, "FullyConstrained", False)),
            "solide": True,
            "volume_mm3": float(shape.Volume),
        }
    finally:
        try:
            App.closeDocument(doc.Name)
        except Exception:
            pass


def ensure_flat_cylinder(path=None):
    """Retourne le chemin du gabarit, en le construisant s'il manque."""
    target = path or library_path(DEFAULT_GEMME)
    if os.path.isfile(target):
        return target
    build_flat_cylinder(target)
    return target


def _app():
    import FreeCAD as App
    return App
