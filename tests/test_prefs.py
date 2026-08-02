"""Preference table integrity and application — runs without FreeCAD."""

import pytest

from freesolid import prefs


class FakeGroup:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def _set(self, key, value):
        self._store[(self._path, key)] = value

    SetBool = SetInt = SetFloat = SetString = _set


class FakeParams:
    """Stands in for FreeCAD.ParamGet."""

    def __init__(self, failing_paths=()):
        self.store = {}
        self._failing = set(failing_paths)

    def __call__(self, full_path):
        path = full_path.removeprefix("User parameter:")
        if path in self._failing:
            raise RuntimeError("no such parameter group")
        return FakeGroup(self.store, path)


def test_kinds_are_supported():
    assert {p.kind for p in prefs.PREFS} <= {"bool", "int", "float", "str"}


def test_rows_are_unique():
    keys = [(p.path, p.key) for p in prefs.PREFS]
    assert len(keys) == len(set(keys))


def test_every_row_explains_itself():
    # The Setup command shows `why` verbatim to the user.
    for pref in prefs.PREFS:
        assert len(pref.why) > 20, (pref.path, pref.key)


def test_paths_are_relative_to_user_parameter():
    for pref in prefs.PREFS:
        assert pref.path.startswith("BaseApp/Preferences/"), pref.path


def test_apply_all_writes_every_row():
    params = FakeParams()
    applied, failed = prefs.apply_all(params)
    assert not failed
    assert len(applied) == len(prefs.PREFS)
    assert params.store[("BaseApp/Preferences/View", "NavigationStyle")] == \
        "Gui::BlenderNavigationStyle"


def test_apply_all_reports_failures_without_raising():
    params = FakeParams(failing_paths={"BaseApp/Preferences/View"})
    applied, failed = prefs.apply_all(params)
    assert failed
    assert all(p.path == "BaseApp/Preferences/View" for p, _ in failed)
    # A bad path must not stop the remaining rows.
    assert len(applied) == len(prefs.PREFS) - len(failed)


def test_unverified_rows_are_declared():
    # These are written from documentation rather than checked on a build;
    # the Setup command surfaces them so a wrong key is visible.
    assert prefs.unverified()
    assert all(not p.verified for p in prefs.unverified())


def test_layout_rows_split_the_tree_out_of_the_combo_view():
    layout = {(p.path, p.key): p.value for p in prefs.by_tag("layout")}
    assert layout[("BaseApp/Preferences/DockWindows/ComboView", "Enabled")] is False
    assert layout[("BaseApp/Preferences/DockWindows/TreeView", "Enabled")] is True


@pytest.mark.parametrize("wb", ["PartDesignWorkbench", "AssemblyWorkbench",
                                "TechDrawWorkbench", "SketcherWorkbench"])
def test_essential_workbenches_are_kept(wb):
    assert wb in prefs.KEEP_WORKBENCHES
