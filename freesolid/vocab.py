"""SolidWorks <-> FreeCAD vocabulary.

Single source of truth for the terminology mapping. Consumed by:

- ``freesolid.commands.aliases`` — to register commands carrying the names
  a mechanical designer already knows.
- ``freesolid.ui.feature_manager`` — to label rows in the feature tree.

Pure Python on purpose: no FreeCAD import, so it is unit-testable in CI.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    """One entry of the mapping.

    Attributes:
        command: the FreeCAD command name, as passed to ``Gui.runCommand``.
        obj_type: the document object type the command produces, used to
            label existing features in the tree. ``""`` when the command
            creates nothing (view commands, for instance).
        fr: the French term a SolidWorks user expects.
        en: the English term a SolidWorks user expects.
        note: a short hint shown as a tooltip, used to flag the places where
            FreeCAD genuinely diverges rather than merely renaming things.
    """

    command: str
    obj_type: str
    fr: str
    en: str
    note: str = ""


#: Ordered so a ribbon/toolbar built from this table reads like a
#: CommandManager "Features" tab rather than an alphabetical dump.
TERMS: tuple[Term, ...] = (
    Term("PartDesign_Pad", "PartDesign::Pad",
         "Bossage/Base extrudé", "Extruded Boss/Base"),
    Term("PartDesign_Pocket", "PartDesign::Pocket",
         "Enlèvement de matière extrudé", "Extruded Cut"),
    Term("PartDesign_Revolution", "PartDesign::Revolution",
         "Bossage/Base avec révolution", "Revolved Boss/Base"),
    Term("PartDesign_Groove", "PartDesign::Groove",
         "Enlèvement de matière avec révolution", "Revolved Cut"),
    Term("PartDesign_AdditivePipe", "PartDesign::AdditivePipe",
         "Bossage/Base balayé", "Swept Boss/Base"),
    Term("PartDesign_SubtractivePipe", "PartDesign::SubtractivePipe",
         "Enlèvement de matière balayé", "Swept Cut"),
    Term("PartDesign_AdditiveLoft", "PartDesign::AdditiveLoft",
         "Bossage/Base lissé", "Lofted Boss/Base"),
    Term("PartDesign_SubtractiveLoft", "PartDesign::SubtractiveLoft",
         "Enlèvement de matière lissé", "Lofted Cut"),
    Term("PartDesign_Hole", "PartDesign::Hole",
         "Assistant de perçage", "Hole Wizard",
         "Filetages normalisés ISO/ANSI intégrés, comme l'assistant SW."),
    Term("PartDesign_Fillet", "PartDesign::Fillet",
         "Congé", "Fillet"),
    Term("PartDesign_Chamfer", "PartDesign::Chamfer",
         "Chanfrein", "Chamfer"),
    Term("PartDesign_Draft", "PartDesign::Draft",
         "Dépouille", "Draft"),
    Term("PartDesign_Thickness", "PartDesign::Thickness",
         "Coque", "Shell"),
    Term("PartDesign_LinearPattern", "PartDesign::LinearPattern",
         "Répétition linéaire", "Linear Pattern"),
    Term("PartDesign_PolarPattern", "PartDesign::PolarPattern",
         "Répétition circulaire", "Circular Pattern"),
    Term("PartDesign_Mirrored", "PartDesign::Mirrored",
         "Symétrie", "Mirror"),
    Term("PartDesign_NewSketch", "Sketcher::SketchObject",
         "Esquisse", "Sketch"),
    Term("PartDesign_Body", "PartDesign::Body",
         "Pièce", "Part",
         "Un Body = un fichier .sldprt. Un document FreeCAD peut en "
         "contenir plusieurs."),
)

#: FreeCAD Origin plane internal names -> the SolidWorks reference planes.
#: FreeCAD is Z-up, SolidWorks is Y-up, hence XY->Dessus and XZ->Face.
ORIGIN_PLANES: dict[str, tuple[str, str]] = {
    "XY_Plane": ("Plan de dessus", "Top Plane"),
    "XZ_Plane": ("Plan de face", "Front Plane"),
    "YZ_Plane": ("Plan de droite", "Right Plane"),
}

ORIGIN_AXES: dict[str, tuple[str, str]] = {
    "X_Axis": ("Axe X", "X Axis"),
    "Y_Axis": ("Axe Y", "Y Axis"),
    "Z_Axis": ("Axe Z", "Z Axis"),
}


def _by(attr: str) -> dict[str, Term]:
    return {getattr(t, attr): t for t in TERMS if getattr(t, attr)}


BY_COMMAND: dict[str, Term] = _by("command")
BY_TYPE: dict[str, Term] = _by("obj_type")


def label_for_type(obj_type: str, lang: str = "fr") -> str:
    """Return the designer-facing name for a document object type.

    Falls back to the raw FreeCAD type stripped of its namespace, so an
    unmapped feature still shows something readable instead of nothing.
    """
    term = BY_TYPE.get(obj_type)
    if term is not None:
        return term.fr if lang == "fr" else term.en
    return obj_type.split("::")[-1]


def label_for_origin(internal_name: str, lang: str = "fr") -> str:
    """Return the SolidWorks name of an Origin plane or axis.

    ``internal_name`` is matched on a suffix basis because FreeCAD appends a
    numeric suffix (``XY_Plane001``) once a document holds several Bodies.
    """
    for table in (ORIGIN_PLANES, ORIGIN_AXES):
        for key, (fr, en) in table.items():
            if internal_name.startswith(key):
                return fr if lang == "fr" else en
    return internal_name
