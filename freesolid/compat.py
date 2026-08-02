"""PySide2/PySide6 compatibility shim.

FreeCAD 1.0+ ships PySide6; older builds and some AppImages still carry
PySide2. Import Qt through this module rather than directly.
"""

try:
    from PySide6 import QtWidgets, QtCore, QtGui  # noqa: F401
    PYSIDE_VERSION = 6
except ImportError:  # pragma: no cover - depends on the host FreeCAD build
    from PySide2 import QtWidgets, QtCore, QtGui  # noqa: F401
    PYSIDE_VERSION = 2
