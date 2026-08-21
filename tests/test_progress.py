"""Avancement hors noyau — ``progress`` ne prend pas ``_KERNEL_LOCK``.

Pur Python : aucun FreeCAD. ``FREESOLID_NO_SERVE`` est posé avant l'import
de ``engine.server`` pour éviter d'ouvrir le port.
"""

import os
import threading
import time
from pathlib import Path

import pytest

os.environ["FREESOLID_NO_SERVE"] = "1"

from engine import kernel as kernel_mod                               # noqa: E402
from engine.kernel import Kernel                                      # noqa: E402
from engine import server                                             # noqa: E402


@pytest.fixture(autouse=True)
def _reset_progress():
    server._set_progress(**server._idle_progress())
    server._KERNEL._progress = None
    yield
    server._set_progress(**server._idle_progress())
    server._KERNEL._progress = None


def test_progress_op_declared():
    from engine import protocol
    assert protocol.OPS["progress"] == ()
    op, params = protocol.validate_request({"op": "progress"})
    assert op == "progress"
    assert params == {}


def test_progress_idle_snapshot():
    snapshot = server._progress_snapshot()
    assert snapshot == {
        "op": None, "phase": "", "fait": 0, "total": 0, "depuis": 0.0,
    }


def test_kernel_progress_callback_is_a_no_op_without_transport():
    k = Kernel()
    k._report_progress("Soustraire", 3, 10)
    seen = []
    k._progress = lambda phase, fait=0, total=0: seen.append(
        (phase, fait, total))
    k._report_progress("Construction du compound", 47, 200)
    assert seen == [("Construction du compound", 47, 200)]


def test_kernel_progress_swallows_callback_errors():
    k = Kernel()

    def boom(*_args, **_kwargs):
        raise RuntimeError("transport hs")

    k._progress = boom
    k._report_progress("Maillage")


def test_kernel_does_not_import_the_server():
    source = Path(kernel_mod.__file__).read_text(encoding="utf-8")
    assert "from engine import server" not in source
    assert "import engine.server" not in source


def test_progress_does_not_call_dispatch(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("progress ne doit pas passer par le noyau")
    monkeypatch.setattr(kernel_mod, "dispatch", boom)
    response = server.run_op("progress", {})
    assert response["ok"] is True
    assert response["result"]["op"] is None


def test_progress_responds_while_kernel_lock_held():
    """Non-régression : si progress prend le verrou, il attend le booléen.

    Un fil tient ``_KERNEL_LOCK`` jusqu'à 1 s. ``progress`` doit répondre
    tout de suite, avec la phase en cours.
    """
    release = threading.Event()
    holding = threading.Event()

    def hold_lock():
        with server._KERNEL_LOCK:
            server._set_progress(
                op="add_boolean",
                phase="Soustraire",
                fait=0,
                total=0,
                depuis=1.5,
            )
            holding.set()
            release.wait(timeout=1.0)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    assert holding.wait(timeout=1.0)

    started = time.monotonic()
    try:
        response = server.run_op("progress", {})
    finally:
        release.set()
        thread.join(timeout=2.0)
    elapsed = time.monotonic() - started

    assert elapsed < 0.2, (
        "progress a attendu le verrou noyau ({:.3f} s) — "
        "il ne doit pas le prendre".format(elapsed))
    assert response["ok"] is True
    result = response["result"]
    assert result["op"] == "add_boolean"
    assert result["phase"] == "Soustraire"
    assert result["fait"] == 0
    assert result["total"] == 0
    assert result["depuis"] == 1.5


def test_run_op_feeds_progress_then_clears(monkeypatch):
    seen = []

    def fake_dispatch(kernel, op, params):
        seen.append(op)
        assert kernel._progress is server._feed_progress
        kernel._progress("Construction du compound", 47, 200)
        snapshot = server._progress_snapshot()
        assert snapshot["op"] == "add_boolean"
        assert snapshot["phase"] == "Construction du compound"
        assert snapshot["fait"] == 47
        assert snapshot["total"] == 200
        assert snapshot["depuis"] > 0
        return {"ok": True, "result": {"tree": True}}

    monkeypatch.setattr(kernel_mod, "dispatch", fake_dispatch)
    response = server.run_op("add_boolean", {"tool": "Semis"})
    assert response == {"ok": True, "result": {"tree": True}}
    assert seen == ["add_boolean"]
    idle = server._progress_snapshot()
    assert idle["op"] is None
    assert idle["phase"] == ""
    assert server._KERNEL._progress is None
