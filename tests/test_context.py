"""Contextual-bar logic — runs without FreeCAD."""

import pytest

from freesolid.commands import ALIAS_NAMES, CORE_NAMES
from freesolid import context


@pytest.mark.parametrize("name,expected", [
    ("Face3", "face"),
    ("Face12", "face"),
    ("Edge5", "edge"),
    ("Vertex2", "edge"),   # dress-up applies to vertices too
    ("Wire1", "object"),
])
def test_subelement_kind(name, expected):
    assert context.subelement_kind(name) == expected


@pytest.mark.parametrize("kinds,expected", [
    ([], "none"),
    (["face"], "face"),
    (["face", "face"], "face"),
    (["edge", "edge"], "edge"),
    (["sketch"], "sketch"),
    (["face", "sketch"], "sketch"),          # a sketch in play wins
    (["face", "edge"], "mixed"),             # dress-up palette
    (["object", "face"], "object"),
    (["object"], "object"),
])
def test_classify(kinds, expected):
    assert context.classify(kinds) == expected


def test_every_context_has_a_palette():
    for ctx in context.CONTEXTS:
        assert context.commands_for(ctx), ctx


def test_unknown_context_falls_back_to_none():
    assert context.commands_for("weird") == context.BAR["none"]


def test_palettes_only_reference_registered_commands():
    known = set(ALIAS_NAMES) | set(CORE_NAMES)
    for ctx, names in context.BAR.items():
        missing = [n for n in names if n not in known]
        assert not missing, "{}: {}".format(ctx, missing)


def test_edge_palette_is_dressup_only():
    assert context.commands_for("edge") == (
        "FreeSolid_Fillet", "FreeSolid_Chamfer")
