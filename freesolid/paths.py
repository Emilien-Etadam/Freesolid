"""Filesystem helpers.

Kept in a plain module so InitGui.py can import it: FreeCAD exec()s Init
scripts, which breaks closures over module-level names.
"""

import os

ADDON_DIRNAME = "freesolid"


def get_addon_dir() -> str:
    """Absolute path of the installed addon, or an empty string."""
    import FreeCAD as App
    for base in (App.getUserAppDataDir(), App.getResourceDir()):
        candidate = os.path.join(base, "Mod", ADDON_DIRNAME)
        if os.path.isdir(candidate):
            return candidate
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_icons_dir() -> str:
    path = os.path.join(get_addon_dir(), "resources", "icons")
    return path if os.path.isdir(path) else ""


def get_icon(name: str = "freesolid.svg") -> str:
    path = os.path.join(get_icons_dir(), name)
    return path if os.path.exists(path) else ""
