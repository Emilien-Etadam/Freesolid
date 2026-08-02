"""Error reporting to FreeCAD's Report view.

Lives in the package rather than in InitGui.py on purpose: FreeCAD exec()s
Init scripts with separate globals/locals dicts, so a helper defined there
cannot see the module-level names it needs. Imported inside methods, this one
resolves normally.
"""

import sys
import traceback


def report(what, exc_info=True, addon_dir=None):
    """Print a failure where the user will actually find it.

    Args:
        what: one-line description of what failed, in user terms.
        exc_info: append the current traceback. Only meaningful inside an
            ``except`` block.
        addon_dir: installation directory, appended as a diagnostic when
            known — a wrong path is the most common cause of an addon that
            loads in the file system but not in Python.

    Returns:
        The formatted message, so callers (and tests) can inspect it.
    """
    message = "FreeSolid: {}\n".format(what)
    if exc_info:
        message += traceback.format_exc()
    if addon_dir:
        message += "  addon dir : {}\n".format(addon_dir)
        message += "  sys.path  : {}\n".format(
            "présent" if addon_dir in sys.path else "ABSENT")
    try:
        import FreeCAD as App
        App.Console.PrintError(message)
    except Exception:
        # Outside FreeCAD (tests, tooling) stderr is the right place.
        sys.stderr.write(message)
    return message
