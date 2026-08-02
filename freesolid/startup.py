"""Deferred startup work.

The Fonctions strip and the FeatureManager dock must exist in every session,
whatever workbench FreeCAD starts in — a user seen on 1.1.3 restarted into
PartDesign and both were simply absent, because they were only instantiated
when the FreeSolid workbench was activated.

Creation is deferred one event-loop turn: at InitGui time the main window
exists but is not fully assembled, and dock geometry restore happens after.

This lives in the package (not InitGui.py) because of FreeCAD's Init-script
scoping: a function defined in InitGui.py cannot see that file's own
module-level names.
"""


def defer_panels():
    """Schedule panel creation for when the event loop is running."""
    from .compat import QtCore
    QtCore.QTimer.singleShot(0, _create_panels)


def _create_panels():
    try:
        from .ui.functions_panel import get_functions_panel
        from .ui.feature_manager import get_feature_manager
        get_functions_panel()
        get_feature_manager()
    except Exception:
        from .log import report
        report("panneaux non créés au démarrage")
