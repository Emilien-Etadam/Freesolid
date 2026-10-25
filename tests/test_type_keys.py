"""Genres neutres des objets (``type_key``) : la table d'``engine/vocab.py``.

L'interface lit ``type_key`` à la place du TypeId FreeCAD. Chaque TypeId
que le moteur crée ou liste a son genre ; les familles d'``app/typekeys.js``
suivent la table (ce que l'interface lisait autrefois sur le préfixe du
TypeId). Sans FreeCAD.
"""

import re
from pathlib import Path

from engine import ops
from engine.surfacefeat.commun import SurfaceCommonMixin
from engine.vocab import (
    TERMS, TYPE_KEY_FALLBACKS, TYPE_KEY_OTHER, TYPE_KEYS, type_key_for,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
TYPEKEYS_JS = ROOT / "app" / "typekeys.js"

# Créés par le moteur mais jamais listés pour l'interface : la mise en plan
# (TechDraw), la mécanique interne de l'assemblage (objet, groupe et
# liaisons, des App::FeaturePython).
NOT_LISTED = re.compile(
    r"^(TechDraw::|Assembly::AssemblyObject$|Assembly::JointGroup$"
    r"|App::FeaturePython$)")


def _created_type_ids():
    """TypeId passés en dur à ``addObject`` / ``newObject`` dans engine/."""
    pattern = re.compile(
        r"""(?:addObject|newObject)\(\s*["']([A-Za-z]+::[A-Za-z0-9]+)["']""")
    found = set()
    for path in ENGINE.rglob("*.py"):
        if "selftest" in path.parts:
            continue
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def _js_set(name):
    text = TYPEKEYS_JS.read_text(encoding="utf-8")
    match = re.search(
        r"export const " + name + r" = new Set\(\[(.*?)\]\);", text, re.S)
    assert match, name
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def test_chaque_typeid_du_catalogue_a_son_genre():
    """Ops qui créent une fonction, vocabulaire, surfaces, et tout ce que le
    moteur crée en dur et liste dans l'arbre."""
    wanted = {op.creates for op in ops.CORE_OPS if op.creates}
    wanted |= {term.obj_type for term in TERMS if term.obj_type}
    wanted |= set(SurfaceCommonMixin._SURFACE_TYPE_IDS)
    wanted |= {t for t in _created_type_ids() if not NOT_LISTED.match(t)}
    assert sorted(t for t in wanted if t not in TYPE_KEYS) == []


def test_un_genre_est_neutre_et_unique():
    keys = list(TYPE_KEYS.values())
    assert len(keys) == len(set(keys))
    for key in keys + list(TYPE_KEY_FALLBACKS.values()) + [TYPE_KEY_OTHER]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", key), key


def test_un_genre_suit_l_op_qui_cree_la_fonction():
    """``add_pad`` -> ``pad`` : le genre est le nom de l'op sans ``add_``,
    quand une op déclare ce qu'elle crée."""
    for op in ops.CORE_OPS:
        if op.creates and op.name.startswith("add_"):
            assert TYPE_KEYS[op.creates] == op.name[len("add_"):], op.name


def test_un_typeid_inconnu_garde_sa_famille():
    assert type_key_for("PartDesign::Pad") == "pad"
    assert type_key_for("PartDesign::AdditiveBox") == "feature"
    assert type_key_for("Part::Box") == "surface"
    assert type_key_for("Surface::Sections") == "surface"
    assert type_key_for("Mesh::Feature") == "object"
    assert type_key_for("") == "object"


def test_les_familles_de_l_interface_suivent_la_table():
    """``app/typekeys.js`` remplace les tests de préfixe : PartDesign:: est
    une fonction de corps, Part:: et Surface:: une surface."""
    body = {key for type_id, key in TYPE_KEYS.items()
            if type_id.startswith("PartDesign::")}
    body.add(TYPE_KEY_FALLBACKS["PartDesign"])
    surface = {key for type_id, key in TYPE_KEYS.items()
               if type_id.startswith(("Part::", "Surface::"))}
    surface.update({TYPE_KEY_FALLBACKS["Part"], TYPE_KEY_FALLBACKS["Surface"]})
    assert _js_set("BODY_FEATURE_KEYS") == body
    assert _js_set("SURFACE_KEYS") == surface
