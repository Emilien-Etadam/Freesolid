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

#: Noms de gabarit = nom de fichier sous ``assets/gemmes/``, sans extension.
_GEMME_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_FACE_NAME_RE = re.compile(r"^Face(\d+)$")

_SPLINE_TYPE_IDS = frozenset({
    "Part::GeomBSplineSurface",
    "Part::GeomBezierSurface",
})

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIBRARY_DIR = os.path.join(_REPO_ROOT, "assets", "gemmes")


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


def is_bspline_surface(face) -> bool:
    """La face d'ancrage se re-paramétrise si ses pôles bougent."""
    surface = getattr(face, "Surface", None)
    type_id = getattr(surface, "TypeId", "") if surface is not None else ""
    return type_id in _SPLINE_TYPE_IDS


def project_uv(face, x, y, z):
    """Point monde → ``(u, v, sur_domaine)``.

    ``Surface.parameter`` est la seule voie (sonde Q1) : les trois
    méthodes testées rendaient des ``(u, v)`` identiques.
    """
    point = _vector(face, x, y, z)
    u, v = face.Surface.parameter(point)
    on_domain = True
    checker = getattr(face, "isPartOfDomain", None)
    if checker is not None:
        try:
            on_domain = bool(checker(u, v))
        except TypeError:
            on_domain = bool(checker((u, v)))
    return float(u), float(v), on_domain


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


def _vector(face, x, y, z):
    App = _app()
    return App.Vector(float(x), float(y), float(z))
