"""Diagnostics probing and report — runs without FreeCAD."""

from freesolid import diagnostics, prefs


class FakeGroup:
    """ParamGet group where absent keys return the caller's default."""

    def __init__(self, store, path):
        self._store = store
        self._path = path

    def _get(self, key, default):
        return self._store.get((self._path, key), default)

    GetBool = GetInt = GetFloat = GetString = GetUnsigned = _get


class FakeParams:
    def __init__(self, store=None, failing=()):
        self.store = store or {}
        self._failing = set(failing)

    def __call__(self, full_path):
        path = full_path.removeprefix("User parameter:")
        if path in self._failing:
            raise RuntimeError("boom")
        return FakeGroup(self.store, path)


def _stored_everything():
    return {(p.path, p.key): p.value for p in prefs.PREFS}


def test_probe_defaults_are_freecad_safe():
    # FreeCAD rejects NUL bytes in GetString defaults with "embedded null
    # character" (seen on 1.1.3) — sentinels must be plain distinct text.
    for kind, (_, (default_a, default_b)) in diagnostics._PROBES.items():
        assert default_a != default_b, kind
        for default in (default_a, default_b):
            if isinstance(default, str):
                assert "\x00" not in default, kind


def test_absent_keys_are_detected():
    rows = diagnostics.collect(FakeParams())          # empty store
    assert all(r["state"] == "absent" for r in rows)
    assert not any(r["match"] for r in rows)


def test_matching_values_are_detected():
    rows = diagnostics.collect(FakeParams(_stored_everything()))
    assert all(r["state"] == "set" and r["match"] for r in rows)


def test_diverging_value_is_flagged_not_matched():
    store = _stored_everything()
    first = prefs.PREFS[0]
    store[(first.path, first.key)] = "something-else"
    rows = diagnostics.collect(FakeParams(store))
    row = next(r for r in rows if r["pref"] is first)
    assert row["state"] == "set" and not row["match"]


def test_probe_errors_become_report_rows():
    failing = {prefs.PREFS[0].path}
    rows = diagnostics.collect(FakeParams(failing=failing))
    assert any(r["state"] == "error" for r in rows)
    assert len(rows) == len(prefs.PREFS)   # an error never truncates


def test_report_mentions_every_path_and_flags_unverified():
    rows = diagnostics.collect(FakeParams(_stored_everything()))
    text = diagnostics.render_report(rows, extras="FreeCAD : x.y.z")
    for pref in prefs.PREFS:
        assert pref.key in text
    assert "[chemin non vérifié]" in text     # unverified rows are marked
    assert "FreeCAD : x.y.z" in text          # extras land at the end
    assert "OK" in text


def test_report_counts_are_consistent():
    store = _stored_everything()
    removed = prefs.PREFS[-1]
    del store[(removed.path, removed.key)]
    text = diagnostics.render_report(diagnostics.collect(FakeParams(store)))
    assert "{} OK, 1 absent(s), 0 différent(s) sur {} réglages".format(
        len(prefs.PREFS) - 1, len(prefs.PREFS)) in text
