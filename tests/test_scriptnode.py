"""Nœud Python : instruction inerte, refus sans confiance, types, plafond."""

import os

import pytest

from engine.nodegraph import COUNT_MAX, GraphError, evaluate
from engine.scriptnode import execute, evaluate as evaluate_trusted, script_nodes
from engine.kernel import Kernel


def _n(ident, kind, **fields):
    node = {"id": ident, "type": kind}
    node.update(fields)
    return node


def _e(src, dst, port):
    return {"from": src, "to": dst, "input": port}


def _g(nodes, edges, output):
    return {"nodes": nodes, "edges": edges, "output": output}


def _script_cylinder(code, **script_fields):
    node = _n("py", "script", code=code, **script_fields)
    return _g(
        [
            node,
            _n("y", "nombre", value=0),
            _n("z", "nombre", value=0),
            _n("pts", "vecteur"),
            _n("cyl", "cylindre", rayon=3, hauteur=10),
        ],
        [
            _e("py", "pts", "x"),
            _e("y", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )


def test_instruction_script_inerte_sans_exec():
    code = "raise RuntimeError('exécuté')"
    graph = _g([_n("py", "script", code=code)], [], "py")
    out = evaluate(graph, {})
    assert len(out) == 1
    assert out[0]["shape"] == "script"
    assert out[0]["code"] == code
    assert out[0]["id"] == "py"
    assert out[0]["inputs"] == {}


def test_script_sur_chemin_sans_callback_n_execute_pas():
    graph = _script_cylinder("raise RuntimeError('exécuté')")
    with pytest.raises(GraphError) as excinfo:
        evaluate(graph, {})
    message = str(excinfo.value)
    assert "exécuté" not in message
    assert "script" in message


def test_graphe_script_non_autorise_nomme_le_noeud():
    graph = _script_cylinder("raise RuntimeError('exécuté')")
    with pytest.raises(GraphError, match=r"nœud « py \(script\) »") as excinfo:
        evaluate_trusted(graph, {}, trusted=False)
    message = str(excinfo.value)
    assert "autoris" in message
    assert "exécuté" not in message
    assert script_nodes(graph)[0]["id"] == "py"


def test_script_non_autorise_n_ecrit_rien(tmp_path):
    marker = tmp_path / "pwned"
    code = "open({!r}, 'w').write('x')\nreturn 1".format(str(marker))
    graph = _script_cylinder(code)
    with pytest.raises(GraphError, match=r"nœud « py"):
        evaluate_trusted(graph, {}, trusted=False)
    assert not marker.exists()


def test_script_type_inconnu_refuse():
    node = _n("py", "script", code="return 'bonjour'")
    instruction = {"shape": "script", "code": node["code"], "inputs": {},
                   "id": "py"}
    with pytest.raises(GraphError, match=r"nœud « py \(script\) »") as excinfo:
        execute(instruction, node, trusted=True)
    assert "type de retour inconnu" in str(excinfo.value)


def test_script_plafond_elements_refuse():
    node = _n("py", "script",
              code="return list(range({}))".format(COUNT_MAX + 1))
    instruction = {"shape": "script", "code": node["code"], "inputs": {},
                   "id": "py"}
    with pytest.raises(GraphError, match=r"plafond") as excinfo:
        execute(instruction, node, trusted=True)
    assert "py" in str(excinfo.value)
    assert "aucune troncature" in str(excinfo.value)


def test_script_autorise_rend_une_liste():
    graph = _script_cylinder("return [0, 10, 20]")
    out = evaluate_trusted(graph, {}, trusted=True)
    assert [round(item["x"]) for item in out] == [0, 10, 20]
    assert all(item["shape"] == "cylinder" for item in out)


def test_script_recoit_ses_ports():
    graph = _g(
        [
            _n("py", "script", code="return a * 2"),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("py", "cyl", "rayon")],
        "cyl",
    )
    graph["nodes"][0]["a"] = 4
    out = evaluate_trusted(graph, {}, trusted=True)
    assert out[0]["radius"] == 8.0


def test_fermeture_document_oublie_l_autorisation():
    kernel = Kernel()
    kernel._scripts_authorized = True
    kernel._close_current()
    assert kernel._scripts_authorized is False


def test_execute_untrusted_ne_compile_pas(tmp_path):
    marker = tmp_path / "compiled"
    node = _n("py", "script", code="open({!r}, 'w').write('x')\nreturn 1".format(
        str(marker)))
    instruction = {"shape": "script", "code": node["code"], "inputs": {},
                   "id": "py"}
    with pytest.raises(GraphError, match=r"autoris"):
        execute(instruction, node, trusted=False)
    assert not os.path.exists(marker)
