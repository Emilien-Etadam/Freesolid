"""Récapitulatif d'autotest — pur Python, sans FreeCAD."""

from engine.kernel import selftest_summary


def test_selftest_summary_empty():
    assert selftest_summary({}) == {
        "verifications": 0, "ok": 0, "echecs": [],
    }
    assert selftest_summary(None) == {
        "verifications": 0, "ok": 0, "echecs": [],
    }


def test_selftest_summary_all_green():
    assert selftest_summary({"a": True, "b": True}) == {
        "verifications": 2, "ok": 2, "echecs": [],
    }


def test_selftest_summary_lists_failures():
    summary = selftest_summary({"a": True, "b": False, "c": False})
    assert summary["verifications"] == 3
    assert summary["ok"] == 1
    assert summary["echecs"] == ["b", "c"]


def test_selftest_summary_ignores_non_bools():
    summary = selftest_summary({
        "ok_flag": True,
        "steps": ["ping", "bilan"],
        "mesh_faces": 12,
        "nested": {"inner": False},
        "bilan": {"verifications": 1, "ok": 1, "echecs": []},
        "bad": False,
    })
    assert summary == {
        "verifications": 2,
        "ok": 1,
        "echecs": ["bad"],
    }
