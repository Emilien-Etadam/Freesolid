"""Solides d'un corps : rapprochement par origines, noms, réglages."""

from engine import protocol
from engine.bodysolids import match_entries, set_entry, solid_rows

LEFT = {"Sketch|g1;SKT", "Sketch|g2;SKT", "Sketch|g3;SKT", "Sketch|g4;SKT"}
RIGHT = {"Sketch|g5;SKT", "Sketch|g6;SKT", "Sketch|g7;SKT", "Sketch|g8;SKT"}


TWO = ["Extrusion", "Extrusion"]


def test_unset_solids_are_numbered_after_their_feature():
    rows = solid_rows(TWO, [], match_entries([LEFT, RIGHT], []))
    assert [r["label"] for r in rows] == ["Extrusion[1]", "Extrusion[2]"]
    assert not any(r["color"] or r["hidden"] for r in rows)


def test_a_solid_alone_with_its_feature_name_has_no_number():
    rows = solid_rows(["Congé", "Extrusion"], [],
                      match_entries([LEFT, RIGHT], []))
    assert [r["label"] for r in rows] == ["Congé", "Extrusion"]


def test_a_setting_follows_its_solid_when_the_order_changes():
    entries = set_entry([], [None, None], 1, RIGHT, color="#cc3333")
    matched = match_entries([RIGHT, LEFT], entries)
    assert matched == [0, None]
    rows = solid_rows(TWO, entries, matched)
    assert rows[0]["color"] == "#cc3333" and rows[1]["color"] is None


def test_a_fillet_keeps_the_solid_recognised():
    entries = set_entry([], [None, None], 0, LEFT, hidden=True)
    filleted = (LEFT - {"Sketch|g1;SKT"}) | {"Fillet|Face3"}
    assert match_entries([filleted, RIGHT], entries) == [0, None]


def test_both_halves_of_a_cut_solid_inherit_its_settings():
    entries = set_entry([], [None, None], 1, RIGHT, label="Bloc",
                        color="#3366cc")
    half_a = {"Sketch|g5;SKT", "Sketch|g7;SKT", "Sketch|g8;SKT", "Cut|a"}
    half_b = {"Sketch|g5;SKT", "Sketch|g7;SKT", "Sketch|g6;SKT", "Cut|b"}
    matched = match_entries([LEFT, half_a, half_b], entries)
    assert matched == [None, 0, 0]
    rows = solid_rows(["Extrusion", "Coupe", "Coupe"], entries, matched)
    assert [r["label"] for r in rows] == ["Extrusion", "Bloc[1]", "Bloc[2]"]
    assert rows[1]["color"] == rows[2]["color"] == "#3366cc"


def test_setting_one_half_gives_it_its_own_entry():
    entries = set_entry([], [None], 0, RIGHT, color="#3366cc")
    half_a = {"Sketch|g5;SKT", "Sketch|g7;SKT", "Sketch|g8;SKT", "Cut|a"}
    half_b = {"Sketch|g5;SKT", "Sketch|g7;SKT", "Sketch|g6;SKT", "Cut|b"}
    matched = match_entries([half_a, half_b], entries)
    entries = set_entry(entries, matched, 0, half_a, color="#33cc66")
    rows = solid_rows(["Coupe", "Coupe"], entries,
                      match_entries([half_a, half_b], entries))
    assert [r["color"] for r in rows] == ["#33cc66", "#3366cc"]


def test_clearing_every_setting_drops_the_entry():
    entries = set_entry([], [None, None], 0, LEFT, color="#cc3333")
    entries = set_entry(entries, match_entries([LEFT, RIGHT], entries), 0,
                        LEFT, color="")
    assert entries == []


def test_solid_is_an_optional_integer_of_the_body_ops():
    for op, params in (
            ("set_body_color", {"body": "Body", "color": "#cc3333"}),
            ("set_hidden", {"objects": ["Body"], "hidden": True}),
            ("rename", {"feature": "Body", "label": "Bloc"})):
        protocol.validate_request({"op": op, "params": dict(params)})
        protocol.validate_request(
            {"op": op, "params": {**params, "solid": 1}})
        try:
            protocol.validate_request(
                {"op": op, "params": {**params, "solid": "1"}})
        except protocol.ProtocolError:
            continue
        raise AssertionError(op + " accepte un solide qui n'est pas un entier")
