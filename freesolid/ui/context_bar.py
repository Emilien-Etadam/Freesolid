"""The "S" contextual bar — a SolidWorks-style shortcut palette at the cursor.

A frameless popup that appears where the cursor is, offering the commands
that make sense for the current selection (see ``freesolid.context``), and
closing on any outside click or Escape — Qt's ``Popup`` window flag gives
both behaviours for free.

Buttons wrap the QActions FreeCAD registered for our alias commands, so
icons, tooltips and enabled-state come along without duplication; when an
action is not found (command not yet materialised as a QAction), the button
falls back to running the command by name.
"""

from ..compat import QtWidgets, QtCore, QtGui
from ..context import classify, commands_for, subelement_kind
from ..vocab import BY_COMMAND

Qt = QtCore.Qt

# PySide6 moved QAction from QtWidgets to QtGui.
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction

_bar = None


def _gui():
    import FreeCADGui as Gui
    return Gui


def current_context():
    """Classify the live FreeCAD selection into a bar context."""
    Gui = _gui()
    kinds = []
    try:
        for sel in Gui.Selection.getSelectionEx():
            if sel.SubElementNames:
                kinds.extend(subelement_kind(n) for n in sel.SubElementNames)
            elif getattr(sel.Object, "TypeId", "") == "Sketcher::SketchObject":
                kinds.append("sketch")
            else:
                kinds.append("object")
    except Exception:
        return "none"
    return classify(kinds)


class ContextBar(QtWidgets.QWidget):
    """One row of tool buttons, rebuilt from the selection on each show."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("FreeSolid_ContextBar")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _label_of(self, name):
        """Designer-facing label for a FreeSolid alias command name."""
        pd_name = "PartDesign_" + name.split("_", 1)[1]
        term = BY_COMMAND.get(pd_name)
        return term.fr if term else name

    def rebuild(self):
        self._clear()
        Gui = _gui()
        main_window = Gui.getMainWindow()
        for name in commands_for(current_context()):
            button = QtWidgets.QToolButton(self)
            button.setIconSize(QtCore.QSize(24, 24))
            button.setAutoRaise(True)
            action = main_window.findChild(QAction, name)
            if action is not None and not action.icon().isNull():
                button.setDefaultAction(action)
            else:
                # No QAction yet (toolbar not built in this session):
                # degrade to a text button that runs the command by name.
                button.setText(self._label_of(name))
                button.clicked.connect(
                    lambda _=False, n=name: _gui().runCommand(n, 0))
            button.setToolTip(self._label_of(name))
            # A popup does not close on inside clicks; do it ourselves so the
            # bar behaves like a menu, not like a parked toolbar.
            button.clicked.connect(self.hide)
            self._layout.addWidget(button)

    def popup_at_cursor(self):
        self.rebuild()
        self.adjustSize()
        # Slightly up-left so the first button sits under the cursor.
        self.move(QtGui.QCursor.pos() - QtCore.QPoint(18, 18))
        self.show()


def show_at_cursor():
    """Show the singleton bar at the mouse position (the "S" entry point)."""
    global _bar
    if _bar is None:
        _bar = ContextBar(_gui().getMainWindow())
    _bar.popup_at_cursor()
