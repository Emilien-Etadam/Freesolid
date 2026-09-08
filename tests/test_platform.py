"""Plateforme de référence FreeCAD — pur Python, sans FreeCAD."""

from pathlib import Path

from engine.platform import (
    FREECAD,
    OVERRIDE_ENV,
    REPO_URL,
    allow_from_environ,
    format_selftest_failure,
    freesolid_version,
    normalize_version,
    version_status,
)

_ROOT = Path(__file__).resolve().parent.parent


def test_freesolid_version_reads_the_version_file(tmp_path):
    assert freesolid_version() == (_ROOT / "VERSION").read_text().strip()
    fake = tmp_path / "VERSION"
    fake.write_text("9.8.7\n")
    assert freesolid_version(str(fake)) == "9.8.7"
    assert freesolid_version(str(tmp_path / "absent")) == "0.0.0-dev"
    fake.write_text("  \n")
    assert freesolid_version(str(fake)) == "0.0.0-dev"


def test_version_file_matches_desktop_app():
    # Une seule version affichée partout : VERSION et tauri.conf.json.
    import json
    conf = json.loads(
        (_ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"))
    assert conf["version"] == freesolid_version()


def test_repo_url_is_the_github_project():
    assert REPO_URL.startswith("https://github.com/")
    assert REPO_URL.endswith("/Freesolid")


def test_normalize_version_tuple_and_string():
    assert normalize_version((1, 1, 3)) == "1.1.3"
    assert normalize_version("1.1.3") == "1.1.3"
    assert normalize_version("1.1.3R39109") == "1.1.3"
    assert normalize_version(["1", "0", "0"]) == "1.0.0"


def test_same_version_matches():
    status = version_status("1.1.3")
    assert status["match"] is True
    assert status["override"] is False
    assert status["running"] == FREECAD
    assert status["reference"] == FREECAD


def test_different_version_fails_and_names_both():
    status = version_status("1.0.0")
    assert status["match"] is False
    assert status["override"] is False
    assert "1.0.0" in status["message"]
    assert FREECAD in status["message"]
    assert OVERRIDE_ENV in status["message"]


def test_explicit_override_marks_incomparable():
    status = version_status("1.0.0", allow="1.0.0")
    assert status["match"] is False
    assert status["override"] is True
    assert "repli explicite" in status["message"]
    assert "pas comparables" in status["message"]


def test_override_that_does_not_match_running_still_fails():
    status = version_status("1.0.0", allow="1.0.2")
    assert status["match"] is False
    assert status["override"] is False


def test_allow_from_environ():
    assert allow_from_environ({}) is None
    assert allow_from_environ({OVERRIDE_ENV: ""}) is None
    assert allow_from_environ({OVERRIDE_ENV: " 1.0.0 "}) == "1.0.0"


def test_format_selftest_failure_is_readable():
    text = format_selftest_failure(
        version={"running": "1.0.0", "reference": "1.1.3",
                 "message": "écart", "override": False},
        failed=["n9_spike_variable"],
    )
    assert text.startswith("SELFTEST ÉCHEC")
    assert "1.0.0" in text
    assert "1.1.3" in text
    assert "n9_spike_variable" in text


def test_ci_reads_platform_module():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "from engine.platform import FREECAD" in workflow
    assert "freecad=${{ steps.platform.outputs.freecad }}" in workflow
    assert workflow.count("freecad=${{ steps.platform.outputs.freecad }}") == 2


def test_ci_prints_failure_file_on_selftest_error():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "selftest-echecs.txt" in workflow
    assert "if: failure()" in workflow
