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
from engine.equations import EquationsMixin
from engine.sketch import SketchMixin
from engine.solids import SolidsMixin


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


class Kernel(SolidsMixin, SketchMixin, EquationsMixin, FilesMixin, GraphMixin, SurfaceMixin, AssemblyMixin, TextMixin, DrawingMixin, SelftestMixin):
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
