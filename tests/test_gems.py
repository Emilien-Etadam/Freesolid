"""Gabarit de pierre et ancrage (u, v) — pur Python, sans FreeCAD."""

import os

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
