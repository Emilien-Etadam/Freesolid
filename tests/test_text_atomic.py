"""P032 : refus d'expression atomique + gravure rééditable (kernel FreeCAD)."""

import pytest

from engine.kernel import Kernel, KernelError


def _freecad_available():
    try:
        import FreeCAD  # noqa: F401
        return True
    except ImportError:
        return False


def _part_with_pattern(kernel):
    kernel.new_part("Atomique")
    kernel.add_rect_sketch(80, 80)
    tree = kernel.add_pad(14)
    pad = next(f["name"] for f in tree["features"]
               if f["type"] == "PartDesign::Pad")
    state = kernel.sketch_start(face=kernel._top_face_id())
    sk = state["sketch"]
    kernel.sketch_add_circle(sk, 28, 28, 3)
    kernel.sketch_finish(sk)
    kernel.add_hole(diameter=6, through=True)
    tree = kernel.add_polar_pattern(count=4, angle=360.0, axis="Z")
    pattern = next(f["name"] for f in tree["features"]
                   if f["type"] == "PartDesign::PolarPattern")
    return pad, pattern


@pytest.mark.skipif(not _freecad_available(), reason="FreeCAD requis")
class TestSetParamsAtomique:
    def setup_method(self):
        self.k = Kernel()

    def teardown_method(self):
        self.k._close_current()

    def test_expression_inconnue_sans_trace(self):
        pad, pattern = _part_with_pattern(self.k)
        with pytest.raises(KernelError):
            self.k.set_params(pattern, {"Occurrences": "inconnu_x"})
        obj = self.k._doc.getObject(pattern)
        assert not dict(obj.ExpressionEngine or [])
        assert "Invalid" not in (obj.State or ())
        # la barre bouge encore — c'était le symptôme utilisateur
        self.k.set_tip(pad)
        tree = self.k.tip_to_end()
        assert not any(f["error"] for f in tree["features"])

    def test_expression_inconnue_conserve_liaison_saine(self):
        pad, pattern = _part_with_pattern(self.k)
        self.k.set_variable("nb", 4.0)
        self.k.set_params(pattern, {"Occurrences": "Variables.nb"})
        obj = self.k._doc.getObject(pattern)
        before = dict(obj.ExpressionEngine or [])
        assert before  # liaison valide posée
        with pytest.raises(KernelError):
            self.k.set_params(pattern, {"Occurrences": "casse_tout"})
        obj = self.k._doc.getObject(pattern)
        assert dict(obj.ExpressionEngine or []) == before

    def test_virgule_decimale_est_un_nombre(self):
        pad, _pattern = _part_with_pattern(self.k)
        self.k.set_params(pad, {"Length": "15,5"})
        obj = self.k._doc.getObject(pad)
        assert not dict(obj.ExpressionEngine or [])
        assert abs(float(obj.Length) - 15.5) < 1e-9

    def test_set_param_atomique_aussi(self):
        _pad, pattern = _part_with_pattern(self.k)
        with pytest.raises(KernelError):
            self.k.set_param(pattern, "Occurrences", "zut_")
        obj = self.k._doc.getObject(pattern)
        assert not dict(obj.ExpressionEngine or [])


@pytest.mark.skipif(not _freecad_available(), reason="FreeCAD requis")
class TestGravureEditable:
    def setup_method(self):
        self.k = Kernel()

    def teardown_method(self):
        self.k._close_current()

    def _part_with_text(self):
        self.k.new_part("Gravée")
        self.k.add_rect_sketch(60, 20)
        self.k.add_pad(5)
        tree = self.k.add_text("AB", face=self.k._top_face_id(),
                               size=8, depth=1)
        return next(f for f in tree["features"]
                    if f["type"] == "PartDesign::Boolean")

    def _volume(self):
        return float(self.k._require_body().Shape.Volume)

    def test_add_text_volume_sain(self):
        # Régression P032 : les faces de glyphes sortaient inversées
        # (aire négative) — le corps gravé valait 17 mm³ au lieu de ~5960.
        self._part_with_text()
        shape = self.k._require_body().Shape
        assert shape.isValid()
        assert 5900.0 < float(shape.Volume) < 5999.9

    def test_edit_text_change_le_texte(self):
        gravure = self._part_with_text()
        assert gravure["text"]["text"] == "AB"
        tris = len(self.k.tessellate()["indices"])
        vol = self._volume()
        tree = self.k.edit_text(gravure["name"], text="CD", size=10)
        entry = next(f for f in tree["features"]
                     if f["name"] == gravure["name"])
        assert entry["text"] == {"text": "CD", "size": 10.0, "depth": 1.0,
                                 "x": 0.0, "y": 0.0}
        assert entry["label"].startswith("Gravure « CD »")
        assert len(self.k.tessellate()["indices"]) != tris
        assert not any(f["error"] for f in tree["features"])
        shape = self.k._require_body().Shape
        assert shape.isValid()
        assert abs(self._volume() - vol) < 100.0  # la pièce, pas le texte

    def test_edit_text_refus_atomique(self):
        gravure = self._part_with_text()
        tris = len(self.k.tessellate()["indices"])
        with pytest.raises(KernelError):
            self.k.edit_text(gravure["name"], text="   ")
        with pytest.raises(KernelError):
            self.k.edit_text(gravure["name"], size=-2)
        tree = self.k.get_tree()
        entry = next(f for f in tree["features"]
                     if f["name"] == gravure["name"])
        assert entry["text"]["text"] == "AB"
        assert len(self.k.tessellate()["indices"]) == tris
        assert not any(f["error"] for f in tree["features"])

    def test_artefacts_internes_caches(self):
        self._part_with_text()
        tree = self.k.get_tree()
        assert not any(s["label"] == "Forme du texte"
                       for s in tree["surfaces"])
        assert not any(b["label"] == "Corps texte" for b in tree["bodies"])
        mesh = self.k.tessellate()
        assert not any(s["label"] == "Forme du texte"
                       for s in mesh.get("surfaces") or [])

    def test_gravure_anterieure_refusee_proprement(self):
        gravure = self._part_with_text()
        obj = self.k._doc.getObject(gravure["name"])
        obj.removeProperty("FreeSolidTextString")
        with pytest.raises(KernelError, match="version antérieure"):
            self.k.edit_text(gravure["name"], text="X")
