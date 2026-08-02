"""Alias command resources — runs without FreeCAD.

``commands.py`` imports FreeCAD only inside function bodies, so the module
itself is importable in CI and the resource-building logic can be checked.
"""

from freesolid.commands import ALIAS_NAMES, AliasCommand
from freesolid.vocab import BY_COMMAND, TERMS


def test_alias_names_match_terms():
    assert len(ALIAS_NAMES) == len(TERMS)
    assert len(set(ALIAS_NAMES)) == len(ALIAS_NAMES)
    assert all(name.startswith("FreeSolid_") for name in ALIAS_NAMES)


def test_alias_names_do_not_collide_with_core_commands():
    core = {"FreeSolid_Setup", "FreeSolid_NewPart", "FreeSolid_FeatureManager"}
    assert core.isdisjoint(ALIAS_NAMES)


def test_resources_carry_the_designer_facing_name():
    resources = AliasCommand(BY_COMMAND["PartDesign_Pad"]).GetResources()
    assert resources["MenuText"] == "Bossage/Base extrudé"
    assert resources["ToolTip"]


def test_every_alias_declares_a_pixmap():
    # Without one FreeCAD renders text labels, which overflow the toolbar.
    for term in TERMS:
        resources = AliasCommand(term).GetResources()
        assert resources.get("Pixmap"), term.command


def test_pixmap_falls_back_to_the_command_name_outside_freecad():
    # Here FreeCADGui is absent, so the lookup fails and the fallback applies.
    resources = AliasCommand(BY_COMMAND["PartDesign_Hole"]).GetResources()
    assert resources["Pixmap"] == "PartDesign_Hole"


def test_note_is_used_as_tooltip_when_present():
    term = BY_COMMAND["PartDesign_Hole"]
    assert term.note
    assert AliasCommand(term).GetResources()["ToolTip"] == term.note
