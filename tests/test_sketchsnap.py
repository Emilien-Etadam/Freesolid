"""Accrochages d'un tracé d'esquisse : forme de ``snaps`` (sans FreeCAD)."""
import pytest

from engine.kernel import KernelError
from engine.ops import BY_NAME
from engine.sketchsnap import (
    ROLES, Target, fits, parse_snaps, relations, snap_positions, targets_of,
)

LINE, ARC, CIRCLE, POINT = ("Part::GeomLineSegment", "Part::GeomArcOfCircle",
                            "Part::GeomCircle", "Part::GeomPoint")
TYPES = {0: LINE, 1: ARC, 2: CIRCLE, 3: POINT, -3: LINE}


def type_of(geo):
    return TYPES[geo]


def test_chaque_trace_accrochable_declare_snaps():
    for op in ROLES:
        assert BY_NAME[op].req.optional.get("snaps") is dict, op


def test_une_cible_point_nomme_geo_et_point():
    parsed = parse_snaps("sketch_add_line", {
        "start": {"geo": 3, "point": 3}, "end": {"geo": -1, "point": 1}})
    assert parsed == {"start": Target("point", 3, point=3),
                      "end": Target("point", -1, point=1)}


def test_milieu_quadrant_sur_et_croisement():
    parsed = parse_snaps("sketch_add_line", {
        "start": {"kind": "midpoint", "geo": 0},
        "end": {"kind": "quadrant", "geo": 2, "quadrant": 3}})
    assert parsed["start"] == Target("midpoint", 0)
    assert parsed["end"] == Target("quadrant", 2, quadrant=3)
    parsed = parse_snaps("sketch_add_point", {
        "at": {"kind": "intersection", "geos": [0, -3]}})
    assert parsed["at"] == Target("intersection", 0, other=-3)
    assert parse_snaps("sketch_add_circle", {
        "center": {"kind": "on", "geo": 1}})["center"] == Target("on", 1)


def test_un_role_absent_ou_nul_n_accroche_rien():
    assert parse_snaps("sketch_add_line", {}) == {}
    assert parse_snaps("sketch_add_line", {"start": None}) == {}


def test_les_points_poses_sur_un_cercle_forment_une_liste():
    parsed = parse_snaps("sketch_add_circle", {
        "center": {"geo": 0, "point": 1},
        "on": [{"geo": 1, "point": 2}, {"geo": -3, "point": 1}]})
    assert parsed["on"] == [Target("point", 1, point=2),
                            Target("point", -3, point=1)]
    assert [(role, t.geo) for role, t in targets_of(parsed)] == [
        ("center", 0), ("on", 1), ("on", -3)]


@pytest.mark.parametrize("op, snaps, message", [
    ("sketch_add_point", {"start": {"geo": 0, "point": 1}},
     "accrochage inconnu : start"),
    ("sketch_add_line", {"start": {"geo": 0}},
     "accrochage « start » : cible invalide"),
    ("sketch_add_line", {"start": {"geo": 0, "point": 4}},
     "accrochage « start » : cible invalide"),
    ("sketch_add_line", {"start": {"geo": True, "point": 1}},
     "accrochage « start » : cible invalide"),
    ("sketch_add_line", {"start": {"geo": 0, "point": 1, "x": 2}},
     "accrochage « start » : cible invalide"),
    ("sketch_add_circle", {"on": {"geo": 0, "point": 1}},
     "accrochage « on » : cible invalide"),
    ("sketch_add_line", {"direction": "horizontal"},
     "accrochage inconnu : direction"),
    ("sketch_add_line", {"end": {"kind": "milieu", "geo": 0}},
     "accrochage « end » : cible invalide"),
    ("sketch_add_line", {"end": {"kind": "quadrant", "geo": 2,
                                 "quadrant": 4}},
     "accrochage « end » : cible invalide"),
    ("sketch_add_line", {"end": {"kind": "intersection", "geos": [1, 1]}},
     "accrochage « end » : cible invalide"),
    ("sketch_add_line", {"end": {"kind": "on", "geo": 0, "point": 1}},
     "accrochage « end » : cible invalide"),
    # Un point posé sur un cercle, le centre d'un rectangle : un point
    # d'esquisse, jamais un milieu.
    ("sketch_add_circle", {"on": [{"kind": "midpoint", "geo": 0}]},
     "accrochage « on » : cible invalide"),
    ("sketch_add_rectangle", {"center": {"kind": "on", "geo": 0}},
     "accrochage « center » : cible invalide"),
])
def test_une_forme_inattendue_est_refusee(op, snaps, message):
    with pytest.raises(KernelError, match="^" + message + "$"):
        parse_snaps(op, snaps)


def test_les_points_visables_suivent_le_type_de_geometrie():
    assert snap_positions("Part::GeomPoint") == (1,)
    assert snap_positions("Part::GeomCircle") == (3,)
    assert snap_positions("Part::GeomArcOfCircle") == (1, 2, 3)
    # Spline, conique : ses deux bouts.
    assert snap_positions("Part::GeomBSplineCurve") == (1, 2)


@pytest.mark.parametrize("target, ok", [
    (Target("point", 2, point=3), True),
    (Target("point", 2, point=1), False),
    (Target("midpoint", 0), True),
    (Target("midpoint", 1), True),
    (Target("midpoint", 2), False),
    (Target("quadrant", 1, quadrant=0), True),
    (Target("quadrant", 0, quadrant=0), False),
    (Target("on", 2), True),
    (Target("on", 3), False),
    (Target("intersection", 0, other=-3), True),
    (Target("intersection", 0, other=3), False),
])
def test_une_cible_convient_a_ce_qu_elle_vise(target, ok):
    assert fits(target, type_of) is ok


def test_les_relations_qui_posent_le_point():
    # Le départ (5, 1) d'une nouvelle ligne.
    assert relations(Target("point", 2, point=3), 5, 1, type_of) == [
        ("Coincident", 5, 1, 2, 3)]
    assert relations(Target("midpoint", 0), 5, 1, type_of) == [
        ("Symmetric", 0, 1, 0, 2, 5, 1)]
    # Le milieu d'un arc : sur l'arc, Sketcher n'a pas mieux.
    assert relations(Target("midpoint", 1), 5, 1, type_of) == [
        ("PointOnObject", 5, 1, 1)]
    assert relations(Target("quadrant", 2, quadrant=1), 5, 1, type_of) == [
        ("PointOnObject", 5, 1, 2), ("Vertical", 5, 1, 2, 3)]
    assert relations(Target("quadrant", 2, quadrant=2), 5, 1, type_of)[1] == (
        "Horizontal", 5, 1, 2, 3)
    assert relations(Target("on", -3), 5, 1, type_of) == [
        ("PointOnObject", 5, 1, -3)]
    assert relations(Target("intersection", 0, other=2), 5, 1, type_of) == [
        ("PointOnObject", 5, 1, 0), ("PointOnObject", 5, 1, 2)]
