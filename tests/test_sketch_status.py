"""État de définition des entités d'esquisse — sans FreeCAD."""

from engine.sketchstatus import (
    FULL, OVER, UNDER, entity_status, sketch_definition)


def test_tout_contraint_sans_parametre_libre():
    assert entity_status(2, [], [[0], [1]], [], []) == [FULL, FULL]


def test_parametre_libre_rend_l_entite_sous_contrainte():
    status = entity_status(3, [(1, 1), (1, 2)], [], [], [])
    assert status == [FULL, UNDER, FULL]


def test_contrainte_redondante_numerotee_a_partir_de_un():
    # La contrainte n°2 (index 1) touche les géométries 0 et 2.
    status = entity_status(3, [], [[1], [0, 2]], [], [2])
    assert status == [OVER, FULL, OVER]


def test_le_conflit_l_emporte_sur_le_libre():
    status = entity_status(2, [(0, 1)], [[0, None, -1]], [1], [])
    assert status == [OVER, FULL]


def test_indices_hors_bornes_ignores():
    assert entity_status(1, [(5, 1), (-1, 1)], [[9]], [7], [1]) == [FULL]


def test_resume_de_l_esquisse():
    assert sketch_definition([FULL, FULL]) == FULL
    assert sketch_definition([FULL, UNDER]) == UNDER
    assert sketch_definition([UNDER, OVER]) == OVER
    assert sketch_definition([FULL], solver_code=-3) == OVER
    assert sketch_definition([]) == FULL


def test_resume_lu_sur_l_objet_esquisse():
    from engine.sketchstatus import definition_from_flags
    assert definition_from_flags(True) == FULL
    assert definition_from_flags(False) == UNDER
    assert definition_from_flags(True, redundant=[3]) == OVER
    assert definition_from_flags(False, conflicting=[1]) == OVER
    assert definition_from_flags(True, malformed=[2]) == OVER
