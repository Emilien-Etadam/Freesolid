"""Commentaires, propriétés du fichier, historique — parties pures."""
from engine.docprops import clean_meta, undo_steps


def test_undo_steps_strip_the_transaction_prefix():
    assert undo_steps(["freesolid-add_pad", "freesolid-set_comment",
                       "Autre"]) == ["add_pad", "set_comment", "Autre"]
    assert undo_steps(None) == []


def test_clean_meta_drops_empty_names_and_values():
    assert clean_meta({" Référence ": " FS-1 ", "": "x", "Vide": "",
                       "Nul": None}) == {"Référence": "FS-1"}
