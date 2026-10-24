"""Selftest — assemblage : instances, contraintes, interférences, solveur.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import os
import tempfile


def p10_deux_instances(self, mark, report, etat):
    mark("p10: assemblage — deux instances d'une pièce")
    self.new_part("Pièce à assembler")
    self.add_rect_sketch(20, 20)
    self.add_pad(10)
    asm_part = os.path.join(tempfile.gettempdir(),
                            "freesolid-selftest-part.FCStd")
    self.save_part(asm_part)
    self.new_assembly()
    self.insert_component(asm_part)
    tree = self.insert_component(asm_part)
    report["p10_two_components"] = len(tree["components"]) == 2
    second = tree["components"][1]["name"]
    tree = self.move_component(second, x=30, z=10, yaw=45)
    moved = next(c for c in tree["components"]
                 if c["name"] == second)
    report["p10_move_ok"] = abs(moved["position"][0] - 30) < 1e-9
    meshes = self.tessellate_assembly()
    report["p10_assembly_meshes_ok"] = (
        len(meshes["components"]) == 2
        and all(c["mesh"]["indices"]
                for c in meshes["components"]))
    etat.second = second
    etat.tree = tree


def p10_contrainte_fixe(self, mark, report, etat):
    second = etat.second  # posé par assemblage.p10_deux_instances
    tree = etat.tree  # posé par assemblage.p10_deux_instances
    mark("p10: contrainte fixe — le solveur déplace le composant")
    first_comp = tree["components"][0]["name"]
    report["p10_first_grounded"] = tree["components"][0]["grounded"]
    tree = self.add_joint(first_comp, second,
                          type="fixe", sub1="Face1", sub2="Face1")
    report["p10_joints_listed"] = len(tree.get("joints", ())) >= 2
    comp2 = next(c for c in tree["components"]
                 if c["name"] == second)
    # Il était en (30, 0, 10) yaw 45 — la contrainte fixe doit
    # l'avoir ramené ailleurs.
    report["p10_joint_solved"] = (
        abs(comp2["position"][0] - 30) > 1e-6
        or abs(comp2["position"][2] - 10) > 1e-6
        or abs(comp2["rotation"][0] - 45) > 1e-6)
    asm = self.assembly_tree()
    report["p10_assembly_tree_ok"] = (
        len(asm["components"]) == 2
        and len(asm.get("joints", ())) >= 2)
    solved = self.solve_assembly()
    report["p10_solve_op_ok"] = (
        len(solved["components"]) == 2
        and "joints" in solved)
    # 2 existants + (3 - 1) copies du second = 4 composants.
    arrayed = self.array_component(second, count=3, dx=80)
    report["p10_array_ok"] = len(arrayed["components"]) == 4


def p16_interferences(self, mark, report, etat):
    mark("p16: interférences (les instances se chevauchent)")
    inter = self.check_interference()
    report["p16_interference_found"] = (
        len(inter["interferences"]) >= 1)


def spike_solveur_assemblage(self, mark, report, etat):
    mark("spike: solveur d'assemblage headless (rapport)")
    report["spike_assembly"] = self.spike_assembly()
    import json
    print("selftest> spike assemblage : " + json.dumps(
        report["spike_assembly"], ensure_ascii=False), flush=True)
