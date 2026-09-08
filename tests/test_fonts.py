"""Police de gravure — dossiers par système et choix stable, sans FreeCAD."""

import os

from engine import fonts


def test_windows_dirs_follow_windir_and_user_fonts():
    env = {"WINDIR": r"D:\Win", "LOCALAPPDATA": r"C:\Users\pc\AppData\Local"}
    dirs = fonts.font_dirs("win32", env)
    assert dirs[0] == os.path.join(r"D:\Win", "Fonts")
    assert dirs[1] == os.path.join(
        r"C:\Users\pc\AppData\Local", "Microsoft", "Windows", "Fonts")
    # Sans variables : l'installation standard.
    assert fonts.font_dirs("win32", {}) == [os.path.join(r"C:\Windows", "Fonts")]


def test_macos_dirs_include_supplemental_and_user_library():
    dirs = fonts.font_dirs("darwin", {"HOME": "/Users/moi"})
    assert dirs[0] == "/System/Library/Fonts/Supplemental"
    assert "/Library/Fonts" in dirs
    assert dirs[-1] == os.path.join("/Users/moi", "Library", "Fonts")


def test_linux_dirs_include_share_and_user_fonts():
    dirs = fonts.font_dirs("linux", {"HOME": "/home/moi"})
    assert dirs[0] == "/usr/share/fonts"
    assert os.path.join("/home/moi", ".local", "share", "fonts") in dirs
    assert os.path.join("/home/moi", ".fonts") in dirs
    xdg = fonts.font_dirs("linux", {"HOME": "/home/moi", "XDG_DATA_HOME": "/data"})
    assert os.path.join("/data", "fonts") in xdg


def test_find_font_prefers_known_faces_then_alphabetical(tmp_path):
    sub = tmp_path / "sys" / "truetype"
    sub.mkdir(parents=True)
    (sub / "zzz.ttf").write_bytes(b"x")
    (sub / "aaa.otf").write_bytes(b"x")
    user = tmp_path / "user"
    user.mkdir()
    dirs = [str(tmp_path / "sys"), str(user), str(tmp_path / "absent")]
    # Ni candidate connue : .ttf avant .otf, puis alphabétique.
    assert fonts.find_font(dirs) == str(sub / "zzz.ttf")
    (sub / "Arial.TTF").write_bytes(b"x")
    assert fonts.find_font(dirs) == str(sub / "Arial.TTF")
    # Une candidate mieux classée, même dans un dossier plus loin, gagne.
    (user / "DejaVuSans.ttf").write_bytes(b"x")
    assert fonts.find_font(dirs) == str(user / "DejaVuSans.ttf")
    # Les fichiers d'autres types ne comptent pas.
    (sub / "notes.txt").write_bytes(b"x")
    assert fonts.find_font([str(tmp_path / "vide")]) is None


def test_find_font_on_this_machine_matches_the_platform_dirs():
    # Le kernel appelle exactement ceci ; ne doit jamais lever.
    result = fonts.find_font(fonts.font_dirs())
    assert result is None or result.lower().endswith((".ttf", ".otf"))
