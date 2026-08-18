"""The FreeCAD-headless side of the protocol.

One ``Kernel`` instance owns one document. FreeCAD is imported inside
methods (the module stays importable in CI), and every error surfaces
through ``engine.guard.friendly_error`` when a translation exists — the
web UI gets designer-facing explanations for known OCCT failures.

Untested-against-FreeCAD code is assumed guilty until the ``selftest`` op
has run on a real install.
"""

import os
import re
import sys

# Make the repo root importable when freecadcmd runs this file from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine.guard import friendly_error          # noqa: E402
from engine.protocol import visible_deps         # noqa: E402
from engine.vocab import label_for_type          # noqa: E402


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


_NEUTRAL_PLANES = frozenset({"XY", "XZ", "YZ"})


def parse_neutral_plane(neutral="XY"):
    """Valide le plan neutre d'une dépouille (XY / XZ / YZ)."""
    key = str(neutral).upper()
    if key not in _NEUTRAL_PLANES:
        raise KernelError("plan neutre inconnu : {}".format(neutral))
    return key


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


class Kernel:
    """Owns one FreeCAD document and executes protocol operations."""

    def __init__(self):
        self._doc = None
        self._body = None
        self._assembly = False  # le document courant est un assemblage

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
        doc.recompute()
        broken = [o for o in doc.Objects if "Invalid" in (o.State or ())]
        if broken:
            messages = []
            for obj in broken:
                text = ""
                try:
                    text = obj.getStatusString() or ""
                except Exception:
                    pass
                messages.append("{} : {}".format(
                    obj.Label, friendly_error(text) or text or "en erreur"))
            raise KernelError(" ; ".join(messages))

    # -- operations ------------------------------------------------------

    def ping(self):
        App = self._app()
        return {"freecad": ".".join(str(v) for v in App.Version()[:3])}

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

    def new_part(self, name="Pièce"):
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolid")
        self._setup_doc(self._doc)
        self._body = self._doc.addObject("PartDesign::Body", "Body")
        self._body.Label = name
        self._recompute()
        return self.get_tree()

    # -- phase C : assemblage v1 (placements directs, sans solveur) -------

    def _require_assembly(self):
        if self._doc is None or not self._assembly:
            raise KernelError(
                "aucun assemblage ouvert — commencez par new_assembly")
        return self._doc

    def new_assembly(self, name="Assemblage"):
        """Nouveau document d'assemblage : des pièces .FCStd insérées par
        référence (App::Link) dans un Assembly::AssemblyObject, avec le
        groupe de joints du solveur natif (plateforme de référence 1.1.3,
        repli 1.0.2)."""
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolidAsm")
        self._setup_doc(self._doc)
        self._assembly = True
        asm = self._doc.addObject("Assembly::AssemblyObject", "Assembly")
        asm.Label = str(name) if name else "Assemblage"
        joints = self._doc.addObject("Assembly::JointGroup", "Joints")
        asm.addObject(joints)
        return self.assembly_tree()

    def _assembly_object(self):
        doc = self._require_assembly()
        for obj in doc.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return obj
        raise KernelError("assemblage sans Assembly::AssemblyObject — "
                          "recréez-le (ancien format)")

    def _joint_group(self):
        doc = self._require_assembly()
        for obj in doc.Objects:
            if obj.TypeId == "Assembly::JointGroup":
                return obj
        asm = self._assembly_object()
        joints = doc.addObject("Assembly::JointGroup", "Joints")
        asm.addObject(joints)
        return joints

    def _solve_assembly(self):
        asm = self._assembly_object()
        try:
            asm.solve()
        except Exception as exc:  # noqa: BLE001 - sur-contraint, surtout
            raise KernelError(
                "le solveur d'assemblage a échoué : {}".format(
                    _explain(exc)))

    def insert_component(self, path):
        """Insérer une pièce : lien vers le premier corps de son fichier.

        La pièce reste un fichier séparé — la modifier puis rouvrir
        l'assemblage met à jour toutes ses instances, comme SolidWorks.
        """
        doc = self._require_assembly()
        App = self._app()
        path = self._user_path(path, (".FCStd",), must_exist=True)
        if not getattr(doc, "FileName", ""):
            # Un App::Link externe exige un document propriétaire déjà
            # enregistré (« Owner document not saved » sinon) : première
            # insertion = enregistrement temporaire ; « Enregistrer »
            # le déplacera où l'utilisateur veut, FreeCAD réécrit les
            # chemins relatifs au saveAs.
            import tempfile
            doc.saveAs(os.path.join(tempfile.gettempdir(),
                                    "freesolid-assemblage.FCStd"))
        part_doc = None
        opened_here = False
        for open_doc in App.listDocuments().values():
            if getattr(open_doc, "FileName", "") == path:
                part_doc = open_doc
                break
        if part_doc is None:
            try:
                part_doc = App.openDocument(path, True)  # hidden
            except TypeError:
                part_doc = App.openDocument(path)
            opened_here = True
            self._setup_doc(part_doc)
        bodies = [o for o in part_doc.Objects
                  if o.TypeId == "PartDesign::Body"]
        if not bodies:
            if opened_here:
                try:
                    App.closeDocument(part_doc.Name)
                except Exception:
                    pass
            raise KernelError(
                "aucun corps PartDesign dans {}".format(path))
        try:
            asm = self._assembly_object()
        except KernelError:
            asm = None  # assemblage ancien format : lien à la racine
        if asm is not None:
            # 1.1.3 : newObject évite « The graph must be a DAG ».
            link = asm.newObject("App::Link", "Component")
        else:
            link = doc.addObject("App::Link", "Component")
        link.LinkedObject = bodies[0]
        link.Label = os.path.splitext(os.path.basename(path))[0]
        existing = [o for o in doc.Objects
                    if o.TypeId == "App::Link" and o is not link]
        if not existing:
            # Le premier composant est fixé, comme dans SolidWorks.
            try:
                self._ground(link)
            except Exception:
                pass  # sans ancrage, le solveur bougera tout — non fatal
        doc.recompute()
        return self.assembly_tree()

    def _ground(self, link):
        """Fixer un composant (GroundedJoint du module natif)."""
        import JointObject
        doc = self._require_assembly()
        joint = doc.addObject("App::FeaturePython", "GroundedJoint")
        self._joint_group().addObject(joint)
        try:
            JointObject.GroundedJoint(joint, link)
        except TypeError:
            JointObject.GroundedJoint(joint)
            if hasattr(joint, "ObjectToGround"):
                joint.ObjectToGround = link
        joint.Label = "Fixé — {}".format(link.Label)

    #: nos noms -> l'énumération JointType du module natif. Les quatre
    #: derniers sont les contraintes mécaniques (vues dans le spike).
    _JOINT_TYPES = {
        "fixe": "Fixed", "fixed": "Fixed",
        "pivot": "Revolute",
        "cylindrique": "Cylindrical",
        "glissiere": "Slider",
        "rotule": "Ball",
        "distance": "Distance",
        "engrenages": "Gears",
        "cremaillere": "RackPinion",
        "vis": "Screw",
        "courroie": "Belt",
    }

    def add_joint(self, component1, component2, type="fixe",
                  sub1=None, sub2=None, distance=None, distance2=None,
                  angle_min=None, angle_max=None,
                  length_min=None, length_max=None):
        """Contrainte d'assemblage entre deux composants, résolue par le
        solveur natif (MbD). ``sub1``/``sub2`` : sous-élément visé
        (« Face3 », « Edge5 ») — la face cliquée dans la zone graphique.
        """
        import JointObject
        doc = self._require_assembly()
        asm = self._assembly_object()
        target = self._JOINT_TYPES.get(str(type).lower())
        if target is None:
            raise KernelError(
                "contrainte inconnue « {} » — attendu : {}".format(
                    type, ", ".join(sorted(set(self._JOINT_TYPES)
                                           - {"fixed"}))))
        links = {}
        for name in (component1, component2):
            obj = doc.getObject(str(name))
            if obj is None or obj.TypeId != "App::Link":
                raise KernelError("composant inconnu : {}".format(name))
            links[name] = obj
        if str(component1) == str(component2):
            raise KernelError("choisissez deux composants différents")

        joint = doc.addObject("App::FeaturePython", "Joint")
        self._joint_group().addObject(joint)
        try:
            JointObject.Joint(joint, 0)
        except Exception as exc:  # noqa: BLE001
            doc.removeObject(joint.Name)
            raise KernelError(_explain(exc))
        allowed = list(joint.getEnumerationsOfProperty("JointType"))
        if target not in allowed:
            doc.removeObject(joint.Name)
            raise KernelError(
                "cette version ne propose pas « {} » — disponibles : "
                "{}".format(target, ", ".join(allowed)))
        joint.JointType = target
        # 1.1.3 : forme directe doublée via setJointConnectors. Un sub vide
        # se double aussi (["", ""]) — banc natif : Face2+Face2 → centre.
        # 1.0.2 lève AttributeError ('NoneType' … 'Placement') : repli.
        refs = []
        for name, sub in ((component1, sub1), (component2, sub2)):
            sub_name = str(sub) if sub else ""
            refs.append((links[name], [sub_name, sub_name]))
        try:
            joint.Proxy.setJointConnectors(joint, refs)
        except Exception:  # noqa: BLE001 - 1.0.2 n'a pas l'API
            # Références : la propriété attend LE couple
            # (objet, [sous-éléments]) — « Expect input sequence of size 2 »
            # si on l'emballe dans une liste (vu sur 1.1.3). Forme UI ancrée
            # à l'assemblage d'abord, repli sur la forme directe.
            for ref_prop, name, sub in (
                    ("Reference1", component1, sub1),
                    ("Reference2", component2, sub2)):
                link = links[name]
                sub_name = str(sub) if sub else ""
                forms = [
                    (asm, ["{}.{}".format(link.Name, sub_name)
                           if sub_name else "{}.".format(link.Name)]),
                    (link, [sub_name] if sub_name else [""]),
                ]
                assigned = False
                last_error = None
                for form in forms:
                    try:
                        setattr(joint, ref_prop, form)
                        assigned = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                if not assigned:
                    doc.removeObject(joint.Name)
                    raise KernelError(_explain(last_error))
        if distance is not None and hasattr(joint, "Distance"):
            joint.Distance = float(distance)
        if distance2 is not None and hasattr(joint, "Distance2"):
            joint.Distance2 = float(distance2)
        # Limites de mouvement (SolidWorks : contraintes avancées).
        for value, prop, enable in (
                (angle_min, "AngleMin", "EnableAngleMin"),
                (angle_max, "AngleMax", "EnableAngleMax"),
                (length_min, "LengthMin", "EnableLengthMin"),
                (length_max, "LengthMax", "EnableLengthMax")):
            if value is not None and hasattr(joint, prop):
                setattr(joint, enable, True)
                setattr(joint, prop, float(value))
        labels = {"Fixed": "Fixe", "Revolute": "Pivot",
                  "Cylindrical": "Cylindrique", "Slider": "Glissière",
                  "Ball": "Rotule", "Distance": "Distance",
                  "Gears": "Engrenages", "RackPinion": "Crémaillère",
                  "Screw": "Vis", "Belt": "Courroie"}
        joint.Label = "{} — {} / {}".format(
            labels.get(target, target),
            links[component1].Label, links[component2].Label)
        doc.recompute()
        try:
            self._solve_assembly()
        except KernelError:
            doc.removeObject(joint.Name)
            doc.recompute()
            raise
        return self.assembly_tree()

    def solve_assembly(self):
        """Relancer le solveur — après un déplacement à la main."""
        self._solve_assembly()
        self._require_assembly().recompute()
        return self.assembly_tree()

    def move_component(self, component, x=0.0, y=0.0, z=0.0,
                       yaw=0.0, pitch=0.0, roll=0.0):
        """Positionner un composant : translation + lacet/tangage/roulis."""
        doc = self._require_assembly()
        App = self._app()
        link = doc.getObject(str(component))
        if link is None or link.TypeId != "App::Link":
            raise KernelError("composant inconnu : {}".format(component))
        link.Placement = App.Placement(
            App.Vector(float(x), float(y), float(z)),
            App.Rotation(float(yaw), float(pitch), float(roll)))
        doc.recompute()
        # Avec des contraintes posées, le solveur reprend la main — le
        # déplacement manuel devient une suggestion, comme dans SolidWorks.
        group = next((o for o in doc.Objects
                      if o.TypeId == "Assembly::JointGroup"), None)
        if group is not None and any(hasattr(o, "JointType")
                                     for o in group.Group):
            try:
                self._solve_assembly()
                doc.recompute()
            except KernelError:
                pass  # sur-contraint : la position saisie reste
        return self.assembly_tree()

    def array_component(self, component, count, dx=0.0, dy=0.0, dz=0.0):
        """Répétition de composants : n instances du même fichier, au pas
        donné — visserie, entretoises, séries à imprimer."""
        doc = self._require_assembly()
        App = self._app()
        link = doc.getObject(str(component))
        if link is None or link.TypeId != "App::Link":
            raise KernelError("composant inconnu : {}".format(component))
        total = int(count)
        if total < 2:
            raise KernelError("au moins 2 occurrences")
        base_placement = link.Placement
        for i in range(1, total):
            copy = doc.addObject("App::Link", "Component")
            copy.LinkedObject = link.LinkedObject
            copy.Label = "{} ({})".format(link.Label, i + 1)
            offset = App.Vector(float(dx) * i, float(dy) * i,
                                float(dz) * i)
            copy.Placement = App.Placement(
                base_placement.Base + offset, base_placement.Rotation)
            try:
                self._assembly_object().addObject(copy)
            except KernelError:
                pass
        doc.recompute()
        return self.assembly_tree()

    def assembly_tree(self):
        doc = self._require_assembly()
        joints = []
        grounded = set()
        group = next((o for o in doc.Objects
                      if o.TypeId == "Assembly::JointGroup"), None)
        for obj in (group.Group if group is not None else ()):
            if hasattr(obj, "ObjectToGround"):
                target = getattr(obj, "ObjectToGround", None)
                if target is not None:
                    grounded.add(target.Name)
                joints.append({"name": obj.Name, "label": obj.Label,
                               "type": "Fixé"})
            elif hasattr(obj, "JointType"):
                joints.append({"name": obj.Name, "label": obj.Label,
                               "type": str(obj.JointType)})
        components = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            placement = obj.Placement
            components.append({
                "name": obj.Name,
                "label": obj.Label,
                "grounded": obj.Name in grounded,
                "position": [placement.Base.x, placement.Base.y,
                             placement.Base.z],
                "rotation": [float(v)
                             for v in placement.Rotation.toEuler()],
            })
        return {"assembly": True, "components": components,
                "joints": joints}

    def tessellate_assembly(self, deviation=0.1):
        """Un maillage par composant — la sélection au clic est par
        composant, pas par face (v1)."""
        from . import protocol
        doc = self._require_assembly()
        components = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            linked = getattr(obj, "LinkedObject", None)
            shape = getattr(linked, "Shape", None)
            if shape is None or not shape.Faces:
                continue
            moved = shape.copy()
            moved.Placement = obj.Placement.multiply(moved.Placement)
            faces = []
            for i, face in enumerate(moved.Faces):
                vertices, triangles = face.tessellate(float(deviation))
                faces.append(
                    (i, [(v.x, v.y, v.z) for v in vertices], triangles))
            components.append({"name": obj.Name, "label": obj.Label,
                               "mesh": protocol.pack_mesh(faces)})
        return {"components": components}

    def check_interference(self):
        """Détection d'interférences : volume commun de chaque paire de
        composants — le contrôle avant impression d'un assemblage."""
        doc = self._require_assembly()
        shapes = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            linked = getattr(obj, "LinkedObject", None)
            shape = getattr(linked, "Shape", None)
            if shape is None or not shape.Solids:
                continue
            moved = shape.copy()
            moved.Placement = obj.Placement.multiply(moved.Placement)
            shapes.append((obj.Label, moved))
        pairs = []
        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                try:
                    volume = float(
                        shapes[i][1].common(shapes[j][1]).Volume)
                except Exception:
                    continue
                if volume > 1e-6:
                    pairs.append({"a": shapes[i][0], "b": shapes[j][0],
                                  "volume_mm3": volume})
        return {"interferences": pairs}

    def spike_assembly(self):
        """Rapport d'exploration : l'atelier Assembly 1.x est-il utilisable
        headless (objets, solveur, module des joints) ?

        Ne lève jamais — le verdict guide la phase C3 ; il ne casse pas
        le selftest. Chaque tentative note sa réussite ou son erreur.
        """
        App = self._app()
        result = {"freecad": ".".join(str(v) for v in App.Version()[:3])}
        doc = None
        try:
            doc = App.newDocument("FreeSolidSpike")
            try:
                asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
                result["assembly_object"] = True
                result["has_solve"] = hasattr(asm, "solve")
                if result["has_solve"]:
                    try:
                        asm.solve()
                        result["solve_empty_ok"] = True
                    except Exception as exc:
                        result["solve_empty_error"] = str(exc)[:160]
            except Exception as exc:
                result["assembly_object"] = False
                result["assembly_object_error"] = str(exc)[:160]
            group = None
            try:
                group = doc.addObject("Assembly::JointGroup", "Joints")
                result["joint_group"] = True
                try:
                    # Le groupe de joints DANS l'assemblage — le proxy du
                    # joint remonte à son parent pour trouver l'assemblage
                    # (« 'NoneType' object has no attribute 'Type' » quand
                    # il est orphelin, vu sur 1.1.3).
                    asm.addObject(group)
                    result["joint_group_in_assembly"] = True
                except Exception as exc:
                    result["joint_group_in_assembly"] = False
                    result["joint_group_in_assembly_error"] = str(exc)[:120]
            except Exception as exc:
                result["joint_group"] = False
                result["joint_group_error"] = str(exc)[:160]
            try:
                import JointObject
                result["joint_module"] = True
                result["joint_symbols"] = [
                    n for n in dir(JointObject)
                    if not n.startswith("_")][:40]
                try:
                    # La vérité terrain : le constructeur réel de cette
                    # version, lu sur la machine de l'utilisateur.
                    import inspect
                    result["joint_init_source"] = inspect.getsource(
                        JointObject.Joint.__init__)[:1500]
                except Exception as exc:
                    result["joint_init_source_error"] = str(exc)[:120]
                joint = doc.addObject("App::FeaturePython", "SpikeJoint")
                if group is not None:
                    try:
                        group.addObject(joint)
                    except Exception as exc:
                        result["joint_into_group_error"] = str(exc)[:120]
                created = False
                for args in ((joint,), (joint, 0), (joint, "Fixed")):
                    try:
                        JointObject.Joint(*args)
                        created = True
                        break
                    except TypeError:
                        continue
                    except Exception as exc:
                        result["joint_proxy_error"] = str(exc)[:160]
                        break
                result["joint_proxy"] = created
                if created:
                    skip = {"Label", "Label2", "ExpressionEngine",
                            "Visibility"}
                    result["joint_properties"] = [
                        p for p in joint.PropertiesList
                        if p not in skip][:25]
            except Exception as exc:
                result["joint_module"] = False
                result["joint_module_error"] = str(exc)[:160]
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)[:160]
        finally:
            if doc is not None:
                try:
                    App.closeDocument(doc.Name)
                except Exception:
                    pass
        return result

    # -- phase D : surfacique (API Part) + courbes 3D ---------------------

    #: Objets document-level exposés dans la section Surfaces de l'arbre.
    #: Les PartDesign::* dérivent aussi de Part::Feature — filtre exact.
    _SURFACE_TYPE_IDS = frozenset({
        "Part::Feature", "Part::Extrusion", "Part::Revolution",
        "Part::Loft", "Part::Offset",
    })

    def _add_surface(self, shape, label):
        """Surface figée (Part::Feature) — couture, courbe 3D, legacy."""
        doc = self._require_doc()
        feature = doc.addObject("Part::Feature", "Surface")
        feature.Shape = shape
        feature.Label = label
        doc.recompute()
        return self.get_tree()

    def _add_part_surface(self, type_id, label, configure):
        """Crée un objet Part paramétrique natif ; purge si le recompute
        échoue — pas d'entrée cassée dans l'arbre."""
        doc = self._require_doc()
        obj = doc.addObject(type_id, "Surface")
        obj.Label = label
        try:
            configure(obj)
            self._recompute()
        except Exception as exc:  # noqa: BLE001
            try:
                doc.removeObject(obj.Name)
            except Exception:
                pass
            if isinstance(exc, KernelError):
                raise
            raise KernelError(_explain(exc))
        return self.get_tree()

    def _surface_source(self, sketch):
        sk = (self._get_sketch(sketch) if sketch is not None
              else self._latest_sketch())
        if not sk.Shape.Edges:
            raise KernelError("l'esquisse est vide")
        return sk

    def _surface_sketch_objects(self, obj):
        """Esquisses sources d'une surface paramétrique Part."""
        sketches = []
        if obj.TypeId == "Part::Extrusion":
            base = getattr(obj, "Base", None)
            if base is not None and base.TypeId == "Sketcher::SketchObject":
                sketches.append(base)
        elif obj.TypeId == "Part::Revolution":
            source = getattr(obj, "Source", None)
            if (source is not None
                    and source.TypeId == "Sketcher::SketchObject"):
                sketches.append(source)
        elif obj.TypeId == "Part::Loft":
            for section in getattr(obj, "Sections", None) or []:
                if (section is not None
                        and section.TypeId == "Sketcher::SketchObject"):
                    sketches.append(section)
        return sketches

    def _surface_tree_entry(self, obj, order_of=None):
        sketches = self._surface_sketch_objects(obj)
        order_of = order_of if order_of is not None else {}
        entry = {
            "name": obj.Name,
            "label": obj.Label,
            "type": obj.TypeId,
            "sketches": [sk.Name for sk in sketches],
            "order": order_of.get(obj.Name, -1),
        }
        # Couture / courbe / fichiers legacy : pas d'objet paramétrique.
        if obj.TypeId == "Part::Feature":
            entry["static"] = True
        if sketches:
            entry["children"] = [{
                "name": sk.Name,
                "label": sk.Label,
                "kind": label_for_type(sk.TypeId),
                "type": sk.TypeId,
                "error": "Invalid" in (sk.State or ()),
                "order": order_of.get(sk.Name, -1),
            } for sk in sketches]
        entry["rolled_back"] = self._is_rolled_back(obj)
        return entry

    def surface_extrude(self, length, sketch=None):
        """Surface extrudée paramétrique — profil ouvert OK."""
        sk = self._surface_source(sketch)
        App = self._app()
        normal = sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        length = float(length)

        def configure(obj):
            obj.Base = sk
            obj.DirMode = "Custom"
            obj.Dir = normal
            obj.LengthFwd = length
            obj.Solid = False

        return self._add_part_surface(
            "Part::Extrusion", "Surface extrudée", configure)

    def surface_revolve(self, angle=360.0, sketch=None):
        """Surface de révolution paramétrique — axe vertical d'esquisse."""
        sk = self._surface_source(sketch)
        App = self._app()
        base = sk.Placement.Base
        axis = sk.Placement.Rotation.multVec(App.Vector(0, 1, 0))
        angle = float(angle)

        def configure(obj):
            obj.Source = sk
            obj.Axis = axis
            obj.Base = base
            obj.Angle = angle
            obj.Solid = False

        return self._add_part_surface(
            "Part::Revolution", "Surface de révolution", configure)

    def surface_loft(self, sketches):
        """Surface lissée paramétrique entre plusieurs profils."""
        if not isinstance(sketches, (list, tuple)) or len(sketches) < 2:
            raise KernelError("une surface lissée demande au moins deux "
                              "profils")
        sections = []
        for name in sketches:
            sk = self._get_sketch(str(name))
            if not sk.Shape.Edges:
                raise KernelError("esquisse vide : {}".format(name))
            sections.append(sk)

        def configure(obj):
            obj.Sections = sections
            obj.Solid = False
            obj.Ruled = False

        return self._add_part_surface(
            "Part::Loft", "Surface lissée", configure)

    def _get_surface(self, name):
        obj = self._require_doc().getObject(str(name))
        if obj is None or obj.TypeId not in self._SURFACE_TYPE_IDS:
            raise KernelError("surface inconnue : {}".format(name))
        return obj

    def surface_sew(self, surfaces):
        """Coudre des surfaces ; reste figé (pas d'objet Part paramétrique
        natif pour la couture). Si la peau est fermée, elle devient un
        solide — le geste « coudre puis solidifier » de SolidWorks."""
        import Part
        if not isinstance(surfaces, (list, tuple)) or len(surfaces) < 2:
            raise KernelError("coudre demande au moins deux surfaces")
        faces = []
        for name in surfaces:
            faces.extend(self._get_surface(name).Shape.Faces)
        if not faces:
            raise KernelError("aucune face à coudre")
        try:
            shell = Part.makeShell(faces)
            shell.sewShape()
            if shell.isClosed():
                return self._add_surface(Part.makeSolid(shell),
                                         "Solide cousu")
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self._add_surface(shell, "Surface cousue")

    def surface_thicken(self, surface, thickness):
        """Épaissir une surface en solide — Part::Offset paramétrique."""
        src = self._get_surface(surface)
        thickness = float(thickness)
        if thickness == 0:
            raise KernelError("l'épaisseur ne peut pas être nulle")

        def configure(obj):
            obj.Source = src
            obj.Value = thickness
            obj.Fill = True

        return self._add_part_surface(
            "Part::Offset", "Épaississement", configure)
    def add_curve3d(self, points, spline=True):
        """Courbe 3D par points — le repli esquisse 3D : une trajectoire
        pour le balayage (B-spline interpolée, ou polyligne)."""
        import Part
        App = self._app()
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            raise KernelError("une courbe demande au moins deux points")
        vectors = []
        for p in points:
            try:
                x, y, z = (float(v) for v in p)
            except Exception:
                raise KernelError("point invalide : {}".format(p))
            vectors.append(App.Vector(x, y, z))
        try:
            if spline and len(vectors) >= 3:
                curve = Part.BSplineCurve()
                curve.interpolate(vectors)
                # Un FIL, pas une arête nue : le balayage exige un
                # TopoDS_Wire (vu sur 1.1.3).
                shape = Part.Wire([curve.toShape()])
            else:
                shape = Part.makePolygon(vectors)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self._add_surface(shape, "Courbe 3D")

    # -- phase E : mise en plan -------------------------------------------

    @staticmethod
    def _drawing_visible_edges(view):
        try:
            return list(view.getVisibleEdges() or [])
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _drawing_apply_scale(view, scale):
        if scale:
            view.ScaleType = "Custom"
            view.Scale = float(scale)

    @staticmethod
    def _drawing_extreme_edge_ids(edges):
        """Indices gauche / droite / bas / haut (centres des BoundBox 2D)."""
        if len(edges) < 2:
            return None
        indexed = list(enumerate(edges))

        def cx(item):
            box = item[1].BoundBox
            return (box.XMin + box.XMax) / 2.0

        def cy(item):
            box = item[1].BoundBox
            return (box.YMin + box.YMax) / 2.0

        left = min(indexed, key=cx)[0]
        right = max(indexed, key=cx)[0]
        bottom = min(indexed, key=cy)[0]
        top = max(indexed, key=cy)[0]
        if left == right or bottom == top:
            return None
        return left, right, bottom, top

    def _drawing_add_extent_dims(self, doc, page, view, created):
        """Cotes d'encombrement DistanceX/DistanceY sur la vue de face.

        Les arêtes 2D doivent déjà être peuplées (CoarseView posé à la
        création de la vue — trop tard ensuite). Retourne False plutôt
        que d'échouer : le DXF muet reste meilleur que pas de DXF.
        """
        edges = self._drawing_visible_edges(view)
        ids = self._drawing_extreme_edge_ids(edges)
        if ids is None:
            return False
        left, right, bottom, top = ids
        dims = []
        for name, dtype, a, b in (
                ("DimLargeur", "DistanceX", left, right),
                ("DimHauteur", "DistanceY", bottom, top)):
            dim = doc.addObject("TechDraw::DrawViewDimension", name)
            created.append(dim)
            dims.append(dim)
            page.addView(dim)
            dim.Type = dtype
            dim.References2D = [
                (view, "Edge{}".format(a)),
                (view, "Edge{}".format(b)),
            ]
        doc.recompute()
        for dim in dims:
            if "Up-to-date" not in getattr(dim, "State", []):
                return False
            if hasattr(dim, "getRawValue"):
                try:
                    if not (dim.getRawValue() > 0):
                        return False
                except Exception:  # noqa: BLE001
                    return False
        return True

    def _drawing_add_section(self, doc, page, body, views, axis, scale,
                             created):
        """Vue en coupe (DrawViewSection) — normale selon X/Y/Z.

        La vue de base doit avoir une Direction non parallèle à la
        normale, sinon TechDraw n'arrive pas à construire le CS
        (getSectionCS) et le cut async peut SIGSEGV. Origine = (0,0,0).
        Hachures : défaut SvgHatch (CutSurfaceDisplay=Hide SIGSEGV en
        1.0.0 headless). La géométrie 2D de la coupe reste souvent vide
        headless (même thread HLR) — l'objet est quand même exporté.
        """
        App = self._app()
        normals = {"X": (1.0, 0.0, 0.0),
                   "Y": (0.0, 1.0, 0.0),
                   "Z": (0.0, 0.0, 1.0)}
        nx, ny, nz = normals[axis]
        nlen = (nx * nx + ny * ny + nz * nz) ** 0.5
        base = views[0]
        for view in views:
            direction = view.Direction
            length = direction.Length or 1.0
            aligned = abs(direction.x * nx + direction.y * ny
                          + direction.z * nz) / (length * nlen)
            if aligned < 0.95:
                base = view
                break
        section = doc.addObject("TechDraw::DrawViewSection", "Coupe" + axis)
        created.append(section)
        page.addView(section)
        section.Source = [body]
        section.BaseView = base
        section.SectionNormal = App.Vector(nx, ny, nz)
        section.SectionOrigin = App.Vector(0, 0, 0)
        section.Direction = App.Vector(nx, ny, nz)
        self._drawing_apply_scale(section, scale)
        section.X = float(base.X) + 80
        section.Y = float(base.Y)
        doc.recompute()
        return "Up-to-date" in getattr(section, "State", [])

    def make_drawing(self, path, scale=None, dims=True, section=None):
        """Mise en plan : Face / Dessus / Isométrique sur une page
        TechDraw, exportée en DXF (le seul export fiable headless).

        ``dims`` (défaut True) : cotes d'encombrement sur la vue de
        face. ``section`` : ``"X"|"Y"|"Z"`` pour une vue en coupe
        optionnelle. La page est retirée du document après l'export.
        """
        doc = self._require_doc()
        body = self._require_body()
        App = self._app()
        path = str(path)
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        path = self._user_path(path, (".dxf",), must_exist=False)
        want_dims = True if dims is None else bool(dims)
        axis = None
        if section not in (None, "", False):
            axis = str(section).strip().upper()
            if axis not in ("X", "Y", "Z"):
                raise KernelError("coupe : axe X, Y ou Z attendu")
        created = []
        cleanup_errors = []
        original = None
        dims_ok = None
        section_ok = None
        try:
            page = doc.addObject("TechDraw::DrawPage", "Page")
            created.append(page)
            template = doc.addObject("TechDraw::DrawSVGTemplate",
                                     "Template")
            created.append(template)
            template_path = os.path.join(
                App.getResourceDir(), "Mod", "TechDraw", "Templates",
                "A4_LandscapeTD.svg")
            if os.path.exists(template_path):
                template.Template = template_path
            page.Template = template
            placements = (("Face", (0, -1, 0), 70, 60),
                          ("Dessus", (0, 0, 1), 70, 150),
                          ("Iso", (1, -1, 1), 210, 105))
            views = []
            for name, direction, x, y in placements:
                view = doc.addObject("TechDraw::DrawViewPart",
                                     "View" + name)
                created.append(view)
                view.Source = [body]
                view.Direction = App.Vector(*direction)
                # Headless 1.0.x : le HLR Qt ne peuple pas les arêtes 2D.
                # CoarseView doit être posé AVANT le premier recompute.
                if want_dims:
                    view.CoarseView = True
                self._drawing_apply_scale(view, scale)
                page.addView(view)
                view.X = x
                view.Y = y
                views.append(view)
            doc.recompute()
            if want_dims:
                try:
                    dims_ok = self._drawing_add_extent_dims(
                        doc, page, views[0], created)
                except Exception:  # noqa: BLE001
                    dims_ok = False
            if axis is not None:
                try:
                    section_ok = self._drawing_add_section(
                        doc, page, body, views, axis, scale, created)
                except Exception:  # noqa: BLE001
                    section_ok = False
            import TechDraw
            TechDraw.writeDXFPage(page, path)
        except KernelError as exc:
            original = exc
            raise
        except Exception as exc:  # noqa: BLE001
            original = KernelError(_explain(exc))
            raise original
        finally:
            for obj in reversed(created):
                try:
                    doc.removeObject(obj.Name)
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append("{} ({})".format(
                        getattr(obj, "Name", "?"), _explain(exc)))
            try:
                doc.recompute()
            except Exception:
                pass
            if cleanup_errors:
                note = "mise en plan : nettoyage incomplet — {}".format(
                    " ; ".join(cleanup_errors))
                if original is None:
                    raise KernelError(note)
                original.args = (original.args[0] + " — " + note,)
        if not os.path.exists(path):
            raise KernelError("l'export DXF n'a rien produit")
        result = {"path": path, "size": os.path.getsize(path)}
        if dims_ok is not None:
            result["dims_ok"] = bool(dims_ok)
        if section_ok is not None:
            result["section_ok"] = bool(section_ok)
        return result

    # -- gravure de texte -------------------------------------------------

    _FONT_CANDIDATES = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    )

    def _find_font(self, font=None):
        import glob as globmod
        if font:
            # Police fournie par le client : jail. Les candidats internes
            # (ci-dessous) ne passent pas par resolve_user_path.
            return self._user_path(font, (".ttf", ".otf"), must_exist=True)
        for candidate in self._FONT_CANDIDATES:
            if os.path.exists(candidate):
                return candidate
        found = globmod.glob("/usr/share/fonts/**/*.ttf", recursive=True)
        if found:
            return sorted(found)[0]
        raise KernelError("aucune police .ttf sur ce système — passez "
                          "font=/chemin/vers/police.ttf")

    def _build_text_solid(self, text, base, size, depth, emboss, x, y,
                          font=None):
        """Solide des glyphes, posé par ``base`` (placement sur la face).

        Géométrie pure — ne touche pas au document, donc un échec (police,
        texte vide) ne laisse aucune trace.
        """
        import Part
        App = self._app()
        text = str(text)
        if not text.strip():
            raise KernelError("texte vide")
        normal = base.Rotation.multVec(App.Vector(0, 0, 1))
        chars = Part.makeWireString(text, self._find_font(font),
                                    float(size), 0)
        glyph_faces = []
        for char_wires in chars:
            if not char_wires:
                continue
            # FaceMakerBullseye : contours + trous de police correctement
            # orientés. Part.Face(wires) sortait des faces d'aire NÉGATIVE
            # (solides retournés, booléens invalides — la gravure « AB »
            # sur plaque 60×20 rendait un corps de 17 mm³, vu P032).
            try:
                glyph_faces.append(
                    Part.makeFace(char_wires, "Part::FaceMakerBullseye"))
            except Exception:
                for wire in char_wires:
                    glyph_faces.append(Part.Face(wire))
        if not glyph_faces:
            raise KernelError("la police n'a rien produit pour ce texte")
        compound = Part.makeCompound(glyph_faces)
        box = compound.BoundBox
        compound.translate(App.Vector(
            -(box.XMin + box.XMax) / 2 + float(x),
            -(box.YMin + box.YMax) / 2 + float(y), 0))
        compound.Placement = base.multiply(compound.Placement)
        margin = 0.2
        if emboss:
            vector = normal * float(depth)
        else:
            # dépasse légèrement la surface pour une coupe franche
            compound.translate(normal * margin)
            vector = normal * (-(float(depth) + margin))
        solids = [f.extrude(vector) for f in compound.Faces]
        text_solid = solids[0]
        for solid in solids[1:]:
            text_solid = text_solid.fuse(solid)
        return text_solid

    _TEXT_PROPS = (
        ("FreeSolidTextString", "App::PropertyString"),
        ("FreeSolidTextSize", "App::PropertyFloat"),
        ("FreeSolidTextDepth", "App::PropertyFloat"),
        ("FreeSolidTextX", "App::PropertyFloat"),
        ("FreeSolidTextY", "App::PropertyFloat"),
        ("FreeSolidTextEmboss", "App::PropertyBool"),
        ("FreeSolidTextFont", "App::PropertyString"),
        ("FreeSolidTextPlacement", "App::PropertyPlacement"),
    )

    def _mark_text_tool(self, obj):
        """Artefact interne d'une gravure : caché de l'arbre et du viewport."""
        if "FreeSolidTextTool" not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", "FreeSolidTextTool",
                            "FreeSolid", "Outil interne d'une gravure")
        obj.FreeSolidTextTool = True

    def _is_text_tool(self, obj):
        return bool(getattr(obj, "FreeSolidTextTool", False))

    def add_text(self, text, face, size=8.0, depth=1.0, x=0.0, y=0.0,
                 emboss=False, font=None):
        """Gravure (ou bossage) de texte sur une face plane — marquage de
        pièces. Le texte devient un corps outil combiné dans l'historique
        (soustraction pour graver, ajout pour embosser). Les paramètres
        sont persistés sur la ligne « Gravure » : rééditables (edit_text)."""
        App = self._app()
        body = self._require_body()
        doc = self._require_doc()
        text = str(text)
        faces = body.Shape.Faces
        index = int(face)
        if index < 0 or index >= len(faces):
            raise KernelError("face inconnue : {}".format(face))
        target = faces[index]
        u0, u1, v0, v1 = target.ParameterRange
        normal = target.normalAt((u0 + u1) / 2, (v0 + v1) / 2).normalize()
        center = target.CenterOfMass
        base = App.Placement(center, App.Rotation(App.Vector(0, 0, 1),
                                                  normal))
        text_solid = self._build_text_solid(text, base, size, depth,
                                            emboss, x, y, font)
        shape_feature = doc.addObject("Part::Feature", "TextShape")
        shape_feature.Shape = text_solid
        shape_feature.Label = "Forme du texte"
        self._mark_text_tool(shape_feature)
        tool_body = doc.addObject("PartDesign::Body", "TextBody")
        tool_body.Label = "Corps texte"
        tool_body.BaseFeature = shape_feature
        self._mark_text_tool(tool_body)
        doc.recompute()
        try:
            self.add_boolean(tool=tool_body.Name,
                             type="fuse" if emboss else "cut")
        except KernelError:
            for name in (tool_body.Name, shape_feature.Name):
                try:
                    doc.removeObject(name)
                except Exception:
                    pass
            doc.recompute()
            raise
        tip = getattr(body, "Tip", None)
        if tip is not None:
            tip.Label = "{} « {} »".format(
                "Texte en relief" if emboss else "Gravure", text[:15])
            for prop, prop_type in self._TEXT_PROPS:
                if prop not in tip.PropertiesList:
                    tip.addProperty(prop_type, prop, "FreeSolid",
                                    "Paramètre de la gravure")
            tip.FreeSolidTextString = text
            tip.FreeSolidTextSize = float(size)
            tip.FreeSolidTextDepth = float(depth)
            tip.FreeSolidTextX = float(x)
            tip.FreeSolidTextY = float(y)
            tip.FreeSolidTextEmboss = bool(emboss)
            tip.FreeSolidTextFont = str(font or "")
            tip.FreeSolidTextPlacement = base
        return self.get_tree()

    def edit_text(self, feature, text=None, size=None, depth=None,
                  x=None, y=None):
        """Rééditer une gravure : texte, taille, profondeur, position.

        La forme des glyphes est reconstruite d'abord (géométrie pure) —
        si elle échoue, la pièce n'est pas modifiée. Les gravures créées
        avant P032 n'ont pas leurs paramètres persistés : refus explicite.
        """
        doc = self._require_doc()
        obj = doc.getObject(str(feature))
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if "FreeSolidTextString" not in obj.PropertiesList:
            raise KernelError(
                "cette gravure date d'une version antérieure — "
                "supprimez-la puis recréez le texte")
        tool_body = next(
            (o for o in (getattr(obj, "Group", None) or [])
             if o.TypeId == "PartDesign::Body"), None)
        shape_feature = getattr(tool_body, "BaseFeature", None)
        if tool_body is None or shape_feature is None:
            raise KernelError(
                "gravure incomplète — le corps outil du texte est absent")
        new_text = obj.FreeSolidTextString if text is None else str(text)
        new_size = (obj.FreeSolidTextSize if size is None
                    else float(size))
        new_depth = (obj.FreeSolidTextDepth if depth is None
                     else float(depth))
        new_x = obj.FreeSolidTextX if x is None else float(x)
        new_y = obj.FreeSolidTextY if y is None else float(y)
        if new_size <= 0 or new_depth <= 0:
            raise KernelError(
                "taille et profondeur doivent être positives")
        emboss = bool(obj.FreeSolidTextEmboss)
        base = obj.FreeSolidTextPlacement
        text_solid = self._build_text_solid(
            new_text, base, new_size, new_depth, emboss, new_x, new_y,
            obj.FreeSolidTextFont or None)
        old_shape = shape_feature.Shape
        shape_feature.Shape = text_solid
        try:
            self._recompute()
        except KernelError as exc:
            shape_feature.Shape = old_shape
            try:
                self._recompute()
            except KernelError:
                pass
            raise KernelError(
                "{} — la gravure n'a pas été modifiée".format(exc))
        obj.FreeSolidTextString = new_text
        obj.FreeSolidTextSize = new_size
        obj.FreeSolidTextDepth = new_depth
        obj.FreeSolidTextX = new_x
        obj.FreeSolidTextY = new_y
        obj.Label = "{} « {} »".format(
            "Texte en relief" if emboss else "Gravure", new_text[:15])
        return self.get_tree()

    # -- phase E : évaluer ------------------------------------------------

    def mass_properties(self, density=1.24):
        """Volume, masse (densité en g/cm³ — PLA par défaut), surface,
        centre de gravité, encombrement — l'onglet Évaluer."""
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Solids:
            raise KernelError("pas de solide à évaluer")
        volume = float(shape.Volume)  # mm³
        com = shape.CenterOfMass
        box = shape.BoundBox
        return {
            "volume_mm3": volume,
            "area_mm2": float(shape.Area),
            "density": float(density),
            "mass_g": volume / 1000.0 * float(density),
            "center_of_mass": [com.x, com.y, com.z],
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
        body.Label = str(name).strip() if name else "Corps"
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

        S'applique au corps actif; le corps outil est absorbé par
        l'opération (comportement PartDesign).
        """
        body = self._require_body()
        doc = self._require_doc()
        tool_obj = doc.getObject(str(tool))
        if tool_obj is None or tool_obj.TypeId != "PartDesign::Body":
            raise KernelError("corps outil inconnu : {}".format(tool))
        if tool_obj is body:
            raise KernelError(
                "un corps ne se combine pas avec lui-même — choisissez "
                "un autre corps outil")
        types = {"cut": "Cut", "fuse": "Fuse", "common": "Common"}
        labels = {"cut": "Combiner — Soustraire",
                  "fuse": "Combiner — Ajouter",
                  "common": "Combiner — Intersection"}
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
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
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

    def export_part(self, path):
        """Export STL (impression 3D) ou STEP (échange CAO), par extension.

        Exports the body's current shape — what the viewport shows is what
        the printer gets.
        """
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Solids:
            raise KernelError("rien à exporter — la pièce n'a pas de solide")
        path = self._user_path(
            path, (".stl", ".step", ".3mf"), must_exist=False)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".stl":
                shape.exportStl(path)
            elif ext == ".step":
                shape.exportStep(path)
            elif ext == ".3mf":
                import Mesh
                Mesh.export([body], path)
            else:
                raise KernelError("format inconnu « {} » — utilisez .stl, "
                                  ".step ou .3mf".format(
                                      ext or "aucune extension"))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return {"path": path, "size": os.path.getsize(path)}

    #: Wire names for the body's origin planes — Dessus/Face/Droite in the
    #: client, following vocab.ORIGIN_PLANES (FreeCAD is Z-up).
    _PLANE_ROLES = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}

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
        sketch.Label = "Esquisse"
        if face is not None:
            self._attach_to_face(sketch, face)

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

    def add_pad(self, length, sketch=None, reversed=False, midplane=False):
        body = self._require_body()
        doc = self._require_doc()
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            profile = self._latest_sketch()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = profile
        pad.Length = float(length)
        if reversed:
            pad.Reversed = True
        if midplane:
            pad.Midplane = True  # « plan milieu » : symétrique au plan
        pad.Label = "Bossage extrudé"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pad.Name)
            raise
        return self.get_tree()

    def _consumed_sketches(self):
        """Esquisse → nom du parent (fonction PartDesign ou surface)."""
        body = self._require_body()
        consumed = {}
        for obj in body.Group:
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
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
                    and not self._is_text_tool(obj)):
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
                   sketch=None):
        """Cut with the latest sketch — Extruded Cut, in SolidWorks terms.

        No length (or ``through``) means « À travers tout » — the option a
        SolidWorks hand reaches for by default on a cut.
        """
        body = self._require_body()
        doc = self._require_doc()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = (self._get_sketch(sketch) if sketch is not None
                          else self._latest_sketch())
        if through or length is None:
            pocket.Type = "ThroughAll"
        else:
            pocket.Length = float(length)
        if reversed:
            pocket.Reversed = True
        pocket.Label = "Enlèvement de matière"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pocket.Name)
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
        plane.Label = "Plan de référence"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(plane.Name)
            raise
        return self.get_tree()

    def add_loft(self, sketches, subtractive=False, ruled=False,
                 closed=False):
        """Bossage/Base lissé (ou enlèvement) entre plusieurs profils —
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
        loft.Label = label_for_type(type_id)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(loft.Name)
            raise
        return self.get_tree()

    def add_sweep(self, profile, spine, subtractive=False):
        """Bossage/Base balayé (ou enlèvement) : un profil suit une
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
            binder.Label = "Trajectoire — {}".format(path.Label)
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
        pipe.Label = label_for_type(type_id)
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
        helix.Label = "Hélice"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(helix.Name)
            raise
        return self.get_tree()

    # -- palier 2 : révolutions, transformations, habillages avancés ------

    def _revolved(self, type_id, angle, sketch):
        """Revolution/Groove share everything but add-vs-cut.

        The axis is the sketch's own vertical axis — draw the profile beside
        it, exactly the SolidWorks revolve reflex.
        """
        body = self._require_body()
        doc = self._require_doc()
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Profile = profile
        feature.ReferenceAxis = (profile, ["V_Axis"])
        feature.Angle = float(angle)
        feature.Label = label_for_type(type_id)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_revolution(self, angle=360.0, sketch=None):
        """Bossage/Base avec révolution, autour de l'axe vertical de
        l'esquisse."""
        return self._revolved("PartDesign::Revolution", angle, sketch)

    def add_groove(self, angle=360.0, sketch=None):
        """Enlèvement de matière avec révolution."""
        return self._revolved("PartDesign::Groove", angle, sketch)

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

    def _transform(self, type_id, configure):
        body = self._require_body()
        doc = self._require_doc()
        original = self._last_solid_feature()
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Originals = [original]
        configure(feature)
        feature.Label = label_for_type(type_id)
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

    def add_mirror(self, plane="YZ"):
        """Symétrie de la dernière fonction par rapport à un plan
        d'origine (XY/XZ/YZ = Dessus/Face/Droite)."""
        role = self._PLANE_ROLES.get(str(plane).upper())
        if role is None:
            raise KernelError(
                "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
        plane_obj = self._origin_feature(role)

        def configure(feature):
            feature.MirrorPlane = (plane_obj, [""])
        return self._transform("PartDesign::Mirrored", configure)

    def _origin_axis(self, axis):
        role = self._AXIS_ROLES.get(str(axis).upper())
        if role is None:
            raise KernelError(
                "axe inconnu « {} » — attendu X, Y ou Z".format(axis))
        return self._origin_feature(role)

    def add_linear_pattern(self, length, count, axis="X"):
        """Répétition linéaire de la dernière fonction le long d'un axe.

        ``length`` is the total span, occurrences included — FreeCAD's
        convention, same as SolidWorks' « jusqu'à » spacing mode.
        """
        axis_obj = self._origin_axis(axis)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Direction = (axis_obj, [""])
            feature.Length = float(length)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::LinearPattern", configure)

    def add_polar_pattern(self, count, angle=360.0, axis="Z"):
        """Répétition circulaire de la dernière fonction autour d'un axe."""
        axis_obj = self._origin_axis(axis)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Axis = (axis_obj, [""])
            feature.Angle = float(angle)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::PolarPattern", configure)

    def add_thickness(self, face, thickness):
        """Coque : évide la pièce, la face cliquée devient l'ouverture."""
        return self._dressup("PartDesign::Thickness",
                             label_for_type("PartDesign::Thickness"),
                             "Value", thickness, face=face)

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
        feature.Label = label_for_type("PartDesign::Draft")
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
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_fillet(self, radius, face=None, edges=None):
        return self._dressup("PartDesign::Fillet", "Congé",
                             "Radius", radius, face=face, edges=edges)

    def add_chamfer(self, size, face=None, edges=None):
        return self._dressup("PartDesign::Chamfer", "Chanfrein",
                             "Size", size, face=face, edges=edges)

    #: Properties offered for editing, in display order. A whitelist rather
    #: than full introspection: Pad alone carries a dozen numeric properties
    #: and prompting through Offset/TaperAngle/Length2 buries the one that
    #: matters.
    _EDITABLE_PROPS = ("Length", "LengthFwd", "Radius", "Size", "Angle",
                       "Thickness", "Value", "Occurrences", "Diameter",
                       "Depth", "HoleCutDiameter", "HoleCutDepth")

    def get_params(self, feature):
        """Editable numeric properties of a feature, with current values."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        exprs = self._expression_map(obj)
        params = []
        for prop in self._EDITABLE_PROPS:
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
            body.Tip = tip_obj
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
            body.Tip = self._require_doc().getObject(tip_name)
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
        if parent_body is not None and getattr(parent_body, "Tip", None) is obj:
            parent_body.Tip = getattr(obj, "BaseFeature", None)
        doc.removeObject(obj.Name)
        try:
            if self._assembly:
                doc.recompute()
            else:
                self._recompute()
        except KernelError as exc:
            raise KernelError(
                "{} supprimé, mais l'aval casse : {}".format(label, exc))
        return self._current_tree()

    def open_part(self, path):
        """Open an existing .FCStd — the user's real files, not our demos.

        M1 scope: single active Body. A multi-body file opens on its first
        Body and says so; a file with none (Part-workbench models, meshes)
        is refused with the reason.
        """
        App = self._app()
        path = self._user_path(
            path, (".FCStd", ".step", ".stp", ".iges", ".igs"),
            must_exist=True)
        if path.lower().endswith((".step", ".stp", ".iges", ".igs")):
            return self._import_cad(path)
        self._close_current()
        doc = App.openDocument(path)
        self._setup_doc(doc)
        bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
        if not bodies:
            links = [o for o in doc.Objects if o.TypeId == "App::Link"]
            if links:
                # C'est un assemblage enregistré par nous : on le rouvre
                # dans le mode qui va avec.
                self._doc, self._body = doc, None
                self._assembly = True
                return self.assembly_tree()
            # Document ouvert ici mais non adopté : le fermer pour ne
            # pas laisser d'orphelin dans App.listDocuments().
            try:
                App.closeDocument(doc.Name)
            except Exception:
                pass
            self._doc = self._body = None
            raise KernelError(
                "aucun corps PartDesign dans ce fichier — il vient "
                "probablement de l'atelier Part (booléennes sans historique "
                "de fonctions), que cette interface ne couvre pas encore")
        self._doc, self._body = doc, bodies[0]
        tree = self.get_tree()
        tree["bodies_in_file"] = len(bodies)
        return tree

    def _import_cad(self, path):
        """Import STEP/IGES : le solide arrive comme base d'un corps —
        toutes les fonctions s'appliquent ensuite dessus."""
        import Part
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolid")
        self._setup_doc(self._doc)
        shape = Part.Shape()
        try:
            shape.read(path)
            label = os.path.splitext(os.path.basename(path))[0]
            body = self._doc.addObject("PartDesign::Body", "Body")
            body.Label = label
            self._body = body
            solids = shape.Solids
            base = self._doc.addObject("Part::Feature", "Imported")
            base.Label = "Import — {}".format(label)
            if solids:
                base.Shape = solids[0]
                body.BaseFeature = base
            else:
                # Que des surfaces : elles restent visibles dans la section
                # Surfaces, le corps attend une première fonction.
                base.Shape = shape
            self._doc.recompute()
            tree = self.get_tree()
            tree["imported_solids"] = len(solids)
            return tree
        except KernelError:
            self._close_current()
            raise
        except Exception as exc:  # noqa: BLE001
            self._close_current()
            raise KernelError(_explain(exc))

    def save_part(self, path):
        """Save as a standard .FCStd — openable in stock FreeCAD.

        The exit door stays open by design: nothing this app produces is
        locked into it.
        """
        doc = self._require_doc()
        path = str(path)
        if not path.endswith(".FCStd"):
            path += ".FCStd"
        path = self._user_path(path, (".FCStd",), must_exist=False)
        doc.saveAs(path)
        return {"path": path}

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
        for prop, value in values.items():
            prop = str(prop)
            if prop not in self._EDITABLE_PROPS:
                raise KernelError("propriété non éditable : {}".format(prop))
            if not hasattr(obj, prop):
                raise KernelError("{} n'a pas de propriété {}".format(
                    obj.Label, prop))
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
            self._recompute()
        except KernelError as exc:
            self._restore_props(obj, previous)
            try:
                self._recompute()
            except KernelError:
                pass  # l'état d'origine était déjà sain : ne pas masquer exc
            raise KernelError(
                "{} — la pièce n'a pas été modifiée".format(exc))
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
        if obj is None and create:
            obj = doc.addObject("App::VarSet", self._VARSET_NAME)
            obj.Label = "Équations"
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
        """Assistant de perçage — version simple.

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
        hole.Label = label_for_type("PartDesign::Hole")
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
        artefacts internes d'une gravure.
        """
        names = set()
        origin = getattr(body, "Origin", None)
        for feature in getattr(origin, "OriginFeatures", None) or ():
            role = getattr(feature, "Role", "")
            if role in self._PLANE_ROLES.values():
                names.add(feature.Name)
        for obj in body.Group:
            if (obj.TypeId == "Sketcher::SketchObject"
                    or obj.isDerivedFrom("PartDesign::Feature")):
                names.add(obj.Name)
        for obj in self._doc.Objects:
            if obj.TypeId == "PartDesign::Body" and not self._is_text_tool(obj):
                names.add(obj.Name)
            elif (obj.TypeId in self._SURFACE_TYPE_IDS
                    and not self._is_text_tool(obj)):
                names.add(obj.Name)
                for sketch in self._surface_sketch_objects(obj):
                    names.add(sketch.Name)
        return names

    def get_tree(self):
        """Arbre de fonctions, vocabulaire du concepteur.

        Forme SolidWorks : les trois plans de référence d'abord, et une
        esquisse consommée par une fonction se range dessous en
        ``children`` plutôt que de polluer le premier niveau.

        Chaque entrée (fonction du corps **et** esquisse imbriquée)
        peut porter deux champs, omis quand ils sont vides :

        - ``deps`` — noms internes des nœuds dont elle dépend
          (``OutList`` filtré). Une arête n'est émise que si sa cible
          est elle-même un nœud du même payload : fonction, esquisse,
          plan de référence, surface ou corps. Aucune arête pendante.
        - ``driven`` — ``{chemin de propriété: expression}``, les
          propriétés pilotées. Chaîne brute, sans parsing des variables.
        """
        body = self._require_body()
        order_of = {obj.Name: i for i, obj in enumerate(self._doc.Objects)}

        consumed = self._consumed_sketches()
        known_names = self._tree_known_names(body)

        def entry(obj):
            item = {
                "name": obj.Name,
                "label": obj.Label,
                "kind": label_for_type(obj.TypeId),
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
            if "FreeSolidTextString" in obj.PropertiesList:
                # Gravure rééditable : le panneau client édite ces valeurs.
                item["text"] = {
                    "text": obj.FreeSolidTextString,
                    "size": float(obj.FreeSolidTextSize),
                    "depth": float(obj.FreeSolidTextDepth),
                    "x": float(obj.FreeSolidTextX),
                    "y": float(obj.FreeSolidTextY),
                }
            deps = visible_deps(
                [o.Name for o in (getattr(obj, "OutList", None) or ())],
                known_names,
            )
            if deps:
                item["deps"] = deps
            driven = self._expression_map(obj)
            if driven:
                item["driven"] = driven
            return item

        items = []
        for obj in body.Group:
            if (obj.TypeId == "Sketcher::SketchObject"
                    and obj.Name in consumed):
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
        planes = [{"id": wire,
                   "label": label_for_origin(self._PLANE_ROLES[wire])}
                  for wire in ("XZ", "XY", "YZ")]
        bodies = []
        for obj in self._doc.Objects:
            if obj.TypeId != "PartDesign::Body":
                continue
            if self._is_text_tool(obj):
                continue  # corps outil d'une gravure : artefact interne
            bodies.append({
                "name": obj.Name,
                "label": obj.Label,
                "active": obj is body,
                "count": len([o for o in obj.Group
                              if o.isDerivedFrom("PartDesign::Feature")
                              or o.TypeId == "Sketcher::SketchObject"]),
                "color": getattr(obj, "FreeSolidColor", "") or None,
                "has_solid": self._body_has_solid(obj),
            })
        surfaces = [self._surface_tree_entry(o, order_of)
                    for o in self._doc.Objects
                    if o.TypeId in self._SURFACE_TYPE_IDS
                    and not self._is_text_tool(o)]
        tip = body.Tip.Name if getattr(body, "Tip", None) else None
        # Variables dans le même appel : le FeatureManager affiche le
        # dossier Équations sans round-trip list_variables.
        return {"body": body.Label, "tip": tip, "bodies": bodies,
                "planes": planes, "features": items,
                "surfaces": surfaces,
                "variables": self.list_variables()["variables"]}

    def tessellate(self, deviation=0.1):
        """Per-face tessellation of the body's current shape.

        Face-by-face on purpose — see ``protocol.pack_mesh``: picking works
        by construction because each OCCT face is its own index group.
        """
        from . import protocol
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        faces = []
        if shape is not None and shape.Faces:
            for i, face in enumerate(shape.Faces):
                vertices, triangles = face.tessellate(float(deviation))
                faces.append(
                    (i, [(v.x, v.y, v.z) for v in vertices], triangles))
        mesh = protocol.pack_mesh(faces)
        mesh["color"] = getattr(body, "FreeSolidColor", "") or None
        # Les autres corps s'affichent estompés, non sélectionnables :
        # on travaille sur le corps actif, on voit la pièce entière.
        # Un maillage par corps (couleur propre) ; ``others`` reste le
        # buffer combiné pour la compatibilité (selftest p9_others_shown).
        other_bodies = []
        for obj in self._doc.Objects:
            if (obj.TypeId != "PartDesign::Body" or obj is body
                    or getattr(obj, "Shape", None) is None
                    or self._is_text_tool(obj)):
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
            if self._is_rolled_back(obj) or self._is_text_tool(obj):
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
            lines.append((i, [(p.x, p.y, p.z) for p in points]))
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
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = "Esquisse"
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
        return self.sketch_state(self._get_sketch(feature).Name)

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
        try:
            sk.solve()
        except Exception:
            pass
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
            "placement": [float(v) for v in matrix],
        }

    @staticmethod
    def _sketch_support_label(sk):
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
                label = label_for_origin(name)
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
        """Répétition linéaire d'entités d'esquisse (grille cols × rows)."""
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
        """Smart dimension: length on a line, radius on a circle or arc,
        distance/angle between two entities.

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
            elif target.TypeId in ("Part::GeomCircle",
                                   "Part::GeomArcOfCircle"):
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
        self._require_doc().recompute()  # les expressions s'évaluent ici
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

        Selftest helper: finds "the top" the way a user's eye does, without
        assuming anything about OCCT's face ordering.
        """
        body = self._require_body()
        best, best_z = None, None
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if normal.z <= 0.5:
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

    def selftest(self):
        """Run the whole flow end to end; return stats worth pasting back.

        Every step prints a live marker to the terminal and any failure
        names the step it died in — a silent selftest is worse than a
        failing one (learned when a user reported "the button does
        nothing").
        """
        report = {"steps": []}

        def mark(name):
            report["steps"].append(name)
            print("selftest> {}".format(name), flush=True)

        try:
            mark("ping")
            report["ping"] = self.ping()

            mark("m0: pièce + esquisse contrainte + bossage")
            tree = self.new_part("Pièce de test")
            report["m0_planes"] = [p["label"] for p in tree["planes"]]
            tree = self.add_rect_sketch(100, 60)
            sk_free = next(
                f["name"] for f in tree["features"]
                if f["type"] == "Sketcher::SketchObject")
            mesh = self.tessellate()
            found = next((s for s in mesh.get("sketches") or []
                          if s["name"] == sk_free), None)
            free_ok = bool(found and found.get("positions"))
            tree = self.add_pad(10)
            report["m0_body_solid"] = (
                bool(tree["bodies"])
                and tree["bodies"][0].get("has_solid") is True)
            mesh = self.tessellate()
            report["p3_free_sketch_in_mesh"] = (
                free_ok
                and not any(s["name"] == sk_free
                            for s in mesh.get("sketches") or []))
            report["m0_faces"] = len(mesh["groups"])

            mark("m0: reparamétrage 10 → 25")
            pad = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            self.set_param(pad, "Length", 25.0)
            report["m0_reparam_ok"] = self.tessellate() != mesh

            mark("m1: esquisse sur face + enlèvement à travers tout + congé")
            top = self._top_face_id()
            report["m1_top_face"] = top
            self.add_rect_sketch(40, 20, face=top)
            self.add_pocket(through=True)
            report["m1_pocket_faces"] = len(self.tessellate()["groups"])
            tree = self.add_fillet(3, face=self._top_face_id())
            report["m1_fillet_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("m1.5: barre de retour aller-retour")
            pad_feature = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pad")
            faces_rolled = len(self.tessellate()["groups"])
            self.set_tip(pad_feature)
            report["m15_rollback_changes_shape"] = (
                len(self.tessellate()["groups"]) != faces_rolled)
            self.tip_to_end()

            mark("m1.5: enregistrer puis rouvrir")
            import tempfile
            path = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.FCStd")
            self.save_part(path)
            tree_before = self.get_tree()
            reopened = self.open_part(path)
            report["m15_roundtrip_ok"] = (
                [f["type"] for f in reopened["features"]]
                == [f["type"] for f in tree_before["features"]])

            mark("m2: rectangle dessiné ligne à ligne")
            state = self.sketch_start()
            name = state["sketch"]
            self.sketch_add_line(name, 0, 0, 80, 0)
            self.sketch_add_line(name, 80, 0, 80, 40)
            self.sketch_add_line(name, 80, 40, 0, 40)
            self.sketch_add_line(name, 0, 40, 0, 0)
            constraints = len(self._get_sketch(name).Constraints)
            # 4 snapped lines: 4 coincidents + 2 horizontal + 2 vertical.
            report["m2_autoconstraints"] = constraints
            report["m2_autoconstraints_ok"] = constraints >= 8

            mark("m2: drag suivi par le solveur")
            self.sketch_move(name, 1, 2, 85, 45)

            mark("m2: cote pilotante à 90")
            state = self.sketch_dim(name, 0)
            dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(name, dim, 90)
            report["m2_dim_drives"] = any(
                abs(d["value"] - 90) < 1e-6 for d in state["dims"])
            report["m2_dof"] = state["dof"]

            mark("m2: extrusion du profil dessiné")
            self.sketch_finish(name)
            tree = self.add_pad(8, sketch=name)
            report["m2_pad_on_drawn_sketch_ok"] = not any(
                f["error"] for f in tree["features"])
            # L'esquisse consommée doit être rangée SOUS son bossage.
            report["m2_sketch_nested_ok"] = any(
                child["name"] == name
                for f in tree["features"]
                for child in f.get("children", ()))

            mark("p1: annuler / rétablir via transactions")
            state = self.sketch_start()
            sk_name = state["sketch"]
            out = dispatch(self, "sketch_add_line",
                           {"sketch": sk_name,
                            "x1": 0, "y1": 0, "x2": 10, "y2": 0})
            if not out["ok"]:
                raise KernelError(out["error"])
            count = len(self._get_sketch(sk_name).Geometry)
            self.undo()
            report["p1_undo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count - 1)
            self.redo()
            report["p1_redo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count)

            mark("p1: géométrie de construction")
            state = self.sketch_toggle_construction(sk_name, 0)
            report["p1_construction_ok"] = bool(
                state["entities"][0].get("construction"))
            self.sketch_finish(sk_name)

            mark("p1: esquisse sur plan nommé (XZ = Plan de face)")
            state = self.sketch_start(plane="XZ")
            identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            report["p1_plane_ok"] = (
                [round(v, 6) for v in state["placement"]] != identity)
            self.sketch_finish(state["sketch"])

            mark("p1: export STL + STEP")
            stl = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest.stl")
            step = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.step")
            report["p1_export_stl_ok"] = self.export_part(stl)["size"] > 0
            report["p1_export_step_ok"] = self.export_part(step)["size"] > 0

            mark("p2: révolution (tube) + enlèvement avec révolution")
            self.new_part("Pièce révolution")
            state = self.sketch_start()
            rev_sk = state["sketch"]
            for line in ((10, 0, 30, 0), (30, 0, 30, 20),
                         (30, 20, 10, 20), (10, 20, 10, 0)):
                self.sketch_add_line(rev_sk, *line)
            self.sketch_finish(rev_sk)
            tree = self.add_revolution(360, sketch=rev_sk)
            report["p2_revolution_ok"] = not any(
                f["error"] for f in tree["features"])
            state = self.sketch_start()
            groove_sk = state["sketch"]
            for line in ((15, 8, 25, 8), (25, 8, 25, 12),
                         (25, 12, 15, 12), (15, 12, 15, 8)):
                self.sketch_add_line(groove_sk, *line)
            self.sketch_finish(groove_sk)
            tree = self.add_groove(360, sketch=groove_sk)
            report["p2_groove_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: symétrie + répétition linéaire")
            self.new_part("Pièce symétrie")
            state = self.sketch_start()
            sym_sk = state["sketch"]
            for line in ((0, -10, 20, -10), (20, -10, 20, 10),
                         (20, 10, 0, 10), (0, 10, 0, -10)):
                self.sketch_add_line(sym_sk, *line)
            self.sketch_finish(sym_sk)
            self.add_pad(10, sketch=sym_sk)
            tree = self.add_mirror(plane="YZ")
            report["p2_mirror_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_linear_pattern(length=20, count=2, axis="Y")
            report["p2_linear_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: répétition circulaire (4 perçages)")
            self.new_part("Pièce répétition")
            self.add_rect_sketch(60, 60)
            self.add_pad(6)
            state = self.sketch_start(face=self._top_face_id())
            pat_sk = state["sketch"]
            self.sketch_add_circle(pat_sk, 20, 0, 4)
            self.sketch_finish(pat_sk)
            self.add_pocket(through=True)
            tree = self.add_polar_pattern(count=4)
            report["p2_polar_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: dépouille + coque")
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            top = self._top_face_id()
            try:
                self.add_draft(face=top, angle=5, neutral="XY")
                report["p2_draft_noop_refuse"] = False
            except KernelError:
                tree = self.get_tree()
                report["p2_draft_noop_refuse"] = not any(
                    f["type"] == "PartDesign::Draft" for f in tree["features"])
            vol_before = float(self._require_body().Shape.Volume)
            tree = self.add_draft(face=top, angle=5, neutral="XZ")
            report["p2_draft_neutral_ok"] = (
                not any(f["error"] for f in tree["features"])
                and abs(float(self._require_body().Shape.Volume)
                        - vol_before) > 1e-9)
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            tree = self.add_draft(face=self._side_face_id(), angle=5)
            report["p2_draft_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_thickness(self._top_face_id(), 2)
            report["p2_thickness_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p4: aperçu jaune (exécuté puis annulé)")
            # Sur sa propre géométrie saine : chanfreiner le bord d'une
            # coque dépouillée segfaultait ChFi3d dans OCCT 7.8 (SIGSEGV
            # vu sur 1.1.3) — un crash C++, ininterceptable en Python.
            self.new_part("Pièce aperçu")
            self.add_rect_sketch(30, 30)
            self.add_pad(10)
            count = len(self.get_tree()["features"])
            faces_now = len(self.tessellate()["groups"])
            ghost = self.preview(
                "add_chamfer", {"face": self._top_face_id(), "size": 2})
            report["p4_preview_changes_mesh"] = (
                len(ghost["groups"]) != faces_now)
            report["p4_preview_leaves_doc_intact"] = (
                len(self.get_tree()["features"]) == count
                and len(self.tessellate()["groups"]) == faces_now)
            vol_before = float(self._require_body().Shape.Volume)
            top_edges = [i for i, e in
                         enumerate(self._require_body().Shape.Edges)
                         if abs(e.CenterOfMass.z - 10) < 1e-6]
            tree = self.add_chamfer(size=2, edges=[top_edges[0]])
            vol_chamfered = float(self._require_body().Shape.Volume)
            report["p4_chamfer_commit_ok"] = (
                not any(f["error"] for f in tree["features"])
                and (vol_chamfered < vol_before - 1e-6
                     or len(self.tessellate()["groups"]) > faces_now))
            chamfer_name = next(f["name"] for f in tree["features"]
                                if f["type"] == "PartDesign::Chamfer")
            tree = self.delete_feature(chamfer_name)
            chamfer_gone = (
                not any(f["type"] == "PartDesign::Chamfer"
                        for f in tree["features"])
                and not any(f["error"] for f in tree["features"]))
            # delete_feature du Tip laisse Tip=None et Shape invalide
            # (constat P007, hors périmètre). Indicateur faux, l'étape
            # continue — p5 repart sur une pièce neuve.
            try:
                vol_restored = abs(
                    float(self._require_body().Shape.Volume)
                    - vol_before) < 1e-6
            except RuntimeError:
                vol_restored = False
            report["p4_delete_feature_ok"] = chamfer_gone and vol_restored

            mark("p5: congé sur arêtes")
            self.new_part("Pièce arêtes")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            edges_pack = self.tessellate_edges()
            report["p5_edges"] = len(edges_pack["groups"])
            top_edges = [i for i, e in
                         enumerate(self._require_body().Shape.Edges)
                         if abs(e.CenterOfMass.z - 10) < 1e-6]
            report["p5_top_edges"] = len(top_edges)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_fillet(radius=3, edges=top_edges)
            report["p5_edge_fillet_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("p6: assistant de perçage (2 trous lamés)")
            self.new_part("Pièce perçages")
            self.add_rect_sketch(60, 40)
            self.add_pad(8)
            state = self.sketch_start(face=self._top_face_id())
            hole_sk = state["sketch"]
            self.sketch_add_circle(hole_sk, -15, 0, 3)
            self.sketch_add_circle(hole_sk, 15, 0, 3)
            self.sketch_finish(hole_sk)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_hole(diameter=6, through=True,
                                 cut="lamage", cut_diameter=11, cut_depth=3)
            report["p6_hole_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("p6: renommer + édition atomique")
            hole_name = next(f["name"] for f in tree["features"]
                             if f["type"] == "PartDesign::Hole")
            tree = self.rename(hole_name, "Perçages de fixation")
            report["p6_rename_ok"] = any(
                f["label"] == "Perçages de fixation"
                for f in tree["features"])
            self.set_params(hole_name, {"Diameter": 8.0})
            report["p6_set_params_ok"] = any(
                p["prop"] == "Diameter" and abs(p["value"] - 8.0) < 1e-9
                for p in self.get_params(hole_name)["params"])

            mark("p7: paramétrique — cote nommée, variable, équation")
            self.new_part("Pièce paramétrique")
            state = self.sketch_start()
            par = state["sketch"]
            self.sketch_add_line(par, 0, 0, 60, 0)     # géo 0 : largeur
            self.sketch_add_line(par, 60, 0, 60, 30)   # géo 1 : hauteur
            state = self.sketch_dim(par, 0)            # cote sur la largeur
            width_dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(par, width_dim,
                                        value=60, name="largeur")
            report["p7_named_dim_ok"] = any(
                d["id"] == width_dim and d["name"] == "largeur"
                for d in state["dims"])
            self.set_variable("coef", 2.0)
            state = self.sketch_dim(par, 1)            # cote sur la hauteur
            height_dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(
                par, height_dim,
                expr=".Constraints.largeur / Variables.coef")
            height = next(d for d in state["dims"] if d["id"] == height_dim)
            report["p7_equation_ok"] = abs(height["value"] - 30.0) < 1e-6
            report["p7_equation_shown"] = bool(height["expr"])
            listed = self.list_variables()
            report["p7_list_variables_ok"] = any(
                v["name"] == "coef" and abs(v["value"] - 2.0) < 1e-9
                for v in listed["variables"])
            tree = self.get_tree()
            report["p7_tree_variables"] = any(
                v["name"] == "coef" and abs(v["value"] - 2.0) < 1e-9
                for v in tree.get("variables", []))
            self.set_variable("jetable", 1.0)
            listed = self.list_variables()
            self.delete_variable("jetable")
            listed_after = self.list_variables()
            report["p7_delete_variable_ok"] = (
                any(v["name"] == "jetable" for v in listed["variables"])
                and not any(v["name"] == "jetable"
                            for v in listed_after["variables"]))

            mark("p7: expression sur une fonction (Length = largeur/10)")
            self.sketch_add_line(par, 60, 30, 0, 30)
            self.sketch_add_line(par, 0, 30, 0, 0)
            self.sketch_finish(par)
            tree = self.add_pad(10, sketch=par)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.set_params(pad_name, {
                "Length": "{}.Constraints.largeur / 10".format(par)})
            pad_length = next(
                p for p in self.get_params(pad_name)["params"]
                if p["prop"] == "Length")
            report["p7_feature_expr_ok"] = (
                abs(pad_length["value"] - 6.0) < 1e-6
                and bool(pad_length.get("expr")))

            mark("p7: relations — concentrique, colinéaire, milieu, fixe")
            state = self.sketch_start()
            rel = state["sketch"]
            self.sketch_add_circle(rel, 0, 0, 10)      # géo 0
            self.sketch_add_circle(rel, 5, 5, 4)       # géo 1
            state = self.sketch_constrain(rel, "concentric", 0, geo2=1)
            circles = [e for e in state["entities"] if e["type"] == "circle"]
            report["p7_concentric_ok"] = (
                abs(circles[0]["c"][0] - circles[1]["c"][0]) < 1e-6
                and abs(circles[0]["c"][1] - circles[1]["c"][1]) < 1e-6)
            self.sketch_add_line(rel, 20, 0, 40, 2)    # géo 2
            self.sketch_add_line(rel, 45, 3, 60, 5)    # géo 3
            self.sketch_constrain(rel, "collinear", 2, geo2=3)
            self.sketch_add_circle(rel, 25, 10, 2)     # géo 4
            state = self.sketch_constrain(rel, "midpoint", 2,
                                          geo2=4, point2=3)
            self.sketch_constrain(rel, "fixed", 3)
            report["p7_relations_ok"] = True

            mark("p7: lister et supprimer une relation")
            listed = self.sketch_constraints(rel, geo=2)
            report["p7_list_count"] = len(listed["constraints"])
            before = len(self._get_sketch(rel).Constraints)
            self.sketch_delete_constraint(
                rel, listed["constraints"][-1]["id"])
            report["p7_delete_constraint_ok"] = (
                len(self._get_sketch(rel).Constraints) == before - 1)
            self.sketch_finish(rel)

            mark("p8: plan de référence décalé + lissage")
            self.new_part("Pièce lissage")
            tree = self.add_datum_plane(base="XY", offset=30)
            datum = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Plane")
            report["p8_datum_has_placement"] = any(
                "placement" in f for f in tree["features"])
            self.add_rect_sketch(40, 40)
            base_sk = self._latest_sketch().Name
            state = self.sketch_start(datum=datum)
            top_sk = state["sketch"]
            for line in ((-10, -10, 10, -10), (10, -10, 10, 10),
                         (10, 10, -10, 10), (-10, 10, -10, -10)):
                self.sketch_add_line(top_sk, *line)
            self.sketch_finish(top_sk)
            tree = self.add_loft(sketches=[base_sk, top_sk])
            report["p8_loft_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > 0)

            mark("p8: balayage (profil + trajectoire)")
            self.new_part("Pièce balayage")
            state = self.sketch_start(plane="XZ")
            spine_sk = state["sketch"]
            self.sketch_add_line(spine_sk, 0, 0, 0, 30)
            self.sketch_add_line(spine_sk, 0, 30, 25, 30)
            self.sketch_finish(spine_sk)
            state = self.sketch_start()
            prof_sk = state["sketch"]
            self.sketch_add_circle(prof_sk, 0, 0, 4)
            self.sketch_finish(prof_sk)
            tree = self.add_sweep(profile=prof_sk, spine=spine_sk)
            report["p8_sweep_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p8: hélice (ressort)")
            self.new_part("Pièce hélice")
            state = self.sketch_start(plane="XZ")
            hel_sk = state["sketch"]
            self.sketch_add_circle(hel_sk, 15, 0, 2)
            self.sketch_finish(hel_sk)
            tree = self.add_helix(pitch=8, height=40, sketch=hel_sk)
            report["p8_helix_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p9: multi-corps + Combiner (soustraction)")
            self.new_part("Pièce multi-corps")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            first_body = self._require_body().Name
            tree = self.add_body("Corps outil")
            report["p9_two_bodies"] = (
                len(tree["bodies"]) == 2
                and any(b["active"] and b["label"] == "Corps outil"
                        for b in tree["bodies"]))
            state = self.sketch_start()
            tool_sk = state["sketch"]
            self.sketch_add_circle(tool_sk, 0, 0, 8)
            self.sketch_finish(tool_sk)
            self.add_pad(30)
            report["p9_others_shown"] = "others" in self.tessellate()
            tool_body = self._require_body().Name
            self.set_active_body(first_body)
            tree = self.set_body_color(first_body, "#cc5533")
            report["p9_color_ok"] = any(
                b["name"] == first_body and b.get("color") == "#cc5533"
                for b in tree["bodies"])
            try:
                self.set_body_color(first_body, "rouge")
                report["p9_color_invalid_ok"] = False
            except KernelError:
                report["p9_color_invalid_ok"] = True
            import tempfile
            color_path = os.path.join(tempfile.gettempdir(),
                                      "freesolid-selftest-color.FCStd")
            self.save_part(color_path)
            reopened = self.open_part(color_path)
            report["p9_color_persist_ok"] = any(
                b["name"] == first_body and b.get("color") == "#cc5533"
                for b in reopened["bodies"])
            self.set_active_body(first_body)
            faces_before = len(self.tessellate()["groups"])
            tree = self.add_boolean(tool=tool_body, type="cut")
            report["p9_boolean_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_before)

            mark("p10: assemblage — deux instances d'une pièce")
            self.new_part("Pièce à assembler")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            asm_part = os.path.join(tempfile.gettempdir(),
                                    "freesolid-selftest-part.FCStd")
            self.save_part(asm_part)
            self.new_assembly()
            self.insert_component(asm_part)
            tree = self.insert_component(asm_part)
            report["p10_two_components"] = len(tree["components"]) == 2
            second = tree["components"][1]["name"]
            tree = self.move_component(second, x=30, z=10, yaw=45)
            moved = next(c for c in tree["components"]
                         if c["name"] == second)
            report["p10_move_ok"] = abs(moved["position"][0] - 30) < 1e-9
            meshes = self.tessellate_assembly()
            report["p10_assembly_meshes_ok"] = (
                len(meshes["components"]) == 2
                and all(c["mesh"]["indices"]
                        for c in meshes["components"]))

            mark("p10: contrainte fixe — le solveur déplace le composant")
            first_comp = tree["components"][0]["name"]
            report["p10_first_grounded"] = tree["components"][0]["grounded"]
            tree = self.add_joint(first_comp, second,
                                  type="fixe", sub1="Face1", sub2="Face1")
            report["p10_joints_listed"] = len(tree.get("joints", ())) >= 2
            comp2 = next(c for c in tree["components"]
                         if c["name"] == second)
            # Il était en (30, 0, 10) yaw 45 — la contrainte fixe doit
            # l'avoir ramené ailleurs.
            report["p10_joint_solved"] = (
                abs(comp2["position"][0] - 30) > 1e-6
                or abs(comp2["position"][2] - 10) > 1e-6
                or abs(comp2["rotation"][0] - 45) > 1e-6)
            asm = self.assembly_tree()
            report["p10_assembly_tree_ok"] = (
                len(asm["components"]) == 2
                and len(asm.get("joints", ())) >= 2)
            solved = self.solve_assembly()
            report["p10_solve_op_ok"] = (
                len(solved["components"]) == 2
                and "joints" in solved)
            # 2 existants + (3 - 1) copies du second = 4 composants.
            arrayed = self.array_component(second, count=3, dx=80)
            report["p10_array_ok"] = len(arrayed["components"]) == 4

            mark("p16: interférences (les instances se chevauchent)")
            inter = self.check_interference()
            report["p16_interference_found"] = (
                len(inter["interferences"]) >= 1)

            mark("p11: évaluer (masse PLA) + mesurer")
            self.new_part("Pièce évaluée")
            self.add_rect_sketch(10, 10)
            self.add_pad(10)
            props = self.mass_properties(density=1.24)
            report["p11_volume_ok"] = abs(props["volume_mm3"] - 1000.0) < 1e-6
            report["p11_mass_ok"] = abs(props["mass_g"] - 1.24) < 1e-9
            body_shape = self._require_body().Shape
            bottom = next(
                i for i, f in enumerate(body_shape.Faces)
                if f.normalAt(*[sum(f.ParameterRange[k:k + 2]) / 2
                                for k in (0, 2)]).z < -0.5)
            distance = self.measure(
                "face", self._top_face_id(), "face", bottom)["distance"]
            report["p11_measure_ok"] = abs(distance - 10.0) < 1e-6

            mark("spike: solveur d'assemblage headless (rapport)")
            report["spike_assembly"] = self.spike_assembly()
            import json
            print("selftest> spike assemblage : " + json.dumps(
                report["spike_assembly"], ensure_ascii=False), flush=True)

            mark("p12: surfacique — extrusion, couture, épaississement")
            self.new_part("Pièce surfaces")
            state = self.sketch_start()
            surf_sk1 = state["sketch"]
            self.sketch_add_line(surf_sk1, 0, 0, 40, 0)  # profil OUVERT
            self.sketch_finish(surf_sk1)
            tree = self.surface_extrude(20, sketch=surf_sk1)
            report["p12_surface_ok"] = len(tree["surfaces"]) == 1
            report["p12_body_not_solid"] = (
                bool(tree["bodies"])
                and tree["bodies"][0].get("has_solid") is False)
            surf = tree["surfaces"][0]
            mesh = self.tessellate()
            surf_meshes = mesh.get("surfaces") or []
            report["p12_surface_mesh"] = (
                isinstance(surf_meshes, list)
                and len(surf_meshes) == 1
                and surf_meshes[0].get("name") == surf["name"]
                and len(surf_meshes[0].get("positions") or []) > 0)
            sk_child = next(
                (c for c in surf.get("children") or []
                 if c.get("name") == surf_sk1),
                None)
            report["p12_surface_order"] = (
                isinstance(surf.get("order"), int)
                and sk_child is not None
                and isinstance(sk_child.get("order"), int)
                and surf["order"] > sk_child["order"])
            state = self.sketch_start()
            surf_sk2 = state["sketch"]
            self.sketch_add_line(surf_sk2, 0, 0, 0, 30)
            self.sketch_finish(surf_sk2)
            tree = self.surface_extrude(20, sketch=surf_sk2)
            names = [s["name"] for s in tree["surfaces"]]
            tree = self.surface_sew(names)
            report["p12_sew_ok"] = len(tree["surfaces"]) == 3
            tree = self.surface_thicken(names[0], 2)
            thick = self._require_doc().getObject(
                tree["surfaces"][-1]["name"])
            report["p12_thicken_solid_ok"] = bool(thick.Shape.Solids)
            state = self.sketch_start()
            rev_sk = state["sketch"]
            self.sketch_add_line(rev_sk, 20, 0, 20, 30)
            self.sketch_finish(rev_sk)
            n_surfaces = len(self.get_tree()["surfaces"])
            tree = self.surface_revolve(360, sketch=rev_sk)
            report["p12_surface_revolve_ok"] = (
                any(s["label"] == "Surface de révolution"
                    for s in tree["surfaces"])
                and len(tree["surfaces"]) > n_surfaces)
            state = self.sketch_start()
            loft_a = state["sketch"]
            self.sketch_add_line(loft_a, 0, 0, 40, 0)
            self.sketch_finish(loft_a)
            tree = self.add_datum_plane(base="XY", offset=25)
            datum = next(f["name"] for f in tree["features"]
                         if f["type"] == "PartDesign::Plane")
            state = self.sketch_start(datum=datum)
            loft_b = state["sketch"]
            self.sketch_add_line(loft_b, -10, -10, 10, 10)
            self.sketch_finish(loft_b)
            n_surfaces = len(self.get_tree()["surfaces"])
            tree = self.surface_loft([loft_a, loft_b])
            report["p12_surface_loft_ok"] = (
                any(s["label"] == "Surface lissée" for s in tree["surfaces"])
                and len(tree["surfaces"]) > n_surfaces)

            # Surfaces paramétriques : édition, suivi d'esquisse, expression,
            # persistance après save/open.
            self.new_part("Pièce surface edit")
            state = self.sketch_start()
            edit_sk = state["sketch"]
            self.sketch_add_line(edit_sk, 0, 0, 40, 0)
            self.sketch_finish(edit_sk)
            tree = self.surface_extrude(20, sketch=edit_sk)
            surf = tree["surfaces"][-1]
            surf_obj = self._require_doc().getObject(surf["name"])
            area_20 = float(surf_obj.Shape.Area)
            self.set_params(surf["name"], {"LengthFwd": 40.0})
            surf_obj = self._require_doc().getObject(surf["name"])
            area_40 = float(surf_obj.Shape.Area)
            report["p12_surface_edit_ok"] = (
                surf.get("type") == "Part::Extrusion"
                and edit_sk in (surf.get("sketches") or [])
                and abs(area_40 - 2.0 * area_20) < 1e-3)
            self.sketch_edit(edit_sk)
            self.sketch_move(edit_sk, 0, 2, 80, 0)
            self.sketch_finish(edit_sk)
            surf_obj = self._require_doc().getObject(surf["name"])
            area_follow = float(surf_obj.Shape.Area)
            report["p12_surface_follows_sketch_ok"] = (
                abs(area_follow - 2.0 * area_40) < 1e-2
                and "Invalid" not in (surf_obj.State or ()))
            self.set_params(surf["name"], {"LengthFwd": "15 * 2"})
            surf_obj = self._require_doc().getObject(surf["name"])
            length_expr = float(getattr(
                surf_obj.LengthFwd, "Value", surf_obj.LengthFwd))
            report["p12_surface_expr_ok"] = abs(length_expr - 30.0) < 1e-6
            surf_path = os.path.join(tempfile.gettempdir(),
                                     "freesolid-surface-edit.FCStd")
            self.save_part(surf_path)
            self.open_part(surf_path)
            tree = self.get_tree()
            reopened = next(
                (s for s in tree["surfaces"]
                 if s.get("type") == "Part::Extrusion"),
                None)
            if reopened is None:
                report["p12_surface_reopen_ok"] = False
            else:
                self.set_params(reopened["name"], {"LengthFwd": 25.0})
                reopened_obj = self._require_doc().getObject(reopened["name"])
                length_re = float(getattr(
                    reopened_obj.LengthFwd, "Value", reopened_obj.LengthFwd))
                report["p12_surface_reopen_ok"] = (
                    abs(length_re - 25.0) < 1e-6
                    and bool(reopened_obj.Shape.Faces)
                    and "Invalid" not in (reopened_obj.State or ()))

            mark("p12: courbe 3D + balayage dessus")
            curve_tree = self.add_curve3d(
                [[0, 0, 0], [0, 0, 30], [20, 0, 50]], spline=True)
            curve_name = curve_tree["surfaces"][-1]["name"]
            state = self.sketch_start()
            pipe_sk = state["sketch"]
            self.sketch_add_circle(pipe_sk, 0, 0, 3)
            self.sketch_finish(pipe_sk)
            tree = self.add_sweep(profile=pipe_sk, spine=curve_name)
            report["p12_sweep_on_curve_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p30: barre de retour — surfaces et esquisses libres")
            self.new_part("Pièce reprise P030")
            self.add_rect_sketch(40, 20)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            state = self.sketch_start()
            free_sk = state["sketch"]
            self.sketch_add_line(free_sk, 0, 0, 30, 0)
            self.sketch_finish(free_sk)
            state = self.sketch_start()
            surf_sk = state["sketch"]
            self.sketch_add_line(surf_sk, 0, 0, 20, 0)
            self.sketch_finish(surf_sk)
            tree = self.surface_extrude(15, sketch=surf_sk)
            surf_name = tree["surfaces"][-1]["name"]

            tree = self.set_tip(free_sk)
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_set_tip_on_sketch"] = (
                tree["tip"] == pad_name
                and free_entry.get("rolled_back") is not True
                and surf_entry.get("rolled_back") is True)
            mesh = self.tessellate()
            report["p30_rolled_surface_absent_mesh"] = not any(
                s.get("name") == surf_name
                for s in mesh.get("surfaces") or [])

            tree = self.set_tip(surf_name)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_set_tip_on_surface"] = (
                tree["tip"] == pad_name
                and surf_entry.get("rolled_back") is not True)

            tree = self.set_tip(pad_name)
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            mesh = self.tessellate()
            report["p30_rolled_sketch_absent_mesh"] = (
                free_entry.get("rolled_back") is True
                and not any(s.get("name") == free_sk
                            for s in mesh.get("sketches") or []))
            try:
                self.add_pad(5)
                report["p30_rolled_sketch_not_reusable"] = False
            except KernelError as exc:
                report["p30_rolled_sketch_not_reusable"] = (
                    "aucune esquisse disponible" in str(exc))

            tree = self.tip_to_end()
            mesh = self.tessellate()
            free_entry = next(f for f in tree["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in tree["surfaces"]
                              if s["name"] == surf_name)
            report["p30_tip_to_end_restores"] = (
                tree["tip"] == pad_name
                and free_entry.get("rolled_back") is not True
                and surf_entry.get("rolled_back") is not True
                and any(s.get("name") == surf_name
                        for s in mesh.get("surfaces") or [])
                and any(s.get("name") == free_sk
                        for s in mesh.get("sketches") or []))

            mark("p13: mise en plan DXF (3 vues, cotes, coupe)")
            self.new_part("Pièce plan")
            self.add_rect_sketch(30, 20)
            self.add_pad(10)
            dxf = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest.dxf")
            drawing = self.make_drawing(dxf, dims=True, section="Y")
            report["p13_drawing_ok"] = drawing["size"] > 0
            report["p13_dims_ok"] = drawing.get("dims_ok") is True
            report["p13_section_ok"] = drawing.get("section_ok") is True
            report["p13_drawing_clean_ok"] = not any(
                o.TypeId.startswith("TechDraw::")
                for o in self._require_doc().Objects)

            mark("p14: convertir les entités (contour de face)")
            self.new_part("Pièce conversion")
            self.add_rect_sketch(30, 20)
            self.add_pad(6)
            state = self.sketch_start(face=self._top_face_id())
            conv = state["sketch"]
            state = self.sketch_convert(conv)
            report["p14_convert_ok"] = (
                state["converted"] == 4 and state["skipped"] == 0)
            self.sketch_finish(conv)

            mark("p15: gravure de texte")
            self.new_part("Pièce gravée")
            self.add_rect_sketch(60, 20)
            self.add_pad(5)
            faces_now = len(self.tessellate()["groups"])
            tree = self.add_text("AB", face=self._top_face_id(),
                                 size=8, depth=1)
            # Volume et validité, pas seulement le compte de faces : la
            # gravure « AB » rendait un corps invalide de 17 mm³ (faces de
            # glyphes d'aire négative) sans que ce test le voie (P032).
            plate = self._require_body().Shape
            report["p15_text_ok"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["groups"]) > faces_now
                and plate.isValid()
                and 5900.0 < float(plate.Volume) < 5999.9)

            mark("p17: spline, ellipse, symétrie, répétition et décalage")
            self.new_part("Pièce esquisse confort")
            state = self.sketch_start()
            comfort = state["sketch"]
            state = self.sketch_add_spline(
                comfort, [[0, 0], [10, 8], [20, -4], [30, 6]])
            spline = next((e for e in state["entities"]
                           if e.get("kind") == "spline"), None)
            report["p17_spline_ok"] = (
                spline is not None
                and spline.get("type") == "poly"
                and (spline.get("npoints") or 0) >= 3)
            state = self.sketch_add_ellipse(comfort, 50, 0, 12, 6,
                                            angle=15)
            ellipse = next((e for e in state["entities"]
                            if e.get("kind") == "ellipse"), None)
            report["p17_ellipse_ok"] = (
                len(state["entities"]) == 2
                and ellipse is not None
                and abs(ellipse.get("rx", 0) - 12) < 1e-4
                and abs(ellipse.get("ry", 0) - 6) < 1e-4)
            self.sketch_add_line(comfort, 0, 20, 20, 30)   # géo 2
            self.sketch_add_line(comfort, 0, 40, 40, 40)   # géo 3 : axe
            state = self.sketch_mirror(comfort, [2], 3)
            report["p17_mirror_ok"] = len(state["entities"]) == 5
            state = self.sketch_array(comfort, [2], dx=15, dy=0,
                                      cols=3, rows=1)
            # 2 copies + 2 lignes de construction qui pilotent le pas
            # (comportement addRectangularArray, sondé sur 1.0.2).
            report["p17_array_ok"] = len(state["entities"]) == 9
            self.sketch_finish(comfort)

            state = self.sketch_start()
            offset_sk = state["sketch"]
            self.sketch_add_line(offset_sk, 0, 0, 40, 0)
            self.sketch_add_line(offset_sk, 40, 0, 40, 30)
            self.sketch_add_line(offset_sk, 40, 30, 0, 30)
            state = self.sketch_add_line(offset_sk, 0, 30, 0, 0)
            orig_lines = [e for e in state["entities"] if e["type"] == "line"]
            before = len(state["entities"])
            state = self.sketch_offset(offset_sk, [0, 1, 2, 3], 5.0)
            new_ents = state["entities"][before:]
            dist_ok = False
            for new_line in new_ents:
                if new_line["type"] != "line":
                    continue
                for orig in orig_lines:
                    oh = abs(orig["p1"][1] - orig["p2"][1]) < 1e-6
                    nh = abs(new_line["p1"][1] - new_line["p2"][1]) < 1e-6
                    if oh and nh:
                        gap = abs(orig["p1"][1] - new_line["p1"][1])
                        if abs(gap - 5.0) < 1e-4:
                            dist_ok = True
                    ov = abs(orig["p1"][0] - orig["p2"][0]) < 1e-6
                    nv = abs(new_line["p1"][0] - new_line["p2"][0]) < 1e-6
                    if ov and nv:
                        gap = abs(orig["p1"][0] - new_line["p1"][0])
                        if abs(gap - 5.0) < 1e-4:
                            dist_ok = True
            report["p17_offset_ok"] = len(new_ents) >= 4 and dist_ok

            state = self.sketch_add_circle(offset_sk, 80, 0, 10)
            circ = next(e for e in state["entities"] if e["type"] == "circle")
            known = {e["id"] for e in state["entities"]}
            state = self.sketch_offset(offset_sk, [circ["id"]], 5.0)
            report["p17_offset_circle_ok"] = any(
                e["type"] == "circle" and e["id"] not in known
                and (abs(e["r"] - 15.0) < 1e-4 or abs(e["r"] - 5.0) < 1e-4)
                for e in state["entities"])

            state = self.sketch_add_line(offset_sk, 200, 0, 220, 0)
            id_a = state["entities"][-1]["id"]
            state = self.sketch_add_line(offset_sk, 200, 30, 220, 30)
            id_b = state["entities"][-1]["id"]
            disjoint_ok = False
            try:
                self.sketch_offset(offset_sk, [id_a, id_b], 5.0)
            except KernelError as exc:
                disjoint_ok = "chaîne connexe" in str(exc)
            report["p17_offset_disjoint_ok"] = disjoint_ok
            self.sketch_finish(offset_sk)

            mark("p18: import STEP + export 3MF")
            tree = self.open_part(os.path.join(
                tempfile.gettempdir(), "freesolid-selftest.step"))
            report["p18_step_import_ok"] = (
                tree.get("imported_solids", 0) >= 1
                and len(self.tessellate()["groups"]) > 0)
            threemf = os.path.join(tempfile.gettempdir(),
                                   "freesolid-selftest.3mf")
            report["p18_3mf_ok"] = self.export_part(threemf)["size"] > 0

            mark("p3: arc, rainure, polygone")
            import math
            self.new_part("Pièce esquisse avancée")

            state = self.sketch_start()
            zero_sk = state["sketch"]
            n_before = len(state["entities"])
            refused = False
            try:
                self.sketch_add_line(zero_sk, 17.8, -15.1, 17.8, -15.1)
            except KernelError as exc:
                refused = "longueur nulle" in str(exc)
            n_after = len(self.sketch_state(zero_sk)["entities"])
            report["p3_zero_line_refused"] = refused and n_after == n_before

            self.sketch_add_line(zero_sk, 0, 0, 40, 0)
            open_tree = self.sketch_finish(zero_sk)
            state = self.sketch_start()
            rect_sk = state["sketch"]
            self.sketch_add_line(rect_sk, 0, 0, 80, 0)
            self.sketch_add_line(rect_sk, 80, 0, 80, 40)
            self.sketch_add_line(rect_sk, 80, 40, 0, 40)
            self.sketch_add_line(rect_sk, 0, 40, 0, 0)
            closed_tree = self.sketch_finish(rect_sk)
            report["p3_open_profile_flag"] = (
                open_tree.get("open_profile") is True
                and closed_tree.get("open_profile") is False)

            state = self.sketch_start()
            adv = state["sketch"]
            state = self.sketch_add_arc(adv, 0, 0, 20, 0, math.pi / 2)
            report["p3_arc_ok"] = state["entities"][-1]["type"] == "arc"
            before = len(state["entities"])
            state = self.sketch_add_slot(adv, 0, -30, 40, -30, 10)
            report["p3_slot_ok"] = len(state["entities"]) == before + 4
            before = len(state["entities"])
            state = self.sketch_add_polygon(adv, 80, 0, 90, 0, 6)
            report["p3_polygon_ok"] = len(state["entities"]) >= before + 6
            self.sketch_finish(adv)
            edited = self.sketch_edit(adv)
            self.sketch_state(adv)
            report["p3_sketch_edit_ok"] = (
                any(e["type"] == "arc" for e in edited["entities"])
                and len(edited["entities"]) >= 1 + 4 + 6)
            n_geo = len(edited["entities"])
            state = self.sketch_add_line(adv, 200, 200, 210, 200)
            added = state["entities"][-1]["id"]
            state = self.sketch_delete_geo(adv, added)
            report["p3_delete_geo_ok"] = len(state["entities"]) == n_geo

            mark("p3: congé d'esquisse")
            state = self.sketch_start()
            fil = state["sketch"]
            self.sketch_add_line(fil, 0, 0, 40, 0)
            self.sketch_add_line(fil, 40, 0, 40, 30)
            state = self.sketch_fillet(fil, 0, 1, 30, 0, 40, 20, 5)
            report["p3_sketch_fillet_ok"] = any(
                e["type"] == "arc" for e in state["entities"])
            self.sketch_finish(fil)

            mark("p3: ajuster (trim)")
            state = self.sketch_start()
            trm = state["sketch"]
            self.sketch_add_line(trm, 0, 0, 40, 0)      # géo 0
            self.sketch_add_line(trm, 20, -10, 20, 10)  # géo 1, croise en (20,0)
            state = self.sketch_trim(trm, 1, 20, 8)     # coupe la branche haute
            top_ys = [max(e["p1"][1], e["p2"][1])
                      for e in state["entities"] if e["type"] == "line"]
            report["p3_trim_ok"] = all(y < 5 for y in top_ys)
            self.sketch_finish(trm)

            mark("p3: contraintes manuelles + cote à 2 entités")
            state = self.sketch_start()
            con = state["sketch"]
            self.sketch_add_line(con, 0, 0, 30, 2)
            self.sketch_add_line(con, 0, 10, 30, 14)
            self.sketch_constrain(con, "horizontal", 0)
            state = self.sketch_constrain(con, "parallel", 0, geo2=1)
            line0 = next(e for e in state["entities"] if e["id"] == 0)
            report["p3_constrain_ok"] = (
                abs(line0["p1"][1] - line0["p2"][1]) < 1e-6)
            state = self.sketch_dim(con, 0, geo2=1)  # parallèles → distance
            report["p3_dim_distance_ok"] = any(
                d["type"] == "Distance" for d in state["dims"])
            self.sketch_add_line(con, 50, 0, 80, 0)   # géo 2
            self.sketch_add_line(con, 50, 0, 80, 20)  # géo 3, snap en (50,0)
            state = self.sketch_dim(con, 2, geo2=3)   # sécantes → angle
            report["p3_dim_angle_ok"] = any(
                d["type"] == "Angle" for d in state["dims"])
            # M3 : l'état expose les contraintes brutes (geos/pos/value/
            # driving) — c'est ce que le solveur local planegcs consomme.
            report["p3_constraints_export_ok"] = (
                any(c["type"] == "Parallel" and c["geos"][:2] == [0, 1]
                    for c in state["constraints"])
                and all(set(c) >= {"id", "type", "geos", "pos", "value",
                                   "driving"}
                        for c in state["constraints"]))
            self.sketch_finish(con)

            mark("cycle de vie: open_part sans Body + UndoLimit")
            App = self._app()
            empty = App.newDocument("EmptyLifecycle")
            empty_path = os.path.join(
                tempfile.gettempdir(),
                "freesolid-lifecycle-empty.FCStd")
            empty.saveAs(empty_path)
            App.closeDocument(empty.Name)
            docs_before = len(App.listDocuments())
            orphan_raised = False
            try:
                self.open_part(empty_path)
            except KernelError:
                orphan_raised = True
            report["lifecycle_orphan_ok"] = (
                orphan_raised
                and len(App.listDocuments()) <= docs_before
                and self._doc is None)
            self.new_part("Pièce lifecycle")
            limit = self._undo_limit(self._doc)
            if limit is not None:
                report["lifecycle_undo_limit_ok"] = limit == 80
            else:
                # FreeCAD 1.0.x : pas d'API ; la pile C++ plafonne déjà
                # (défaut 20). On prouve la borne comportementale ≤ 80.
                body = self._body
                for i in range(100):
                    self._doc.openTransaction("lim{}".format(i))
                    body.Label = "Lim{}".format(i)
                    self._doc.commitTransaction()
                report["lifecycle_undo_limit_ok"] = (
                    self._doc.UndoMode == 1
                    and 0 < self._doc.UndoCount <= 80)

            def _refused(action, needle):
                try:
                    action()
                    return False
                except KernelError as exc:
                    return needle in str(exc)

            def _close(actual, expected, tol=1e-6):
                scale = abs(float(expected)) or 1.0
                return abs(float(actual) - float(expected)) <= tol * scale

            def _volume():
                return float(self._require_body().Shape.Volume)

            def _dispatch(op, **params):
                out = dispatch(self, op, params)
                if not out["ok"]:
                    raise KernelError(out["error"])
                return out["result"]

            mark("p31: gardes — les refus parlent français")
            self.new_part("Pièce gardes P031")
            body_name = self._require_body().Name
            report["p31_refus_sans_esquisse"] = _refused(
                lambda: self.add_pad(10), "aucune esquisse disponible")
            report["p31_refus_dernier_corps"] = _refused(
                lambda: self.delete_feature(body_name),
                "impossible de supprimer le dernier")
            report["p31_refus_tip_hors_historique"] = _refused(
                lambda: self.set_tip(body_name), "ligne d'historique")
            report["p31_refus_delete_inconnue"] = _refused(
                lambda: self.delete_feature("PasUneFonction"),
                "fonction inconnue")
            report["p31_refus_param_inconnue"] = _refused(
                lambda: self.set_param("PasUneFonction", "Length", 1),
                "fonction inconnue")
            report["p31_refus_rename_inconnue"] = _refused(
                lambda: self.rename("PasUneFonction", "x"),
                "fonction inconnue")
            report["p31_refus_esquisse_inconnue"] = _refused(
                lambda: self.sketch_state("PasUneEsquisse"),
                "esquisse inconnue")
            missing = os.path.join(tempfile.gettempdir(),
                                   "freesolid-absent-p31.FCStd")
            if os.path.isfile(missing):
                os.remove(missing)
            report["p31_refus_open_inexistant"] = _refused(
                lambda: self.open_part(missing), "fichier introuvable")
            report["p31_refus_combiner"] = _refused(
                lambda: self.add_boolean(tool="PasUnCorps"),
                "corps outil inconnu")
            report["p31_refus_nom_vide"] = _refused(
                lambda: self.rename(body_name, "   "),
                "le nom ne peut pas être vide")
            report["p31_refus_cote_nulle"] = _refused(
                lambda: self.add_rect_sketch(0, 10),
                "largeur et hauteur doivent être positives")
            report["p31_refus_plan_esquisse"] = _refused(
                lambda: self.sketch_start(plane="AB"),
                "plan inconnu")

            mark("p31: vérités géométriques")
            self.new_part("Pièce volumes P031")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            report["p31_volume_pad"] = _close(_volume(), 12000.0)
            report["p31_faces_pad"] = len(self.tessellate()["groups"]) == 6
            self.add_rect_sketch(10, 10, face=self._top_face_id())
            self.add_pocket(through=True)
            report["p31_volume_pocket"] = _close(_volume(), 11000.0)

            self.new_part("Pièce miroir P031")
            state = self.sketch_start()
            mir_sk = state["sketch"]
            # 20×20 à cheval sur YZ (x=-5..15) : un Body n'a qu'un solide,
            # les copies disjointes sont jetées — le chevauchement fusionne.
            for line in ((-5, -10, 15, -10), (15, -10, 15, 10),
                         (15, 10, -5, 10), (-5, 10, -5, -10)):
                self.sketch_add_line(mir_sk, *line)
            self.sketch_finish(mir_sk)
            self.add_pad(10, sketch=mir_sk)
            vol_before_mirror = _volume()
            self.add_mirror(plane="YZ")
            report["p31_volume_miroir"] = _close(
                _volume(), vol_before_mirror * 1.5)

            self.new_part("Pièce répétition P031")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            vol_before_pattern = _volume()
            self.add_linear_pattern(length=10, count=2, axis="X")
            report["p31_volume_repetition"] = _close(
                _volume(), vol_before_pattern * 1.5)

            self.new_part("Pièce combiner P031")
            self.add_rect_sketch(40, 40)
            self.add_pad(10)
            first_body = self._require_body().Name
            vol_host = _volume()
            self.add_body("Corps outil")
            self.add_rect_sketch(20, 20)
            self.add_pad(10)
            tool_body = self._require_body().Name
            vol_tool = _volume()
            self.set_active_body(first_body)
            self.add_boolean(tool=tool_body, type="cut")
            report["p31_volume_combiner"] = _close(
                _volume(), vol_host - vol_tool)

            mark("p31: aller-retour complet")
            self.new_part("Pièce roundtrip P031")
            self.set_variable("hauteur", 10.0)
            self.add_rect_sketch(40, 30)
            tree = self.add_pad(10)
            pad_name = next(f["name"] for f in tree["features"]
                            if f["type"] == "PartDesign::Pad")
            self.set_params(pad_name, {"Length": "Variables.hauteur"})
            tree = self.rename(pad_name, "Bossage principal")
            body_name = self._require_body().Name
            tree = self.set_body_color(body_name, "#336699")
            state = self.sketch_start()
            free_sk = state["sketch"]
            self.sketch_add_line(free_sk, 0, 0, 25, 0)
            self.sketch_finish(free_sk)
            state = self.sketch_start()
            surf_sk = state["sketch"]
            self.sketch_add_line(surf_sk, 0, 0, 18, 0)
            self.sketch_finish(surf_sk)
            tree = self.surface_extrude(12, sketch=surf_sk)
            surf_name = tree["surfaces"][-1]["name"]
            tree = self.set_tip(pad_name)
            vol_before_save = _volume()
            round_path = os.path.join(tempfile.gettempdir(),
                                      "freesolid-selftest-p31.FCStd")
            self.save_part(round_path)
            reopened = self.open_part(round_path)
            report["p31_reopen_variables"] = any(
                v["name"] == "hauteur" and abs(v["value"] - 10.0) < 1e-9
                for v in reopened.get("variables", []))
            report["p31_reopen_label"] = any(
                f["name"] == pad_name and f["label"] == "Bossage principal"
                for f in reopened["features"])
            report["p31_reopen_couleur"] = any(
                b["name"] == body_name and b.get("color") == "#336699"
                for b in reopened["bodies"])
            free_entry = next(f for f in reopened["features"]
                              if f["name"] == free_sk)
            surf_entry = next(s for s in reopened["surfaces"]
                              if s["name"] == surf_name)
            report["p31_reopen_rolled_back"] = (
                free_entry.get("rolled_back") is True
                and surf_entry.get("rolled_back") is True)
            report["p31_reopen_tip"] = reopened.get("tip") == pad_name
            report["p31_reopen_volume"] = _close(_volume(), vol_before_save)

            mark("p31: aller-retour STEP")
            self.new_part("Pièce STEP P031")
            self.add_rect_sketch(40, 30)
            self.add_pad(10)
            vol_step = _volume()
            step_path = os.path.join(tempfile.gettempdir(),
                                     "freesolid-selftest-p31.step")
            self.export_part(step_path)
            self.open_part(step_path)
            report["p31_step_roundtrip"] = _close(
                _volume(), vol_step, tol=0.001)

            mark("p31: annuler en chaîne")
            self.new_part("Pièce undo P031")
            _dispatch("add_rect_sketch", width=30, height=20)
            _dispatch("add_pad", length=10)
            tree = _dispatch("add_fillet", radius=2, face=self._top_face_id())
            vol_chain = _volume()
            sig_chain = [(f["type"], f["name"], f["label"])
                         for f in tree["features"]]
            self.undo()
            self.undo()
            self.undo()
            self.redo()
            self.redo()
            tree = self.redo()
            report["p31_undo_chain"] = (
                _close(_volume(), vol_chain)
                and [(f["type"], f["name"], f["label"])
                     for f in tree["features"]] == sig_chain)

            mark("p31: pièce vitrine")
            # Chaque fonction est testée sur une pièce jetable : sans cette
            # étape, l'Autotest finissait sur la pièce la plus banale
            # (plaque m1.5). Une seule pièce enchaîne ici des fonctions
            # visibles ; le bilan la rouvre pour le viewport. Le chanfrein
            # est écarté exprès : sur coque/dépouille, ChFi3d a déjà
            # segfaulté (voir p4).
            self.new_part("Pièce vitrine")
            self.add_rect_sketch(80, 80)
            self.add_pad(14)
            self.add_draft(face=self._side_face_id(), angle=5)
            self.add_fillet(3, face=self._top_face_id())
            self.add_rect_sketch(40, 40, face=self._top_face_id())
            self.add_pocket(6)
            state = self.sketch_start(face=self._top_face_id())
            vitrine_sk = state["sketch"]
            self.sketch_add_circle(vitrine_sk, 28, 28, 3)
            self.sketch_finish(vitrine_sk)
            self.add_hole(diameter=6, through=True, cut="lamage",
                          cut_diameter=11, cut_depth=3)
            self.add_polar_pattern(count=4, angle=360.0, axis="Z")
            tree = self.add_text("FS", face=self._top_face_id(),
                                 size=8, depth=1, x=0, y=-30)
            vitrine_path = os.path.join(tempfile.gettempdir(),
                                        "freesolid-selftest-vitrine.FCStd")
            self.save_part(vitrine_path)
            report["p31_vitrine_ok"] = (
                not any(f["error"] for f in tree["features"])
                and tree["bodies"][0].get("has_solid") is True
                and _volume() > 0
                and len(self.tessellate()["groups"]) >= 20)

            mark("p32: refus atomique, virgule, gravure rééditable")
            vitrine_pp = next(f["name"] for f in tree["features"]
                              if f["type"] == "PartDesign::PolarPattern")
            vitrine_pad = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pad")
            # Une expression inconnue est refusée SANS corrompre la pièce
            # (avant P032 : liaison stockée, pièce Invalid, barre bloquée).
            try:
                self.set_params(vitrine_pp, {"Occurrences": "inconnu_p32"})
                report["p32_expr_refus_atomique"] = False
            except KernelError:
                obj = self._require_doc().getObject(vitrine_pp)
                intact = not dict(obj.ExpressionEngine or [])
                self.set_tip(vitrine_pad)     # la barre bouge encore
                tree = self.tip_to_end()
                report["p32_expr_refus_atomique"] = (
                    intact and not any(f["error"]
                                       for f in tree["features"]))
            # « 15,5 » est un nombre (virgule française), pas une équation.
            self.set_params(vitrine_pad, {"Length": "15,5"})
            obj = self._require_doc().getObject(vitrine_pad)
            report["p32_virgule_nombre"] = (
                not dict(obj.ExpressionEngine or [])
                and abs(float(obj.Length) - 15.5) < 1e-9)
            self.set_params(vitrine_pad, {"Length": 14})
            # La gravure se réédite : autre texte -> autre géométrie.
            gravure = next(f["name"] for f in self.get_tree()["features"]
                           if f["type"] == "PartDesign::Boolean")
            tris_before = len(self.tessellate()["indices"])
            vol_before_edit = _volume()
            tree = self.edit_text(gravure, text="OK")
            vitrine_shape = self._require_body().Shape
            report["p32_gravure_editable"] = (
                not any(f["error"] for f in tree["features"])
                and len(self.tessellate()["indices"]) != tris_before
                and any(f.get("text", {}).get("text") == "OK"
                        for f in tree["features"])
                # volume sain : la pièce entière, pas le texte seul
                and vitrine_shape.isValid()
                and abs(_volume() - vol_before_edit) < 100.0)
            tree = self.edit_text(gravure, text="FS")
            # Les artefacts internes de la gravure restent hors de l'arbre.
            report["p32_forme_texte_cachee"] = (
                not any(s["label"] == "Forme du texte"
                        for s in tree["surfaces"])
                and not any(b["label"] == "Corps texte"
                            for b in tree["bodies"]))
            # L'état vitrine (14, « FS ») est restauré : re-sauver pour
            # que le bilan rouvre exactement la pièce attendue.
            self.save_part(vitrine_path)

            mark("n1: arêtes de dépendance dans get_tree")
            self.new_part("Pièce nœuds N001")
            tree = self.add_rect_sketch(80, 50)
            sketch_name = next(
                f["name"] for f in tree["features"]
                if f["type"] == "Sketcher::SketchObject")
            tree = self.add_pad(12)
            pad = next(f for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            report["n1_deps_pad_sketch"] = (
                sketch_name in pad.get("deps", []))
            self.set_params(pad["name"], {"Length": "12 + 3"})
            pad = next(f for f in self.get_tree()["features"]
                       if f["type"] == "PartDesign::Pad")
            report["n1_driven_ok"] = "Length" in pad.get("driven", {})

            mark("bilan")
            # Rouvrir la pièce vitrine : le viewport finit sur une pièce
            # qui montre ce que l'Autotest a testé, pas sur la plaque m1.5.
            self.open_part(vitrine_path)
            report["tree_after_pad"] = self.get_tree()
            mesh = self.tessellate()
            report["mesh_faces"] = len(mesh["groups"])
            report["mesh_triangles"] = len(mesh["indices"]) // 3
            report["bilan"] = selftest_summary(report)
            return report
        except KernelError as exc:
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], exc))
        except Exception as exc:  # noqa: BLE001 - name the step, always
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], _explain(exc)))


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
    "edit_text", "make_drawing",
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
})


def _abort(doc):
    if doc is None:
        return
    try:
        doc.abortTransaction()
    except Exception:
        pass


def dispatch(kernel: Kernel, op: str, params: dict):
    """Route one validated request to the kernel, normalizing errors.

    Mutating ops run inside a document transaction: one UI action = one
    Ctrl+Z, and a failed op leaves the document as it was.
    """
    from . import protocol
    doc = kernel._doc if op in _TRANSACTIONAL else None
    if doc is not None:
        doc.openTransaction("freesolid-" + op)
    try:
        result = getattr(kernel, op)(**params)
    except KernelError as exc:
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
