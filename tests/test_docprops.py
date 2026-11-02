"""Commentaires, propriétés du fichier, historique — parties pures."""
from engine.docprops import (
    body_before, clean_meta, session_steps, transaction_name, undo_steps,
)


def test_undo_steps_strip_the_transaction_prefix():
    assert undo_steps(["freesolid-add_pad", "freesolid-set_comment",
                       "Autre"]) == ["add_pad", "set_comment", "Autre"]
    assert undo_steps(None) == []


def test_a_sketch_session_marks_its_transactions():
    assert transaction_name("add_pad") == "freesolid-add_pad"
    assert transaction_name("sketch_add_line", 3) == "freesolid-sketch_add_line@3"
    # L'historique montre l'op, sans la marque de la session.
    assert undo_steps([transaction_name("sketch_drop", 12)]) == ["sketch_drop"]


def test_ctrl_z_in_a_sketch_only_counts_its_own_steps():
    names = [transaction_name("sketch_drop", 4),
             transaction_name("sketch_add_line", 4),
             transaction_name("sketch_start", 3),   # l'esquisse elle-même
             transaction_name("sketch_add_line", 4),
             "Autre@4"]
    assert session_steps(names, 4) == 2
    assert session_steps(names, 3) == 0
    # « @14 » n'est pas « @4 ».
    assert session_steps([transaction_name("sketch_add_line", 14)], 4) == 0
    assert session_steps(None, 1) == 0


def test_the_transaction_keeps_the_body_active_before_the_op():
    name = transaction_name("add_pad", 7, "Body001")
    assert name == "freesolid-add_pad#Body001@7"
    assert body_before(name) == "Body001"
    assert body_before(transaction_name("add_pad", body="Body")) == "Body"
    # L'historique et Ctrl+Z dans l'esquisse n'en voient rien.
    assert undo_steps([name]) == ["add_pad"]
    assert session_steps([name], 7) == 1
    assert body_before(transaction_name("add_pad")) is None
    assert body_before("Autre#Body") is None
    assert body_before(None) is None


def test_clean_meta_drops_empty_names_and_values():
    assert clean_meta({" Référence ": " FS-1 ", "": "x", "Vide": "",
                       "Nul": None}) == {"Référence": "FS-1"}
