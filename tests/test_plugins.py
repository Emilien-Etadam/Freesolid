"""Registre de plugins — pur Python, sans FreeCAD."""

import ast
import json
from pathlib import Path

import pytest

from engine.plugins import (
    PluginError, Registry, client_plugins, discover, load_plugins,
    missing_selftest_plugins, parse_manifest,
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


def test_run_selftest_compte_les_indicateurs_par_plugin():
    """Le compte distingue « a tout passé » de « n'était pas là ».

    Sans lui, un plugin absent rend un rapport plus court, tous les
    indicateurs du noyau vrais, et un selftest vert qui ne prouve rien.
    """
    registry = Registry()
    alpha = Registry(nom="alpha")
    alpha.selftest_step("deux", lambda k, mark, rep: rep.update(
        a1=True, a2=False, a_detail="pas un indicateur"))
    beta = Registry(nom="beta")
    beta.selftest_step("une", lambda k, mark, rep: rep.update(b1=True))
    registry.extend(alpha)
    registry.extend(beta)

    report = {"noyau": True}
    registry.run_selftest(None, lambda _n: None, report)

    assert registry.selftest_counts == {"alpha": 2, "beta": 1}


def test_run_selftest_sans_plugin_ne_compte_rien():
    registry = Registry()
    report = {"noyau": True}
    registry.run_selftest(None, lambda _n: None, report)
    assert registry.selftest_counts == {}


def test_run_selftest_additionne_deux_etapes_du_meme_plugin():
    registry = Registry()
    sub = Registry(nom="gamma")
    sub.selftest_step("un", lambda k, mark, rep: rep.update(g1=True))
    sub.selftest_step("deux", lambda k, mark, rep: rep.update(g2=True, g3=True))
    registry.extend(sub)
    registry.run_selftest(None, lambda _n: None, {})
    assert registry.selftest_counts == {"gamma": 3}


def _registre_charge(nom, indicateurs):
    registry = Registry()
    registry.manifests.append({"nom": nom})
    if indicateurs:
        registry.selftest_counts[nom] = indicateurs
    return registry


def test_plugin_exige_et_present_ne_manque_pas():
    registry = _registre_charge("bijouterie", 24)
    assert missing_selftest_plugins(registry, ["bijouterie"]) == []


def test_plugin_exige_mais_absent_est_signale():
    """Le cas qui rendait la CI du dépôt privé verte pour rien."""
    manquants = missing_selftest_plugins(Registry(), ["bijouterie"])
    assert manquants == ["bijouterie : non chargé"]


def test_plugin_charge_mais_muet_est_signale():
    """Chargé ne suffit pas : le noyau a pu bouger sous ses étapes."""
    registry = _registre_charge("bijouterie", 0)
    manquants = missing_selftest_plugins(registry, ["bijouterie"])
    assert manquants == [
        "bijouterie : chargé mais n'a contribué aucun indicateur"]


def test_aucune_exigence_ne_manque_jamais_rien():
    assert missing_selftest_plugins(Registry(), []) == []
    assert missing_selftest_plugins(None, []) == []


def test_registre_absent_avec_exigence_est_un_manque():
    """Ne pas savoir vérifier n'est pas la même chose que vérifier."""
    assert missing_selftest_plugins(None, ["bijouterie"]) == [
        "bijouterie : non chargé"]


def test_chaine_complete_plugin_casse_donne_un_manque(tmp_path):
    """Du ``register()`` qui lève jusqu'au verdict, sans rien inventer.

    C'est le scénario exact que la CI d'un dépôt de plugin doit voir
    rouge : le registre avale l'erreur pour ne pas briquer FreeSolid, le
    selftest tourne et ne rend que les indicateurs du noyau — tous vrais.
    """
    _write_python_plugin(
        tmp_path, "casse", register_body="raise RuntimeError('noyau bougé')")
    registry = load_plugins(root=str(tmp_path))

    report = {"noyau": True}
    registry.run_selftest(None, lambda _n: None, report)

    # Le selftest est « vert » : aucun indicateur faux.
    assert [k for k, v in report.items() if v is not True] == []
    # Et pourtant le plugin exigé n'est pas là — c'est ça qu'on attrape.
    assert any("casse" in note for note in registry.notes)
    assert missing_selftest_plugins(registry, ["casse"]) == [
        "casse : non chargé"]


def test_chaine_complete_plugin_sain_ne_manque_pas(tmp_path):
    _write_python_plugin(
        tmp_path, "sain",
        register_body=(
            "registre.selftest_step('etape', "
            "lambda k, mark, rep: rep.update(s1=True, s2=True))"))
    registry = load_plugins(root=str(tmp_path))

    report = {"noyau": True}
    registry.run_selftest(None, lambda _n: None, report)

    assert registry.selftest_counts == {"sain": 2}
    assert missing_selftest_plugins(registry, ["sain"]) == []


def test_compte_negatif_compte_comme_absent():
    """Une étape qui écrase un booléen ne vaut pas contribution."""
    registry = Registry()
    registry.manifests.append({"nom": "delta"})
    registry.selftest_counts["delta"] = -1
    assert missing_selftest_plugins(registry, ["delta"]) == [
        "delta : chargé mais n'a contribué aucun indicateur"]
