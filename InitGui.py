"""FreeSolid — GUI initialization.

**Scoping rule for this file.** FreeCAD exec()s Init scripts with separate
globals and locals dictionaries. Names bound at the top level here land in
the locals dict, while function and method bodies look their names up in the
globals dict — so *a method defined in this file cannot see anything defined
in this file*. Referencing a module-level constant from a method raises
``NameError: name '...' is not defined`` at initialization, and the workbench
never registers.

Consequences, both deliberate:

- this file stays straight-line; no module-level helper functions;
- every method imports what it needs *inside its own body*, which is why the
  real logic lives in the ``freesolid`` package.
"""

import os
import sys

import FreeCAD as App
import FreeCADGui as Gui

try:
    _DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # FreeCAD does not always populate __file__ when exec()ing Init scripts.
    _DIR = os.path.join(App.getUserAppDataDir(), "Mod", "freesolid")

# FreeCAD normally puts the addon directory on sys.path before running this
# file. "Normally" is not "always" — a manual install or a relocated user data
# directory can leave it out, and then every `import freesolid.*` fails.
if _DIR and _DIR not in sys.path:
    sys.path.append(_DIR)


class FreeSolidWorkbench(Gui.Workbench):
    """A familiar mechanical-CAD front end for FreeCAD's PartDesign."""

    MenuText = "FreeSolid"
    ToolTip = ("Interface familière pour les concepteurs venant de la CAO "
               "mécanique commerciale")
    Icon = ""

    def Initialize(self):
        """Build toolbars and menus. Called on first activation."""
        from freesolid.log import report
        try:
            from freesolid import commands
            commands.register()
        except Exception:
            report("les commandes n'ont pas pu être enregistrées")
            return

        try:
            self.appendToolbar("FreeSolid", list(commands.CORE_NAMES))
            self.appendToolbar("Fonctions", list(commands.ALIAS_NAMES))
            self.appendMenu("FreeSolid",
                            list(commands.CORE_NAMES)
                            + ["FreeSolid_ContextBar", "Separator"]
                            + list(commands.ALIAS_NAMES))
        except Exception:
            report("barres d'outils et menus incomplets")

        # The guardrail observes recomputes to explain PartDesign's refusals
        # in designer terms; purely additive, so a failure is only reported.
        try:
            from freesolid import guard
            guard.install()
        except Exception:
            report("garde-fou non installé")

    def Activated(self):
        from freesolid.log import report
        try:
            from freesolid.ui.feature_manager import get_feature_manager
            dock = get_feature_manager()
            if dock:
                dock.show()
        except Exception:
            report("le dock FeatureManager n'a pas pu s'ouvrir")

    def Deactivated(self):
        # The dock stays: a designer switching to Assembly or TechDraw still
        # wants the construction tree in view.
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


# Commands are registered at application start, not at first workbench
# activation: the "S" contextual bar, the Fonctions strip and the guardrail
# must work in PartDesign and Sketcher without the user ever selecting the
# FreeSolid workbench.
try:
    from freesolid import commands as _commands
    _commands.register()
    from freesolid import guard as _guard
    _guard.install()
    # The Fonctions strip and the FeatureManager must exist in every session,
    # whatever workbench FreeCAD starts in — not only after FreeSolid is
    # activated. Deferred one event-loop turn (main window not assembled yet).
    from freesolid import startup as _startup
    _startup.defer_panels()
except Exception:
    import traceback as _tb
    App.Console.PrintError(
        "FreeSolid: enregistrement au démarrage incomplet\n" + _tb.format_exc())

# Icons are cosmetic: resolved best-effort, never at the cost of registration.
try:
    _ICONS = os.path.join(_DIR, "resources", "icons")
    if os.path.isdir(_ICONS):
        Gui.addIconPath(_ICONS)
        _ICON = os.path.join(_ICONS, "freesolid.svg")
        if os.path.exists(_ICON):
            FreeSolidWorkbench.Icon = _ICON
except Exception:
    App.Console.PrintWarning("FreeSolid: icône indisponible, sans conséquence\n")

try:
    Gui.addWorkbench(FreeSolidWorkbench())
except Exception:
    import traceback
    App.Console.PrintError(
        "FreeSolid: l'atelier n'a pas pu être enregistré, il n'apparaîtra pas "
        "dans le sélecteur\n"
        + traceback.format_exc()
        + "  addon dir : {}\n".format(_DIR)
        + "  sys.path  : {}\n".format(
            "présent" if _DIR in sys.path else "ABSENT"))
