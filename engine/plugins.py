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
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_ROOT = os.path.join(_REPO_ROOT, "plugins")

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
    """Cinq points de contribution. Ordre d'enregistrement = ordre d'exécution."""

    def __init__(self, nom=""):
        self.nom = nom
        self.errors = []
        self.notes = []
        self.transactional = set()
        self.manifests = []
        self._after = []
        self._tree = []
        self._mesh = []
        self._ops = {}
        self._selftest = []

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

    def extend(self, other):
        """Ajoute les crochets d'un registre, dans l'ordre."""
        self._after.extend(other._after)
        self._tree.extend(other._tree)
        self._mesh.extend(other._mesh)
        self._ops.update(other._ops)
        self._selftest.extend(other._selftest)
        self.manifests.extend(other.manifests)
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
        registry.manifests.append(manifest)
    return registry


def default_registry():
    """Registre chargé une fois, au premier noyau."""
    global _LOADED
    if _LOADED is None:
        _LOADED = load_plugins()
    return _LOADED


#: Fichier JS annoncé par ``list_plugins`` et servi sous ``statique/``.
_CLIENT_ENTRY = "plugin.js"


def client_entry_path(manifest) -> str:
    """Chemin URL du JS client, ou « » si le plugin n'en a pas."""
    if not isinstance(manifest, dict):
        return ""
    nom = manifest.get("nom") or ""
    statique = manifest.get("statique") or ""
    directory = manifest.get("directory") or ""
    if not nom or not statique or not directory:
        return ""
    path = os.path.join(directory, statique, _CLIENT_ENTRY)
    if not os.path.isfile(path):
        return ""
    return "/plugins/{}/{}".format(nom, _CLIENT_ENTRY)


def client_plugins(registry=None):
    """``{plugins: [{nom, entree}, …]}`` — plugins chargés qui ont un JS.

    L'ordre suit le registre (noms triés à la découverte). Un plugin
    sans ``statique`` ou sans ``plugin.js`` est omis, pas une erreur.
    """
    if registry is None:
        registry = default_registry()
    plugins = []
    for manifest in getattr(registry, "manifests", ()):
        entree = client_entry_path(manifest)
        if not entree:
            continue
        plugins.append({"nom": manifest["nom"], "entree": entree})
    return {"plugins": plugins}
