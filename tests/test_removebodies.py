"""Supprimer des corps : ce que la fonction ôte, sans FreeCAD."""

from engine.removebodies import doomed_solids, removal_plan

ALIVE = {"bodies": {"Body": 2, "Body001": 1}, "surfaces": ["Surface", "Surface001"]}


def test_un_corps_entier_et_une_surface():
    plan = removal_plan([{"name": "Body001"}, {"name": "Surface"}], ALIVE)
    assert plan == {"bodies": ["Body001"], "solids": {}, "surfaces": ["Surface"]}


def test_un_solide_d_un_corps_qui_en_garde_plusieurs():
    plan = removal_plan([{"name": "Body", "solid": 1}], ALIVE)
    assert plan == {"bodies": [], "solids": {"Body": [1]}, "surfaces": []}


def test_tous_les_solides_font_partir_le_corps_entier():
    plan = removal_plan([{"name": "Body", "solid": 0},
                         {"name": "Body", "solid": 1}], ALIVE)
    assert plan["bodies"] == ["Body"] and plan["solids"] == {}


def test_garder_ote_tout_le_reste():
    plan = removal_plan([{"name": "Body", "solid": 0}], ALIVE, keep=True)
    assert plan == {"bodies": ["Body001"], "solids": {"Body": [1]},
                    "surfaces": ["Surface", "Surface001"]}
    plan = removal_plan([{"name": "Body"}, {"name": "Surface001"}], ALIVE,
                        keep=True)
    assert plan == {"bodies": ["Body001"], "solids": {},
                    "surfaces": ["Surface"]}


def test_un_solide_retenu_se_retrouve_par_ses_origines():
    origins = [{"Sketch|g1", "Sketch|g2"}, {"Sketch|g5", "Sketch|g6"}]
    assert doomed_solids(origins, [["Sketch|g5", "Sketch|g6"]]) == {1}
    # Une origine qu'aucun solide n'a : rien ne part.
    assert doomed_solids(origins, [["Sketch001|g1"]]) == set()


def test_les_deux_moities_d_un_solide_coupe_partent_ensemble():
    origins = [{"Sketch|g1", "Pocket|f1"}, {"Sketch|g1", "Pocket|f2"},
               {"Sketch|g9"}]
    assert doomed_solids(origins, [["Sketch|g1"]]) == {0, 1}
