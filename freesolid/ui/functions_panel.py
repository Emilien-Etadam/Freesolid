"""The "Fonctions" strip — a CommandManager-shaped panel that never vanishes.

FreeCAD toolbars belong to a workbench: switch workbench, lose the toolbar.
That churn is the single biggest "this is not SolidWorks" signal, because the
CommandManager never goes away. Docks, however, are global — the
FeatureManager dock survives every switch. So the command strip is built as
a dock in the TOP area: one row of icon+text buttons, SolidWorks names,
visible in PartDesign, Sketcher, Assembly alike.

Buttons run commands by name through ``Gui.runCommand`` and pull their
icon/label/tooltip from ``Gui.Command.get(...).getInfo()`` — no dependency on
QActions that only exist while the FreeSolid workbench is active.
"""

from ..compat import QtWidgets, QtCore

Qt = QtCore.Qt

_panel = None

#: Buttons, in CommandManager order. None = a separator.
_BUTTONS = (
    "FreeSolid_NewPart",
    None,
    "FreeSolid_NewSketch",
    "FreeSolid_Pad",
    "FreeSolid_Pocket",
    "FreeSolid_Revolution",
    "FreeSolid_Groove",
    "FreeSolid_AdditivePipe",
    "FreeSolid_AdditiveLoft",
    "FreeSolid_Hole",
    None,
    "FreeSolid_Fillet",
    "FreeSolid_Chamfer",
    "FreeSolid_Draft",
    "FreeSolid_Thickness",
    None,
    "FreeSolid_LinearPattern",
    "FreeSolid_PolarPattern",
    "FreeSolid_Mirrored",
)


def _gui():
    import FreeCADGui as Gui
    return Gui


class FunctionsPanel(QtWidgets.QDockWidget):
    """One horizontal row of commands, docked to the top area."""

    def __init__(self, parent=None):
        super().__init__("Fonctions", parent)
        self.setObjectName("FreeSolid_Functions")
        # No float/close decorations: the CommandManager is furniture, not a
        # palette. Still closable through the View > Panels menu.
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)

        body = QtWidgets.QWidget(self)
        self._layout = QtWidgets.QHBoxLayout(body)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setWidget(scroll)

        self.rebuild()

    def _button(self, name):
        Gui = _gui()
        button = QtWidgets.QToolButton(self)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QtCore.QSize(24, 24))
        button.setAutoRaise(True)
        label = tooltip = name
        try:
            info = Gui.Command.get(name).getInfo()
            label = info.get("menuText", name).replace("&", "")
            tooltip = info.get("toolTip", "") or label
            pixmap = info.get("pixmap", "")
            if pixmap:
                button.setIcon(Gui.getIcon(pixmap))
        except Exception:
            pass
        # SolidWorks wraps its button captions on two short lines; a QToolButton
        # does not wrap, so keep the first word group only when it gets long.
        button.setText(label if len(label) <= 18 else label.split(" ")[0])
        button.setToolTip(tooltip)
        button.clicked.connect(lambda _=False, n=name: _gui().runCommand(n, 0))
        return button

    def rebuild(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for name in _BUTTONS:
            if name is None:
                separator = QtWidgets.QFrame(self)
                separator.setFrameShape(QtWidgets.QFrame.VLine)
                separator.setFrameShadow(QtWidgets.QFrame.Sunken)
                self._layout.addWidget(separator)
            else:
                self._layout.addWidget(self._button(name))
        self._layout.addStretch(1)


def get_functions_panel(create=True):
    """Return the singleton panel, docking it to the top area on creation."""
    global _panel
    if _panel is None and create:
        main_window = _gui().getMainWindow()
        _panel = FunctionsPanel(main_window)
        main_window.addDockWidget(Qt.TopDockWidgetArea, _panel)
    return _panel
