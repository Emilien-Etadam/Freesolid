"""Pièces d'un autre modeleur lues par OpenSW — partie pure, sans FreeCAD."""
import os
import subprocess
from types import SimpleNamespace

import pytest

from engine import foreign, i18n


def _opensw(root):
    """Un dépôt OpenSW minimal : son convertisseur suffit."""
    script = root / "tools" / "convert.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    return script


def test_extensions_are_recognised_whatever_the_case():
    assert foreign.is_foreign("/pieces/fermoir.SLDPRT")
    assert foreign.is_foreign("cube.x_t") and foreign.is_foreign("cube.X_B")
    assert not foreign.is_foreign("cube.step")
    assert not foreign.is_foreign("sldprt")


def test_converter_from_the_variable_or_next_to_freesolid(tmp_path):
    script = _opensw(tmp_path / "ailleurs" / "OpenSW")
    repo = tmp_path / "Freesolid"
    repo.mkdir()
    # La variable désigne le dépôt, ou le script lui-même.
    for value in (str(script.parent.parent), str(script)):
        found = foreign.find_converter({foreign.READER_ENV: value}, repo)
        assert found == str(script)
    # Une variable fausse ne retombe pas sur un dépôt voisin.
    _opensw(tmp_path / "OpenSW")
    assert foreign.find_converter({foreign.READER_ENV: str(repo)}, repo) is None
    assert foreign.find_converter({}, repo) == str(
        tmp_path / "OpenSW" / "tools" / "convert.py")


def test_no_converter_anywhere(tmp_path):
    repo = tmp_path / "Freesolid"
    repo.mkdir()
    assert foreign.find_converter({}, repo) is None


def test_python_of_the_freecad_install_first(tmp_path):
    def nowhere(name):
        return None

    assert foreign.find_python({}, str(tmp_path), which=nowhere) is None
    windows = tmp_path / "python.exe"
    windows.write_text("", encoding="utf-8")
    assert foreign.find_python({}, str(tmp_path), which=nowhere) == str(windows)
    posix = tmp_path / "bin" / "python3"
    posix.parent.mkdir()
    posix.write_text("", encoding="utf-8")
    assert foreign.find_python({}, str(tmp_path), which=nowhere) == str(posix)
    # Le PATH en dernier recours, la variable avant tout.
    empty = tmp_path / "vide"
    empty.mkdir()
    assert foreign.find_python(
        {}, str(empty), which=lambda name: "/usr/bin/" + name) == "/usr/bin/python3"
    assert foreign.find_python(
        {foreign.PYTHON_ENV: str(windows)}, str(tmp_path)) == str(windows)
    assert foreign.find_python(
        {foreign.PYTHON_ENV: str(tmp_path / "absent")}, str(tmp_path)) is None


def test_command_asks_for_step_only_in_the_work_folder():
    command = foreign.convert_command("py", "convert.py", "/p/a.SLDPRT", "/w")
    assert command == ["py", "convert.py", "--step", "--force", "-o", "/w",
                       "/p/a.SLDPRT"]
    assert foreign.expected_output("/w", "/p/bague v2.x_t") == os.path.join(
        "/w", "bague v2.STEP")


def test_failure_reason_keeps_the_last_line_without_the_file_name():
    stderr = "avertissement\nfermoir.SLDPRT → .STEP: LoadError: no Parasolid partition found\n"
    assert foreign.failure_reason(stderr, 1) == "LoadError: no Parasolid partition found"
    assert foreign.failure_reason("", 2) == "code de sortie 2"
    assert len(foreign.failure_reason("x" * 1000, 1)) == 300


def _setup(tmp_path):
    script = _opensw(tmp_path / "OpenSW")
    repo = tmp_path / "Freesolid"
    repo.mkdir()
    python = tmp_path / "env" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    work = tmp_path / "travail"
    work.mkdir()
    return script, repo, str(tmp_path / "env"), work


def test_convert_runs_the_reader_apart_and_returns_its_step(tmp_path):
    script, repo, prefix, work = _setup(tmp_path)
    seen = {}

    def run(command, **options):
        seen.update(command=command, **options)
        (work / "cube.STEP").write_text("ISO-10303-21;", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    step = foreign.convert("/pieces/cube.SLDPRT", str(work), environ={},
                           repo_root=repo, prefix=prefix, run=run)
    assert step == str(work / "cube.STEP")
    assert seen["command"][:2] == [os.path.join(prefix, "bin", "python3"),
                                   str(script)]
    assert seen["cwd"] == str(work)
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"
    assert seen["timeout"] == foreign.TIMEOUT_S


def test_convert_failures_say_what_to_do(tmp_path):
    script, repo, prefix, work = _setup(tmp_path)

    def refused(command, **options):
        return SimpleNamespace(
            returncode=1, stdout="",
            stderr="cube.SLDPRT → .STEP: StepError: no body could be written\n")

    with pytest.raises(foreign.ForeignError) as failed:
        foreign.convert("cube.SLDPRT", str(work), environ={},
                        repo_root=repo, prefix=prefix, run=refused)
    assert str(failed.value) == (
        "OpenSW n'a pas pu lire ce fichier : StepError: no body could be written")

    def silent(command, **options):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(foreign.ForeignError, match="code de sortie 0"):
        foreign.convert("cube.SLDPRT", str(work), environ={},
                        repo_root=repo, prefix=prefix, run=silent)

    def slow(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])

    with pytest.raises(foreign.ForeignError, match="au bout de 5 s"):
        foreign.convert("cube.SLDPRT", str(work), environ={}, repo_root=repo,
                        prefix=prefix, run=slow, timeout=5)

    def broken(command, **options):
        raise PermissionError("accès refusé")

    with pytest.raises(foreign.ForeignError, match="impossible à lancer"):
        foreign.convert("cube.SLDPRT", str(work), environ={},
                        repo_root=repo, prefix=prefix, run=broken)


def test_missing_reader_points_to_opensw_in_both_languages(tmp_path):
    repo = tmp_path / "Freesolid"
    repo.mkdir()
    with pytest.raises(foreign.ForeignError) as missing:
        foreign.convert("cube.x_t", str(tmp_path), environ={}, repo_root=repo,
                        prefix=str(tmp_path))
    message = str(missing.value)
    assert foreign.READER_URL in message and foreign.READER_ENV in message
    assert i18n.translate(message, "en") == (
        "OpenSW reader missing — clone {} next to FreeSolid, or set its "
        "folder in {}".format(foreign.READER_URL, foreign.READER_ENV))
    with pytest.raises(foreign.ForeignError) as wrong:
        foreign.convert("cube.x_t", str(tmp_path),
                        environ={foreign.READER_ENV: str(repo)},
                        repo_root=repo, prefix=str(tmp_path))
    assert "ne désigne pas un dépôt OpenSW" in str(wrong.value)
    assert i18n.translate(
        "OpenSW n'a pas pu lire ce fichier : code de sortie 3", "en") == (
        "OpenSW could not read this file: exit code 3")
