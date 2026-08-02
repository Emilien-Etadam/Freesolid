"""FreeSolid — GUI initialization."""

import FreeCADGui as Gui


class FreeSolidWorkbench(Gui.Workbench):
    """A familiar mechanical-CAD front end for FreeCAD's PartDesign."""

    MenuText = "FreeSolid"
    ToolTip = ("Interface familière pour les concepteurs venant de la CAO "
               "mécanique commerciale")

    def __init__(self):
        from freesolid.paths import get_icon
        icon = get_icon()
        if icon:
            self.__class__.Icon = icon

    def Initialize(self):
        from freesolid import commands
        commands.register()

        core = ["FreeSolid_NewPart", "FreeSolid_FeatureManager",
                "FreeSolid_Setup"]
        self.appendToolbar("FreeSolid", core)
        self.appendToolbar("Fonctions", list(commands.ALIAS_NAMES))
        self.appendMenu("FreeSolid", core + ["Separator"]
                        + list(commands.ALIAS_NAMES))

    def Activated(self):
        from freesolid.ui.feature_manager import get_feature_manager
        dock = get_feature_manager()
        if dock:
            dock.show()

    def Deactivated(self):
        # The dock stays: a designer switching to Assembly or TechDraw still
        # wants the construction tree in view.
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


# Icons must be reachable before any command resource is queried.
try:
    from freesolid.paths import get_icons_dir as _icons_dir
    _path = _icons_dir()
    if _path:
        Gui.addIconPath(_path)
except Exception:
    pass

Gui.addWorkbench(FreeSolidWorkbench())
