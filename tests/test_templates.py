"""Gabarits — parties pures."""
import os

from engine.templates import clean_template_name, template_dir


def test_template_dir_prefers_the_data_dir():
    assert template_dir({"FREESOLID_DATA_DIR": "/data"}) == os.path.join(
        "/data", "Gabarits")
    assert template_dir({}, home="/home/x") == os.path.join(
        "/home/x", "FreeSolid", "Gabarits")


def test_template_names_stay_plain():
    assert clean_template_name("  Tôle alu 2 ") == "Tôle alu 2"
    assert clean_template_name("../évasion") is None
    assert clean_template_name(".cache") is None
    assert clean_template_name("") is None
