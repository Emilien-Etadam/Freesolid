"""Registre de plugins — pur Python, sans FreeCAD."""

import json

import pytest

from engine.plugins import (
    PluginError, Registry, client_plugins, discover, load_plugins,
    parse_manifest,
)
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


def _write_python_plugin(root, nom, register_body="pass", with_js=True):
    folder = _write_plugin(
        root, nom, nom=nom, module="{}.plugin".format(nom))
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "plugin.py").write_text(
        "def register(registre):\n    {}\n".format(register_body),
        encoding="utf-8")
    if with_js:
        ui = folder / "ui"
        ui.mkdir()
        (ui / "plugin.js").write_text("export function register() {}\n")
    return folder


def test_load_plugins_records_manifest_and_js_entry(tmp_path):
    _write_python_plugin(tmp_path, "recok")
    registry = load_plugins(root=str(tmp_path))
    assert [item["nom"] for item in registry.manifests] == ["recok"]
    assert client_plugins(registry) == {
        "plugins": [{"nom": "recok", "entree": "/plugins/recok/plugin.js"}],
    }


def test_client_plugins_omits_plugin_without_js(tmp_path):
    _write_python_plugin(tmp_path, "nojs", with_js=False)
    registry = load_plugins(root=str(tmp_path))
    assert [item["nom"] for item in registry.manifests] == ["nojs"]
    assert client_plugins(registry) == {"plugins": []}


def test_failed_plugin_is_not_in_manifests(tmp_path):
    _write_python_plugin(tmp_path, "boompl", register_body="raise RuntimeError('boom')")
    registry = load_plugins(root=str(tmp_path))
    assert registry.manifests == []
    assert any("boompl" in note for note in registry.notes)
