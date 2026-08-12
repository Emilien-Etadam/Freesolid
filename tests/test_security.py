"""Sécurité serveur — jail chemins, anti-CSRF, cap requête.

Pur Python : aucun FreeCAD. ``FREESOLID_NO_SERVE`` est posé avant l'import
de ``engine.server`` pour éviter d'ouvrir le port.
"""

import os
import tempfile

import pytest

os.environ["FREESOLID_NO_SERVE"] = "1"

from engine import protocol                                          # noqa: E402
from engine import server                                            # noqa: E402


# -- resolve_user_path ---------------------------------------------------

def test_resolve_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "piece.FCStd"
    target.write_text("x")
    got = protocol.resolve_user_path(
        str(target), (".FCStd",), must_exist=True)
    assert got == os.path.realpath(str(target))


def test_resolve_under_tempdir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    target = tmp_path / "out.stl"
    # écriture : parent existe, fichier pas encore
    got = protocol.resolve_user_path(
        str(target), (".stl",), must_exist=False)
    assert got == os.path.realpath(str(target))


def test_resolve_etc_passwd_refused():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            "/etc/passwd", (".FCStd",), must_exist=False)
    assert "hors du dossier autorisé" in str(excinfo.value)


def test_resolve_traversal_via_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            "~/../ailleurs/x.FCStd", (".FCStd",), must_exist=False)
    assert "hors du dossier autorisé" in str(excinfo.value)


def test_resolve_dotfile_under_home_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    target = ssh / "x.FCStd"
    target.write_text("x")
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            str(target), (".FCStd",), must_exist=True)
    assert "hors du dossier autorisé" in str(excinfo.value)


def test_resolve_bad_extension_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "notes.txt"
    target.write_text("x")
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            str(target), (".FCStd",), must_exist=True)
    assert "extension non autorisée" in str(excinfo.value)


def test_resolve_extension_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "piece.fcstd"
    target.write_text("x")
    got = protocol.resolve_user_path(
        str(target), (".FCStd",), must_exist=True)
    assert got.endswith(".fcstd")


def test_resolve_must_exist_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    missing = tmp_path / "absent.FCStd"
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            str(missing), (".FCStd",), must_exist=True)
    assert "introuvable" in str(excinfo.value)


def test_resolve_symlink_escaping_jail_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    link = tmp_path / "escape.FCStd"
    link.symlink_to("/etc/passwd")
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.resolve_user_path(
            str(link), (".FCStd",), must_exist=True)
    assert "hors du dossier autorisé" in str(excinfo.value)


def test_resolve_data_dir_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FREESOLID_DATA_DIR", str(data))
    target = data / "piece.FCStd"
    target.write_text("x")
    got = protocol.resolve_user_path(
        str(target), (".FCStd",), must_exist=True)
    assert got == os.path.realpath(str(target))


# -- handlers HTTP (fonctions pures) -------------------------------------

def test_origin_absent_ok():
    assert server._origin_ok(None) is True
    assert server._origin_ok("") is True


def test_origin_localhost_ok():
    assert server._origin_ok("http://127.0.0.1:8787") is True
    assert server._origin_ok("http://localhost:8787") is True


def test_origin_foreign_refused():
    assert server._origin_ok("https://evil.example") is False
    assert server._origin_ok("http://127.0.0.1:9999") is False


def test_origin_uses_port_constant():
    assert server._origin_ok("http://localhost:9000", port=9000) is True
    assert server._origin_ok("http://localhost:8787", port=9000) is False


def test_payload_ok_json():
    status, length = server._payload_ok({
        "Content-Type": "application/json",
        "Content-Length": "12",
    })
    assert status is None
    assert length == 12


def test_payload_ok_json_with_charset():
    status, length = server._payload_ok({
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": "1",
    })
    assert status is None
    assert length == 1


def test_payload_rejects_text_plain():
    status, message = server._payload_ok({
        "Content-Type": "text/plain",
        "Content-Length": "10",
    })
    assert status == 403
    assert "application/json" in message


def test_payload_rejects_missing_content_type():
    status, message = server._payload_ok({"Content-Length": "10"})
    assert status == 403


def test_payload_rejects_missing_content_length():
    status, message = server._payload_ok({
        "Content-Type": "application/json",
    })
    assert status == 413
    assert "Content-Length" in message


def test_payload_rejects_invalid_content_length():
    status, message = server._payload_ok({
        "Content-Type": "application/json",
        "Content-Length": "abc",
    })
    assert status == 413


def test_payload_rejects_oversize():
    status, message = server._payload_ok({
        "Content-Type": "application/json",
        "Content-Length": str(4 * 1024 * 1024 + 1),
    })
    assert status == 413
    assert "4 Mo" in message


def test_safe_static_path_inside(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html></html>")
    assert server._safe_static_path("/", app_dir=str(tmp_path)) == os.path.realpath(
        str(page))


def test_safe_static_path_traversal(tmp_path):
    assert server._safe_static_path(
        "/../etc/passwd", app_dir=str(tmp_path)) is None
