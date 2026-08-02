"""FreeSolid — GUI initialization.

Two things this file must never do: fail silently, and let a cosmetic
problem (a missing icon) stop the workbench from registering. An exception
raised while constructing the Workbench means ``addWorkbench`` never runs and
FreeSolid simply does not appear in the selector, with nothing in the Report
view to say why — so every step here reports rather than swallows.
"""

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui

_ADDON_NAME = "freesolid"


def _addon_dir():
    """Directory holding this file.

    ``__file__`` is the reliable answer, but FreeCAD exec()s Init scripts and
    does not always populate it, hence the fallback scan of the Mod folders.
    """
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    for base in (App.getUserAppDataDir(), App.getResourceDir()):
        candidate = os.path.join(base, "Mod", _ADDON_NAME)
        if os.path.isdir(candidate):
            return candidate
    return ""


_DIR = _addon_dir()

# FreeCAD normally puts the addon directory on sys.path before running this
# file. "Normally" is not "always" — a manual install or a relocated user data
# dir can leave it out, and then every `import freesolid.*` below fails.
if _DIR and _DIR not in sys.path:
    sys.path.append(_DIR)


def _report(what, exc_info=True):
    """Send a failure to the Report view, loudly enough to be actionable."""
    message = "FreeSolid: {}\n".format(what)
    if exc_info:
        message += traceback.format_exc()
        message += "  addon dir : {}\n".format(_DIR or "(introuvable)")
        message += "  sys.path  : {}\n".format(
            "présent" if _DIR in sys.path else "ABSENT")
    App.Console.PrintError(message)


class FreeSolidWorkbench(Gui.Workbench):
    """A familiar mechanical-CAD front end for FreeCAD's PartDesign."""

    MenuText = "FreeSolid"
    ToolTip = ("Interface familière pour les concepteurs venant de la CAO "
               "mécanique commerciale")
    Icon = ""

    def Initialize(self):
        """Build toolbars and menus. Called on first activation."""
        try:
            from freesolid import commands
            commands.register()
        except Exception:
            _report("les commandes n'ont pas pu être enregistrées")
            return

        core = ["FreeSolid_NewPart", "FreeSolid_FeatureManager",
                "FreeSolid_Setup"]
        try:
            self.appendToolbar("FreeSolid", core)
            self.appendToolbar("Fonctions", list(commands.ALIAS_NAMES))
            self.appendMenu("FreeSolid", core + ["Separator"]
                            + list(commands.ALIAS_NAMES))
        except Exception:
            _report("barres d'outils et menus incomplets")

    def Activated(self):
        try:
            from freesolid.ui.feature_manager import get_feature_manager
            dock = get_feature_manager()
            if dock:
                dock.show()
        except Exception:
            _report("le dock FeatureManager n'a pas pu s'ouvrir")

    def Deactivated(self):
        # The dock stays: a designer switching to Assembly or TechDraw still
        # wants the construction tree in view.
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


# Icons are cosmetic: resolve them best-effort, never at the cost of
# registration.
try:
    icons = os.path.join(_DIR, "resources", "icons")
    if os.path.isdir(icons):
        Gui.addIconPath(icons)
        icon = os.path.join(icons, "freesolid.svg")
        if os.path.exists(icon):
            FreeSolidWorkbench.Icon = icon
except Exception:
    _report("icône indisponible (sans conséquence)")

try:
    Gui.addWorkbench(FreeSolidWorkbench())
except Exception:
    _report("l'atelier n'a pas pu être enregistré — il n'apparaîtra pas "
            "dans le sélecteur")
