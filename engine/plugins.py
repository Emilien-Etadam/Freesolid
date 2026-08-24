"""Registre de plugins — découverte de manifestes, puis crochets.

Aucun import FreeCAD, aucun ``exec`` : ce module **lit et valide des
manifestes**, il ne charge rien. Le chargement des modules (``import``)
est ``load_plugins``, appelé au démarrage du noyau.

Un plugin est du Python arbitraire dans le processus du noyau, avec les
mêmes droits. Pas de bac à sable, et pas de dialogue de consentement non
plus — contrairement au nœud Python de ``scriptnode.py``.

La différence est réelle : un script arrive dans un ``.FCStd`` qu'on a pu
recevoir de n'importe qui ; un plugin est un répertoire que l'utilisateur
a délibérément posé dans ``plugins/``. Le geste d'installation *est* le
consentement, comme pour n'importe quel paquet.

Un manifeste est une **entrée**, pas une confidence : ``module`` et
``statique`` sont jailés, même discipline que ``sanitize_gemme``.

Surface kernel qu'un plugin a le droit d'appeler
------------------------------------------------
Mesurée sur le bloc bijouterie, pas supposée. Un plugin hors dépôt
n'appelle que ces neuf membres privés :

    _app  _body  _doc  _face_mesh  _recompute
    _report_progress  _require_body  _require_doc  get_tree

et, pour les étapes de selftest, deux aides de test :

    _top_face_id  _side_face_id

Ces membres restent privés : pas de renommage public, pas de façade
``KernelServices``. Les nommer et les épingler (voir
``test_surface_plugin_reste_disponible``) suffit. Retirer
``_require_body`` casserait un plugin que la CI publique ne peut
pas exécuter.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_ROOT = os.path.join(_REPO_ROOT, "plugins")

# ``plugins/`` est un chemin d'import dès que ce module vit — pas
# seulement au premier Kernel. Les tests voient alors ``bijouterie``.
if os.path.isdir(_DEFAULT_ROOT) and _DEFAULT_ROOT not in sys.path:
    sys.path.insert(0, _DEFAULT_ROOT)

_MODULE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
_DIR_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_NOM_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_KINDS = frozenset({"int", "float", "str", "list", "dict", "bool"})

_LOADED = None


class PluginError(ValueError):
    """Manifeste ou contribution invalide — message designer."""


def plugins_root(root=None) -> str:
    if root is None:
        return _DEFAULT_ROOT
    return os.path.abspath(root)


def _jail_module(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text or not _MODULE_RE.fullmatch(text):
        raise PluginError(
            "module de plugin invalide « {} » — identifiant pointé "
            "attendu, sans chemin".format(text or ""))
    if ".." in text:
        raise PluginError(
            "module de plugin invalide « {} » — identifiant pointé "
            "attendu, sans chemin".format(text))
    return text


def _jail_statique(value) -> str:
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if (not text or not _DIR_NAME_RE.fullmatch(text)
            or "/" in text or "\\" in text or ".." in text
            or os.path.isabs(text)):
        raise PluginError(
            "répertoire statique invalide « {} » — un nom simple, "
            "sans séparateur".format(text))
    return text


def _require_str(raw, key, what):
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PluginError("{} manquant — le plugin n'a pas été chargé".format(
            what))
    return value.strip()


def _parse_ops(raw_ops, reserved):
    if raw_ops is None:
        return {}
    if not isinstance(raw_ops, dict):
        raise PluginError(
            "ops de plugin invalides — un objet {nom: spécification} "
            "est attendu")
    parsed = {}
    reserved = frozenset(reserved or ())
    for name, spec in raw_ops.items():
        if not isinstance(name, str) or not _OP_NAME_RE.fullmatch(name):
            raise PluginError(
                "nom d'opération invalide « {} »".format(name))
        if name in reserved:
            raise PluginError(
                "l'opération « {} » existe déjà — le plugin n'a pas "
                "été chargé".format(name))
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            raise PluginError(
                "spécification de « {} » invalide — un objet est "
                "attendu".format(name))
        parsed[name] = _parse_op_spec(name, spec)
    return parsed


def _parse_op_spec(name, spec):
    requis = spec.get("requis") or {}
    optionnels = spec.get("optionnels") or {}
    if not isinstance(requis, dict) or not isinstance(optionnels, dict):
        raise PluginError(
            "paramètres de « {} » invalides — requis et optionnels "
            "sont des objets".format(name))
    for group, label in ((requis, "requis"), (optionnels, "optionnels")):
        for param, kind in group.items():
            if not isinstance(param, str) or not param:
                raise PluginError(
                    "paramètre {} de « {} » invalide".format(label, name))
            if kind not in _KINDS:
                raise PluginError(
                    "type « {} » inconnu pour {} de « {} » — "
                    "attendu int, float, str, list, dict ou bool".format(
                        kind, param, name))
    transactionnel = spec.get("transactionnel", False)
    if transactionnel not in (True, False):
        raise PluginError(
            "transactionnel de « {} » doit être un booléen".format(name))
    return {
        "requis": dict(requis),
        "optionnels": dict(optionnels),
        "transactionnel": bool(transactionnel),
    }


def parse_manifest(raw, directory, reserved=None):
    """Valide un manifeste. Lève ``PluginError`` avec un message designer."""
    if not isinstance(raw, dict):
        raise PluginError("manifeste invalide — un objet JSON est attendu")
    nom = _require_str(raw, "nom", "nom")
    if not _NOM_RE.fullmatch(nom):
        raise PluginError(
            "nom de plugin invalide « {} » — un identifiant minuscule "
            "est attendu".format(nom))
    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PluginError(
            "version manquante — le plugin « {} » n'a pas été chargé".format(
                nom))
    libelle = _require_str(raw, "libelle", "libellé")
    module = _jail_module(raw.get("module"))
    statique = _jail_statique(raw.get("statique"))
    ops = _parse_ops(raw.get("ops"), reserved)
    return {
        "nom": nom,
        "version": version.strip(),
        "libelle": libelle,
        "module": module,
        "ops": ops,
        "statique": statique,
        "directory": os.path.abspath(directory),
    }


def discover(root=None, reserved=None):
    """Manifestes valides trouvés sous ``plugins/*/plugin.json``.

    Un manifeste invalide n'empêche pas les autres de charger : on le
    note et on continue. L'ordre est déterministe : tri par ``nom``.
    """
    base = plugins_root(root)
    found = []
    notes = []
    if not os.path.isdir(base):
        discover.notes = notes
        return found
    names = sorted(
        name for name in os.listdir(base)
        if os.path.isdir(os.path.join(base, name)))
    for name in names:
        directory = os.path.join(base, name)
        path = os.path.join(directory, "plugin.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            found.append(parse_manifest(raw, directory, reserved=reserved))
        except PluginError as exc:
            notes.append(str(exc))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            notes.append(
                "manifeste illisible dans « {} » : {}".format(name, exc))
    found.sort(key=lambda item: item["nom"])
    discover.notes = notes
    return found


discover.notes = []


class Registry:
    """Points de contribution. Ordre d'enregistrement = ordre d'exécution."""

    def __init__(self, nom=""):
        self.nom = nom
        self.errors = []
        self.notes = []
        self.transactional = set()
        self._after = []
        self._tree = []
        self._mesh = []
        self._ops = {}
        self._selftest = []
        self._tolerates_invalid = []
        self._boolean_tool = []
        self._deletes_feature = []
        self._state = {}

    def after_recompute(self, fn):
        """fn(kernel) — après doc.recompute(), avant le contrôle de validité."""
        self._after.append((self.nom, fn))

    def tree_contribution(self, fn):
        """fn(kernel) -> dict, fusionné dans get_tree."""
        self._tree.append((self.nom, fn))

    def mesh_contribution(self, fn):
        """fn(kernel, deviation) -> dict, fusionné dans tessellate."""
        self._mesh.append((self.nom, fn))

    def op(self, nom, fn):
        """fn(kernel, **params). Le noyau reste prioritaire au dispatch."""
        self._ops[nom] = (self.nom, fn)

    def selftest_step(self, libelle, fn):
        """fn(kernel, mark, report) — après les étapes du noyau."""
        self._selftest.append((self.nom, libelle, fn))

    def tolerates_invalid(self, fn):
        """fn(kernel, obj) -> bool. True = cet objet a le droit d'être Invalid."""
        self._tolerates_invalid.append((self.nom, fn))

    def boolean_tool(self, fn):
        """fn(kernel, obj) -> objet outil | None. None = personne ne réclame."""
        self._boolean_tool.append((self.nom, fn))

    def deletes_feature(self, fn):
        """fn(kernel, obj) -> True si le plugin a pris en charge la suppression."""
        self._deletes_feature.append((self.nom, fn))

    def state(self, nom):
        """Dict d'état pour ce plugin, dans le document courant.

        Remis à zéro par le noyau à la construction et à la fermeture
        du document. Deux plugins ne partagent pas le même sac.
        """
        bag = self._state.get(nom)
        if bag is None:
            bag = {}
            self._state[nom] = bag
        return bag

    def reset_state(self):
        """Vide tous les sacs. Appelé par le noyau, pas par les plugins."""
        self._state.clear()

    def extend(self, other):
        """Ajoute les crochets d'un registre, dans l'ordre."""
        self._after.extend(other._after)
        self._tree.extend(other._tree)
        self._mesh.extend(other._mesh)
        self._ops.update(other._ops)
        self._selftest.extend(other._selftest)
        self._tolerates_invalid.extend(other._tolerates_invalid)
        self._boolean_tool.extend(other._boolean_tool)
        self._deletes_feature.extend(other._deletes_feature)
        self.transactional.update(other.transactional)
        self.errors.extend(other.errors)
        self.notes.extend(other.notes)

    def run_after_recompute(self, kernel):
        """Un crochet qui lève est noté ; les suivants s'exécutent."""
        for nom, fn in self._after:
            try:
                fn(kernel)
            except Exception as exc:  # noqa: BLE001 — le plugin porte l'erreur
                self.errors.append(
                    "plugin « {} » : {}".format(nom or "?", exc))

    def contribute_tree(self, kernel, tree):
        """Fusionne les contributions. Collision de clé → PluginError."""
        _merge_contributions(self._tree, tree, lambda fn: fn(kernel))

    def contribute_mesh(self, kernel, mesh, deviation):
        """Fusionne les contributions de maillage. Collision → PluginError."""
        _merge_contributions(
            self._mesh, mesh, lambda fn: fn(kernel, deviation))

    def has_op(self, nom):
        return nom in self._ops

    def call_op(self, nom, kernel, **params):
        entry = self._ops.get(nom)
        if entry is None:
            raise PluginError("opération inconnue : {}".format(nom))
        _plugin_nom, fn = entry
        return fn(kernel, **params)

    def run_selftest(self, kernel, mark, report):
        for _nom, _libelle, fn in self._selftest:
            fn(kernel, mark, report)

    def run_tolerates_invalid(self, kernel, obj):
        """True dès qu'un plugin réclame. Personne → False, comportement d'origine."""
        for _nom, fn in self._tolerates_invalid:
            if fn(kernel, obj):
                return True
        return False

    def run_boolean_tool(self, kernel, obj):
        """Premier objet outil non ``None``. Personne → ``None``, chemin par défaut."""
        for _nom, fn in self._boolean_tool:
            result = fn(kernel, obj)
            if result is not None:
                return result
        return None

    def run_deletes_feature(self, kernel, obj):
        """True dès qu'un plugin a pris en charge. Personne → False, chemin par défaut."""
        for _nom, fn in self._deletes_feature:
            if fn(kernel, obj):
                return True
        return False


def _merge_contributions(hooks, target, invoke):
    for nom, fn in hooks:
        extra = invoke(fn)
        if extra is None:
            continue
        if not isinstance(extra, dict):
            raise PluginError(
                "le plugin « {} » a rendu une contribution invalide — "
                "un objet est attendu".format(nom or "?"))
        for key, value in extra.items():
            if key in target:
                raise PluginError(
                    "le plugin « {} » revendique la clé « {} », "
                    "déjà portée".format(nom or "?", key))
            target[key] = value


def load_plugins(root=None, reserved=None):
    """Importe les modules valides et appelle ``register(registre)``.

    Un plugin cassé ne bloque pas les autres. Les plugins chargent par
    nom trié (celui du manifeste).
    """
    registry = Registry()
    manifests = discover(root=root, reserved=reserved)
    registry.notes.extend(discover.notes)
    base = plugins_root(root)
    if base not in sys.path:
        sys.path.insert(0, base)
    for manifest in manifests:
        sub = Registry(nom=manifest["nom"])
        for name, spec in manifest["ops"].items():
            if spec.get("transactionnel"):
                sub.transactional.add(name)
        try:
            module = importlib.import_module(manifest["module"])
            register = getattr(module, "register", None)
            if not callable(register):
                raise PluginError(
                    "le plugin « {} » n'expose pas register(registre)".format(
                        manifest["nom"]))
            register(sub)
        except Exception as exc:  # noqa: BLE001 — un plugin cassé n'empêche pas
            registry.notes.append(
                "plugin « {} » non chargé : {}".format(
                    manifest["nom"], exc))
            continue
        registry.extend(sub)
    return registry


def default_registry():
    """Registre chargé une fois, au premier noyau."""
    global _LOADED
    if _LOADED is None:
        _LOADED = load_plugins()
    return _LOADED
