"""Clés neutres des cotes rééditables : la table ``PARAM_KEYS``.

L'interface lit et écrit les cotes d'une fonction par clé neutre
(``get_params`` -> ``key``, ``set_params``), jamais par nom de propriété
FreeCAD. La table vit dans ``engine/vocab.py`` ; ses clés sont celles des
formulaires de création. Sans FreeCAD : l'aller-retour tourne sur des
objets factices.
"""

import re
from pathlib import Path

import pytest

from engine.equations import EquationsMixin
from engine.kernel import Kernel, KernelError
from engine.vocab import (
    PARAM_KEYS, PARAM_KEYS_DEFAULT, TYPE_KEYS, param_key_for, param_prop_for,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
FEATURES = APP / "features"
TREE_JS = APP / "tree.js"

#: Cotes que la réédition propose en plus de ``_EDITABLE_PROPS``, par genre.
EXTRA_PROPS = {
    "chamfer": ("Size2", "ChamferType", "FlipDirection"),
    "revolution": ("Reversed", "Midplane", "axis"),
    "groove": ("Reversed", "Midplane", "axis"),
    "linear_pattern": ("Occurrences2", "Length2"),
}


def _all_props():
    props = set(PARAM_KEYS_DEFAULT)
    for table in PARAM_KEYS.values():
        props |= set(table)
    return props


# -- la table ---------------------------------------------------------------

def test_les_genres_de_la_table_existent():
    assert set(PARAM_KEYS) <= set(TYPE_KEYS.values())


def test_une_cle_est_neutre():
    """camelCase comme les formulaires ; jamais un nom de propriété."""
    props = _all_props()
    tables = list(PARAM_KEYS.values()) + [PARAM_KEYS_DEFAULT]
    for table in tables:
        for prop, key in table.items():
            assert re.fullmatch(r"[a-z][A-Za-z0-9]*", key), key
            assert key == prop or key not in props, (prop, key)


def test_une_table_par_genre_va_et_revient():
    """Chaque cote d'un genre a sa clé, et la clé ramène la cote : la table
    du genre l'emporte sur la table par défaut."""
    for type_key, table in PARAM_KEYS.items():
        assert len(set(table.values())) == len(table), type_key
        for prop, key in table.items():
            assert param_key_for(type_key, prop) == key
            assert param_prop_for(type_key, key) == prop, (type_key, key)
        for prop, key in PARAM_KEYS_DEFAULT.items():
            if prop in table or key in table.values():
                continue
            assert param_prop_for(type_key, key) == prop, (type_key, key)
    assert len(set(PARAM_KEYS_DEFAULT.values())) == len(PARAM_KEYS_DEFAULT)


def test_chaque_cote_reeditable_a_sa_cle():
    for prop in EquationsMixin._EDITABLE_PROPS:
        assert prop in PARAM_KEYS_DEFAULT, prop
    for type_key, extras in EXTRA_PROPS.items():
        for prop in extras:
            assert prop in PARAM_KEYS[type_key], (type_key, prop)


def test_les_cles_reprennent_les_formulaires_de_creation():
    """Une clé de genre se lit dans app/features/ : clé d'un champ de
    formulaire, ou paramètre que le formulaire envoie à l'op."""
    text = "\n".join(path.read_text(encoding="utf-8")
                     for path in FEATURES.glob("*.js"))
    for type_key, table in PARAM_KEYS.items():
        for key in table.values():
            assert re.search(r"\b%s\b" % re.escape(key), text), (type_key, key)


def test_transition_et_refus():
    assert param_prop_for("pad", "length") == "Length"
    assert param_prop_for("pad", "Length") == "Length"  # nom FreeCAD connu
    assert param_prop_for("surface_extrude", "length") == "LengthFwd"
    assert param_prop_for("surface_extrude", "lengthFwd") is None
    assert param_prop_for("thickness", "thickness") == "Value"
    assert param_prop_for("datum_plane", "length") == "Length"  # par défaut
    assert param_prop_for("pad", "depth2") is None
    assert param_prop_for("pad", "Bogus") is None


# -- l'interface ------------------------------------------------------------

def _labels():
    text = TREE_JS.read_text(encoding="utf-8")
    match = re.search(r"export const PARAM_LABELS = \{(.*?)\n\};", text, re.S)
    assert match
    return set(re.findall(r"^\s*([A-Za-z0-9]+):", match.group(1), re.M))


def test_chaque_cote_affichee_a_son_libelle():
    """Une cote numérique s'affiche (panneau, cote dans la vue, graphe) sous
    son libellé : ``PARAM_LABELS`` de tree.js la nomme."""
    labels = _labels()
    numeric = set(EquationsMixin._EDITABLE_PROPS) | {"Size2", "Occurrences2"}
    for prop in numeric:
        assert PARAM_KEYS_DEFAULT.get(prop, "size2" if prop == "Size2"
                                      else "count2") in labels, prop
    for type_key, table in PARAM_KEYS.items():
        for prop, key in table.items():
            if prop in numeric:
                assert key in labels, (type_key, key)
    assert not labels & _all_props()


#: Propriétés qui sont aussi un mot affiché (« Angle », « Occurrences ») ou
#: un type de contrainte d'esquisse (``Radius``, ``Diameter``) : seules
#: leurs lectures (``.Angle``) et leurs clés d'objet (``Angle:``) comptent.
#: Une clé d'objet colle ses deux-points ; le français met une espace.
_AUSSI_UN_MOT = {"Angle", "Radius", "Diameter", "Occurrences"}


def test_app_ne_nomme_aucune_propriete_freecad():
    props = sorted(_all_props() - {"axis"})
    words = "|".join(props)
    strict = "|".join(p for p in props if p not in _AUSSI_UN_MOT)
    pattern = re.compile(
        r"""\.(?:%s)\b|(?<![\w.$])(?:%s):|["'`](?:%s)["'`]"""
        % (words, words, strict))
    # ``prop`` (la propriété FreeCAD de get_params) reste pour le moteur et
    # les plugins pendant la transition : l'interface lit ``key``.
    reads_prop = re.compile(r"""\.prop\b|\[["']prop["']\]""")
    hits = []
    for path in APP.rglob("*.js"):
        if "vendor" in path.relative_to(APP).parts:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) or reads_prop.search(line):
                hits.append("{}:{}: {}".format(
                    path.relative_to(ROOT), i, line.strip()))
    assert hits == []


# -- aller-retour get_params -> set_params, objets factices -----------------

class _Obj:
    """Une fonction : TypeId, propriétés, moteur d'expressions."""

    def __init__(self, name, type_id, **props):
        self.Name = name
        self.Label = name
        self.TypeId = type_id
        self.ExpressionEngine = []
        self.PropertiesList = list(props)
        for prop, value in props.items():
            setattr(self, prop, value)

    def setExpression(self, prop, expr):
        self.ExpressionEngine = [
            (path, text) for path, text in self.ExpressionEngine if path != prop]
        if expr is not None:
            self.ExpressionEngine.append((prop, expr))


class _Doc:
    def __init__(self, *objects):
        self._objects = {obj.Name: obj for obj in objects}

    def getObject(self, name):
        return self._objects.get(name)


def _kernel(*objects):
    kernel = Kernel.__new__(Kernel)
    kernel._doc = _Doc(*objects)
    kernel._recompute = lambda: None
    kernel._invalid_dressup_message = lambda obj: None
    kernel._drop_unused_axis_tools = lambda: None
    kernel.get_tree = lambda: {"features": []}
    return kernel


#: Un objet par genre rééditable : TypeId et cotes de départ.
CASES = {
    "pad": ("PartDesign::Pad", {"Length": 10.0}),
    "pocket": ("PartDesign::Pocket", {"Length": 5.0}),
    "revolution": ("PartDesign::Revolution", {"Angle": 360.0}),
    "groove": ("PartDesign::Groove", {"Angle": 180.0}),
    "fillet": ("PartDesign::Fillet", {"Radius": 2.0}),
    "chamfer": ("PartDesign::Chamfer", {
        "ChamferType": "Two distances", "Size": 1.0, "Size2": 2.0,
        "Angle": 45.0, "FlipDirection": False}),
    "thickness": ("PartDesign::Thickness", {"Value": 1.0}),
    "draft": ("PartDesign::Draft", {"Angle": 3.0}),
    "hole": ("PartDesign::Hole", {
        "Diameter": 6.0, "Depth": 15.0, "HoleCutDiameter": 10.0,
        "HoleCutDepth": 3.0}),
    "linear_pattern": ("PartDesign::LinearPattern", {
        "Length": 30.0, "Occurrences": 3, "Occurrences2": 2}),
    "polar_pattern": ("PartDesign::PolarPattern", {
        "Angle": 360.0, "Occurrences": 4}),
    "helix": ("PartDesign::AdditiveHelix", {
        "Pitch": 8.0, "Height": 40.0, "Angle": 0.0}),
    "helix_cut": ("PartDesign::SubtractiveHelix", {
        "Pitch": 4.0, "Height": 20.0, "Angle": 0.0}),
    "surface_extrude": ("Part::Extrusion", {"LengthFwd": 12.0}),
    "surface_revolve": ("Part::Revolution", {"Angle": 90.0}),
    "surface_offset": ("Part::Offset", {"Value": 2.0}),
    "surface_radiate": ("Part::Offset2D", {"Value": 3.0}),
    "curve_helix": ("Part::Helix", {
        "Pitch": 5.0, "Height": 20.0, "Radius": 4.0, "Angle": 0.0}),
    "datum_plane": ("PartDesign::Plane", {"Length": 50.0}),
}


@pytest.mark.parametrize("type_key", sorted(CASES))
def test_aller_retour_en_cles_neutres(type_key):
    type_id, props = CASES[type_key]
    obj = _Obj("F", type_id, **props)
    kernel = _kernel(obj)
    params = kernel.get_params("F")["params"]
    assert params, type_key
    for param in params:
        assert param["key"] == param_key_for(type_key, param["prop"])
        assert param["key"] != param["prop"]
    # Chaque cote change d'une unité, par sa clé neutre ; elle arrive sur
    # la bonne propriété FreeCAD.
    values = {p["key"]: p["value"] + 1 for p in params}
    kernel.set_params("F", values)
    for param in params:
        assert getattr(obj, param["prop"]) == param["value"] + 1
    again = kernel.get_params("F")["params"]
    assert [(p["key"], p["value"]) for p in again] == [
        (key, value) for key, value in values.items()]


def test_aller_retour_des_cotes_non_numeriques():
    """Type et sens du chanfrein, sens de la révolution : clés neutres."""
    chamfer = _Obj("C", "PartDesign::Chamfer", ChamferType="Equal distance",
                   Size=1.0, Size2=1.0, Angle=45.0, FlipDirection=False)
    kernel = _kernel(chamfer)
    kernel.set_params("C", {"kind": "angle", "size": 2, "angle": 30,
                            "flip": True})
    assert chamfer.ChamferType == "Distance and Angle"
    assert (chamfer.Size, chamfer.Angle, chamfer.FlipDirection) == (2, 30, True)
    assert [p["key"] for p in kernel.get_params("C")["params"]] == [
        "size", "angle"]
    revolution = _Obj("R", "PartDesign::Revolution", Angle=360.0,
                      Reversed=False, Midplane=False)
    kernel = _kernel(revolution)
    kernel.set_params("R", {"reversed": True, "midplane": False})
    assert (revolution.Reversed, revolution.Midplane) == (True, False)


def test_une_expression_passe_par_la_cle_neutre():
    obj = _Obj("F", "PartDesign::Pad", Length=10.0)
    kernel = _kernel(obj)
    kernel.set_params("F", {"length": "2*Variables.largeur"})
    assert obj.ExpressionEngine == [("Length", "2*Variables.largeur")]
    assert kernel.get_params("F")["params"][0]["expr"] == "2*Variables.largeur"


def test_set_param_accepte_la_cle_neutre():
    obj = _Obj("F", "PartDesign::Fillet", Radius=2.0)
    kernel = _kernel(obj)
    kernel.set_param("F", "radius", 3)
    assert obj.Radius == 3


def test_transition_un_nom_freecad_connu_passe_encore():
    obj = _Obj("F", "PartDesign::Pad", Length=10.0)
    kernel = _kernel(obj)
    kernel.set_params("F", {"Length": 7})
    assert obj.Length == 7


@pytest.mark.parametrize("key", ["depthh", "Bogus", "depth2", "thinT9"])
def test_une_cle_inconnue_est_refusee(key):
    obj = _Obj("F", "PartDesign::Pad", Length=10.0)
    kernel = _kernel(obj)
    with pytest.raises(KernelError, match="propriété non éditable : " + key):
        kernel.set_params("F", {key: 3})
    assert obj.Length == 10.0


def test_une_cote_absente_est_refusee_sous_sa_cle():
    """``lengthFwd`` (table par défaut) sur une extrusion : la fonction n'a
    pas cette cote, le refus nomme la clé demandée."""
    obj = _Obj("F", "PartDesign::Pad", Length=10.0)
    kernel = _kernel(obj)
    with pytest.raises(KernelError, match="F n'a pas de propriété lengthFwd$"):
        kernel.set_params("F", {"lengthFwd": 3})


def test_une_cle_connue_mais_non_editable_est_refusee_sous_son_nom():
    """``reversed`` d'une extrusion se règle à la création : le refus nomme
    la clé demandée, pas la propriété FreeCAD."""
    obj = _Obj("F", "PartDesign::Pad", Length=10.0, Reversed=False)
    kernel = _kernel(obj)
    with pytest.raises(KernelError, match="propriété non éditable : reversed$"):
        kernel.set_params("F", {"reversed": True})
    assert obj.Reversed is False
