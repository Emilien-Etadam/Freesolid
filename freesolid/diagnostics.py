"""Installation diagnostics.

Purpose: close the loop on the ``verified=False`` parameter paths without
needing FreeCAD in CI. The user runs one command on a real install; the
report says, for every preference row, whether the key exists on that build
and whether its value matches — a wrong path shows up as ABSENT instead of
pretending to be applied. The report is plain text, made to be pasted back
into an issue or a conversation.

``param_state`` and ``collect`` take an injected ``param_get`` so the logic
is unit-testable with a fake; only ``full_report``/``show_dialog`` touch
FreeCAD and Qt.
"""

from . import prefs as prefs_mod

#: Getter name and two distinct defaults per kind. Reading a key twice with
#: different defaults is the only way FreeCAD's ParamGet API reveals whether
#: a key exists: an absent key returns each default verbatim.
_PROBES = {
    "bool": ("GetBool", (True, False)),
    "int": ("GetInt", (1, 2)),
    "float": ("GetFloat", (1.0, 2.0)),
    "str": ("GetString", ("\x00probe-a", "\x00probe-b")),
}


def param_state(group, kind: str, key: str):
    """Return ``("set", value)`` or ``("absent", None)`` for one key."""
    getter, (default_a, default_b) = _PROBES[kind]
    first = getattr(group, getter)(key, default_a)
    second = getattr(group, getter)(key, default_b)
    if first != second:
        return ("absent", None)
    return ("set", first)


def collect(param_get):
    """Probe every preference row. Returns a list of report dicts."""
    rows = []
    for pref in prefs_mod.PREFS:
        try:
            group = param_get("User parameter:" + pref.path)
            state, value = param_state(group, pref.kind, pref.key)
        except Exception as exc:  # noqa: BLE001 - the report is the handler
            rows.append({"pref": pref, "state": "error", "value": str(exc),
                         "match": False})
            continue
        rows.append({
            "pref": pref,
            "state": state,
            "value": value,
            "match": state == "set" and value == pref.value,
        })
    return rows


def render_report(rows, extras: str = "") -> str:
    """Human-readable report, stable enough to be pasted and diffed."""
    lines = ["=== Diagnostic FreeSolid ===", ""]
    matches = absents = diffs = 0
    for row in rows:
        pref = row["pref"]
        where = "{}/{}".format(pref.path, pref.key)
        if row["state"] == "error":
            tag, detail = "ERREUR", row["value"]
        elif row["state"] == "absent":
            tag, detail = "ABSENT", "attendu: {!r}".format(pref.value)
            absents += 1
        elif row["match"]:
            tag, detail = "OK", repr(row["value"])
            matches += 1
        else:
            tag = "DIFFÈRE"
            detail = "{!r} (attendu: {!r})".format(row["value"], pref.value)
            diffs += 1
        note = "" if pref.verified else "  [chemin non vérifié]"
        lines.append("[{:>7}] {} = {}{}".format(tag, where, detail, note))
    lines += ["",
              "{} OK, {} absent(s), {} différent(s) sur {} réglages".format(
                  matches, absents, diffs, len(rows))]
    if extras:
        lines += ["", extras]
    lines.append("")
    return "\n".join(lines)


def _gui_extras() -> str:
    """Environment census: versions, docks, workbenches. Best-effort."""
    parts = []
    try:
        import FreeCAD as App
        parts.append("FreeCAD : " + ".".join(str(v) for v in App.Version()[:3]))
    except Exception:
        pass
    try:
        import FreeCADGui as Gui
        from .compat import QtWidgets
        docks = Gui.getMainWindow().findChildren(QtWidgets.QDockWidget)
        parts.append("Panneaux :")
        for dock in docks:
            parts.append("  - {} ({}) {}".format(
                dock.objectName() or "?", dock.windowTitle(),
                "visible" if dock.isVisible() else "masqué"))
        parts.append("Ateliers : {} enregistrés".format(
            len(Gui.listWorkbenches())))
    except Exception:
        pass
    return "\n".join(parts)


def full_report() -> str:
    """The report the Diagnostics command shows — needs FreeCAD."""
    import FreeCAD as App
    return render_report(collect(App.ParamGet), _gui_extras())


def show_dialog(text: str):
    """Read-only, copyable report window (a message box is not copyable)."""
    from .compat import QtWidgets, QtGui
    import FreeCADGui as Gui
    dialog = QtWidgets.QDialog(Gui.getMainWindow())
    dialog.setWindowTitle("Diagnostic FreeSolid")
    layout = QtWidgets.QVBoxLayout(dialog)
    view = QtWidgets.QPlainTextEdit(text, dialog)
    view.setReadOnly(True)
    view.setFont(QtGui.QFontDatabase.systemFont(
        QtGui.QFontDatabase.FixedFont))
    layout.addWidget(view)
    hint = QtWidgets.QLabel(
        "Copiez ce rapport tel quel pour vérifier les chemins de paramètres.",
        dialog)
    hint.setWordWrap(True)
    layout.addWidget(hint)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Close, dialog)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.resize(640, 480)
    dialog.exec()
