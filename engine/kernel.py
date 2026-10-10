"""The FreeCAD-headless side of the protocol.

One ``Kernel`` instance owns one document. FreeCAD is imported inside
methods (the module stays importable in CI), and every error surfaces
through ``engine.guard.failure_message`` when a translation exists — the
web UI gets a designer-facing explanation, with the raw text kept
in parentheses when it still helps diagnosis.

Untested-against-FreeCAD code is assumed guilty until the ``selftest`` op
has run on a real install.
"""

import json
import os
import re
import sys

# Make the repo root importable when freecadcmd runs this file from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine import fonts                          # noqa: E402
from engine.guard import (                       # noqa: E402
    failure_message, friendly_error, shell_too_thick_message,
)
from engine.nodegraph import (  # noqa: E402
    GraphError, classify_shape_instructions, evaluate_instances,
    graph_surface_kind, mixed_output_message, migrate_graph, output_nature,
)
from engine.platform import (                    # noqa: E402
    FREECAD, allow_from_environ, freesolid_version, version_status,
)
from engine.plugins import PluginError           # noqa: E402
from engine.protocol import dangling_deps, visible_dep_subs, visible_deps  # noqa: E402
from engine.scriptnode import evaluate as evaluate_graph  # noqa: E402
from engine.i18n import label as _label_in       # noqa: E402
from engine.vocab import label_for_type          # noqa: E402


from engine.drawing import DrawingMixin
from engine.selftest import SelftestMixin
from engine.text import TextMixin
from engine.assembly import AssemblyMixin
from engine.surfacefeat import SurfaceMixin
from engine.graphfeat import GraphMixin
from engine.files import FilesMixin


class KernelError(Exception):
    """Operation failed; message is designer-facing when translatable."""


_BODY_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_body_color(color):
    """Valide une couleur d'affichage.

    ``None`` / ``""`` reviennent au défaut. Sinon ``#rrggbb``.
    """
    if color is None or color == "":
        return ""
    if not isinstance(color, str) or _BODY_COLOR_RE.fullmatch(color) is None:
        raise KernelError(
            "couleur invalide « {} » — attendu #rrggbb".format(color))
    return color


#: Seuil « face orientée vers le haut » : ``normal.z`` au-delà duquel
#: une face est candidate au sommet. Lu par ``Kernel._top_face_id`` et
#: par la garde d'attache de ``engine.replay`` — une seule valeur, sinon
#: la garde cesse de décrire le choix qu'elle est censée vérifier.
UPWARD_Z = 0.5


_NEUTRAL_PLANES = frozenset({"XY", "XZ", "YZ"})


def parse_neutral_plane(neutral="XY"):
    """Valide le plan neutre d'une dépouille (XY / XZ / YZ)."""
    key = str(neutral).upper()
    if key not in _NEUTRAL_PLANES:
        raise KernelError("plan neutre inconnu : {}".format(neutral))
    return key


def resolve_pattern_originals(names, catalog):
    """Valide la liste ``features`` d'une répétition / symétrie.

    *names* : noms demandés, dans l'ordre. *catalog* : ``{nom: {in_body,
    is_addsub, label}}``. Retour : noms uniques, ordre conservé.

    Fonction pure — le catalogue est fourni par l'appelant (le kernel
    le construit depuis le corps actif ; les tests unitaires le fabriquent).
    """
    if not isinstance(names, (list, tuple)):
        raise KernelError("features doit être une liste de noms")
    if len(names) == 0:
        raise KernelError("aucune fonction à répéter — la liste features "
                          "est vide")
    ordered = []
    seen = set()
    for raw in names:
        if not isinstance(raw, str) or not raw.strip():
            raise KernelError("fonction inconnue : {}".format(raw))
        name = raw.strip()
        entry = catalog.get(name)
        if entry is None:
            raise KernelError("fonction inconnue : {}".format(name))
        label = entry.get("label") or name
        if not entry.get("in_body"):
            raise KernelError(
                "{} n'appartient pas au corps actif".format(label))
        if not entry.get("is_addsub"):
            raise KernelError(
                "{} n'est pas une fonction additive ou soustractive — "
                "une répétition porte sur un bossage ou un enlèvement "
                "de matière".format(label))
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


#: Lignes hors chaîne PartDesign — flag ``FreeSolidRolledBack``.
_ROLLBACK_KINDS = frozenset({"sketch", "surface"})

#: Propriété custom persistée dans le .FCStd (source de vérité du recul).
_ROLLED_BACK_PROP = "FreeSolidRolledBack"


def rollback_plan(history, target_name=None):
    """Calcule les flags de recul et le Tip à partir des lignes d'historique.

    *history* : séquence de dicts ``{name, order, kind}`` déjà triée par
    ``order``, avec ``kind`` ∈ ``{"feature", "sketch", "surface"}``.
    *target_name* : dernière ligne visible, ou ``None`` (barre en tête).

    Retour : ``(flags, tip)`` — ``flags`` mappe chaque nom sketch/surface
    vers un booléen reculé ; ``tip`` est le nom de la dernière fonction
    volumique visible, ou ``None``.
    """
    if target_name is None:
        flags = {row["name"]: True
                 for row in history
                 if row["kind"] in _ROLLBACK_KINDS}
        return flags, None
    target_order = None
    for row in history:
        if row["name"] == target_name:
            target_order = row["order"]
            break
    if target_order is None:
        raise KernelError(
            "« {} » n'est pas une ligne d'historique — la barre de "
            "retour se pose sur une fonction, une esquisse libre ou "
            "une surface".format(target_name))
    flags = {}
    tip = None
    for row in history:
        if row["kind"] in _ROLLBACK_KINDS:
            flags[row["name"]] = row["order"] > target_order
        elif row["kind"] == "feature" and row["order"] <= target_order:
            tip = row["name"]
    return flags, tip


def _explain(exc) -> str:
    text = str(exc)
    return friendly_error(text) or text


def weighted_center_of_mass(contributions):
    """Centre de gravité pondéré — contributions ``(masse, (x, y, z))``.

    Fonction pure (sans FreeCAD) pour les solides d'un compound.
    """
    total = 0.0
    cx = cy = cz = 0.0
    for weight, (x, y, z) in contributions:
        weight = float(weight)
        if weight <= 0:
            continue
        total += weight
        cx += float(x) * weight
        cy += float(y) * weight
        cz += float(z) * weight
    if total <= 0:
        return None
    return cx / total, cy / total, cz / total


def _shape_center_of_mass(shape):
    """Centre de gravité d'une forme — les compounds n'ont pas toujours l'attribut."""
    try:
        com = shape.CenterOfMass
        return float(com.x), float(com.y), float(com.z)
    except AttributeError:
        contributions = []
        for solid in shape.Solids:
            volume = float(solid.Volume)
            if volume <= 0:
                continue
            c = solid.CenterOfMass
            contributions.append((volume, (c.x, c.y, c.z)))
        com = weighted_center_of_mass(contributions)
        if com is None:
            raise KernelError("pas de solide à évaluer")
        return com


def selftest_summary(report):
    """Récapitulatif des indicateurs booléens top-niveau d'un rapport.

    Les valeurs non booléennes (étapes, entiers, dicts imbriqués) sont
    ignorées. Retour : ``verifications``, ``ok``, ``echecs`` (noms faux).
    Fonction pure — pas d'import FreeCAD.
    """
    if not isinstance(report, dict):
        report = {}
    echecs = []
    ok = 0
    verifications = 0
    for name, value in report.items():
        if not isinstance(value, bool):
            continue
        verifications += 1
        if value:
            ok += 1
        else:
            echecs.append(name)
    return {
        "verifications": verifications,
        "ok": ok,
        "echecs": echecs,
    }


def parse_user_number(text):
    """« 6,5 » est un nombre (virgule décimale française), pas une équation.

    Retour : float, ou None si le texte n'est pas un nombre — l'appelant
    tente alors le chemin expression. Fonction pure, sans FreeCAD.
    """
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        return None


def _format_mm(value):
    """Cote affichée : virgule française, zéros inutiles retirés."""
    text = "{:.6f}".format(float(value)).rstrip("0").rstrip(".")
    return text.replace(".", ",") or "0"


class Kernel(FilesMixin, GraphMixin, SurfaceMixin, AssemblyMixin, TextMixin, DrawingMixin, SelftestMixin):
    """Owns one FreeCAD document and executes protocol operations."""

    def __init__(self):
        self._doc = None
        self._body = None
        self._assembly = False  # le document courant est un assemblage
        # Langue de l'interface (posée par le serveur à chaque requête) :
        # les libellés que le noyau écrit dans le document la suivent.
        self.lang = "fr"
        # Consentement Python : ce document, cette session. Jamais le .FCStd.
        self._scripts_authorized = False
        # Esquisse ouverte : de quoi l'annuler (sketch_cancel).
        self._sketch_session = None
        self._reset_face_match()
        # Callback d'avancement (phase, fait, total) — posé par le
        # transport, jamais importé d'ici. Absent = no-op.
        self._progress = None
        from engine.plugins import default_registry
        self._plugins = default_registry()
        # État par plugin, pour ce document. Remis à zéro ici et à
        # la fermeture — les deux seuls points du cycle de vie.
        self._plugins.reset_state()

    def _report_progress(self, phase, fait=0, total=0):
        """Nourrit l'état d'avancement. Aucun appel FreeCAD."""
        callback = self._progress
        if not callable(callback):
            return
        try:
            callback(phase, fait, total)
        except Exception:
            pass

    # -- helpers ---------------------------------------------------------

    def _app(self):
        import FreeCAD as App
        return App

    def _user_path(self, path, extensions, must_exist=False):
        """Jail des chemins client — voir ``protocol.resolve_user_path``."""
        from . import protocol
        try:
            return protocol.resolve_user_path(
                path, extensions, must_exist=must_exist)
        except protocol.ProtocolError as exc:
            raise KernelError(str(exc))

    def _user_expression(self, text):
        """Allowlist d'expressions client — voir ``protocol.validate_expression``."""
        from . import protocol
        try:
            return protocol.validate_expression(text)
        except protocol.ProtocolError as exc:
            raise KernelError(str(exc))

    def _require_doc(self):
        if self._doc is None:
            raise KernelError(
                "aucune pièce ouverte — commencez par new_part")
        return self._doc

    def _require_body(self):
        self._require_doc()
        if self._body is None:
            raise KernelError("aucun corps — commencez par new_part")
        return self._body

    def _recompute(self):
        doc = self._require_doc()
        self._sync_revolution_axes()
        doc.recompute()
        if not self._assembly:
            self._report_progress("Reconstruction de l'arbre")
            self._plugins.run_after_recompute(self)
            doc.recompute()
        broken = [o for o in doc.Objects
                  if "Invalid" in (o.State or ())
                  and not self._is_internal_tool(o)
                  and not self._plugins.run_tolerates_invalid(self, o)]
        if broken:
            raise KernelError(" ; ".join(
                self._broken_message(obj) for obj in broken))

    def _drop_failed_feature(self, body, doc, feature, previous_tip):
        """Retire une fonction refusée et rend la pointe au solide d'avant.

        ``newObject`` a déjà fait de la fonction la pointe. La supprimer
        sans la rendre laisse le corps sans solide.
        """
        if getattr(body, "Tip", None) is feature or body.Tip is None:
            body.Tip = previous_tip
        doc.removeObject(feature.Name)

    def _broken_message(self, obj) -> str:
        """Ligne d'erreur d'une fonction invalide.

        Phrase utile selon la fonction quand on la connaît, texte brut
        entre parenthèses. Sinon le texte brut, ou « en erreur ».
        """
        text = ""
        try:
            text = obj.getStatusString() or ""
        except Exception:
            pass
        explained = failure_message(
            getattr(obj, "Label", "") or "",
            text,
            getattr(obj, "TypeId", "") or "",
        )
        if explained:
            return explained
        return "{} : {}".format(obj.Label, text or "en erreur")

    def _force_recompute(self):
        """Recalcul complet, drapeaux « à jour » ignorés."""
        doc = self._require_doc()
        try:
            doc.recompute(None, True, True)
        except TypeError:
            try:
                doc.recompute([], True)
            except TypeError:
                doc.recompute()

    def rebuild(self):
        """Forcer le recalcul de tout l'arbre — dernier recours.

        Tout ce qui est cassé remonte : une fonction qui refuse de se
        reconstruire affiche son message, c'est précisément ce qu'on
        cherche en appuyant sur Reconstruire.
        """
        self._require_doc()
        try:
            self._force_recompute()
            if not self._assembly:
                self._plugins.run_after_recompute(self)
                self._force_recompute()
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc)) from exc
        if self._assembly:
            return self.assembly_tree()
        broken = [o for o in self._doc.Objects
                  if "Invalid" in (o.State or ())
                  and not self._is_internal_tool(o)
                  and not self._plugins.run_tolerates_invalid(self, o)]
        messages = [self._broken_message(obj) for obj in broken]
        if messages:
            raise KernelError(" ; ".join(messages))
        return self.get_tree()

    def _reset_face_match(self, faces=0):
        self._face_match = {
            "faces": faces,
            "matched": 0,
            "assigned": 0,
            "hash": 0,
            "same": 0,
            "geo": 0,
            "tip": 0,
            "hash_errors": [],
        }

    def _face_hash(self, face):
        """hashCode OCCT, ou (None, cause) si l'API ne rend rien d'utilisable."""
        hasher = getattr(face, "hashCode", None)
        if not callable(hasher):
            return None, "hashCode absent"
        try:
            return hasher(), None
        except Exception as exc:  # noqa: BLE001 — on compte, on n'avale pas
            return None, type(exc).__name__

    def _face_geo_key(self, face):
        """Empreinte (aire, centre) — distincte pour les faces d'un pavé.

        hashCode et isSame comparent l'identité OCCT. Sur FreeCAD 1.0/1.1
        le Shape du Tip et celui de la fonction sont des copies : les
        hashes ne se recouvrent pas, isSame est faux. L'aire et le centre
        de masse, eux, coïncident (mesuré 6/6 en ~1 ms sur un bossage).
        """
        try:
            com = face.CenterOfMass
            return (round(float(face.Area), 6),
                    round(float(com.x), 4),
                    round(float(com.y), 4),
                    round(float(com.z), 4))
        except Exception:  # noqa: BLE001 — face dégénérée
            return None

    def _face_same(self, left, right):
        try:
            return bool(left.isSame(right))
        except Exception:  # noqa: BLE001 — on tente le repli géométrique
            return False

    def _claim_face(self, unmatched, producer, how, index, name, via):
        if index not in unmatched:
            return False
        producer[index] = name
        how[index] = via
        unmatched.remove(index)
        return True

    def _face_producers(self):
        """Index de face du Tip → nom de la fonction qui l'a introduite.

        Appariement, dans l'ordre : hash OCCT, ``isSame``, empreinte
        (aire + centre). La première fonction de l'historique qui
        porte la face est celle qui l'a produite. Faces restantes :
        le Tip — et le compte ``_face_match`` le dit.
        """
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        faces = list(getattr(shape, "Faces", None) or ())
        self._reset_face_match(len(faces))
        if not faces:
            return {}
        hash_errors = []
        tip_geo = []
        hash_index = {}
        for index, face in enumerate(faces):
            digest, err = self._face_hash(face)
            if err:
                hash_errors.append(err)
            if digest is not None:
                hash_index[digest] = index
            tip_geo.append(self._face_geo_key(face))

        unmatched = set(range(len(faces)))
        producer = {}
        how = {}
        skip = {
            "Sketcher::SketchObject",
            "PartDesign::Plane",
            "PartDesign::CoordinateSystem",
            "PartDesign::Body",
        }
        for obj in body.Group:
            if obj.TypeId in skip:
                continue
            feat_shape = getattr(obj, "Shape", None)
            if feat_shape is None:
                continue
            try:
                if feat_shape.isNull():
                    continue
            except Exception:
                continue
            for feat_face in list(getattr(feat_shape, "Faces", None) or ()):
                digest, err = self._face_hash(feat_face)
                if err:
                    hash_errors.append(err)
                claimed = False
                if digest is not None and digest in hash_index:
                    claimed = self._claim_face(
                        unmatched, producer, how,
                        hash_index[digest], obj.Name, "hash")
                if claimed:
                    continue
                for index in tuple(unmatched):
                    if self._face_same(faces[index], feat_face):
                        self._claim_face(
                            unmatched, producer, how, index, obj.Name, "same")
                        claimed = True
                        break
                if claimed:
                    continue
                key = self._face_geo_key(feat_face)
                if key is None:
                    continue
                for index in tuple(unmatched):
                    if tip_geo[index] == key:
                        self._claim_face(
                            unmatched, producer, how, index, obj.Name, "geo")
                        break
        tip = getattr(body, "Tip", None)
        if tip is not None:
            for index in tuple(unmatched):
                self._claim_face(
                    unmatched, producer, how, index, tip.Name, "tip")
        matched = sum(1 for via in how.values() if via != "tip")
        self._face_match = {
            "faces": len(faces),
            "matched": matched,
            "assigned": len(producer),
            "hash": sum(1 for via in how.values() if via == "hash"),
            "same": sum(1 for via in how.values() if via == "same"),
            "geo": sum(1 for via in how.values() if via == "geo"),
            "tip": sum(1 for via in how.values() if via == "tip"),
            "hash_errors": list(dict.fromkeys(hash_errors))[:5],
        }
        return producer

    # -- operations ------------------------------------------------------

    def _t(self, text):
        """Libellé dans la langue de l'interface (« Esquisse » → « Sketch »)."""
        return _label_in(text, self.lang)

    def ping(self):
        """Identité du moteur — ce que le panneau Paramètres affiche."""
        App = self._app()
        return {
            "freecad": ".".join(str(v) for v in App.Version()[:3]),
            "freecad_reference": FREECAD,
            "freecadcmd": sys.executable or "",
            "freesolid": freesolid_version(),
            "platform": sys.platform,
        }

    def list_plugins(self):
        """Plugins chargés : nom et point d'entrée JS. Aucun FreeCAD."""
        from engine.plugins import client_plugins
        return client_plugins(self._plugins)

    def _close_current(self):
        """Drop the engine's previous document, if any.

        A lingering document keeps recomputing in the background and its
        warnings land in the terminal attributed to a part the user thinks
        is gone — one document per engine, by construction.
        """
        if self._doc is not None:
            try:
                self._app().closeDocument(self._doc.Name)
            except Exception:
                pass
        self._doc = self._body = None
        self._assembly = False
        self._scripts_authorized = False
        self._plugins.reset_state()

    def _setup_doc(self, doc):
        """Active l'undo et borne la pile (mémoire en longue session).

        FreeCAD 1.0.x n'expose pas ``UndoLimit`` / ``setMaxUndoStackSize``
        en Python — la pile C++ est déjà bornée (défaut 20). Sur les
        versions qui exposent l'API, on fixe 80.
        """
        doc.UndoMode = 1
        if hasattr(doc, "UndoLimit"):
            doc.UndoLimit = 80
        elif hasattr(doc, "setMaxUndoStackSize"):
            doc.setMaxUndoStackSize(80)

    def _undo_limit(self, doc):
        """Limite undo effective, ou None si l'API Python est absente."""
        if hasattr(doc, "UndoLimit"):
            return doc.UndoLimit
        if hasattr(doc, "getMaxUndoStackSize"):
            return doc.getMaxUndoStackSize()
        return None

    def new_part(self, name=None):
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolid")
        self._setup_doc(self._doc)
        self._body = self._doc.addObject("PartDesign::Body", "Body")
        self._body.Label = name or self._t("Pièce")
        self._recompute()
        return self.get_tree()

    # -- phase E : évaluer ------------------------------------------------

    def mass_properties(self, density=1.24):
        """Volume, masse (densité en g/cm³ — PLA par défaut), surface,
        centre de gravité, encombrement — l'onglet Évaluer."""
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None:
            raise KernelError("pas de solide à évaluer")
        try:
            solids = shape.Solids
        except Exception:  # noqa: BLE001 — forme OCCT inaccessible
            solids = []
        if not solids:
            raise KernelError("pas de solide à évaluer")
        try:
            volume = float(shape.Volume)  # mm³ — s'additionne sur un compound
            area = float(shape.Area)
            com_x, com_y, com_z = _shape_center_of_mass(shape)
            box = shape.BoundBox
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc)) from exc
        return {
            "volume_mm3": volume,
            "area_mm2": area,
            "density": float(density),
            "mass_g": volume / 1000.0 * float(density),
            "center_of_mass": [com_x, com_y, com_z],
            "bounding_box": [box.XLength, box.YLength, box.ZLength],
        }

    def measure(self, a_kind, a_id, b_kind, b_id):
        """Distance minimale entre deux éléments (faces ou arêtes)."""
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None:
            raise KernelError("pas de forme à mesurer")

        def sub(kind, index):
            if kind == "face":
                sequence = shape.Faces
            elif kind == "edge":
                sequence = shape.Edges
            else:
                raise KernelError(
                    "élément inconnu « {} » — face ou edge".format(kind))
            index = int(index)
            if index < 0 or index >= len(sequence):
                raise KernelError("{} {} inexistant".format(kind, index))
            return sequence[index]

        first = sub(str(a_kind), a_id)
        second = sub(str(b_kind), b_id)
        try:
            distance = float(first.distToShape(second)[0])
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return {"distance": distance}

    # -- phase C : multi-corps -------------------------------------------

    def add_body(self, name=None):
        """Nouveau corps dans la pièce — il devient le corps actif.

        SolidWorks: un corps par fonction séparée; FreeCAD: un Body
        explicite. Les fonctions suivantes s'empilent dans ce corps.
        """
        doc = self._require_doc()
        body = doc.addObject("PartDesign::Body", "Body")
        body.Label = str(name).strip() if name else self._t("Corps")
        self._body = body
        doc.recompute()
        return self.get_tree()

    def set_active_body(self, body):
        """Changer de corps actif — les fonctions s'appliquent à lui."""
        doc = self._require_doc()
        obj = doc.getObject(str(body))
        if obj is None or obj.TypeId != "PartDesign::Body":
            raise KernelError("corps inconnu : {}".format(body))
        self._body = obj
        return self.get_tree()

    def set_body_color(self, body, color):
        """Couleur d'affichage d'un corps, persistée dans le .FCStd.

        Headless : pas de ViewObject. Propriété custom ``FreeSolidColor``.
        ``color`` = ``#rrggbb``, ou ``None`` / ``""`` pour le défaut.
        """
        doc = self._require_doc()
        obj = doc.getObject(str(body))
        if obj is None or obj.TypeId != "PartDesign::Body":
            raise KernelError("corps inconnu : {}".format(body))
        value = parse_body_color(color)
        if "FreeSolidColor" not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", "FreeSolidColor",
                            "FreeSolid", "Couleur d'affichage")
        obj.FreeSolidColor = value
        return self.get_tree()

    def add_boolean(self, tool, type="cut"):
        """Combiner deux corps — Soustraire / Ajouter / Intersection.

        S'applique au corps actif. Un ``PartDesign::Body`` outil est
        absorbé (comportement PartDesign). Un semis de pierres n'est
        pas absorbé : le corps outil est dérivé, le compound se relit
        depuis ``PlacementList`` à chaque recompute.
        """
        body = self._require_body()
        doc = self._require_doc()
        tool_obj = doc.getObject(str(tool))
        derived_names = []
        hooked = self._plugins.run_boolean_tool(self, tool_obj)
        if hooked is not None:
            tool_obj = hooked
            derived_names.append(tool_obj.Name)
            base = getattr(tool_obj, "BaseFeature", None)
            if base is not None:
                derived_names.append(base.Name)
        elif tool_obj is None or tool_obj.TypeId != "PartDesign::Body":
            raise KernelError("corps outil inconnu : {}".format(tool))
        if tool_obj is body:
            raise KernelError(
                "un corps ne se combine pas avec lui-même — choisissez "
                "un autre corps outil")
        types = {"cut": "Cut", "fuse": "Fuse", "common": "Common"}
        labels = {"cut": self._t("Combiner — Soustraire"),
                  "fuse": self._t("Combiner — Ajouter"),
                  "common": self._t("Combiner — Intersection")}
        boolean_type = types.get(str(type))
        if boolean_type is None:
            raise KernelError(
                "opération inconnue « {} » — attendu cut, fuse ou "
                "common".format(type))
        feature = body.newObject("PartDesign::Boolean", "Boolean")
        feature.Type = boolean_type
        # L'API d'ajout du corps outil a changé selon les versions.
        try:
            feature.addObjects([tool_obj])
        except AttributeError:
            try:
                feature.addObject(tool_obj)
            except AttributeError:
                feature.Group = [tool_obj]
        feature.Label = labels[str(type)]
        boolean_phases = {
            "cut": "Soustraire",
            "fuse": "Ajouter",
            "common": "Intersection",
        }
        self._report_progress(boolean_phases[str(type)])
        try:
            self._recompute()
        except KernelError:
            try:
                doc.removeObject(feature.Name)
            except Exception:
                pass
            for name in derived_names:
                try:
                    doc.removeObject(name)
                except Exception:
                    pass
            raise
        return self.get_tree()

    def _current_tree(self):
        """Part tree or assembly tree, whichever mode the document is in."""
        return self.assembly_tree() if self._assembly else self.get_tree()

    def undo(self):
        """Annuler la dernière opération — une transaction par op UI."""
        doc = self._require_doc()
        if not doc.UndoNames:
            raise KernelError("rien à annuler")
        doc.undo()
        doc.recompute()
        return self._current_tree()

    def redo(self):
        doc = self._require_doc()
        if not doc.RedoNames:
            raise KernelError("rien à rétablir")
        doc.redo()
        doc.recompute()
        return self._current_tree()

    _PLANE_ROLES = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}

    def _origin_feature_or_none(self, role):
        """``_origin_feature`` sans lever — pour l'arbre, où un plan
        introuvable ne doit pas faire échouer tout le payload."""
        try:
            return self._origin_feature(role)
        except KernelError:
            return None

    def _origin_feature(self, role):
        """One of the body's origin planes/axes, by role (XY_Plane, Z_Axis…)."""
        body = self._require_body()
        origin = getattr(body, "Origin", None)
        features = getattr(origin, "OriginFeatures", None) or ()
        for feature in features:
            if getattr(feature, "Role", "") == role:
                return feature
        raise KernelError("élément d'origine introuvable : {}".format(role))

    def _attach_to_support(self, sketch, support):
        try:
            sketch.AttachmentSupport = support
        except AttributeError:
            sketch.Support = support
        sketch.MapMode = "FlatFace"

    def _attach_to_face(self, sketch, face_id):
        """Map a sketch flat onto one of the current shape's faces.

        ``face_id`` is the tessellation index, so ``Face{id+1}`` on the Tip
        feature — the same numbering the viewport picked. The attachment
        property was renamed in 1.x, hence the two spellings.
        """
        body = self._require_body()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas encore de solide pour accueillir "
                              "une esquisse sur face")
        self._attach_to_support(
            sketch, [(tip, ("Face{}".format(int(face_id) + 1),))])

    def add_rect_sketch(self, width, height, face=None):
        """Centered, fully-constrained rectangle.

        On the XY plane by default; with ``face`` (a picked face id), mapped
        flat onto that face — the SolidWorks "click a face, sketch on it"
        gesture. Anchored by symmetry about the sketch origin, driven by
        DistanceX/DistanceY; the interactive part is M2's job.
        """
        import Part
        import Sketcher
        body = self._require_body()
        doc = self._require_doc()
        w, h = float(width), float(height)
        if w <= 0 or h <= 0:
            raise KernelError("largeur et hauteur doivent être positives")

        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = self._t("Esquisse")
        if face is not None:
            self._attach_to_face(sketch, face)
        else:
            # Plan XY d'origine : la docstring le promettait déjà, mais
            # sans AttachmentSupport l'esquisse n'avait pas d'arête dans
            # le graphe. Même geste que ``sketch_start(plane="XY")``.
            self._attach_to_support(
                sketch, [(self._origin_feature(self._PLANE_ROLES["XY"]),
                          ("",))])

        V = self._app().Vector
        x, y = w / 2.0, h / 2.0
        corners = [V(-x, -y, 0), V(x, -y, 0), V(x, y, 0), V(-x, y, 0)]
        for i in range(4):
            sketch.addGeometry(
                Part.LineSegment(corners[i], corners[(i + 1) % 4]), False)

        C = Sketcher.Constraint
        for i in range(4):
            sketch.addConstraint(C("Coincident", i, 2, (i + 1) % 4, 1))
        sketch.addConstraint(C("Horizontal", 0))
        sketch.addConstraint(C("Horizontal", 2))
        sketch.addConstraint(C("Vertical", 1))
        sketch.addConstraint(C("Vertical", 3))
        # Symmetry about the origin point pins the rectangle in space.
        sketch.addConstraint(C("Symmetric", 0, 1, 2, 1, -1, 1))
        sketch.addConstraint(C("DistanceX", 0, 1, 0, 2, w))
        sketch.addConstraint(C("DistanceY", 1, 1, 1, 2, h))

        self._recompute()
        return self.get_tree()

    def add_pad(self, length=None, sketch=None, reversed=False,
                midplane=False, thin=None, **conditions):
        """Extrusion. ``conditions`` : voir ``engine.extrude`` —
        cond, face, offset, taper, cond2, length2, face2, offset2, taper2.
        ``thin`` : paroi mince, voir ``engine.extrude.thin_settings``."""
        body = self._require_body()
        doc = self._require_doc()
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            profile = self._latest_sketch()
        tip = body.Tip  # les faces visées appartiennent à l'état d'avant
        spec, helpers = self._thin_profile(body, profile, thin)
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = helpers[-1] if helpers else profile
        try:
            self._apply_extrude(pad, "pad", tip, length=length,
                                reversed=reversed, midplane=midplane,
                                **conditions)
            pad.Label = self._t("Extrusion")
            if spec is not None:
                self._mark_thin(pad, spec)
                self._own_thin_helpers(pad, helpers)
                if spec["caps"]:
                    helpers += self._thin_cavity(body, pad, profile, spec)
            self._recompute()
        except KernelError:
            self._remove_all([pad] + helpers)
            raise
        return self.get_tree()

    #: Objets d'une paroi mince : hors arbre, ils suivent leur fonction
    #: (``FreeSolidThinOwner`` = son nom ; une chaîne, pas un lien — un lien
    #: de la fonction vers sa cavité, placée après elle, ferait un cycle).
    _THIN_HELPER = "FreeSolidThinHelper"

    def _is_thin_helper(self, obj):
        return bool(getattr(obj, self._THIN_HELPER, False))

    def _new_thin_helper(self, body, type_id, name, label):
        obj = body.newObject(type_id, name)
        obj.addProperty("App::PropertyBool", self._THIN_HELPER,
                        "FreeSolid", "Objet de paroi mince")
        setattr(obj, self._THIN_HELPER, True)
        obj.Label = self._t(label)
        return obj

    def _new_thin_binder(self, body, source, offset, fill, label):
        binder = self._new_thin_helper(
            body, "PartDesign::SubShapeBinder", "ThinProfile", label)
        try:
            binder.Support = [(source, ("",))]
        except TypeError:
            binder.Support = (source, [""])
        binder.OffsetJoinType = "Intersection"  # coins vifs
        binder.OffsetOpenResult = True  # profil ouvert : un côté
        binder.OffsetFill = fill
        binder.Offset = offset
        binder.Visibility = False
        return binder

    def _own_thin_helpers(self, feature, helpers):
        for helper in helpers:
            if "FreeSolidThinOwner" not in helper.PropertiesList:
                helper.addProperty("App::PropertyString",
                                   "FreeSolidThinOwner", "FreeSolid",
                                   "Fonction de cette paroi mince")
            helper.FreeSolidThinOwner = feature.Name

    def _thin_profile(self, body, profile, thin):
        """Paroi mince : le profil devient une bande d'épaisseur constante.

        Un ou deux ``SubShapeBinder`` décalés (objets natifs, recalculés
        quand l'esquisse change) tiennent la bande dans le corps ; la
        fonction l'extrude comme n'importe quel profil, avec toutes ses
        conditions de fin. Extrémités fermées : le profil est le contour
        extérieur plein, la cavité vient après (``_thin_cavity``).
        Renvoie ``(spec, liants)`` — ``(None, [])`` sans paroi mince.
        """
        if not thin:
            return None, []
        from engine.extrude import (
            ExtrudeError, thin_cap_offsets, thin_offsets, thin_settings)
        if not isinstance(thin, dict):
            raise KernelError("paroi mince : objet attendu")
        try:
            spec = thin_settings(**thin)
        except (ExtrudeError, TypeError, ValueError) as exc:
            raise KernelError(str(exc))
        if spec["caps"]:
            profile.recompute()   # une esquisse tout juste tracée
            wires = getattr(profile.Shape, "Wires", None) or []
            if not wires or not all(w.isClosed() for w in wires):
                raise KernelError(
                    "extrémités fermées : le profil doit être fermé")
            steps = [(thin_cap_offsets(spec)[0], False)]
        else:
            steps = thin_offsets(spec)
        doc = self._require_doc()
        helpers = []
        source = profile
        try:
            for offset, fill in steps:
                source = self._new_thin_binder(
                    body, source, offset, fill, "Profil de paroi mince")
                helpers.append(source)
            doc.recompute()
        except Exception as exc:  # noqa: BLE001
            self._remove_all(helpers)
            raise KernelError(_explain(exc))
        return spec, helpers

    def _thin_cavity(self, body, feature, profile, spec):
        """Extrémités fermées : la cavité, un enlèvement caché entre les
        deux bouts, dont les profondeurs suivent la fonction."""
        from engine.extrude import ExtrudeError, cavity_plan, thin_cap_offsets
        side = str(getattr(feature, "SideType", "One side"))
        borgne = (feature.Type == "Length"
                  and (side != "Two sides" or feature.Type2 == "Length"))
        tapered = any(abs(float(getattr(feature, prop, 0) or 0)) > 1e-9
                      for prop in ("TaperAngle", "TaperAngle2"))
        if not borgne or tapered:
            raise KernelError(
                "extrémités fermées : profondeur borgne, sans dépouille")
        try:
            self._check_cavity(feature)
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        helpers = []
        try:
            binder = self._new_thin_binder(
                body, profile, thin_cap_offsets(spec)[1], False,
                "Profil de paroi mince")
            helpers.append(binder)
            cavity = self._new_thin_helper(
                body, "PartDesign::Pocket", "ThinCavity",
                "Cavité de paroi mince")
            helpers.append(cavity)
            self._own_thin_helpers(feature, helpers)
            cavity.Profile = binder
            plan = cavity_plan(side, feature.Name)
            cavity.SideType = plan.pop("SideType")
            # L'enlèvement part à l'opposé de l'extrusion.
            cavity.Reversed = not feature.Reversed
            for prop, expr in plan.items():
                cavity.setExpression(prop, expr)
        except Exception as exc:  # noqa: BLE001
            self._remove_all(helpers)
            raise KernelError(_explain(exc))
        return helpers

    def _check_cavity(self, feature):
        from engine.extrude import check_cavity
        def mm(prop):
            value = getattr(feature, prop, 0.0)
            return float(getattr(value, "Value", value))
        check_cavity(str(getattr(feature, "SideType", "One side")),
                     mm("Length"), mm("Length2"), mm("CapThickness"))

    def _mark_thin(self, feature, spec):
        """Épaisseurs sur la fonction : rééditables par ``set_params``."""
        props = [("FreeSolidThinType", "App::PropertyString"),
                 ("FreeSolidThinReversed", "App::PropertyBool"),
                 ("Thickness", "App::PropertyLength")]
        if spec["type"] == "deux":
            props.append(("Thickness2", "App::PropertyLength"))
        if spec["caps"]:
            props.append(("CapThickness", "App::PropertyLength"))
        for prop, prop_type in props:
            if prop not in feature.PropertiesList:
                feature.addProperty(prop_type, prop, "FreeSolid",
                                    "Paroi mince")
        feature.FreeSolidThinType = spec["type"]
        feature.FreeSolidThinReversed = spec["reversed"]
        feature.Thickness = spec["thickness"]
        if spec["type"] == "deux":
            feature.Thickness2 = spec["thickness2"]
        if spec["caps"]:
            feature.CapThickness = spec["caps"]

    def _thin_spec(self, obj):
        """Paroi mince d'une fonction (dict de ``thin_settings``) ou None."""
        kind = getattr(obj, "FreeSolidThinType", "")
        if not kind:
            return None
        def mm(prop):
            value = getattr(obj, prop, 0.0)
            return float(getattr(value, "Value", value))
        return {"type": kind, "thickness": mm("Thickness"),
                "thickness2": mm("Thickness2") if kind == "deux" else 0.0,
                "reversed": bool(getattr(obj, "FreeSolidThinReversed",
                                         False)),
                "caps": mm("CapThickness")}

    def _thin_chain(self, obj):
        """Liants de paroi mince d'une fonction (du premier au dernier) et
        l'esquisse source : ``([], None)`` pour une fonction pleine."""
        profile = getattr(obj, "Profile", None)
        linked = profile[0] if isinstance(profile, tuple) else profile
        chain = []
        while linked is not None and self._is_thin_helper(linked):
            chain.insert(0, linked)
            support = getattr(linked, "Support", None) or []
            linked = support[0][0] if support else None
        return chain, (linked if chain else None)

    def _thin_helpers(self, obj):
        """Tous les objets cachés d'une paroi mince, dans l'ordre du corps."""
        chain, _ = self._thin_chain(obj)
        group = getattr(obj.getParentGeoFeatureGroup(), "Group", None) or []
        return [o for o in group
                if o in chain or getattr(o, "FreeSolidThinOwner", "") == obj.Name]

    def _thin_owner(self, obj):
        """La fonction d'un objet caché de paroi mince, sinon l'objet."""
        owner = getattr(obj, "FreeSolidThinOwner", "") if obj else ""
        found = self._doc.getObject(owner) if owner else None
        return found or obj

    def _tip_with_helpers(self, obj):
        """Barre de retour sur une fonction : après sa cavité éventuelle."""
        features = [h for h in self._thin_helpers(obj)
                    if h.isDerivedFrom("PartDesign::Feature")]
        return features[-1] if features else obj

    def _sync_thin(self, obj):
        """Recopie les épaisseurs de la fonction dans ses liants."""
        from engine.extrude import (
            ExtrudeError, thin_cap_offsets, thin_offsets, thin_settings)
        spec = self._thin_spec(obj)
        chain, _ = self._thin_chain(obj)
        if spec is None or not chain:
            return
        try:
            spec = thin_settings(**spec)
            if spec["caps"]:
                self._check_cavity(obj)
                outer, inner = thin_cap_offsets(spec)
                binders = [h for h in self._thin_helpers(obj)
                           if h.TypeId == "PartDesign::SubShapeBinder"]
                steps = [(outer, False), (inner, False)]
                chain = binders
            else:
                steps = thin_offsets(spec)
        except ExtrudeError as exc:
            raise KernelError(str(exc))
        if len(steps) != len(chain):
            raise KernelError("paroi mince incomplète : profil décalé absent")
        for binder, (offset, fill) in zip(chain, steps):
            binder.OffsetFill = fill
            binder.Offset = offset

    def _remove_all(self, objects):
        doc = self._require_doc()
        for obj in reversed(objects):
            try:
                doc.removeObject(obj.Name)
            except Exception:
                pass

    def _apply_extrude(self, obj, kind, tip, **params):
        """Pose les propriétés calculées par ``engine.extrude``."""
        from engine.extrude import ExtrudeError, extrude_settings
        try:
            props = extrude_settings(kind, **params)
        except (ExtrudeError, TypeError, ValueError) as exc:
            raise KernelError(str(exc))
        side = props.pop("SideType")
        if "SideType" in obj.PropertiesList:
            obj.SideType = side
        elif side == "Symmetric":
            obj.Midplane = True          # FreeCAD 1.0 : pas de SideType
        elif side == "Two sides":
            raise KernelError(
                "deuxième direction : FreeCAD {} requis".format("1.1"))
        for name, value in props.items():
            if name.startswith("UpToFace"):
                if tip is None:
                    raise KernelError(
                        "jusqu'à la face : la pièce n'a pas encore de face")
                value = (tip, ["Face{}".format(int(value) + 1)])
            setattr(obj, name, value)

    def reorder_feature(self, feature, target, after=False):
        """Déplacer une fonction (avec ses esquisses) avant ou après une
        autre, par glisser-déposer dans l'arbre. Refusé si l'arbre ne se
        reconstruit plus (une fonction viendrait avant ce dont elle
        dépend) : la transaction est alors annulée."""
        body = self._require_body()
        doc = self._require_doc()
        moved = doc.getObject(str(feature))
        anchor = doc.getObject(str(target))
        members = list(body.Group)
        if moved not in members or anchor not in members:
            raise KernelError("réordonner : fonction inconnue dans ce corps")
        if moved is anchor:
            return self.get_tree()
        consumed = self._consumed_sketches()
        # La fonction voyage avec ses esquisses ; « avant » une fonction,
        # c'est avant ses esquisses à elle aussi.
        # Une paroi mince fermée a sa cavité *après* elle : le groupe garde
        # l'ordre du corps, et « après » une fonction, c'est après sa cavité.
        group = [o for o in members if consumed.get(o.Name) == moved.Name
                 or o is moved]
        if anchor in group:
            return self.get_tree()
        anchor_group = [o for o in members
                        if consumed.get(o.Name) == anchor.Name or o is anchor]
        anchor = anchor_group[-1] if after else anchor_group[0]
        tip_at_end = body.Tip is not None and body.Tip is self._last_body_feature()
        for obj in group:
            body.removeObject(obj)
        if after:
            for obj in reversed(group):
                body.insertObject(obj, anchor, True)
        else:
            for obj in group:
                body.insertObject(obj, anchor, False)
        if tip_at_end:
            last = self._last_body_feature()
            if last is not None:
                body.Tip = last
        # Chaque objet doit venir après ce qu'il référence dans le corps
        # (esquisse posée sur une face, habillage sur des arêtes…). Le
        # chaînage BaseFeature, lui, est refait par FreeCAD.
        order = {o.Name: i for i, o in enumerate(body.Group)}
        for obj in body.Group:
            base = getattr(obj, "BaseFeature", None)
            for dep in getattr(obj, "OutList", ()):
                if dep is base or dep.Name not in order:
                    continue
                if order[dep.Name] > order[obj.Name]:
                    raise KernelError(
                        "réordonner : « {} » dépend de « {} », qui viendrait "
                        "après".format(obj.Label, dep.Label))
        doc.recompute()
        broken = [o.Label for o in body.Group if "Invalid" in (o.State or ())]
        if broken:
            raise KernelError(
                "réordonner : l'arbre ne se reconstruit plus ({}) — une "
                "fonction viendrait avant ce dont elle dépend".format(
                    ", ".join(broken)))
        return self.get_tree()

    def _last_body_feature(self):
        """Dernière fonction solide du corps (hors esquisses et plans)."""
        body = self._require_body()
        for obj in reversed(list(body.Group)):
            if obj.isDerivedFrom("PartDesign::Feature"):
                return obj
        return None

    def _consumed_sketches(self):
        """Esquisse → nom du parent (fonction PartDesign ou surface)."""
        body = self._require_body()
        consumed = {}
        for obj in body.Group:
            owner = getattr(obj, "FreeSolidThinOwner", "")
            if owner:
                # Objet caché de paroi mince : il voyage avec sa fonction ;
                # la cavité (un enlèvement) ne consomme pas l'esquisse.
                consumed[obj.Name] = owner
                continue
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            chain, source = self._thin_chain(obj)
            for helper in chain:   # voyagent avec la fonction (réordonner)
                consumed[helper.Name] = obj.Name
            if source is not None:
                linked = source
            if linked is not None:
                consumed[linked.Name] = obj.Name
        for obj in self._doc.Objects:
            if obj.TypeId not in self._SURFACE_TYPE_IDS:
                continue
            for sk in self._surface_sketch_objects(obj):
                consumed.setdefault(sk.Name, obj.Name)
        return consumed

    def _is_rolled_back(self, obj):
        return bool(getattr(obj, _ROLLED_BACK_PROP, False))

    def _set_rolled_back(self, obj, rolled):
        """Pose le flag (source de vérité) et miroir ``Visibility``."""
        rolled = bool(rolled)
        if _ROLLED_BACK_PROP not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", _ROLLED_BACK_PROP,
                            "FreeSolid", "Reculé par la barre de retour")
        setattr(obj, _ROLLED_BACK_PROP, rolled)
        if hasattr(obj, "Visibility"):
            obj.Visibility = not rolled

    def _history_kind(self, obj, consumed):
        """``feature`` / ``sketch`` / ``surface``, ou None si hors historique."""
        if self._is_thin_helper(obj):
            return None
        if obj.TypeId in self._SURFACE_TYPE_IDS:
            return "surface"
        if obj.TypeId == "Sketcher::SketchObject":
            return None if obj.Name in consumed else "sketch"
        if obj.isDerivedFrom("PartDesign::Feature"):
            return "feature"
        return None

    def _history_lines(self):
        """Lignes d'historique top-niveau, triées par index dans le document."""
        doc = self._require_doc()
        body = self._require_body()
        consumed = self._consumed_sketches()
        lines = []
        for obj in body.Group:
            kind = self._history_kind(obj, consumed)
            if kind in ("feature", "sketch"):
                lines.append(obj)
        for obj in doc.Objects:
            if (obj.TypeId in self._SURFACE_TYPE_IDS
                    and not self._is_internal_tool(obj)):
                lines.append(obj)
        order_of = {o.Name: i for i, o in enumerate(doc.Objects)}
        lines.sort(key=lambda o: order_of.get(o.Name, -1))
        return lines

    def _history_rows(self, lines=None):
        doc = self._require_doc()
        consumed = self._consumed_sketches()
        order_of = {o.Name: i for i, o in enumerate(doc.Objects)}
        rows = []
        for obj in (lines if lines is not None else self._history_lines()):
            kind = self._history_kind(obj, consumed)
            if kind is None:
                continue
            rows.append({
                "name": obj.Name,
                "order": order_of.get(obj.Name, -1),
                "kind": kind,
            })
        return rows

    def _apply_rollback_flags(self, flags):
        """Applique ``flags`` (nom → reculé) aux surfaces, esquisses libres
        et esquisses sources des surfaces reculées."""
        doc = self._require_doc()
        for name, rolled in flags.items():
            obj = doc.getObject(name)
            if obj is None:
                continue
            self._set_rolled_back(obj, rolled)
            if obj.TypeId in self._SURFACE_TYPE_IDS:
                for sk in self._surface_sketch_objects(obj):
                    self._set_rolled_back(sk, rolled)

    def _free_sketches(self):
        """Esquisses du corps actif non consommées par une fonction.

        Mêmes candidates que ``_latest_sketch`` : une esquisse dont le
        ``Profile`` d'une fonction pointe dessus est repliée, comme
        SolidWorks la range sous le bossage. Les esquisses reculées par
        la barre de retour sont exclues — on ne référence pas ce qui
        est sous la barre.
        """
        body = self._require_body()
        used = set()
        for obj in body.Group:
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            if linked is not None:
                used.add(linked.Name)
        return [o for o in body.Group
                if o.TypeId == "Sketcher::SketchObject"
                and o.Name not in used
                and not self._is_rolled_back(o)]

    def _latest_sketch(self):
        """The newest sketch not yet consumed by a feature.

        Root cause of the "passage esquisse → extrusion" confusion: reusing
        an already-extruded profile fails downstream with a cryptic error.
        A profile is used once; the next feature takes the next fresh
        sketch, exactly the SolidWorks mental model.
        """
        sketches = self._free_sketches()
        if not sketches:
            raise KernelError(
                "aucune esquisse disponible — les esquisses existantes "
                "sont déjà utilisées par des fonctions, dessinez-en une "
                "nouvelle")
        return sketches[-1]

    def add_pocket(self, length=None, through=False, reversed=False,
                   sketch=None, midplane=False, cond=None, thin=None,
                   **conditions):
        """Cut with the latest sketch — Extruded Cut, in SolidWorks terms.

        No length (or ``through``) means « À travers tout » — the option a
        SolidWorks hand reaches for by default on a cut. ``cond`` and the
        other conditions: see ``engine.extrude``.
        """
        body = self._require_body()
        tip = body.Tip
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        if isinstance(thin, dict) and thin.get("caps"):
            raise KernelError(
                "extrémités fermées : réservées à l'extrusion")
        spec, helpers = self._thin_profile(body, profile, thin)
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = helpers[-1] if helpers else profile
        if cond is None:
            cond = "travers" if (through or length is None) else "borgne"
        try:
            self._apply_extrude(pocket, "pocket", tip, cond=cond,
                                length=length, reversed=reversed,
                                midplane=midplane, **conditions)
        except KernelError:
            self._remove_all([pocket] + helpers)
            raise
        pocket.Label = self._t("Enlèvement extrudé")
        if spec is not None:
            self._mark_thin(pocket, spec)
            self._own_thin_helpers(pocket, helpers)
        try:
            self._recompute()
        except KernelError:
            self._remove_all([pocket] + helpers)
            raise
        return self.get_tree()

    #: Ops the yellow ghost preview may run speculatively.
    _PREVIEWABLE = frozenset({
        "add_pad", "add_pocket", "add_revolution", "add_groove",
        "add_fillet", "add_chamfer", "add_thickness", "add_draft",
        "add_mirror", "add_linear_pattern", "add_polar_pattern",
        "add_hole", "set_params",
        "add_loft", "add_sweep", "add_helix", "add_boolean", "add_text",
    })

    def preview(self, op, params):
        """Aperçu jaune : exécute la fonction, tesselle, puis annule tout.

        The op runs inside its own transaction which is always aborted —
        the document comes back exactly as it was, whatever happened. The
        client renders the returned mesh as the SolidWorks-style ghost.
        """
        doc = self._require_doc()
        if op not in self._PREVIEWABLE:
            raise KernelError(
                "aperçu non disponible pour {}".format(op))
        if not isinstance(params, dict):
            raise KernelError("params doit être un objet JSON")
        doc.openTransaction("freesolid-preview")
        self._previewing = True
        try:
            getattr(self, op)(**params)
            return self.tessellate()
        finally:
            self._previewing = False
            try:
                doc.abortTransaction()
            except Exception:
                pass
            doc.recompute()

    # -- phase B : références et ossature ---------------------------------

    def add_datum_plane(self, base=None, face=None, offset=0.0, angle=0.0):
        """Plan de référence : décalé (et incliné) d'un plan d'origine ou
        d'une face — le prérequis des pièces qui ne s'empilent pas sur
        les trois plans."""
        body = self._require_body()
        doc = self._require_doc()
        App = self._app()
        plane = body.newObject("PartDesign::Plane", "DatumPlane")
        if face is not None:
            tip = getattr(body, "Tip", None)
            if tip is None:
                raise KernelError("pas de solide pour porter ce plan")
            support = [(tip, ("Face{}".format(int(face) + 1),))]
        else:
            role = self._PLANE_ROLES.get(str(base or "XY").upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(base))
            support = [(self._origin_feature(role), ("",))]
        try:
            plane.AttachmentSupport = support
        except AttributeError:
            plane.Support = support
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(
            App.Vector(0, 0, float(offset)),
            App.Rotation(App.Vector(1, 0, 0), float(angle)))
        plane.Label = self._t("Plan de référence")
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(plane.Name)
            raise
        return self.get_tree()

    def add_loft(self, sketches, subtractive=False, ruled=False,
                 closed=False):
        """Lissage (ou enlèvement) entre plusieurs profils —
        typiquement des esquisses posées sur des plans de référence."""
        body = self._require_body()
        doc = self._require_doc()
        if not isinstance(sketches, (list, tuple)) or len(sketches) < 2:
            raise KernelError("un lissage demande au moins deux profils")
        profiles = [self._get_sketch(str(n)) for n in sketches]
        type_id = ("PartDesign::SubtractiveLoft" if subtractive
                   else "PartDesign::AdditiveLoft")
        loft = body.newObject(type_id, type_id.split("::")[-1])
        loft.Profile = profiles[0]
        try:
            loft.Sections = profiles[1:]
        except TypeError:
            loft.Sections = [(p, ("",)) for p in profiles[1:]]
        loft.Ruled = bool(ruled)
        loft.Closed = bool(closed)
        loft.Label = label_for_type(type_id, self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(loft.Name)
            raise
        return self.get_tree()

    def add_sweep(self, profile, spine, subtractive=False):
        """Balayage (ou enlèvement) : un profil suit une
        trajectoire — deux esquisses, souvent sur des plans différents."""
        body = self._require_body()
        doc = self._require_doc()
        section = self._get_sketch(str(profile))
        # La trajectoire : une esquisse OU une courbe 3D (Part::Feature).
        path = doc.getObject(str(spine))
        if (path is None
                or path.TypeId not in ("Sketcher::SketchObject",
                                       "Part::Feature")
                or not getattr(path, "Shape", None)
                or not path.Shape.Edges):
            raise KernelError(
                "trajectoire inconnue : {} (esquisse ou courbe 3D)".format(
                    spine))
        if section.Name == path.Name:
            raise KernelError("profil et trajectoire doivent être "
                              "différents")
        binder = None
        if path.TypeId == "Part::Feature":
            # PartDesign n'accepte que des liens internes au corps
            # (« out of the allowed scope » sinon) : un SubShapeBinder
            # importe la courbe 3D dans le corps.
            binder = body.newObject("PartDesign::SubShapeBinder",
                                    "SpineBinder")
            try:
                binder.Support = [(path, ("",))]
            except TypeError:
                binder.Support = (path, [""])
            binder.Label = self._t("Trajectoire — {}").format(path.Label)
            doc.recompute()
            path = binder
        type_id = ("PartDesign::SubtractivePipe" if subtractive
                   else "PartDesign::AdditivePipe")
        pipe = body.newObject(type_id, type_id.split("::")[-1])
        pipe.Profile = section
        try:
            pipe.Spine = path
        except TypeError:
            pipe.Spine = (path, ("",))
        pipe.Label = label_for_type(type_id, self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pipe.Name)
            if binder is not None:
                try:
                    doc.removeObject(binder.Name)
                except Exception:
                    pass
            raise
        return self.get_tree()

    def add_helix(self, pitch, height, sketch=None):
        """Hélice additive (ressort, filet réel) — le profil tourne autour
        de l'axe vertical de son esquisse, comme la révolution."""
        body = self._require_body()
        doc = self._require_doc()
        if float(pitch) <= 0 or float(height) <= 0:
            raise KernelError("pas et hauteur doivent être positifs")
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        helix = body.newObject("PartDesign::AdditiveHelix", "AdditiveHelix")
        helix.Profile = profile
        helix.ReferenceAxis = (profile, ["V_Axis"])
        helix.Pitch = float(pitch)
        helix.Height = float(height)
        helix.Label = self._t("Hélice")
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(helix.Name)
            raise
        return self.get_tree()

    # -- palier 2 : révolutions, transformations, habillages avancés ------

    _SKETCH_AXES = {"vertical": "V_Axis", "horizontal": "H_Axis"}

    def _revolution_reference(self, profile, axis):
        """Référence d'axe : axe d'esquisse, ligne, ou axe d'origine."""
        token = str(axis or "vertical").strip() or "vertical"
        if token in self._SKETCH_AXES:
            return (profile, [self._SKETCH_AXES[token]])
        if token.upper() in self._AXIS_ROLES:
            return (self._origin_axis(token), [""])
        if token.startswith("line:"):
            try:
                gid = int(token.split(":", 1)[1])
            except ValueError:
                gid = -1
            geometry = list(getattr(profile, "Geometry", []) or [])
            if gid < 0 or gid >= len(geometry):
                raise KernelError("l'axe de révolution doit être une ligne")
            geo = geometry[gid]
            if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
                raise KernelError("l'axe de révolution doit être une ligne")
            # La géométrie de construction n'est pas dans la forme de
            # l'esquisse : une ligne de référence, cachée, la porte.
            if self._is_construction(profile, gid, geo):
                return (self._axis_datum(profile, gid), [""])
            edge = 0
            for index, item in enumerate(geometry):
                if self._is_construction(profile, index, item):
                    continue
                edge += 1
                if index == gid:
                    return (profile, ["Edge{}".format(edge)])
            raise KernelError("l'axe de révolution doit être une ligne")
        raise KernelError(
            "axe de révolution inconnu « {} »".format(token))

    def _axis_datum(self, profile, gid):
        """Ligne de référence cachée, calée sur une ligne de construction."""
        body = self._require_body()
        for obj in body.Group:
            if not getattr(obj, "FreeSolidAxisTool", False):
                continue
            if (getattr(obj, "AxisSketch", None) == profile
                    and int(getattr(obj, "AxisGeo", -1)) == int(gid)):
                self._place_axis_datum(obj, profile, gid)
                return obj
        tip = getattr(body, "Tip", None)
        datum = body.newObject("PartDesign::Line", "AxisLine")
        if "FreeSolidAxisTool" not in datum.PropertiesList:
            datum.addProperty("App::PropertyBool", "FreeSolidAxisTool",
                              "FreeSolid", "Axe interne d'une révolution")
            datum.addProperty("App::PropertyLink", "AxisSketch",
                              "FreeSolid", "Esquisse portée")
            datum.addProperty("App::PropertyInteger", "AxisGeo",
                              "FreeSolid", "Géométrie d'axe")
        datum.FreeSolidAxisTool = True
        datum.AxisSketch = profile
        datum.AxisGeo = int(gid)
        datum.MapMode = "Deactivated"
        try:
            datum.Visibility = False
        except Exception:
            pass
        self._place_axis_datum(datum, profile, gid)
        if tip is not None and getattr(body, "Tip", None) is not tip:
            body.Tip = tip
        return datum

    def _place_axis_datum(self, datum, profile, gid):
        geometry = list(getattr(profile, "Geometry", []) or [])
        if gid < 0 or gid >= len(geometry):
            raise KernelError("l'axe de révolution doit être une ligne")
        geo = geometry[gid]
        if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
            raise KernelError("l'axe de révolution doit être une ligne")
        p1 = profile.Placement.multVec(geo.StartPoint)
        p2 = profile.Placement.multVec(geo.EndPoint)
        direction = p2.sub(p1)
        if float(direction.Length) < 1e-9:
            raise KernelError("l'axe de révolution doit être une ligne")
        app = self._app()
        datum.MapMode = "Deactivated"
        datum.Placement = app.Placement(
            p1, app.Rotation(app.Vector(0, 0, 1), direction))

    def _sync_revolution_axes(self):
        """Recale les axes internes avant le recalcul du solide."""
        doc = getattr(self, "_doc", None)
        if doc is None:
            return
        for obj in list(doc.Objects):
            if not getattr(obj, "FreeSolidAxisTool", False):
                continue
            sketch = getattr(obj, "AxisSketch", None)
            if sketch is None:
                continue
            self._place_axis_datum(obj, sketch, int(getattr(obj, "AxisGeo", -1)))

    def _drop_unused_axis_tools(self):
        doc = self._require_doc()
        used = set()
        for obj in doc.Objects:
            ref = getattr(obj, "ReferenceAxis", None)
            try:
                target = ref[0]
            except Exception:
                continue
            if getattr(target, "FreeSolidAxisTool", False):
                used.add(target.Name)
        for obj in list(doc.Objects):
            if getattr(obj, "FreeSolidAxisTool", False) and obj.Name not in used:
                try:
                    doc.removeObject(obj.Name)
                except Exception:
                    pass

    @staticmethod
    def _as_object(link):
        """Lien simple ou sous-lien ``(objet, [sous])`` → l'objet."""
        if isinstance(link, (list, tuple)) and link:
            return link[0]
        return link

    def _revolution_axis_token(self, obj):
        """Jeton d'axe relu sur la fonction (vertical par défaut)."""
        profile = self._as_object(getattr(obj, "Profile", None))
        ref = getattr(obj, "ReferenceAxis", None)
        try:
            target, subs = ref[0], ref[1]
        except Exception:
            return "vertical"
        sub = ""
        try:
            sub = str(list(subs)[0]) if subs else ""
        except Exception:
            sub = ""
        profile_name = getattr(profile, "Name", "") or ""
        target_name = getattr(target, "Name", "") or ""
        if getattr(target, "FreeSolidAxisTool", False):
            return "line:{}".format(int(getattr(target, "AxisGeo", -1)))
        if target_name and target_name == profile_name:
            if sub == "H_Axis":
                return "horizontal"
            if sub.startswith("Edge"):
                try:
                    wanted = int(sub[4:])
                except ValueError:
                    return "vertical"
                edge = 0
                for index, geo in enumerate(getattr(profile, "Geometry", []) or []):
                    if self._is_construction(profile, index, geo):
                        continue
                    edge += 1
                    if edge == wanted:
                        return "line:{}".format(index)
                return "vertical"
            return "vertical"
        for token, role in self._AXIS_ROLES.items():
            if target_name == role or target_name.startswith(role):
                return token
        return "vertical"

    def _revolution_state(self, obj):
        profile = self._as_object(getattr(obj, "Profile", None))
        return {
            "axis": self._revolution_axis_token(obj),
            "angle": self._prop_float(obj, "Angle"),
            "reversed": bool(getattr(obj, "Reversed", False)),
            "midplane": bool(getattr(obj, "Midplane", False)),
            "profile": getattr(profile, "Name", "") or "",
        }

    def _sketch_line_axes(self, sk):
        """Lignes de l'esquisse proposées comme axe de révolution."""
        lines = []
        try:
            geometry = list(sk.Geometry)
        except Exception:
            return lines
        for gid, geo in enumerate(geometry):
            if getattr(geo, "TypeId", "") != "Part::GeomLineSegment":
                continue
            lines.append({
                "id": int(gid),
                "construction": bool(self._is_construction(sk, gid, geo)),
                "x1": round(float(geo.StartPoint.x), 2),
                "y1": round(float(geo.StartPoint.y), 2),
                "x2": round(float(geo.EndPoint.x), 2),
                "y2": round(float(geo.EndPoint.y), 2),
            })
        return lines

    def _revolved(self, type_id, angle, sketch, axis=None,
                  reversed=False, midplane=False):
        """Révolution ou gorge : même axe, ajout ou enlèvement.

        Sans axe, l'axe vertical de l'esquisse — le profil se dessine à
        côté. ``axis`` peut être ``horizontal``, ``line:<id>`` (une ligne
        de l'esquisse, de construction de préférence) ou ``X``, ``Y``, ``Z``.
        """
        body = self._require_body()
        doc = self._require_doc()
        try:
            degrees = float(angle)
        except (TypeError, ValueError):
            raise KernelError("angle de révolution invalide")
        if not (degrees > 0 and degrees <= 360):
            raise KernelError("angle de révolution invalide")
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        reference = self._revolution_reference(profile, axis)
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Profile = profile
        feature.ReferenceAxis = reference
        feature.Angle = degrees
        if reversed:
            feature.Reversed = True
        if midplane:
            feature.Midplane = True
        feature.Label = label_for_type(type_id, self.lang)
        self._drop_unused_axis_tools()
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            self._drop_unused_axis_tools()
            raise
        return self.get_tree()

    def add_revolution(self, angle=360.0, sketch=None, axis=None,
                       reversed=False, midplane=False):
        """Révolution."""
        return self._revolved(
            "PartDesign::Revolution", angle, sketch, axis=axis,
            reversed=reversed, midplane=midplane)

    def add_groove(self, angle=360.0, sketch=None, axis=None,
                   reversed=False, midplane=False):
        """Enlèvement par révolution."""
        return self._revolved(
            "PartDesign::Groove", angle, sketch, axis=axis,
            reversed=reversed, midplane=midplane)

    _AXIS_ROLES = {"X": "X_Axis", "Y": "Y_Axis", "Z": "Z_Axis"}

    def _last_solid_feature(self):
        """The feature a pattern/mirror duplicates: the latest add/sub one.

        Dress-ups and other transforms don't qualify — PartDesign patterns
        transform additive/subtractive features.
        """
        body = self._require_body()
        features = [o for o in body.Group
                    if o.isDerivedFrom("PartDesign::FeatureAddSub")]
        if not features:
            raise KernelError("aucune fonction à répéter — créez d'abord "
                              "un bossage ou un enlèvement de matière")
        return features[-1]

    def _pattern_catalog(self):
        """Catalogue {nom: {in_body, is_addsub, label}} du document."""
        body = self._require_body()
        doc = self._require_doc()
        in_body = {o.Name for o in body.Group}
        catalog = {}
        for obj in doc.Objects:
            is_addsub = False
            try:
                is_addsub = bool(
                    obj.isDerivedFrom("PartDesign::FeatureAddSub"))
            except Exception:
                is_addsub = False
            catalog[obj.Name] = {
                "in_body": obj.Name in in_body,
                "is_addsub": is_addsub,
                "label": obj.Label,
            }
        return catalog

    def _pattern_originals(self, features):
        """Fonctions à répéter : ``features`` ou la dernière additive."""
        if features is None:
            return [self._last_solid_feature()]
        names = resolve_pattern_originals(features, self._pattern_catalog())
        doc = self._require_doc()
        return [doc.getObject(name) for name in names]

    def _transform(self, type_id, configure, features=None):
        body = self._require_body()
        doc = self._require_doc()
        originals = self._pattern_originals(features)
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Originals = originals
        configure(feature)
        feature.Label = label_for_type(type_id, self.lang)
        # FreeCAD 1.0 laisse le Tip sur l'original après newObject d'un
        # Transformed : la répétition existe alors sans devenir le solide
        # du corps (volume inchangé). Un Body n'a qu'un solide — les copies
        # disjointes sont jetées ; on pose le Tip pour que la fusion compte.
        body.Tip = feature
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_mirror(self, plane="YZ", features=None):
        """Symétrie d'une ou plusieurs fonctions par rapport à un plan
        d'origine (XY/XZ/YZ = Dessus/Face/Droite).

        ``features`` : noms des fonctions à symétriser. Absent : la
        dernière fonction additive ou soustractive du corps actif.
        """
        role = self._PLANE_ROLES.get(str(plane).upper())
        if role is None:
            raise KernelError(
                "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
        plane_obj = self._origin_feature(role)

        def configure(feature):
            feature.MirrorPlane = (plane_obj, [""])
        return self._transform("PartDesign::Mirrored", configure,
                               features=features)

    def _origin_axis(self, axis):
        role = self._AXIS_ROLES.get(str(axis).upper())
        if role is None:
            raise KernelError(
                "axe inconnu « {} » — attendu X, Y ou Z".format(axis))
        return self._origin_feature(role)

    def _pattern_direction(self, axis, edge):
        """Direction d'une répétition : arête droite de la pièce (numéro
        d'arête 0-based), sinon axe d'origine."""
        if edge is not None:
            tip = self._require_body().Tip
            if tip is None:
                raise KernelError("aucune arête : la pièce est vide")
            return (tip, ["Edge{}".format(int(edge) + 1)])
        return (self._origin_axis(axis), [""])

    def add_linear_pattern(self, length, count, axis="X", features=None,
                           edge=None, spacing=False, reversed=False):
        """Réseau linéaire d'une ou plusieurs fonctions le long d'un axe
        ou d'une arête droite.

        ``length`` : longueur totale (par défaut) ou, avec ``spacing``,
        pas entre deux occurrences. ``features`` : noms des fonctions à
        répéter. Absent : la dernière fonction additive ou soustractive.
        """
        direction = self._pattern_direction(axis, edge)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Direction = direction
            if spacing and "Mode" in feature.PropertiesList:
                feature.Mode = "Spacing"
                feature.Offset = float(length)
            elif spacing:
                feature.Length = float(length) * (occurrences - 1)
            else:
                feature.Length = float(length)
            feature.Occurrences = occurrences
            if reversed:
                feature.Reversed = True
        return self._transform("PartDesign::LinearPattern", configure,
                               features=features)

    def add_polar_pattern(self, count, angle=360.0, axis="Z", features=None,
                          edge=None, reversed=False):
        """Réseau circulaire d'une ou plusieurs fonctions autour d'un
        axe d'origine ou d'une arête droite.

        ``features`` : noms des fonctions à répéter. Absent : la dernière
        fonction additive ou soustractive du corps actif.
        """
        axis_ref = self._pattern_direction(axis, edge)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Axis = axis_ref
            if reversed:
                feature.Reversed = True
            feature.Angle = float(angle)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::PolarPattern", configure,
                               features=features)

    def add_thickness(self, face=None, thickness=None, faces=None,
                      outward=False):
        """Coque : évide la pièce, les faces choisies deviennent des
        ouvertures. Vers l'intérieur par défaut ; ``outward`` ajoute
        l'épaisseur à l'extérieur (la pièce d'origine devient le vide)."""
        picked = [int(f) for f in (faces or [])]
        if not picked and face is not None:
            picked = [int(face)]
        if not picked:
            raise KernelError(
                "coque : cliquez au moins une face à ouvrir")
        if thickness is None or float(thickness) <= 0:
            raise KernelError("coque : épaisseur invalide")
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        previous_tip = tip
        volume_before = float(body.Shape.Volume)
        feature = body.newObject("PartDesign::Thickness", "Thickness")
        feature.Base = (tip, ["Face{}".format(f + 1) for f in picked])
        feature.Value = float(thickness)
        feature.Reversed = not outward   # FreeCAD : Reversed = vers l'intérieur
        feature.Label = label_for_type("PartDesign::Thickness", self.lang)
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, previous_tip)
            raise
        # Une épaisseur supérieure à la pièce est parfois acceptée sans
        # rien évider (le volume ne baisse pas). On refuse, comme un échec.
        if (not outward
                and float(body.Shape.Volume) >= volume_before - 1e-3):
            if not getattr(self, "_previewing", False):
                self._drop_failed_feature(body, doc, feature, previous_tip)
                self._recompute()
            raise KernelError(shell_too_thick_message())
        return self.get_tree()

    def _tip_face_parallel_to(self, tip, plane, exclude_face=None):
        """Face de ``tip`` parallèle à XY/XZ/YZ, hors ``exclude_face``.

        PartDesign::Draft (FreeCAD 1.0 / OCCT) ignore souvent un plan
        d'origine XZ/YZ comme plan neutre pour une face de calotte ; une
        face du solide de même orientation fonctionne. Repli : plan
        d'origine via ``_origin_feature``.
        """
        shape = getattr(tip, "Shape", None)
        if shape is None or shape.isNull():
            return None
        axis = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
        exclude = None if exclude_face is None else int(exclude_face)
        for index, face in enumerate(shape.Faces):
            if exclude is not None and index == exclude:
                continue
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            component = (normal.x, normal.y, normal.z)[axis]
            if abs(component) > 0.9:
                return (tip, ["Face{}".format(index + 1)])
        return None

    def add_draft(self, face, angle, neutral="XY"):
        """Dépouille de la face cliquée ; plan neutre XY/XZ/YZ."""
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à dépouiller")
        plane = parse_neutral_plane(neutral)
        # XY : plan d'origine (comportement historique, OK pour les parois).
        # XZ/YZ : une face du Tip parallèle — les plans d'origine XZ/YZ sont
        # un no-op OCCT sur les faces de calotte (FreeCAD 1.0).
        if plane == "XY":
            neutral_ref = (self._origin_feature(self._PLANE_ROLES[plane]), [""])
        else:
            neutral_ref = self._tip_face_parallel_to(
                tip, plane, exclude_face=face)
            if neutral_ref is None:
                neutral_ref = (
                    self._origin_feature(self._PLANE_ROLES[plane]), [""])
        volume_before = float(body.Shape.Volume)
        previous_tip = tip
        feature = body.newObject("PartDesign::Draft", "Draft")
        feature.Base = (tip, ["Face{}".format(int(face) + 1)])
        feature.Angle = float(angle)
        feature.NeutralPlane = neutral_ref
        feature.Label = label_for_type("PartDesign::Draft", self.lang)
        try:
            self._recompute()
        except KernelError:
            if getattr(body, "Tip", None) is feature or body.Tip is None:
                body.Tip = previous_tip
            doc.removeObject(feature.Name)
            raise
        volume_after = float(body.Shape.Volume)
        if abs(volume_after - volume_before) < 1e-9:
            # Sous aperçu, l'abort de la transaction restaure tout ; un
            # removeObject d'une fonction aboutie DANS la transaction
            # serait rejoué par l'abort — double-nettoyage qui peut
            # ressusciter des objets (doublons observés dans l'arbre).
            if not getattr(self, "_previewing", False):
                body.Tip = previous_tip
                doc.removeObject(feature.Name)
                self._recompute()
            raise KernelError(
                "cette face ne peut pas être dépouillée par rapport à ce "
                "plan neutre — choisissez un autre plan neutre ou une autre face")
        return self.get_tree()

    def _dressup(self, type_id, label, prop, value, face=None, edges=None):
        """Fillet/chamfer share everything but the property they drive.

        The dress-up references the picked face or edges on the Tip
        feature — the shape the viewport tessellated, so the numbering
        matches by construction. A face means every edge of that face;
        an edge list is the precise SolidWorks gesture.
        """
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        if edges:
            subs = ["Edge{}".format(int(e) + 1) for e in edges]
        elif face is not None:
            subs = ["Face{}".format(int(face) + 1)]
        else:
            raise KernelError(
                "sélectionnez des arêtes ou une face de la pièce")
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Base = (tip, subs)
        setattr(feature, prop, float(value))
        feature.Label = label
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, tip)
            raise
        return self.get_tree()

    def add_fillet(self, radius, face=None, edges=None):
        return self._dressup("PartDesign::Fillet", "Congé",
                             "Radius", radius, face=face, edges=edges)

    #: Jeton du panneau → énumération FreeCAD ``ChamferType``.
    _CHAMFER_TYPES = {
        "egale": "Equal distance",
        "deux": "Two distances",
        "angle": "Distance and Angle",
    }

    def _chamfer_kind(self, obj):
        """``egale``, ``deux`` ou ``angle`` — ``egale`` si la propriété manque."""
        current = str(getattr(obj, "ChamferType", "") or "")
        for token, label in self._CHAMFER_TYPES.items():
            if current == label:
                return token
        return "egale"

    @staticmethod
    def _prop_float(obj, name):
        value = getattr(obj, name, 0)
        return float(getattr(value, "Value", value))

    def _chamfer_state(self, obj):
        """État relu pour l'arbre et la réédition."""
        return {
            "type": self._chamfer_kind(obj),
            "size": self._prop_float(obj, "Size"),
            "size2": self._prop_float(obj, "Size2"),
            "angle": self._prop_float(obj, "Angle"),
            "flip": bool(getattr(obj, "FlipDirection", False)),
        }

    def _editable_props(self, obj):
        """Cotes proposées à l'édition. Le chanfrein ne montre que celles
        du type en cours : une distance, deux distances, ou distance et angle."""
        if getattr(obj, "TypeId", "") != "PartDesign::Chamfer":
            return self._EDITABLE_PROPS
        kind = self._chamfer_kind(obj)
        if kind == "deux":
            return ("Size", "Size2")
        if kind == "angle":
            return ("Size", "Angle")
        return ("Size",)

    def add_chamfer(self, size, face=None, edges=None,
                    size2=None, angle=None, chamfer_type="egale", flip=False):
        """Chanfrein : distance égale, deux distances, ou distance et angle.

        ``chamfer_type`` vaut ``egale`` (défaut, le geste historique),
        ``deux`` (``size`` et ``size2``) ou ``angle`` (``size`` et ``angle``
        en degrés, strictement entre 0 et 90). ``flip`` échange les deux
        côtés — sans effet quand les deux côtés sont égaux.
        """
        kind = str(chamfer_type or "egale")
        if kind not in self._CHAMFER_TYPES:
            raise KernelError(
                "type de chanfrein inconnu « {} » — attendu : {}".format(
                    kind, ", ".join(self._CHAMFER_TYPES)))
        try:
            distance = float(size)
        except (TypeError, ValueError):
            raise KernelError("distance de chanfrein invalide")
        if distance <= 0:
            raise KernelError("distance de chanfrein invalide")
        second = None
        degrees = None
        if kind == "deux":
            try:
                second = float(size2)
            except (TypeError, ValueError):
                raise KernelError("seconde distance de chanfrein invalide")
            if second <= 0:
                raise KernelError("seconde distance de chanfrein invalide")
        elif kind == "angle":
            try:
                degrees = float(angle)
            except (TypeError, ValueError):
                degrees = None
            if degrees is None or not (0 < degrees < 90):
                raise KernelError(
                    "angle de chanfrein invalide — entre 0 et 90 degrés, exclus")
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        if edges:
            subs = ["Edge{}".format(int(e) + 1) for e in edges]
        elif face is not None:
            subs = ["Face{}".format(int(face) + 1)]
        else:
            raise KernelError(
                "sélectionnez des arêtes ou une face de la pièce")
        feature = body.newObject("PartDesign::Chamfer", "Chamfer")
        feature.Base = (tip, subs)
        feature.ChamferType = self._CHAMFER_TYPES[kind]
        feature.Size = distance
        if second is not None:
            feature.Size2 = second
        if degrees is not None:
            feature.Angle = degrees
        feature.FlipDirection = bool(flip) and kind != "egale"
        feature.Label = self._t("Chanfrein")
        try:
            self._recompute()
        except KernelError:
            self._drop_failed_feature(body, doc, feature, tip)
            raise
        return self.get_tree()

    #: Properties offered for editing, in display order. A whitelist rather
    #: than full introspection: Pad alone carries a dozen numeric properties
    #: and prompting through Offset/TaperAngle/Length2 buries the one that
    #: matters.
    _EDITABLE_PROPS = ("Length", "LengthFwd", "Radius", "Size", "Angle",
                       "Thickness", "Thickness2", "CapThickness", "Value",
                       "Occurrences",
                       "Diameter", "Depth", "HoleCutDiameter",
                       "HoleCutDepth")

    def get_params(self, feature):
        """Editable numeric properties of a feature, with current values."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        exprs = self._expression_map(obj)
        params = []
        for prop in self._editable_props(obj):
            if not hasattr(obj, prop):
                continue
            value = getattr(obj, prop)
            entry = {"prop": prop,
                     "value": float(getattr(value, "Value", value))}
            if prop in exprs:
                entry["expr"] = exprs[prop]
            params.append(entry)
        return {"feature": feature, "label": obj.Label, "params": params}

    def set_tip(self, feature=None):
        """Déplace la barre de retour : l'historique se reconstruit
        jusqu'à cette ligne (fonction, esquisse libre ou surface).

        Sans *feature* (ou nom vide), la barre se pose avant la première
        ligne — tout est reculé, comme un glisser tout en haut du
        FeatureManager. ``body.Tip`` ne couvre que la chaîne PartDesign ;
        les surfaces et esquisses libres portent ``FreeSolidRolledBack``.
        """
        body = self._require_body()
        history = self._history_lines()
        if feature is None or not str(feature).strip():
            flags, tip_name = rollback_plan(self._history_rows(history), None)
            body.Tip = None
            self._apply_rollback_flags(flags)
            self._recompute()
            return self.get_tree()
        obj = self._require_doc().getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        names = {line.Name for line in history}
        if obj.Name not in names:
            raise KernelError(
                "« {} » n'est pas une ligne d'historique — la barre de "
                "retour se pose sur une fonction, une esquisse libre ou "
                "une surface".format(obj.Label))
        flags, tip_name = rollback_plan(
            self._history_rows(history), obj.Name)
        if tip_name is None:
            body.Tip = None
        else:
            tip_obj = self._require_doc().getObject(tip_name)
            body.Tip = self._tip_with_helpers(tip_obj)
        self._apply_rollback_flags(flags)
        self._recompute()
        return self.get_tree()

    def tip_to_end(self):
        """Barre de retour en bout d'historique — l'état final."""
        body = self._require_body()
        history = self._history_lines()
        if not history:
            raise KernelError("aucune fonction dans la pièce")
        flags, tip_name = rollback_plan(
            self._history_rows(history), history[-1].Name)
        if tip_name is None:
            body.Tip = None
        else:
            body.Tip = self._tip_with_helpers(
                self._require_doc().getObject(tip_name))
        self._apply_rollback_flags(flags)
        self._recompute()
        return self.get_tree()

    def delete_feature(self, feature):
        """Remove one feature. Its sketch stays — deleting it too would be
        a second, separate decision, exactly as in SolidWorks. Deleting a
        body removes its whole contents; the last body is protected."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if self._plugins.run_deletes_feature(self, obj):
            return self._current_tree()
        label = obj.Label
        if obj.TypeId == "PartDesign::Body":
            bodies = [o for o in doc.Objects
                      if o.TypeId == "PartDesign::Body"]
            if len(bodies) <= 1:
                raise KernelError("impossible de supprimer le dernier "
                                  "corps de la pièce")
            for child in list(obj.Group):
                try:
                    doc.removeObject(child.Name)
                except Exception:
                    pass
            if self._body is obj:
                self._body = next(b for b in bodies if b is not obj)
        # Supprimer le Tip laissait Body.Tip = None et une Shape invalide
        # (attrapé par le selftest P007) : le Tip recule d'abord sur la
        # fonction précédente de la chaîne (None si c'était la seule —
        # corps vide légitime).
        parent_body = obj.getParentGeoFeatureGroup()
        thin_helpers = self._thin_helpers(obj)
        if parent_body is not None and getattr(parent_body, "Tip", None) in (
                [obj] + thin_helpers):
            parent_body.Tip = getattr(obj, "BaseFeature", None)
        # Paroi mince : la cavité (après la fonction) part avant elle, les
        # profils décalés (avant) après.
        order = {o.Name: i for i, o in enumerate(
            getattr(parent_body, "Group", None) or [])}
        rank = order.get(obj.Name, -1)
        later = [o for o in thin_helpers if order.get(o.Name, -1) > rank]
        earlier = [o.Name for o in thin_helpers if o not in later]
        self._remove_all(later)
        doc.removeObject(obj.Name)
        for name in reversed(earlier):
            if doc.getObject(name) is not None:
                doc.removeObject(name)
        try:
            if self._assembly:
                doc.recompute()
            else:
                self._recompute()
        except KernelError as exc:
            raise KernelError(
                "{} supprimé, mais l'aval casse : {}".format(label, exc))
        return self._current_tree()

    def set_param(self, feature, prop, value):
        """Set one property on one feature by internal name, and recompute.

        This is the whole parametric promise in one operation: the UI edits
        ``Pad.Length`` and the part rebuilds. Même atomicité que
        ``set_params`` : un refus ne modifie pas la pièce.
        """
        return self.set_params(feature, {str(prop): value})

    def set_params(self, feature, values):
        """Set several properties at once, one recompute — the edit panel
        applies (and previews) its whole form atomically.

        A value may be a number, or a string: a numeric string is a
        number, anything else is an **expression** (``2*Largeur + 5``) —
        the SolidWorks equation, via FreeCAD's expression engine.
        """
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if not isinstance(values, dict):
            raise KernelError("values doit être un objet JSON")
        # Atomicité : une expression était stockée AVANT que le recompute
        # ne la valide — un identifiant inconnu (« _ ») laissait la pièce
        # Invalid pour toujours (barre bloquée, cascade « Tool shape is
        # null »). On mémorise l'état pour tout restaurer sur refus.
        exprs_before = dict(obj.ExpressionEngine or [])
        previous = []  # (prop, ancienne expression ou None, ancienne valeur)
        editable = self._EDITABLE_PROPS
        thin = self._thin_spec(obj) is not None
        revolved = obj.TypeId in (
            "PartDesign::Revolution", "PartDesign::Groove")
        if obj.TypeId == "PartDesign::Chamfer":
            editable = editable + ("Size2", "ChamferType", "FlipDirection")
        if revolved:
            editable = editable + ("Reversed", "Midplane", "axis")
        for prop, value in values.items():
            prop = str(prop)
            if prop not in editable:
                raise KernelError("propriété non éditable : {}".format(prop))
            if prop == "axis":
                profile = self._as_object(getattr(obj, "Profile", None))
                if profile is None:
                    self._restore_props(obj, previous)
                    raise KernelError("l'axe de révolution doit être une ligne")
                token = str(value).strip() if value is not None else ""
                try:
                    reference = self._revolution_reference(profile, token)
                except KernelError:
                    self._restore_props(obj, previous)
                    raise
                previous.append(("ReferenceAxis", exprs_before.get("ReferenceAxis"),
                                 getattr(obj, "ReferenceAxis", None)))
                try:
                    obj.ReferenceAxis = reference
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop in ("Reversed", "Midplane") and revolved:
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError("sens de révolution : booléen attendu")
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, flag)
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if not hasattr(obj, prop):
                raise KernelError("{} n'a pas de propriété {}".format(
                    obj.Label, prop))
            if prop == "ChamferType":
                token = str(value).strip() if value is not None else ""
                if token not in self._CHAMFER_TYPES:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "type de chanfrein inconnu « {} » — attendu : {}"
                        .format(token, ", ".join(self._CHAMFER_TYPES)))
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, self._CHAMFER_TYPES[token])
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if prop == "FlipDirection":
                if isinstance(value, bool):
                    flag = value
                elif type(value) is int and value in (0, 1):
                    flag = bool(value)
                else:
                    self._restore_props(obj, previous)
                    raise KernelError(
                        "inverser le chanfrein : booléen attendu")
                previous.append((prop, exprs_before.get(prop),
                                 getattr(obj, prop, None)))
                try:
                    setattr(obj, prop, flag)
                except Exception as exc:  # noqa: BLE001
                    self._restore_props(obj, previous)
                    raise KernelError(_explain(exc))
                continue
            if (prop in ("Thickness", "Thickness2", "CapThickness") and thin
                    and isinstance(value, str)
                    and parse_user_number(value) is None):
                self._restore_props(obj, previous)
                raise KernelError(
                    "épaisseur de paroi : valeur numérique attendue")
            previous.append((prop, exprs_before.get(prop),
                             getattr(obj, prop, None)))
            if isinstance(value, str):
                number = parse_user_number(value)
                if number is not None:
                    value = number  # « 6,5 » est un nombre, pas une équation
                else:
                    text = self._user_expression(value.strip())
                    try:
                        obj.setExpression(prop, text)
                    except Exception as exc:  # noqa: BLE001
                        self._restore_props(obj, previous)
                        raise KernelError(_explain(exc))
                    continue
            # Valeur numérique : une expression existante reprendrait la
            # main au recompute — on la retire d'abord.
            try:
                obj.setExpression(prop, None)
            except Exception:
                pass
            current = getattr(obj, prop, None)
            if isinstance(current, int) and not isinstance(current, bool):
                value = int(value)
            try:
                setattr(obj, prop, value)
            except Exception as exc:  # noqa: BLE001
                self._restore_props(obj, previous)
                raise KernelError(_explain(exc))
        try:
            self._sync_thin(obj)
            self._recompute()
        except KernelError as exc:
            self._restore_props(obj, previous)
            try:
                self._sync_thin(obj)
                self._recompute()
            except KernelError:
                pass  # l'état d'origine était déjà sain : ne pas masquer exc
            raise KernelError(
                "{} — la pièce n'a pas été modifiée".format(exc))
        self._drop_unused_axis_tools()
        return self.get_tree()

    @staticmethod
    def _restore_props(obj, previous):
        """Défait ``set_params`` : remet liaisons et valeurs mémorisées."""
        for prop, old_expr, old_value in reversed(previous):
            try:
                obj.setExpression(prop, old_expr)  # None efface la liaison
            except Exception:
                pass
            if old_expr is None and old_value is not None:
                try:
                    setattr(obj, prop, old_value)
                except Exception:
                    pass

    # -- paramétrique : variables globales + équations -------------------

    _VARSET_NAME = "Variables"

    @staticmethod
    def _valid_identifier(name):
        import re
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)))

    def _varset(self, create=False):
        doc = self._require_doc()
        obj = doc.getObject(self._VARSET_NAME)
        if obj is not None and self._is_internal_tool(obj):
            obj = next((item for item in doc.Objects
                        if item.TypeId == "App::VarSet"
                        and not self._is_internal_tool(item)
                        and item.Label == "Équations"), None)
            if obj is None:
                obj = next((item for item in doc.Objects
                            if item.TypeId == "App::VarSet"
                            and not self._is_internal_tool(item)), None)
        if obj is None and create:
            obj = doc.addObject("App::VarSet", self._VARSET_NAME)
            obj.Label = self._t("Équations")
        return obj

    def _variable_names(self, varset):
        return [p for p in varset.PropertiesList
                if varset.getGroupOfProperty(p) == "Variables"]

    def list_variables(self):
        varset = self._varset()
        if varset is None:
            return {"variables": []}
        return {"variables": [
            {"name": name,
             "value": float(getattr(varset, name))}
            for name in self._variable_names(varset)]}

    def set_variable(self, name, value):
        """Créer ou modifier une variable globale — utilisable ensuite
        dans toute expression : ``Variables.Largeur * 2``."""
        name = str(name).strip()
        if not self._valid_identifier(name):
            raise KernelError(
                "nom invalide « {} » — lettres, chiffres et _ seulement, "
                "sans commencer par un chiffre".format(name))
        varset = self._varset(create=True)
        if name not in varset.PropertiesList:
            varset.addProperty("App::PropertyFloat", name, "Variables")
        try:
            setattr(varset, name, float(value))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        self._require_doc().recompute()
        return self.list_variables()

    def delete_variable(self, name):
        varset = self._varset()
        name = str(name).strip()
        if varset is None or name not in self._variable_names(varset):
            raise KernelError("variable inconnue : {}".format(name))
        try:
            varset.removeProperty(name)
        except Exception as exc:  # noqa: BLE001 - encore référencée
            raise KernelError(_explain(exc))
        self._require_doc().recompute()
        return self.list_variables()

    @staticmethod
    def _expression_map(obj):
        """{property path -> expression}, normalized without leading dot."""
        table = {}
        for path, expr in (getattr(obj, "ExpressionEngine", None) or ()):
            table[str(path).lstrip(".")] = str(expr)
        return table

    def rename(self, feature, label):
        """Renommer une fonction, une esquisse ou la pièce."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        label = str(label).strip()
        if not label:
            raise KernelError("le nom ne peut pas être vide")
        obj.Label = label
        return self._current_tree()

    #: Correspondance panneau -> énumération FreeCAD du type de lamage.
    _HOLE_CUTS = {"none": "None", "lamage": "Counterbore",
                  "fraisage": "Countersink"}

    def add_hole(self, diameter, depth=None, through=False, cut="none",
                 cut_diameter=None, cut_depth=None, cut_angle=None):
        """Perçage — version simple.

        Le profil est la dernière esquisse non utilisée : ses cercles (un
        par perçage) positionnent les trous ; le diamètre saisi remplace
        le leur. Borgne ou à travers tout, lamage ou fraisage optionnel.
        """
        body = self._require_body()
        doc = self._require_doc()
        cut_type = self._HOLE_CUTS.get(str(cut))
        if cut_type is None:
            raise KernelError(
                "type inconnu « {} » — attendu : none, lamage ou "
                "fraisage".format(cut))
        if float(diameter) <= 0:
            raise KernelError("le diamètre doit être positif")
        profile = self._latest_sketch()
        hole = body.newObject("PartDesign::Hole", "Hole")
        hole.Profile = profile
        hole.Threaded = False
        hole.Diameter = float(diameter)
        if through or depth is None:
            hole.DepthType = "ThroughAll"
        else:
            hole.DepthType = "Dimension"
            hole.Depth = float(depth)
        hole.HoleCutType = cut_type
        if cut_type != "None" and cut_diameter:
            hole.HoleCutDiameter = float(cut_diameter)
        if cut_type == "Counterbore" and cut_depth:
            hole.HoleCutDepth = float(cut_depth)
        if cut_type == "Countersink" and cut_angle:
            try:
                hole.HoleCutCountersinkAngle = float(cut_angle)
            except AttributeError:
                pass  # renommée selon les versions ; l'angle par défaut sert
        hole.Label = label_for_type("PartDesign::Hole", self.lang)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(hole.Name)
            raise
        return self.get_tree()

    def _body_has_solid(self, body):
        """Vrai si le corps porte un solide OCCT réel (état affiché)."""
        shape = getattr(body, "Shape", None)
        if shape is None:
            return False
        try:
            if shape.isNull():
                return False
            solids = shape.Solids
        except Exception:  # noqa: BLE001 — Shape OCCT parfois inaccessible
            return False
        return bool(solids)

    def _tree_known_names(self, body):
        """Noms des nœuds dessinables du payload ``get_tree``.

        Fonction, esquisse, plan de référence, surface ou corps déjà
        présents dans la réponse — pas l'Origin, le VarSet, ni les
        artefacts internes (gravure, fonction graphe, répétition).
        """
        names = set()
        origin = getattr(body, "Origin", None)
        for feature in getattr(origin, "OriginFeatures", None) or ():
            role = getattr(feature, "Role", "")
            if role in self._PLANE_ROLES.values():
                names.add(feature.Name)
        # Tout ``body.Group`` : ``get_tree`` émet chaque objet du corps —
        # une esquisse consommée revient en ``children``, un plan ou un axe
        # de référence n'est pas un ``PartDesign::Feature`` mais reste un
        # nœud. Filtrer ici ferait diverger l'ensemble des cibles de ce que
        # le payload expose, et perdrait des arêtes réelles en silence.
        for obj in body.Group:
            if (getattr(obj, "FreeSolidAxisTool", False)
                    or self._is_thin_helper(obj)):   # hors arbre
                continue
            names.add(obj.Name)
        for obj in self._doc.Objects:
            if obj.TypeId == "PartDesign::Body" and not self._is_internal_tool(obj):
                names.add(obj.Name)
            if (obj.TypeId in self._SURFACE_TYPE_IDS
                    and not self._is_internal_tool(obj)):
                names.add(obj.Name)
                for sketch in self._surface_sketch_objects(obj):
                    names.add(sketch.Name)
        for obj in self._doc.Objects:
            # Semis : App::Link marqué. Même discipline que
            # ``_is_internal_tool`` — le noyau reconnaît une propriété,
            # il n'appelle plus le métier bijouterie.
            if (getattr(obj, "TypeId", "") == "App::Link"
                    and "FreeSolidGemFace" in getattr(
                        obj, "PropertiesList", ())):
                names.add(obj.Name)
        return names

    @staticmethod
    def _is_sub_names(value):
        """Vrai si ``value`` est un nom de sous-élément ou une liste de noms."""
        if isinstance(value, str):
            return True
        if not isinstance(value, (list, tuple)):
            return False
        return all(isinstance(item, str) for item in value)

    @staticmethod
    def _iter_link_subs(value):
        """Paires ``(objet, [sous-éléments])`` d'un Link, LinkSub ou LinkSubList.

        ``Base`` (habillage, dépouille) a la forme ``(objet, [noms])`` ;
        ``AttachmentSupport`` (esquisse sur face) est une liste de telles
        paires. Un objet nu (``Profile`` d'un bossage) n'a pas de sous-élément.
        """
        if value is None:
            return
        if isinstance(value, (list, tuple)):
            if (len(value) == 2
                    and getattr(value[0], "Name", None)
                    and Kernel._is_sub_names(value[1])):
                subs = ([value[1]] if isinstance(value[1], str)
                        else list(value[1]))
                yield value[0], subs
                return
            for item in value:
                for pair in Kernel._iter_link_subs(item):
                    yield pair
            return
        if getattr(value, "Name", None):
            yield value, []
            return
        try:
            items = list(value)
        except TypeError:
            return
        for item in items:
            for pair in Kernel._iter_link_subs(item):
                yield pair

    def _object_dep_subs(self, obj):
        """``{cible: [sous-éléments]}`` lus sur ``Base`` et l'appui d'esquisse.

        Les sous-éléments vides (attache à l'objet entier) sont omis : ils
        n'ajoutent rien à ``deps``. Le filtrage des cibles hors payload
        est ``visible_dep_subs``.
        """
        raw = {}
        for prop in ("Base", "AttachmentSupport", "Support"):
            if not hasattr(obj, prop):
                continue
            try:
                value = getattr(obj, prop)
            except Exception:  # noqa: BLE001 — propriété FreeCAD parfois cassée
                continue
            for target, subs in self._iter_link_subs(value):
                name = getattr(target, "Name", "") or ""
                if not name:
                    continue
                existing = raw.setdefault(name, [])
                for sub in subs:
                    if not isinstance(sub, str) or not sub or sub in existing:
                        continue
                    existing.append(sub)
        return raw

    def _repeat_source_names(self, obj):
        """Noms des fonctions source d'une répétition variable, ou [].

        Les copies rejouées n'existent plus dans l'OutList : le lien
        se lit dans le JSON persisté.
        """
        if "FreeSolidRepeatJson" not in getattr(obj, "PropertiesList", ()):
            return []
        try:
            parsed = json.loads(obj.FreeSolidRepeatJson or "")
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed, dict):
            return []
        names = []
        for name in parsed.get("features") or ():
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def _annotate_tree_links(self, item, obj, known_names):
        """Pose ``deps``, ``dep_subs``, ``driven`` et ``params`` s'ils existent.

        ``params`` réutilise ``get_params`` — pas de seconde boucle sur
        ``_EDITABLE_PROPS``. Champs omis quand vides.
        """
        outs = [o.Name for o in (getattr(obj, "OutList", None) or ())]
        _, source = self._thin_chain(obj)
        if source is not None:
            # Paroi mince : l'arête va à l'esquisse, pas au profil caché.
            outs = [source.Name] + outs
        deps = visible_deps(outs + self._repeat_source_names(obj),
                            known_names)
        if deps:
            item["deps"] = deps
        dep_subs = visible_dep_subs(self._object_dep_subs(obj), known_names)
        if dep_subs:
            item["dep_subs"] = dep_subs
        driven = self._expression_map(obj)
        if driven:
            item["driven"] = driven
        params = self.get_params(obj.Name).get("params") or []
        if params:
            item["params"] = params
        return item

    def get_tree(self):
        """Arbre de fonctions, vocabulaire du concepteur.

        Forme SolidWorks : les trois plans de référence d'abord, et une
        esquisse consommée par une fonction se range dessous en
        ``children`` plutôt que de polluer le premier niveau.

        Chaque entrée — fonction du corps, esquisse imbriquée, surface et
        esquisse de surface — peut porter quatre champs, omis quand ils
        sont vides :

        - ``deps`` — noms internes des nœuds dont elle dépend
          (``OutList`` filtré). Une arête n'est émise que si sa cible
          est elle-même un nœud du même payload : fonction, esquisse,
          plan de référence, surface ou corps. Aucune arête pendante.
        - ``dep_subs`` — ``{cible: [sous-éléments]}`` lus sur ``Base``
          et ``AttachmentSupport``. Les noms de face ou d'arête que
          ``OutList`` jette. Même filtre que ``deps`` : une cible hors
          payload n'émet pas de sous-élément.
        - ``driven`` — ``{chemin de propriété: expression}``, les
          propriétés pilotées. Chaîne brute, sans parsing des variables.
        - ``params`` — cotes éditables, même forme que ``get_params``.

        Les plans de référence sont adressables : chaque entrée de
        ``planes`` porte le ``name`` de l'objet, seule adresse par
        laquelle une arête peut les désigner — ``id`` reste ``"XZ"`` quand
        le nom prend un suffixe en multi-corps.

        La cohérence de l'ensemble se vérifie par
        ``protocol.dangling_deps`` : elle confronte chaque arête à ce que
        le payload expose vraiment, et non à l'ensemble de noms qui a
        servi à la filtrer. Le selftest la passe sur la pièce vitrine.
        """
        body = self._require_body()
        order_of = {obj.Name: i for i, obj in enumerate(self._doc.Objects)}
        # Dans le corps, l'ordre fait foi (réordonner le change sans toucher
        # l'ordre de création) : on redistribue ses rangs selon body.Group,
        # ce qui garde l'entrelacement avec les surfaces hors corps.
        members = [o for o in body.Group if o.Name in order_of]
        for slot, obj in zip(sorted(order_of[o.Name] for o in members),
                             members):
            order_of[obj.Name] = slot

        consumed = self._consumed_sketches()
        known_names = self._tree_known_names(body)

        def entry(obj):
            item = {
                "name": obj.Name,
                "label": obj.Label,
                "kind": label_for_type(obj.TypeId, self.lang),
                "type": obj.TypeId,
                "error": "Invalid" in (obj.State or ()),
                "order": order_of.get(obj.Name, -1),
            }
            if obj.TypeId == "PartDesign::Plane":
                # Le client dessine le plan de référence dans le viewport.
                item["placement"] = [
                    float(v) for v in obj.Placement.Matrix.A]
            if obj.TypeId == "Sketcher::SketchObject":
                item["rolled_back"] = self._is_rolled_back(obj)
                item["definition"] = self._sketch_definition(obj)
                lines = self._sketch_line_axes(obj)
                if lines:
                    item["lines"] = lines
            if obj.TypeId == "PartDesign::Chamfer":
                item["chamfer"] = self._chamfer_state(obj)
            thin = self._thin_spec(obj)
            if thin is not None:
                item["thin"] = thin
            if obj.TypeId in ("PartDesign::Revolution", "PartDesign::Groove"):
                item["revolution"] = self._revolution_state(obj)
            if "FreeSolidTextString" in obj.PropertiesList:
                # Gravure rééditable : le panneau client édite ces valeurs.
                item["text"] = {
                    "text": obj.FreeSolidTextString,
                    "size": float(obj.FreeSolidTextSize),
                    "depth": float(obj.FreeSolidTextDepth),
                    "x": float(obj.FreeSolidTextX),
                    "y": float(obj.FreeSolidTextY),
                }
            if "FreeSolidGraphJson" in obj.PropertiesList:
                graph = self._tree_graph_payload(obj)
                if graph is not None:
                    item["graph"] = graph
            if "FreeSolidRepeatJson" in obj.PropertiesList:
                try:
                    parsed = json.loads(obj.FreeSolidRepeatJson or "")
                except (TypeError, ValueError):
                    parsed = None
                if isinstance(parsed, dict):
                    item["repeat"] = parsed
            self._annotate_tree_links(item, obj, known_names)
            return item

        items = []
        for obj in body.Group:
            if getattr(obj, "FreeSolidAxisTool", False):
                continue
            if (obj.TypeId == "Sketcher::SketchObject"
                    and obj.Name in consumed) or self._is_thin_helper(obj):
                continue
            item = entry(obj)
            children = [entry(o) for o in body.Group
                        if o.TypeId == "Sketcher::SketchObject"
                        and consumed.get(o.Name) == obj.Name]
            if children:
                item["children"] = children
            items.append(item)

        from engine.vocab import label_for_origin
        # L'ordre SolidWorks : Plan de face, Plan de dessus, Plan de droite.
        # ``name`` : le nom d'objet réel, seule adresse par laquelle une
        # arête peut désigner un plan de référence (``id`` ne suffit pas —
        # en multi-corps FreeCAD suffixe le nom, « XZ_Plane001 »).
        planes = []
        for wire in ("XZ", "XY", "YZ"):
            role = self._PLANE_ROLES[wire]
            feature = self._origin_feature_or_none(role)
            planes.append({
                "id": wire,
                "label": label_for_origin(role, self.lang),
                "name": feature.Name if feature is not None else "",
            })
        bodies = []
        for obj in self._doc.Objects:
            if obj.TypeId != "PartDesign::Body":
                continue
            if self._is_internal_tool(obj):
                continue  # corps outil interne : artefact hors arbre
            bodies.append({
                "name": obj.Name,
                "label": obj.Label,
                "active": obj is body,
                "count": len([o for o in obj.Group
                              if (o.isDerivedFrom("PartDesign::Feature")
                                  or o.TypeId == "Sketcher::SketchObject")
                              and not self._is_thin_helper(o)]),
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "has_solid": self._body_has_solid(obj),
            })
        surfaces = [self._surface_tree_entry(o, order_of, known_names)
                    for o in self._doc.Objects
                    if o.TypeId in self._SURFACE_TYPE_IDS
                    and not self._is_internal_tool(o)]
        tip = (self._thin_owner(body.Tip).Name
               if getattr(body, "Tip", None) else None)
        # Variables dans le même appel : le FeatureManager affiche le
        # dossier Équations sans round-trip list_variables.
        tree = {"body": body.Label, "tip": tip, "bodies": bodies,
                "planes": planes, "features": items,
                "surfaces": surfaces,
                "variables": self.list_variables()["variables"]}
        self._plugins.contribute_tree(self, tree)
        return tree

    def _face_mesh(self, face, face_id, deviation):
        """Tessellation d'une face + normales exactes ``normalAt(u, v)``."""
        from engine.surfaces import is_bspline_surface, project_uv
        vertices, triangles = face.tessellate(float(deviation))
        points = [(v.x, v.y, v.z) for v in vertices]
        normals = []
        for vertex in vertices:
            try:
                u, v, _on = project_uv(face, vertex.x, vertex.y, vertex.z)
                normal = face.normalAt(u, v)
                if hasattr(normal, "normalize"):
                    normal = normal.normalize()
                length = float(getattr(normal, "Length", 0) or 0)
                if length < 1e-12:
                    normals.append((0.0, 0.0, 1.0))
                else:
                    normals.append((float(normal.x), float(normal.y),
                                    float(normal.z)))
            except Exception:
                normals.append((0.0, 0.0, 1.0))
        return (face_id, points, triangles, normals), is_bspline_surface(face)

    def tessellate(self, deviation=0.1):
        """Per-face tessellation of the body's current shape.

        Face-by-face on purpose — see ``protocol.pack_mesh``: picking works
        by construction because each OCCT face is its own index group.
        """
        from . import protocol
        body = self._require_body()
        self._report_progress("Maillage")
        shape = getattr(body, "Shape", None)
        faces = []
        splines = []
        if shape is not None and shape.Faces:
            for i, face in enumerate(shape.Faces):
                packed, spline = self._face_mesh(face, i, deviation)
                faces.append(packed)
                splines.append(spline)
        mesh = protocol.pack_mesh(faces)
        producers = self._face_producers()
        for group, spline in zip(mesh.get("groups") or [], splines):
            if spline:
                group["spline"] = True
            feature = producers.get(group.get("faceId"))
            if feature:
                group["feature"] = self._thin_owner(
                    self._doc.getObject(feature)).Name
        match = getattr(self, "_face_match", None) or {}
        mesh["face_match"] = {
            "matched": int(match.get("matched") or 0),
            "faces": int(match.get("faces") or 0),
        }
        mesh["color"] = getattr(body, "FreeSolidColor", "") or None
        # Les autres corps s'affichent estompés, non sélectionnables :
        # on travaille sur le corps actif, on voit la pièce entière.
        # Un maillage par corps (couleur propre) ; ``others`` reste le
        # buffer combiné pour la compatibilité (selftest p9_others_shown).
        other_bodies = []
        for obj in self._doc.Objects:
            if (obj.TypeId != "PartDesign::Body" or obj is body
                    or getattr(obj, "Shape", None) is None
                    or self._is_internal_tool(obj)):
                continue
            other_faces = []
            for face in obj.Shape.Faces:
                vertices, triangles = face.tessellate(float(deviation))
                other_faces.append(
                    (0, [(v.x, v.y, v.z) for v in vertices], triangles))
            if not other_faces:
                continue
            packed = protocol.pack_mesh(other_faces)
            other_bodies.append({
                "name": obj.Name,
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "positions": packed["positions"],
                "indices": packed["indices"],
            })
        if other_bodies:
            mesh["other_bodies"] = other_bodies
            positions = []
            indices = []
            vertex_base = 0
            for extra in other_bodies:
                positions.extend(extra["positions"])
                indices.extend(i + vertex_base for i in extra["indices"])
                vertex_base += len(extra["positions"]) // 3
            mesh["others"] = {"positions": positions, "indices": indices}
        # Surfaces (Part::*) : un maillage par objet, comme les esquisses
        # libres — le client les rend opaques et sélectionnables. Les
        # courbes 3D (pas de Faces) restent un buffer combiné.
        surfaces_out = []
        surface_lines = []
        for obj in self._doc.Objects:
            if obj.TypeId not in self._SURFACE_TYPE_IDS:
                continue
            if self._is_rolled_back(obj) or self._is_internal_tool(obj):
                continue
            shape = getattr(obj, "Shape", None)
            if shape is None:
                continue
            if shape.Faces:
                surface_faces = []
                for face in shape.Faces:
                    vertices, triangles = face.tessellate(float(deviation))
                    surface_faces.append(
                        (0, [(v.x, v.y, v.z) for v in vertices], triangles))
                packed = protocol.pack_mesh(surface_faces)
                if packed["positions"]:
                    surfaces_out.append({
                        "name": obj.Name,
                        "label": obj.Label,
                        "positions": packed["positions"],
                        "indices": packed["indices"],
                    })
            else:
                for i, edge in enumerate(shape.Edges):
                    try:
                        points = edge.discretize(Deviation=0.1)
                    except Exception:
                        continue
                    surface_lines.append(
                        (i, [(p.x, p.y, p.z) for p in points]))
        if surfaces_out:
            mesh["surfaces"] = surfaces_out
        if surface_lines:
            packed = protocol.pack_edges(surface_lines)
            mesh["curves"] = {"positions": packed["positions"],
                              "indices": packed["indices"]}
        # Esquisses libres : polylignes 3D pour le viewport. Le Shape
        # d'un SketchObject est déjà posé dans l'espace et n'inclut pas
        # la géométrie de construction (Construction / getConstruction).
        sketches_out = []
        for sk in self._free_sketches():
            shape = getattr(sk, "Shape", None)
            if shape is None or not shape.Edges:
                continue
            lines = []
            for i, edge in enumerate(shape.Edges):
                try:
                    # Deviation= est rejeté sur les arêtes d'esquisse
                    # (keyword OCCT : Deflection).
                    points = edge.discretize(Deflection=0.1)
                except Exception:
                    try:
                        points = edge.discretize(Number=24)
                    except Exception:
                        continue
                lines.append((i, [(p.x, p.y, p.z) for p in points]))
            packed = protocol.pack_edges(lines)
            if not packed["positions"]:
                continue
            sketches_out.append({
                "name": sk.Name,
                "label": sk.Label,
                "positions": packed["positions"],
                "indices": packed["indices"],
            })
        if sketches_out:
            mesh["sketches"] = sketches_out
        self._plugins.contribute_mesh(self, mesh, deviation)
        return mesh

    def tessellate_edges(self, deviation=0.05):
        """Per-edge polylines of the body's current shape.

        Edge-by-edge on purpose — see ``protocol.pack_edges``: a raycast
        hit maps to exactly one OCCT edge, same contract as ``tessellate``
        for faces. Ids are Edge indices, so ``Edge{id+1}`` server-side.
        """
        from . import protocol
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Edges:
            return protocol.pack_edges([])
        lines = []
        for i, edge in enumerate(shape.Edges):
            try:
                points = edge.discretize(Deviation=float(deviation))
            except Exception:
                try:
                    points = edge.discretize(Number=24)
                except Exception:
                    continue  # arête dégénérée : les ids restent justes
            lines.append((i, [(p.x, p.y, p.z) for p in points],
                          float(edge.Length)))
        return protocol.pack_edges(lines)

    # -- M2 : sketch editing --------------------------------------------

    #: Exact-match tolerance for auto-constraints. The client snaps and
    #: sends identical coordinates; this only recognizes that decision.
    _SNAP_TOL = 1e-7

    def _coincident_2d(self, x1, y1, x2, y2):
        import math
        return math.hypot(float(x2) - float(x1),
                          float(y2) - float(y1)) < self._SNAP_TOL

    def _get_sketch(self, name):
        obj = self._require_doc().getObject(name)
        if obj is None or obj.TypeId != "Sketcher::SketchObject":
            raise KernelError("esquisse inconnue : {}".format(name))
        return obj

    def sketch_start(self, face=None, plane=None, datum=None):
        """Open a new empty sketch — XY by default, a picked face, a
        named origin plane (XY/XZ/YZ), or a datum plane by name."""
        body = self._require_body()
        doc = self._require_doc()
        # La transaction de sketch_start est ouverte, pas encore validée :
        # UndoCount est encore celui d'avant l'esquisse.
        mark = doc.UndoCount
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        self._sketch_session = {"sketch": sketch.Name, "mark": mark,
                                "snapshot": None}
        sketch.Label = self._t("Esquisse")
        if face is not None:
            self._attach_to_face(sketch, face)
        elif datum is not None:
            target = doc.getObject(str(datum))
            if target is None or target.TypeId != "PartDesign::Plane":
                raise KernelError(
                    "plan de référence inconnu : {}".format(datum))
            self._attach_to_support(sketch, [(target, ("",))])
        elif plane is not None:
            role = self._PLANE_ROLES.get(str(plane).upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
            self._attach_to_support(
                sketch, [(self._origin_feature(role), ("",))])
        doc.recompute()  # resolves the placement before the client reads it
        return self.sketch_state(sketch.Name)

    def sketch_edit(self, feature):
        """Re-enter an existing sketch."""
        sk = self._get_sketch(feature)
        doc = self._require_doc()
        self._sketch_session = {
            "sketch": sk.Name, "mark": doc.UndoCount,
            # Les glisser (sketch_move) ne passent pas par une transaction :
            # l'instantané les rattrape.
            "snapshot": (list(sk.Geometry), list(sk.Constraints)),
        }
        return self.sketch_state(sk.Name)

    def sketch_cancel(self, sketch):
        """Quitter l'esquisse sans garder les modifications.

        Défait les transactions ouvertes depuis l'entrée en esquisse —
        une esquisse neuve disparaît — puis restaure la géométrie et les
        contraintes d'une esquisse rééditée (les glisser n'ont pas de
        transaction)."""
        doc = self._require_doc()
        session = self._sketch_session
        self._sketch_session = None
        if not session or session["sketch"] != str(sketch):
            return self.get_tree()
        while doc.UndoCount > session["mark"] and doc.UndoNames:
            doc.undo()
        sk = doc.getObject(session["sketch"])
        if sk is not None and session["snapshot"] is not None:
            geometry, constraints = session["snapshot"]
            sk.Constraints = []
            sk.Geometry = geometry
            sk.Constraints = constraints
        doc.recompute()
        return self.get_tree()

    def sketch_state(self, sketch):
        """Everything the client needs to draw the sketch.

        Geometry in sketch-local 2D, dimensional constraints with values,
        degrees of freedom, and the placement matrix (row-major, which is
        what THREE.Matrix4.set expects) to position the plane in 3D.
        """
        sk = self._get_sketch(sketch)
        entities = []
        for gid, geo in enumerate(sk.Geometry):
            if geo.TypeId == "Part::GeomLineSegment":
                entity = {
                    "id": gid, "type": "line",
                    "p1": [geo.StartPoint.x, geo.StartPoint.y],
                    "p2": [geo.EndPoint.x, geo.EndPoint.y]}
            elif geo.TypeId == "Part::GeomCircle":
                entity = {
                    "id": gid, "type": "circle",
                    "c": [geo.Center.x, geo.Center.y],
                    "r": float(geo.Radius)}
            elif geo.TypeId == "Part::GeomArcOfCircle":
                entity = {
                    "id": gid, "type": "arc",
                    "c": [geo.Center.x, geo.Center.y],
                    "r": float(geo.Radius),
                    "p1": [geo.StartPoint.x, geo.StartPoint.y],
                    "p2": [geo.EndPoint.x, geo.EndPoint.y]}
            else:
                type_id = geo.TypeId
                entity = {"id": gid, "type": "other", "kind": type_id}
                try:
                    # Splines, ellipses, coniques : une polyligne suffit
                    # au client pour afficher et viser n'importe quelle
                    # courbe.
                    points = geo.toShape().discretize(Number=24)
                    entity["type"] = "poly"
                    entity["points"] = [[p.x, p.y] for p in points]
                except Exception:
                    pass
                self._enrich_poly_entity(entity, geo, type_id)
            entity["construction"] = self._is_construction(sk, gid, geo)
            entities.append(entity)
        import re
        exprs = {}  # constraint index -> expression
        names = {c.Name: cid for cid, c in enumerate(sk.Constraints)
                 if c.Name}
        for path, expr in self._expression_map(sk).items():
            by_index = re.match(r"^Constraints\[(\d+)\]$", path)
            by_name = re.match(r"^Constraints\.(.+)$", path)
            if by_index:
                exprs[int(by_index.group(1))] = expr
            elif by_name and by_name.group(1) in names:
                exprs[names[by_name.group(1)]] = expr
        dims = []
        for cid, constraint in enumerate(sk.Constraints):
            if constraint.Type in ("Distance", "DistanceX", "DistanceY",
                                   "Radius", "Diameter", "Angle"):
                dims.append({"id": cid, "type": constraint.Type,
                             "value": float(constraint.Value),
                             "name": constraint.Name or "",
                             "expr": exprs.get(cid, ""),
                             "geo": constraint.First})
        constraints = []
        for cid, c in enumerate(sk.Constraints):
            geos, pos = [], []
            for geo_attr, pos_attr in (("First", "FirstPos"),
                                       ("Second", "SecondPos"),
                                       ("Third", "ThirdPos")):
                g = getattr(c, geo_attr, None)
                # -2000 = GeoUndef chez Sketcher : « pas de géométrie »
                geos.append(None if g is None or g <= -2000 else int(g))
                p = getattr(c, pos_attr, 0)
                pos.append(int(getattr(p, "value", p) or 0))
            constraints.append({
                "id": cid, "type": c.Type, "geos": geos, "pos": pos,
                "value": float(c.Value),
                "driving": bool(getattr(c, "Driving", True))})
        solver_code = 0
        try:
            solver_code = int(sk.solve())
        except Exception:
            pass
        # Bleu / blanc / rouge côté client : entité libre, définie, en trop.
        from engine.sketchstatus import entity_status, sketch_definition
        try:
            dependent = list(sk.getGeometryWithDependentParameters())
        except Exception:
            dependent = []
        status = entity_status(
            len(entities), dependent,
            [c["geos"] for c in constraints],
            list(getattr(sk, "ConflictingConstraints", []) or []),
            list(getattr(sk, "RedundantConstraints", []) or []))
        for entity, state in zip(entities, status):
            entity["status"] = state
        dof = None
        try:
            dof = int(sk.getLastDoF())
        except Exception:
            pass
        if dof is None:
            # FreeCAD 1.0 : propriété DoF (getLastDoF a disparu).
            try:
                dof = int(sk.DoF)
            except Exception:
                pass
        matrix = sk.Placement.Matrix.A
        return {
            "sketch": sk.Name,
            "label": sk.Label,
            "support": self._sketch_support_label(sk),
            "entities": entities,
            "dims": dims,
            "constraints": constraints,
            "dof": dof,
            "fullyConstrained": bool(getattr(sk, "FullyConstrained", False)),
            "definition": sketch_definition(status, solver_code),
            "placement": [float(v) for v in matrix],
        }

    @staticmethod
    def _sketch_definition(sk):
        """under | full | over — préfixe (-) / (+) de l'arbre."""
        from engine.sketchstatus import definition_from_flags
        return definition_from_flags(
            bool(getattr(sk, "FullyConstrained", False)),
            getattr(sk, "ConflictingConstraints", []),
            getattr(sk, "RedundantConstraints", []),
            getattr(sk, "MalformedConstraints", []))

    def _sketch_support_label(self, sk):
        """Label du plan ou de la face d'appui — pour le panneau infos."""
        from engine.vocab import label_for_origin
        support = (getattr(sk, "AttachmentSupport", None)
                   or getattr(sk, "Support", None))
        try:
            for obj, subs in list(support or ()):
                if obj is None:
                    continue
                # Plan d'origine : vocabulaire SolidWorks (« Plan de
                # face ») via le Name interne ; sinon label utilisateur.
                name = getattr(obj, "Name", "") or ""
                label = label_for_origin(name, self.lang)
                if label == name:
                    label = obj.Label
                for sub in subs or ():
                    text = str(sub)
                    if text.startswith("Face"):
                        return "{} · {}".format(label, text)
                return label
        except Exception:
            pass
        return ""

    @staticmethod
    def _enrich_poly_entity(entity, geo, type_id):
        """Champs du panneau propriétés (P025) : ellipse, spline, polyligne."""
        if type_id in ("Part::GeomEllipse", "Part::GeomArcOfEllipse"):
            entity["kind"] = "ellipse"
            try:
                center = geo.Center
                entity["c"] = [float(center.x), float(center.y)]
                entity["rx"] = float(geo.MajorRadius)
                entity["ry"] = float(geo.MinorRadius)
            except Exception:
                pass
            return
        if "BSpline" in type_id or "Bezier" in type_id:
            entity["kind"] = "spline"
            npoints = None
            try:
                npoints = int(geo.NbPoles)
            except Exception:
                getter = getattr(geo, "getPoles", None)
                if callable(getter):
                    try:
                        npoints = len(getter())
                    except Exception:
                        pass
            if npoints is None and entity.get("points"):
                npoints = len(entity["points"])
            if npoints is not None:
                entity["npoints"] = npoints
            return
        if entity.get("points"):
            entity["npoints"] = len(entity["points"])

    @staticmethod
    def _endpoints_of(geo):
        """(Sketcher pos, point) pairs a snap can land on — lines and arcs."""
        if geo.TypeId in ("Part::GeomLineSegment", "Part::GeomArcOfCircle"):
            return ((1, geo.StartPoint), (2, geo.EndPoint))
        return ()

    def _auto_constrain(self, sk, gid):
        """The SolidWorks reflexes: snap becomes coincident, near-axis
        becomes horizontal/vertical.

        The client decides (it snapped and sent exact coordinates); this
        turns that decision into constraints so the solver holds it.
        """
        import Sketcher
        C = Sketcher.Constraint
        geo = sk.Geometry[gid]
        for pos, point in self._endpoints_of(geo):
            for other in range(len(sk.Geometry)):
                if other == gid:
                    continue
                matched = False
                for opos, opoint in self._endpoints_of(sk.Geometry[other]):
                    if point.distanceToPoint(opoint) < self._SNAP_TOL:
                        sk.addConstraint(C("Coincident", gid, pos,
                                           other, opos))
                        matched = True
                        break
                if matched:
                    break
        if geo.TypeId != "Part::GeomLineSegment":
            return
        dx = abs(geo.EndPoint.x - geo.StartPoint.x)
        dy = abs(geo.EndPoint.y - geo.StartPoint.y)
        if dx > self._SNAP_TOL or dy > self._SNAP_TOL:  # not degenerate
            if dy < self._SNAP_TOL:
                sk.addConstraint(C("Horizontal", gid))
            elif dx < self._SNAP_TOL:
                sk.addConstraint(C("Vertical", gid))

    def sketch_add_line(self, sketch, x1, y1, x2, y2):
        import Part
        sk = self._get_sketch(sketch)
        if self._coincident_2d(x1, y1, x2, y2):
            raise KernelError(
                "segment de longueur nulle — les deux points coïncident")
        V = self._app().Vector
        gid = sk.addGeometry(Part.LineSegment(
            V(float(x1), float(y1), 0), V(float(x2), float(y2), 0)), False)
        self._auto_constrain(sk, gid)
        return self.sketch_state(sketch)

    def sketch_add_arc(self, sketch, cx, cy, r, a1, a2):
        """Arc de cercle — angles en radians, sens trigonométrique."""
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        App = self._app()
        circle = Part.Circle(App.Vector(float(cx), float(cy), 0),
                             App.Vector(0, 0, 1), float(r))
        gid = sk.addGeometry(
            Part.ArcOfCircle(circle, float(a1), float(a2)), False)
        self._auto_constrain(sk, gid)
        return self.sketch_state(sketch)

    def sketch_add_spline(self, sketch, points):
        """Spline interpolée par les points cliqués — la spline SolidWorks."""
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        if not isinstance(points, (list, tuple)) or len(points) < 3:
            raise KernelError("une spline demande au moins trois points")
        vectors = []
        for p in points:
            try:
                x, y = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            if vectors and self._coincident_2d(
                    vectors[-1].x, vectors[-1].y, x, y):
                raise KernelError(
                    "segment de longueur nulle — deux points de contrôle "
                    "consécutifs coïncident")
            vectors.append(App.Vector(x, y, 0))
        try:
            curve = Part.BSplineCurve()
            curve.interpolate(vectors)
            sk.addGeometry(curve, False)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_ellipse(self, sketch, cx, cy, rx, ry, angle=0.0):
        """Ellipse par centre + rayons, inclinée de ``angle`` degrés."""
        import math
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        rx, ry = float(rx), float(ry)
        if rx <= 0 or ry <= 0:
            raise KernelError("les deux rayons doivent être positifs")
        tilt = float(angle)
        if ry > rx:
            rx, ry = ry, rx
            tilt += 90.0
        try:
            ellipse = Part.Ellipse(App.Vector(float(cx), float(cy), 0),
                                   rx, ry)
            try:
                ellipse.AngleXU = math.radians(tilt)
            except AttributeError:
                pass
            sk.addGeometry(ellipse, False)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_mirror(self, sketch, geos, axis):
        """Symétrie d'entités : copies miroir par rapport à une ligne."""
        sk = self._get_sketch(sketch)
        ids = [int(g) for g in (geos or ())]
        if not ids:
            raise KernelError("sélectionnez les entités à symétriser")
        axis_id = int(axis)
        if axis_id in ids:
            raise KernelError("l'axe ne peut pas faire partie de la "
                              "sélection")
        try:
            sk.addSymmetric(ids, axis_id)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_array(self, sketch, geos, dx, dy, cols, rows):
        """Réseau linéaire d'entités d'esquisse (grille cols × rows)."""
        sk = self._get_sketch(sketch)
        App = self._app()
        ids = [int(g) for g in (geos or ())]
        if not ids:
            raise KernelError("sélectionnez les entités à répéter")
        cols, rows = int(cols), int(rows)
        if cols < 1 or rows < 1 or cols * rows < 2:
            raise KernelError("au moins deux occurrences (cols × rows)")
        displacement = App.Vector(float(dx), float(dy), 0)
        try:
            sk.addRectangularArray(ids, displacement, False, cols, rows,
                                   True)
        except TypeError:
            sk.addRectangularArray(ids, displacement, False, cols, rows)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_offset(self, sketch, geos, distance, reversed=False):
        """Décalage d'entités : offset 2D non contraint (makeOffset2D).

        Le « Décalage » paramétrique SolidWorks (contraintes d'égalité
        de distance) viendra plus tard — les copies restent libres.
        """
        import Part
        sk = self._get_sketch(sketch)
        App = self._app()
        ids = []
        seen = set()
        for raw in geos or ():
            try:
                gid = int(raw)
            except (TypeError, ValueError):
                raise KernelError(
                    "identifiant d'entité invalide : {}".format(raw))
            if gid in seen:
                continue
            seen.add(gid)
            if gid < 0 or gid >= len(sk.Geometry):
                raise KernelError("entité inconnue : {}".format(gid))
            ids.append(gid)
        if not ids:
            raise KernelError("sélectionnez les entités à décaler")
        dist = float(distance)
        if dist <= 0:
            raise KernelError("la distance doit être positive")
        signed = -dist if reversed else dist

        edges = []
        for gid in ids:
            try:
                shape = sk.Geometry[gid].toShape()
            except Exception as exc:  # noqa: BLE001
                raise KernelError(_explain(exc))
            found = [shape] if shape.ShapeType == "Edge" else list(shape.Edges)
            if not found:
                raise KernelError(
                    "les entités à décaler doivent former une chaîne connexe")
            edges.extend(found)
        try:
            chains = Part.sortEdges(edges)
        except Exception:  # noqa: BLE001
            raise KernelError(
                "les entités à décaler doivent former une chaîne connexe")
        if len(chains) != 1:
            raise KernelError(
                "les entités à décaler doivent former une chaîne connexe")
        try:
            wire = Part.Wire(chains[0])
            offset_shape = wire.makeOffset2D(signed)
        except Exception as exc:  # noqa: BLE001
            raise KernelError("décalage impossible : {}".format(_explain(exc)))

        offset_edges = list(offset_shape.Edges)
        if not offset_edges:
            raise KernelError("décalage impossible : aucun contour produit")

        # Tout ou rien : convertir d'abord, n'injecter qu'ensuite.
        geoms = [self._geom_from_offset_edge(edge, Part, App)
                 for edge in offset_edges]
        for geom in geoms:
            sk.addGeometry(geom, False)
        return self.sketch_state(sketch)

    @staticmethod
    def _geom_from_offset_edge(edge, Part, App):
        """Arête d'offset → géométrie d'esquisse (ligne, arc ou cercle)."""
        import math
        curve = edge.Curve
        tid = curve.TypeId
        V = App.Vector
        if tid in ("Part::GeomLine", "Part::GeomLineSegment"):
            verts = edge.Vertexes
            if len(verts) != 2:
                raise KernelError("géométrie non décalable pour l'instant")
            return Part.LineSegment(
                V(verts[0].Point.x, verts[0].Point.y, 0),
                V(verts[1].Point.x, verts[1].Point.y, 0))
        if tid == "Part::GeomCircle":
            span = abs(edge.LastParameter - edge.FirstParameter)
            full = (bool(getattr(edge, "Closed", False))
                    or abs(span - 2 * math.pi) < 1e-4)
            if full:
                return Part.Circle(
                    V(curve.Center.x, curve.Center.y, 0),
                    V(0, 0, 1), float(curve.Radius))
            p1 = edge.valueAt(edge.FirstParameter)
            p2 = edge.valueAt(
                0.5 * (edge.FirstParameter + edge.LastParameter))
            p3 = edge.valueAt(edge.LastParameter)
            return Part.ArcOfCircle(
                V(p1.x, p1.y, 0), V(p2.x, p2.y, 0), V(p3.x, p3.y, 0))
        raise KernelError("géométrie non décalable pour l'instant")

    def sketch_add_slot(self, sketch, x1, y1, x2, y2, width):
        """Rainure droite : deux arcs + deux lignes, tangences et rayons
        égaux posés d'emblée — le contour reste une rainure sous le solveur.
        """
        import math
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        w = float(width)
        p1x, p1y, p2x, p2y = (float(v) for v in (x1, y1, x2, y2))
        if w <= 0:
            raise KernelError("la largeur doit être positive")
        if math.hypot(p2x - p1x, p2y - p1y) < 1e-9:
            raise KernelError("les deux centres de la rainure sont confondus")
        r = w / 2.0
        theta = math.atan2(p2y - p1y, p2x - p1x)
        ux, uy = math.cos(theta + math.pi / 2), math.sin(theta + math.pi / 2)
        V = self._app().Vector
        z_axis = V(0, 0, 1)
        base = len(sk.Geometry)
        # Cap at p2 (CCW through +direction), top line, cap at p1, bottom.
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p2x, p2y, 0), z_axis, r),
            theta - math.pi / 2, theta + math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p2x + r * ux, p2y + r * uy, 0),
            V(p1x + r * ux, p1y + r * uy, 0)), False)
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p1x, p1y, 0), z_axis, r),
            theta + math.pi / 2, theta + 3 * math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p1x - r * ux, p1y - r * uy, 0),
            V(p2x - r * ux, p2y - r * uy, 0)), False)
        C = Sketcher.Constraint
        try:
            # Endpoint-to-endpoint tangency implies coincidence: the
            # standard Sketcher slot recipe.
            sk.addConstraint(C("Tangent", base + 0, 2, base + 1, 1))
            sk.addConstraint(C("Tangent", base + 1, 2, base + 2, 1))
            sk.addConstraint(C("Tangent", base + 2, 2, base + 3, 1))
            sk.addConstraint(C("Tangent", base + 3, 2, base + 0, 1))
            sk.addConstraint(C("Equal", base + 0, base + 2))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_polygon(self, sketch, cx, cy, x, y, sides):
        """Polygone régulier (centre + un sommet), via l'outil Sketcher."""
        sk = self._get_sketch(sketch)
        n = int(sides)
        if n < 3:
            raise KernelError("un polygone a au moins 3 côtés")
        try:
            from ProfileLib import RegularPolygon
        except ImportError:
            raise KernelError("outil polygone indisponible sur cette "
                              "version de FreeCAD")
        V = self._app().Vector
        center = V(float(cx), float(cy), 0)
        corner = V(float(x), float(y), 0)
        try:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner, False)
        except TypeError:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_fillet(self, sketch, geo1, geo2, x1, y1, x2, y2, radius):
        """Congé d'esquisse entre deux lignes, aux points cliqués."""
        sk = self._get_sketch(sketch)
        if float(radius) <= 0:
            raise KernelError("le rayon doit être positif")
        V = self._app().Vector
        try:
            sk.fillet(int(geo1), int(geo2),
                      V(float(x1), float(y1), 0), V(float(x2), float(y2), 0),
                      float(radius))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_trim(self, sketch, geo, x, y):
        """Ajuster : supprime le tronçon cliqué jusqu'aux intersections."""
        sk = self._get_sketch(sketch)
        V = self._app().Vector
        try:
            sk.trim(int(geo), V(float(x), float(y), 0))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _constraint_for(self, sk, kind, geo1, point1, geo2, point2, geo3):
        """Build the Sketcher constraint for one designer-facing kind.

        The SolidWorks relation set maps onto Sketcher with a few
        translations: colinéaire = Tangent between lines, concentrique =
        Coincident of centers, milieu = Symmetric of the line's endpoints
        about the point, fixe = Block.
        """
        import Sketcher
        C = Sketcher.Constraint
        line = "Part::GeomLineSegment"
        round_types = ("Part::GeomCircle", "Part::GeomArcOfCircle")
        g1 = int(geo1)
        if kind in ("horizontal", "vertical"):
            return C(kind.capitalize(), g1)
        if kind == "fixed":
            return C("Block", g1)
        if geo2 is None:
            raise KernelError(
                "{} : sélectionnez deux entités".format(kind))
        g2 = int(geo2)
        if kind == "coincident":
            if point1 is None or point2 is None:
                raise KernelError("coïncidence : cliquez deux points "
                                  "(extrémités ou centres)")
            return C("Coincident", g1, int(point1), g2, int(point2))
        if kind == "concentric":
            for g in (g1, g2):
                if sk.Geometry[g].TypeId not in round_types:
                    raise KernelError("concentrique : deux cercles ou arcs")
            return C("Coincident", g1, 3, g2, 3)
        if kind == "collinear":
            for g in (g1, g2):
                if sk.Geometry[g].TypeId != line:
                    raise KernelError("colinéaire : deux lignes")
            return C("Tangent", g1, g2)
        if kind == "midpoint":
            # point (souvent un centre) au milieu d'une ligne — dans un
            # ordre ou l'autre.
            if sk.Geometry[g1].TypeId == line and point2 is not None:
                return C("Symmetric", g1, 1, g1, 2, g2, int(point2))
            if sk.Geometry[g2].TypeId == line and point1 is not None:
                return C("Symmetric", g2, 1, g2, 2, g1, int(point1))
            raise KernelError("milieu : un point et une ligne")
        if kind == "symmetric":
            if geo3 is None or point1 is None or point2 is None:
                raise KernelError(
                    "symétrique : deux points puis la ligne d'axe")
            g3 = int(geo3)
            if sk.Geometry[g3].TypeId != line:
                raise KernelError("symétrique : le 3e élément doit être "
                                  "une ligne (l'axe)")
            return C("Symmetric", g1, int(point1), g2, int(point2), g3)
        if kind in ("parallel", "perpendicular", "equal", "tangent"):
            names = {"parallel": "Parallel", "perpendicular": "Perpendicular",
                     "equal": "Equal", "tangent": "Tangent"}
            return C(names[kind], g1, g2)
        raise KernelError(
            "contrainte inconnue « {} » — attendu : horizontal, vertical, "
            "coincident, parallel, perpendicular, equal, tangent, "
            "concentric, collinear, midpoint, symmetric, fixed".format(kind))

    def sketch_constrain(self, sketch, kind, geo1, point1=None,
                         geo2=None, point2=None, geo3=None):
        """Contrainte manuelle. Points au sens Sketcher : 1 départ, 2 fin,
        3 centre. ``symmetric`` prend trois entités (2 points + l'axe)."""
        sk = self._get_sketch(sketch)
        try:
            constraint = self._constraint_for(
                sk, str(kind), geo1, point1, geo2, point2, geo3)
            sk.addConstraint(constraint)
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_circle(self, sketch, cx, cy, r):
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        App = self._app()
        sk.addGeometry(Part.Circle(
            App.Vector(float(cx), float(cy), 0),
            App.Vector(0, 0, 1), float(r)), False)
        return self.sketch_state(sketch)

    def sketch_move(self, sketch, geo, point, x, y):
        """Drag: move one point, let the solver follow. ``point`` is the
        Sketcher convention — 1 start, 2 end, 3 center, 0 whole curve.

        The API was renamed across FreeCAD versions (movePoint →
        moveGeometry, plus a grouped moveGeometries), so this tries the
        known spellings in order — 1.1.3 has no ``movePoint`` at all,
        which the instrumented selftest caught on a real install.
        """
        sk = self._get_sketch(sketch)
        gid, pos = int(geo), int(point)
        target = self._app().Vector(float(x), float(y), 0)
        attempts = (
            ("moveGeometry", lambda fn: fn(gid, pos, target, 0)),
            ("movePoint", lambda fn: fn(gid, pos, target, 0)),
            ("moveGeometries", lambda fn: fn([(gid, pos)], target, False)),
        )
        tried = []
        for name, invoke in attempts:
            fn = getattr(sk, name, None)
            if fn is None:
                continue
            tried.append(name)
            try:
                invoke(fn)
                return self.sketch_state(sketch)
            except TypeError:
                continue  # exists but wants another signature: next spelling
            except Exception as exc:  # noqa: BLE001 - solver refusal
                raise KernelError(_explain(exc))
        raise KernelError(
            "aucune API de déplacement compatible sur cette version de "
            "FreeCAD (essayé : {})".format(", ".join(tried) or "aucune"))

    @staticmethod
    def _point_of(geo, pos):
        """Sketcher point convention: 1 start, 2 end, 3 center."""
        if pos == 3:
            return geo.Center
        if pos == 2:
            return geo.EndPoint
        return geo.StartPoint

    @staticmethod
    def _distance_point_line(p, a, b):
        import math
        abx, aby = b.x - a.x, b.y - a.y
        denominator = math.hypot(abx, aby)
        if denominator < 1e-12:
            return 0.0
        return abs(abx * (p.y - a.y) - aby * (p.x - a.x)) / denominator

    def _dim_two(self, sk, g1, g2, point, point2, value):
        """Smart dimension between two entities — the pair decides the
        constraint, as under the SolidWorks cursor: two points → distance,
        point + line → distance, parallel lines → distance, otherwise angle
        (radians on the wire; the client displays degrees)."""
        import math
        import Sketcher
        C = Sketcher.Constraint
        if point is None and point2 is not None:
            # Normalize "line then point" to "point then line".
            g1, g2 = g2, g1
            point, point2 = point2, None
        e1, e2 = sk.Geometry[g1], sk.Geometry[g2]
        line = "Part::GeomLineSegment"
        if point is not None and point2 is not None:
            v1 = self._point_of(e1, int(point))
            v2 = self._point_of(e2, int(point2))
            distance = value if value is not None else v1.distanceToPoint(v2)
            return C("Distance", g1, int(point), g2, int(point2),
                     float(distance))
        if point is not None and e2.TypeId == line:
            v1 = self._point_of(e1, int(point))
            distance = (value if value is not None else
                        self._distance_point_line(
                            v1, e2.StartPoint, e2.EndPoint))
            return C("Distance", g1, int(point), g2, float(distance))
        if e1.TypeId == line and e2.TypeId == line:
            d1x = e1.EndPoint.x - e1.StartPoint.x
            d1y = e1.EndPoint.y - e1.StartPoint.y
            d2x = e2.EndPoint.x - e2.StartPoint.x
            d2y = e2.EndPoint.y - e2.StartPoint.y
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-7 * math.hypot(d1x, d1y) * math.hypot(d2x, d2y):
                distance = (value if value is not None else
                            self._distance_point_line(
                                e1.StartPoint, e2.StartPoint, e2.EndPoint))
                return C("Distance", g1, 1, g2, float(distance))
            angle = (value if value is not None else
                     abs(math.atan2(cross, d1x * d2x + d1y * d2y)))
            return C("Angle", g1, g2, float(angle))
        raise KernelError("cote non gérée entre ces deux entités — "
                          "deux points, un point et une ligne, ou deux "
                          "lignes")

    def sketch_dim(self, sketch, geo, value=None,
                   geo2=None, point=None, point2=None):
        """Smart dimension: length on a line, diameter on a circle,
        radius on an arc, distance/angle between two entities.

        Driving, SolidWorks-style: dimension it and the geometry obeys.
        """
        import Sketcher
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if gid < 0 or gid >= len(sk.Geometry):
            raise KernelError("géométrie inconnue : {}".format(geo))
        try:
            if geo2 is not None:
                g2 = int(geo2)
                if g2 < 0 or g2 >= len(sk.Geometry):
                    raise KernelError("géométrie inconnue : {}".format(geo2))
                sk.addConstraint(
                    self._dim_two(sk, gid, g2, point, point2, value))
                return self.sketch_state(sketch)
            target = sk.Geometry[gid]
            if target.TypeId == "Part::GeomLineSegment":
                length = (value if value is not None
                          else target.StartPoint.distanceToPoint(
                              target.EndPoint))
                sk.addConstraint(Sketcher.Constraint(
                    "Distance", gid, float(length)))
            elif target.TypeId == "Part::GeomCircle":
                # Un cercle se cote au diamètre, un arc au rayon.
                diameter = (value if value is not None
                            else 2 * target.Radius)
                sk.addConstraint(Sketcher.Constraint(
                    "Diameter", gid, float(diameter)))
            elif target.TypeId == "Part::GeomArcOfCircle":
                radius = value if value is not None else target.Radius
                sk.addConstraint(Sketcher.Constraint(
                    "Radius", gid, float(radius)))
            else:
                raise KernelError("cote non gérée sur ce type de géométrie")
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_set_dim(self, sketch, dim, value=None, name=None, expr=None):
        """Edit a dimension — the double-click-a-dim gesture, complete:
        value, **name** (``largeur``) and **expression** (``largeur/2``).

        An expression takes over the value; setting a plain value clears
        any expression. Names make the SolidWorks equation workflow:
        name a dim, then reference it from any other dim or feature.
        """
        sk = self._get_sketch(sketch)
        idx = int(dim)
        if idx < 0 or idx >= len(sk.Constraints):
            raise KernelError("cote inconnue : {}".format(dim))
        try:
            if name is not None:
                name = str(name).strip()
                if name and not self._valid_identifier(name):
                    raise KernelError(
                        "nom invalide « {} » — lettres, chiffres et _ "
                        "seulement".format(name))
                sk.renameConstraint(idx, name)
            path = "Constraints[{}]".format(idx)
            if expr is not None and str(expr).strip():
                sk.setExpression(path, self._user_expression(expr))
            elif value is not None:
                try:
                    sk.setExpression(path, None)
                except Exception:
                    pass
                sk.setDatum(idx, float(value))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        if self._assembly:
            self._require_doc().recompute()
        else:
            # _recompute applique aussi PlacementList des semis : sans le
            # second passage, la cote change et l'écran ne suit pas.
            self._recompute()
        return self.sketch_state(sketch)

    #: Libellé français des types de contraintes, pour le panneau Relations.
    _CONSTRAINT_LABELS = {
        "Coincident": "Coïncidente", "Horizontal": "Horizontale",
        "Vertical": "Verticale", "Parallel": "Parallèle",
        "Perpendicular": "Perpendiculaire", "Tangent": "Tangente",
        "Equal": "Égale", "Symmetric": "Symétrique", "Block": "Fixe",
        "PointOnObject": "Sur l'entité", "Distance": "Cote (distance)",
        "DistanceX": "Cote (horizontale)", "DistanceY": "Cote (verticale)",
        "Radius": "Cote (rayon)", "Diameter": "Cote (diamètre)",
        "Angle": "Cote (angle)",
    }

    def sketch_constraints(self, sketch, geo=None):
        """Les relations de l'esquisse — filtrables par entité.

        C'est la sortie du mur des esquisses sur-contraintes : voir ce qui
        tient une entité, et pouvoir supprimer la relation de trop.
        """
        sk = self._get_sketch(sketch)
        undefined = -2000  # Sketcher.GeoUndef
        items = []
        for cid, constraint in enumerate(sk.Constraints):
            geos = [g for g in (constraint.First, constraint.Second,
                                constraint.Third)
                    if g is not None and g != undefined]
            if geo is not None and int(geo) not in geos:
                continue
            entry = {
                "id": cid,
                "type": constraint.Type,
                "label": self._CONSTRAINT_LABELS.get(
                    constraint.Type, constraint.Type),
                "geos": geos,
                "name": constraint.Name or "",
            }
            if constraint.Type in ("Distance", "DistanceX", "DistanceY",
                                   "Radius", "Diameter", "Angle"):
                entry["value"] = float(constraint.Value)
            items.append(entry)
        return {"constraints": items}

    def sketch_delete_constraint(self, sketch, constraint):
        sk = self._get_sketch(sketch)
        idx = int(constraint)
        if idx < 0 or idx >= len(sk.Constraints):
            raise KernelError("relation inconnue : {}".format(constraint))
        try:
            sk.delConstraint(idx)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def _is_construction(self, sk, gid, geo):
        """Construction flag across API generations: attribute on old
        geometry objects, ``getConstruction`` on 1.x facades."""
        flag = getattr(geo, "Construction", None)
        if flag is not None:
            return bool(flag)
        getter = getattr(sk, "getConstruction", None)
        if getter is not None:
            try:
                return bool(getter(gid))
            except Exception:
                pass
        return False

    def sketch_toggle_construction(self, sketch, geo):
        """Basculer une entité en géométrie de construction, et retour."""
        sk = self._get_sketch(sketch)
        try:
            sk.toggleConstruction(int(geo))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_delete_geo(self, sketch, geo):
        sk = self._get_sketch(sketch)
        try:
            sk.delGeometry(int(geo))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_convert(self, sketch, face=None):
        """Convertir les entités : le contour d'une face devient de la
        géométrie d'esquisse réelle, bloquée (Block) — le geste SolidWorks
        « esquisse sur face → convertir → décaler/modifier ».

        Sans ``face``, la face porteuse de l'esquisse est utilisée.
        Lignes, cercles et arcs parallèles au plan sont convertis ; le
        reste est compté dans ``skipped``.
        """
        import math
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        body = self._require_body()
        target = None
        if face is not None:
            faces = body.Shape.Faces
            index = int(face)
            if index < 0 or index >= len(faces):
                raise KernelError("face inconnue : {}".format(face))
            target = faces[index]
        else:
            support = (getattr(sk, "AttachmentSupport", None)
                       or getattr(sk, "Support", None))
            try:
                for obj, subs in list(support or ()):
                    for sub in subs:
                        if str(sub).startswith("Face"):
                            target = obj.Shape.Faces[int(str(sub)[4:]) - 1]
                            break
                    if target is not None:
                        break
            except Exception:
                target = None
            if target is None:
                raise KernelError(
                    "l'esquisse n'est pas posée sur une face — cliquez "
                    "d'abord une face, ou passez face=<id>")
        inverse = sk.Placement.inverse()
        V = self._app().Vector
        C = Sketcher.Constraint
        added = skipped = 0
        for edge in target.Edges:
            curve = edge.Curve
            kind = type(curve).__name__
            gid = None
            try:
                if kind == "Line":
                    p1 = inverse.multVec(edge.Vertexes[0].Point)
                    p2 = inverse.multVec(edge.Vertexes[-1].Point)
                    if p1.distanceToPoint(p2) < 1e-9:
                        skipped += 1
                        continue
                    gid = sk.addGeometry(Part.LineSegment(
                        V(p1.x, p1.y, 0), V(p2.x, p2.y, 0)), False)
                elif kind == "Circle":
                    axis_local = inverse.Rotation.multVec(curve.Axis)
                    if abs(axis_local.z) < 0.99:
                        skipped += 1
                        continue
                    center = inverse.multVec(curve.Center)
                    circle = Part.Circle(V(center.x, center.y, 0),
                                         V(0, 0, 1), curve.Radius)
                    if edge.isClosed():
                        gid = sk.addGeometry(circle, False)
                    else:
                        s = inverse.multVec(edge.Vertexes[0].Point)
                        e = inverse.multVec(edge.Vertexes[-1].Point)
                        m = inverse.multVec(edge.valueAt(
                            (edge.FirstParameter + edge.LastParameter) / 2))
                        a_s = math.atan2(s.y - center.y, s.x - center.x)
                        a_e = math.atan2(e.y - center.y, e.x - center.x)
                        a_m = math.atan2(m.y - center.y, m.x - center.x)

                        def onward(a, start):
                            return a + 2 * math.pi if a <= start else a
                        if onward(a_m, a_s) < onward(a_e, a_s):
                            a1, a2 = a_s, onward(a_e, a_s)
                        else:
                            a1, a2 = a_e, onward(a_s, a_e)
                        gid = sk.addGeometry(
                            Part.ArcOfCircle(circle, a1, a2), False)
                else:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            sk.addConstraint(C("Block", gid))
            added += 1
        if not added:
            raise KernelError("aucune arête convertible sur cette face "
                              "(lignes, cercles, arcs)")
        state = self.sketch_state(sketch)
        state["converted"] = added
        state["skipped"] = skipped
        return state

    def sketch_finish(self, sketch):
        """Close the sketch: recompute and hand back the feature tree."""
        self._get_sketch(sketch)
        self._sketch_session = None
        self._recompute()
        tree = self.get_tree()
        tree["open_profile"] = self._sketch_open_profile(sketch)
        return tree

    def _sketch_open_profile(self, sketch):
        """True si la géométrie réelle ne forme aucune boucle fermée.

        Esquisse vide ou 100 % construction : False — rien d'anormal,
        pas de message côté client. Au moins une boucle fermée : False.
        """
        import Part
        sk = self._get_sketch(sketch)
        edges = []
        for gid, geo in enumerate(sk.Geometry):
            if self._is_construction(sk, gid, geo):
                continue
            try:
                shape = geo.toShape()
            except Exception:
                continue
            if getattr(shape, "ShapeType", None) == "Edge":
                edges.append(shape)
            else:
                edges.extend(list(getattr(shape, "Edges", ()) or ()))
        if not edges:
            return False
        try:
            chains = Part.sortEdges(edges)
        except Exception:
            return True
        for chain in chains:
            try:
                if Part.Wire(chain).isClosed():
                    return False
            except Exception:
                continue
        if any(bool(getattr(edge, "Closed", False)) for edge in edges):
            return False
        return True

    def _top_face_id(self):
        """Index of the upward-facing face with the highest centroid.

        Used on the production path when a replayed sketch sits on a
        face: pick the current top rather than a stale face index.
        """
        body = self._require_body()
        best, best_z = None, None
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if normal.z <= UPWARD_Z:
                continue
            z = face.CenterOfMass.z
            if best_z is None or z > best_z:
                best, best_z = i, z
        if best is None:
            raise KernelError("aucune face orientée vers le haut")
        return best

    def _side_face_id(self):
        """Selftest helper: any vertical (side) face of the current shape."""
        body = self._require_body()
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if abs(normal.z) < 0.1:
                return i
        raise KernelError("aucune face latérale")


#: Ops recorded as one undo step each. Left out on purpose: document
#: lifecycle (new/open), read-only ops, undo/redo themselves, and
#: sketch_move — a drag streaming at ~20 Hz would shred the undo stack
#: into per-frame steps.
_TRANSACTIONAL = frozenset({
    "add_rect_sketch", "add_pad", "add_pocket", "add_fillet", "add_chamfer",
    "add_revolution", "add_groove", "add_mirror", "add_linear_pattern",
    "add_polar_pattern", "add_thickness", "add_draft", "add_hole",
    "add_datum_plane", "add_loft", "add_sweep", "add_helix",
    "add_body", "add_boolean", "set_body_color",
    "insert_component", "move_component", "add_joint", "solve_assembly",
    "surface_extrude", "surface_revolve", "surface_loft", "surface_sew",
    "surface_thicken", "add_curve3d", "sketch_convert", "add_text",
    "edit_text", "add_graph_feature", "edit_graph_feature",
    "add_repeat_feature", "edit_repeat_feature", "make_drawing",
    "set_param", "set_params", "rename",
    "set_variable", "delete_variable", "sketch_delete_constraint",
    "set_tip", "tip_to_end", "delete_feature",
    "sketch_start", "sketch_add_line", "sketch_add_circle", "sketch_dim",
    "sketch_set_dim", "sketch_delete_geo", "sketch_finish",
    "sketch_toggle_construction",
    "sketch_add_arc", "sketch_add_slot", "sketch_add_polygon",
    "sketch_fillet", "sketch_trim", "sketch_constrain",
    "sketch_add_spline", "sketch_add_ellipse", "sketch_mirror",
    "sketch_array", "sketch_offset", "array_component",
    "set_component_grounded", "reorder_feature",
})


def _abort(doc):
    if doc is None:
        return
    try:
        doc.abortTransaction()
    except Exception:
        pass


def _transactional(kernel, op):
    extra = getattr(getattr(kernel, "_plugins", None), "transactional", ())
    return op in _TRANSACTIONAL or op in extra


def dispatch(kernel: Kernel, op: str, params: dict):
    """Route one validated request to the kernel, normalizing errors.

    Mutating ops run inside a document transaction: one UI action = one
    Ctrl+Z, and a failed op leaves the document as it was.

    Méthode du noyau si elle existe, sinon opération du registre — dans
    cet ordre. Un plugin ne détourne pas une opération existante.
    """
    from . import protocol
    doc = kernel._doc if _transactional(kernel, op) else None
    if doc is not None:
        doc.openTransaction("freesolid-" + op)
    try:
        method = getattr(kernel, op, None)
        if callable(method):
            result = method(**params)
        else:
            result = kernel._plugins.call_op(op, kernel, **params)
    except (KernelError, PluginError) as exc:
        _abort(doc)
        return protocol.err(str(exc))
    except Exception as exc:  # noqa: BLE001 - the envelope is the handler
        _abort(doc)
        return protocol.err(_explain(exc),
                            hint="erreur moteur non traduite — à signaler")
    if doc is not None:
        try:
            doc.commitTransaction()
        except Exception:
            pass
    return protocol.ok(result)
