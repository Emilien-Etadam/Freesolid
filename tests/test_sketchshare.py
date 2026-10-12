"""Contours choisis d'une esquisse partagée (sans FreeCAD)."""
from engine.sketchshare import contour_groups


def test_no_chosen_edge_means_every_contour():
    assert contour_groups([["Edge1"], ["Edge2", "Edge3"]], []) == [0, 1]


def test_a_contour_counts_only_when_all_its_edges_are_chosen():
    wires = [["Edge1", "Edge2", "Edge3", "Edge4"], ["Edge5"], ["Edge6"]]
    assert contour_groups(wires, ["Edge5", "Edge6"]) == [1, 2]
    assert contour_groups(wires, ["Edge1", "Edge2", "Edge5"]) == [1]
