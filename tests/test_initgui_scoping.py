"""Guard against FreeCAD's Init-script scoping trap.

FreeCAD exec()s InitGui.py with separate globals and locals dicts: names
bound at the top level go into locals, while function and method bodies
resolve names against globals. A method that reads a module-level name
therefore raises ``NameError`` at initialization and the workbench silently
never registers — which is exactly what happened in 0.1.0-alpha.

These tests read InitGui.py as an AST rather than importing it, because
importing it requires FreeCAD.
"""

import ast
import pathlib

import pytest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "InitGui.py"

_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@pytest.fixture(scope="module")
def tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _module_scope_nodes(node):
    """Yield every node at module scope, not descending into def/class."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_BOUNDARIES):
            continue
        yield child
        yield from _module_scope_nodes(child)


def _bound_names(nodes):
    names = set()
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


def test_no_module_level_functions(tree):
    # A helper defined here could not see the constants it needs.
    offenders = [n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert not offenders, (
        "InitGui.py must stay straight-line; move these into the freesolid "
        "package: {}".format(offenders))


def test_methods_never_read_module_level_names(tree):
    module_names = _bound_names(_module_scope_nodes(tree))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local = _bound_names(ast.walk(node))
        local.update(a.arg for a in node.args.args)
        local.update(a.arg for a in node.args.kwonlyargs)
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
                    and sub.id in module_names and sub.id not in local):
                offenders.append("{}() reads module-level '{}'".format(
                    node.name, sub.id))

    assert not offenders, (
        "These would raise NameError under FreeCAD's exec() scoping; import "
        "them inside the method instead: {}".format(offenders))


def test_registration_is_guarded(tree):
    # addWorkbench must sit inside a try, or a failure is invisible again.
    guarded = any(
        isinstance(node, ast.Try)
        and any(isinstance(n, ast.Attribute) and n.attr == "addWorkbench"
                for n in ast.walk(node))
        for node in tree.body)
    assert guarded, "Gui.addWorkbench() must be wrapped in try/except"
