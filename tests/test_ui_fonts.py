"""Polices de l'interface : chaque @font-face pointe un fichier embarqué,
servi avec le bon type, licence à côté."""
import os
import re

from engine import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_font_face_has_its_file():
    html = open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8").read()
    urls = re.findall(r'url\("(fonts/[^"]+)"\)', html)
    assert len(urls) == 12
    for url in urls:
        assert os.path.isfile(os.path.join(ROOT, "app", url)), url


def test_fonts_are_served_and_licensed():
    assert server._CONTENT_TYPES[".woff2"] == "font/woff2"
    fonts = os.path.join(ROOT, "app", "fonts")
    for name in ("OFL-IBM-Plex-Sans.txt", "OFL-IBM-Plex-Mono.txt"):
        text = open(os.path.join(fonts, name), encoding="utf-8").read()
        assert "SIL Open Font License" in text
