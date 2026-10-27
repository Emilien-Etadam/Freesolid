"""Accrochages d'un tracé d'esquisse : forme de ``snaps`` (sans FreeCAD)."""
import pytest

from engine.kernel import KernelError
from engine.ops import BY_NAME
from engine.sketchsnap import (
    ROLES, Target, fits, parse_snaps, relations, snap_positions, targets_of,
    with_direction,
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


def test_un_point_lache_nomme_sa_cible():
    assert parse_snaps("sketch_drop", {"at": {"geo": 2, "point": 3}}) == {
        "at": Target("point", 2, point=3)}
    assert parse_snaps("sketch_drop", {"at": {"kind": "on", "geo": 1}}) == {
        "at": Target("on", 1)}
    with pytest.raises(KernelError, match="^accrochage inconnu : start$"):
        parse_snaps("sketch_drop", {"start": {"geo": 0, "point": 1}})


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
    ("sketch_add_line", {"sens": "horizontal"},
     "accrochage inconnu : sens"),
    ("sketch_add_line", {"direction": "horizontal"},
     "accrochage « direction » : cible invalide"),
    ("sketch_add_line", {"direction": {"kind": "on", "geo": 0}},
     "accrochage « direction » : cible invalide"),
    ("sketch_add_line", {"end": {"kind": "tangent", "geo": 0}},
     "accrochage « end » : cible invalide"),
    ("sketch_add_point", {"direction": {"kind": "tangent", "geo": 0}},
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
    (Target("parallel", 0), True),
    (Target("perpendicular", -3), True),
    (Target("parallel", 2), False),
    (Target("tangent", 1), True),
    (Target("tangent", 0), False),
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


def test_la_direction_d_une_ligne():
    parsed = parse_snaps("sketch_add_line", {
        "direction": {"kind": "perpendicular", "geo": 0}})
    assert parsed["direction"] == Target("perpendicular", 0)
    assert with_direction(Target("parallel", 0), 5, []) == [
        ("Parallel", 5, 0)]
    assert with_direction(Target("perpendicular", -3), 5, [
        ("Coincident", 5, 1, 0, 2)]) == [
        ("Coincident", 5, 1, 0, 2), ("Perpendicular", 5, -3)]


def test_tangente_au_bout_d_un_arc_au_lieu_de_la_coincidence():
    # Partie du bout 2 de l'arc 1 : tangente en ce bout, une relation.
    assert with_direction(Target("tangent", 1), 5, [
        ("Coincident", 5, 1, 1, 2), ("PointOnObject", 5, 2, 0)]) == [
        ("Tangent", 5, 1, 1, 2), ("PointOnObject", 5, 2, 0)]
    # Posée sur le cercle (« sur l'entité », un quadrant) : tangente en
    # ce point.
    assert with_direction(Target("tangent", 2), 5, [
        ("PointOnObject", 5, 2, 2), ("Vertical", 5, 2, 2, 3)]) == [
        ("Tangent", 5, 2, 2), ("Vertical", 5, 2, 2, 3)]
    # Ailleurs (le centre, un autre arc) : tangente tout court.
    assert with_direction(Target("tangent", 1), 5, [
        ("Coincident", 5, 1, 1, 3)]) == [
        ("Coincident", 5, 1, 1, 3), ("Tangent", 5, 1)]
