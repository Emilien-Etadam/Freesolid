"""Extraction des sous-éléments de LinkSub — sans FreeCAD."""

from engine.kernel import Kernel


class _Obj:
    def __init__(self, name):
        self.Name = name


def test_iter_link_sub_tuple():
    pad = _Obj("Pad")
    pairs = list(Kernel._iter_link_subs((pad, ["Edge3", "Edge7"])))
    assert len(pairs) == 1
    assert pairs[0][0] is pad
    assert pairs[0][1] == ["Edge3", "Edge7"]


def test_iter_link_sub_list_of_pairs():
    pad = _Obj("Pad")
    pairs = list(Kernel._iter_link_subs([(pad, ("Face3",))]))
    assert len(pairs) == 1
    assert pairs[0][1] == ["Face3"]


def test_iter_link_sub_bare_object_has_no_subs():
    sketch = _Obj("Sketch")
    pairs = list(Kernel._iter_link_subs(sketch))
    assert pairs == [(sketch, [])]


def test_iter_link_sub_empty():
    assert list(Kernel._iter_link_subs(None)) == []
    assert list(Kernel._iter_link_subs([])) == []
