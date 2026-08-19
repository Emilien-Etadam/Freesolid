"""Vocabulary table integrity — runs without FreeCAD."""

import pytest

from engine import vocab


def test_commands_are_unique():
    commands = [t.command for t in vocab.TERMS]
    assert len(commands) == len(set(commands))


def test_every_term_has_both_languages():
    for term in vocab.TERMS:
        assert term.fr.strip(), term.command
        assert term.en.strip(), term.command


def test_commands_are_namespaced():
    # AliasCommand derives its own name by splitting on the first underscore,
    # so a command without one would collide.
    for term in vocab.TERMS:
        assert "_" in term.command, term.command


@pytest.mark.parametrize("obj_type,expected", [
    ("PartDesign::Pad", "Bossage/Base extrudé"),
    ("PartDesign::Pocket", "Enlèvement de matière extrudé"),
    ("PartDesign::Hole", "Assistant de perçage"),
])
def test_label_for_known_type(obj_type, expected):
    assert vocab.label_for_type(obj_type) == expected


def test_label_for_unknown_type_falls_back_to_short_name():
    assert vocab.label_for_type("Part::Cut") == "Cut"


@pytest.mark.parametrize("name,expected", [
    ("XY_Plane", "Plan de dessus"),
    ("XZ_Plane", "Plan de face"),
    ("YZ_Plane", "Plan de droite"),
    # FreeCAD suffixes Origin features once a document holds several Bodies.
    ("XZ_Plane001", "Plan de face"),
    ("Z_Axis", "Axe Z"),
])
def test_origin_plane_mapping(name, expected):
    assert vocab.label_for_origin(name) == expected


def test_unknown_origin_name_is_returned_verbatim():
    assert vocab.label_for_origin("Whatever") == "Whatever"


def test_english_labels_available():
    assert vocab.label_for_type("PartDesign::Pad", lang="en") == \
        "Extruded Boss/Base"
    assert vocab.label_for_origin("XY_Plane", lang="en") == "Top Plane"


def test_graph_node_labels_are_french():
    assert vocab.graph_node_label("cylindre") == "Cylindre"
    assert vocab.graph_node_label("boite") == "Boîte"
    assert vocab.graph_node_label("serie") == "Série"
    assert vocab.graph_input_label("rayon") == "Rayon"
    assert vocab.graph_input_label("ancrage") == "Ancrage"
    assert vocab.graph_field_label("value") == "Valeur"
    assert vocab.graph_node_label("cylindre", lang="en") == "Cylinder"
    assert vocab.graph_node_label("vecteur") == "Vecteur"
    assert vocab.graph_node_label("addition") == "Addition"
    assert vocab.graph_category_label("list") == "Liste"
    assert vocab.graph_category_label("generators") == "Générateurs"
    assert vocab.GRAPH_NODE_BY_TYPE["serie"].category == "list"
    assert vocab.GRAPH_NODE_BY_TYPE["nombre"].category == "number"
    assert vocab.GRAPH_NODE_BY_TYPE["vecteur"].category == "vector"
    assert "scene" not in {n.category for n in vocab.GRAPH_NODES}
    assert "viz" not in {n.category for n in vocab.GRAPH_NODES}
