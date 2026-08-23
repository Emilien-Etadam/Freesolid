"""Gabarit de pierre et ancrage (u, v) — pur Python, sans FreeCAD."""

import os
import math
import random

import pytest

from engine import gems, protocol


def test_sanitize_gemme_default_and_valid():
    assert gems.sanitize_gemme(None) == "cylindre-plat"
    assert gems.sanitize_gemme("") == "cylindre-plat"
    assert gems.sanitize_gemme("  brillant-rond  ") == "brillant-rond"


@pytest.mark.parametrize("name", [
    "../etc/passwd", "Cylindre", "cylindre_plat", "a/b", ".",
    "cylindre.plat", "-plat", "1gem",
])
def test_sanitize_gemme_rejects_paths(name):
    with pytest.raises(gems.GemError) as excinfo:
        gems.sanitize_gemme(name)
    assert "gabarit" in str(excinfo.value)


def test_library_path_stays_under_assets():
    path = gems.library_path("cylindre-plat")
    assert path.endswith(os.path.join("assets", "gemmes", "cylindre-plat.FCStd"))
    assert os.path.basename(os.path.dirname(path)) == "gemmes"


def test_face_name_roundtrip():
    assert gems.face_name(0) == "Face1"
    assert gems.face_name(2) == "Face3"
    assert gems.face_index("Face1") == 0
    assert gems.face_index("Face3") == 2
    with pytest.raises(gems.GemError):
        gems.face_index("Edge1")
    with pytest.raises(gems.GemError):
        gems.face_name(-1)


def test_cache_key_rounds_diametre():
    assert gems.cache_key("cylindre-plat", 1.5) == ("cylindre-plat", 1.5)
    assert gems.cache_key("cylindre-plat", 1.5000001) == gems.cache_key(
        "cylindre-plat", 1.5)


def test_parse_diametre_rejects_zero_and_negative():
    assert gems.parse_diametre(None) == gems.DEFAULT_DIAMETRE
    with pytest.raises(gems.GemError):
        gems.parse_diametre(0)
    with pytest.raises(gems.GemError):
        gems.parse_diametre(-1)


def test_arc_entraxe_and_gap():
    entraxe = gems.arc_entraxe_mm(9.0, 30)
    assert entraxe is not None
    assert abs(entraxe - 1.885) < 0.001
    assert gems.seating_gap_mm(entraxe, 1.5) is not None
    assert gems.seating_gap_mm(entraxe, 1.5) > 0
    assert gems.seating_gap_mm(1.414, 1.5) < 0
    assert gems.arc_entraxe_mm(9.0, 0) is None
    assert gems.seating_gap_mm(None, 1.5) is None


def test_face_radius_mm_reads_cylinder_or_torus_without_freecad():
    class _Surf:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Face:
        def __init__(self, surface):
            self.Surface = surface

    assert gems.face_radius_mm(_Face(_Surf(Radius=9.0))) == 9.0
    assert gems.face_radius_mm(_Face(_Surf(MajorRadius=10.0))) == 10.0
    assert gems.face_radius_mm(_Face(_Surf())) is None
    assert gems.face_radius_mm(None) is None


def test_pack_mesh_optional_normals_aligned_on_vertices():
    mesh = protocol.pack_mesh([
        (0, [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)],
         [(0, 0, 1), (0, 0, 1), (0, 0, 1)]),
        (1, [(0, 0, 1)], [], [(1, 0, 0)]),
    ])
    assert mesh["normals"] == [
        0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0,
        1.0, 0.0, 0.0,
    ]
    assert "normals" not in protocol.pack_mesh([])


def test_pack_mesh_without_normals_omits_the_key():
    mesh = protocol.pack_mesh([
        (0, [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)]),
    ])
    assert "normals" not in mesh
    assert mesh["indices"] == [0, 1, 2]


def _naive_voisines(points, rayons):
    n = min(len(points), len(rayons))
    out = [(None, None)] * n
    for i in range(n):
        best_e = None
        best_g = None
        xi, yi, zi = (float(points[i][0]), float(points[i][1]),
                      float(points[i][2]))
        ri = float(rayons[i])
        for j in range(n):
            if i == j:
                continue
            dx = xi - float(points[j][0])
            dy = yi - float(points[j][1])
            dz = zi - float(points[j][2])
            entraxe = (dx * dx + dy * dy + dz * dz) ** 0.5
            gap = entraxe - (ri + float(rayons[j]))
            if best_e is None or entraxe < best_e:
                best_e, best_g = entraxe, gap
        out[i] = (best_e, best_g)
    return out


def test_voisines_min_mm_matches_naive_on_200_random_points():
    rng = random.Random(42)
    points = [(rng.uniform(-20, 20), rng.uniform(-20, 20), rng.uniform(-5, 5))
              for _ in range(200)]
    rayons = [rng.uniform(0.3, 1.2) for _ in range(200)]
    got = gems.voisines_min_mm(points, rayons)
    naive = _naive_voisines(points, rayons)
    assert len(got) == 200
    for (e1, g1), (e2, g2) in zip(got, naive):
        assert e1 is not None and e2 is not None
        assert abs(e1 - e2) < 1e-9
        assert abs(g1 - g2) < 1e-9


def test_voisines_min_mm_gap_uses_half_sum_of_diameters():
    points = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
    rayons = [0.5, 0.75]  # Ø 1,0 et Ø 1,5
    pairs = gems.voisines_min_mm(points, rayons)
    assert len(pairs) == 2
    entraxe, ecart = pairs[0]
    assert abs(entraxe - 2.0) < 1e-12
    assert abs(ecart - (2.0 - 1.25)) < 1e-12
    assert pairs[0] == pairs[1]


def test_voisines_min_mm_single_stone_is_none():
    assert gems.voisines_min_mm([(0.0, 0.0, 0.0)], [0.75]) == [(None, None)]
    assert gems.voisines_min_mm([], []) == []


def test_voisines_min_mm_overlap_is_negative():
    pairs = gems.voisines_min_mm(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [1.0, 1.0])
    assert pairs[0][0] == 1.0
    assert pairs[0][1] == -1.0
    assert pairs[1][1] == -1.0


def test_voisines_min_mm_circle_chord_is_negative():
    """50 points sur un cercle de rayon 11,94 mm, Ø 1,5 : corde, pas arc.

    ``entraxe_mm = 2πR/n`` donne +4,25e-4 mm ; la mesure réelle est la
    corde ``2R·sin(π/n)``, négative. Un test ne doit pas écrire à la
    main la valeur d'arc que le moteur ne peut pas rendre.
    """
    n = 50
    radius = 11.94
    diametre = 1.5
    points = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        points.append((
            radius * math.cos(angle),
            radius * math.sin(angle),
            0.0,
        ))
    pairs = gems.voisines_min_mm(points, [diametre / 2.0] * n)
    gaps = [gap for _entraxe, gap in pairs if gap is not None]
    assert gaps
    assert all(gap < 0 for gap in gaps)
    expected = 2.0 * radius * math.sin(math.pi / n) - diametre
    assert abs(min(gaps) - expected) < 1e-9
    assert expected < 0


class _Named:
    def __init__(self, name, type_id=""):
        self.Name = name
        self.TypeId = type_id


def test_trace_pairs_list_of_couples():
    pad = _Named("Pad")
    sketch = _Named("Sketch")
    pairs = gems.trace_pairs([
        (pad, "#6:1;:G;XTR;:H17e:7,F"),
        (sketch, "g1;SKT"),
    ])
    assert pairs == [
        ("Pad", "#6:1;:G;XTR;:H17e:7,F"),
        ("Sketch", "g1;SKT"),
    ]


def test_trace_pairs_flat_tuple():
    assert gems.trace_pairs(
        (42, "#6:1;:G;XTR;:H17e:7,F", ["mid"])
    ) == [("42", "#6:1;:G;XTR;:H17e:7,F")]


def test_trace_pairs_none_string_empty():
    assert gems.trace_pairs(None) == []
    assert gems.trace_pairs("erreur : historique illisible") == []
    assert gems.trace_pairs([]) == []


def test_owner_couple_deepest_non_sketch():
    def _pairs(*names):
        return [(n, "elem-{}".format(n)) for n in names]

    assert gems.owner_couple(
        _pairs("Body", "Pocket", "Pad", "Sketch")
    ) == ("Pad", "elem-Pad")
    assert gems.owner_couple(
        _pairs("Body", "Pad", "Sketch")
    ) == ("Pad", "elem-Pad")
    assert gems.owner_couple(
        _pairs("Body", "Sketch")
    ) == ("Body", "elem-Body")
    assert gems.owner_couple([]) is None
    assert gems.owner_couple(
        _pairs("Body", "Pad", "Sketch001")
    ) == ("Pad", "elem-Pad")


def test_resolution_verdict_three_states():
    assert gems.resolution_verdict([3]) == "résolu"
    assert gems.resolution_verdict([1, 4]) == "ambigu"
    assert gems.resolution_verdict([]) == "perdu"
    assert gems.resolution_verdict(None) == "perdu"
