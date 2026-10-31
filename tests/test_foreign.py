"""Pièces d'un autre modeleur lues par OpenSW — partie pure, sans FreeCAD."""
from types import SimpleNamespace

import pytest

from engine import foreign, i18n
from engine.vendor.sldprt.parasolid import TEXT_PREAMBLE


def test_extensions_are_recognised_whatever_the_case():
    assert foreign.is_foreign("/pieces/fermoir.SLDPRT")
    assert foreign.is_foreign("cube.x_t") and foreign.is_foreign("cube.X_B")
    assert not foreign.is_foreign("cube.step")
    assert not foreign.is_foreign("sldprt")


def test_failure_reason_is_one_short_line():
    assert foreign.failure_reason(ValueError("bad\n  block")) == "ValueError: bad block"
    assert foreign.failure_reason(RuntimeError()) == "RuntimeError"
    assert len(foreign.failure_reason(ValueError("x" * 1000))) == 300


def test_damaged_part_is_refused_by_the_real_reader(tmp_path):
    part = tmp_path / "abime.SLDPRT"
    part.write_bytes(b"pas une piece")
    with pytest.raises(foreign.ForeignError) as refused:
        foreign.convert(part, tmp_path / "abime.step")
    message = str(refused.value)
    assert message.startswith("OpenSW n'a pas pu lire ce fichier : ContainerError: ")
    assert i18n.translate(message, "en").startswith(
        "OpenSW could not read this file: ContainerError: ")
    assert not (tmp_path / "abime.step").exists()


def test_truncated_parasolid_text_is_refused(tmp_path):
    part = tmp_path / "coupe.x_t"
    part.write_bytes(TEXT_PREAMBLE[:40])
    with pytest.raises(foreign.ForeignError, match="n'a pas pu lire"):
        foreign.convert(part, tmp_path / "coupe.step")


def test_convert_writes_the_step_with_the_part_name(tmp_path, monkeypatch):
    seen = {}

    def load(source):
        seen["source"] = source
        return "modèle"

    def write(model, path, *, name):
        seen.update(model=model, path=path, name=name)
        return SimpleNamespace(bodies=2, skipped_bodies=0)

    monkeypatch.setattr(foreign, "load_model", load)
    monkeypatch.setattr(foreign, "write_step", write)
    long_name = "bague " + "x" * 60
    report = foreign.convert("/p/" + long_name + ".SLDPRT", "/w/piece.step")
    assert report.bodies == 2
    assert seen == {"source": "/p/" + long_name + ".SLDPRT", "model": "modèle",
                    "path": "/w/piece.step", "name": long_name[:40]}
