"""One-shot window arrangement: put everything where SolidWorks puts it.

Applied by the Setup command. Works directly on the live QMainWindow instead
of guessing parameter keys: FreeCAD persists the window state (dock
positions, visibility) on exit, so an arrangement done once survives
restarts — the same mechanism that already keeps the FeatureManager where
the user left it.

Target arrangement:

- left column: model tree, FeatureManager tabbed with it, properties below
  — the FeatureManager/PropertyManager stack;
- top area: the "Fonctions" strip (CommandManager);
- hidden: Python console, Report view, Selection view — open on demand via
  View > Panels, never part of the default chrome;
- toolbars that duplicate what the strip or the menus already offer are
  collapsed to reduce FreeCAD's three-row toolbar noise.
"""

from ..compat import QtWidgets, QtCore

Qt = QtCore.Qt

#: Docks hidden by default. objectName, as reported by the diagnostics census.
_HIDE_DOCKS = ("Python console", "Report view", "Selection view", "DAG view")

#: Toolbars kept visible. Everything else is hidden — the strip and the
#: menus cover it. Identified by windowTitle because FreeCAD's toolbar
#: objectNames vary with locale and version.
_KEEP_TOOLBARS = ("File", "Fichier", "Edit", "Édition", "View", "Affichage",
                  "FreeSolid", "Fonctions")


def _main_window():
    import FreeCADGui as Gui
    return Gui.getMainWindow()


def _dock(main_window, object_name):
    return main_window.findChild(QtWidgets.QDockWidget, object_name)


def apply_solidworks_layout():
    """Arrange docks and toolbars. Returns a report of what moved."""
    main_window = _main_window()
    done = []

    tree = _dock(main_window, "Tree view")
    properties = _dock(main_window, "Property view")

    from .feature_manager import get_feature_manager
    fm = get_feature_manager()

    if tree is not None:
        main_window.addDockWidget(Qt.LeftDockWidgetArea, tree)
        tree.show()
        done.append("arbre du modèle à gauche")
    if fm is not None:
        main_window.addDockWidget(Qt.LeftDockWidgetArea, fm)
        if tree is not None:
            # Tabbed like SolidWorks' FeatureManager tab strip, with the
            # FeatureManager presentation on top.
            main_window.tabifyDockWidget(tree, fm)
        fm.show()
        fm.raise_()
        done.append("FeatureManager en onglet sur l'arbre")
    if properties is not None:
        main_window.addDockWidget(Qt.LeftDockWidgetArea, properties)
        anchor = fm or tree
        if anchor is not None:
            main_window.splitDockWidget(anchor, properties, Qt.Vertical)
        properties.show()
        done.append("propriétés sous l'arbre")

    from .functions_panel import get_functions_panel
    if get_functions_panel() is not None:
        done.append("bandeau Fonctions en haut")

    for name in _HIDE_DOCKS:
        dock = _dock(main_window, name)
        if dock is not None and dock.isVisible():
            dock.hide()
            done.append("{} masqué".format(name))

    hidden = 0
    for toolbar in main_window.findChildren(QtWidgets.QToolBar):
        title = toolbar.windowTitle()
        if not title:
            continue  # internal/unnamed bars are not ours to manage
        if title not in _KEEP_TOOLBARS and toolbar.isVisible():
            toolbar.hide()
            hidden += 1
    if hidden:
        done.append("{} barres d'outils repliées".format(hidden))

    return done
