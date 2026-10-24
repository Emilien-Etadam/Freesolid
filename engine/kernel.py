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
from engine.ops import PREVIEWABLE, TRANSACTIONAL  # noqa: E402
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
from engine.equations import EquationsMixin
from engine.sketch import SketchMixin
from engine.sketchdraw import SketchDrawMixin
from engine.sketchedit import SketchEditMixin
from engine.sketchref import SketchRefMixin
from engine.sketchmore import SketchMoreMixin
from engine.sketchshare import SketchShareMixin
from engine.sketchlayers import SketchLayersMixin
from engine.docprops import DocPropsMixin
from engine.vertexchamfer import VertexChamferMixin
from engine.selectchain import SelectChainMixin
from engine.materials import MaterialsMixin
from engine.refgeom import RefGeomMixin
from engine.clipboard import ClipboardMixin
from engine.templates import TemplatesMixin
from engine.treeorg import TreeOrgMixin
from engine.directedit import DirectEditMixin
from engine.configs import ConfigsMixin
from engine.splineedit import SplineEditMixin
from engine.sketch3d import Sketch3dMixin
from engine.solids import SolidsMixin
from engine.tree import TreeMixin


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


class Kernel(SketchShareMixin, TreeMixin, SolidsMixin, SketchMixin, SketchDrawMixin, SketchEditMixin, SketchRefMixin, SketchMoreMixin, SketchLayersMixin, DocPropsMixin, VertexChamferMixin, SelectChainMixin, MaterialsMixin, RefGeomMixin, ClipboardMixin, TemplatesMixin, TreeOrgMixin, DirectEditMixin, ConfigsMixin, SplineEditMixin, Sketch3dMixin, EquationsMixin, FilesMixin, GraphMixin, SurfaceMixin, AssemblyMixin, TextMixin, DrawingMixin, SelftestMixin):
    """Owns one FreeCAD document and executes protocol operations."""

    def __init__(self):
        self._doc = None
        self._body = None
        self._assembly = False  # le document courant est un assemblage
        # Modifié depuis le dernier « nouveau / ouvrir / enregistrer » :
        # le client demande confirmation avant de l'abandonner.
        self._modified = False
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
        # Formes figées (suppression de face) : elles suivent les
        # fonctions d'avant, une passe par niveau d'imbrication.
        for _ in range(8):
            if not self._refresh_frozen_shapes():
                break
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

    def document_status(self):
        """État du document pour le client : ouvert, modifié depuis le
        dernier enregistrement (ou depuis sa création / son ouverture)."""
        return {"open": self._doc is not None, "modified": self._modified}

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

    def mass_properties(self, density=None):
        """Volume, masse (densité en g/cm³ : celle donnée, sinon la
        matière du corps, sinon le PLA), surface, centre de gravité,
        encombrement — l'onglet Évaluer."""
        body = self._require_body()
        material = self._material_of(body)
        if density is None:
            density = material["density"] if material else 1.24
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
            "material": material["name"] if material else None,
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

    def _current_tree(self):
        """Part tree or assembly tree, whichever mode the document is in."""
        return self.assembly_tree() if self._assembly else self.get_tree()

    def undo(self, steps=1):
        """Annuler la dernière opération — une transaction par op UI ;
        ``steps`` : plusieurs d'un coup (liste de l'historique)."""
        doc = self._require_doc()
        if not doc.UndoNames:
            raise KernelError("rien à annuler")
        for _ in range(max(1, min(int(steps), len(doc.UndoNames)))):
            doc.undo()
        doc.recompute()
        return self._current_tree()

    def redo(self, steps=1):
        doc = self._require_doc()
        if not doc.RedoNames:
            raise KernelError("rien à rétablir")
        for _ in range(max(1, min(int(steps), len(doc.RedoNames)))):
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

    #: Dérivé du catalogue (``preview=True``), plus les ops pas encore
    #: décrites dans engine/ops/.
    _PREVIEWABLE = PREVIEWABLE | frozenset({
        "set_params",
    })

    def preview(self, op, params):
        """Aperçu jaune : exécute la fonction, tesselle, puis annule tout.

        The op runs inside its own transaction which is always aborted —
        the document comes back exactly as it was, whatever happened. The
        client renders the returned mesh as the translucent preview ghost.
        """
        doc = self._require_doc()
        if op not in self._PREVIEWABLE:
            raise KernelError(
                "aperçu non disponible pour {}".format(op))
        if not isinstance(params, dict):
            raise KernelError("params doit être un objet JSON")
        doc.openTransaction("freesolid-preview")
        self._previewing = True
        planes = {o.Name for o in doc.Objects
                  if o.TypeId == "PartDesign::Plane"}
        try:
            getattr(self, op)(**params)
            if op == "add_datum_plane":
                # Un plan ne change pas le solide : on renvoie où il se pose.
                made = [o for o in doc.Objects
                        if o.TypeId == "PartDesign::Plane"
                        and o.Name not in planes]
                if not made:
                    raise KernelError("plan de référence introuvable")
                return {"plane": list(made[-1].Placement.Matrix.A)}
            return self.tessellate()
        finally:
            self._previewing = False
            try:
                doc.abortTransaction()
            except Exception:
                pass
            doc.recompute()

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


#: Ops recorded as one undo step each. Left out on purpose: document
#: lifecycle (new/open), read-only ops, undo/redo themselves, and
#: sketch_move — a drag streaming at ~20 Hz would shred the undo stack
#: into per-frame steps.
#: Dérivé du catalogue (``undo=True``), plus les ops pas encore décrites
#: dans engine/ops/.
_TRANSACTIONAL = TRANSACTIONAL | frozenset({
    "make_drawing",
    "set_param", "set_params", "rename",
    "set_variable", "delete_variable",
    "set_tip", "tip_to_end", "delete_feature",
    "reorder_feature", "set_comment",
    "set_suppressed",
    "set_body_material", "set_face_color",
    "paste_feature",
    "set_folder", "rename_folder", "add_configuration",
    "activate_configuration", "rename_configuration", "delete_configuration",
    "set_configuration_values",
})


#: Ops qui laissent un document « propre » : neuf, ouvert ou enregistré.
_CLEAN_OPS = frozenset({"new_part", "new_assembly", "open_part", "save_part",
                        "new_from_template"})
#: Ops qui changent le document hors transaction.
_DIRTY_OPS = frozenset({"undo", "redo", "sketch_move",
                        "set_document_properties", "set_hidden"})


def _track_modified(kernel, op):
    if op in _CLEAN_OPS:
        kernel._modified = False
    elif op in _DIRTY_OPS or _transactional(kernel, op):
        kernel._modified = True


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
    _track_modified(kernel, op)
    return protocol.ok(result)
