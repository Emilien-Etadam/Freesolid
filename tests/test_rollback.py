"""Barre de retour : plan pur + kernel FreeCAD si disponible."""

import os
import tempfile

import pytest

from engine.kernel import Kernel, KernelError, rollback_plan, rollback_tips


def _hist(*rows):
    return [{"name": name, "order": order, "role": role}
            for name, order, role in rows]


def test_rollback_plan_bar_at_top():
    history = _hist(("Pad", 5, "feature"),
                    ("Sketch001", 8, "sketch"),
                    ("Surface", 10, "surface"))
    flags, tip = rollback_plan(history, None)
    assert tip is None
    assert flags == {"Sketch001": True, "Surface": True}


def test_rollback_plan_on_sketch():
    history = _hist(("Pad", 5, "feature"),
                    ("Sketch001", 8, "sketch"),
                    ("Surface", 10, "surface"))
    flags, tip = rollback_plan(history, "Sketch001")
    assert tip == "Pad"
    assert flags == {"Sketch001": False, "Surface": True}


def test_rollback_plan_on_surface():
    history = _hist(("Pad", 5, "feature"),
                    ("Sketch001", 8, "sketch"),
                    ("Surface", 10, "surface"))
    flags, tip = rollback_plan(history, "Surface")
    assert tip == "Pad"
    assert flags == {"Sketch001": False, "Surface": False}


def test_rollback_plan_on_pad():
    history = _hist(("Pad", 5, "feature"),
                    ("Sketch001", 8, "sketch"),
                    ("Surface", 10, "surface"))
    flags, tip = rollback_plan(history, "Pad")
    assert tip == "Pad"
    assert flags == {"Sketch001": True, "Surface": True}


def test_rollback_plan_unknown_raises():
    with pytest.raises(KernelError, match="ligne d'historique"):
        rollback_plan(_hist(("Pad", 1, "feature")), "Body")


def test_rollback_plan_surfaces_only():
    history = _hist(("Surface", 3, "surface"))
    flags, tip = rollback_plan(history, "Surface")
    assert tip is None
    assert flags == {"Surface": False}
    flags, tip = rollback_plan(history, None)
    assert tip is None
    assert flags == {"Surface": True}


def test_rollback_plan_empty():
    flags, tip = rollback_plan([], None)
    assert flags == {}
    assert tip is None


def _freecad_available():
    try:
        import FreeCAD  # noqa: F401
        return True
    except ImportError:
        return False


def _pad_free_sketch_surface(kernel):
    kernel.new_part("Reprise")
    kernel.add_rect_sketch(40, 20)
    tree = kernel.add_pad(10)
    pad = next(f["name"] for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    state = kernel.sketch_start()
    free_sk = state["sketch"]
    kernel.sketch_add_line(free_sk, 0, 0, 30, 0)
    kernel.sketch_finish(free_sk)
    state = kernel.sketch_start()
    surf_sk = state["sketch"]
    kernel.sketch_add_line(surf_sk, 0, 0, 20, 0)
    kernel.sketch_finish(surf_sk)
    tree = kernel.surface_extrude(15, sketch=surf_sk)
    surf = tree["surfaces"][-1]["name"]
    return pad, free_sk, surf


def _pad_then_pocket(kernel):
    kernel.new_part("Absorbée")
    kernel.add_rect_sketch(40, 20)
    tree = kernel.add_pad(10)
    pad = next(f["name"] for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    kernel.add_rect_sketch(10, 5, face=kernel._top_face_id())
    tree = kernel.add_pocket(through=True)
    item = next(f for f in tree["features"]
                if f["type"] == "PartDesign::Pocket")
    return pad, item["name"], item["children"][0]["name"]


def test_rollback_plan_on_absorbed_sketch():
    history = _hist(("Pad", 5, "feature"),
                    ("Sketch001", 6, "absorbed"),
                    ("Pocket", 7, "feature"),
                    ("Sketch002", 8, "sketch"))
    flags, tip = rollback_plan(history, "Sketch001")
    assert tip == "Pad"
    assert flags == {"Sketch002": True}


def _bodies(*rows):
    return [{"name": name, "order": order, "role": role, "body": body}
            for name, order, role, body in rows]


def test_rollback_tips_one_tip_per_body():
    # Deux corps entrelacés : chacun s'arrête sur sa dernière fonction
    # au-dessus de la barre.
    history = _bodies(("Pad", 1, "feature", "Body"),
                      ("Pad001", 2, "feature", "Body001"),
                      ("Pocket", 3, "feature", "Body"),
                      ("Sketch005", 4, "sketch", "Body001"),
                      ("Pad002", 5, "feature", "Body001"))
    flags, tips = rollback_tips(history, "Pocket")
    assert tips == {"Body": "Pocket", "Body001": "Pad001"}
    assert flags == {"Sketch005": True}


def test_rollback_tips_body_born_after_the_bar():
    history = _bodies(("Pad", 1, "feature", "Body"),
                      ("Pad001", 2, "feature", "Body001"))
    _, tips = rollback_tips(history, "Pad")
    assert tips == {"Body": "Pad", "Body001": None}


def test_rollback_tips_pattern_copies_born_with_the_pattern():
    # La base d'une copie a le rang de son réseau : la barre posée sur le
    # réseau la garde, posée au-dessus elle n'existe pas encore.
    history = _bodies(("Pad", 1, "feature", "Body"),
                      ("BodyPattern", 2, "pattern", None),
                      ("FeatureBase", 2, "feature", "Body001"),
                      ("Fillet", 3, "feature", "Body001"))
    assert rollback_tips(history, "BodyPattern")[1] == {
        "Body": "Pad", "Body001": "FeatureBase"}
    assert rollback_tips(history, "Pad")[1] == {"Body": "Pad", "Body001": None}
    assert rollback_tips(history, "Fillet")[1]["Body001"] == "Fillet"


def test_rollback_tips_bar_at_top_and_unknown():
    history = _bodies(("Pad", 1, "feature", "Body"),
                      ("Pad001", 2, "feature", "Body001"))
    assert rollback_tips(history, None)[1] == {"Body": None, "Body001": None}
    with pytest.raises(KernelError):
        rollback_tips(history, "Inconnue")


@pytest.mark.skipif(not _freecad_available(), reason="FreeCAD requis")
class TestRollbackKernel:
    def setup_method(self):
        self.k = Kernel()

    def teardown_method(self):
        self.k._close_current()

    def test_set_tip_on_sketch_and_surface(self):
        pad, free_sk, surf = _pad_free_sketch_surface(self.k)
        tree = self.k.set_tip(free_sk)
        free = next(f for f in tree["features"] if f["name"] == free_sk)
        surface = next(s for s in tree["surfaces"] if s["name"] == surf)
        assert tree["tip"] == pad
        assert free.get("rolled_back") is not True
        assert surface["rolled_back"] is True

        tree = self.k.set_tip(surf)
        surface = next(s for s in tree["surfaces"] if s["name"] == surf)
        assert tree["tip"] == pad
        assert surface.get("rolled_back") is not True

    def test_tessellate_excludes_rolled_back(self):
        pad, free_sk, surf = _pad_free_sketch_surface(self.k)
        self.k.set_tip(pad)
        mesh = self.k.tessellate()
        assert not any(s["name"] == surf for s in mesh.get("surfaces") or [])
        assert not any(s["name"] == free_sk for s in mesh.get("sketches") or [])
        tree = self.k.get_tree()
        free = next(f for f in tree["features"] if f["name"] == free_sk)
        surface = next(s for s in tree["surfaces"] if s["name"] == surf)
        assert free["rolled_back"] is True
        assert surface["rolled_back"] is True

    def test_latest_sketch_skips_rolled_back(self):
        pad, _free_sk, _surf = _pad_free_sketch_surface(self.k)
        self.k.set_tip(pad)
        with pytest.raises(KernelError, match="aucune esquisse disponible"):
            self.k._latest_sketch()

    def test_tip_to_end_restores(self):
        pad, free_sk, surf = _pad_free_sketch_surface(self.k)
        self.k.set_tip(pad)
        tree = self.k.tip_to_end()
        mesh = self.k.tessellate()
        free = next(f for f in tree["features"] if f["name"] == free_sk)
        surface = next(s for s in tree["surfaces"] if s["name"] == surf)
        assert tree["tip"] == pad
        assert free.get("rolled_back") is not True
        assert surface.get("rolled_back") is not True
        assert any(s["name"] == surf for s in mesh.get("surfaces") or [])
        assert any(s["name"] == free_sk for s in mesh.get("sketches") or [])

    def test_tip_to_end_without_volume_feature(self):
        self.k.new_part("Surfaces seules")
        state = self.k.sketch_start()
        sk = state["sketch"]
        self.k.sketch_add_line(sk, 0, 0, 20, 0)
        self.k.sketch_finish(sk)
        self.k.surface_extrude(10, sketch=sk)
        self.k.set_tip()
        tree = self.k.tip_to_end()
        assert tree["tip"] is None
        assert all(not s.get("rolled_back") for s in tree["surfaces"])

    def test_set_tip_rejects_non_history(self):
        self.k.new_part("Rejet")
        tree = self.k.get_tree()
        with pytest.raises(KernelError, match="ligne d'historique"):
            self.k.set_tip(tree["bodies"][0]["name"])
        with pytest.raises(KernelError, match="fonction inconnue"):
            self.k.set_tip("InconnuXYZ")

    def test_set_tip_between_sketch_and_feature(self):
        pad, pocket, pocket_sk = _pad_then_pocket(self.k)
        tree = self.k.set_tip(pocket_sk)
        assert tree["tip"] == pad
        item = next(f for f in tree["features"] if f["name"] == pocket)
        child = next(c for c in item["children"] if c["name"] == pocket_sk)
        assert child.get("unabsorbed") is True
        mesh = self.k.tessellate()
        assert any(s["name"] == pocket_sk for s in mesh.get("sketches") or [])
        # La barre sur la fonction : l'esquisse rentre dessous.
        tree = self.k.tip_to_end()
        item = next(f for f in tree["features"] if f["name"] == pocket)
        assert all(not c.get("unabsorbed") for c in item["children"])
        mesh = self.k.tessellate()
        assert not any(s["name"] == pocket_sk
                       for s in mesh.get("sketches") or [])

    def test_bar_above_feature_keeps_sketch_absorbed(self):
        pad, pocket, _pocket_sk = _pad_then_pocket(self.k)
        tree = self.k.set_tip(pad)
        item = next(f for f in tree["features"] if f["name"] == pocket)
        assert all(not c.get("unabsorbed") for c in item["children"])

    def test_delete_rolled_back(self):
        pad, pocket, pocket_sk = _pad_then_pocket(self.k)
        self.k.set_tip(pad)
        tree = self.k.delete_rolled_back()
        names = {f["name"] for f in tree["features"]}
        assert pocket not in names and pocket_sk not in names
        assert tree["tip"] == pad
        with pytest.raises(KernelError, match="rien sous la barre"):
            self.k.delete_rolled_back()

    def test_delete_rolled_back_keeps_unabsorbed_sketch(self):
        pad, pocket, pocket_sk = _pad_then_pocket(self.k)
        self.k.set_tip(pocket_sk)
        tree = self.k.delete_rolled_back()
        names = {f["name"] for f in tree["features"]}
        assert pocket not in names
        free = next(f for f in tree["features"] if f["name"] == pocket_sk)
        assert free.get("rolled_back") is not True

    def test_flags_persist_save_reopen(self):
        pad, free_sk, surf = _pad_free_sketch_surface(self.k)
        self.k.set_tip(pad)
        path = os.path.join(tempfile.gettempdir(),
                            "freesolid-p030-rollback.FCStd")
        self.k.save_part(path)
        tree = self.k.open_part(path)
        free = next(f for f in tree["features"] if f["name"] == free_sk)
        surface = next(s for s in tree["surfaces"] if s["name"] == surf)
        assert free["rolled_back"] is True
        assert surface["rolled_back"] is True
        mesh = self.k.tessellate()
        assert not any(s["name"] == surf for s in mesh.get("surfaces") or [])
        assert not any(s["name"] == free_sk for s in mesh.get("sketches") or [])
