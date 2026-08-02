"""Selection-context logic for the "S" contextual bar.

Pure Python on purpose — no FreeCAD, no Qt — so the mapping from "what is
selected" to "which commands the bar offers" is unit-testable in CI. The Qt
popup itself lives in ``freesolid.ui.context_bar`` and consumes this module.

The contexts mirror SolidWorks' shortcut bar behaviour: the palette changes
with the selection (nothing / face / edge / sketch), it does not merely
reposition a fixed toolbar.
"""

#: Selection contexts, in the vocabulary of the designer, not of OCC.
CONTEXTS = ("none", "face", "edge", "sketch", "object", "mixed")

#: Context -> commands offered by the bar, in display order.
#: Names are FreeSolid aliases so the bar shows the designer-facing labels
#: and inherits the PartDesign icons.
BAR: dict[str, tuple[str, ...]] = {
    # Nothing selected: start something.
    "none": ("FreeSolid_NewSketch", "FreeSolid_Pad", "FreeSolid_Pocket",
             "FreeSolid_Revolution", "FreeSolid_Hole"),
    # A face: sketch on it, cut into it, drill it, dress it.
    "face": ("FreeSolid_NewSketch", "FreeSolid_Pad", "FreeSolid_Pocket",
             "FreeSolid_Hole", "FreeSolid_Fillet", "FreeSolid_Chamfer"),
    # An edge: dress-up only.
    "edge": ("FreeSolid_Fillet", "FreeSolid_Chamfer"),
    # A sketch: turn it into a feature.
    "sketch": ("FreeSolid_Pad", "FreeSolid_Pocket", "FreeSolid_Revolution",
               "FreeSolid_Groove"),
    # A whole object without sub-element: same as nothing, minus the sketch
    # (sketching needs a plane or face, not a solid).
    "object": ("FreeSolid_Pad", "FreeSolid_Pocket", "FreeSolid_Revolution",
               "FreeSolid_Hole"),
    # Faces and edges together: only what applies to both.
    "mixed": ("FreeSolid_Fillet", "FreeSolid_Chamfer"),
}


def subelement_kind(name: str) -> str:
    """Kind of an OCC sub-element name (``Face3`` -> ``face``)."""
    for prefix, kind in (("Face", "face"), ("Edge", "edge"),
                         ("Vertex", "edge")):
        # Vertices get edge treatment: fillet/chamfer apply there too.
        if name.startswith(prefix):
            return kind
    return "object"


def classify(kinds: list[str]) -> str:
    """Reduce a list of selected kinds to one bar context.

    Priority: an empty selection is ``none``; any sketch wins (the designer
    just closed it and wants to use it); a homogeneous selection keeps its
    kind; faces mixed with edges fall back to the dress-up palette.
    """
    if not kinds:
        return "none"
    if "sketch" in kinds:
        return "sketch"
    unique = set(kinds)
    if len(unique) == 1:
        return kinds[0]
    if unique <= {"face", "edge"}:
        return "mixed"
    return "object"


def commands_for(context: str) -> tuple[str, ...]:
    """Commands the bar shows for a context; unknown contexts get ``none``."""
    return BAR.get(context, BAR["none"])
