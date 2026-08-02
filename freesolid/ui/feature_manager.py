"""A FeatureManager-shaped view of the active PartDesign Body.

Why a second tree rather than restyling FreeCAD's own:

- FreeCAD greys out every feature except the Tip, because only one solid is
  displayed at a time. In SolidWorks greyed means *suppressed*, so the native
  tree reads as "everything is broken" to a designer coming from there. This
  tree never greys a healthy feature.
- The Tip is shown as a rollback bar, which is the mental model it actually
  implements.
- Origin planes are labelled Face / Dessus / Droite instead of XZ / XY / YZ.

Read-mostly: the only mutation offered is moving the rollback bar, which maps
onto ``Body.Tip``. Everything else defers to FreeCAD's own commands.
"""

from ..compat import QtWidgets, QtCore, QtGui
from ..vocab import label_for_type, label_for_origin

Qt = QtCore.Qt

_ROLE_OBJ = Qt.UserRole + 1
_ROLE_KIND = Qt.UserRole + 2

_dock = None


def _gui():
    import FreeCADGui as Gui
    return Gui


def _app():
    import FreeCAD as App
    return App


def active_body():
    """Return the active PartDesign Body, or the only one in the document.

    Returns ``None`` when there is no document, or when the document holds
    several Bodies and none is active — guessing would be worse than showing
    an explicit prompt.
    """
    App, Gui = _app(), _gui()
    doc = App.ActiveDocument
    if doc is None:
        return None
    try:
        view = Gui.ActiveDocument.ActiveView
        body = view.getActiveObject("pdbody")
        if body is not None:
            return body
    except Exception:
        pass
    bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
    return bodies[0] if len(bodies) == 1 else None


def _origin_children(body):
    """Return the Origin's planes and axes, across FreeCAD API variations."""
    origin = getattr(body, "Origin", None)
    if origin is None:
        return []
    for attr in ("OriginFeatures", "Group", "OutList"):
        items = getattr(origin, attr, None)
        if items:
            return list(items)
    return []


def _features(body):
    """Ordered PartDesign features of the Body, excluding Origin and sketches.

    ``Body.Group`` is in creation order, which is exactly the chronological
    order a FeatureManager shows.
    """
    out = []
    for obj in getattr(body, "Group", []) or []:
        try:
            if obj.isDerivedFrom("PartDesign::Feature"):
                out.append(obj)
        except Exception:
            continue
    return out


def _profile_of(feature):
    """Best-effort sketch behind a feature, or ``None``.

    ``Profile`` is a link-sub on most additive/subtractive features and a
    plain link on others; older types expose ``Sketch``.
    """
    for attr in ("Profile", "Sketch"):
        value = getattr(feature, attr, None)
        if value is None:
            continue
        if isinstance(value, (tuple, list)) and value:
            value = value[0]
        if hasattr(value, "TypeId"):
            return value
    return None


class FeatureManagerDock(QtWidgets.QDockWidget):
    """Dock hosting the tree. Polls rather than observing the document.

    A document observer would be lighter, but it has to be registered
    globally and torn down reliably; for a read-mostly view a cheap signature
    poll is far less likely to leave a stale hook behind on unload.
    """

    POLL_MS = 400

    def __init__(self, parent=None):
        super().__init__("FeatureManager", parent)
        self.setObjectName("FreeSolid_FeatureManager")

        self._signature = None

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)

        self._hint = QtWidgets.QLabel(self)
        self._hint.setWordWrap(True)
        self._hint.setContentsMargins(8, 6, 8, 6)

        body = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._hint)
        layout.addWidget(self._tree, 1)
        self.setWidget(body)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._refresh_if_changed)
        self._timer.start()

        self._refresh_if_changed(force=True)

    # -- refresh ---------------------------------------------------------

    def _current_signature(self):
        body = active_body()
        if body is None:
            return None
        try:
            tip = body.Tip.Name if body.Tip else ""
            return (body.Name,
                    tip,
                    tuple((o.Name, o.Label) for o in _features(body)))
        except Exception:
            return None

    def _refresh_if_changed(self, force=False):
        try:
            signature = self._current_signature()
        except Exception:
            return
        if not force and signature == self._signature:
            return
        self._signature = signature
        try:
            self._rebuild()
        except Exception:
            # Never let a tree glitch take the dock — or FreeCAD — down.
            pass

    def _rebuild(self):
        self._tree.clear()
        body = active_body()
        if body is None:
            self._hint.setText(
                "Aucune pièce active. Utilisez « Nouvelle pièce », ou "
                "double-cliquez un Body dans l'arbre du modèle pour "
                "l'activer.")
            return
        self._hint.setText("")

        root = QtWidgets.QTreeWidgetItem(self._tree, [body.Label])
        root.setData(0, _ROLE_OBJ, body.Name)
        root.setData(0, _ROLE_KIND, "body")
        font = root.font(0)
        font.setBold(True)
        root.setFont(0, font)

        origin = QtWidgets.QTreeWidgetItem(root, ["Origine"])
        origin.setData(0, _ROLE_KIND, "group")
        for child in _origin_children(body):
            item = QtWidgets.QTreeWidgetItem(
                origin, [label_for_origin(child.Name)])
            item.setData(0, _ROLE_OBJ, child.Name)
            item.setData(0, _ROLE_KIND, "origin")

        features = _features(body)
        tip_name = body.Tip.Name if getattr(body, "Tip", None) else ""
        past_tip = False

        for feature in features:
            label = "{} — {}".format(
                label_for_type(feature.TypeId), feature.Label)
            item = QtWidgets.QTreeWidgetItem(root, [label])
            item.setData(0, _ROLE_OBJ, feature.Name)
            item.setData(0, _ROLE_KIND, "feature")

            if self._is_error(feature):
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#d13438")))
                item.setToolTip(0, "Fonction en erreur — double-cliquez pour "
                                   "l'éditer.")
            elif past_tip:
                # Rolled back: dimmed *and* labelled, so it is never confused
                # with FreeCAD's "merely not displayed" greying.
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#8a8a8a")))
                item.setToolTip(0, "Après la barre de retour arrière.")

            sketch = _profile_of(feature)
            if sketch is not None:
                sub = QtWidgets.QTreeWidgetItem(item, ["Esquisse — " + sketch.Label])
                sub.setData(0, _ROLE_OBJ, sketch.Name)
                sub.setData(0, _ROLE_KIND, "sketch")

            if feature.Name == tip_name:
                past_tip = True
                bar = QtWidgets.QTreeWidgetItem(
                    root, ["──────  barre de retour arrière  ──────"])
                bar.setData(0, _ROLE_KIND, "rollback")
                bar.setToolTip(0, "Double-cliquez une fonction pour amener la "
                                  "barre juste après elle.")
                bar_font = bar.font(0)
                bar_font.setItalic(True)
                bar.setFont(0, bar_font)

        self._tree.expandAll()

    @staticmethod
    def _is_error(obj):
        try:
            return bool(obj.State) and "Invalid" in obj.State
        except Exception:
            return False

    # -- interaction -----------------------------------------------------

    def _object_of(self, item):
        if item is None:
            return None
        name = item.data(0, _ROLE_OBJ)
        if not name:
            return None
        doc = _app().ActiveDocument
        return doc.getObject(name) if doc else None

    def _on_double_click(self, item, _column):
        kind = item.data(0, _ROLE_KIND)
        obj = self._object_of(item)
        if obj is None:
            return
        if kind == "feature":
            self.set_rollback(obj)
        elif kind == "sketch":
            try:
                _gui().ActiveDocument.setEdit(obj.Name)
            except Exception:
                pass

    def _on_menu(self, point):
        item = self._tree.itemAt(point)
        kind = item.data(0, _ROLE_KIND) if item else None
        menu = QtWidgets.QMenu(self)

        if kind == "feature":
            menu.addAction(
                "Amener la barre de retour ici",
                lambda: self.set_rollback(self._object_of(item)))
            menu.addAction(
                "Éditer",
                lambda: self._edit(self._object_of(item)))
        menu.addAction("Revenir à l'état final", self.rollback_to_end)

        menu.exec(self._tree.viewport().mapToGlobal(point))

    def _edit(self, obj):
        if obj is None:
            return
        try:
            _gui().ActiveDocument.setEdit(obj.Name)
        except Exception:
            pass

    def set_rollback(self, feature):
        """Move the rollback bar, i.e. set ``Body.Tip``."""
        body = active_body()
        if body is None or feature is None:
            return
        try:
            body.Tip = feature
            _app().ActiveDocument.recompute()
        except Exception:
            return
        self._refresh_if_changed(force=True)

    def rollback_to_end(self):
        body = active_body()
        if body is None:
            return
        features = _features(body)
        if features:
            self.set_rollback(features[-1])


def get_feature_manager(create=True):
    """Return the singleton dock, creating and docking it on first call."""
    global _dock
    if _dock is None and create:
        main_window = _gui().getMainWindow()
        _dock = FeatureManagerDock(main_window)
        main_window.addDockWidget(Qt.LeftDockWidgetArea, _dock)
    return _dock
