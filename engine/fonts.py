"""Police pour la gravure de texte — les dossiers de chaque système.

Pur Python, sans FreeCAD : ``font_dirs`` dit où chercher selon la
plateforme, ``find_font`` prend la première police TrueType trouvée,
candidates connues d'abord. Le kernel (``_find_font``) s'en sert quand le
client ne passe pas ``font=``.
"""

import os
import sys

#: Noms de fichiers (sans extension, minuscules) préférés, dans l'ordre :
#: lisibles, présents d'office sur au moins un des trois systèmes.
PREFERRED = (
    "dejavusans",
    "liberationsans-regular",
    "arial",
    "segoeui",
    "helvetica",
    "notosans-regular",
)

_EXTENSIONS = (".ttf", ".otf")


def font_dirs(system=None, environ=None) -> list:
    """Dossiers de polices du système, système puis utilisateur.

    ``system`` est ``sys.platform`` (« win32 », « darwin », « linux »…) ;
    ``environ`` un dict à la place de ``os.environ`` (tests). Les dossiers
    sont rendus tels quels, existants ou non.
    """
    system = sys.platform if system is None else system
    env = os.environ if environ is None else environ
    home = env.get("HOME") or env.get("USERPROFILE") or ""
    if system.startswith("win"):
        windir = env.get("WINDIR") or env.get("SystemRoot") or r"C:\Windows"
        dirs = [os.path.join(windir, "Fonts")]
        local = env.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return dirs
    if system == "darwin":
        dirs = [
            "/System/Library/Fonts/Supplemental",
            "/System/Library/Fonts",
            "/Library/Fonts",
        ]
        if home:
            dirs.append(os.path.join(home, "Library", "Fonts"))
        return dirs
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts"]
    xdg = env.get("XDG_DATA_HOME") or (
        os.path.join(home, ".local", "share") if home else "")
    if xdg:
        dirs.append(os.path.join(xdg, "fonts"))
    if home:
        dirs.append(os.path.join(home, ".fonts"))
    return dirs


def find_font(dirs):
    """Chemin d'une police .ttf/.otf sous ``dirs``, ou ``None``.

    Une police de ``PREFERRED`` gagne (dans l'ordre de la liste, puis de
    ``dirs``) ; sinon la première par ordre alphabétique, .ttf avant .otf,
    pour un résultat stable d'un lancement à l'autre.
    """
    found = []
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for root, _subdirs, files in os.walk(base):
            for name in files:
                stem, ext = os.path.splitext(name)
                if ext.lower() in _EXTENSIONS:
                    found.append((stem.lower(), ext.lower(), os.path.join(root, name)))
    if not found:
        return None
    for wanted in PREFERRED:
        for stem, _ext, path in found:
            if stem == wanted:
                return path
    found.sort(key=lambda item: (_EXTENSIONS.index(item[1]), item[2].lower()))
    return found[0][2]
