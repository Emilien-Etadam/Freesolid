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
