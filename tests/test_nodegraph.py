"""Évaluateur de fonction graphe — pur, sans FreeCAD."""

import pytest

from engine.nodegraph import (
    COUNT_MAX, GraphError, _NODE_INPUTS, evaluate, migrate_graph, vocabulary,
)
from engine import vocab


def _n(ident, kind, **fields):
    node = {"id": ident, "type": kind}
    node.update(fields)
    return node


def _e(src, dst, port):
    return {"from": src, "to": dst, "input": port}


def _g(nodes, edges, output):
    return {"nodes": nodes, "edges": edges, "output": output}


def _box_at(x, y, z, length=1, width=1, height=1):
    return _g(
        [
            _n("p", "point", x=x, y=y, z=z),
            _n("b", "boite", longueur=length, largeur=width, hauteur=height),
        ],
        [_e("p", "b", "ancrage")],
        "b",
    )


def test_broadcast_scalaire_sur_liste():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=10, nombre=5),
            _n("deux", "nombre", value=2),
            _n("x", "calcul", op="*"),
            _n("y", "nombre", value=0),
            _n("z", "nombre", value=0),
            _n("pts", "point"),
            _n("cyl", "cylindre", rayon=3, hauteur=20),
        ],
        [
            _e("xs", "x", "a"),
            _e("deux", "x", "b"),
            _e("x", "pts", "x"),
            _e("y", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )
    out = evaluate(graph, {})
    assert len(out) == 5
    assert [round(item["x"]) for item in out] == [0, 20, 40, 60, 80]
    assert all(item["shape"] == "cylinder" for item in out)
    assert all(item["y"] == 0 and item["z"] == 0 for item in out)


def test_appariement_memes_longueurs():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=10, nombre=3),
            _n("ys", "serie", depart=1, pas=1, nombre=3),
            _n("z", "nombre", value=0),
            _n("pts", "point"),
            _n("cyl", "cylindre", rayon=2, hauteur=8),
        ],
        [
            _e("xs", "pts", "x"),
            _e("ys", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )
    out = evaluate(graph, {})
    assert [(item["x"], item["y"]) for item in out] == [
        (0, 1), (10, 2), (20, 3),
    ]


def test_refus_longueurs_differentes_cite_les_deux():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=10, nombre=3),
            _n("ys", "serie", depart=0, pas=10, nombre=5),
            _n("z", "nombre", value=0),
            _n("pts", "point"),
            _n("cyl", "cylindre", rayon=2, hauteur=8),
        ],
        [
            _e("xs", "pts", "x"),
            _e("ys", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"longueurs 3 et 5") as excinfo:
        evaluate(graph, {})
    assert "pts" in str(excinfo.value)


def test_cycle_refuse_noeud_nomme():
    graph = _g(
        [
            _n("a", "calcul", op="+"),
            _n("b", "calcul", op="+"),
            _n("un", "nombre", value=1),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [
            _e("un", "a", "a"),
            _e("b", "a", "b"),
            _e("un", "b", "a"),
            _e("a", "b", "b"),
            _e("a", "cyl", "rayon"),
        ],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"cycle détecté") as excinfo:
        evaluate(graph, {})
    message = str(excinfo.value)
    assert "a" in message or "b" in message


def test_cycle_sur_soi_meme():
    graph = _g(
        [
            _n("a", "calcul", op="+", b=1),
            _n("cyl", "cylindre", rayon=1, hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("a", "a", "a"), _e("a", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"cycle détecté.*a"):
        evaluate(graph, {})


def test_plafond_depasse_sans_troncature():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=1, nombre=COUNT_MAX + 1),
            _n("cyl", "cylindre", rayon=1, hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("xs", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"aucune troncature") as excinfo:
        evaluate(graph, {})
    assert str(COUNT_MAX) in str(excinfo.value)
    assert str(COUNT_MAX + 1) in str(excinfo.value)


def test_output_inconnu():
    graph = _box_at(0, 0, 0)
    graph["output"] = "fantome"
    with pytest.raises(GraphError, match=r"sortie inconnu.*fantome"):
        evaluate(graph, {})


def test_entree_manquante():
    graph = _g(
        [_n("cyl", "cylindre", rayon=1, hauteur=1)],
        [],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"entrée manquante « ancrage »") as excinfo:
        evaluate(graph, {})
    assert "cyl" in str(excinfo.value)


def test_pas_nul():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=0, nombre=3),
            _n("cyl", "cylindre", rayon=1, hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("xs", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"pas nul"):
        evaluate(graph, {})


def test_division_par_zero():
    graph = _g(
        [
            _n("a", "nombre", value=8),
            _n("b", "nombre", value=0),
            _n("q", "calcul", op="/"),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("a", "q", "a"), _e("b", "q", "b"), _e("q", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"division par zéro"):
        evaluate(graph, {})


def test_compte_negatif():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=1, nombre=-4),
            _n("cyl", "cylindre", rayon=1, hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("xs", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"compte négatif"):
        evaluate(graph, {})


def test_type_inattendu():
    graph = _g(
        [
            _n("p", "point", x=1, y=2, z=3),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("p", "cyl", "rayon")],
        "cyl",
    )
    with pytest.raises(GraphError, match=r"nombre attendu"):
        evaluate(graph, {})


def test_variable_courante():
    graph = _g(
        [
            _n("v", "variable", name="espacement"),
            _n("xs", "serie", depart=0, nombre=3),
            _n("y", "nombre", value=0),
            _n("z", "nombre", value=0),
            _n("pts", "point"),
            _n("cyl", "cylindre", rayon=2, hauteur=10),
        ],
        [
            _e("v", "xs", "pas"),
            _e("xs", "pts", "x"),
            _e("y", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )
    out = evaluate(graph, {"espacement": 12})
    assert [item["x"] for item in out] == [0, 12, 24]


def test_variable_inconnue():
    graph = _g(
        [
            _n("v", "variable", name="manquant"),
            _n("b", "boite", longueur=1, largeur=1, hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("v", "b", "longueur")],
        "b",
    )
    with pytest.raises(GraphError, match=r"variable inconnue « manquant »"):
        evaluate(graph, {})


def test_sortie_non_forme_refusee():
    graph = _g([_n("n", "nombre", value=3)], [], "n")
    with pytest.raises(GraphError, match=r"n'est pas une forme"):
        evaluate(graph, {})


def test_boite_une_instruction():
    out = evaluate(_box_at(4, 5, 6, length=10, width=8, height=2), {})
    assert out == [{
        "shape": "box", "length": 10.0, "width": 8.0, "height": 2.0,
        "x": 4.0, "y": 5.0, "z": 6.0,
    }]


def _grid_graph(cols=3, rows=2):
    """Grille cols × rows par diffusion d'une série sur une série."""
    return _g(
        [
            _n("ny", "nombre", value=rows),
            _n("one", "nombre", value=1),
            _n("zero", "nombre", value=0),
            _n("x0", "nombre", value=-20),
            _n("dx", "nombre", value=20),
            _n("nx", "nombre", value=cols),
            _n("y0", "nombre", value=-10),
            _n("dy", "nombre", value=20),
            _n("z", "nombre", value=-6),
            _n("ones", "serie"),
            _n("zeros", "calcul", op="*"),
            _n("xstart", "calcul", op="+"),
            _n("xs", "serie"),
            _n("ys", "serie"),
            _n("pts", "point"),
            _n("cyl", "cylindre", rayon=3, hauteur=20),
        ],
        [
            _e("one", "ones", "depart"),
            _e("one", "ones", "pas"),
            _e("ny", "ones", "nombre"),
            _e("zero", "zeros", "a"),
            _e("ones", "zeros", "b"),
            _e("x0", "xstart", "a"),
            _e("zeros", "xstart", "b"),
            _e("xstart", "xs", "depart"),
            _e("dx", "xs", "pas"),
            _e("nx", "xs", "nombre"),
            _e("y0", "ys", "depart"),
            _e("dy", "ys", "pas"),
            _e("ny", "ys", "nombre"),
            _e("xs", "pts", "x"),
            _e("ys", "pts", "y"),
            _e("z", "pts", "z"),
            _e("pts", "cyl", "ancrage"),
        ],
        "cyl",
    )


def test_grille_de_cylindres():
    out = evaluate(_grid_graph(3, 2), {})
    assert len(out) == 6
    positions = [(item["x"], item["y"], item["z"]) for item in out]
    assert positions == [
        (-20.0, -10.0, -6.0), (0.0, -10.0, -6.0), (20.0, -10.0, -6.0),
        (-20.0, 10.0, -6.0), (0.0, 10.0, -6.0), (20.0, 10.0, -6.0),
    ]
    assert all(item["shape"] == "cylinder" for item in out)
    assert all(item["radius"] == 3 and item["height"] == 20 for item in out)


def test_vocabulary_matches_evaluator_inputs():
    """Un type ajouté d'un seul côté casse ce test — c'est le but."""
    from pathlib import Path

    entries = vocabulary()
    types = {entry["type"]: entry for entry in entries}
    declared = {spec.type: spec for spec in vocab.GRAPH_NODES}
    assert set(types) == set(_NODE_INPUTS)
    assert set(types) == set(vocab.GRAPH_NODE_LABELS)
    assert set(types) == set(declared)
    assert len(vocab.GRAPH_NODES) == len(declared)
    icons_dir = Path(__file__).resolve().parents[1] / "app" / "icons"
    allowed_same = {"a", "b", "x", "y", "z", "u", "v"}
    for kind, ports in _NODE_INPUTS.items():
        spec = declared[kind]
        keys = tuple(item["key"] for item in types[kind]["inputs"])
        assert keys == ports
        assert keys == tuple(port.key for port in spec.inputs)
        for item, port in zip(types[kind]["inputs"], spec.inputs):
            assert item["label"] == vocab.graph_input_label(item["key"])
            assert item["label"] != item["key"] or item["key"] in allowed_same
            if port.kind == "number":
                assert "kind" not in item
            else:
                assert item["kind"] == port.kind
        assert types[kind]["label"] == vocab.graph_node_label(kind)
        assert types[kind]["shape"] is spec.shape
        assert types[kind]["implemented"] is spec.implemented
        assert types[kind]["category"] == spec.category
        assert types[kind]["category_label"] == vocab.graph_category_label(
            spec.category)
        assert types[kind]["icon"] == spec.icon
        assert (icons_dir / spec.icon).is_file(), spec.icon
        if spec.implemented:
            assert "reason" not in types[kind]
        else:
            assert types[kind]["reason"] == spec.reason
            assert spec.reason.strip()
    cylindre = types["cylindre"]
    ancrage = next(item for item in cylindre["inputs"]
                   if item["key"] == "ancrage")
    assert ancrage["kind"] == "point"
    assert types["nombre"]["fields"][0]["key"] == "value"
    assert types["addition"]["inputs"][0]["key"] == "a"
    assert "calcul" not in types
    assert types["vecteur"]["implemented"] is True
    assert types["point"]["implemented"] is False
    assert types["sphere"]["implemented"] is False


def test_migrate_calcul_et_point():
    graph = _g(
        [
            _n("deux", "nombre", value=2),
            _n("x", "calcul", op="*"),
            _n("xs", "serie", depart=0, pas=1, nombre=3),
        ],
        [_e("xs", "x", "a"), _e("deux", "x", "b")],
        "x",
    )
    migrated = migrate_graph(graph)
    types = {node["id"]: node["type"] for node in migrated["nodes"]}
    assert types["x"] == "multiplication"
    assert "op" not in migrated["nodes"][1]
    graph["nodes"].append(_n("p", "point", x=1, y=2, z=3))
    graph["output"] = "p"
    migrated = migrate_graph(graph)
    kinds = {node["id"]: node["type"] for node in migrated["nodes"]}
    assert kinds["p"] == "vecteur"


def test_listes_longueur_aplatir_decalage():
    graph = _g(
        [
            _n("xs", "serie", depart=0, pas=1, nombre=4),
            _n("len", "longueur_liste"),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("xs", "len", "liste"), _e("len", "cyl", "rayon")],
        "cyl",
    )
    out = evaluate(graph, {})
    assert out[0]["radius"] == 4.0

    flat = evaluate(_g(
        [
            _n("flat", "option_liste", op="flatten",
               liste=[[1, 2], [3]]),
            _n("len", "longueur_liste"),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("flat", "len", "liste"), _e("len", "cyl", "rayon")],
        "cyl",
    ), {})
    assert flat[0]["radius"] == 3.0

    shifted = evaluate(_g(
        [
            _n("xs", "serie", depart=0, pas=1, nombre=3),
            _n("s", "decalage", decalage=1),
            _n("p", "vecteur", y=0, z=0),
            _n("cyl", "cylindre", rayon=1, hauteur=1),
        ],
        [
            _e("xs", "s", "liste"),
            _e("s", "p", "x"),
            _e("p", "cyl", "ancrage"),
        ],
        "cyl",
    ), {})
    assert [round(item["x"]) for item in shifted] == [1, 2, 0]


def test_vecteur_et_plage():
    graph = _g(
        [
            _n("xs", "plage", depart=1, fin=4, pas=1),
            _n("vx", "vecteur_x"),
            _n("scale", "echelle_vecteur", facteur=10),
            _n("cyl", "cylindre", hauteur=2),
        ],
        [
            _e("vx", "scale", "vecteur"),
            _e("xs", "cyl", "rayon"),
            _e("scale", "cyl", "ancrage"),
        ],
        "cyl",
    )
    out = evaluate(graph, {})
    assert [round(item["radius"]) for item in out] == [1, 2, 3]
    assert all(item["x"] == 10 and item["y"] == 0 and item["z"] == 0
               for item in out)


def test_noeud_non_implemente_cite_sa_raison():
    graph = _g(
        [_n("s", "sphere", rayon=1, point={"x": 0, "y": 0, "z": 0})],
        [],
        "s",
    )
    with pytest.raises(GraphError, match=r"API Part"):
        evaluate(graph, {})


def test_alias_calcul_s_evalue_encore():
    graph = _g(
        [
            _n("a", "nombre", value=8),
            _n("b", "nombre", value=2),
            _n("q", "calcul", op="/"),
            _n("cyl", "cylindre", hauteur=1,
               ancrage={"x": 0, "y": 0, "z": 0}),
        ],
        [_e("a", "q", "a"), _e("b", "q", "b"), _e("q", "cyl", "rayon")],
        "cyl",
    )
    out = evaluate(graph, {})
    assert out[0]["radius"] == 4.0
