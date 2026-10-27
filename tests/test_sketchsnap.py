"""Accrochages d'un tracé d'esquisse : forme de ``snaps`` (sans FreeCAD)."""
import pytest

from engine.kernel import KernelError
from engine.ops import BY_NAME
from engine.sketchsnap import ROLES, parse_snaps, snap_positions, targets_of


def test_chaque_trace_accrochable_declare_snaps():
    for op in ROLES:
        assert BY_NAME[op].req.optional.get("snaps") is dict, op


def test_une_cible_devient_un_couple_geo_point():
    parsed = parse_snaps("sketch_add_line", {
        "start": {"geo": 3, "point": 3}, "end": {"geo": -1, "point": 1}})
    assert parsed == {"start": (3, 3), "end": (-1, 1)}


def test_un_role_absent_ou_nul_n_accroche_rien():
    assert parse_snaps("sketch_add_line", {}) == {}
    assert parse_snaps("sketch_add_line", {"start": None}) == {}


def test_les_points_poses_sur_un_cercle_forment_une_liste():
    parsed = parse_snaps("sketch_add_circle", {
        "center": {"geo": 0, "point": 1},
        "on": [{"geo": 1, "point": 2}, {"geo": -3, "point": 1}]})
    assert parsed["on"] == [(1, 2), (-3, 1)]
    assert list(targets_of(parsed)) == [
        ("center", (0, 1)), ("on", (1, 2)), ("on", (-3, 1))]


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
