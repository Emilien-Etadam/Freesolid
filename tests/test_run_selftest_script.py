"""``scripts/run-selftest.py`` sans FreeCAD, par noyau bouchon.

Ce script n'est exercé en CI que par le job selftest, qui exige un
FreeCAD réel. Or c'est lui qui porte le verdict sur les plugins exigés :
sans ces tests, la seule preuve que le verdict fonctionne serait de
casser un plugin exprès et de regarder la CI rougir.

Le bouchon remplace ``engine.kernel`` dans ``sys.modules`` avant que le
script ne l'importe. Tout le reste — ``engine.platform``,
``engine.plugins`` — est le vrai code.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "run-selftest.py"


def _lanceur(rapport, plugins):
    """Script qui injecte un noyau bouchon puis exécute run-selftest.py.

    ``plugins`` est une liste de ``(nom, indicateurs)`` : le nom apparaît
    dans les manifestes, le compte dans ``selftest_counts``. C'est
    exactement ce que le vrai registre porte après un selftest.
    """
    return textwrap.dedent("""
        import sys, types
        sys.path.insert(0, {repo!r})
        from engine.plugins import Registry

        registre = Registry()
        for nom, n in {plugins!r}:
            registre.manifests.append({{"nom": nom}})
            if n is not None:
                registre.selftest_counts[nom] = n

        faux = types.ModuleType("engine.kernel")

        class KernelError(Exception):
            pass

        class Kernel:
            def __init__(self):
                self._plugins = registre

            def ping(self):
                return {{"freecad": "1.1.3"}}

            def selftest(self):
                return dict({rapport!r})

        faux.Kernel = Kernel
        faux.KernelError = KernelError
        sys.modules["engine.kernel"] = faux

        code = open({script!r}, encoding="utf-8").read()
        exec(compile(code, {script!r}, "exec"),
             {{"__name__": "__main__", "__file__": {script!r}}})
    """).format(repo=str(_REPO), plugins=plugins, rapport=rapport,
                script=str(_SCRIPT))


def _run(rapport, plugins, exige=None, tmp_path=None):
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONIOENCODING": "utf-8",
        "FREESOLID_SELFTEST_FAILURES": str(tmp_path / "echecs.txt"),
    }
    if exige is not None:
        env["FREESOLID_SELFTEST_PLUGINS"] = exige
    return subprocess.run(
        [sys.executable, "-c", _lanceur(rapport, plugins)],
        capture_output=True, text=True, env=env, timeout=60)


_VERT = {"steps": ["m0"], "noyau_ok": True, "freecad": "1.1.3",
         "freecad_reference": "1.1.3"}


def test_noyau_seul_sans_exigence_sort_zero(tmp_path):
    """FreeSolid sans aucun plugin doit rester vert — il tourne très bien."""
    res = _run(_VERT, [], tmp_path=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "plugins chargés : (aucun)" in res.stdout
    assert "SELFTEST OK" in res.stdout


def test_plugin_exige_et_present_sort_zero(tmp_path):
    rapport = dict(_VERT, gem_ok=True)
    res = _run(rapport, [("bijouterie", 24)], exige="bijouterie",
               tmp_path=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "plugins chargés : bijouterie" in res.stdout
    assert "(bijouterie : 24)" in res.stdout


def test_plugin_exige_mais_absent_sort_un(tmp_path):
    """Le cas entier : rapport sans un seul indicateur faux, et pourtant rouge."""
    res = _run(_VERT, [], exige="bijouterie", tmp_path=tmp_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "bijouterie : non chargé" in res.stdout
    trace = (tmp_path / "echecs.txt").read_text(encoding="utf-8")
    assert "bijouterie" in trace


def test_plugin_charge_mais_muet_sort_un(tmp_path):
    res = _run(_VERT, [("bijouterie", 0)], exige="bijouterie",
               tmp_path=tmp_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "n'a contribué aucun indicateur" in res.stdout


def test_les_notes_du_registre_sont_imprimees(tmp_path):
    """Une panne de chargement doit être lisible, pas muette."""
    lanceur = _lanceur(_VERT, []).replace(
        "registre = Registry()",
        "registre = Registry()\n"
        "registre.notes.append('plugin « x » non chargé : boum')")
    res = subprocess.run(
        [sys.executable, "-c", lanceur], capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8",
             "FREESOLID_SELFTEST_FAILURES": str(tmp_path / "echecs.txt")},
        timeout=60)
    assert "non chargé : boum" in res.stdout, res.stdout + res.stderr


def test_indicateur_faux_reste_prioritaire(tmp_path):
    """Un indicateur faux sort 1 par lui-même, sans passer par les plugins."""
    res = _run(dict(_VERT, noyau_ok=False), [], exige="bijouterie",
               tmp_path=tmp_path)
    assert res.returncode == 1
    assert "indicateurs faux : noyau_ok" in res.stdout


def test_exigence_vide_ou_espaces_n_exige_rien(tmp_path):
    for valeur in ("", "  ", " , "):
        res = _run(_VERT, [], exige=valeur, tmp_path=tmp_path)
        assert res.returncode == 0, (valeur, res.stdout + res.stderr)


def test_deux_plugins_exiges_un_seul_present(tmp_path):
    res = _run(dict(_VERT, g=True), [("bijouterie", 1)],
               exige="bijouterie,gravure", tmp_path=tmp_path)
    assert res.returncode == 1
    assert "gravure : non chargé" in res.stdout
    assert "bijouterie : non chargé" not in res.stdout
