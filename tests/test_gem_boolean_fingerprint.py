"""Empreinte du booléen de semis — gabarit et VarSet, sans FreeCAD."""

from engine.kernel import Kernel


class _VarSet:
    TypeId = "App::VarSet"
    PropertiesList = ("Label", "Visibility", "epaisseur", "diametre")
    Label = "Variables"
    Visibility = True
    diametre = 1.5
    epaisseur = 0.5


class _Place:
    class _Base:
        x, y, z = 1.0, 2.0, 3.0

    class _Rot:
        Q = (0.0, 0.0, 0.0, 1.0)

    Base = _Base()
    Rotation = _Rot()


class _Body:
    OutListRecursive = (_VarSet,)
    InListRecursive = ()


class _Link:
    Name = "Semis"
    FreeSolidGemTemplate = "cylindre-plat"
    LinkedObject = _Body()
    PlacementList = (_Place(),)


def test_fingerprint_signs_template_and_sorted_varset():
    fp = Kernel()._gem_placement_fingerprint(_Link())
    assert fp.startswith("Semis#cylindre-plat#")
    assert "diametre=1.500000" in fp
    assert "epaisseur=0.500000" in fp
    diametre_at = fp.index("diametre=1.500000")
    epaisseur_at = fp.index("epaisseur=0.500000")
    assert diametre_at < epaisseur_at
    assert "Visibility" not in fp
    assert "Label=" not in fp


def test_fingerprint_changes_when_diameter_changes():
    kernel = Kernel()
    before = kernel._gem_placement_fingerprint(_Link())
    _VarSet.diametre = 1.7
    try:
        after = kernel._gem_placement_fingerprint(_Link())
    finally:
        _VarSet.diametre = 1.5
    assert before != after
    assert "diametre=1.700000" in after


def test_fingerprint_changes_when_template_name_changes():
    kernel = Kernel()
    before = kernel._gem_placement_fingerprint(_Link())
    _Link.FreeSolidGemTemplate = "brillant-rond"
    try:
        after = kernel._gem_placement_fingerprint(_Link())
    finally:
        _Link.FreeSolidGemTemplate = "cylindre-plat"
    assert before != after
    assert "brillant-rond" in after
