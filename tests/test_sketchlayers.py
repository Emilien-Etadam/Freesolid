"""Calques d'esquisse : liste et report des entités (sans FreeCAD)."""
import pytest

from engine.sketchlayers import LayerError, normalize_layers, remap_assignments


def test_layers_need_unique_names_and_valid_colors():
    out = normalize_layers([{"name": " Cotes ", "color": "#ff0000"},
                            {"name": "Axes", "visible": False}])
    assert out == [{"name": "Cotes", "color": "#ff0000", "visible": True},
                   {"name": "Axes", "color": "", "visible": False}]
    for bad in ([{"name": ""}], [{"name": "a"}, {"name": "a"}],
                [{"name": "a", "color": "rouge"}], ["a"]):
        with pytest.raises(LayerError):
            normalize_layers(bad)


def test_renamed_layer_keeps_its_entities_removed_one_releases_them():
    layers = normalize_layers([{"name": "Contours", "rename": "Profil"}])
    assert remap_assignments({"1": "Profil", "2": "Axes"}, layers) == {
        "1": "Contours"}
