"""Évaluateur de fonction graphe — pur, sans FreeCAD."""

import pytest

from engine.nodegraph import (
    COUNT_MAX, GraphError, _NODE_INPUTS, classify_shape_instructions,
    evaluate, evaluate_instances, mixed_output_message, migrate_graph,
    output_nature, vocabulary,
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
    assert all(item["shape"] == "cylindre" for item in out)
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
        "shape": "boite", "length": 10.0, "width": 8.0, "height": 2.0,
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
    assert all(item["shape"] == "cylindre" for item in out)
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


def test_evaluate_instances_serie_cote_instance():
    graph = _g(
        [
            _n("sx", "serie", depart=0, pas=40, nombre=5),
            _n("vx", "vecteur", y=0, z=0),
            _n("sl", "serie", depart=10, pas=5, nombre=5),
            _n("c", "cote", feature="Pad", prop="Length"),
            _n("i", "instance"),
        ],
        [
            _e("sx", "vx", "x"),
            _e("vx", "i", "decalage"),
            _e("sl", "c", "valeur"),
            _e("c", "i", "cotes"),
        ],
        "i",
    )
    out = evaluate_instances(graph, {})
    assert len(out) == 5
    assert [item["offset"][0] for item in out] == [0, 40, 80, 120, 160]
    assert [item["params"]["Pad"]["Length"] for item in out] == [
        10, 15, 20, 25, 30]
    with pytest.raises(GraphError, match=r"n'est pas une forme"):
        evaluate(graph, {})


def test_evaluate_instances_chaine_et_doublon():
    chain = _g(
        [
            _n("v", "serie", depart=10, pas=5, nombre=2),
            _n("d", "vecteur", x=0, y=0, z=0),
            _n("c1", "cote", feature="Pad", prop="Length"),
            _n("c2", "cote", feature="Pocket", prop="Diameter"),
            _n("i", "instance"),
        ],
        [
            _e("v", "c1", "valeur"),
            _e("c1", "c2", "suite"),
            _e("v", "c2", "valeur"),
            _e("d", "i", "decalage"),
            _e("c2", "i", "cotes"),
        ],
        "i",
    )
    out = evaluate_instances(chain, {})
    assert len(out) == 2
    assert out[0]["params"] == {
        "Pad": {"Length": 10.0}, "Pocket": {"Diameter": 10.0}}
    assert out[1]["params"] == {
        "Pad": {"Length": 15.0}, "Pocket": {"Diameter": 15.0}}
    dup = _g(
        [
            _n("v", "nombre", value=10),
            _n("c1", "cote", feature="Pad", prop="Length"),
            _n("c2", "cote", feature="Pad", prop="Length"),
            _n("i", "instance", decalage={"x": 0, "y": 0, "z": 0}),
        ],
        [
            _e("v", "c1", "valeur"),
            _e("v", "c2", "valeur"),
            _e("c1", "c2", "suite"),
            _e("c2", "i", "cotes"),
        ],
        "i",
    )
    with pytest.raises(GraphError, match=r"Pad\.Length définie deux fois"):
        evaluate_instances(dup, {})


def test_evaluate_instances_longueurs_suite_differentes():
    graph = _g(
        [
            _n("a", "serie", depart=1, pas=1, nombre=2),
            _n("b", "serie", depart=1, pas=1, nombre=3),
            _n("c1", "cote", feature="Pad", prop="Length"),
            _n("c2", "cote", feature="Pocket", prop="Diameter"),
            _n("i", "instance", decalage={"x": 0, "y": 0, "z": 0}),
        ],
        [
            _e("a", "c1", "valeur"),
            _e("b", "c2", "valeur"),
            _e("c1", "c2", "suite"),
            _e("c2", "i", "cotes"),
        ],
        "i",
    )
    with pytest.raises(GraphError, match=r"listes de longueurs 3 et 2"):
        evaluate_instances(graph, {})


def test_instruction_kinds_derived_from_catalogue():
    from engine.nodegraph import _INSTRUCTION_KINDS, _NODE_SHAPES, _SCRIPT_KIND
    assert _NODE_SHAPES == frozenset(
        spec.type for spec in vocab.GRAPH_NODES if spec.shape)
    assert _SCRIPT_KIND in _INSTRUCTION_KINDS
    assert "boite" in _INSTRUCTION_KINDS
    assert "cylindre" in _INSTRUCTION_KINDS
    assert "ligne" in _INSTRUCTION_KINDS
    assert "box" not in _INSTRUCTION_KINDS
    assert "cylinder" not in _INSTRUCTION_KINDS


def test_ligne_et_cercle_emettent_une_instruction():
    line = evaluate(_g(
        [_n("l", "ligne",
            point1={"x": 0, "y": 0, "z": 0},
            point2={"x": 10, "y": 0, "z": 0})],
        [], "l",
    ), {})
    assert line == [{
        "shape": "ligne",
        "point1": [0.0, 0.0, 0.0],
        "point2": [10.0, 0.0, 0.0],
    }]
    circle = evaluate(_g(
        [_n("c", "cercle", rayon=5,
            point={"x": 0, "y": 0, "z": 0},
            direction={"x": 0, "y": 0, "z": 1})],
        [], "c",
    ), {})
    assert circle[0]["shape"] == "cercle"
    assert circle[0]["rayon"] == 5.0


def test_serie_dans_le_rayon_donne_n_cercles():
    graph = _g(
        [
            _n("s", "serie", depart=1, pas=1, nombre=3),
            _n("c", "cercle",
               point={"x": 0, "y": 0, "z": 0},
               direction={"x": 0, "y": 0, "z": 1}),
        ],
        [_e("s", "c", "rayon")],
        "c",
    )
    out = evaluate(graph, {})
    assert [item["rayon"] for item in out] == [1.0, 2.0, 3.0]
    assert all(item["shape"] == "cercle" for item in out)


def test_polyligne_consomme_la_liste_de_points():
    graph = _g(
        [_n("p", "polyligne", ferme=0, point=[
            {"x": 0, "y": 0, "z": 0},
            {"x": 10, "y": 0, "z": 0},
            {"x": 10, "y": 10, "z": 0},
        ])],
        [], "p",
    )
    out = evaluate(graph, {})
    assert len(out) == 1
    assert out[0]["shape"] == "polyligne"
    assert out[0]["points"] == [
        [0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0],
    ]


def test_bspline_interpole_les_points_de_passage():
    graph = _g(
        [_n("b", "bspline", ferme=0, centres=[
            {"x": 0, "y": 0, "z": 0},
            {"x": 5, "y": 1, "z": 0},
            {"x": 10, "y": 0, "z": 0},
        ])],
        [], "b",
    )
    out = evaluate(graph, {})
    assert out[0]["shape"] == "bspline"
    assert out[0]["points"][0] == [0.0, 0.0, 0.0]
    assert out[0]["points"][-1] == [10.0, 0.0, 0.0]


def test_discretiser_cite_la_vraie_raison():
    graph = _g(
        [
            _n("l", "ligne",
               point1={"x": 0, "y": 0, "z": 0},
               point2={"x": 1, "y": 0, "z": 0}),
            _n("d", "discretiser", distance=1),
        ],
        [_e("l", "d", "courbe")],
        "d",
    )
    with pytest.raises(GraphError, match=r"consomme une forme") as excinfo:
        evaluate(graph, {})
    assert "d" in str(excinfo.value)
    assert "API Part" not in str(excinfo.value)


def test_sortie_mixte_nomme_les_natures():
    instructions = [
        {"shape": "boite", "length": 1, "width": 1, "height": 1,
         "x": 0, "y": 0, "z": 0},
        {"shape": "ligne", "point1": [0, 0, 0], "point2": [1, 0, 0]},
    ]
    solids, surfaces = classify_shape_instructions(instructions)
    assert solids == ["boite"]
    assert surfaces == ["ligne"]
    assert output_nature(instructions) is None
    message = mixed_output_message(solids, surfaces)
    assert "Boîte" in message
    assert "Ligne" in message
    assert "une seule nature" in message
