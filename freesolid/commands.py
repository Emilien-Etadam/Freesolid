"""FreeSolid commands.

Three families:

- ``Setup`` applies the preference table and reports what it did.
- ``NewPart`` reproduces SolidWorks' File > New > Part, which in FreeCAD
  means "document + Body + activate the Body" — the step whose absence
  causes most of the early confusion.
- The aliases in :data:`freesolid.vocab.TERMS` re-expose PartDesign commands
  under the names a mechanical designer already knows. They delegate; they do
  not reimplement.
"""

from . import prefs as prefs_mod
from .vocab import TERMS


def _gui():
    import FreeCADGui as Gui
    return Gui


def _app():
    import FreeCAD as App
    return App


class SetupCommand:
    """Apply the FreeSolid defaults, then show what changed."""

    def GetResources(self):
        return {
            "MenuText": "Configurer FreeSolid",
            "ToolTip": "Applique la navigation, la disposition des panneaux "
                       "et les réglages par défaut adaptés aux utilisateurs "
                       "de CAO mécanique commerciale",
        }

    def Activated(self, index=0):
        App = _app()
        applied, failed = prefs_mod.apply_all(App.ParamGet)
        self._restrict_workbenches()

        lines = ["{} réglage(s) appliqué(s) :".format(len(applied)), ""]
        lines += ["  • {}".format(p.why) for p in applied]

        pending = [p for p in applied if not p.verified]
        if pending:
            lines += ["", "À vérifier sur cette version de FreeCAD "
                          "(chemin de paramètre non confirmé) :"]
            lines += ["  • {}/{}".format(p.path, p.key) for p in pending]

        if failed:
            lines += ["", "Échecs :"]
            lines += ["  • {}/{} — {}".format(p.path, p.key, exc)
                      for p, exc in failed]

        lines += ["", "Redémarrez FreeCAD pour que la disposition des "
                      "panneaux prenne effet."]

        message = "\n".join(lines)
        App.Console.PrintMessage(message + "\n")
        self._show(message)

    def _restrict_workbenches(self):
        """Hide the workbenches a mechanical designer never opens.

        Kept out of the declarative table: FreeCAD stores this as one
        comma-separated blob, and the key has moved between releases, so this
        is best-effort and deliberately non-fatal.
        """
        try:
            App = _app()
            group = App.ParamGet("User parameter:BaseApp/Preferences/Workbenches")
            available = [wb for wb in _gui().listWorkbenches()]
            disabled = [wb for wb in available
                        if wb not in prefs_mod.KEEP_WORKBENCHES]
            group.SetString("Disabled", ",".join(sorted(disabled)))
        except Exception as exc:  # noqa: BLE001
            _app().Console.PrintWarning(
                "FreeSolid: liste des ateliers non modifiée ({})\n".format(exc))

    @staticmethod
    def _show(message):
        try:
            from .compat import QtWidgets
            QtWidgets.QMessageBox.information(
                _gui().getMainWindow(), "FreeSolid", message)
        except Exception:
            pass

    def IsActive(self):
        return True


class NewPartCommand:
    """Document + Body + activation, in one click."""

    def GetResources(self):
        return {
            "MenuText": "Nouvelle pièce",
            "ToolTip": "Crée un document contenant une pièce (Body) active, "
                       "équivalent de Fichier > Nouveau > Pièce",
        }

    def Activated(self, index=0):
        App, Gui = _app(), _gui()
        doc = App.ActiveDocument or App.newDocument()
        body = doc.addObject("PartDesign::Body", "Piece")
        doc.recompute()
        try:
            Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
        except Exception:
            pass
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
        except Exception:
            pass
        from .ui.feature_manager import get_feature_manager
        dock = get_feature_manager()
        if dock:
            dock.show()

    def IsActive(self):
        return True


class FeatureManagerCommand:
    """Show/hide the FeatureManager dock."""

    def GetResources(self):
        return {
            "MenuText": "FeatureManager",
            "ToolTip": "Affiche l'arbre de construction en présentation "
                       "chronologique, avec barre de retour arrière",
            "Checkable": True,
        }

    def Activated(self, index=0):
        from .ui.feature_manager import get_feature_manager
        dock = get_feature_manager()
        if dock is None:
            return
        dock.setVisible(not dock.isVisible())

    def IsChecked(self):
        from .ui.feature_manager import get_feature_manager
        dock = get_feature_manager(create=False)
        return bool(dock and dock.isVisible())

    def IsActive(self):
        return True


class AliasCommand:
    """Run a PartDesign command under its SolidWorks name.

    The icon is inherited from the delegated command rather than redrawn:
    a designer should see the same picture whichever name they reach the tool
    by, and without one FreeCAD falls back to text labels, which overflow the
    toolbar within a handful of entries.
    """

    def __init__(self, term):
        self._term = term

    def GetResources(self):
        resources = {
            "MenuText": self._term.fr,
            "ToolTip": self._term.note or "{} ({})".format(
                self._term.fr, self._term.command),
        }
        pixmap = self._inherited_pixmap()
        if pixmap:
            resources["Pixmap"] = pixmap
        return resources

    def _inherited_pixmap(self):
        """Icon of the PartDesign command we delegate to.

        Two strategies, because the first only works once PartDesign has been
        loaded — which is not guaranteed when FreeSolid builds its toolbars.
        The fallback is the command name itself: FreeCAD resolves icons by
        name against its registered icon paths, and PartDesign's icons are
        named after their commands.
        """
        try:
            command = _gui().Command.get(self._term.command)
            if command is not None:
                pixmap = command.getInfo().get("pixmap", "")
                if pixmap:
                    return pixmap
        except Exception:
            pass
        return self._term.command

    def Activated(self, index=0):
        try:
            _gui().runCommand(self._term.command, 0)
        except Exception as exc:  # noqa: BLE001
            _app().Console.PrintError(
                "FreeSolid: {} indisponible ({})\n".format(
                    self._term.command, exc))

    def IsActive(self):
        return _app().ActiveDocument is not None


class ContextBarCommand:
    """Pop the SolidWorks-style shortcut bar at the cursor (the "S" key)."""

    def GetResources(self):
        return {
            "MenuText": "Barre contextuelle",
            "ToolTip": "Palette de commandes au curseur, adaptée à la "
                       "sélection — l'équivalent de la barre « S » de "
                       "SolidWorks",
            "Accel": "S",
        }

    def Activated(self, index=0):
        try:
            from .ui.context_bar import show_at_cursor
            show_at_cursor()
        except Exception as exc:  # noqa: BLE001
            _app().Console.PrintError(
                "FreeSolid: barre contextuelle indisponible ({})\n".format(exc))

    def IsActive(self):
        return _app().ActiveDocument is not None


class DiagnosticsCommand:
    """Probe this install and produce a copy-pastable report."""

    def GetResources(self):
        return {
            "MenuText": "Diagnostic FreeSolid",
            "ToolTip": "Vérifie sur cette installation les chemins de "
                       "paramètres utilisés par FreeSolid et l'état des "
                       "panneaux, et produit un rapport copiable",
        }

    def Activated(self, index=0):
        from . import diagnostics
        text = diagnostics.full_report()
        _app().Console.PrintMessage(text)
        try:
            diagnostics.show_dialog(text)
        except Exception:
            pass  # the console copy is already out

    def IsActive(self):
        return True


#: Core (non-alias) command names, in toolbar order.
CORE_NAMES = ("FreeSolid_NewPart", "FreeSolid_FeatureManager",
              "FreeSolid_Setup", "FreeSolid_Diagnostics")

#: Alias command names, in ribbon order — consumed by InitGui to build the
#: toolbar without restating the list.
ALIAS_NAMES = tuple(
    "FreeSolid_" + term.command.split("_", 1)[1] for term in TERMS)


def register():
    """Register every command with FreeCAD. Idempotent."""
    Gui = _gui()
    Gui.addCommand("FreeSolid_Setup", SetupCommand())
    Gui.addCommand("FreeSolid_NewPart", NewPartCommand())
    Gui.addCommand("FreeSolid_FeatureManager", FeatureManagerCommand())
    Gui.addCommand("FreeSolid_Diagnostics", DiagnosticsCommand())
    Gui.addCommand("FreeSolid_ContextBar", ContextBarCommand())
    for name, term in zip(ALIAS_NAMES, TERMS):
        Gui.addCommand(name, AliasCommand(term))
