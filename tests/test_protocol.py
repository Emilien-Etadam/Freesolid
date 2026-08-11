"""Engine wire protocol — runs without FreeCAD."""

import pytest

from engine import protocol


# -- validation ----------------------------------------------------------

def test_valid_request_roundtrips():
    op, params = protocol.validate_request(
        {"op": "add_rect_sketch", "params": {"width": 100, "height": 60}})
    assert op == "add_rect_sketch"
    assert params == {"width": 100, "height": 60}


def test_missing_params_are_named():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request({"op": "add_rect_sketch",
                                   "params": {"width": 100}})
    assert "height" in str(excinfo.value)


@pytest.mark.parametrize("payload", [
    None, [], "x",
    {"op": "no_such_op"},
    {"op": "ping", "params": []},
])
def test_malformed_requests_raise(payload):
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(payload)


def test_paramless_ops_accept_absent_params():
    for op in ("ping", "selftest", "new_part", "get_tree", "tessellate"):
        assert protocol.validate_request({"op": op})[0] == op


def test_envelopes():
    assert protocol.ok(1) == {"ok": True, "result": 1}
    assert protocol.err("boom") == {"ok": False, "error": "boom"}
    assert protocol.err("boom", "try X")["hint"] == "try X"


# -- mesh packing --------------------------------------------------------

def _two_triangles():
    # Face 0: one triangle; face 7: one triangle with its own local indices.
    return [
        (0, [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)]),
        (7, [(0, 0, 1), (1, 0, 1), (0, 1, 1)], [(0, 1, 2)]),
    ]


def test_pack_mesh_rebases_indices_per_face():
    mesh = protocol.pack_mesh(_two_triangles())
    assert mesh["indices"] == [0, 1, 2, 3, 4, 5]
    assert len(mesh["positions"]) == 6 * 3


def test_pack_mesh_groups_map_faces_by_construction():
    # The picking contract: every index range belongs to exactly one face.
    mesh = protocol.pack_mesh(_two_triangles())
    assert mesh["groups"] == [
        {"faceId": 0, "start": 0, "count": 3},
        {"faceId": 7, "start": 3, "count": 3},
    ]


def test_pack_mesh_groups_are_contiguous_and_complete():
    mesh = protocol.pack_mesh(_two_triangles())
    cursor = 0
    for group in mesh["groups"]:
        assert group["start"] == cursor
        cursor += group["count"]
    assert cursor == len(mesh["indices"])


def test_pack_mesh_empty():
    assert protocol.pack_mesh([]) == {
        "positions": [], "indices": [], "groups": []}


def test_pack_mesh_coerces_to_plain_floats():
    # Payload must be JSON-serializable: no Vector objects may leak through.
    mesh = protocol.pack_mesh([(0, [(1, 2, 3)], [])])
    assert all(isinstance(v, float) for v in mesh["positions"])


def test_m1_ops_declare_their_required_params():
    # Both optional: no length means « à travers tout ».
    assert protocol.OPS["add_pocket"] == ()
    assert protocol.OPS["add_fillet"] == ("face", "radius")
    assert protocol.OPS["add_chamfer"] == ("face", "size")
    assert protocol.OPS["save_part"] == ("path",)
    assert protocol.OPS["open_part"] == ("path",)
    assert protocol.OPS["get_params"] == ("feature",)
    assert protocol.OPS["set_tip"] == ("feature",)
    assert protocol.OPS["tip_to_end"] == ()
    assert protocol.OPS["delete_feature"] == ("feature",)


def test_sketch_face_param_stays_optional():
    # The viewport sends `face` only when a face is selected; the plane
    # sketch must keep working without it.
    op, params = protocol.validate_request(
        {"op": "add_rect_sketch",
         "params": {"width": 40, "height": 20, "face": 5}})
    assert params["face"] == 5
    protocol.validate_request(
        {"op": "add_rect_sketch", "params": {"width": 40, "height": 20}})


def test_m2_sketch_ops_declare_their_required_params():
    assert protocol.OPS["sketch_add_line"] == (
        "sketch", "x1", "y1", "x2", "y2")
    assert protocol.OPS["sketch_add_circle"] == ("sketch", "cx", "cy", "r")
    assert protocol.OPS["sketch_move"] == ("sketch", "geo", "point", "x", "y")
    assert protocol.OPS["sketch_set_dim"] == ("sketch", "dim", "value")
    assert protocol.OPS["sketch_dim"] == ("sketch", "geo")   # value optional
    assert protocol.OPS["sketch_start"] == ()                # face optional
    assert protocol.OPS["sketch_finish"] == ("sketch",)


def test_p1_ops_declare_their_required_params():
    assert protocol.OPS["undo"] == ()
    assert protocol.OPS["redo"] == ()
    assert protocol.OPS["export_part"] == ("path",)
    assert protocol.OPS["sketch_toggle_construction"] == ("sketch", "geo")


def test_sketch_start_accepts_named_plane():
    op, params = protocol.validate_request(
        {"op": "sketch_start", "params": {"plane": "XZ"}})
    assert params["plane"] == "XZ"


def test_pocket_accepts_length_or_through():
    protocol.validate_request({"op": "add_pocket", "params": {"length": 5}})
    protocol.validate_request({"op": "add_pocket", "params": {"through": True}})
    protocol.validate_request({"op": "add_pocket"})
