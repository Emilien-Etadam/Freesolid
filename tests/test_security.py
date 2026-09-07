"""Sécurité serveur — jail chemins, anti-CSRF, cap requête, expressions.

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


def test_origin_tauri_desktop_ok():
    # desktop/ (Tauri) : l'écran de lancement parle au moteur local.
    assert server._origin_ok("tauri://localhost") is True
    assert server._origin_ok("http://tauri.localhost") is True
    assert server._origin_ok("https://tauri.localhost") is True
    assert server._origin_ok("tauri://evil") is False


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


def test_ribbon_json_sert_le_bon_mime():
    """L'UI importe ribbon.json en module (``with { type: "json" }``) —
    le navigateur refuse l'import si le type MIME servi n'est pas JSON."""
    chemin = server._safe_static_path("/ribbon.json")
    assert chemin is not None
    ext = os.path.splitext(chemin)[1]
    assert server._CONTENT_TYPES[ext].startswith("application/json")


def _plugin_loaded(tmp_path, nom="alpha", directory="disk-name"):
    folder = tmp_path / directory
    ui = folder / "ui"
    ui.mkdir(parents=True)
    (ui / "plugin.js").write_text("export function register() {}\n")
    (ui / "note.txt").write_text("ok")
    return [{
        "nom": nom,
        "statique": "ui",
        "directory": str(folder),
    }]


def test_plugin_static_serves_under_loaded_jail(tmp_path):
    loaded = _plugin_loaded(tmp_path)
    got = server._safe_plugin_static_path(
        "/plugins/alpha/plugin.js", loaded=loaded)
    assert got == os.path.realpath(str(tmp_path / "disk-name" / "ui" / "plugin.js"))


def test_plugin_static_uses_loaded_name_not_url_directory(tmp_path):
    loaded = _plugin_loaded(tmp_path, nom="alpha", directory="disk-name")
    assert server._safe_plugin_static_path(
        "/plugins/disk-name/plugin.js", loaded=loaded) is None
    assert server._safe_plugin_static_path(
        "/plugins/alpha/plugin.js", loaded=loaded) is not None


def test_plugin_static_unknown_plugin_refused(tmp_path):
    loaded = _plugin_loaded(tmp_path)
    assert server._safe_plugin_static_path(
        "/plugins/inconnu/plugin.js", loaded=loaded) is None


def test_plugin_static_traversal_refused(tmp_path):
    loaded = _plugin_loaded(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("no")
    assert server._safe_plugin_static_path(
        "/plugins/alpha/../secret.txt", loaded=loaded) is None
    assert server._safe_plugin_static_path(
        "/plugins/alpha/../../etc/passwd", loaded=loaded) is None
    assert server._safe_plugin_static_path(
        "/plugins/../alpha/plugin.js", loaded=loaded) is None


def test_plugin_static_missing_file_refused(tmp_path):
    loaded = _plugin_loaded(tmp_path)
    assert server._safe_plugin_static_path(
        "/plugins/alpha/absent.js", loaded=loaded) is None


def test_plugin_static_query_and_fragment_ignored(tmp_path):
    loaded = _plugin_loaded(tmp_path)
    got = server._safe_plugin_static_path(
        "/plugins/alpha/note.txt?x=1#y", loaded=loaded)
    assert got == os.path.realpath(str(tmp_path / "disk-name" / "ui" / "note.txt"))


# -- validate_expression -------------------------------------------------

@pytest.mark.parametrize("text", [
    "2*Largeur + 5",
    "Variables.epaisseur / 2",
    "sin(30 deg)",
    "(a + b) * 0,5",
    "Variables.épaisseur / 2",
])
def test_validate_expression_accepts_real_usage(text):
    assert protocol.validate_expression(text) == text


def test_validate_expression_strips():
    assert protocol.validate_expression("  2*x  ") == "2*x"


@pytest.mark.parametrize("text, char", [
    ("<<Autre>>.Valeur", "<"),
    ("a; b", ";"),
    ("x = 3", "="),
    ('"txt"', '"'),
    ("a[0]", "["),
])
def test_validate_expression_refuses_injection_chars(text, char):
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_expression(text)
    message = str(excinfo.value)
    assert "caractère non autorisé" in message
    assert "«{}»".format(char) in message


def test_validate_expression_refuses_empty():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_expression("")
    assert "vide" in str(excinfo.value)
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_expression("  ")
    assert "vide" in str(excinfo.value)


def test_validate_expression_refuses_too_long():
    with pytest.raises(protocol.ProtocolError) as excinfo:
        protocol.validate_expression("a" * 300)
    assert "trop longue" in str(excinfo.value)
