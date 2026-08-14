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
    # face OU edges : seuls le rayon/la distance sont obligatoires.
    assert protocol.OPS["add_fillet"] == ("radius",)
    assert protocol.OPS["add_chamfer"] == ("size",)
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
    # value | expr | name tous optionnels : renommer sans changer la valeur.
    assert protocol.OPS["sketch_set_dim"] == ("sketch", "dim")
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


def test_p2_ops_declare_their_required_params():
    assert protocol.OPS["add_revolution"] == ()      # angle, sketch en option
    assert protocol.OPS["add_groove"] == ()
    assert protocol.OPS["add_mirror"] == ()          # plane en option
    assert protocol.OPS["add_linear_pattern"] == ("length", "count")
    assert protocol.OPS["add_polar_pattern"] == ("count",)
    assert protocol.OPS["add_thickness"] == ("face", "thickness")
    assert protocol.OPS["add_draft"] == ("face", "angle")


def test_pad_accepts_direction_options():
    op, params = protocol.validate_request(
        {"op": "add_pad",
         "params": {"length": 10, "reversed": True, "midplane": True}})
    assert params["midplane"] is True


def test_p3_ops_declare_their_required_params():
    assert protocol.OPS["sketch_add_arc"] == (
        "sketch", "cx", "cy", "r", "a1", "a2")
    assert protocol.OPS["sketch_add_slot"] == (
        "sketch", "x1", "y1", "x2", "y2", "width")
    assert protocol.OPS["sketch_add_polygon"] == (
        "sketch", "cx", "cy", "x", "y", "sides")
    assert protocol.OPS["sketch_fillet"] == (
        "sketch", "geo1", "geo2", "x1", "y1", "x2", "y2", "radius")
    assert protocol.OPS["sketch_trim"] == ("sketch", "geo", "x", "y")
    assert protocol.OPS["sketch_constrain"] == ("sketch", "kind", "geo1")


def test_dim_accepts_second_entity():
    op, params = protocol.validate_request(
        {"op": "sketch_dim",
         "params": {"sketch": "Sketch", "geo": 0, "geo2": 1,
                    "point": 1, "point2": 2}})
    assert params["geo2"] == 1


def test_pack_edges_maps_segments_to_edges_by_construction():
    packed = protocol.pack_edges([
        (0, [(0, 0, 0), (1, 0, 0)]),               # segment unique
        (4, [(0, 0, 1), (1, 0, 1), (1, 1, 1)]),    # polyligne : 2 segments
        (9, [(5, 5, 5)]),                          # dégénérée : ignorée
    ])
    assert packed["indices"] == [0, 1, 2, 3, 3, 4]
    assert packed["groups"] == [
        {"edgeId": 0, "start": 0, "count": 2},
        {"edgeId": 4, "start": 2, "count": 4},
    ]
    cursor = 0
    for group in packed["groups"]:
        assert group["start"] == cursor
        cursor += group["count"]
    assert cursor == len(packed["indices"])
    assert all(isinstance(v, float) for v in packed["positions"])


def test_edge_ops_declared():
    assert protocol.OPS["tessellate_edges"] == ()
    protocol.validate_request(
        {"op": "add_fillet", "params": {"radius": 3, "edges": [1, 5, 7]}})
    protocol.validate_request(
        {"op": "add_chamfer", "params": {"size": 2, "face": 4}})


def test_hole_rename_and_atomic_edit_ops():
    assert protocol.OPS["add_hole"] == ("diameter",)
    assert protocol.OPS["rename"] == ("feature", "label")
    assert protocol.OPS["set_params"] == ("feature", "values")
    protocol.validate_request(
        {"op": "add_hole",
         "params": {"diameter": 6, "through": True, "cut": "lamage",
                    "cut_diameter": 11, "cut_depth": 3}})


def test_parametric_ops_declared():
    assert protocol.OPS["set_variable"] == ("name", "value")
    assert protocol.OPS["delete_variable"] == ("name",)
    assert protocol.OPS["list_variables"] == ()
    assert protocol.OPS["sketch_constraints"] == ("sketch",)
    assert protocol.OPS["sketch_delete_constraint"] == (
        "sketch", "constraint")
    protocol.validate_request(
        {"op": "sketch_set_dim",
         "params": {"sketch": "Sketch", "dim": 3,
                    "name": "largeur", "expr": "Variables.coef * 2"}})
    protocol.validate_request(
        {"op": "sketch_constrain",
         "params": {"sketch": "Sketch", "kind": "symmetric",
                    "geo1": 0, "point1": 1, "geo2": 1, "point2": 1,
                    "geo3": 2}})


def test_phase_b_ops_declared():
    assert protocol.OPS["add_datum_plane"] == ()
    assert protocol.OPS["add_loft"] == ("sketches",)
    assert protocol.OPS["add_sweep"] == ("profile", "spine")
    assert protocol.OPS["add_helix"] == ("pitch", "height")
    protocol.validate_request(
        {"op": "add_loft",
         "params": {"sketches": ["Sketch", "Sketch001"],
                    "subtractive": True}})
    protocol.validate_request(
        {"op": "sketch_start", "params": {"datum": "DatumPlane"}})


def test_multibody_ops_declared():
    assert protocol.OPS["add_body"] == ()
    assert protocol.OPS["set_active_body"] == ("body",)
    assert protocol.OPS["add_boolean"] == ("tool",)
    protocol.validate_request(
        {"op": "add_boolean", "params": {"tool": "Body001", "type": "cut"}})


def test_joint_ops_declared():
    assert protocol.OPS["add_joint"] == ("component1", "component2")
    assert protocol.OPS["solve_assembly"] == ()
    protocol.validate_request(
        {"op": "add_joint",
         "params": {"component1": "Component", "component2": "Component001",
                    "type": "pivot", "sub1": "Face3", "sub2": "Face1"}})


def test_assembly_ops_declared():
    assert protocol.OPS["new_assembly"] == ()
    assert protocol.OPS["insert_component"] == ("path",)
    assert protocol.OPS["move_component"] == ("component",)
    assert protocol.OPS["assembly_tree"] == ()
    assert protocol.OPS["tessellate_assembly"] == ()
    protocol.validate_request(
        {"op": "move_component",
         "params": {"component": "Component", "x": 30, "yaw": 45}})


def test_evaluate_and_spike_ops_declared():
    assert protocol.OPS["mass_properties"] == ()
    assert protocol.OPS["measure"] == ("a_kind", "a_id", "b_kind", "b_id")
    assert protocol.OPS["spike_assembly"] == ()
    protocol.validate_request(
        {"op": "measure",
         "params": {"a_kind": "face", "a_id": 2,
                    "b_kind": "edge", "b_id": 7}})


def test_surface_and_drawing_ops_declared():
    assert protocol.OPS["surface_extrude"] == ("length",)
    assert protocol.OPS["surface_revolve"] == ()
    assert protocol.OPS["surface_loft"] == ("sketches",)
    assert protocol.OPS["surface_sew"] == ("surfaces",)
    assert protocol.OPS["surface_thicken"] == ("surface", "thickness")
    assert protocol.OPS["add_curve3d"] == ("points",)
    assert protocol.OPS["make_drawing"] == ("path",)
    protocol.validate_request(
        {"op": "add_curve3d",
         "params": {"points": [[0, 0, 0], [0, 0, 30]], "spline": False}})
    protocol.validate_request(
        {"op": "make_drawing",
         "params": {"path": "/tmp/piece.dxf", "dims": True,
                    "section": "Y", "scale": 2}})


def test_convert_text_interference_ops_declared():
    assert protocol.OPS["sketch_convert"] == ("sketch",)
    assert protocol.OPS["add_text"] == ("text", "face")
    assert protocol.OPS["check_interference"] == ()
    protocol.validate_request(
        {"op": "add_text",
         "params": {"text": "REF-001", "face": 5, "size": 8,
                    "depth": 1, "emboss": False}})
    protocol.validate_request(
        {"op": "add_joint",
         "params": {"component1": "A", "component2": "B",
                    "type": "engrenages", "sub1": "Face1", "sub2": "Face1",
                    "distance": 20, "distance2": 10}})


def test_comfort_ops_declared():
    assert protocol.OPS["sketch_add_spline"] == ("sketch", "points")
    assert protocol.OPS["sketch_add_ellipse"] == (
        "sketch", "cx", "cy", "rx", "ry")
    assert protocol.OPS["sketch_mirror"] == ("sketch", "geos", "axis")
    assert protocol.OPS["sketch_array"] == (
        "sketch", "geos", "dx", "dy", "cols", "rows")
    assert protocol.OPS["sketch_offset"] == ("sketch", "geos", "distance")
    assert protocol.OPS["array_component"] == ("component", "count")
    protocol.validate_request(
        {"op": "sketch_offset",
         "params": {"sketch": "Sketch", "geos": [0, 1, 2, 3],
                    "distance": 5}})
    protocol.validate_request(
        {"op": "sketch_offset",
         "params": {"sketch": "Sketch", "geos": [0], "distance": 5.0,
                    "reversed": True}})
    protocol.validate_request(
        {"op": "add_joint",
         "params": {"component1": "A", "component2": "B", "type": "pivot",
                    "sub1": "Face1", "sub2": "Face2",
                    "angle_min": -45, "angle_max": 45}})


def test_preview_wraps_an_op_and_its_params():
    op, params = protocol.validate_request(
        {"op": "preview",
         "params": {"op": "add_pad", "params": {"length": 10}}})
    assert params["op"] == "add_pad"
    assert params["params"] == {"length": 10}


def test_pocket_accepts_length_or_through():
    protocol.validate_request({"op": "add_pocket", "params": {"length": 5}})
    protocol.validate_request({"op": "add_pocket", "params": {"through": True}})
    protocol.validate_request({"op": "add_pocket"})


# -- P008 : snapshot, déclarations manquantes, types/bornes, preview ------

def test_ops_snapshot_keys():
    assert sorted(protocol.OPS) == [
        "add_body",
        "add_boolean",
        "add_chamfer",
        "add_curve3d",
        "add_datum_plane",
        "add_draft",
        "add_fillet",
        "add_groove",
        "add_helix",
        "add_hole",
        "add_joint",
        "add_linear_pattern",
        "add_loft",
        "add_mirror",
        "add_pad",
        "add_pocket",
        "add_polar_pattern",
        "add_rect_sketch",
        "add_revolution",
        "add_sweep",
        "add_text",
        "add_thickness",
        "array_component",
        "assembly_tree",
        "check_interference",
        "delete_feature",
        "delete_variable",
        "export_part",
        "get_params",
        "get_tree",
        "insert_component",
        "list_variables",
        "make_drawing",
        "mass_properties",
        "measure",
        "move_component",
        "new_assembly",
        "new_part",
        "open_part",
        "ping",
        "preview",
        "redo",
        "rename",
        "save_part",
        "selftest",
        "set_active_body",
        "set_param",
        "set_params",
        "set_tip",
        "set_variable",
        "sketch_add_arc",
        "sketch_add_circle",
        "sketch_add_ellipse",
        "sketch_add_line",
        "sketch_add_polygon",
        "sketch_add_slot",
        "sketch_add_spline",
        "sketch_array",
        "sketch_constrain",
        "sketch_constraints",
        "sketch_convert",
        "sketch_delete_constraint",
        "sketch_delete_geo",
        "sketch_dim",
        "sketch_edit",
        "sketch_fillet",
        "sketch_finish",
        "sketch_mirror",
        "sketch_move",
        "sketch_offset",
        "sketch_set_dim",
        "sketch_start",
        "sketch_state",
        "sketch_toggle_construction",
        "sketch_trim",
        "solve_assembly",
        "spike_assembly",
        "surface_extrude",
        "surface_loft",
        "surface_revolve",
        "surface_sew",
        "surface_thicken",
        "tessellate",
        "tessellate_assembly",
        "tessellate_edges",
        "tip_to_end",
        "undo",
    ]


def test_audit_missing_op_declarations():
    assert protocol.OPS["set_param"] == ("feature", "prop", "value")
    assert protocol.OPS["sketch_edit"] == ("feature",)
    assert protocol.OPS["sketch_state"] == ("sketch",)
    assert protocol.OPS["sketch_delete_geo"] == ("sketch", "geo")


def test_pack_edges_empty():
    assert protocol.pack_edges([]) == {
        "positions": [], "indices": [], "groups": []}


def test_float_param_accepts_int_refuses_bool_and_str():
    protocol.validate_request({"op": "add_pad", "params": {"length": 10}})
    protocol.validate_request({"op": "add_pad", "params": {"length": 10.5}})
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "add_pad", "params": {"length": "x"}})
    assert str(excinfo.value) == 'paramètre length : nombre attendu, reçu "x"'
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(
            {"op": "add_pad", "params": {"length": True}})


def test_int_count_bounds_and_bool_refused():
    protocol.validate_request(
        {"op": "add_polar_pattern", "params": {"count": 1}})
    protocol.validate_request(
        {"op": "add_polar_pattern", "params": {"count": 10000}})
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "add_polar_pattern", "params": {"count": 0}})
    assert "count" in str(excinfo.value)
    assert "1" in str(excinfo.value) and "10000" in str(excinfo.value)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(
            {"op": "add_polar_pattern", "params": {"count": 10001}})
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(
            {"op": "add_polar_pattern", "params": {"count": True}})
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(
            {"op": "add_polar_pattern", "params": {"count": 1.5}})


def test_empty_feature_name_refused():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "get_params", "params": {"feature": ""}})
    assert "feature" in str(excinfo.value)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_request(
            {"op": "get_params", "params": {"feature": "  "}})


def test_set_param_value_stays_untyped():
    protocol.validate_request(
        {"op": "set_param",
         "params": {"feature": "Pad", "prop": "Length", "value": 12}})
    protocol.validate_request(
        {"op": "set_param",
         "params": {"feature": "Pad", "prop": "Length",
                    "value": "Variables.epaisseur * 2"}})


def test_preview_unknown_nested_op_refused():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "preview",
             "params": {"op": "no_such_op", "params": {}}})
    assert "inconnue" in str(excinfo.value)


def test_preview_of_preview_refused():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "preview",
             "params": {"op": "preview",
                        "params": {"op": "add_pad",
                                   "params": {"length": 1}}}})
    assert str(excinfo.value) == "preview d'un preview refusé"


def test_preview_nested_typed_params_refused():
    protocol.validate_request(
        {"op": "preview",
         "params": {"op": "add_pad", "params": {"length": 10}}})
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_request(
            {"op": "preview",
             "params": {"op": "add_pad", "params": {"length": "x"}}})
    assert str(excinfo.value) == 'paramètre length : nombre attendu, reçu "x"'
