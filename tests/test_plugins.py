"""Registre de plugins — pur Python, sans FreeCAD."""

import ast
import json
from pathlib import Path

import pytest

from engine.plugins import PluginError, Registry, discover, parse_manifest
from engine.protocol import CORE_OP_NAMES, OPS


def _manifest(nom="alpha", module=None, **extra):
    data = {
        "nom": nom,
        "version": "1.0.0",
        "libelle": nom.capitalize(),
        "module": module or "{}.plugin".format(nom),
        "ops": {},
        "statique": "ui",
    }
    data.update(extra)
    return data


def _write_plugin(root, directory, nom=None, raw=None, **extra):
    folder = root / directory
    folder.mkdir()
    payload = raw if raw is not None else _manifest(nom=nom or directory, **extra)
    (folder / "plugin.json").write_text(
        json.dumps(payload), encoding="utf-8")
    return folder


def test_parse_manifest_valid():
    parsed = parse_manifest(_manifest(), "alpha")
    assert parsed["nom"] == "alpha"
    assert parsed["version"] == "1.0.0"
    assert parsed["module"] == "alpha.plugin"
    assert parsed["statique"] == "ui"
    assert parsed["ops"] == {}


def test_parse_manifest_refuses_module_dotdot():
    with pytest.raises(PluginError, match="module"):
        parse_manifest(_manifest(module="foo..bar"), "alpha")
    with pytest.raises(PluginError, match="module"):
        parse_manifest(_manifest(module="../evil"), "alpha")


def test_parse_manifest_refuses_statique_separator():
    with pytest.raises(PluginError, match="statique"):
        parse_manifest(_manifest(statique="ui/../x"), "alpha")
    with pytest.raises(PluginError, match="statique"):
        parse_manifest(_manifest(statique="ui\\x"), "alpha")
    with pytest.raises(PluginError, match="statique"):
        parse_manifest(_manifest(statique="/tmp"), "alpha")


def test_parse_manifest_refuses_missing_version():
    raw = _manifest()
    del raw["version"]
    with pytest.raises(PluginError, match="version"):
        parse_manifest(raw, "alpha")
    with pytest.raises(PluginError, match="version"):
        parse_manifest(_manifest(version=""), "alpha")


def test_parse_manifest_refuses_kernel_op_collision():
    raw = _manifest(ops={"ping": {}})
    with pytest.raises(PluginError, match="existe déjà"):
        parse_manifest(raw, "alpha", reserved=CORE_OP_NAMES)
    raw = _manifest(ops={"add_pad": {
        "requis": {"length": "float"},
        "transactionnel": True,
    }})
    with pytest.raises(PluginError, match="existe déjà"):
        parse_manifest(raw, "alpha", reserved=CORE_OP_NAMES)


def test_discover_two_plugins_sorted_by_nom(tmp_path):
    _write_plugin(tmp_path, "zeta-dir", nom="zeta")
    _write_plugin(tmp_path, "aaa-dir", nom="alpha")
    found = discover(root=str(tmp_path))
    assert [item["nom"] for item in found] == ["alpha", "zeta"]


def test_discover_invalid_does_not_block_the_other(tmp_path):
    _write_plugin(tmp_path, "ok", nom="ok")
    _write_plugin(
        tmp_path, "bad",
        raw={"nom": "bad", "version": "1.0.0", "libelle": "Bad",
             "module": "foo..bar"})
    found = discover(root=str(tmp_path))
    assert [item["nom"] for item in found] == ["ok"]
    assert discover.notes


def test_registry_hook_error_is_noted_and_others_run():
    seen = []
    registre = Registry(nom="alpha")

    def boom(_kernel):
        raise RuntimeError("le semis a échoué")

    def ok(_kernel):
        seen.append("ok")

    registre.after_recompute(boom)
    registre.after_recompute(ok)
    registre.run_after_recompute(object())
    assert seen == ["ok"]
    assert registre.errors
    assert "le semis a échoué" in registre.errors[0]


def test_registry_tree_key_collision_raises():
    registre = Registry(nom="alpha")
    registre.tree_contribution(lambda _k: {"gems": [1]})
    registre.tree_contribution(lambda _k: {"gems": [2]})
    with pytest.raises(PluginError, match="gems"):
        registre.contribute_tree(object(), {})


def test_bijouterie_ops_remain_in_protocol_snapshot():
    """Tant que le plugin est dans le dépôt, les six ops restent dans OPS."""
    for name in ("place_gem", "move_gem", "spin_gem", "remove_gem",
                 "list_gems", "resize_gem"):
        assert name in OPS
        assert name not in CORE_OP_NAMES


def test_ops_gem_ne_sont_plus_des_methodes_du_noyau():
    """getattr échoue : dispatch emprunte le registre, plus Kernel."""
    from engine.kernel import Kernel
    kernel = Kernel()
    for name in ("place_gem", "move_gem", "spin_gem", "remove_gem",
                 "list_gems", "resize_gem"):
        assert not callable(getattr(Kernel, name, None)), name
        assert kernel._plugins.has_op(name)


# -- surface plugin (P047 / P048) -----------------------------------------

# Douze membres : neuf du noyau, deux aides de selftest, et ``state``
# sur le registre. Épinglés ici parce que la bijouterie partira dans un
# dépôt privé — la CI publique ne pourra plus voir un rename.
_SURFACE_PLUGIN = (
    "_app", "_body", "_doc", "_face_mesh", "_recompute",
    "_report_progress", "_require_body", "_require_doc", "get_tree",
    "_top_face_id", "_side_face_id",
    "state",
)


def test_surface_plugin_reste_disponible():
    """Ces membres sont appelés par des plugins hors dépôt."""
    from engine.kernel import Kernel
    kernel = Kernel()
    manquants = []
    for name in _SURFACE_PLUGIN:
        holder = kernel._plugins if name == "state" else kernel
        if not hasattr(holder, name):
            manquants.append(name)
    assert manquants == []


def test_le_noyau_n_importe_rien_du_plugin():
    """Le jour du git mv, aucun import ne doit se briser."""
    root = Path(__file__).resolve().parents[1] / "engine"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    if module == "gems" or module.startswith("gems."):
                        names.append("engine.gems")
                    if not module:
                        for alias in node.names:
                            if alias.name == "gems":
                                names.append("engine.gems")
                else:
                    names.append(module)
                    if module == "engine":
                        for alias in node.names:
                            names.append("engine." + alias.name)
            for name in names:
                if (name == "engine.gems" or name.startswith("engine.gems.")
                        or name == "bijouterie"
                        or name.startswith("bijouterie.")
                        or name == "plugins"
                        or name.startswith("plugins.")):
                    rel = path.relative_to(root.parent)
                    offenders.append("{}: {}".format(rel, name))
    assert offenders == []


def test_etat_par_plugin_distinct_et_raz_au_document():
    """Deux plugins ont des sacs distincts ; un nouveau document les vide."""
    from engine.kernel import Kernel
    kernel = Kernel()
    alpha = kernel._plugins.state("alpha")
    beta = kernel._plugins.state("beta")
    assert alpha is not beta
    alpha["k"] = 1
    beta["k"] = 2
    assert kernel._plugins.state("alpha") is alpha
    kernel._close_current()
    assert kernel._plugins.state("alpha") == {}
    assert kernel._plugins.state("beta") == {}
    kernel._plugins.state("alpha")["k"] = 1
    other = Kernel()
    assert other._plugins.state("alpha") == {}


def test_ops_bijouterie_transactionnelles_via_le_manifeste():
    """Les six ops restent transactionnelles par le manifeste, pas la liste."""
    from engine.kernel import Kernel, _TRANSACTIONAL, _transactional
    kernel = Kernel()
    for name in ("place_gem", "move_gem", "spin_gem", "remove_gem",
                 "resize_gem"):
        assert name not in _TRANSACTIONAL
        assert _transactional(kernel, name)
    assert "list_gems" not in _TRANSACTIONAL
    assert not _transactional(kernel, "list_gems")


# -- plugin bouchon : call_op, transaction, crochets qui ne réclament pas --

class _FakeDoc:
    def __init__(self):
        self.opened = False
        self.aborted = False
        self.committed = False

    def openTransaction(self, _name):
        self.opened = True

    def abortTransaction(self):
        self.aborted = True

    def commitTransaction(self):
        self.committed = True


class _FakeKernel:
    def __init__(self, plugins, doc=None):
        self._plugins = plugins
        self._doc = doc


def _bouchon():
    from tests.plugin_bouchon import register
    registre = Registry(nom="bouchon")
    register(registre)
    return registre


def test_dispatch_emprunte_call_op():
    from engine.kernel import dispatch
    kernel = _FakeKernel(_bouchon())
    result = dispatch(kernel, "echo_bouchon", {"message": "ping"})
    assert result == {"ok": True, "result": {"echo": "ping"}}


def test_dispatch_op_transactionnelle():
    from engine.kernel import dispatch
    doc = _FakeDoc()
    kernel = _FakeKernel(_bouchon(), doc=doc)
    result = dispatch(kernel, "muter_bouchon", {})
    assert result == {"ok": True, "result": {"muté": True}}
    assert doc.opened
    assert doc.committed
    assert not doc.aborted


def test_dispatch_op_qui_leve_annule_la_transaction():
    from engine.kernel import dispatch
    doc = _FakeDoc()
    kernel = _FakeKernel(_bouchon(), doc=doc)
    result = dispatch(kernel, "boom_bouchon", {})
    assert result["ok"] is False
    assert result["error"] == "le bouchon a levé"
    assert doc.opened
    assert doc.aborted
    assert not doc.committed


def test_hooks_personne_ne_reclame():
    """False / None / False : le noyau se comporte comme sans plugin."""
    vide = Registry()
    bouchon = _bouchon()
    kernel, obj = object(), object()
    assert vide.run_tolerates_invalid(kernel, obj) is False
    assert bouchon.run_tolerates_invalid(kernel, obj) is False
    assert vide.run_boolean_tool(kernel, obj) is None
    assert bouchon.run_boolean_tool(kernel, obj) is None
    assert vide.run_deletes_feature(kernel, obj) is False
    assert bouchon.run_deletes_feature(kernel, obj) is False


def test_bijouterie_reclame_un_semis_pas_un_pad():
    from engine.kernel import Kernel

    class _Gem:
        TypeId = "App::Link"
        PropertiesList = ("FreeSolidGemFace",)

    class _Pad:
        TypeId = "PartDesign::Pad"
        PropertiesList = ()

    kernel = Kernel()
    assert kernel._plugins.run_tolerates_invalid(kernel, _Gem()) is True
    assert kernel._plugins.run_tolerates_invalid(kernel, _Pad()) is False
    assert kernel._plugins.run_boolean_tool(kernel, _Pad()) is None
    assert kernel._plugins.run_deletes_feature(kernel, _Pad()) is False
