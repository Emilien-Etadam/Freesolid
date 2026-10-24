"""Selftest — graphe de nœuds : fonction graphe, nœud Python, répétition
variable, rejeu.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import json
import math

from engine.kernel import (
    GraphError,
    KernelError,
    dangling_deps,
    evaluate_instances,
)
from engine.replay import _temp_bodies_left


def n1_aretes_de_dependance(self, mark, report, etat):
    mark("n1: arêtes de dépendance dans get_tree")
    self.new_part("Pièce nœuds N001")
    tree = self.add_rect_sketch(80, 50)
    sketch_name = next(
        f["name"] for f in tree["features"]
        if f["type"] == "Sketcher::SketchObject")
    tree = self.add_pad(12)
    pad = next(f for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    report["n1_deps_pad_sketch"] = (
        sketch_name in pad.get("deps", []))
    self.set_params(pad["name"], {"Length": "12 + 3"})
    pad = next(f for f in self.get_tree()["features"]
               if f["type"] == "PartDesign::Pad")
    report["n1_driven_ok"] = "Length" in pad.get("driven", {})
    # Un plan de référence n'est désignable que par son ``name`` :
    # ``id`` reste « XZ » là où le nom prend un suffixe en
    # multi-corps. Sans ce champ, l'arête était pendante.
    tree = self.add_datum_plane(base="XZ")
    xz_name = next(pl["name"] for pl in tree["planes"]
                   if pl["id"] == "XZ")
    datum = next(f for f in tree["features"]
                 if f["type"] == "PartDesign::Plane")
    report["n1b_deps_plan_origine"] = (
        bool(xz_name) and xz_name in datum.get("deps", []))
    report["n1b_arbre_coherent"] = not dangling_deps(tree)


def n4_fonction_graphe(self, mark, report, etat):
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n4: fonction graphe — perçage, réédition, refus atomique")
    import math

    def _n4_node(ident, kind, **fields):
        node = {"id": ident, "type": kind}
        node.update(fields)
        return node

    def _n4_grid(cols, rows):
        # Grille écrite à la main : série en X diffusée sur une
        # série en Y (appariement récursif), cylindres en cut.
        return {
            "nodes": [
                _n4_node("ny", "nombre", value=rows),
                _n4_node("one", "nombre", value=1),
                _n4_node("zero", "nombre", value=0),
                _n4_node("x0", "nombre", value=-20),
                _n4_node("dx", "nombre", value=20),
                _n4_node("nx", "nombre", value=cols),
                _n4_node("y0", "nombre", value=-10),
                _n4_node("dy", "nombre", value=20),
                _n4_node("z", "nombre", value=-6),
                _n4_node("ones", "serie"),
                _n4_node("zeros", "multiplication"),
                _n4_node("xstart", "addition"),
                _n4_node("xs", "serie"),
                _n4_node("ys", "serie"),
                _n4_node("pts", "vecteur"),
                _n4_node("cyl", "cylindre", rayon=3, hauteur=20),
            ],
            "edges": [
                {"from": "one", "to": "ones", "input": "depart"},
                {"from": "one", "to": "ones", "input": "pas"},
                {"from": "ny", "to": "ones", "input": "nombre"},
                {"from": "zero", "to": "zeros", "input": "a"},
                {"from": "ones", "to": "zeros", "input": "b"},
                {"from": "x0", "to": "xstart", "input": "a"},
                {"from": "zeros", "to": "xstart", "input": "b"},
                {"from": "xstart", "to": "xs", "input": "depart"},
                {"from": "dx", "to": "xs", "input": "pas"},
                {"from": "nx", "to": "xs", "input": "nombre"},
                {"from": "y0", "to": "ys", "input": "depart"},
                {"from": "dy", "to": "ys", "input": "pas"},
                {"from": "ny", "to": "ys", "input": "nombre"},
                {"from": "xs", "to": "pts", "input": "x"},
                {"from": "ys", "to": "pts", "input": "y"},
                {"from": "z", "to": "pts", "input": "z"},
                {"from": "pts", "to": "cyl", "input": "ancrage"},
            ],
            "output": "cyl",
        }

    self.new_part("Pièce graphe N004")
    self.add_rect_sketch(80, 50)
    self.add_pad(8)
    vol_plaque = _volume()
    hole_vol = math.pi * 3.0 * 3.0 * 8.0
    tree = self.add_graph_feature(_n4_grid(3, 2), mode="cut")
    graphe = next(f for f in tree["features"] if f.get("graph"))
    vol_perce = _volume()
    shape = self._require_body().Shape
    report["n4_graphe_perce"] = (
        not any(f["error"] for f in tree["features"])
        and shape.isValid()
        and abs((vol_plaque - vol_perce) - 6 * hole_vol) < 25.0)
    stored = self.get_graph_feature(graphe["name"])
    report["n4_graphe_persiste"] = (
        stored.get("mode") == "cut"
        and stored.get("graph", {}).get("output") == "cyl")

    tree = self.edit_graph_feature(graphe["name"], _n4_grid(2, 2))
    vol_reedite = _volume()
    report["n4_graphe_reedite"] = (
        not any(f["error"] for f in tree["features"])
        and self._require_body().Shape.isValid()
        and abs((vol_plaque - vol_reedite) - 4 * hole_vol) < 25.0
        and abs(vol_reedite - vol_perce) > 50.0)

    invalid = _n4_grid(2, 2)
    invalid["output"] = "fantome"
    try:
        self.edit_graph_feature(graphe["name"], invalid)
        report["n4_graphe_refus_atomique"] = False
    except KernelError:
        report["n4_graphe_refus_atomique"] = (
            abs(_volume() - vol_reedite) < 1e-6
            and not any(f["error"]
                        for f in self.get_tree()["features"]))

    tree = self.get_tree()
    report["n4_arbre_propre"] = (
        not any(s["label"] == "Forme du graphe"
                for s in tree["surfaces"])
        and not any(b["label"] == "Corps graphe"
                    for b in tree["bodies"])
        and not dangling_deps(tree)
        and any(f.get("graph") for f in tree["features"]))
    etat._n4_node = _n4_node


def n8_noeud_python(self, mark, report, etat):
    _n4_node = etat._n4_node  # posé par noeuds.n4_fonction_graphe
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n8: nœud Python — refus sans confiance, valeur une fois autorisé")
    self.new_part("Pièce graphe N008")
    self.add_rect_sketch(80, 50)
    self.add_pad(8)
    vol_n8 = _volume()

    def _n8_script_graph():
        return {
            "nodes": [
                _n4_node("py", "script",
                         code="return [0.0, 20.0, 40.0]"),
                _n4_node("y", "nombre", value=0),
                _n4_node("z", "nombre", value=-6),
                _n4_node("pts", "vecteur"),
                _n4_node("cyl", "cylindre", rayon=3, hauteur=20),
            ],
            "edges": [
                {"from": "py", "to": "pts", "input": "x"},
                {"from": "y", "to": "pts", "input": "y"},
                {"from": "z", "to": "pts", "input": "z"},
                {"from": "pts", "to": "cyl", "input": "ancrage"},
            ],
            "output": "cyl",
        }

    try:
        self.add_graph_feature(_n8_script_graph(), mode="cut")
        report["n8_script_refuse_sans_confiance"] = False
    except KernelError as exc:
        message = str(exc)
        report["n8_script_refuse_sans_confiance"] = (
            "py" in message
            and ("autoris" in message or "Python" in message))
    report["n8_script_piece_intacte"] = (
        abs(_volume() - vol_n8) < 1e-3)
    stored_before = [
        f.get("graph") for f in self.get_tree()["features"]
        if f.get("graph")]
    report["n8_script_pas_dans_fcstd"] = not stored_before
    self.authorize_scripts()
    tree = self.add_graph_feature(_n8_script_graph(), mode="cut")
    vol_n8_cut = _volume()
    graphe_n8 = next(
        (f for f in tree["features"] if f.get("graph")), None)
    persisted = (graphe_n8 or {}).get("graph") or {}
    persisted_text = json.dumps(persisted)
    report["n8_script_valeur"] = (
        vol_n8_cut < vol_n8 - 1
        and not any(f["error"] for f in tree["features"])
        and "authorized" not in persisted_text
        and "trusted" not in persisted_text)
    self.new_part("Pièce graphe N008 reset")
    try:
        self.add_graph_feature(_n8_script_graph(), mode="cut")
        report["n8_script_reset_document"] = False
    except KernelError:
        report["n8_script_reset_document"] = True


def n7_sous_elements_esquisse_attachee(self, mark, report, etat):
    mark("n7: sous-éléments et esquisse attachée")
    self.new_part("Pièce nœuds N007")
    tree = self.add_rect_sketch(80, 50)
    xy_name = next(pl["name"] for pl in tree["planes"]
                   if pl["id"] == "XY")
    tree = self.add_pad(12)
    sketch = next(
        child for feat in tree["features"]
        for child in feat.get("children", ())
        if child["type"] == "Sketcher::SketchObject")
    coherent = not dangling_deps(tree)
    report["n7_esquisse_attachee"] = (
        bool(xy_name) and xy_name in sketch.get("deps", [])
        and coherent)
    top_edges = [i for i, edge in
                 enumerate(self._require_body().Shape.Edges)
                 if abs(edge.CenterOfMass.z - 12) < 1e-6]
    fillet_edges = top_edges[:2] if len(top_edges) >= 2 else top_edges
    tree = self.add_fillet(radius=2, edges=fillet_edges)
    fillet = next(f for f in tree["features"]
                  if f["type"] == "PartDesign::Fillet")
    fillet_subs = [
        name for names in (fillet.get("dep_subs") or {}).values()
        for name in names]
    # Dépouille sur une boîte neuve : après congé, la face
    # latérale n'est plus dépouillable (constat n7).
    self.new_part("Pièce nœuds N007 dépouille")
    self.add_rect_sketch(80, 50)
    self.add_pad(12)
    tree = self.add_draft(face=self._side_face_id(), angle=5)
    draft = next(f for f in tree["features"]
                 if f["type"] == "PartDesign::Draft")
    draft_subs = [
        name for names in (draft.get("dep_subs") or {}).values()
        for name in names]
    report["n7_sous_elements"] = (
        any(str(name).startswith("Edge") for name in fillet_subs)
        and any(str(name).startswith("Face") for name in draft_subs)
        and not dangling_deps(tree))


def n9_repetition_groupe_fonctions(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n9: répétition d'un groupe de fonctions")
    self.new_part("Pièce répétition groupe N009")
    self.add_rect_sketch(40, 40)
    tree = self.add_pad(10)
    pad_name = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pad")
    self.add_rect_sketch(10, 10, face=self._top_face_id())
    tree = self.add_pocket(through=True)
    pocket_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pocket")
    tree = self.add_linear_pattern(
        length=30, count=2, axis="X",
        features=[pad_name, pocket_name])
    # 40×40×10 × 2, recouvrement 10 mm, deux perçages 10×10.
    report["n9_repetition_groupe"] = (
        not any(f["error"] for f in tree["features"])
        and _close(_volume(), 26000.0, tol=1e-4))


def n9_spike_rejeu_variable(self, mark, report, etat):
    mark("n9: spike rejeu variable")
    from engine.replay import run_spike_report
    spike = run_spike_report(self)
    report["n9_spike_variable"] = bool(spike["minimal"]["ok"])
    report["n9_spike_rapport"] = {
        "fused_volume": spike["minimal"]["fused_volume"],
        "expected_fused": spike["minimal"]["expected_fused"],
        "cut_volume": spike["minimal"]["cut_volume"],
        "expected_cut": spike["minimal"]["expected_cut"],
        "failed_instance_cleaned": spike["minimal"][
            "failed_instance_cleaned"],
        "tool_absorbed": spike["minimal"].get("tool_absorbed"),
        "habillage": spike["dressup"],
        "indice_perime": spike["stale_index"],
        "cout_s": {k: v for k, v in spike["cost"].items()
                   if k != "cleanup_ok"},
        "cout_proprete": spike["cost"].get("cleanup_ok"),
        "reconstitution": {
            "replayable": sorted(spike["reconstitution"][
                "replayable"]),
            "unreplayable": sorted(spike["reconstitution"][
                "unreplayable"]),
        },
    }


def n10_repetition_variable(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n10: répétition variable")
    from engine.replay import _temp_bodies_left
    self.new_part("Pièce répétition variable N010")
    self.add_rect_sketch(20, 20)
    tree = self.add_pad(10)
    pad_name = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pad")
    self.add_rect_sketch(8, 8, face=self._top_face_id())
    tree = self.add_pocket(through=True)
    pocket_name = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pocket")
    n_before = len(tree["features"])
    # Source : 20×20×10 − 8×8×10 = 3360.
    # Trois instances qui se touchent (pas de 20 mm = largeur),
    # L = 10, 20, 30 : 336 × 60 = 20160. Total fuse = 23520.
    # Un Body n'accepte qu'un solide : des copies disjointes
    # (pas de 40 mm) feraient échouer le booléen.
    tree = self.add_repeat_feature(
        [pad_name, pocket_name],
        [
            {"offset": [20, 0, 0],
             "params": {pad_name: {"Length": 10}}},
            {"offset": [40, 0, 0],
             "params": {pad_name: {"Length": 20}}},
            {"offset": [60, 0, 0],
             "params": {pad_name: {"Length": 30}}},
        ],
        mode="fuse",
    )
    repeat_line = next(f for f in tree["features"] if f.get("repeat"))
    report["n10_repetition_variable"] = (
        not any(f["error"] for f in tree["features"])
        and len(tree["features"]) == n_before + 1
        and _close(_volume(), 23520.0, tol=1e-4)
        and pad_name in (repeat_line.get("deps") or [])
        and pocket_name in (repeat_line.get("deps") or [])
        and not dangling_deps(tree))
    etat.pad_name = pad_name
    etat.pocket_name = pocket_name
    etat.repeat_line = repeat_line


def n10_reedition(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    pad_name = etat.pad_name  # posé par noeuds.n10_repetition_variable
    pocket_name = etat.pocket_name  # posé par noeuds.n10_repetition_variable
    repeat_line = etat.repeat_line  # posé par noeuds.n10_repetition_variable
    mark("n10: réédition")
    # 3360 (source) + 336 × (15+25+35) = 3360 + 25200 = 28560.
    tree = self.edit_repeat_feature(
        repeat_line["name"],
        [
            {"offset": [20, 0, 0],
             "params": {pad_name: {"Length": 15}}},
            {"offset": [40, 0, 0],
             "params": {pad_name: {"Length": 25}}},
            {"offset": [60, 0, 0],
             "params": {pad_name: {"Length": 35}}},
        ],
    )
    stored = self.get_repeat_feature(repeat_line["name"])
    n_repeat = sum(1 for f in tree["features"] if f.get("repeat"))
    report["n10_reedition"] = (
        not any(f["error"] for f in tree["features"])
        and n_repeat == 1
        and _close(_volume(), 28560.0, tol=1e-4)
        and stored.get("mode") == "fuse"
        and stored.get("features") == [pad_name, pocket_name]
        and len(stored.get("instances") or []) == 3)


def n10_proprete(self, mark, report, etat):
    mark("n10: propreté")
    leftover = _temp_bodies_left(self)
    tree = self.get_tree()
    report["n10_proprete"] = (
        leftover == []
        and not any(s["label"] == "Forme de la répétition"
                    for s in tree["surfaces"])
        and not any(b["label"] == "Corps répétition"
                    for b in tree["bodies"])
        and not dangling_deps(tree))


def n10_garde_topologique(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n10: garde topologique — tout ou rien")
    self.new_part("Pièce garde N010")
    self.add_rect_sketch(20, 20)
    tree = self.add_pad(20)
    pad_g = next(f["name"] for f in tree["features"]
                 if f["type"] == "PartDesign::Pad")
    self.add_rect_sketch(8, 8, face=self._top_face_id())
    tree = self.add_pocket(length=5)
    pocket_g = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pocket")
    tree = self.add_fillet(radius=1, edges=[2])
    fillet_g = next(f for f in tree["features"]
                    if f["type"] == "PartDesign::Fillet")
    vol_garde = _volume()
    n_garde = len(self.get_tree()["features"])
    try:
        self.add_repeat_feature(
            [pad_g, pocket_g, fillet_g["name"]],
            [
                {"offset": [40, 0, 0],
                 "params": {pocket_g: {"Length": 5}}},
                {"offset": [80, 0, 0],
                 "params": {pocket_g: {"Length": 25}}},
            ],
            mode="fuse",
        )
        report["n10_garde_refuse"] = False
    except KernelError as exc:
        garde_msg = str(exc)
        report["n10_garde_refuse"] = (
            "n° 2 sur 2" in garde_msg
            and fillet_g["label"] in garde_msg
            and _close(_volume(), vol_garde)
            and len(self.get_tree()["features"]) == n_garde
            and _temp_bodies_left(self) == [])


def n10b_graphe_pilote(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n10b: le graphe pilote")
    # Source : 20×20×10 − 8×8×10 = 3360.
    # serie(20, 20, 3) → décalage X = 20, 40, 60
    # serie(10, 10, 3) → Length = 10, 20, 30
    # 336 × (10+20+30) = 20160 ; total fuse = 3360 + 20160 = 23520.
    self.new_part("Pièce graphe N010b")
    self.add_rect_sketch(20, 20)
    tree = self.add_pad(10)
    pad_b = next(f["name"] for f in tree["features"]
                 if f["type"] == "PartDesign::Pad")
    self.add_rect_sketch(8, 8, face=self._top_face_id())
    tree = self.add_pocket(through=True)
    pocket_b = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pocket")
    n_before_b = len(tree["features"])
    graph_b = {
        "nodes": [
            {"id": "sx", "type": "serie",
             "depart": 20, "pas": 20, "nombre": 3},
            {"id": "vx", "type": "vecteur", "y": 0, "z": 0},
            {"id": "sl", "type": "serie",
             "depart": 10, "pas": 10, "nombre": 3},
            {"id": "c", "type": "cote",
             "feature": pad_b, "prop": "Length"},
            {"id": "i", "type": "instance"},
        ],
        "edges": [
            {"from": "sx", "to": "vx", "input": "x"},
            {"from": "vx", "to": "i", "input": "decalage"},
            {"from": "sl", "to": "c", "input": "valeur"},
            {"from": "c", "to": "i", "input": "cotes"},
        ],
        "output": "i",
    }
    tree = self.add_repeat_feature(
        [pad_b, pocket_b], graph=graph_b, mode="fuse")
    repeat_b = next(f for f in tree["features"] if f.get("repeat"))
    report["n10b_graphe_pilote"] = (
        not any(f["error"] for f in tree["features"])
        and len(tree["features"]) == n_before_b + 1
        and _close(_volume(), 23520.0, tol=1e-4)
        and pad_b in (repeat_b.get("deps") or [])
        and pocket_b in (repeat_b.get("deps") or [])
        and not dangling_deps(tree))
    etat.pad_b = pad_b
    etat.pocket_b = pocket_b
    etat.repeat_b = repeat_b


def n10b_seul_point_verite(self, mark, report, etat):
    pad_b = etat.pad_b  # posé par noeuds.n10b_graphe_pilote
    pocket_b = etat.pocket_b  # posé par noeuds.n10b_graphe_pilote
    repeat_b = etat.repeat_b  # posé par noeuds.n10b_graphe_pilote
    mark("n10b: un seul point de vérité")
    stored_b = self.get_repeat_feature(repeat_b["name"])
    report["n10b_un_seul_point"] = (
        isinstance(stored_b.get("graph"), dict)
        and "instances" not in stored_b
        and stored_b.get("features") == [pad_b, pocket_b])


def n10b_chaine_cotes(self, mark, report, etat):
    mark("n10b: chaîne de cotes")
    chain = {
        "nodes": [
            {"id": "v", "type": "serie",
             "depart": 10, "pas": 5, "nombre": 2},
            {"id": "d", "type": "vecteur", "x": 0, "y": 0, "z": 0},
            {"id": "c1", "type": "cote",
             "feature": "Pad", "prop": "Length"},
            {"id": "c2", "type": "cote",
             "feature": "Pocket", "prop": "Diameter"},
            {"id": "i", "type": "instance"},
        ],
        "edges": [
            {"from": "v", "to": "c1", "input": "valeur"},
            {"from": "c1", "to": "c2", "input": "suite"},
            {"from": "v", "to": "c2", "input": "valeur"},
            {"from": "d", "to": "i", "input": "decalage"},
            {"from": "c2", "to": "i", "input": "cotes"},
        ],
        "output": "i",
    }
    chained = evaluate_instances(chain, {})
    dup = {
        "nodes": [
            {"id": "v", "type": "nombre", "value": 10},
            {"id": "c1", "type": "cote",
             "feature": "Pad", "prop": "Length"},
            {"id": "c2", "type": "cote",
             "feature": "Pad", "prop": "Length"},
            {"id": "i", "type": "instance",
             "decalage": {"x": 0, "y": 0, "z": 0}},
        ],
        "edges": [
            {"from": "v", "to": "c1", "input": "valeur"},
            {"from": "v", "to": "c2", "input": "valeur"},
            {"from": "c1", "to": "c2", "input": "suite"},
            {"from": "c2", "to": "i", "input": "cotes"},
        ],
        "output": "i",
    }
    dup_named = False
    try:
        evaluate_instances(dup, {})
    except GraphError as exc:
        dup_named = "Pad.Length" in str(exc)
    report["n10b_chaine_cotes"] = (
        len(chained) == 2
        and all("Length" in (item["params"].get("Pad") or {})
                for item in chained)
        and all("Diameter" in (item["params"].get("Pocket") or {})
                for item in chained)
        and dup_named)


def n10b_garde_attache(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n10b: garde d'attache")
    self.new_part("Pièce attache N010b")
    self.add_rect_sketch(20, 20)
    tree = self.add_pad(10)
    pad_a = next(f["name"] for f in tree["features"]
                 if f["type"] == "PartDesign::Pad")
    self.add_rect_sketch(8, 8, face=self._top_face_id())
    tree = self.add_pocket(length=5)
    pocket_a = next(f["name"] for f in tree["features"]
                    if f["type"] == "PartDesign::Pocket")
    tree = self.add_rect_sketch(6, 6, face=self._top_face_id())
    attach_sk = next(
        f for f in reversed(tree["features"])
        if f["type"] == "Sketcher::SketchObject")
    tree = self.add_pad(2)
    pads_a = [f["name"] for f in tree["features"]
              if f["type"] == "PartDesign::Pad"]
    small_a = pads_a[-1]
    vol_attache = _volume()
    n_attache = len(self.get_tree()["features"])
    try:
        self.add_repeat_feature(
            [pad_a, pocket_a, small_a],
            [
                {"offset": [40, 0, 0],
                 "params": {pocket_a: {"Length": 5}}},
                {"offset": [80, 0, 0],
                 "params": {pocket_a: {"Length": 20}}},
            ],
            mode="fuse",
        )
        report["n10b_attache_refuse"] = False
    except KernelError as exc:
        attache_msg = str(exc)
        report["n10b_attache_refuse"] = (
            "n° 2" in attache_msg
            and attach_sk["label"] in attache_msg
            and _close(_volume(), vol_attache)
            and len(self.get_tree()["features"]) == n_attache
            and _temp_bodies_left(self) == [])


def n11_helice_graphe_balayage(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _n4_node = etat._n4_node  # posé par noeuds.n4_fonction_graphe
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    mark("n11: hélice graphe + balayage — le chemin complet")
    # Hélice cylindrique : pas=10, hauteur=20, rayon=10 → 2 tours.
    # Longueur = 2 * sqrt((2π·10)² + 10²) = 2√(400π²+100) ≈ 127.245.
    # Profil Ø4 → aire π·2² ; volume ≈ 4π × 127.245 ≈ 1599.15.
    self.new_part("Pièce graphe N011")
    helix_graph = {
        "nodes": [
            _n4_node("h", "helice", pas_helice=10, hauteur=20,
                     rayon=10, angle=0, gauche=0),
        ],
        "edges": [],
        "output": "h",
    }
    tree = self.add_graph_feature(helix_graph)
    helix_surf = next(
        (s for s in tree["surfaces"] if s.get("graph")), None)
    helix_ok = (
        helix_surf is not None
        and sum(1 for s in tree["surfaces"] if s.get("graph")) == 1)
    # Profil dans le plan XZ, centré au départ de l'hélice (10, 0, 0) :
    # la tangente initiale est ≈ +Y, normale du plan XZ.
    state = self.sketch_start(plane="XZ")
    pipe_sk = state["sketch"]
    self.sketch_add_circle(pipe_sk, 10, 0, 2)
    self.sketch_finish(pipe_sk)
    try:
        tree = self.add_sweep(
            profile=pipe_sk, spine=helix_surf["name"])
        helix_len = 2.0 * math.sqrt((2.0 * math.pi * 10.0) ** 2 + 10.0 ** 2)
        expected_vol = (math.pi * 2.0 * 2.0) * helix_len
        vol = _volume()
        report["n11_helice_balayage"] = (
            helix_ok
            and not any(f["error"] for f in tree["features"])
            and vol > 0
            and self._require_body().Shape.isValid()
            and _close(vol, expected_vol, tol=0.05))
    except KernelError:
        report["n11_helice_balayage"] = False


def n11_neuf_noeuds(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _n4_node = etat._n4_node  # posé par noeuds.n4_fonction_graphe
    mark("n11: neuf nœuds — chacun sa forme")
    origin = {"x": 0, "y": 0, "z": 0}
    zdir = {"x": 0, "y": 0, "z": 1}

    def _n11_last_shape():
        surf = self.get_tree()["surfaces"][-1]
        return self._require_doc().getObject(surf["name"]).Shape

    def _n11_add(graph):
        n_before = len(self.get_tree()["surfaces"])
        tree = self.add_graph_feature(graph)
        return (
            len(tree["surfaces"]) == n_before + 1
            and bool(tree["surfaces"][-1].get("graph")))

    n11_nodes = {}
    n11_nodes["ligne"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "ligne",
                point1=origin, point2={"x": 10, "y": 0, "z": 0})],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Length, 10.0, tol=1e-6))
    n11_nodes["cercle"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "cercle", rayon=10, point=origin,
                direction=zdir)],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Length, 2 * math.pi * 10,
                      tol=1e-4))
    # Arc 90° rayon 10 : longueur = 10·π/2.
    n11_nodes["arc"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "arc", rayon=10, point=origin, direction=zdir,
                angle1=0, angle2=90)],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Length, 10 * math.pi / 2,
                      tol=1e-4))
    # Arc 3 pts : (10,0,0), (0,10,0), (-10,0,0) → demi-cercle r=10.
    n11_nodes["arc_3pts"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "arc_3pts",
                point1={"x": 10, "y": 0, "z": 0},
                point2={"x": 0, "y": 10, "z": 0},
                point3={"x": -10, "y": 0, "z": 0})],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Length, math.pi * 10,
                      tol=1e-4))
    n11_nodes["polyligne"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "polyligne", ferme=0,
                point=[origin, {"x": 10, "y": 0, "z": 0},
                       {"x": 10, "y": 10, "z": 0}])],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Length, 20.0, tol=1e-6))
    spline_shape_ok = False
    if _n11_add({
        "nodes": [_n4_node(
            "n", "bspline", ferme=0,
            centres=[origin, {"x": 10, "y": 0, "z": 0},
                     {"x": 10, "y": 10, "z": 0}])],
        "edges": [], "output": "n",
    }):
        shp = _n11_last_shape()
        verts = list(shp.Vertexes)
        spline_shape_ok = (
            len(verts) >= 2
            and _close(verts[0].Point.distanceToPoint(
                self._app().Vector(0, 0, 0)), 0.0, tol=1e-4)
            and _close(verts[-1].Point.distanceToPoint(
                self._app().Vector(10, 10, 0)), 0.0, tol=1e-4))
    n11_nodes["bspline"] = spline_shape_ok
    n11_nodes["helice"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "helice", pas_helice=10, hauteur=20,
                rayon=10, angle=0, gauche=0)],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().BoundBox.ZLength, 20.0,
                      tol=1e-3))
    n11_nodes["plan"] = (
        _n11_add({
            "nodes": [_n4_node(
                "n", "plan", longueur=20, largeur=10,
                point=origin, direction=zdir)],
            "edges": [], "output": "n",
        }) and _close(_n11_last_shape().Area, 200.0, tol=1e-4))
    grid = [
        [origin, {"x": 10, "y": 0, "z": 0}],
        [{"x": 0, "y": 10, "z": 0}, {"x": 10, "y": 10, "z": 0}],
    ]
    n11_nodes["bspline_surface"] = (
        _n11_add({
            "nodes": [_n4_node("n", "bspline_surface", centres=grid)],
            "edges": [], "output": "n",
        }) and bool(_n11_last_shape().Faces)
        and _close(_n11_last_shape().Area, 100.0, tol=0.05))
    report["n11_neuf_noeuds"] = all(n11_nodes.values())
    report["n11_neuf_detail"] = n11_nodes
    etat.origin = origin
    etat.zdir = zdir


def n11_ligne_appariement_refus(self, mark, report, etat):
    _close = etat._close  # posé par document.cycle_de_vie_open_part
    _n4_node = etat._n4_node  # posé par noeuds.n4_fonction_graphe
    _volume = etat._volume  # posé par document.cycle_de_vie_open_part
    origin = etat.origin  # posé par noeuds.n11_neuf_noeuds
    zdir = etat.zdir  # posé par noeuds.n11_neuf_noeuds
    mark("n11: une ligne, appariement, trois refus")
    self.new_part("Pièce graphe N011 ligne")
    five = {
        "nodes": [
            _n4_node("s", "serie", depart=5, pas=5, nombre=5),
            _n4_node("c", "cercle", point=origin, direction=zdir),
        ],
        "edges": [{"from": "s", "to": "c", "input": "rayon"}],
        "output": "c",
    }
    tree = self.add_graph_feature(five)
    graphs = [s for s in tree["surfaces"] if s.get("graph")]
    five_obj = (self._require_doc().getObject(graphs[-1]["name"])
                if graphs else None)
    stored = (self.get_graph_feature(graphs[-1]["name"])
              if graphs else {})
    report["n11_une_ligne"] = (
        len(graphs) == 1
        and stored.get("graph", {}).get("output") == "c"
        and stored.get("graph", {}).get("nodes") == five["nodes"])
    report["n11_appariement"] = (
        five_obj is not None
        and len(five_obj.Shape.Edges) == 5)

    mixed = {
        "nodes": [
            _n4_node("mix", "option_liste", op="flatten", liste=[
                {"shape": "boite", "length": 10, "width": 10,
                 "height": 10, "x": 0, "y": 0, "z": 0},
                {"shape": "ligne",
                 "point1": [0, 0, 0], "point2": [10, 0, 0]},
            ]),
        ],
        "edges": [],
        "output": "mix",
    }
    n_surf = len(self.get_tree()["surfaces"])
    n_feat = len(self.get_tree()["features"])
    try:
        self.add_graph_feature(mixed)
        report["n11_refus_mixte"] = False
    except KernelError as exc:
        msg = str(exc)
        report["n11_refus_mixte"] = (
            "Boîte" in msg and "Ligne" in msg
            and len(self.get_tree()["surfaces"]) == n_surf
            and len(self.get_tree()["features"]) == n_feat)

    circle = {
        "nodes": [_n4_node(
            "c", "cercle", rayon=5, point=origin, direction=zdir)],
        "edges": [], "output": "c",
    }
    n_surf = len(self.get_tree()["surfaces"])
    try:
        self.add_graph_feature(circle, mode="cut")
        report["n11_refus_mode"] = False
    except KernelError as exc:
        report["n11_refus_mode"] = (
            "fuse" in str(exc) and "cut" in str(exc)
            and len(self.get_tree()["surfaces"]) == n_surf)

    self.new_part("Pièce graphe N011 nature")
    self.add_rect_sketch(40, 40)
    self.add_pad(10)
    vol_nature = _volume()
    box_graph = {
        "nodes": [_n4_node(
            "b", "boite", longueur=8, largeur=8, hauteur=8,
            ancrage={"x": -4, "y": -4, "z": -1})],
        "edges": [], "output": "b",
    }
    tree = self.add_graph_feature(box_graph, mode="cut")
    graphe_bool = next(f for f in tree["features"] if f.get("graph"))
    vol_cut = _volume()
    line_graph = {
        "nodes": [_n4_node(
            "l", "ligne", point1=origin,
            point2={"x": 10, "y": 0, "z": 0})],
        "edges": [], "output": "l",
    }
    try:
        self.edit_graph_feature(graphe_bool["name"], line_graph)
        report["n11_refus_nature"] = False
    except KernelError as exc:
        report["n11_refus_nature"] = (
            "solide" in str(exc)
            and _close(_volume(), vol_cut)
            and abs(_volume() - vol_nature) > 1.0)


def n11b_libelle_courbe_surface(self, mark, report, etat):
    _n4_node = etat._n4_node  # posé par noeuds.n4_fonction_graphe
    origin = etat.origin  # posé par noeuds.n11_neuf_noeuds
    zdir = etat.zdir  # posé par noeuds.n11_neuf_noeuds
    mark("n11b: libellé Courbe / Surface, et la réédition le met à jour")
    self.new_part("Pièce graphe N011b")
    circle_graph = {
        "nodes": [_n4_node(
            "c", "cercle", rayon=10, point=origin, direction=zdir)],
        "edges": [], "output": "c",
    }
    plane_graph = {
        "nodes": [_n4_node(
            "p", "plan", longueur=20, largeur=10,
            point=origin, direction=zdir)],
        "edges": [], "output": "p",
    }
    tree = self.add_graph_feature(circle_graph)
    curve_line = next(s for s in tree["surfaces"] if s.get("graph"))
    tree = self.edit_graph_feature(curve_line["name"], plane_graph)
    edited = next(
        s for s in tree["surfaces"] if s["name"] == curve_line["name"])
    self.new_part("Pièce graphe N011b surface")
    tree = self.add_graph_feature(plane_graph)
    surf_line = next(s for s in tree["surfaces"] if s.get("graph"))
    report["n11b_libelle"] = (
        curve_line["label"] == "Fonction graphe — Courbe"
        and edited["label"] == "Fonction graphe — Surface"
        and edited["label"] != curve_line["label"]
        and surf_line["label"] == "Fonction graphe — Surface")
